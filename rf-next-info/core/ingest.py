"""Ingestão offline de ETL/PCAPNG/PCAP usando o decoder canônico."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import struct
import subprocess
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, Iterator

SENSITIVE_OPCODE = 0x0101
DEFAULT_PORTS = (12000, 12010, 12020, 12040)
INGESTION_VERSION = 3


def _decoder_file(path: Path | None = None) -> Path:
    candidates = [
        path,
        Path(os.environ["RFNEXT_DECODER_PATH"]) if os.environ.get("RFNEXT_DECODER_PATH") else None,
        Path(__file__).with_name("rfnext_frame_decode.py"),
        Path(r"K:\MCP\Karvalho\rf-next\analysis\1.28.5\rfnext_frame_decode.py"),
    ]
    decoder_path = next((candidate for candidate in candidates if candidate and candidate.is_file()), None)
    if decoder_path is None:
        raise RuntimeError("decoder canônico não foi empacotado ou configurado")
    return decoder_path


def decoder_identity(
    path: Path | None = None, ports: tuple[int, ...] = DEFAULT_PORTS
) -> str:
    digest = hashlib.sha256(_decoder_file(path).read_bytes())
    digest.update(f"|ingest={INGESTION_VERSION}|".encode())
    catalog = Path(__file__).with_name("collection_requirements.csv")
    if catalog.is_file():
        digest.update(hashlib.sha256(catalog.read_bytes()).digest())
    digest.update(",".join(str(port) for port in sorted(set(ports))).encode())
    return digest.hexdigest()


def load_decoder(path: Path | None = None) -> ModuleType:
    decoder_path = _decoder_file(path)
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
    packets: list[tuple[int, bytes, int, int]] = []
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
            if len(body) < 8:
                raise ValueError("IDB PCAPNG truncado")
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
            if len(body) < 20:
                raise ValueError("EPB PCAPNG truncado")
            interface_id, high, low, captured, original = struct.unpack_from(endian + "IIIII", body)
            if interface_id >= len(interfaces) or 20 + captured > len(body):
                raise ValueError("EPB PCAPNG inválido")
            linktype, ts_to_ns = interfaces[interface_id]
            timestamp_ns = ((high << 32) | low) * ts_to_ns
            packets.append(
                (timestamp_ns, body[20 : 20 + captured], original, linktype)
            )
        cursor += block_len
    packets = [packet for packet in packets if packet[3] in (1, 113)]
    linktypes = {packet[3] for packet in packets}
    if not packets:
        raise ValueError(
            f"PCAPNG sem pacotes utilizáveis "
            f"(bytes={len(raw)}, interfaces={len(interfaces)}, pacotes=0)"
        )
    if len(linktypes) != 1:
        raise ValueError(
            f"PCAPNG com múltiplos linktypes de pacotes: {sorted(linktypes)}"
        )
    with target.open("wb") as output:
        output.write(struct.pack("<IHHIIII", 0xA1B23C4D, 2, 4, 0, 0, 0xFFFF, next(iter(linktypes))))
        for timestamp_ns, packet, original, _linktype in packets:
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


def _safe_parse(
    decoder: ModuleType,
    decoded: bytes,
    port: int,
    collection_slots: dict | None = None,
) -> dict[str, Any] | None:
    try:
        parsed = (
            decoder.parse_exchange_payload(decoded)
            or decoder.parse_collection_payload(decoded)
            or decoder.parse_observation_payload(decoded)
            or decoder.parse_marked_gameplay_payload(decoded, port)
            or getattr(decoder, "parse_inventory_payload", lambda _value: None)(
                decoded
            )
            or decoder.parse_job1_payload(decoded)
        )
        if parsed is None and port == 12000:
            login = decoder.parse_login_session_payload(decoded, port)
            if login and login.get("type") == "ans_all_character_infos":
                characters = []
                for item in login.get("fields", {}).get("characters") or []:
                    if not isinstance(item, dict):
                        continue
                    characters.append(
                        {
                            "character_uid": item.get("character_uid"),
                            "level": item.get("level"),
                            "name": item.get("name"),
                            "world_id": item.get("world_id"),
                            "guild_name": item.get("guild_name"),
                        }
                    )
                parsed = {
                    "type": "ans_all_character_infos",
                    "opcode": "0x010d",
                    "message": "FA2C_ans_all_character_infos_Message",
                    "direction": "FA2C",
                    "confidence": login.get("confidence"),
                    "fields": {
                        "character_count": len(characters),
                        "characters": characters,
                    },
                }
    except (decoder.DecodeError, struct.error, ValueError, IndexError):
        return None
    if (
        parsed
        and collection_slots
        and str(parsed.get("type", "")).startswith("collection_")
    ):
        try:
            decoder.add_collection_catalog(parsed, collection_slots)
        except (decoder.DecodeError, struct.error, ValueError, IndexError):
            pass
    return parsed


def _frame_at(
    decoder: ModuleType, stream: bytes, offset: int
) -> tuple[bytes, dict[str, Any], int]:
    if len(stream) - offset < 6:
        raise decoder.DecodeError("cabeçalho incompleto")
    length = int(decoder.frame_length_from_wire(stream[offset : offset + 3]))
    end = offset + length
    if length < 6 or end > len(stream):
        raise decoder.DecodeError("frame truncado")
    decoded, info = decoder.decode_frame(stream[offset:end])
    info["stream_offset"] = offset
    return decoded, info, end


def _decode_stream_resync(
    decoder: ModuleType, stream: bytes
) -> list[tuple[bytes, dict[str, Any]]]:
    try:
        return decoder.decode_stream(stream)
    except decoder.DecodeError:
        pass
    recovered: list[tuple[bytes, dict[str, Any]]] = []
    cursor = 0
    while cursor + 6 <= len(stream):
        candidate: list[tuple[bytes, dict[str, Any]]] = []
        next_offset = cursor
        while next_offset + 6 <= len(stream):
            try:
                decoded, info, next_offset = _frame_at(
                    decoder, stream, next_offset
                )
            except decoder.DecodeError:
                break
            candidate.append((decoded, info))
        if len(candidate) >= 3:
            recovered.extend(candidate)
            cursor = max(next_offset, cursor + 1)
        else:
            cursor += 1
    return recovered


def decoded_events(
    source: Path,
    *,
    decoder_path: Path | None = None,
    ports: tuple[int, ...] = DEFAULT_PORTS,
) -> Iterator[dict[str, Any]]:
    decoder = load_decoder(decoder_path)
    catalog_path = Path(__file__).with_name("collection_requirements.csv")
    collection_slots = decoder.load_collection_slots(
        catalog_path if catalog_path.is_file() else None
    )
    with tempfile.TemporaryDirectory(prefix="rf-next-info-") as temp:
        pcap = _to_pcap(Path(source), Path(temp))
        for port in ports:
            for flow, stream, spans in decoder.pcap_tcp_streams(pcap, port):
                appearances = []
                time_cursor = 0
                outer_frames = _decode_stream_resync(decoder, stream)
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
                        parsed = _safe_parse(decoder, decoded, port, collection_slots)
                        if parsed is None:
                            if port != 12000:
                                yield {
                                    "source": str(source),
                                    "flow": flow,
                                    "stream_offset": int(info["stream_offset"]),
                                    "bundle_seq": bundle_seq,
                                    "ts_ns": info.get("pcap_time_ns"),
                                    "opcode": opcode,
                                    "type": "unparsed",
                                    "data": {
                                        "port": port,
                                        "decoded_size": len(decoded),
                                        "confidence": "unparsed_no_payload",
                                    },
                                }
                            continue
                        if parsed.get("type") == "appear_player_prefix":
                            if parsed.get("fields", {}).get("equipment_refs"):
                                appearances.append(parsed)
                                appearances = appearances[-64:]
                        elif parsed.get("type") == "player_profile_info":
                            correlated = decoder.correlate_active_equipment(
                                parsed, appearances
                            )
                            if correlated is not None:
                                active_equipment, appearance = correlated
                                parsed["fields"]["active_equipment"] = active_equipment
                                appearance["fields"]["active_equipment"] = (
                                    active_equipment
                                )
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
