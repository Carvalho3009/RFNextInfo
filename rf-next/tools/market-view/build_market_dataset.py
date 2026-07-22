#!/usr/bin/env python3
"""Gera dataset JSON de mercado para o RF Online Next.

Le um sqlite estatico do cliente (RF_ItemTable + RF_StringTable_PT_BR) e um
snapshot de mercado (JSONL, um objeto por linha, chave opcional
"exchange.exchange_item_simple_infos" com a lista de ofertas capturadas).

REGRA DE OURO: nunca inventar dado. Item sem metadados no banco vira
fallback explicito (meta_ok=false) em vez de ser descartado ou preenchido
com valores chutados.

Uso:
    python3 build_market_dataset.py --db cliente.sqlite --snapshot captura.jsonl -o mercado.json
    python3 build_market_dataset.py --db cliente.sqlite -o mercado.json
        (sem --snapshot: usa o *.exchange.jsonl mais recente em ./captures)
"""
import argparse
import collections
import glob
import json
import os
import re
import sqlite3
import sys

CAT_LABELS = {
    0: "Outros",
    1: "Arma",
    2: "Armadura",
    3: "Acessórios",
    4: "Expansão",
    6: "Livro de Hab.",
    7: "Material",
    8: "Outros",
}

SUB_PREFIX_TWO_WORDS = {"Protetor", "Arma", "Guarda"}


def cat_label(cat):
    return CAT_LABELS.get(cat, f"Categoria {cat}")


def find_latest_snapshot(captures_dir="captures"):
    candidates = glob.glob(os.path.join(captures_dir, "*.exchange.jsonl"))
    if not candidates:
        sys.exit(f"Nenhum *.exchange.jsonl encontrado em '{captures_dir}/'.")
    return max(candidates, key=os.path.getmtime)


def snapshot_label(path):
    base = os.path.basename(path)
    m = re.search(r"(\d{8})-(\d{6})", base)
    if m:
        try:
            import datetime
            dt = datetime.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
            return dt.strftime("%d/%m/%Y %H:%M")
        except ValueError:
            pass
    import datetime
    dt = datetime.datetime.fromtimestamp(os.path.getmtime(path))
    return dt.strftime("%d/%m/%Y %H:%M")


def get_infos(obj):
    """Extrai a lista exchange.exchange_item_simple_infos, aceitando tanto
    chave plana literal quanto objeto aninhado {"exchange": {...}}."""
    flat = obj.get("exchange.exchange_item_simple_infos")
    if flat is not None:
        return flat
    exch = obj.get("exchange")
    if isinstance(exch, dict):
        return exch.get("exchange_item_simple_infos")
    return None


def price_val(v):
    """Preco float integral vira int; null/0/ausente vira None (explicito)."""
    if v is None or v == 0:
        return None
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def load_snapshot(path):
    """Agrega por (item_index, enchant_level); ultima ocorrencia vence."""
    agg = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            infos = get_infos(obj)
            if not infos:
                continue
            for info in infos:
                try:
                    item_index = int(info["item_index"])
                    enchant = int(info.get("enchant_level", 0))
                except (KeyError, TypeError, ValueError):
                    continue
                agg[(item_index, enchant)] = {
                    "item_index": item_index,
                    "enchant_level": enchant,
                    "lowest_price": info.get("lowest_price"),
                    "highest_price": info.get("highest_price"),
                    "number_of_registered_items": info.get("number_of_registered_items"),
                    "item_name": info.get("item_name"),
                }
    return agg


