#!/usr/bin/env python3
import argparse
import collections
import ipaddress
import json
import math
import socket
import struct
from pathlib import Path


def entropy(counter):
    total = sum(counter.values())
    return 0.0 if not total else -sum((n / total) * math.log2(n / total) for n in counter.values())


def strings(data, minimum=5):
    found, current = [], bytearray()
    for byte in data:
        if 32 <= byte < 127:
            current.append(byte)
        else:
            if len(current) >= minimum:
                found.append(current.decode("ascii"))
            current.clear()
    if len(current) >= minimum:
        found.append(current.decode("ascii"))
    return found


def dns_name(data, offset, seen=None):
    seen = set() if seen is None else seen
    labels, end = [], offset
    while end < len(data):
        length = data[end]
        if length == 0:
            return ".".join(labels), end + 1
        if length & 0xC0 == 0xC0 and end + 1 < len(data):
            pointer = ((length & 0x3F) << 8) | data[end + 1]
            if pointer in seen:
                return ".".join(labels), end + 2
            suffix, _ = dns_name(data, pointer, seen | {pointer})
            if suffix:
                labels.append(suffix)
            return ".".join(labels), end + 2
        end += 1
        if end + length > len(data):
            break
        labels.append(data[end:end + length].decode("ascii", "replace"))
        end += length
    return ".".join(labels), end


def parse_dns(data):
    if len(data) < 12:
        return [], []
    _, flags, qd, an, _, _ = struct.unpack_from("!HHHHHH", data)
    offset, queries, answers = 12, [] , []
    for _ in range(qd):
        name, offset = dns_name(data, offset)
        if offset + 4 > len(data):
            return queries, answers
        qtype, _ = struct.unpack_from("!HH", data, offset)
        offset += 4
        queries.append((name, qtype))
    if not flags & 0x8000:
        return queries, answers
    for _ in range(an):
        name, offset = dns_name(data, offset)
        if offset + 10 > len(data):
            break
        rtype, _, _, rdlen = struct.unpack_from("!HHIH", data, offset)
        offset += 10
        rdata = data[offset:offset + rdlen]
        offset += rdlen
        if rtype == 1 and len(rdata) == 4:
            answers.append((name, socket.inet_ntop(socket.AF_INET, rdata)))
        elif rtype == 28 and len(rdata) == 16:
            answers.append((name, socket.inet_ntop(socket.AF_INET6, rdata)))
        elif rtype == 5:
            target, _ = dns_name(data, offset - rdlen)
            answers.append((name, target))
    return queries, answers


def client_hello(body):
    if len(body) < 38:
        return None
    version = body[:2].hex()
    offset = 34
    sid_len = body[offset]
    offset += 1 + sid_len
    if offset + 2 > len(body):
        return None
    cipher_len = struct.unpack_from("!H", body, offset)[0]
    ciphers = [body[i:i + 2].hex() for i in range(offset + 2, min(offset + 2 + cipher_len, len(body)), 2)]
    offset += 2 + cipher_len
    if offset >= len(body):
        return {"legacy_version": version, "ciphers": ciphers, "sni": [], "alpn": []}
    compression_len = body[offset]
    offset += 1 + compression_len
    if offset + 2 > len(body):
        return {"legacy_version": version, "ciphers": ciphers, "sni": [], "alpn": []}
    ext_total = struct.unpack_from("!H", body, offset)[0]
    offset += 2
    end, sni, alpn, versions = min(offset + ext_total, len(body)), [], [], []
    while offset + 4 <= end:
        ext_type, ext_len = struct.unpack_from("!HH", body, offset)
        value = body[offset + 4:offset + 4 + ext_len]
        offset += 4 + ext_len
        if ext_type == 0 and len(value) >= 5:
            pos = 2
            while pos + 3 <= len(value):
                kind, length = value[pos], struct.unpack_from("!H", value, pos + 1)[0]
                pos += 3
                if kind == 0:
                    sni.append(value[pos:pos + length].decode("ascii", "replace"))
                pos += length
        elif ext_type == 16 and len(value) >= 2:
            pos = 2
            while pos < len(value):
                length = value[pos]
                pos += 1
                alpn.append(value[pos:pos + length].decode("ascii", "replace"))
                pos += length
        elif ext_type == 43 and value:
            pos = 1 if len(value) % 2 else 0
            versions.extend(value[i:i + 2].hex() for i in range(pos, len(value) - 1, 2))
    return {"legacy_version": version, "supported_versions": versions, "ciphers": ciphers, "sni": sni, "alpn": alpn}


