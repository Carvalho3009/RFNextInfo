#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_codex_dataset.py - RF Next Codex (Colecoes) dataset builder.

Python 3 stdlib puro (roda no device do usuario). Le os exports 1.28.5 +
uma captura de mercado e gera codex_dataset.json no schema aprovado (SPEC).

Regra de ouro do projeto: NUNCA inventar dado. Preco ausente vira null no core
(nao e estimado aqui). Este script so materializa o que existe nos inputs.

Uso:
    python build_codex_dataset.py --exports DIR --exchange FILE_OU_DIR \
        --market FILE --out FILE
Defaults sao relativos ao repo do device (K:\\MCP\\projects\\rf-next).
Se --exchange for um diretorio, escolhe o *exchange*.jsonl de maior mtime.
Fonte de preco: exchange (preferida); se vazia/ausente, cai para market.csv.
"""
import argparse
import csv
import glob
import json
import os
import sys


def read_csv(path):
    # utf-8-sig remove o BOM que aparece no header de todos os exports/market.
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def to_int(v, default=0):
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return default


def to_num(v, default=0):
    s = str(v).strip()
    try:
        f = float(s)
        return int(f) if f.is_integer() else f
    except (ValueError, TypeError):
        return default


def newest_exchange(path):
    """Se path e diretorio, retorna o *exchange*.jsonl mais recente por mtime."""
    if os.path.isdir(path):
        cands = glob.glob(os.path.join(path, "*exchange*.jsonl"))
        if not cands:
            return None
        return max(cands, key=os.path.getmtime)
    return path if os.path.isfile(path) else None


def load_prices_exchange(path):
    """Le prices do jsonl. Usa a ULTIMA ocorrencia de cada par (item,ench)."""
    prices = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            ex = d.get("exchange")
            if not isinstance(ex, dict):
                continue
            infos = ex.get("exchange_item_simple_infos")
            if not infos:
                continue  # linhas de outro opcode (bookmarks/recomendados) nao tem infos
            for it in infos:
                key = "%s_%s" % (it["item_index"], it["enchant_level"])
                prices[key] = to_num(it["lowest_price"])  # ultima vence (snapshot recente)
    return prices


def load_prices_market(path):
    """Fallback: market.csv (PricePerUnit ja e o menor preco / lowest)."""
    prices = {}
    for row in read_csv(path):
        key = "%s_%s" % (to_int(row["ItemIndex"]), to_int(row["Enhance"]))
        prices[key] = to_num(row["PricePerUnit"])
    return prices


def build(exports_dir, exchange_path, market_path, out_path):
    coll_csv = os.path.join(exports_dir, "collections.csv")
    req_csv = os.path.join(exports_dir, "collection_requirements.csv")
    part_csv = os.path.join(exports_dir, "collection_part_rewards.csv")
    complete_csv = os.path.join(exports_dir, "collection_complete_rewards.csv")
    stat_csv = os.path.join(exports_dir, "stat_types.csv")

    # --- groups: itemGroup -> {acceptedItemIndex: nome} ---
    groups = {}
    for row in read_csv(req_csv):
        ig = to_int(row["ItemGroup"])
        if ig == 0:
            continue
        ai = to_int(row["AcceptedItemIndex"])
        groups.setdefault(ig, {})
        # primeiro nome visto por item vence (todos iguais na pratica)
        groups[ig].setdefault(ai, row["AcceptedItemNamePTBR"])

    # --- part rewards: CollectionIndex -> [[number, statId, valor], ...] ---
    part_rewards = {}
    for row in read_csv(part_csv):
        st = to_int(row["StatType"])
        if st == 0:
            continue
        ci = to_int(row["CollectionIndex"])
        part_rewards.setdefault(ci, []).append(
            [to_int(row["Number"]), st, to_num(row["StatValue"])]
        )

    # --- stat names: statId -> nomePT (fonte canonica) ---
    stat_names = {}
    for row in read_csv(stat_csv):
        stat_names[to_int(row["StatType"])] = row["StatNamePTBR"]

    used_stats = set()

    def note_stat(sid, fallback_name):
        used_stats.add(sid)
        if sid not in stat_names or not stat_names[sid]:
            if fallback_name:
                stat_names[sid] = fallback_name

    # --- collections ---
    collections = []
    for row in read_csv(coll_csv):
        ci = to_int(row["CollectionIndex"])
        req = []
        for n in range(1, 11):
            ig = to_int(row["Collection%d_ItemGroup" % n])
            if ig == 0:
                continue  # slot inativo
            ench = to_int(row["Collection%d_EnchantLevel" % n])
            qtd = to_int(row["Collection%d_Value" % n])
            req.append([n, ig, qtd, ench])

        rw = []
        for k in (1, 2, 3):
            t = to_int(row["RewardStat%d_Type" % k])
            if t == 0:
                continue
            rw.append([t, to_num(row["RewardStat%d_Value" % k])])
            note_stat(t, row.get("RewardStat%d_NamePTBR" % k, ""))

        prw = part_rewards.get(ci, [])
        for _num, sid, _val in prw:
            note_stat(sid, "")

        collections.append({
            "i": ci,
            "n": row["NamePTBR"],
            "t": to_int(row["CollectionType"]),
            "s": to_int(row["CollectionSeparation"]),
            "o": to_int(row["Sort"]),
            "ev": 1 if str(row["PeriodCollection"]).strip().lower() == "true" else 0,
            "chip": to_int(row["MemoryChipType"]),
            "req": req,
            "rw": rw,
            "prw": prw,
        })

    # --- type (complete) rewards: tipo -> [[itemCount, statId, valor], ...] ---
    type_rewards = {}
    for row in read_csv(complete_csv):
        tipo = to_int(row["CollectionType"])
        cnt = to_int(row["CollectionItemCount"])
        bucket = type_rewards.setdefault(tipo, [])
        for k in (1, 2):
            t = to_int(row["CompleteReward_Stat%dType" % k])
            if t == 0:
                continue
            bucket.append([cnt, t, to_num(row["CompleteReward_Stat%dValue" % k])])
            note_stat(t, row.get("CompleteReward_Stat%dNamePTBR" % k, ""))

    # --- prices ---
    price_source = None
    prices = {}
    xpath = newest_exchange(exchange_path) if exchange_path else None
    if xpath:
        prices = load_prices_exchange(xpath)
        price_source = xpath
    if not prices and market_path and os.path.isfile(market_path):
        # ponytail: sem exchange usavel caimos para market.csv; teto = snapshot unico
        #           sem historico por opcode. Upgrade: mesclar varias capturas por mtime.
        prices = load_prices_market(market_path)
        price_source = market_path

    # --- stats: so os usados ---
    stats = {}
    for sid in sorted(used_stats):
        stats[str(sid)] = stat_names.get(sid, "")

    # groups em formato de lista compacta + chaves string (JSON)
    groups_out = {}
    for ig in sorted(groups):
        groups_out[str(ig)] = [[ai, groups[ig][ai]] for ai in sorted(groups[ig])]

    type_rewards_out = {str(k): v for k, v in sorted(type_rewards.items())}

    dataset = {
        "generated_from": {
            "exports_dir": exports_dir,
            "price_source": price_source,
        },
        "collections": collections,
        "typeRewards": type_rewards_out,
        "groups": groups_out,
        "stats": stats,
        "prices": prices,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, separators=(",", ":"))

    active = sum(len(c["req"]) for c in collections)
    resolvable = 0
    for c in collections:
        for _slot, ig, _qtd, ench in c["req"]:
            for ai, _nm in groups_out.get(str(ig), []):
                if ("%d_%d" % (ai, ench)) in prices:
                    resolvable += 1
                    break

    size = os.path.getsize(out_path)
    sys.stderr.write(
        "OK %s\n"
        "  collections=%d  reqs(active slots)=%d  resolvable_slots=%d\n"
        "  groups=%d  stats=%d  prices=%d  typeRewards_types=%d\n"
        "  price_source=%s\n"
        "  bytes=%d (%.2f MB)\n"
        % (out_path, len(collections), active, resolvable,
           len(groups_out), len(stats), len(prices), len(type_rewards_out),
           price_source, size, size / 1048576.0)
    )
    return dataset


def main(argv):
    p = argparse.ArgumentParser(description="Build RF Next Codex dataset.")
    p.add_argument("--exports", default="analysis/1.28.5/exports",
                   help="diretorio dos CSVs exportados")
    p.add_argument("--exchange", default="captures",
                   help="arquivo .exchange.jsonl OU diretorio (glob *exchange*.jsonl)")
    p.add_argument("--market", default="captures/market.csv",
                   help="fallback de preco (market.csv)")
    p.add_argument("--out", default="codex_dataset.json",
                   help="caminho de saida do JSON")
    args = p.parse_args(argv)
    build(args.exports, args.exchange, args.market, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