def load_db(db_path):
    conn = sqlite3.connect("file:" + db_path + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def build_string_map(conn):
    rows = conn.execute("SELECT StringID, KO_KR FROM RF_StringTable_PT_BR").fetchall()
    return {str(r["StringID"]): r["KO_KR"] for r in rows}


def build_grade_labels(conn):
    labels = {}
    try:
        rows = conn.execute(
            "SELECT StringID, KO_KR FROM RF_StringTable_PT_BR WHERE StringID LIKE 'ui_grade_text_%'"
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    for r in rows:
        m = re.search(r"(\d+)$", str(r["StringID"]))
        if m:
            labels[int(m.group(1))] = r["KO_KR"]
    return labels


def grade_label(grade, grade_labels):
    return grade_labels.get(grade, f"Grau {grade}")


def build_itemtable_index(conn, str_map):
    """ItemIndex -> dict com metadados + nome resolvido."""
    rows = conn.execute(
        "SELECT ItemIndex, NameStringIndex, ItemCategory, ItemSubCategory, "
        "ItemType, Grade, Quality, UseLv FROM RF_ItemTable"
    ).fetchall()
    index = {}
    for r in rows:
        name = str_map.get(str(r["NameStringIndex"]))
        index[int(r["ItemIndex"])] = {
            "name": name,
            "cat": r["ItemCategory"],
            "sub": r["ItemSubCategory"],
            "grade": r["Grade"],
            "quality": r["Quality"],
            "lv": r["UseLv"],
        }
    return index


def derive_sub_label(sub_id, conn, str_map):
    """Deriva o rotulo de uma subcategoria a partir dos nomes dos itens
    dessa sub nas categorias 1 (Arma), 2 (Armadura) e 3 (Acessorios)."""
    rows = conn.execute(
        "SELECT NameStringIndex FROM RF_ItemTable "
        "WHERE ItemSubCategory = ? AND ItemCategory IN (1, 2, 3)",
        (sub_id,),
    ).fetchall()
    names = []
    for r in rows:
        n = str_map.get(str(r["NameStringIndex"]))
        if not n:
            continue
        if n.startswith("(Evento)"):
            continue
        names.append(n)
    if len(names) < 3:
        return f"Tipo {sub_id}"

    prefixes = []
    for n in names:
        words = n.split()
        if not words:
            continue
        first = words[0]
        if first in SUB_PREFIX_TWO_WORDS and len(words) >= 2:
            pref = [first, words[1]]
            # prefixo terminando em preposicao inclui a palavra seguinte
            # (ex.: "Arma de Fogo", "Protetor de Pernas")
            while pref[-1].lower() in ("de", "da", "do", "dos", "das") and len(words) > len(pref):
                pref.append(words[len(pref)])
            prefixes.append(" ".join(pref))
        else:
            prefixes.append(first)

    if not prefixes:
        return f"Tipo {sub_id}"

    counter = collections.Counter(prefixes)
    label, count = counter.most_common(1)[0]
    if count / len(names) < 0.5:
        return f"Tipo {sub_id}"
    return label


def main():
    ap = argparse.ArgumentParser(description="Gera dataset JSON de mercado (RF Online Next).")
    ap.add_argument("--db", required=True, help="Caminho do sqlite estatico do cliente.")
    ap.add_argument("--snapshot", help="Caminho do snapshot JSONL. Se omitido, usa o "
                                       "*.exchange.jsonl mais recente em ./captures.")
    ap.add_argument("-o", "--output", required=True, help="Caminho do JSON de saida.")
    args = ap.parse_args()

    snapshot_path = args.snapshot or find_latest_snapshot(
        os.path.join(os.getcwd(), "captures")
    )
    if not os.path.isfile(snapshot_path):
        sys.exit(f"Snapshot não encontrado: {snapshot_path}")
    if not os.path.isfile(args.db):
        sys.exit(f"Banco não encontrado: {args.db}")

    agg = load_snapshot(snapshot_path)

    conn = load_db(args.db)
    str_map = build_string_map(conn)
    grade_labels = build_grade_labels(conn)
    itemtable = build_itemtable_index(conn, str_map)

    # Agrupa ofertas por item_index.
    by_item = collections.defaultdict(list)
    for (item_index, enchant), rec in agg.items():
        by_item[item_index].append(rec)

    # Resolve metadados de cada item e detecta as subcategorias presentes
    # para derivar seus rotulos sob demanda (uma unica query por sub).
    meta_by_item = {}
    for item_index, recs in by_item.items():
        meta = itemtable.get(item_index)
        if meta is None or not meta["name"]:
            meta_by_item[item_index] = {
                "name": recs[-1].get("item_name") or f"Item {item_index}",
                "cat": 0,
                "sub": 0,
                "grade": 0,
                "quality": 0,
                "lv": 0,
                "meta_ok": False,
            }
        else:
            meta_by_item[item_index] = {
                "name": meta["name"],
                "cat": meta["cat"] if meta["cat"] is not None else 0,
                "sub": meta["sub"] if meta["sub"] is not None else 0,
                "grade": meta["grade"] if meta["grade"] is not None else 0,
                "quality": meta["quality"] if meta["quality"] is not None else 0,
                "lv": meta["lv"] if meta["lv"] is not None else 0,
                "meta_ok": True,
            }

    sub_ids_present = {m["sub"] for m in meta_by_item.values() if m["meta_ok"]}
    sub_labels = {sub_id: derive_sub_label(sub_id, conn, str_map) for sub_id in sub_ids_present}

    items = []
    for item_index, recs in by_item.items():
        meta = meta_by_item[item_index]
        recs_sorted = sorted(recs, key=lambda r: r["enchant_level"])
        of = [
            [
                r["enchant_level"],
                price_val(r["lowest_price"]),
                price_val(r["highest_price"]),
                r["number_of_registered_items"] or 0,
            ]
            for r in recs_sorted
        ]
        items.append({
            "id": item_index,
            "n": meta["name"],
            "cat": meta["cat"],
            "sub": meta["sub"],
            "grade": meta["grade"],
            "q": meta["quality"],
            "lv": meta["lv"],
            "meta_ok": meta["meta_ok"],
            "of": of,
        })

    items.sort(key=lambda it: it["n"])

    cats_present = sorted({it["cat"] for it in items})
    subs_present = sorted({it["sub"] for it in items})
    grades_present = sorted({it["grade"] for it in items})

    out = {
        "meta": {
            "snapshot_file": os.path.basename(snapshot_path),
            "snapshot_label": snapshot_label(snapshot_path),
            "region": "world",
            "entries": len(agg),
            "bases": len(by_item),
        },
        "regions": [
            {"id": "world", "label": "Mercado Mundial", "available": True},
            {"id": "wg", "label": "Grupo de Mundos", "available": False},
        ],
        "cats": {str(c): cat_label(c) for c in cats_present},
        "subs": {str(s): sub_labels.get(s, f"Tipo {s}") for s in subs_present},
        "grades": {str(g): grade_label(g, grade_labels) for g in grades_present},
        "items": items,
    }

    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))

    bases_multi = sum(1 for recs in by_item.values() if len(recs) > 1)
    meta_bad = sum(1 for it in items if not it["meta_ok"])
    print(f"entradas: {len(agg)}")
    print(f"bases (item_index distintos): {len(by_item)}")
    print(f"bases com >1 variante (encantamento): {bases_multi}")
    print(f"itens meta_ok=false: {meta_bad}")
    print(f"categorias presentes: {sorted(cats_present)}")


if __name__ == "__main__":
    main()