def tls_scan(data, result, flow):
    offset = 0
    while offset + 5 <= len(data):
        content, major, minor, length = struct.unpack_from("!BBBH", data, offset)
        if content not in range(20, 24) or major != 3 or length > 65535:
            offset += 1
            continue
        end = offset + 5 + length
        if end > len(data):
            offset += 1
            continue
        result["record_types"][str(content)] += 1
        result["record_versions"][f"{major}.{minor}"] += 1
        result["record_lengths"][str(length)] += 1
        payload = data[offset + 5:end]
        if content == 22:
            pos = 0
            while pos + 4 <= len(payload):
                kind = payload[pos]
                size = int.from_bytes(payload[pos + 1:pos + 4], "big")
                body = payload[pos + 4:pos + 4 + size]
                if len(body) != size:
                    break
                result["handshake_types"][str(kind)] += 1
                if kind == 1:
                    hello = client_hello(body)
                    if hello:
                        hello["flow"] = flow
                    if hello and hello not in result["client_hellos"]:
                        result["client_hellos"].append(hello)
                pos += 4 + size
        offset = end


def merge_segments(segments):
    chunks, current, end = [], bytearray(), None
    for seq, data in sorted(segments):
        if not data:
            continue
        if end is None or seq > end:
            if current:
                chunks.append(bytes(current))
            current, end = bytearray(data), seq + len(data)
        elif seq + len(data) > end:
            current.extend(data[end - seq:])
            end = seq + len(data)
    if current:
        chunks.append(bytes(current))
    return chunks


def network_payload(data, linktype):
    if linktype == 113:  # Linux cooked capture v1
        if len(data) < 16:
            return None, b""
        ethertype, offset = struct.unpack_from("!H", data, 14)[0], 16
    elif linktype == 1:  # Ethernet
        if len(data) < 14:
            return None, b""
        ethertype, offset = struct.unpack_from("!H", data, 12)[0], 14
    else:
        raise ValueError(f"Linktype {linktype}; esperado Ethernet (1) ou Linux SLL (113)")
    while ethertype in (0x8100, 0x88A8, 0x9100):
        if len(data) < offset + 4:
            return None, b""
        ethertype = struct.unpack_from("!H", data, offset + 2)[0]
        offset += 4
    return ethertype, data[offset:]


