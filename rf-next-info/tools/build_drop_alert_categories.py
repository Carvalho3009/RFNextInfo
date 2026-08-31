"""Gera tipos de item para alertas a partir do catálogo oficial."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def category(row: dict[str, str]) -> str | None:
    item_type = int(row.get("ItemType") or 0)
    equip_part = int(row.get("EquipPartType") or 0)
    item_category = int(row.get("ItemCategory") or 0)
    if item_type == 2025:
        return "blueprint_mau"
    if item_type == 2026:
        return "blueprint_launcher"
    if item_type == 2034:
        return "skill"
    if equip_part == 1:
        return "weapon"
    if 2 <= equip_part <= 6:
        return "armor"
    if equip_part in {7, 8, 9, 10, 16}:
        return "accessory"
    if item_category == 4 or equip_part in {15, 17, 18}:
        return "expansion"
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    with args.source.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    categories = {
        str(int(row["ItemIndex"])): value
        for row in rows
        if (value := category(row)) is not None
    }
    payload = {
        "schema_version": 1,
        "game_data_version": "1.28.5",
        "source": "RF_ItemTable.RFTable",
        "categories": dict(
            sorted(categories.items(), key=lambda item: int(item[0]))
        ),
    }
    args.target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
