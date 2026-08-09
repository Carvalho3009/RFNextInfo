#!/usr/bin/env python3
"""Atualiza o SQLite compacto do site a partir do banco RFTable extraído."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


def searchable(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    return " ".join(text.encode("ascii", "ignore").decode().split())


def rows(connection: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return list(connection.execute(f"SELECT * FROM [{table}]"))


def stat_types(raw: sqlite3.Connection, strings: dict[str, str]) -> dict[int, tuple[str, str]]:
    enums = {
        str(row["EnumType"]): row
        for row in rows(raw, "RF_EnumPrintTable")
        if row["EnumGroup"] == "eSTAT"
    }
    result = {}
    for status in rows(raw, "RF_CharacterTable_StatusTable"):
        enum_name = str(status["StatusNameIndex"]).replace("ui_STATUS_", "STAT_").replace("ui_STAUS_", "STAT_")
        enum = enums[enum_name]
        result[int(status["StatusIndex"])] = (
            enum_name,
            strings.get(str(enum["TextStringIndex"]), enum_name),
        )
    assert len(result) == 187
    return result


def changes(
    old: sqlite3.Connection,
    new: sqlite3.Connection,
    table: str,
    key: str,
) -> dict[str, str]:
    before = {str(row[key]): tuple(row) for row in rows(old, table)}
    after = {str(row[key]): tuple(row) for row in rows(new, table)}
    return {
        entity_id: "new" if entity_id not in before else "modified"
        for entity_id, record in after.items()
        if entity_id not in before or record != before[entity_id]
    }


def market_category(item: sqlite3.Row) -> tuple[str, str]:
    category_code = int(item["ItemCategory"])
    subcategory_code = int(item["ItemSubCategory"])
    categories = {1: "Arma", 2: "Armadura", 3: "Acessório", 4: "Expansão", 6: "Skillbook"}
    category = categories.get(category_code)
    if category_code == 7:
        category = "Material de Craft" if subcategory_code == 31 else "Material"
    category = category or "Outros"
    mappings = {
        1: {1: "Punisher", 2: "Phantom", 3: "Enforcer", 4: "Psypher", 5: "Dreadnought", 6: "Technician", 7: "Arbiter", 8: "Demolisher"},
        2: {2: "Neck Guard", 3: "Chest Guard", 4: "Lower Guard", 5: "Arm Guards", 6: "Leg Guards"},
        3: {7: "Ear Cuffs", 8: "Necklace", 9: "Bangles", 10: "Ring", 11: "Circlet"},
        4: {15: "Drive", 17: "Stargazer", 18: "Deflector"},
        6: {27: "Skillbook", 28: "Skill Upgrade Material"},
        7: {30: "Powerup Materials", 31: "Crafting Materials", 32: "Addon Materials"},
    }
    mapping_value = int(item["Equip_Biosuit"]) if category_code == 1 else int(item["EquipPartType"])
    if category_code in (6, 7):
        mapping_value = subcategory_code
    subcategory = mappings.get(category_code, {}).get(mapping_value)
    if not subcategory:
        subcategory = "Special Collectible" if category_code not in categories and subcategory_code == 31 else "Consumable"
    taxonomy = {
        "Arma": {"Punisher", "Phantom", "Enforcer", "Psypher", "Dreadnought", "Technician", "Arbiter", "Demolisher"},
        "Armadura": {"Neck Guard", "Chest Guard", "Lower Guard", "Arm Guards", "Leg Guards"},
        "Acessório": {"Ear Cuffs", "Necklace", "Bangles", "Ring", "Circlet"},
        "Expansão": {"Drive", "Stargazer", "Deflector"},
        "Skillbook": {"Skillbook", "Skill Upgrade Material"},
        "Material": {"Powerup Materials", "Addon Materials"},
        "Material de Craft": {"Crafting Materials"},
        "Outros": {"Special Collectible", "Consumable"},
    }
    return (category, subcategory) if subcategory in taxonomy.get(category, set()) else ("Outros", "Consumable")


def equipment_stats(row: sqlite3.Row, prefix: str, slots: int, suffix: str) -> dict[int, float]:
    result: dict[int, float] = {}
    for slot in range(1, slots + 1):
        stat = int(row[f"{prefix}_{slot}_Type"])
        if stat:
            result[stat] = result.get(stat, 0) + float(row[f"{prefix}_{slot}_{suffix}"] or 0)
    return result


def rebuild_equipment_compare(
    app: sqlite3.Connection,
    raw: sqlite3.Connection,
    strings: dict[str, str],
) -> int:
    enum_rows = rows(raw, "RF_EnumPrintTable")

    def enum_labels(group: str) -> dict[int, str]:
        selected = [row for row in enum_rows if row["EnumGroup"] == group]
        max_order = max(int(row["Order"]) for row in selected)
        return {
            max_order + 1 - int(row["Order"]): strings.get(str(row["TextStringIndex"]), str(row["EnumType"]))
            for row in selected
        }

    statuses = stat_types(raw, strings)
    stat_labels = {stat_id: value[1] for stat_id, value in statuses.items()}
    stat_enums = {stat_id: value[0] for stat_id, value in statuses.items()}
    part_labels = enum_labels("eEQUIP_PART")
    grade_labels = {
        int(row["Order"]): strings.get(str(row["TextStringIndex"]), str(row["EnumType"]))
        for row in enum_rows if row["EnumGroup"] == "eITEM_GRADE"
    }
    items = {
        int(row["ItemIndex"]): row for row in rows(raw, "RF_ItemTable")
        if int(row["EquipPartType"]) > 0 and strings.get(str(row["NameStringIndex"]), "")
    }
    enchantments: dict[int, dict[int, dict[int, float]]] = defaultdict(dict)
    for row in rows(raw, "RF_ItemEnchantTable_Status"):
        values: dict[int, float] = {}
        for slot in range(1, 4):
            stat = int(row[f"Status_Type{slot}"])
            if stat:
                values[stat] = values.get(stat, 0) + float(row[f"Status_Value{slot}"] or 0)
        for slot in range(1, 8):
            stat = int(row[f"SubStatus_Type{slot}"])
            if stat:
                values[stat] = values.get(stat, 0) + float(row[f"SubStatus_Value{slot}"] or 0)
        enchantments[int(row["ItemEnchantStatusIndex"])][int(row["Level"])] = values

    records = []
    for item_id, item in items.items():
        name = strings[str(item["NameStringIndex"])]
        base = equipment_stats(item, "Status", 3, "Base")
        for stat, value in equipment_stats(item, "SubStatus", 7, "Base").items():
            base[stat] = base.get(stat, 0) + value
        prime = equipment_stats(item, "PrimeStatus", 5, "Base")
        prime_target = items.get(int(item["Remodel_ItemIndex"])) if int(item["Remodel_ItemIndex"]) else (item if prime else None)
        target_base: dict[int, float] = {}
        target_prime: dict[int, float] = {}
        if prime_target:
            target_base = equipment_stats(prime_target, "Status", 3, "Base")
            for stat, value in equipment_stats(prime_target, "SubStatus", 7, "Base").items():
                target_base[stat] = target_base.get(stat, 0) + value
            target_prime = equipment_stats(prime_target, "PrimeStatus", 5, "Base")
        normal_enchant = enchantments.get(int(item["ItemEnchantStatusIndex"]), {})
        prime_enchant = enchantments.get(int(prime_target["ItemEnchantStatusIndex"]), {}) if prime_target else {}
        all_stats = set(base) | set(target_base) | set(target_prime)
        for level in normal_enchant.values():
            all_stats.update(level)
        for level in prime_enchant.values():
            all_stats.update(level)
        stats = []
        for stat in sorted(all_stats):
            regular = [base.get(stat, 0)] + [
                base.get(stat, 0) + normal_enchant[level].get(stat, 0) if level in normal_enchant else None
                for level in range(1, 16)
            ]
            upgraded = [target_base.get(stat, 0) + target_prime.get(stat, 0)] + [
                target_base.get(stat, 0) + target_prime.get(stat, 0) + prime_enchant[level].get(stat, 0)
                if level in prime_enchant else None
                for level in range(1, 16)
            ] if prime_target else [None] * 16
            stats.append({
                "statId": stat,
                "statEnum": stat_enums.get(stat, ""),
                "name": stat_labels.get(stat, f"STAT {stat}"),
                "regular": regular,
                "prime": upgraded,
            })
        part = part_labels.get(int(item["EquipPartType"]), f"Parte {item['EquipPartType']}")
        grade = grade_labels.get(int(item["Grade"]), str(item["Grade"]))
        version = "Prime" if prime else "Normal"
        records.append((
            str(item_id), name, part, grade, int(item["Tier"]), int(item["UseLv"]), version,
            str(item["Icon"] or ""), searchable(f"{item_id} {name} {part} {grade} {item['Tier']} {version}"),
            json.dumps(stats, ensure_ascii=False, separators=(",", ":")),
        ))

    app.executescript(
        """
        CREATE TABLE IF NOT EXISTS equipment_compare(
            item_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            part TEXT NOT NULL,
            grade TEXT NOT NULL,
            tier INTEGER NOT NULL,
            use_level INTEGER NOT NULL,
            version TEXT NOT NULL,
            icon TEXT NOT NULL,
            search_text TEXT NOT NULL,
            stats_json TEXT NOT NULL
        ) WITHOUT ROWID;
        CREATE INDEX IF NOT EXISTS ix_equipment_compare_search ON equipment_compare(search_text);
        DELETE FROM equipment_compare;
        """
    )
    app.executemany("INSERT INTO equipment_compare VALUES(?,?,?,?,?,?,?,?,?,?)", records)
    return len(records)


def rebuild_equipment_upgrade_rules(app: sqlite3.Connection, raw: sqlite3.Connection, strings: dict[str, str]) -> tuple[int, int]:
    enchant = {
        (int(row["EquipPartType"]), int(row["Grade"]), int(row["Level"])): row
        for row in rows(raw, "RF_ItemEnchantTable")
    }
    material_groups = {
        (int(row["EquipPart_Category"]), int(row["Grade"])): int(row["UpGradeMaterial_ItemGroup"])
        for row in rows(raw, "RF_ItemEnchantTable_Material")
    }
    rules = []
    referenced_groups = set()
    item_rows = rows(raw, "RF_ItemTable")
    for item in item_rows:
        part, grade, category = int(item["EquipPartType"]), int(item["Grade"]), int(item["ItemCategory"])
        group = material_groups.get((category, grade), 0)
        if not part or not group:
            continue
        referenced_groups.add(group)
        for level in range(15):
            rule = enchant.get((part, grade, level))
            if rule:
                rules.append((str(item["ItemIndex"]), level, int(rule["SuccessRate"]), int(rule["Fail_ItemBreakRate"]), int(rule["Enchant_CurrencyCount"]), group))
    upgraders = [
        (int(item["ItemGroup"]), str(item["ItemIndex"]), strings.get(str(item["NameStringIndex"]), f"Item {item['ItemIndex']}"))
        for item in item_rows if int(item["ItemGroup"]) in referenced_groups
    ]
    app.executescript(
        """
        CREATE TABLE IF NOT EXISTS equipment_upgrade_rules(
            item_id TEXT NOT NULL, level INTEGER NOT NULL, success_rate INTEGER NOT NULL,
            break_rate INTEGER NOT NULL, credit_cost INTEGER NOT NULL, upgrader_item_group INTEGER NOT NULL,
            PRIMARY KEY(item_id, level)
        ) WITHOUT ROWID;
        CREATE TABLE IF NOT EXISTS equipment_upgrader_items(
            item_group INTEGER NOT NULL, item_id TEXT NOT NULL, item_name TEXT NOT NULL,
            PRIMARY KEY(item_group, item_id)
        ) WITHOUT ROWID;
        DELETE FROM equipment_upgrade_rules;
        DELETE FROM equipment_upgrader_items;
        """
    )
    app.executemany("INSERT INTO equipment_upgrade_rules VALUES(?,?,?,?,?,?)", rules)
    app.executemany("INSERT INTO equipment_upgrader_items VALUES(?,?,?)", upgraders)
    return len(rules), len(upgraders)


def rebuild(
    output: Path,
    base: Path,
    old_raw: Path,
    new_raw: Path,
    bonuses: Path,
    source_version: str,
    asset_update: str,
) -> None:
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    shutil.copy2(base, temporary)
    updated_at = datetime.now(timezone.utc).isoformat()

    old = sqlite3.connect(f"file:{old_raw.as_posix()}?mode=ro", uri=True)
    new = sqlite3.connect(f"file:{new_raw.as_posix()}?mode=ro", uri=True)
    app = sqlite3.connect(temporary)
    for connection in (old, new, app):
        connection.row_factory = sqlite3.Row

    strings = {str(row["StringID"]): str(row["KO_KR"] or "") for row in rows(new, "RF_StringTable_PT_BR")}
    strings_en = {str(row["StringID"]): str(row["KO_KR"] or "") for row in rows(new, "RF_StringTable_EN_US")}
    item_rows = rows(new, "v_items_ptbr")
    items = {int(row["ItemIndex"]): row for row in item_rows}
    groups: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for item in item_rows:
        if group_id := int(item["ItemGroup"]):
            groups[group_id].append(item)

    tags: list[tuple[str, str, str, str]] = []
    visible_sources = (
        ("item", "v_items_ptbr", "ItemIndex"),
        ("collection", "v_collections_ptbr", "CollectionIndex"),
        ("map", "v_maps_ptbr", "MapInfoIndex"),
        ("mission", "v_missions_ptbr", "MissionIndex"),
        ("npc", "v_npcs_ptbr", "NPCIndex"),
        ("skill", "v_skills_ptbr", "SkillIndex"),
        ("title", "RF_TitleTable", "ItemIndex"),
        ("costume", "RF_Costume", "ItemIndex"),
        ("string", "RF_StringTable_PT_BR", "StringID"),
    )
    for domain, table, key in visible_sources:
        tags.extend((domain, entity_id, status, updated_at) for entity_id, status in changes(old, new, table, key).items())

    old_craft = Counter(tuple(row) for row in old.execute("SELECT * FROM RF_ItemCraft"))
    seen_craft: Counter[tuple] = Counter()
    for row in new.execute("SELECT rowid, * FROM RF_ItemCraft ORDER BY rowid"):
        record = tuple(row)[1:]
        seen_craft[record] += 1
        if seen_craft[record] > old_craft[record]:
            tags.append(("craft", str(row["rowid"]), "new", updated_at))

    app.execute("BEGIN IMMEDIATE")
    app.executescript(
        """
        CREATE TABLE IF NOT EXISTS content_changes(
            domain TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            change_type TEXT NOT NULL CHECK(change_type IN ('new','modified')),
            detected_at TEXT NOT NULL,
            PRIMARY KEY(domain, entity_id)
        ) WITHOUT ROWID;
        DELETE FROM content_changes;
        CREATE TABLE IF NOT EXISTS market_item_aliases(
            alias_item_id TEXT PRIMARY KEY,
            market_item_id TEXT NOT NULL
        ) WITHOUT ROWID;
        DELETE FROM market_item_aliases;
        """
    )
    app.executemany("INSERT INTO content_changes VALUES(?,?,?,?)", tags)

    app.execute("DELETE FROM entities")
    entity_specs = (
        ("item", "v_items_ptbr", "ItemIndex", "NamePTBR", "DescriptionPTBR", "RF_ItemTable"),
        ("collection", "v_collections_ptbr", "CollectionIndex", "NamePTBR", None, "RF_ItemCollection"),
        ("map", "v_maps_ptbr", "MapInfoIndex", "NamePTBR", None, "RF_MapInfoTable"),
        ("mission", "v_missions_ptbr", "MissionIndex", "MissionTitlePTBR", "MissionGoalPTBR", "RF_MissionTable"),
        ("npc", "v_npcs_ptbr", "NPCIndex", "NamePTBR", "TitlePTBR", "RF_NPCTable"),
        ("skill", "v_skills_ptbr", "SkillIndex", "NamePTBR", "DescriptionPTBR", "RF_SkillTable"),
    )
    entity_counts = {}
    for domain, table, key, name_key, description_key, source in entity_specs:
        batch = []
        for row in rows(new, table):
            name = str(row[name_key] or "")
            if not name:
                continue
            entity_id = str(row[key])
            description = str(row[description_key] or "") if description_key else ""
            batch.append((domain, entity_id, name, description, source, searchable(f"{name} {description} {entity_id}")))
        app.executemany("INSERT INTO entities VALUES(?,?,?,?,?,?)", batch)
        entity_counts[domain] = len(batch)

    app.execute("DELETE FROM item_details")
    app.executemany(
        "INSERT INTO item_details VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            (
                str(row["ItemIndex"]), row["Grade"], row["Tier"], row["ItemType"], row["ItemCategory"],
                row["ItemSubCategory"], row["EquipPartType"], row["Equip_Biosuit"], row["UseLv"],
                row["ExchangeItem"], row["WGExchangeItem"], row["TradeAble"], str(row["Icon"] or ""),
            )
            for row in item_rows
        ),
    )
    items_by_id = {str(row["ItemIndex"]): row for row in item_rows}
    market_aliases = [
        (str(row["ItemIndex"]), str(row["ItemGroup"]))
        for row in item_rows
        if str(row["ItemIndex"]) != str(row["ItemGroup"])
        and str(row["ItemGroup"]) in items_by_id
        and str(row["NameStringIndex"]) == str(items_by_id[str(row["ItemGroup"])]["NameStringIndex"])
    ]
    app.executemany("INSERT INTO market_item_aliases VALUES(?,?)", market_aliases)

    collection_rows = rows(new, "v_collections_ptbr")
    app.execute("DELETE FROM collection_details")
    app.execute("DELETE FROM collection_requirements")
    details, requirements = [], []
    for row in collection_rows:
        collection_id = str(row["CollectionIndex"])
        requirement_count = 0
        for slot in range(1, 11):
            group_id = int(row[f"Collection{slot}_ItemGroup"])
            quantity = int(row[f"Collection{slot}_Value"])
            if not group_id or not quantity:
                continue
            requirement_count += 1
            accepted = groups.get(group_id) or [None]
            for item in accepted:
                requirements.append(
                    (
                        collection_id, slot, group_id, quantity, int(row[f"Collection{slot}_EnchantLevel"]),
                        str(item["ItemIndex"]) if item else "0", str(item["NamePTBR"] or "") if item else "",
                        int(item["Grade"]) if item else 0, int(item["Tier"]) if item else 0,
                    )
                )
        details.append(
            (
                collection_id, row["CollectionType"], row["CollectionSeparation"],
                row["PeriodCollection"], requirement_count,
            )
        )
    app.executemany("INSERT INTO collection_details VALUES(?,?,?,?,?)", details)
    app.executemany("INSERT INTO collection_requirements VALUES(?,?,?,?,?,?,?,?,?)", requirements)

    app.execute("DELETE FROM map_details")
    app.executemany(
        "INSERT INTO map_details VALUES(?,?,?,?,?,?)",
        (
            (
                str(row["MapInfoIndex"]), row["MapIndex"], row["RegionIndex"], row["RegionGroupIndex"],
                row["TabIndex"], str(row["Location"] or ""),
            )
            for row in rows(new, "v_maps_ptbr")
        ),
    )
    app.execute("DELETE FROM mission_details")
    app.executemany(
        "INSERT INTO mission_details VALUES(?,?,?,?,?,?,?,?,?)",
        (
            (
                str(row["MissionIndex"]), row["MissionLevel"], row["MapIndex"], row["RegionIndex"],
                row["NeedMissionCount"], row["FixRewardIndex"], row["RandomRewardIndex"],
                str(row["MissionGoalPTBR"] or ""), str(row["MissionGoal2PTBR"] or ""),
            )
            for row in rows(new, "v_missions_ptbr")
        ),
    )

    spawn_counts = Counter(str(row[0]) for row in app.execute("SELECT npc_id FROM spawns"))
    npc_rows = rows(new, "v_npcs_ptbr")
    app.execute("DELETE FROM npc_details")
    app.executemany(
        "INSERT INTO npc_details VALUES(?,?,?,?,?,?,?)",
        (
            (
                str(row["NPCIndex"]), row["Level"], row["Grade"], row["NPCType"], row["NPCSubType"],
                row["RewardIndex"], spawn_counts[str(row["NPCIndex"])],
            )
            for row in npc_rows
        ),
    )
    app.execute(
        "UPDATE spawns SET npc_name=COALESCE((SELECT name FROM entities "
        "WHERE entity_type='npc' AND entity_id=spawns.npc_id), npc_name)"
    )
    app.execute(
        "UPDATE spawns SET map_name=COALESCE((SELECT name FROM entities "
        "WHERE entity_type='map' AND entity_id=spawns.map_info_id), map_name)"
    )
    app.execute(
        "UPDATE npc_exp SET npc_level=COALESCE((SELECT level FROM npc_details "
        "WHERE id=CAST(npc_exp.npc_id AS TEXT)), npc_level)"
    )

    app.execute("DELETE FROM skill_details")
    app.executemany(
        "INSERT INTO skill_details VALUES(?,?,?,?,?,?,?,?,?)",
        (
            (
                str(row["SkillIndex"]), row["Suit_Type"], row["Skill_Type"], row["First_Damagetype"],
                row["Cool_Time"], row["First_MaxRange"], row["UseCost_Type"], row["UseCost_Value"],
                str(row["Skill_Icon"] or ""),
            )
            for row in rows(new, "v_skills_ptbr")
        ),
    )

    app.execute("DELETE FROM craft_recipes")
    app.execute("DELETE FROM craft_materials")
    app.execute("DELETE FROM craft_results")
    recipes, materials, results = [], [], []
    for recipe in new.execute("SELECT rowid recipe_key, * FROM RF_ItemCraft ORDER BY rowid"):
        recipe_key = int(recipe["recipe_key"])
        output_item = items.get(int(recipe["Craft_Result_Normal"]))
        output_name = str(output_item["NamePTBR"] or "") if output_item else ""
        output_name_en = strings_en.get(str(output_item["NameStringIndex"]), "") if output_item else ""
        description = str(output_item["DescriptionPTBR"] or "") if output_item else ""
        category, subcategory = market_category(output_item) if output_item else ("Outros", "Consumable")
        recipes.append(
            (
                recipe_key, recipe["ItemCraftIndex"], str(recipe["Craft_Result_Normal"]), output_name,
                description, category, subcategory, int(output_item["Grade"]) if output_item else 0,
                int(output_item["Tier"]) if output_item else 0, int(output_item["UseLv"]) if output_item else 0,
                str(output_item["Icon"] or "") if output_item else "", recipe["CraftCostType"], recipe["CraftCostValue"],
                recipe["CraftPeriod"], recipe["Craft_Result_Normal_Enchant"], recipe["Craft_Result_Normal_Prob"],
                recipe["Craft_Result_Better_Prob"], recipe["Craft_Result_Huge_Prob"], recipe["Craft_Result_Fail_Prob"],
                searchable(f"{output_name} {output_name_en} {recipe['Craft_Result_Normal']} {recipe['ItemCraftIndex']}"),
                output_name_en,
            )
        )
        for slot in range(1, 8):
            group_id = int(recipe[f"Material_ItemGroup{slot}"])
            if not group_id:
                continue
            for item in groups.get(group_id) or [None]:
                name_id = str(item["NameStringIndex"]) if item else ""
                materials.append(
                    (
                        recipe_key, slot, group_id, recipe[f"Material{slot}Value"],
                        recipe[f"Material{slot}_Enchant_Value"], str(item["ItemIndex"]) if item else "0",
                        str(item["NamePTBR"] or "") if item else "", int(item["Grade"]) if item else 0,
                        int(item["Tier"]) if item else 0, str(item["Icon"] or "") if item else "",
                        strings_en.get(name_id, ""),
                    )
                )
        for result_type, suffix in (("normal", "Normal"), ("better", "Better"), ("huge", "Huge")):
            item_id = int(recipe[f"Craft_Result_{suffix}"])
            if not item_id:
                continue
            item = items.get(item_id)
            name_id = str(item["NameStringIndex"]) if item else ""
            results.append(
                (
                    recipe_key, result_type, str(item_id), str(item["NamePTBR"] or "") if item else "",
                    recipe[f"Craft_Result_{suffix}_Enchant"], recipe[f"Craft_Result_{suffix}_Prob"],
                    recipe[f"Craft_Result_{suffix}_Value"], int(item["Grade"]) if item else 0,
                    int(item["Tier"]) if item else 0, str(item["Icon"] or "") if item else "",
                    strings_en.get(name_id, ""),
                )
            )
    app.executemany("INSERT INTO craft_recipes VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", recipes)
    app.executemany("INSERT INTO craft_materials VALUES(?,?,?,?,?,?,?,?,?,?,?)", materials)
    app.executemany("INSERT INTO craft_results VALUES(?,?,?,?,?,?,?,?,?,?,?)", results)

    reward_groups = {
        (int(row["RewardIndex"]), str(row["BoxType"]), int(row["SubGroupIndex"]))
        for row in rows(new, "RF_RewardTableRow")
    }
    subgroup_outputs: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for row in rows(new, "RF_SubGroupInfoRow"):
        subgroup_outputs[int(row["SubGroupIndex"])].append(row)
    npc_by_reward: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for npc in npc_rows:
        if reward_index := int(npc["RewardIndex"]):
            npc_by_reward[reward_index].append(npc)
    loot = []
    for reward_index, box_type, subgroup_index in sorted(reward_groups):
        for npc in npc_by_reward.get(reward_index, ()):
            for reward in subgroup_outputs.get(subgroup_index, ()):
                item_id = int(reward["RewardItemIndex"])
                item = items.get(item_id)
                is_exp = item_id == 900
                loot.append(
                    (
                        str(npc["NPCIndex"]), str(npc["NamePTBR"] or ""), npc["Level"], reward_index,
                        box_type, subgroup_index, str(item_id), "exp" if is_exp else "item",
                        str(item["NamePTBR"] or "") if item else "", "RF_ItemTable", reward["MinValue"],
                        reward["EnchantLevel"], str(reward["BiosuitType"]), 0,
                    )
                )
    app.execute("DELETE FROM loot_candidates")
    app.executemany("INSERT INTO loot_candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", loot)

    raw_items = rows(new, "RF_ItemTable")
    item_rewards = {int(row["ItemIndex"]): int(row["ItemReward"]) for row in raw_items}
    blocked = {int(row["Dismantle_Ditch_ItemIndex"]) for row in rows(new, "RF_Dismantle_Ditch_ItemList")}
    rules_by_item_reward: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for rule in rows(new, "RF_ItemTable_Reward"):
        rules_by_item_reward[int(rule["ItemReward"])].append(rule)
    reward_subgroups: dict[int, list[int]] = defaultdict(list)
    for reward_index, _, subgroup_index in reward_groups:
        reward_subgroups[reward_index].append(subgroup_index)
    salvage = []
    for item_id, item_reward in item_rewards.items():
        if not item_reward or item_id in blocked:
            continue
        for rule in rules_by_item_reward[item_reward]:
            reward_index = int(rule["Dismantle_RewardIndex"])
            for subgroup_index in reward_subgroups.get(reward_index, ()):
                for reward in subgroup_outputs.get(subgroup_index, ()):
                    if int(reward["MinValue"]) > 0:
                        salvage.append(
                            (
                                str(item_id), int(rule["Level"]), str(reward["RewardItemIndex"]),
                                int(reward["MinValue"]), int(reward["EnchantLevel"]),
                                str(reward["BiosuitType"]), reward_index,
                            )
                        )
    salvage = list(dict.fromkeys(salvage))
    app.execute("DELETE FROM salvage_items")
    app.execute("DELETE FROM salvage_results")
    app.executemany(
        "INSERT INTO salvage_items VALUES(?,?,?,?,?,?)",
        (
            (
                str(row["ItemIndex"]), str(row["NamePTBR"] or f"ItemIndex {row['ItemIndex']}"),
                searchable(f"{row['NamePTBR']} {strings_en.get(str(row['NameStringIndex']), '')} {row['ItemIndex']}"),
                row["Grade"], row["Tier"], str(row["Icon"] or ""),
            )
            for row in item_rows
        ),
    )
    app.executemany("INSERT INTO salvage_results VALUES(?,?,?,?,?,?,?)", salvage)
    equipment_count = rebuild_equipment_compare(app, new, strings)
    upgrade_rule_count, upgrader_item_count = rebuild_equipment_upgrade_rules(app, new, strings)

    app.execute("DELETE FROM quality")
    app.executemany(
        "INSERT INTO quality VALUES(?,?,?,?,?)",
        (tuple(row) for row in rows(new, "_quality_checks")),
    )
    metadata = {
        "source_version": source_version,
        "generated_at": updated_at,
        "count_item": entity_counts["item"],
        "count_collection": entity_counts["collection"],
        "count_map": entity_counts["map"],
        "count_mission": entity_counts["mission"],
        "count_npc": entity_counts["npc"],
        "count_skill": entity_counts["skill"],
        "count_collection_requirements": len(requirements),
        "count_loot_candidates": len(loot),
        "count_craft_recipes": len(recipes),
        "count_craft_materials": len(materials),
        "count_salvage_items": len({row[0] for row in salvage}),
        "count_salvage_results": len(salvage),
        "count_salvage_reward_items": len({row[2] for row in salvage}),
        "count_salvage_blocked": len(blocked),
        "count_content_changes": len(tags),
        "count_equipment_compare": equipment_count,
        "count_equipment_upgrade_rules": upgrade_rule_count,
        "count_equipment_upgrader_items": upgrader_item_count,
        "count_market_item_aliases": len(market_aliases),
        "asset_update": asset_update,
    }
    app.executemany(
        "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        ((key, str(value)) for key, value in metadata.items()),
    )

    if app.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise RuntimeError("SQLite inválido após atualização")
    expected = {
        "item_details": len(item_rows),
        "collection_details": len(collection_rows),
        "collection_requirements": len(requirements),
        "craft_recipes": len(recipes),
        "craft_materials": len(materials),
        "craft_results": len(results),
        "salvage_results": len(salvage),
        "loot_candidates": len(loot),
        "equipment_compare": equipment_count,
        "equipment_upgrade_rules": upgrade_rule_count,
        "equipment_upgrader_items": upgrader_item_count,
        "market_item_aliases": len(market_aliases),
    }
    actual = {table: app.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0] for table in expected}
    if actual != expected:
        raise RuntimeError(f"Contagens inesperadas: {actual}")
    if app.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise RuntimeError("SQLite contém violação de chave estrangeira")
    app.commit()
    app.close()

    collection_stats = stat_types(new, strings)
    bonus_rows = []
    for row in collection_rows:
        required = sum(
            bool(int(row[f"Collection{slot}_ItemGroup"])) and bool(int(row[f"Collection{slot}_Value"]))
            for slot in range(1, 11)
        )
        for slot in range(1, 4):
            stat_type = int(row[f"RewardStat{slot}_Type"])
            if stat_type:
                stat_enum, stat_name = collection_stats.get(stat_type, ("", ""))
                bonus_rows.append((row["CollectionIndex"], "complete", required, stat_type, stat_enum, stat_name, row[f"RewardStat{slot}_Value"]))
    for row in rows(new, "RF_Collection_PartReward"):
        stat_type = int(row["StatType"])
        if stat_type and int(row["Number"]) > 0:
            stat_enum, stat_name = collection_stats.get(stat_type, ("", ""))
            bonus_rows.append((row["CollectionIndex"], "partial", row["Number"], stat_type, stat_enum, stat_name, row["StatValue"]))
    with bonuses.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("CollectionIndex", "RewardKind", "RequiredSlots", "StatType", "StatEnum", "StatNamePTBR", "StatValue"))
        writer.writerows(bonus_rows)

    old.close()
    new.close()
    temporary.replace(output)
    print(f"Banco atualizado: {output}")
    print(f"Tags: {len(tags)}; bônus: {len(bonus_rows)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--old-raw", type=Path, required=True)
    parser.add_argument("--new-raw", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bonuses", type=Path, required=True)
    parser.add_argument("--source-version", required=True)
    parser.add_argument("--asset-update", required=True)
    args = parser.parse_args()
    rebuild(
        args.output,
        args.base,
        args.old_raw,
        args.new_raw,
        args.bonuses,
        args.source_version,
        args.asset_update,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