def analyze(path):
    raw = Path(path).read_bytes()
    if len(raw) < 24:
        raise ValueError("PCAP menor que o cabeçalho global")
    magic = raw[:4]
    formats = {
        b"\xd4\xc3\xb2\xa1": ("<", 1_000_000), b"\xa1\xb2\xc3\xd4": (">", 1_000_000),
        b"\x4d\x3c\xb2\xa1": ("<", 1_000_000_000), b"\xa1\xb2\x3c\x4d": (">", 1_000_000_000),
    }
    if magic not in formats:
        raise ValueError("Formato PCAP não reconhecido")
    endian, divisor = formats[magic]
    _, major, minor, _, _, snaplen, linktype = struct.unpack_from(endian + "IHHIIII", raw)
    if linktype not in (1, 113):
        raise ValueError(f"Linktype {linktype}; esperado Ethernet (1) ou Linux SLL (113)")

    packets, wire_bytes, captured_bytes, offset = 0, 0, 0, 24
    first_ts = last_ts = previous_ts = None
    timestamp_inversions, largest_inversion = 0, 0.0
    protocol_counts, port_counts = collections.Counter(), collections.Counter()
    endpoint_stats, conversations = collections.defaultdict(lambda: [0, 0, 0]), collections.defaultdict(lambda: [0, 0, 0, None, None])
    frame_lengths, seconds = collections.Counter(), collections.defaultdict(lambda: [0, 0])
    tcp_flags, tcp_segments = collections.Counter(), collections.defaultdict(list)
    direction_bytes = collections.defaultdict(collections.Counter)
    payload_lengths, payload_prefixes = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
    text_values, dns_queries, dns_answers = collections.Counter(), collections.Counter(), collections.Counter()
    custom_packets = []
    quic = {"long": 0, "short": 0, "versions": collections.Counter(), "dcids": collections.Counter()}
    tls = {key: collections.Counter() for key in ("record_types", "record_versions", "record_lengths", "handshake_types")}
    tls["client_hellos"] = []
    fragments = malformed = 0

    while offset + 16 <= len(raw):
        ts_sec, ts_frac, incl_len, orig_len = struct.unpack_from(endian + "IIII", raw, offset)
        offset += 16
        data = raw[offset:offset + incl_len]
        offset += incl_len
        if len(data) != incl_len:
            malformed += 1
            break
        ts = ts_sec + ts_frac / divisor
        packets += 1
        wire_bytes += orig_len
        captured_bytes += incl_len
        frame_lengths[orig_len] += 1
        first_ts = ts if first_ts is None else min(first_ts, ts)
        last_ts = ts if last_ts is None else max(last_ts, ts)
        if previous_ts is not None and ts < previous_ts:
            timestamp_inversions += 1
            largest_inversion = max(largest_inversion, previous_ts - ts)
        previous_ts = ts
        ethertype, net = network_payload(data, linktype)
        if ethertype is None:
            malformed += 1
            continue
        if ethertype != 0x0800 or len(net) < 20:
            protocol_counts[f"ethertype_0x{ethertype:04x}"] += 1
            continue
        version_ihl = net[0]
        ihl = (version_ihl & 0x0F) * 4
        if version_ihl >> 4 != 4 or len(net) < ihl:
            malformed += 1
            continue
        total_len = struct.unpack_from("!H", net, 2)[0]
        proto = net[9]
        src, dst = socket.inet_ntoa(net[12:16]), socket.inet_ntoa(net[16:20])
        frag = struct.unpack_from("!H", net, 6)[0]
        ip_payload = net[ihl:min(total_len, len(net))]
        if frag & 0x1FFF:
            fragments += 1
            continue
        transport = "OTHER"
        sport = dport = payload_len = 0
        payload = b""
        if proto == 6 and len(ip_payload) >= 20:
            transport = "TCP"
            sport, dport, seq, _, off_flags = struct.unpack_from("!HHIIH", ip_payload)
            header_len, flags = (off_flags >> 12) * 4, off_flags & 0x1FF
            payload = ip_payload[header_len:] if header_len >= 20 else b""
            payload_len = len(payload)
            tcp_flags[f"0x{flags:03x}"] += 1
            if payload:
                tcp_segments[(src, sport, dst, dport)].append((seq, payload))
        elif proto == 17 and len(ip_payload) >= 8:
            transport = "UDP"
            sport, dport, udp_len = struct.unpack_from("!HHH", ip_payload)
            payload = ip_payload[8:min(udp_len, len(ip_payload))]
            payload_len = len(payload)
            if sport == 53 or dport == 53:
                queries, answers = parse_dns(payload)
                dns_queries.update(f"{name}|type={qtype}" for name, qtype in queries)
                dns_answers.update(f"{name}|{answer}" for name, answer in answers)
            if sport == 443 or dport == 443:
                if payload and payload[0] & 0x80:
                    quic["long"] += 1
                    if len(payload) >= 6:
                        version = payload[1:5].hex()
                        quic["versions"][version] += 1
                        dcid_len = payload[5]
                        if len(payload) >= 6 + dcid_len:
                            quic["dcids"][payload[6:6 + dcid_len].hex()] += 1
                else:
                    quic["short"] += 1
        else:
            protocol_counts[f"ip_proto_{proto}"] += 1

        protocol_counts[transport] += 1
        port_counts[f"{transport}/{dport}"] += 1
        endpoint_stats[src][0] += 1
        endpoint_stats[src][1] += orig_len
        endpoint_stats[src][2] += payload_len
        endpoint_stats[dst][0] += 1
        endpoints = sorted((f"{src}:{sport}", f"{dst}:{dport}"))
        key = f"{transport} {endpoints[0]} <-> {endpoints[1]}"
        stat = conversations[key]
        stat[0] += 1
        stat[1] += orig_len
        stat[2] += payload_len
        stat[3] = ts if stat[3] is None else min(stat[3], ts)
        stat[4] = ts if stat[4] is None else max(stat[4], ts)
        direction = f"{src}:{sport} -> {dst}:{dport}"
        direction_bytes[direction].update(payload)
        if payload:
            payload_lengths[direction][len(payload)] += 1
            payload_prefixes[direction][payload[:8].hex()] += 1
            text_values.update(strings(payload))
            if sport in (12000, 12020) or dport in (12000, 12020):
                custom_packets.append({"epoch": ts, "src": src, "sport": sport, "dst": dst, "dport": dport,
                                       "transport": transport, "payload_length": payload_len, "payload_hex": payload.hex()})
        seconds[int(ts)][0] += 1
        seconds[int(ts)][1] += orig_len

    for flow, segments in tcp_segments.items():
        if flow[1] == 443 or flow[3] == 443:
            for chunk in merge_segments(segments):
                tls_scan(chunk, tls, f"{flow[0]}:{flow[1]} -> {flow[2]}:{flow[3]}")

    private_counts = collections.Counter()
    for address, stat in endpoint_stats.items():
        try:
            if ipaddress.ip_address(address).is_private:
                private_counts[address] += stat[0]
        except ValueError:
            pass
    local_ip = private_counts.most_common(1)[0][0] if private_counts else None

    def sorted_counter(counter, limit=None):
        values = [{"value": k, "count": v} for k, v in counter.most_common(limit)]
        return values

    endpoint_output = []
    for address, (count, total, payload_total) in sorted(endpoint_stats.items(), key=lambda item: item[1][1], reverse=True):
        endpoint_output.append({"ip": address, "packet_mentions": count, "wire_bytes_as_source": total, "payload_bytes_as_source": payload_total})
    conversation_output = []
    for key, (count, total, payload_total, start, end) in sorted(conversations.items(), key=lambda item: item[1][1], reverse=True):
        conversation_output.append({"conversation": key, "packets": count, "wire_bytes": total, "payload_bytes": payload_total,
                                    "start_epoch": start, "end_epoch": end, "duration_s": round(end - start, 6)})
    direction_output = []
    for direction, byte_counter in sorted(direction_bytes.items(), key=lambda item: sum(item[1].values()), reverse=True):
        total = sum(byte_counter.values())
        direction_output.append({
            "direction": direction, "payload_bytes": total, "entropy_bits_per_byte": round(entropy(byte_counter), 4),
            "top_payload_lengths": sorted_counter(payload_lengths[direction], 12),
            "top_prefixes": sorted_counter(payload_prefixes[direction], 8),
        })
    timeline = [{"epoch_second": second, "packets": values[0], "wire_bytes": values[1]} for second, values in sorted(seconds.items())]

    return {
        "file": str(Path(path).resolve()),
        "pcap": {"version": f"{major}.{minor}", "snaplen": snaplen, "linktype": linktype, "packets": packets,
                 "wire_bytes": wire_bytes, "captured_bytes": captured_bytes, "first_epoch": first_ts, "last_epoch": last_ts,
                 "duration_s": round((last_ts or 0) - (first_ts or 0), 6), "timestamp_inversions": timestamp_inversions,
                 "largest_timestamp_inversion_s": round(largest_inversion, 6), "malformed_records": malformed,
                 "ipv4_fragments_without_first_header": fragments},
        "local_ip_guess": local_ip,
        "protocols": sorted_counter(protocol_counts),
        "destination_ports": sorted_counter(port_counts),
        "frame_lengths": sorted_counter(frame_lengths, 30),
        "tcp_flags": sorted_counter(tcp_flags),
        "endpoints": endpoint_output,
        "conversations": conversation_output,
        "directions": direction_output,
        "dns": {"queries": sorted_counter(dns_queries), "answers": sorted_counter(dns_answers)},
        "tls": {"record_types": sorted_counter(tls["record_types"]), "record_versions": sorted_counter(tls["record_versions"]),
                "record_lengths": sorted_counter(tls["record_lengths"], 30), "handshake_types": sorted_counter(tls["handshake_types"]),
                "client_hellos": tls["client_hellos"]},
        "quic": {"long_header_packets": quic["long"], "short_header_packets": quic["short"],
                 "versions": sorted_counter(quic["versions"]), "destination_connection_ids": sorted_counter(quic["dcids"], 20)},
        "printable_payload_strings": sorted_counter(text_values, 100),
        "custom_channel_packets": custom_packets,
        "timeline_per_second": timeline,
    }


def self_test():
    assert round(entropy(collections.Counter(b"aaaa")), 3) == 0
    assert round(entropy(collections.Counter(range(256))), 3) == 8
    assert strings(b"\x00hello\x00") == ["hello"]
    assert dns_name(b"\x03www\x07example\x03com\x00", 0)[0] == "www.example.com"
    assert network_payload(b"\0" * 12 + b"\x08\x00IP", 1) == (0x0800, b"IP")
    assert network_payload(b"\0" * 12 + b"\x81\x00\0\1\x08\x00IP", 1) == (0x0800, b"IP")
    assert network_payload(b"\0" * 14 + b"\x08\x00IP", 113) == (0x0800, b"IP")
    print("Self-test OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Resumo passivo de PCAP Ethernet ou Linux SLL")
    parser.add_argument("pcap", nargs="?")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    elif not args.pcap:
        parser.error("informe o arquivo PCAP")
    else:
        print(json.dumps(analyze(args.pcap), ensure_ascii=False, indent=2))
