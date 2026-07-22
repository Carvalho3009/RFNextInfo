#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# build_dashboard_dataset.py
# Monta dashboard_dataset.json a partir de rfnext-data.sqlite (RF Online Next 1.28.5)
# Roda com CWD = pasta que contem rfnext-data.sqlite e exports/strings-ptbr.csv
# stdlib apenas: sqlite3, json, csv, os

import sqlite3
import json
import csv
import os

DB_PATH = "rfnext-data.sqlite"
STRINGS_CSV = os.path.join("exports", "strings-ptbr.csv")
OUT_PATH = "dashboard_dataset.json"

KNOWN_HP = {
    305208: 32560,
    305215: 30540,
    361269: 22648,
    361270: 29037,
    361271: 25407,
}

# 1. strings PT-BR
strings = {}
with open(STRINGS_CSV, "r", encoding="utf-8-sig", newline="") as f:
    reader = csv.reader(f)
    header = next(reader, None)
    for row in reader:
        if not row or len(row) < 2:
            continue
        # chaves sao texto, ex.: "Monster_Name_305208", "Map_Name_1"
        strings[row[0]] = row[1]


def sname(sid):
    if sid is None:
        return ""
    return strings.get(sid, "") or ""


# 2. conexao com o banco (somente leitura)
conn = sqlite3.connect("file:%s?mode=ro" % DB_PATH, uri=True)
cur = conn.cursor()

# 3. counts
count_tables = [
    ("npcs", "RF_NPCTable"),
    ("items", "RF_ItemTable"),
    ("maps", "RF_MapTable"),
    ("spawns", "RF_MapInfoTable_Spawn"),
    ("reward_rows", "RF_RewardTableRow"),
    ("subgroup_rows", "RF_SubGroupInfoRow"),
    ("quests", "RF_QuestMainTable"),
    ("skills", "RF_SkillTable"),
    ("crafts", "RF_ItemCraft"),
    ("collections", "RF_ItemCollection"),
    ("strings_ptbr", "RF_StringTable_PT_BR"),
]
counts = {}
for key, table in count_tables:
    cur.execute("SELECT COUNT(*) FROM %s" % table)
    counts[key] = cur.fetchone()[0]

# 4. RF_RewardTableRow -> reward_to_subgroups
reward_to_subgroups = {}
cur.execute("SELECT RewardIndex, SubGroupIndex FROM RF_RewardTableRow")
for reward_index, subgroup_index in cur.fetchall():
    reward_to_subgroups.setdefault(reward_index, []).append(subgroup_index)

# 5. RF_SubGroupInfoRow -> subgroup_items
subgroup_items = {}
cur.execute("SELECT SubGroupIndex, RewardItemIndex, MinValue FROM RF_SubGroupInfoRow")
for subgroup_index, reward_item_index, min_value in cur.fetchall():
    subgroup_items.setdefault(subgroup_index, []).append((reward_item_index, min_value))

# 6. RF_MapInfoTable_Spawn -> mobmaps e n_spawns por mapa
mobmaps = {}
map_spawn_count = {}
cur.execute("SELECT MapIndex, NPCIndex FROM RF_MapInfoTable_Spawn")
for map_index, npc_index in cur.fetchall():
    maps_set = mobmaps.setdefault(npc_index, set())
    maps_set.add(map_index)
    map_spawn_count[map_index] = map_spawn_count.get(map_index, 0) + 1

for npc_index in list(mobmaps.keys()):
    mobmaps[npc_index] = sorted(mobmaps[npc_index])

# 7. RF_MapTable -> maps
maps_out = {}
cur.execute("SELECT MapIndex, MapNameString, RecommendLv FROM RF_MapTable")
for map_index, map_name_string, recommend_lv in cur.fetchall():
    maps_out[map_index] = [sname(map_name_string), recommend_lv, map_spawn_count.get(map_index, 0)]

for map_index, spawn_count in map_spawn_count.items():
    if map_index not in maps_out:
        maps_out[map_index] = ["", None, spawn_count]

# 8. RF_ItemTable -> items
items_out = {}
cur.execute(
    "SELECT ItemIndex, NameStringIndex, Grade, Quality, Tier, ItemCategory, "
    "ItemSubCategory, UseLv, Sell_MoneyValue FROM RF_ItemTable"
)
for (item_index, name_string_index, grade, quality, tier, item_category,
     item_sub_category, use_lv, sell_money_value) in cur.fetchall():
    items_out[item_index] = [
        sname(name_string_index), grade, quality, tier, item_category,
        item_sub_category, use_lv, sell_money_value,
    ]

# 9. RF_NPCTable -> mobs + loot por RewardIndex + item_drops
cur.execute(
    "SELECT NPCIndex, Level, RewardIndex, NameStringIndex, TitleStringIndex, "
    "NPCType, NPCSubType, Grade FROM RF_NPCTable"
)
npc_rows = cur.fetchall()

needed_rewards = set()
for row in npc_rows:
    reward_index = row[2]
    if reward_index:
        needed_rewards.add(reward_index)

reward_data = {}
loot_out = {}
for reward_index in needed_rewards:
    item_qty = {}
    for subgroup_index in reward_to_subgroups.get(reward_index, []):
        for reward_item_index, min_value in subgroup_items.get(subgroup_index, []):
            item_qty[reward_item_index] = item_qty.get(reward_item_index, 0) + min_value

    exp_base = item_qty.pop(900, None)
    credit_base = item_qty.pop(1, None)
    contrib = item_qty.pop(1701, None)

    loot_list = sorted(item_qty.items())
    reward_data[reward_index] = (exp_base, credit_base, contrib, loot_list)
    loot_out[reward_index] = [[item, qty] for item, qty in loot_list]

item_drops = {}
mobs_out = []
for (npc_index, level, reward_index, name_string_index, title_string_index,
     npc_type, npc_sub_type, grade) in npc_rows:
    reward_index = reward_index or 0
    exp_base = credit_base = None
    if reward_index and reward_index in reward_data:
        exp_base, credit_base, _contrib, loot_list = reward_data[reward_index]
        for item, _qty in loot_list:
            item_drops.setdefault(item, set()).add(npc_index)

    hp = KNOWN_HP.get(npc_index)
    map_list = mobmaps.get(npc_index, [])

    mobs_out.append([
        npc_index, level, npc_type, npc_sub_type, grade,
        sname(name_string_index), reward_index, exp_base, credit_base, hp,
        map_list,
    ])

mobs_out.sort(key=lambda m: (m[1] if m[1] is not None else -1, m[5]))

item_drops_out = {item: sorted(npcs) for item, npcs in item_drops.items()}

# 10. dataset final
dataset = {
    "version": "1.28.5",
    "generated": "2026-07-22",
    "counts": counts,
    "hp_captured": len(KNOWN_HP),
    "mobs": mobs_out,
    "loot": loot_out,
    "items": items_out,
    "maps": maps_out,
    "item_drops": item_drops_out,
}

with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(dataset, f, separators=(",", ":"), ensure_ascii=False)

conn.close()

# 11. resumo
file_size_mb = os.path.getsize(OUT_PATH) / (1024.0 * 1024.0)

print("mobs: %d" % len(mobs_out))
print("itens: %d" % len(items_out))
print("mapas: %d" % len(maps_out))
print("rewards com loot: %d" % len(loot_out))
print("tamanho do arquivo: %.2f MB" % file_size_mb)
print("amostra de mobs:")
for sample in mobs_out[:3]:
    print(sample)
