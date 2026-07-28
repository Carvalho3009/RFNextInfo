"""Ingestão offline de ETL/PCAPNG/PCAP usando o decoder canônico."""

from __future__ import annotations

import importlib.util
import os
import struct
import subprocess
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, Iterator

SENSITIVE_OPCODE = 0x0101


def load_decoder(path: Path | None = None) -> ModuleType:
    candidates = [
        path,
        Path(__file__).with_name("rfnext_frame_decode.py"),
        Path(os.environ["RFNEXT_DECODER_PATH"]) if os.environ.get("RFNEXT_DECODER_PATH") else None,
        Path(r"K:\MCP\Karvalho\rf-next\analysis\1.28.5\rfnext_frame_decode.py"),
    ]
    decoder_path = next((candidate for candidate in candidates if candidate and candidate.is_file()), None)
    if decoder_path is None:
        raise RuntimeError("decoder canônico não foi empacotado ou configurado")
    spec = importlib.util.spec_from_file_location("rfnext_info_decoder", decoder_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("não foi possível carregar o decoder canônico")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pcapng_to_pcap(source: Path, target: Path) -> None:
    """Converte os blocos padrão emitidos pelo Pktmon; metadados ETL ficam fora."""
    raw = source.read_bytes()
    cursor = 0
    endian = "<"
    interfaces: list[tuple[int, int]] = []
    packets: list[tuple[int, bytes, int]] = []
    while cursor + 12 <= len(raw):
        block_type_bytes = raw[cursor : cursor + 4]
        if block_type_bytes == b"\x0a\x0d\x0d\x0a":
            magic = raw[cursor + 8 : cursor + 12]
            endian = "<" if magic == b"\x4d\x3c\x2b\x1a" else ">" if magic == b"\x1a\x2b\x3c\x4d" else ""
            if not endian:
                raise ValueError("PCAPNG com byte-order magic inválido")
            interfaces.clear()
        block_type, block_len = struct.unpack_from(endian + "II", raw, cursor)
        if block_len < 12 or cursor + block_len > len(raw):
            raise ValueError("PCAPNG truncado ou bloco inválido")
        body = raw[cursor + 8 : cursor + block_len - 4]
        if block_type == 1:
            linktype = struct.unpack_from(endian + "H", body)[0]
            ts_to_ns = 1_000  # resolução padrão: microssegundos
            option = 8
            while option + 4 <= len(body):
                code, length = struct.unpack_from(endian + "HH", body, option)
                value = body[option + 4 : option + 4 + length]
                if code == 9 and value:
                    resolution = value[0]
                    if resolution & 0x80:
                        raise ValueError("resolução binária PCAPNG ainda não suportada")
                    if resolution > 9:
                        raise ValueError("resolução PCAPNG inferior a nanossegundo não suportada")
                    ts_to_ns = 10 ** (9 - resolution)
                option += 4 + ((length + 3) & ~3)
                if code == 0:
                    break
            interfaces.append((linktype, ts_to_ns))
        elif block_type == 6:
            interface_id, high, low, captured, original = struct.unpack_from(endian + "IIIII", body)
            if interface_id >= len(interfaces) or 20 + captured > len(body):
                raise ValueError("EPB PCAPNG inválido")
            linktype, ts_to_ns = interfaces[interface_id]
            timestamp_ns = ((high << 32) | low) * ts_to_ns
            packets.append((timestamp_ns, body[20 : 20 + captured], original))
        cursor += block_len
    linktypes = {item[0] for item in interfaces}
    if not packets or len(linktypes) != 1 or next(iter(linktypes)) not in (1, 113):
        raise ValueError("PCAPNG sem pacotes Ethernet/Linux SLL compatíveis")
    with target.open("wb") as output:
        output.write(struct.pack("<IHHIIII", 0xA1B23C4D, 2, 4, 0, 0, 0xFFFF, next(iter(linktypes))))
        for timestamp_ns, packet, original in packets:
            seconds, fraction = divmod(timestamp_ns, 1_000_000_000)
            output.write(struct.pack("<IIII", seconds, fraction, len(packet), original))
            output.write(packet)


def _to_pcap(source: Path, work_dir: Path) -> Path:
    suffix = source.suffix.lower()
    if suffix == ".pcap":
        return source
    pcapng = source
    if suffix == ".etl":
        pcapng = work_dir / f"{source.stem}.pcapng"
        result = subprocess.run(
            ["pktmon", "etl2pcap", str(source), "--out", str(pcapng)],
            capture_output=True, text=True, timeout=300,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout).strip())
    if pcapng.suffix.lower() != ".pcapng":
        raise ValueError("formato aceito: .etl, .pcapng ou .pcap")
    target = work_dir / f"{source.stem}.pcap"
    _pcapng_to_pcap(pcapng, target)
    return target


def decoded_events(
    source: Path,
    *,
    decoder_path: Path | None = None,
    ports: tuple[int, ...] = (12000, 12020),
) -> Iterator[dict[str, Any]]:
    decoder = load_decoder(decoder_path)
    with tempfile.TemporaryDirectory(prefix="rf-next-info-") as temp:
        pcap = _to_pcap(Path(source), Path(temp))
        for port in ports:
            for flow, stream, spans in decoder.pcap_tcp_streams(pcap, port):
                time_cursor = 0
                try:
                    outer_frames = decoder.decode_stream(stream)
                except decoder.DecodeError:
                    continue
                for outer_decoded, outer_info in outer_frames:
                    if spans:
                        frame_end = outer_info["stream_offset"] + outer_info["wire_length"]
                        while time_cursor + 1 < len(spans) and spans[time_cursor][0] < frame_end:
                            time_cursor += 1
                        outer_info["pcap_time_ns"] = spans[time_cursor][1]
                    for bundle_seq, (decoded, info) in enumerate(decoder.expand_bundle(outer_decoded, outer_info)):
                        opcode = int(info["opcode"])
                        if opcode == SENSITIVE_OPCODE:
                            continue
                        parsed = (
                            decoder.parse_exchange_payload(decoded)
                            or decoder.parse_collection_payload(decoded)
                            or decoder.parse_observation_payload(decoded)
                            or decoder.parse_marked_gameplay_payload(decoded, port)
                        )
                        if parsed is None:
                            continue
                        yield {
                            "source": str(source),
                            "flow": flow,
                            "stream_offset": int(info["stream_offset"]),
                            "bundle_seq": bundle_seq,
                            "ts_ns": info.get("pcap_time_ns"),
                            "opcode": opcode,
                            "type": parsed.get("type") or parsed.get("message") or "decoded",
                            "data": parsed,
                        }
