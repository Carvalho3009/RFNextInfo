#!/usr/bin/env python3
"""Gera o catálogo compacto MapIndex -> nomes localizados do RF QOL."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def _rows(table_path: Path, reader_root: Path) -> list[dict]:
    sys.path.insert(0, str(reader_root))
    try:
        import rftable
    finally:
        sys.path.pop(0)
    return list(rftable.load(table_path).rows())


def build(
    *,
    map_table: Path,
    strings_pt: Path,
    strings_en: Path,
    reader_root: Path,
    output: Path,
    source_version: str,
) -> dict:
    map_rows = _rows(map_table, reader_root)
    english = {
        str(row.get("StringID") or ""): str(row.get("KO_KR") or "").strip()
        for row in _rows(strings_en, reader_root)
    }
    with strings_pt.open(encoding="utf-8-sig", newline="") as handle:
        portuguese = {
            str(row.get("StringID") or ""): str(row.get("KO_KR") or "").strip()
            for row in csv.DictReader(handle)
        }

    entries = {}
    for row in sorted(map_rows, key=lambda item: int(item["MapIndex"])):
        map_index = int(row["MapIndex"])
        name_key = str(row.get("MapNameString") or "").strip()
        entries[str(map_index)] = {
            "key": name_key,
            "pt": portuguese.get(name_key, ""),
            "en": english.get(name_key, ""),
        }

    catalog = {
        "schema_version": 1,
        "source_version": source_version,
        "entries": entries,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map-table", type=Path, required=True)
    parser.add_argument("--strings-pt", type=Path, required=True)
    parser.add_argument("--strings-en", type=Path, required=True)
    parser.add_argument("--reader-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-version", default="1.28.5")
    args = parser.parse_args()
    catalog = build(**vars(args))
    entries = catalog["entries"]
    print(
        "map catalog: "
        f"{len(entries)} entries, "
        f"{sum(bool(item['pt']) for item in entries.values())} pt, "
        f"{sum(bool(item['en']) for item in entries.values())} en"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
