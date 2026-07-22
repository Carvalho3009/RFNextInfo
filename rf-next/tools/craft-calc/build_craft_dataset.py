#!/usr/bin/env python3
"""Build calc/craft_dataset.json from RF Online Next 1.28.5 offline DB + market.csv.
Re-runnable: regenerates the JSON from scratch. Stdlib only."""
import sqlite3, csv, json, os, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = os.path.join(ROOT, "analysis", "1.28.5", "rfnext-data.sqlite")
MARKET = os.path.join(ROOT, "captures", "market.csv")
OUT = os.path.join(ROOT, "calc", "craft_dataset.json")


def iso(ts):
    return datetime.datetime.fromtimestamp(ts).astimezone().isoformat()


def main():
    con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
    cur = con.cursor()

    # ---- asserts on the raw data (fail loud) ----
    cur.execute("SELECT COUNT(*), SUM(CASE WHEN CraftCostType=1 THEN 1 ELSE 0 END) FROM RF_ItemCraft")
    n, n_cost1 = cur.fetchone()
    assert n == n_cost1, "CraftCostType not always 1"
    cur.execute("SELECT COUNT(*) FROM RF_ItemCraft WHERE "
                "(Craft_Result_Normal_Prob+Craft_Result_Better_Prob+Craft_Result_Huge_Prob+Craft_Result_Fail_Prob)<>10000")
    assert cur.fetchone()[0] == 0, "some roulette does not sum to 10000"

    # ---- categories ----
    cats = {}
    cur.execute("SELECT ItemCraftCategoryIndex, MainTab, SubTab FROM RF_ItemCraftCategory")
    for idx, main, sub in cur.fetchall():
        cats[str(idx)] = {"main": main, "sub": sub}

    # ---- recipes ----
    cur.execute("SELECT * FROM RF_ItemCraft")
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    recipes = []
    referenced = set()  # item indices used anywhere
    for r in rows:
        mats = []
        for k in range(1, 8):
            item = r["Material_ItemGroup%d" % k]
            if item is None or item <= 0:
                continue
            mats.append({"item": item, "qty": r["Material%dValue" % k],
                         "ench": r["Material%d_Enchant_Value" % k]})
            referenced.add(item)
        results = []
        for tier in ("Normal", "Better", "Huge"):
            prob = r["Craft_Result_%s_Prob" % tier]
            if prob and prob > 0:
                it = r["Craft_Result_%s" % tier]
                results.append({"item": it, "ench": r["Craft_Result_%s_Enchant" % tier],
                                "qty": r["Craft_Result_%s_Value" % tier], "prob": prob})
                referenced.add(it)
        rec = {"id": r["ItemCraftIndex"], "cat": r["ItemCraftCategoryIndex"],
               "sort": r["Sort"], "fee": r["CraftCostValue"],
               "mats": mats, "results": results}
        fp = r["Craft_Result_Fail_Prob"]
        if fp and fp > 0:
            ret_item = r["Material1_Fail_Return_Item"] or 0
            rec["fail"] = {"prob": fp, "ret_item": ret_item,
                           "ret_ench": r["Material1_Fail_Return_Item_Enchant"] or 0,
                           "ret_qty": r["Material1_Fail_Return_Value"] or 0}
            if ret_item > 0:
                referenced.add(ret_item)
        rec["uid"] = len(recipes)  # ItemCraftIndex NAO e unico (1086 linhas/1004 ids; variantes de insumo)
        recipes.append(rec)

    # ---- names (PT-BR) for referenced items ----
    names = {}
    if referenced:
        qmarks = ",".join("?" * len(referenced))
        cur.execute(
            "SELECT it.ItemIndex, s.KO_KR FROM RF_ItemTable it "
            "JOIN RF_StringTable_PT_BR s ON it.NameStringIndex = s.StringID "
            "WHERE it.ItemIndex IN (%s)" % qmarks, tuple(referenced))
        for item, name in cur.fetchall():
            names[str(item)] = name

    # ---- tradeable flag: only TradeAble=0 (non-tradeable) among referenced ----
    tradeable = {}
    if referenced:
        cur.execute("SELECT ItemIndex, TradeAble FROM RF_ItemTable WHERE ItemIndex IN (%s)" % qmarks,
                    tuple(referenced))
        for item, tr in cur.fetchall():
            if tr == 0:
                tradeable[str(item)] = 0

    # ---- prices from market.csv ----
    prices = {}
    with open(MARKET, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            item = row["ItemIndex"].strip()
            ench = row["Enhance"].strip()
            try:
                ppu = float(row["PricePerUnit"])
            except (ValueError, KeyError):
                continue
            prices.setdefault(item, {})[ench] = ppu

    mtime = os.path.getmtime(MARKET)
    data = {
        "generated_at": datetime.datetime.now().astimezone().isoformat(),
        "market_snapshot": "captures/market.csv @ %s" % iso(mtime),
        "cats": cats,
        "recipes": recipes,
        "prices": prices,
        "names": names,
        "tradeable": tradeable,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    # ---- report ----
    def priced(item, ench):
        return str(item) in prices and str(ench) in prices[str(item)]

    full = partial = none = 0
    for rec in recipes:
        ms = rec["mats"]
        if not ms:
            none += 1
            continue
        hit = sum(1 for m in ms if priced(m["item"], m["ench"]))
        if hit == len(ms):
            full += 1
        elif hit == 0:
            none += 1
        else:
            partial += 1

    bad = sum(1 for r in rows if (r["Craft_Result_Normal_Prob"] + r["Craft_Result_Better_Prob"]
              + r["Craft_Result_Huge_Prob"] + r["Craft_Result_Fail_Prob"]) != 10000)
    print("recipes: %d" % len(recipes))
    print("all roulettes sum to 10000: %s (bad=%d)" % (bad == 0, bad))
    print("price coverage -> fully: %d  partial: %d  none: %d" % (full, partial, none))
    print("output: %s (%d bytes)" % (OUT, os.path.getsize(OUT)))


if __name__ == "__main__":
    main()
