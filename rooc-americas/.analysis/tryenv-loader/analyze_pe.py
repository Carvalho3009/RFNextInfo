import argparse
import hashlib
import math
import re
import struct
from datetime import datetime, timezone
from pathlib import Path


def u16(data, offset):
    return struct.unpack_from("<H", data, offset)[0]


def u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def u64(data, offset):
    return struct.unpack_from("<Q", data, offset)[0]


def c_string(data, offset):
    end = data.find(b"\0", offset)
    return data[offset : end if end >= 0 else len(data)].decode("ascii", "replace")


def rva_to_offset(rva, sections, size_of_headers):
    if rva < size_of_headers:
        return rva
    for section in sections:
        span = max(section["virtual_size"], section["raw_size"])
        if section["virtual_address"] <= rva < section["virtual_address"] + span:
            return section["raw_offset"] + rva - section["virtual_address"]
    raise ValueError(f"unmapped RVA 0x{rva:x}")


def entropy(chunk):
    if not chunk:
        return 0.0
    counts = [0] * 256
    for byte in chunk:
        counts[byte] += 1
    return -sum((n / len(chunk)) * math.log2(n / len(chunk)) for n in counts if n)


def neighborhoods(data, needles, radius=384):
    lowered = data.lower()
    for needle in needles:
        start = 0
        while True:
            hit = lowered.find(needle.lower().encode(), start)
            if hit < 0:
                break
            left, right = max(0, hit - radius), min(len(data), hit + len(needle) + radius)
            print(f"  [{needle}] file_offset=0x{hit:x}")
            for match in re.finditer(rb"[\x20-\x7e]{4,}", data[left:right]):
                print(f"    0x{left + match.start():x}: {match.group().decode('ascii', 'replace')[:300]}")
            start = hit + len(needle)


def parse(path, needles):
    data = path.read_bytes()
    if data[:2] != b"MZ":
        raise ValueError("not an MZ executable")
    pe = u32(data, 0x3C)
    if data[pe : pe + 4] != b"PE\0\0":
        raise ValueError("missing PE signature")

    coff = pe + 4
    machine, section_count, timestamp = struct.unpack_from("<HHI", data, coff)
    optional_size = u16(data, coff + 16)
    optional = coff + 20
    magic = u16(data, optional)
    if magic not in (0x10B, 0x20B):
        raise ValueError(f"unsupported optional header 0x{magic:x}")
    is_64 = magic == 0x20B
    entrypoint = u32(data, optional + 16)
    image_base = u64(data, optional + 24) if is_64 else u32(data, optional + 28)
    size_of_headers = u32(data, optional + 60)
    subsystem = u16(data, optional + 68)
    dll_characteristics = u16(data, optional + 70)
    directory = optional + (112 if is_64 else 96)

    sections = []
    section_table = optional + optional_size
    for i in range(section_count):
        offset = section_table + i * 40
        name = data[offset : offset + 8].rstrip(b"\0").decode("ascii", "replace")
        virtual_size, virtual_address, raw_size, raw_offset = struct.unpack_from("<IIII", data, offset + 8)
        chunk = data[raw_offset : raw_offset + raw_size]
        sections.append(
            {
                "name": name,
                "virtual_size": virtual_size,
                "virtual_address": virtual_address,
                "raw_size": raw_size,
                "raw_offset": raw_offset,
                "entropy": entropy(chunk),
            }
        )

    imports = {}
    import_rva, import_size = struct.unpack_from("<II", data, directory + 8)
    if import_rva:
        descriptor = rva_to_offset(import_rva, sections, size_of_headers)
        thunk_size = 8 if is_64 else 4
        ordinal_mask = 1 << (63 if is_64 else 31)
        read_thunk = u64 if is_64 else u32
        for _ in range(import_size // 20 + 1):
            original, _, _, name_rva, first = struct.unpack_from("<IIIII", data, descriptor)
            descriptor += 20
            if not any((original, name_rva, first)):
                break
            dll = c_string(data, rva_to_offset(name_rva, sections, size_of_headers))
            thunk = rva_to_offset(original or first, sections, size_of_headers)
            names = []
            while True:
                value = read_thunk(data, thunk)
                thunk += thunk_size
                if not value:
                    break
                if value & ordinal_mask:
                    names.append(f"ordinal:{value & 0xFFFF}")
                else:
                    item = rva_to_offset(value, sections, size_of_headers)
                    names.append(c_string(data, item + 2))
            imports[dll] = names

    ascii_strings = [m.decode("ascii", "replace") for m in re.findall(rb"[\x20-\x7e]{6,}", data)]
    utf16_strings = [m.decode("utf-16le", "replace") for m in re.findall(rb"(?:[\x20-\x7e]\x00){6,}", data)]
    strings = ascii_strings + utf16_strings
    url_pattern = re.compile(r"https?://[A-Za-z0-9][A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]{3,200}", re.I)
    urls = sorted({match.group(0) for value in strings for match in url_pattern.finditer(value)})
    generic = re.compile(r"cargo\\registry|/rustc/|\\rustc\\|tauri|wry|webview|tokio|hyper|reqwest|\.rs(?::\d+)?$", re.I)
    app_strings = sorted(
        {
            value
            for value in strings
            if len(value) <= 500
            and not generic.search(value)
            and re.search(
                r"tryenv|ragnarok|inject|\.dll\b|loader|moduler|login|license|token|discord|auth|download|update|OpenProcess|CreateRemoteThread|WriteProcessMemory|VirtualAllocEx",
                value,
                re.I,
            )
        }
    )
    overlay_start = max((s["raw_offset"] + s["raw_size"] for s in sections), default=len(data))

    print(f"path: {path}")
    print(f"size: {len(data)}")
    for algorithm in ("md5", "sha1", "sha256"):
        print(f"{algorithm}: {hashlib.new(algorithm, data).hexdigest()}")
    print(f"machine: 0x{machine:04x}")
    print(f"architecture: {'x64' if is_64 else 'x86'}")
    print(f"timestamp_utc: {datetime.fromtimestamp(timestamp, timezone.utc).isoformat()}")
    print(f"entrypoint_rva: 0x{entrypoint:x}")
    print(f"image_base: 0x{image_base:x}")
    print(f"subsystem: {subsystem}")
    print(f"dll_characteristics: 0x{dll_characteristics:04x}")
    print(f"overlay_size: {max(0, len(data) - overlay_start)}")
    print("sections:")
    for section in sections:
        print(
            f"  {section['name']:<8} RVA=0x{section['virtual_address']:08x} "
            f"virtual={section['virtual_size']:8d} raw={section['raw_size']:8d} "
            f"entropy={section['entropy']:.3f}"
        )
    print("imports:")
    for dll, names in imports.items():
        print(f"  {dll}: {', '.join(names)}")
    print("urls:")
    for value in urls:
        print(f"  {value}")
    print("app_strings:")
    for value in app_strings:
        print(f"  {value[:500]}")
    if needles:
        print("neighborhoods:")
        neighborhoods(data, needles)


def self_test():
    sections = [{"virtual_address": 0x1000, "virtual_size": 0x200, "raw_size": 0x200, "raw_offset": 0x400}]
    assert rva_to_offset(0x1010, sections, 0x400) == 0x410
    assert entropy(b"A" * 100) == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--needle", action="append", default=[])
    args = parser.parse_args()
    self_test()
    parse(args.path, args.needle)
