#!/usr/bin/env python3
"""Build farm_dataset.json from rfnext-data.sqlite (RF Next 1.28.5).

Modo ponytail: uma passada por tabela, join em memoria, sem abstracoes extras.
"""
import csv
import json
import sqlite3
import sys
from datetime import datetime, timezone

DB = "/sessions/rcw-01wqvmfxavcrqdrdpxnq6y86/mnt/rf-next/analysis/1.28.5/rfnext-data.sqlite"
STRINGS_CSV = "/sessions/rcw-01wqvmfxavcrqdrdpxnq6y86/mnt/rf-next/analysis/1.28.5/exports/strings-ptbr.csv"
OUT = "/sessions/rcw-01wqvmfxavcrqdrdpxnq6y86/mnt/rf-next/calc/farm_dataset.json"
VERSION = "1.28.5"

KNOWN_HP = {
    305208: 32560,  # Ramon Clops Sniper
    305215: 30540,  # Junker Desenfreado
    361269: 22648,  # Fantasma do Pesadelo
    361270: 29037,  # Fundidor Guardiao
    361271: 25407,  # Fundidor Purificador
}

EXP_ITEM = 900
CREDIT_ITEM = 1


def load_strings():
    strings = {}
    with open(STRINGS_CSV, encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        header = next(r)
        for row in r:
            if len(row) < 2:
                continue
            sid, text = row[0], row[1]
            strings[sid] = text
    return strings


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()

    strings = load_strings()

    def sname(string_id):
        if not string_id:
            return ""
        return strings.get(string_id, "")

    # level curve
    cur.execute("select Level, PC_NeedExp from RF_LevelUpTable order by Level")
    level_curve = [{"level": lvl, "need_exp": exp} for lvl, exp in cur.fetchall()]

    # server boost: StatType 87 = exp, 86 = gold
    cur.execute("select BuffStatType, MinLevel, MaxLevel, ExpBuffValue, GoldBuffValue from RF_BoostSeverTable")
    boost_rows = cur.fetchall()
    boost_by_range = {}
    for stat_type, min_lvl, max_lvl, exp_val, gold_val in boost_rows:
        key = (min_lvl, max_lvl)
        entry = boost_by_range.setdefault(key, {"min_level": min_lvl, "max_level": max_lvl, "exp_pct": 0.0, "gold_pct": 0.0})
        if stat_type == 87:
            entry["exp_pct"] = exp_val / 10000.0
        elif stat_type == 86:
            entry["gold_pct"] = gold_val / 10000.0
    server_boost = [boost_by_range[k] for k in sorted(boost_by_range.keys())]

    # RewardIndex -> list of SubGroupIndex
    cur.execute("select RewardIndex, SubGroupIndex from RF_RewardTableRow")
    reward_to_subgroups = {}
    for reward_idx, subgroup_idx in cur.fetchall():
        reward_to_subgroups.setdefault(reward_idx, []).append(subgroup_idx)

    # SubGroupIndex -> list of (RewardItemIndex, MinValue)
    cur.execute("select SubGroupIndex, RewardItemIndex, MinValue from RF_SubGroupInfoRow")
    subgroup_items = {}
    for subgroup_idx, item_idx, min_val in cur.fetchall():
        subgroup_items.setdefault(subgroup_idx, []).append((item_idx, min_val))

    # item name cache: ItemIndex -> NameStringIndex -> text
    cur.execute("select ItemIndex, NameStringIndex from RF_ItemTable")
    item_name_string = dict(cur.fetchall())

    def item_name(item_idx):
        sid = item_name_string.get(item_idx)
        return sname(sid)

    # maps: MapIndex -> MapNameString -> text
    cur.execute("select MapIndex, MapNameString from RF_MapTable")
    map_name_string = dict(cur.fetchall())
    map_name_cache = {}

    def map_name(map_idx):
        if map_idx in map_name_cache:
            return map_name_cache[map_idx]
        sid = map_name_string.get(map_idx)
        val = sname(sid)
        map_name_cache[map_idx] = val
        return val

    # NPCIndex -> maps list (aggregated by MapIndex, sum SpawnValue)
    cur.execute("select NPCIndex, MapIndex, RegionIndex, SpawnValue from RF_MapInfoTable_Spawn")
    npc_maps = {}
    for npc_idx, map_idx, region_idx, spawn_val in cur.fetchall():
        d = npc_maps.setdefault(npc_idx, {})
        if map_idx in d:
            d[map_idx]["spawn"] += spawn_val or 0
        else:
            d[map_idx] = {"map": map_idx, "name": map_name(map_idx), "region": region_idx, "spawn": spawn_val or 0}

    # main NPC table
    cur.execute("select NPCIndex, Level, RewardIndex, NameStringIndex, NPCType, Grade from RF_NPCTable")
    npc_rows = cur.fetchall()

    mobs = []
    for npc_idx, level, reward_idx, name_string_idx, npc_type, grade in npc_rows:
        subgroups = reward_to_subgroups.get(reward_idx)
        if not subgroups:
            continue

        exp_base = None
        credit_base = None
        loot = {}  # item_id -> min value (dedup, keep lowest)
        for sg in subgroups:
            for item_idx, min_val in subgroup_items.get(sg, ()):
                if item_idx == EXP_ITEM:
                    exp_base = min_val
                elif item_idx == CREDIT_ITEM:
                    credit_base = min_val
                else:
                    if item_idx in loot:
                        if min_val < loot[item_idx]:
                            loot[item_idx] = min_val
                    else:
                        loot[item_idx] = min_val

        if exp_base is None:
            continue  # only mobs that have exp reward

        loot_list = [
            {"item": item_idx, "name": item_name(item_idx), "min": min_val}
            for item_idx, min_val in sorted(loot.items())
        ]

        maps_list = list(npc_maps.get(npc_idx, {}).values())
        maps_list.sort(key=lambda m: m["map"])

        mobs.append({
            "id": npc_idx,
            "name": sname(name_string_idx),
            "level": level,
            "grade": grade,
            "type": npc_type,
            "exp_base": exp_base,
            "credit_base": credit_base if credit_base is not None else 0,
            "maps": maps_list,
            "loot": loot_list,
            "hp": KNOWN_HP.get(npc_idx),
        })

    mobs.sort(key=lambda m: m["id"])

    dataset = {
        "version": VERSION,
        "generated": datetime.now(timezone.utc).isoformat(),
        "level_curve": level_curve,
        "server_boost": server_boost,
        "mobs": mobs,
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, separators=(",", ":"))

    # ---- validations ----
    print("=== VALIDATIONS ===")

    by_id = {m["id"]: m for m in mobs}

    m1 = by_id.get(361270)
    ok1a = m1 is not None and m1["exp_base"] == 9669 and m1["credit_base"] == 454
    print(f"1a) mob 361270 exp_base==9669 credit_base==454: "
          f"{'PASS' if ok1a else 'FAIL'} (got exp_base={m1['exp_base'] if m1 else None}, credit_base={m1['credit_base'] if m1 else None})")

    m2 = by_id.get(305208)
    ok1b = m2 is not None and m2["exp_base"] == 10869 and m2["credit_base"] == 474
    print(f"1b) mob 305208 exp_base==10869 credit_base==474: "
          f"{'PASS' if ok1b else 'FAIL'} (got exp_base={m2['exp_base'] if m2 else None}, credit_base={m2['credit_base'] if m2 else None})")

    v2a = int(9669 * (1 + 0.35 + 0.20))
    ok2a = v2a == 14986
    print(f"2a) floor(9669*(1+0.35+0.20))==14986: {'PASS' if ok2a else 'FAIL'} (got {v2a})")

    v2b = int(10869 * (1 + 0.35 + 0.15))
    ok2b = v2b == 16303
    print(f"2b) floor(10869*(1+0.35+0.15))==16303: {'PASS' if ok2b else 'FAIL'} (got {v2b})")

    need_exp_sum = sum(e["need_exp"] for e in level_curve if 2 <= e["level"] <= 200)
    ok3 = need_exp_sum == 3022660132182889
    print(f"3) sum need_exp levels 2..200 == 3022660132182889: {'PASS' if ok3 else 'FAIL'} (got {need_exp_sum})")

    import os
    size_bytes = os.path.getsize(OUT)
    print(f"4) total mobs: {len(mobs)} (expected ~2566)")
    print(f"4) farm_dataset.json size: {size_bytes} bytes")

    all_pass = ok1a and ok1b and ok2a and ok2b and ok3
    print(f"\nOVERALL: {'ALL PASS' if all_pass else 'SOME FAILED'}")

    # sample mob for reporting
    sample = mobs[0] if mobs else None
    if sample:
        print("\nSample mob:")
        print(json.dumps(sample, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
