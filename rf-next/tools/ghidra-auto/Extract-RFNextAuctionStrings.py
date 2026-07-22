#!/usr/bin/env python3
"""List auction/exchange-related ASCII strings and file offsets from a binary."""

import re
import sys
from pathlib import Path


PRINTABLE = re.compile(rb"[\x20-\x7e]{5,}")
AUCTION = re.compile(
    r"(?i)(?:"
    r"handle_.*(?:exchange|auction).*message|"
    r"(?:FL2C|L2C|C2L|CL2|LS2C|C2S|S2C)_.*(?:exchange|auction)|"
    r"(?:exchange|auction).*(?:product|item|sale|purchase|list|price|register|cancel|bookmark)|"
    r"(?:product|item|sale|purchase|list|price|register|cancel|bookmark).*(?:exchange|auction)"
    r")"
)


def matches(path: Path):
    data = path.read_bytes()
    for hit in PRINTABLE.finditer(data):
        value = hit.group().decode("ascii", "replace")
        if AUCTION.search(value):
            yield hit.start(), value


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print(f"Uso: {Path(sys.argv[0]).name} <binario> [regex]", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    pattern = re.compile(sys.argv[2], re.IGNORECASE) if len(sys.argv) == 3 else AUCTION
    found = []
    for offset, value in matches(path) if pattern is AUCTION else (
        (hit.start(), hit.group().decode("ascii", "replace"))
        for hit in PRINTABLE.finditer(path.read_bytes())
    ):
        if pattern.search(value):
            found.append((offset, value))
    for offset, value in found:
        print(f"0x{offset:08x}\t{value}")
    print(f"MATCHES={len(found)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
