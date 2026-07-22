#!/usr/bin/env python3
"""Exporta tabelas relacionadas de RF ONLINE NEXT para CSVs utilizaveis."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from rftable import load


TABLE_RELATIVE = Path("ProjectRF/Content/Streaming/DataTables/TableBinaries")
LAYER_ORDER = ("patch1", "patch0", "base")


def pick_table(root: Path, name: str) -> tuple[str, Path]:
    for layer in LAYER_ORDER:
        candidate = root / layer / TABLE_RELATIVE / name
        if candidate.exists():
            return layer, candidate
    raise FileNotFoundError(name)


def read_rows(root: Path, name: str) -> tuple[str, list[dict[str, Any]]]:
    layer, path = pick_table(root, name)
    return layer, list(load(path).rows())


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str] | None = None) -> int:
    materialized = list(rows)
    if fields is None:
        fields = list(materialized[0]) if materialized else []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in materialized:
            writer.writerow({
                key: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                if isinstance(value, (list, tuple)) else value
                for key, value in row.items()
            })
    return len(materialized)


def latest_sqlite(root: Path, name: str) -> tuple[str, Path]:
    return pick_table(root, name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tables-root",
        type=Path,
        default=Path(r"K:\MCP\projects\rf-next\analysis\1.28.5\game-tables"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(r"K:\MCP\projects\rf-next\analysis\1.28.5\exports"),
    )
    args = parser.parse_args()
    root = args.tables_root
    output = args.output
    output.mkdir(parents=True, exist_ok=True)

    sources: dict[str, str] = {}
    counts: dict[str, int] = {}

    string_layer, string_rows = read_rows(root, "RF_StringTable_PT_BR.RFTable")
    sources["strings"] = string_layer
    strings = {row["StringID"]: row["KO_KR"] for row in string_rows}

    enum_layer, enum_rows = read_rows(root, "RF_EnumPrintTable.RFTable")
    sources["enums"] = enum_layer
    stat_enum_rows = [row for row in enum_rows if row["EnumGroup"] == "eSTAT"]
    max_stat_order = max(int(row["Order"]) for row in stat_enum_rows)
    stat_types: dict[int, dict[str, Any]] = {}
    stat_export = []
    for row in stat_enum_rows:
        stat_value = max_stat_order + 1 - int(row["Order"])
        record = {
            "StatType": stat_value,
            "StatEnum": row["EnumType"],
            "StatNameKey": row["TextStringIndex"],
            "StatNamePTBR": strings.get(row["TextStringIndex"], ""),
        }
        stat_types[stat_value] = record
        stat_export.append(record)
    counts["stat_types.csv"] = write_csv(output / "stat_types.csv", stat_export)

    item_layer, item_rows = read_rows(root, "RF_ItemTable.RFTable")
    sources["items"] = item_layer
    items = {int(row["ItemIndex"]): row for row in item_rows}
    item_export = []
    for row in item_rows:
        item_export.append({
            **row,
            "NamePTBR": strings.get(row["NameStringIndex"], ""),
            "DescriptionPTBR": strings.get(row["DescStringIndex"], ""),
        })
    counts["items.csv"] = write_csv(output / "items.csv", item_export)
    auction_eligible = [
        row for row in item_export
        if row["ExchangeItem"] or row["WGExchangeItem"]
    ]
    counts["auction_eligible_items.csv"] = write_csv(
        output / "auction_eligible_items.csv", auction_eligible
    )

    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in item_rows:
        group_id = int(row["ItemGroup"])
        if group_id:
            groups[group_id].append(row)

    collection_layer, collection_rows = read_rows(root, "RF_ItemCollection.RFTable")
    sources["collections"] = collection_layer
    collection_export = []
    requirement_export = []
    for row in collection_rows:
        collection_name = strings.get(row["NameStringIndex"], "")
        enriched_collection = {**row, "NamePTBR": collection_name}
        for reward_slot in range(1, 4):
            stat_type = int(row[f"RewardStat{reward_slot}_Type"])
            stat = stat_types.get(stat_type, {})
            enriched_collection[f"RewardStat{reward_slot}_Enum"] = stat.get("StatEnum", "")
            enriched_collection[f"RewardStat{reward_slot}_NamePTBR"] = stat.get("StatNamePTBR", "")
        collection_export.append(enriched_collection)
        for slot in range(1, 11):
            group_id = int(row[f"Collection{slot}_ItemGroup"])
            required = int(row[f"Collection{slot}_Value"])
            enchant = int(row[f"Collection{slot}_EnchantLevel"])
            if not group_id or not required:
                continue
            accepted = groups.get(group_id) or [{"ItemIndex": 0}]
            for member in accepted:
                item_id = int(member["ItemIndex"])
                item = items.get(item_id, {})
                requirement_export.append({
                    "CollectionIndex": row["CollectionIndex"],
                    "CollectionNamePTBR": collection_name,
                    "Slot": slot,
                    "ItemGroup": group_id,
                    "RequiredQuantity": required,
                    "RequiredEnchantLevel": enchant,
                    "AcceptedItemIndex": item_id,
                    "AcceptedItemNamePTBR": strings.get(item.get("NameStringIndex", ""), ""),
                    "AcceptedItemGrade": item.get("Grade", ""),
                    "AcceptedItemTier": item.get("Tier", ""),
                })
    counts["collections.csv"] = write_csv(output / "collections.csv", collection_export)
    counts["collection_requirements.csv"] = write_csv(
        output / "collection_requirements.csv", requirement_export
    )

    part_layer, part_rows = read_rows(root, "RF_Collection_PartReward.RFTable")
    sources["RF_Collection_PartReward.RFTable"] = part_layer
    part_export = []
    for row in part_rows:
        stat = stat_types.get(int(row["StatType"]), {})
        part_export.append({
            **row,
            "StatEnum": stat.get("StatEnum", ""),
            "StatNamePTBR": stat.get("StatNamePTBR", ""),
        })
    counts["collection_part_rewards.csv"] = write_csv(
        output / "collection_part_rewards.csv", part_export
    )

    complete_layer, complete_rows = read_rows(root, "RF_Collection_CompleteReward.RFTable")
    sources["RF_Collection_CompleteReward.RFTable"] = complete_layer
    complete_export = []
    for row in complete_rows:
        enriched = dict(row)
        for reward_slot in range(1, 3):
            stat_type = int(row[f"CompleteReward_Stat{reward_slot}Type"])
            stat = stat_types.get(stat_type, {})
            enriched[f"CompleteReward_Stat{reward_slot}Enum"] = stat.get("StatEnum", "")
            enriched[f"CompleteReward_Stat{reward_slot}NamePTBR"] = stat.get("StatNamePTBR", "")
        complete_export.append(enriched)
    counts["collection_complete_rewards.csv"] = write_csv(
        output / "collection_complete_rewards.csv", complete_export
    )

    auction_layer, auction_rows = read_rows(root, "RF_Guild_Auction.RFTable")
    sources["RF_Guild_Auction.RFTable"] = auction_layer
    counts["guild_auction_settings.csv"] = write_csv(
        output / "guild_auction_settings.csv", auction_rows
    )

    npc_layer, npc_rows = read_rows(root, "RF_NPCTable.RFTable")
    sources["npcs"] = npc_layer
    mob_export = []
    for row in npc_rows:
        mob_export.append({
            **row,
            "NamePTBR": strings.get(row["NameStringIndex"], ""),
            "TitlePTBR": strings.get(row["TitleStringIndex"], ""),
            "HP": "",
            "EXPBaseMinCandidates": [],
        })

    reward_layer, reward_db = latest_sqlite(root, "RF_RewardTable.sqlite")
    subgroup_layer, subgroup_db = latest_sqlite(root, "RF_SubGroupInfo.sqlite")
    sources["reward_database"] = reward_layer
    sources["subgroup_database"] = subgroup_layer

    with sqlite3.connect(f"file:{reward_db.as_posix()}?mode=ro", uri=True) as connection:
        reward_rows = [
            {"RewardIndex": row[0], "BoxType": row[1], "SubGroupIndex": row[2]}
            for row in connection.execute(
                "SELECT RewardIndex, BoxType, SubGroupIndex FROM RF_RewardTableRow"
            )
        ]
    with sqlite3.connect(f"file:{subgroup_db.as_posix()}?mode=ro", uri=True) as connection:
        subgroup_rows = [
            {
                "SubGroupIndex": row[0],
                "RewardItemIndex": row[1],
                "MinValue": row[2],
                "EnchantLevel": row[3],
                "BiosuitType": row[4],
            }
            for row in connection.execute(
                "SELECT SubGroupIndex, RewardItemIndex, MinValue, EnchantLevel, BiosuitType "
                "FROM RF_SubGroupInfoRow"
            )
        ]
    counts["reward_groups.csv"] = write_csv(output / "reward_groups.csv", reward_rows)
    counts["reward_items.csv"] = write_csv(output / "reward_items.csv", subgroup_rows)

    reward_multiplicity = Counter(
        (int(row["RewardIndex"]), int(row["SubGroupIndex"])) for row in reward_rows
    )
    reward_totals = Counter(int(row["RewardIndex"]) for row in reward_rows)
    subgroup_map: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in subgroup_rows:
        subgroup_map[int(row["SubGroupIndex"])].append(row)
    npc_by_reward: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for npc in npc_rows:
        reward_id = int(npc["RewardIndex"])
        if reward_id:
            npc_by_reward[reward_id].append(npc)

    loot_export = []
    exp_export = []
    exp_by_npc: dict[int, list[int]] = defaultdict(list)
    for (reward_id, subgroup_id), multiplicity in reward_multiplicity.items():
        for npc in npc_by_reward.get(reward_id, []):
            for reward_item in subgroup_map.get(subgroup_id, []):
                item_id = int(reward_item["RewardItemIndex"])
                item = items.get(item_id, {})
                record = {
                    "NPCIndex": npc["NPCIndex"],
                    "NPCNamePTBR": strings.get(npc["NameStringIndex"], ""),
                    "NPCLevel": npc["Level"],
                    "RewardIndex": reward_id,
                    "SubGroupIndex": subgroup_id,
                    "RewardItemIndex": item_id,
                    "RewardItemNamePTBR": strings.get(item.get("NameStringIndex", ""), ""),
                    "MinValue": reward_item["MinValue"],
                    "EnchantLevel": reward_item["EnchantLevel"],
                    "Multiplicity": multiplicity,
                    "MultiplicityShareCandidate": multiplicity / reward_totals[reward_id],
                    "ChanceConfirmed": False,
                }
                loot_export.append(record)
                if item_id == 900:
                    exp_value = int(reward_item["MinValue"])
                    exp_by_npc[int(npc["NPCIndex"])].append(exp_value)
                    exp_export.append({
                        "NPCIndex": npc["NPCIndex"],
                        "NPCNamePTBR": strings.get(npc["NameStringIndex"], ""),
                        "NPCLevel": npc["Level"],
                        "RewardIndex": reward_id,
                        "SubGroupIndex": subgroup_id,
                        "EXPBaseMin": exp_value,
                        "ObservedTarget": 16303,
                        "DifferenceFromObserved": exp_value - 16303,
                    })
    counts["mob_loot_candidates.csv"] = write_csv(
        output / "mob_loot_candidates.csv", loot_export
    )
    counts["mob_exp_candidates.csv"] = write_csv(output / "mob_exp_candidates.csv", exp_export)

    for row in mob_export:
        values = sorted(set(exp_by_npc.get(int(row["NPCIndex"]), [])))
        row["EXPBaseMinCandidates"] = values
    counts["mobs.csv"] = write_csv(output / "mobs.csv", mob_export)

    nearest_distance = min(
        (abs(int(row["EXPBaseMin"]) - 16303) for row in exp_export),
        default=0,
    )
    nearest_exp = [
        row for row in exp_export
        if abs(int(row["EXPBaseMin"]) - 16303) == nearest_distance
    ]
    counts["exp-nearest-16303.csv"] = write_csv(output / "exp-nearest-16303.csv", nearest_exp)

    summary = {
        "version": "1.28.5",
        "layer_precedence": list(LAYER_ORDER),
        "sources": sources,
        "files": counts,
        "limitations": [
            "As tabelas cliente extraidas nao possuem coluna explicita de HP por NPC.",
            "As tabelas cliente extraidas nao possuem coluna explicita de EXP por abate.",
            "A EXP base foi relacionada pelo item interno 900 (EXP), mas bonus dinamicos podem alterar o ganho exibido.",
            "MultiplicityShareCandidate nao e chance confirmada; precisa ser validada no codigo do jogo ou por amostragem.",
            "Precos e itens listados atualmente no leilao sao dados dinamicos do servidor e nao aparecem nestas tabelas estaticas.",
        ],
    }
    (output / "export_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report = [
        "# Exportacao RF ONLINE NEXT 1.28.5",
        "",
        f"Gerados {len(counts)} CSVs a partir das camadas patch1, patch0 e base.",
        "",
        "## Resultados principais",
        "",
        f"- NPCs: {counts['mobs.csv']}",
        f"- Itens: {counts['items.csv']}",
        f"- Itens estaticamente elegiveis para negociacao: {counts['auction_eligible_items.csv']}",
        f"- Colecoes: {counts['collections.csv']}",
        f"- Requisitos aceitos de colecao: {counts['collection_requirements.csv']}",
        f"- Candidatos de loot relacionados a NPC: {counts['mob_loot_candidates.csv']}",
        f"- NPCs com candidato de EXP base: {counts['mob_exp_candidates.csv']}",
        "",
        "## Limites confirmados",
        "",
        "- HP por mob nao aparece como coluna nas tabelas cliente encontradas.",
        "- EXP base foi relacionada pelo item interno 900, mas o ganho final pode incluir bonus dinamicos.",
        "- A multiplicidade dos grupos de recompensa foi exportada, mas ainda nao prova a chance de drop.",
        "- Listagens e precos atuais de leilao continuam sendo dados dinamicos do servidor.",
    ]
    (output / "README.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
