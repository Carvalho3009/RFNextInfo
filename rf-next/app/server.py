import csv
import hashlib
import io
import json
import math
import mimetypes
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import parse_qs, quote, unquote, urlparse

from PIL import Image, ImageOps, UnidentifiedImageError


ROOT = Path(__file__).parent
DB_PATH = Path(os.getenv("RFNEXT_DB", "/data/rfnext.db"))
GAME_DB_PATH = Path(os.getenv("RFNEXT_GAME_DB", ROOT / "rfnext-game-data.sqlite"))
MARKET_CSV_PATH = Path(os.getenv("RFNEXT_MARKET_CSV", "/data/market.csv"))
MARKET_IMAGE_ROOT = Path(os.getenv("RFNEXT_MARKET_IMAGE_ROOT", "/data/market-images"))
LOCAL_USER = os.getenv("RFNEXT_LOCAL_USER", "local")
MAX_BODY = 5 * 1024 * 1024
MAX_IMAGE = 12 * 1024 * 1024
MCP_VISION_URL = os.getenv("MCP_VISION_URL", "")
MCP_VISION_TOKEN = os.getenv("MCP_VISION_TOKEN", "")
MCP_VISION_TIMEOUT = int(os.getenv("MCP_VISION_TIMEOUT", "75"))
USERNAME = re.compile(r"[a-z0-9][a-z0-9_.-]{2,31}")
Image.MAX_IMAGE_PIXELS = 25_000_000

GAME_ENTITY_TYPES = {
    "item": ("Item", "item_details"),
    "npc": ("NPC", "npc_details"),
    "skill": ("Habilidade", "skill_details"),
    "map": ("Mapa", "map_details"),
    "mission": ("Missão", "mission_details"),
    "collection": ("Coleção", "collection_details"),
}

MARKET_TAXONOMY = {
    "Arma": ["Punisher", "Phantom", "Enforcer", "Psypher", "Dreadnought", "Technician", "Arbiter", "Demolisher"],
    "Armadura": ["Neck Guard", "Chest Guard", "Lower Guard", "Arm Guards", "Leg Guards"],
    "Acessório": ["Ear Cuffs", "Necklace", "Bangles", "Ring", "Circlet"],
    "Expansão": ["Drive", "Stargazer", "Deflector"],
    "Skillbook": ["Skillbook", "Skill Upgrade Material"],
    "Material": ["Powerup Materials", "Addon Materials"],
    "Material de Craft": ["Crafting Materials"],
    "Outros": ["Special Collectible", "Consumable"],
}


def normalize_user(value):
    value = value.strip().lower()
    return value if USERNAME.fullmatch(value) else None


def normalize_search(value):
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    return re.sub(r"\s+", " ", text.encode("ascii", "ignore").decode()).strip()


@contextmanager
def game_database():
    uri = GAME_DB_PATH.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def game_summary():
    with game_database() as db:
        meta = dict(db.execute("SELECT key, value FROM meta"))
        return {
            "version": meta.get("source_version", "—"),
            "generatedAt": meta.get("generated_at"),
            "counts": {
                kind: int(meta.get(f"count_{kind}", 0)) for kind in GAME_ENTITY_TYPES
            },
            "spawns": int(meta.get("count_spawns", 0)),
            "lootCandidates": int(meta.get("count_loot_candidates", 0)),
            "collectionRequirements": int(meta.get("count_collection_requirements", 0)),
            "lootNotice": "Os vínculos são candidatos extraídos das tabelas; a chance de drop não foi confirmada.",
        }


def game_search(query, entity_type, limit=50):
    if entity_type and entity_type not in GAME_ENTITY_TYPES:
        raise ValueError("Tipo inválido")
    search = normalize_search(query)[:80]
    limit = max(1, min(int(limit), 100))
    clauses, values = [], []
    if entity_type:
        clauses.append("entity_type = ?")
        values.append(entity_type)
    if search:
        clauses.append("search_text LIKE ?")
        values.append(f"%{search}%")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    sql = (
        "SELECT entity_type, entity_id, name, description, "
        "CASE WHEN entity_type = 'npc' THEN COALESCE((SELECT group_concat(map_name, ' · ') FROM "
        "(SELECT DISTINCT map_name FROM spawns WHERE npc_id = entities.entity_id AND map_name <> '' "
        "ORDER BY map_name LIMIT 5)), '') ELSE '' END map_names FROM entities"
        + where
        + " ORDER BY CASE WHEN name = '' THEN 1 ELSE 0 END, name COLLATE NOCASE, entity_id LIMIT ?"
    )
    with game_database() as db:
        rows = db.execute(sql, (*values, limit)).fetchall()
    return [{**dict(row), "typeLabel": GAME_ENTITY_TYPES[row["entity_type"]][0]} for row in rows]


def game_detail(entity_type, entity_id):
    if entity_type not in GAME_ENTITY_TYPES or not 1 <= len(entity_id) <= 80:
        raise ValueError("Entidade inválida")
    label, detail_table = GAME_ENTITY_TYPES[entity_type]
    with game_database() as db:
        entity = db.execute(
            "SELECT entity_type, entity_id, name, description, source_table FROM entities WHERE entity_type = ? AND entity_id = ?",
            (entity_type, entity_id),
        ).fetchone()
        if not entity:
            return None
        detail = db.execute(f"SELECT * FROM {detail_table} WHERE id = ? LIMIT 1", (entity_id,)).fetchone()
        related = {}
        if entity_type == "npc":
            related["spawns"] = [dict(row) for row in db.execute(
                "SELECT map_info_id, map_name, map_index, region_index, position, spawn_value "
                "FROM spawns WHERE npc_id = ? LIMIT 80", (entity_id,)
            )]
            related["lootCandidates"] = [dict(row) for row in db.execute(
                "SELECT reward_item_id, reward_item_name, reward_entity_type, min_value, enchant_level, subgroup_index "
                "FROM loot_candidates WHERE npc_id = ? LIMIT 100", (entity_id,)
            )]
        elif entity_type == "item":
            related["lootSources"] = [dict(row) for row in db.execute(
                "SELECT npc_id, npc_name, npc_level, min_value, enchant_level, subgroup_index "
                "FROM loot_candidates WHERE reward_item_id = ? LIMIT 100", (entity_id,)
            )]
            related["collections"] = [dict(row) for row in db.execute(
                "SELECT collection_id, required_quantity, required_enchant_level FROM collection_requirements "
                "WHERE accepted_item_id = ? LIMIT 100", (entity_id,)
            )]
        elif entity_type == "map" and detail:
            related["spawns"] = [dict(row) for row in db.execute(
                "SELECT npc_id, npc_name, npc_level, npc_grade, position, spawn_value FROM spawns "
                "WHERE map_index = ? AND region_index = ? LIMIT 100", (detail["map_index"], detail["region_index"])
            )]
        elif entity_type == "collection":
            related["requirements"] = [dict(row) for row in db.execute(
                "SELECT slot, item_group, required_quantity, required_enchant_level, accepted_item_id, "
                "accepted_item_name, accepted_item_grade, accepted_item_tier FROM collection_requirements "
                "WHERE collection_id = ? LIMIT 100", (entity_id,)
            )]
    return {"entity": {**dict(entity), "typeLabel": label}, "details": dict(detail) if detail else {}, "related": related}


def market_key(value):
    return re.sub(r"[^a-z0-9]", "", normalize_search(value))


def canonical_market_category(value):
    aliases = {"weapon": "Arma", "armor": "Armadura", "accessories": "Acessório", "accessory": "Acessório",
               "expansion": "Expansão", "materialdecraft": "Material de Craft", "craftmaterial": "Material de Craft",
               "miscellaneous": "Outros"}
    lookup = {market_key(name): name for name in MARKET_TAXONOMY} | aliases
    return lookup.get(market_key(value))


def canonical_market_subcategory(value, category):
    aliases = {
        "protetorcervical": "Neck Guard", "protetorsuperior": "Chest Guard", "protetorinferior": "Lower Guard",
        "protetordebraco": "Arm Guards", "protetordeperna": "Leg Guards", "brincos": "Ear Cuffs",
        "colar": "Necklace", "bracelete": "Bangles", "anel": "Ring", "diadema": "Circlet",
        "materialdeaprimoramento": "Powerup Materials", "materialdeaddon": "Addon Materials",
        "materialdecraft": "Crafting Materials", "colecionavelespecial": "Special Collectible", "consumivel": "Consumable",
    }
    lookup = {market_key(name): name for name in MARKET_TAXONOMY.get(category, [])} | aliases
    result = lookup.get(market_key(value))
    return result if result in MARKET_TAXONOMY.get(category, []) else None


def parse_market_integer(value, label, maximum):
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits or not 0 < int(digits) <= maximum:
        raise ValueError(f"{label} inválido")
    return int(digits)


def parse_market_number(value, label, maximum):
    raw = str(value or "").strip()
    if re.fullmatch(r"\d{1,3}(?:\.\d{3}){2,}", raw):
        raw = raw.replace(".", "")
    else:
        raw = raw.replace(",", ".")
    try:
        number = float(raw)
    except ValueError as exc:
        raise ValueError(f"{label} inválido") from exc
    if not math.isfinite(number) or not 0 < number <= maximum:
        raise ValueError(f"{label} inválido")
    return int(number) if number.is_integer() else number


def parse_market_optional_integer(value):
    value = str(value or "").strip()
    return int(value) if re.fullmatch(r"\d+", value) else None


def classify_market_item(item):
    category_code = item["raw_category"]
    subcategory_code = item["raw_subcategory"]
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
    mapping_value = item["equip_biosuit"] if category_code == 1 else item["equip_part_type"]
    if category_code in (6, 7):
        mapping_value = subcategory_code
    subcategory = mappings.get(category_code, {}).get(mapping_value)
    if not subcategory:
        subcategory = "Special Collectible" if category_code not in categories and subcategory_code == 31 else "Consumable"
    if subcategory not in MARKET_TAXONOMY.get(category, []):
        category, subcategory = "Outros", "Consumable"
    return category, subcategory


def market_item_lookup(item_ids):
    item_ids = sorted({str(value) for value in item_ids if str(value).isdigit()})
    found = {}
    with game_database() as db:
        for offset in range(0, len(item_ids), 500):
            batch = item_ids[offset:offset + 500]
            placeholders = ",".join("?" for _ in batch)
            rows = db.execute(
                "SELECT d.id, COALESCE(e.name, '') name, d.grade, d.category raw_category, "
                "d.subcategory raw_subcategory, d.equip_part_type, d.equip_biosuit, d.icon "
                "FROM item_details d LEFT JOIN entities e ON e.entity_type = 'item' AND e.entity_id = d.id "
                f"WHERE d.id IN ({placeholders})", batch,
            )
            for row in rows:
                item = dict(row)
                item["category"], item["subcategory"] = classify_market_item(item)
                found[item["id"]] = item
    return found


@lru_cache(maxsize=1)
def market_image_names():
    try:
        return {path.name for path in MARKET_IMAGE_ROOT.iterdir() if path.is_file()}
    except OSError:
        return set()


def market_image_url(image_name, item_id, icon):
    if image_name:
        if Path(image_name).name != image_name or not re.fullmatch(r"[\w .()\-]+", image_name):
            raise ValueError("imagem inválida")
        return f"/market-images/{quote(image_name, safe='')}"
    icon_name = str(icon or "").rsplit(".", 1)[-1]
    for stem in (str(item_id or ""), icon_name):
        if not stem:
            continue
        for extension in (".webp", ".png", ".jpg", ".jpeg"):
            candidate = f"{stem}{extension}"
            if candidate in market_image_names():
                return f"/market-images/{quote(candidate, safe='')}"
    return ""


def parse_market_csv(text):
    dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    aliases = {
        "itemId": ("itemid", "id", "itemindex"), "name": ("nome", "name", "itemname"),
        "category": ("categoria", "category"), "subcategory": ("subcategoria", "subcategory"),
        "refinement": ("refino", "refinement", "refine", "enchant", "enhance"),
        "price": ("preco", "price", "valor", "priceperunit"),
        "quantity": ("quantidade", "quantity", "qtd", "qty"), "seller": ("vendedor", "seller"),
        "image": ("imagem", "image", "imagefile", "arquivoimagem"),
        "listingId": ("ofertaid", "listingid", "anuncioid", "idhex"),
        "salesTotal": ("salestotal",), "grade": ("grade",), "quality": ("quality",),
        "highestPrice": ("highestprice", "maxprice", "maiorpreco"),
        "start": ("start",), "expire": ("expire",),
    }
    headers = {market_key(name): name for name in (reader.fieldnames or [])}
    columns = {key: next((headers[name] for name in names if name in headers), None) for key, names in aliases.items()}
    if not columns["price"] or not columns["quantity"] or not (columns["name"] or columns["itemId"]):
        raise ValueError("Cabeçalhos obrigatórios: Name ou ItemIndex, PricePerUnit e Qty")
    source_rows = list(reader)
    get_value = lambda row, key: str(row.get(columns[key], "") or "").strip() if columns[key] else ""
    item_lookup = market_item_lookup(get_value(row, "itemId") for row in source_rows)
    listings = []
    for line, row in enumerate(source_rows, 2):
        get = lambda key: get_value(row, key)
        item_id = get("itemId")
        item = item_lookup.get(item_id, {})
        name = item.get("name") or re.sub(r"^\+\d+\s+", "", get("name")).strip()
        category = canonical_market_category(get("category")) or item.get("category")
        subcategory = canonical_market_subcategory(get("subcategory"), category) or item.get("subcategory")
        if not 1 <= len(name) <= 160 or not category or not subcategory:
            raise ValueError(f"Linha {line}: ItemIndex não encontrado ou categoria inválida")
        raw_refinement = get("refinement")
        match = re.search(r"\d+", raw_refinement)
        refinement = f"+{int(match.group())}" if match and int(match.group()) else "Sem refino"
        try:
            image = market_image_url(get("image"), item_id, item.get("icon"))
        except ValueError as exc:
            raise ValueError(f"Linha {line}: {exc}") from exc
        price = parse_market_number(get("price"), f"Linha {line}: preço", 10**15)
        highest_price = parse_market_number(get("highestPrice"), f"Linha {line}: maior preço", 10**15) if get("highestPrice") else price
        if highest_price < price:
            raise ValueError(f"Linha {line}: maior preço abaixo do menor preço")
        quantity = parse_market_integer(get("quantity"), f"Linha {line}: quantidade", 10**7)
        sales_total = parse_market_optional_integer(get("salesTotal"))
        listings.append({
            "listingId": get("listingId") or str(line - 1), "itemId": item_id, "name": name,
            "category": category, "subcategory": subcategory, "refinement": refinement,
            "price": price, "highestPrice": highest_price, "quantity": quantity, "salesTotal": sales_total or price * quantity,
            "seller": get("seller")[:120], "image": image,
            "grade": parse_market_optional_integer(get("grade")) or item.get("grade"),
            "quality": parse_market_optional_integer(get("quality")),
            "start": parse_market_optional_integer(get("start")),
            "expire": parse_market_optional_integer(get("expire")),
        })
        if len(listings) > 100_000:
            raise ValueError("CSV excede 100.000 ofertas")
    return listings


def read_market_csv(path):
    if not path.is_file():
        raise ValueError("CSV do Mercado não encontrado")
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("CSV excede 20 MB")
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    return raw, parse_market_csv(text)


def normalize_market_timestamp(value, fallback):
    try:
        captured = datetime.fromisoformat(value.replace("Z", "+00:00")) if value else fallback
    except ValueError as exc:
        raise ValueError("Timestamp da captura inválido") from exc
    if captured.tzinfo is None:
        captured = captured.replace(tzinfo=timezone.utc)
    return captured.astimezone(timezone.utc).isoformat()


def import_market_csv(path, captured_at=None, source_id=None):
    raw, listings = read_market_csv(path)
    source_id = str(source_id or hashlib.sha256(raw).hexdigest()).strip()
    if not 1 <= len(source_id) <= 128:
        raise ValueError("Identificador da captura inválido")
    captured_at = normalize_market_timestamp(
        captured_at, datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    )
    grouped = {}
    for listing in listings:
        match = re.search(r"\d+", listing["refinement"])
        refinement = int(match.group()) if match else 0
        key = (listing["itemId"], refinement)
        if key not in grouped:
            grouped[key] = {**listing, "refinementValue": refinement}
            continue
        current = grouped[key]
        current["price"] = min(current["price"], listing["price"])
        current["highestPrice"] = max(current["highestPrice"], listing["highestPrice"])
        current["quantity"] += listing["quantity"]

    with database() as db:
        previous = db.execute("SELECT id FROM market_snapshots WHERE source_id = ?", (source_id,)).fetchone()
        if previous:
            return {"snapshotId": previous[0], "rows": len(grouped), "inserted": False}
        cursor = db.execute(
            "INSERT INTO market_snapshots (captured_at, source_id, row_count, total_registered) VALUES (?, ?, ?, ?)",
            (captured_at, source_id, len(grouped), sum(row["quantity"] for row in grouped.values())),
        )
        snapshot_id = cursor.lastrowid
        db.executemany(
            "INSERT INTO market_prices (snapshot_id, item_id, item_name, category, subcategory, refinement, "
            "lowest_price, highest_price, registered_items, grade) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ((snapshot_id, item_id, row["name"], row["category"], row["subcategory"], refinement,
              row["price"], row["highestPrice"], row["quantity"], row["grade"])
             for (item_id, refinement), row in grouped.items()),
        )
    return {"snapshotId": snapshot_id, "rows": len(grouped), "inserted": True, "capturedAt": captured_at}


def market_data():
    payload = {"loaded": False, "updatedAt": None, "listings": [], "taxonomy": MARKET_TAXONOMY,
               "requiredColumns": ["Name", "ItemIndex", "Enhance", "PricePerUnit", "Qty", "HighestPrice"]}
    with database() as db:
        snapshot = db.execute(
            "SELECT id, captured_at, row_count, total_registered FROM market_snapshots "
            "ORDER BY captured_at DESC, id DESC LIMIT 1"
        ).fetchone()
        snapshot_count = db.execute("SELECT COUNT(*) FROM market_snapshots").fetchone()[0]
        if snapshot:
            rows = db.execute(
                "WITH ranked AS (SELECT p.*, s.captured_at, "
                "ROW_NUMBER() OVER (PARTITION BY p.item_id, p.refinement ORDER BY s.captured_at DESC, s.id DESC) position, "
                "COUNT(*) OVER (PARTITION BY p.item_id, p.refinement) capture_count "
                "FROM market_prices p JOIN market_snapshots s ON s.id = p.snapshot_id) "
                "SELECT item_id, item_name, category, subcategory, refinement, lowest_price, highest_price, "
                "registered_items, grade, captured_at, capture_count FROM ranked WHERE position = 1 "
                "ORDER BY item_id, refinement"
            ).fetchall()
            item_lookup = market_item_lookup(row["item_id"] for row in rows)
            listings = []
            for row in rows:
                item = item_lookup.get(row["item_id"], {})
                listings.append({
                    "listingId": f"{snapshot['id']}:{row['item_id']}:{row['refinement']}",
                    "itemId": row["item_id"], "name": row["item_name"], "category": row["category"],
                    "subcategory": row["subcategory"], "refinement": f"+{row['refinement']}" if row["refinement"] else "Sem refino",
                    "price": row["lowest_price"], "highestPrice": row["highest_price"],
                    "quantity": row["registered_items"], "aggregate": True,
                    "seller": "", "image": market_image_url("", row["item_id"], item.get("icon")),
                    "grade": row["grade"], "quality": None, "start": None, "expire": None,
                    "capturedAt": row["captured_at"], "captureCount": row["capture_count"],
                    "iconAsset": item.get("icon", ""),
                })
            payload.update({"loaded": True, "updatedAt": snapshot["captured_at"], "listings": listings,
                            "snapshotCount": snapshot_count, "totalRegistered": snapshot["total_registered"]})
            return payload
    if not MARKET_CSV_PATH.is_file():
        return payload
    _, listings = read_market_csv(MARKET_CSV_PATH)
    payload.update({"loaded": True, "updatedAt": datetime.fromtimestamp(MARKET_CSV_PATH.stat().st_mtime, timezone.utc).isoformat(),
                    "listings": listings, "snapshotCount": 0})
    return payload


def market_history(item_id):
    if not re.fullmatch(r"\d{1,12}", item_id):
        raise ValueError("ItemIndex inválido")
    with database() as db:
        rows = db.execute(
            "SELECT s.captured_at, p.item_name, p.refinement, p.lowest_price, p.highest_price, "
            "p.registered_items FROM market_prices p JOIN market_snapshots s ON s.id = p.snapshot_id "
            "WHERE p.item_id = ? ORDER BY s.captured_at DESC, s.id DESC, p.refinement LIMIT 500",
            (item_id,),
        ).fetchall()
    if not rows:
        return None
    item = market_item_lookup([item_id]).get(item_id, {})
    return {
        "itemId": item_id,
        "name": rows[0]["item_name"],
        "image": market_image_url("", item_id, item.get("icon")),
        "iconAsset": item.get("icon", ""),
        "captures": [{
            "capturedAt": row["captured_at"],
            "refinement": f"+{row['refinement']}" if row["refinement"] else "Sem refino",
            "lowestPrice": row["lowest_price"],
            "highestPrice": row["highest_price"],
            "quantity": row["registered_items"],
        } for row in rows],
    }


def craft_summary():
    with game_database() as db:
        meta = dict(db.execute("SELECT key, value FROM meta"))
        rows = db.execute("SELECT category, subcategory, COUNT(*) count FROM craft_recipes GROUP BY category, subcategory ORDER BY category, subcategory")
        categories = {}
        for row in rows:
            categories.setdefault(row["category"], {})[row["subcategory"]] = row["count"]
    return {"version": meta.get("source_version", "—"), "recipes": int(meta.get("count_craft_recipes", 0)), "categories": categories}


def craft_search(query, category, subcategory, limit=60):
    if category and category not in MARKET_TAXONOMY:
        raise ValueError("Categoria inválida")
    if subcategory and subcategory not in MARKET_TAXONOMY.get(category, []):
        raise ValueError("Subcategoria inválida")
    clauses, values = [], []
    if query := normalize_search(query)[:80]:
        clauses.append("search_text LIKE ?")
        values.append(f"%{query}%")
    if category:
        clauses.append("category = ?")
        values.append(category)
    if subcategory:
        clauses.append("subcategory = ?")
        values.append(subcategory)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    limit = max(1, min(int(limit), 100))
    with game_database() as db:
        total = db.execute("SELECT COUNT(*) FROM craft_recipes" + where, values).fetchone()[0]
        rows = db.execute(
            "SELECT recipe_key, recipe_id, output_item_id, output_name, description, category, subcategory, grade, tier, use_level, "
            "cost_type, cost_value, output_enchant, normal_probability, better_probability, huge_probability, fail_probability "
            "FROM craft_recipes" + where + " ORDER BY output_name COLLATE NOCASE, recipe_id LIMIT ?", (*values, limit)
        ).fetchall()
    return {"results": [dict(row) for row in rows], "count": len(rows), "total": total}


def craft_detail(recipe_key):
    try:
        recipe_key = int(recipe_key)
    except (TypeError, ValueError) as exc:
        raise ValueError("Receita inválida") from exc
    with game_database() as db:
        recipe = db.execute("SELECT * FROM craft_recipes WHERE recipe_key = ?", (recipe_key,)).fetchone()
        if not recipe:
            return None
        results = [dict(row) for row in db.execute(
            "SELECT result_type, item_id, item_name, enchant_level, probability, quantity, grade, tier FROM craft_results WHERE recipe_key = ? ORDER BY CASE result_type WHEN 'normal' THEN 1 WHEN 'better' THEN 2 ELSE 3 END",
            (recipe_key,),
        )]
        material_rows = db.execute(
            "SELECT slot, item_group, quantity, enchant_level, accepted_item_id, accepted_item_name, accepted_item_grade, accepted_item_tier FROM craft_materials WHERE recipe_key = ? ORDER BY slot, accepted_item_name",
            (recipe_key,),
        )
        materials = []
        for row in material_rows:
            if not materials or materials[-1]["slot"] != row["slot"]:
                materials.append({"slot": row["slot"], "itemGroup": row["item_group"], "quantity": row["quantity"],
                                  "enchantLevel": row["enchant_level"], "acceptedItems": []})
            materials[-1]["acceptedItems"].append({"itemId": row["accepted_item_id"], "name": row["accepted_item_name"],
                                                    "grade": row["accepted_item_grade"], "tier": row["accepted_item_tier"]})
    return {"recipe": dict(recipe), "results": results, "materials": materials}


def parse_display_number(text, decimal=False):
    cleaned = text.upper().strip().replace("O", "0").replace("I", "1").replace("L", "1")
    if decimal and cleaned.startswith((".", ",")):
        cleaned = "0" + cleaned
    match = re.search(r"(\d[\d.,]*)\s*([KMB]?)", cleaned)
    if not match:
        return None
    number, suffix = match.groups()
    if decimal and not {".", ","}.intersection(number) and len(number) == 4 and number.startswith("0"):
        number = f"0.{number[1:]}"
    if suffix and not {".", ","}.intersection(number) and len(number) >= 4:
        number = f"{number[:-1]}.{number[-1]}"
    if decimal or suffix:
        number = number.replace(".", "").replace(",", ".") if "," in number else number
    else:
        number = number.replace(".", "").replace(",", "")
    value = float(number) * {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[suffix]
    return round(value, 3) if decimal else round(value)


def parse_faction_points(text):
    cleaned = text.upper().replace(" ", "")
    cleaned = re.sub(r"^B(?=[.,]?\d)", "6", cleaned)
    cleaned = re.sub(r"(?<=\d)B(?=M)", ",6", cleaned)
    if not re.fullmatch(r"\d+(?:[.,]\d+)?[KMB]?", cleaned):
        return None
    if re.fullmatch(r"\d{2}M", cleaned):
        cleaned = f"{cleaned[0]},{cleaned[1:]}"
    if re.fullmatch(r"\d[.,]\d{2}", cleaned):
        return int(parse_display_number(cleaned, decimal=True) * 10 + .5) * 100_000
    return parse_display_number(cleaned)


def parse_elapsed_seconds(text):
    digits = re.sub(r"\D", "", text)
    if not digits:
        return None
    seconds = int(digits[-2:])
    minutes = int(digits[-4:-2] or 0)
    hours = int(digits[:-4] or 0)
    return hours * 3600 + minutes * 60 + seconds if minutes < 60 and seconds < 60 else None


def crop_by_width(image, box):
    return image.crop(tuple(round(value * image.width) for value in box))


def ocr_line(image, box, threshold=155, padding=0):
    crop = crop_by_width(image, box).resize(
        (round((box[2] - box[0]) * image.width * 4), round((box[3] - box[1]) * image.width * 4)),
        Image.Resampling.LANCZOS,
    )
    gray = ImageOps.autocontrast(ImageOps.grayscale(crop))
    prepared = gray.point(lambda value: 0 if value > threshold else 255)
    if padding:
        prepared = ImageOps.expand(prepared, border=padding, fill=255)
    source = io.BytesIO()
    prepared.save(source, format="PNG")
    result = subprocess.run(
        ["tesseract", "stdin", "stdout", "--psm", "7", "-l", "eng", "-c", "tessedit_char_whitelist=0123456789.,%KkMmBb"],
        input=source.getvalue(), capture_output=True, timeout=12, check=True,
    )
    return result.stdout.decode(errors="replace").strip()


def count_purple_items(image):
    area = crop_by_width(image, (.025, .53, .975, 1.1)).convert("RGB")
    columns, rows = 5, 3
    found = 0
    for row in range(rows):
        for column in range(columns):
            cell = area.crop((column * area.width // columns, row * area.height // rows, (column + 1) * area.width // columns, (row + 1) * area.height // rows)).resize((32, 32))
            purple = sum(1 for red, green, blue in cell.getdata() if red > 60 and blue > 60 and min(red, blue) - green > 10)
            found += purple >= 100
    return found


def analyze_image(source):
    with Image.open(source) as opened:
        image = opened.convert("RGB")
    if image.height <= image.width * 1.15:
        raw = {
            "time": ocr_line(image, (.23, .12, .82, .31)),
            "credits": ocr_line(image, (.24, .31, .72, .46), 155, 20),
            "xp": ocr_line(image, (.23, .48, .75, .66)),
        }
        return {
            "layout": "compact",
            "elapsedSeconds": parse_elapsed_seconds(raw["time"]),
            "xp": parse_display_number(raw["xp"], decimal=True),
            "credits": parse_display_number(raw["credits"]),
            "factionPoints": 0,
            "purpleItems": 0,
            "raw": raw,
        }
    if image.width < 220:
        xp_box, credits_box = (.80, .21, .99, .29), (.80, .285, .99, .365)
    elif image.width < 300:
        xp_box, credits_box = (.80, .235, .99, .315), (.77, .285, .99, .37)
    elif image.width < 500:
        xp_box, credits_box = (.80, .235, .99, .315), (.74, .275, .99, .355)
    else:
        xp_box, credits_box = (.80, .21, .99, .29), (.74, .275, .99, .355)
    faction_box = (.08, .65, .23, .76) if image.width < 500 else (.09, .64, .23, .72)
    raw = {"xp": ocr_line(image, xp_box), "credits": ocr_line(image, credits_box), "factionPoints": ocr_line(image, faction_box)}
    if parse_faction_points(raw["factionPoints"]) is None:
        faction_box = (.095, .66, .23, .715) if image.width < 500 else (.095, .635, .23, .68)
        raw["factionPoints"] = ocr_line(image, faction_box, 140 if image.width < 500 else 205, 20)
    return {
        "layout": "farm",
        "xp": parse_display_number(raw["xp"], decimal=True),
        "credits": parse_display_number(raw["credits"]),
        "factionPoints": parse_faction_points(raw["factionPoints"]),
        "purpleItems": count_purple_items(image),
        "raw": raw,
    }


def clean_mcp_result(payload):
    if not isinstance(payload, dict):
        raise ValueError("Resposta MCP inválida")

    limits = {"elapsedSeconds": 604800, "xp": 100, "credits": 10**12, "factionPoints": 10**12, "purpleItems": 100}
    result = {"layout": payload.get("layout") if payload.get("layout") in {"compact", "farm", "unknown"} else "unknown"}
    for key, limit in limits.items():
        value = payload.get(key)
        if value is None:
            result[key] = None
            continue
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Campo MCP inválido: {key}") from exc
        if isinstance(value, bool) or not 0 <= number <= limit:
            raise ValueError(f"Campo MCP inválido: {key}")
        result[key] = round(number, 3) if key == "xp" else round(number)
    if all(result[key] is None for key in ("xp", "credits", "factionPoints", "purpleItems")):
        raise ValueError("Worker MCP não reconheceu dados")
    result["source"] = str(payload.get("source") or "mcp")[:80]
    return result


def analyze_with_mcp(image, content_type):
    if not MCP_VISION_URL or not MCP_VISION_TOKEN:
        raise OSError("Worker MCP não configurado")
    request = urlrequest.Request(
        MCP_VISION_URL,
        data=image,
        method="POST",
        headers={"Content-Type": content_type, "X-RFNext-Vision-Token": MCP_VISION_TOKEN},
    )
    with urlrequest.urlopen(request, timeout=MCP_VISION_TIMEOUT) as response:
        return clean_mcp_result(json.loads(response.read(MAX_BODY)))


@contextmanager
def database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            share INTEGER NOT NULL DEFAULT 0,
            state TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS market_snapshots (
            id INTEGER PRIMARY KEY,
            captured_at TEXT NOT NULL,
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source_id TEXT NOT NULL UNIQUE,
            row_count INTEGER NOT NULL,
            total_registered INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS market_prices (
            snapshot_id INTEGER NOT NULL REFERENCES market_snapshots(id) ON DELETE CASCADE,
            item_id TEXT NOT NULL,
            item_name TEXT NOT NULL,
            category TEXT NOT NULL,
            subcategory TEXT NOT NULL,
            refinement INTEGER NOT NULL,
            lowest_price REAL NOT NULL,
            highest_price REAL NOT NULL,
            registered_items INTEGER NOT NULL,
            grade INTEGER,
            PRIMARY KEY (snapshot_id, item_id, refinement)
        );
        CREATE INDEX IF NOT EXISTS market_prices_item_history
            ON market_prices (item_id, refinement, snapshot_id);
    """)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def clean_locations(values):
    clean = []
    seen = set()
    for location in values:
        if not isinstance(location, str) or not 1 <= len(location.strip()) <= 80:
            raise ValueError("Localização inválida")
        name = location.strip()
        key = re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", name.casefold()).encode("ascii", "ignore").decode())
        if key and key not in seen:
            clean.append(name)
            seen.add(key)
    return clean


def clean_state(value):
    if not isinstance(value, dict):
        raise ValueError("Estado inválido")
    history = value.get("history", [])
    characters = value.get("characters", [])
    locations = value.get("locations", [])
    spots = value.get("spots")
    mob_database = value.get("mobDatabase", [])
    if not isinstance(history, list) or not isinstance(characters, list) or not isinstance(locations, list) or (spots is not None and not isinstance(spots, list)) or not isinstance(mob_database, list):
        raise ValueError("Estado inválido")
    if len(history) > 10_000 or len(characters) > 200 or len(locations) > 500 or len(spots or []) > 500 or len(mob_database) > 5_000:
        raise ValueError("Limite de dados excedido")
    clean_mobs = []
    for item in mob_database:
        if not isinstance(item, dict):
            raise ValueError("Mob inválido")
        location = str(item.get("location", "")).strip()
        mob = str(item.get("mob", "")).strip()
        try:
            level = int(item.get("level", 0))
            xp = float(item.get("xpPerMob", 0))
            credits = float(item.get("creditsPerMob", 0))
            faction = float(item.get("factionPointsPerMob", 0))
        except (TypeError, ValueError):
            raise ValueError("Mob inválido")
        if not all(map(math.isfinite, (xp, credits, faction))) or not 1 <= len(location) <= 80 or not 1 <= len(mob) <= 80 or level < 1 or xp <= 0 or credits < 0 or faction < 0 or not (credits or faction):
            raise ValueError("Mob inválido")
        clean_mobs.append({"id": item.get("id"), "location": location, "mob": mob, "level": level, "xpPerMob": xp, "creditsPerMob": credits, "factionPointsPerMob": faction})
    return {"history": history, "characters": characters, "locations": clean_locations(locations), "spots": clean_locations(spots) if spots is not None else None, "mobDatabase": clean_mobs}


class Handler(SimpleHTTPRequestHandler):
    def identity(self):
        username = normalize_user(self.headers.get("X-Karvalho-User", ""))
        if username:
            return username
        email = self.headers.get("Cf-Access-Authenticated-User-Email", "").strip().lower()
        host = self.headers.get("Host", "").split(":", 1)[0].lower()
        if email:
            return email[:254]
        if host in {"localhost", "127.0.0.1", "rfnext"} or host.endswith(".localhost"):
            return LOCAL_USER
        return None

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def require_identity(self):
        user = self.identity()
        if not user:
            self.send_json(401, {"error": "Entre pelo Cloudflare Access para usar o aplicativo."})
        return user

    def read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0 or length > MAX_BODY:
            raise ValueError("Conteúdo inválido")
        return json.loads(self.rfile.read(length))

    def send_market_image(self, encoded_name):
        name = unquote(encoded_name)
        if Path(name).name != name or not re.fullmatch(r"[\w .()\-]+\.(?:png|jpe?g|webp|gif|avif)", name, re.IGNORECASE):
            return self.send_json(404, {"error": "Imagem não encontrada."})
        target = MARKET_IMAGE_ROOT / name
        if not target.is_file():
            return self.send_json(404, {"error": "Imagem não encontrada."})
        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(target.stat().st_size))
        self.send_header("Cache-Control", "private, max-age=3600")
        self.end_headers()
        with target.open("rb") as source:
            self.copyfile(source, self.wfile)

    def do_GET(self):
        request_url = urlparse(self.path)
        path = request_url.path.rstrip("/")
        if path.startswith("/market-images/"):
            if not self.require_identity():
                return
            return self.send_market_image(path.removeprefix("/market-images/"))

        if path == "/api/market":
            if not self.require_identity():
                return
            try:
                return self.send_json(200, market_data())
            except (OSError, ValueError, csv.Error) as exc:
                return self.send_json(422, {"error": str(exc)})

        if path == "/api/market/history":
            if not self.require_identity():
                return
            try:
                history = market_history(parse_qs(request_url.query).get("itemId", [""])[0])
                return self.send_json(200, history) if history else self.send_json(404, {"error": "Histórico não encontrado."})
            except ValueError as exc:
                return self.send_json(400, {"error": str(exc)})
            except (OSError, sqlite3.Error):
                return self.send_json(503, {"error": "Histórico do Mercado indisponível."})

        if path.startswith("/api/craft/"):
            if not self.require_identity():
                return
            try:
                if path == "/api/craft/summary":
                    return self.send_json(200, craft_summary())
                params = parse_qs(request_url.query)
                if path == "/api/craft/search":
                    return self.send_json(200, craft_search(params.get("q", [""])[0], params.get("category", [""])[0],
                                                            params.get("subcategory", [""])[0], params.get("limit", ["60"])[0]))
                if path == "/api/craft/detail":
                    detail = craft_detail(params.get("id", [""])[0])
                    return self.send_json(200, detail) if detail else self.send_json(404, {"error": "Receita não encontrada."})
            except (ValueError, TypeError):
                return self.send_json(400, {"error": "Consulta inválida."})
            except (OSError, sqlite3.Error):
                return self.send_json(503, {"error": "Banco de craft indisponível."})
            return self.send_json(404, {"error": "Rota não encontrada."})

        if path.startswith("/api/game-data/"):
            if not self.require_identity():
                return
            try:
                if path == "/api/game-data/summary":
                    return self.send_json(200, game_summary())
                params = parse_qs(request_url.query)
                if path == "/api/game-data/search":
                    results = game_search(
                        params.get("q", [""])[0],
                        params.get("type", [""])[0],
                        params.get("limit", ["50"])[0],
                    )
                    return self.send_json(200, {"results": results, "count": len(results)})
                if path == "/api/game-data/detail":
                    detail = game_detail(params.get("type", [""])[0], params.get("id", [""])[0])
                    return self.send_json(200, detail) if detail else self.send_json(404, {"error": "Registro não encontrado."})
            except (ValueError, TypeError):
                return self.send_json(400, {"error": "Consulta inválida."})
            except (OSError, sqlite3.Error):
                return self.send_json(503, {"error": "Banco extraído indisponível."})
            return self.send_json(404, {"error": "Rota não encontrada."})

        if path == "/api/state":
            user = self.require_identity()
            if not user:
                return
            with database() as db:
                row = db.execute("SELECT share, state FROM users WHERE id = ?", (user,)).fetchone()
                if not row:
                    db.execute("INSERT INTO users(id) VALUES (?)", (user,))
                    row = (0, "{}")
            state = clean_state(json.loads(row[1] or "{}"))
            return self.send_json(200, {"user": user.split("@", 1)[0], "share": bool(row[0]), **state})

        if path == "/api/history/general":
            if not self.require_identity():
                return
            records = []
            with database() as db:
                rows = db.execute("SELECT id, state FROM users WHERE share = 1").fetchall()
            for user, raw_state in rows:
                try:
                    state = clean_state(json.loads(raw_state or "{}"))
                except (ValueError, json.JSONDecodeError):
                    continue
                owner = user.split("@", 1)[0]
                records.extend({**item, "owner": owner} for item in state["history"] if isinstance(item, dict))
            records.sort(key=lambda item: item.get("createdAt") or item.get("id") or 0, reverse=True)
            return self.send_json(200, {"history": records})

        if path.startswith("/api/"):
            return self.send_json(404, {"error": "Rota não encontrada."})
        self.path = path if path in {"/karvalho-logo.png", "/market-template.csv"} else "/index.html"
        return super().do_GET()

    def do_PUT(self):
        if urlparse(self.path).path.rstrip("/") != "/api/state":
            return self.send_json(404, {"error": "Rota não encontrada."})
        user = self.require_identity()
        if not user:
            return
        try:
            payload = self.read_json()
            state = clean_state(payload)
            share = 1 if payload.get("share") is True else 0
        except (ValueError, json.JSONDecodeError):
            return self.send_json(400, {"error": "Dados inválidos."})
        with database() as db:
            db.execute(
                "INSERT INTO users(id, share, state) VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET share=excluded.share, state=excluded.state",
                (user, share, json.dumps(state, ensure_ascii=False, separators=(",", ":"))),
            )
        return self.send_json(200, {"ok": True})

    def do_POST(self):
        if urlparse(self.path).path.rstrip("/") != "/api/ocr":
            return self.send_json(404, {"error": "Rota não encontrada."})
        if not self.require_identity():
            return
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0]
        length = int(self.headers.get("Content-Length", 0))
        if content_type not in {"image/png", "image/jpeg", "image/webp"} or length <= 0 or length > MAX_IMAGE:
            return self.send_json(400, {"error": "Envie uma imagem PNG, JPG ou WebP de até 12 MB."})
        image = self.rfile.read(length)
        try:
            result = analyze_with_mcp(image, content_type)
        except (ValueError, OSError, TimeoutError, urlerror.URLError, json.JSONDecodeError):
            try:
                result = analyze_image(io.BytesIO(image))
                result["source"] = "tesseract"
            except (UnidentifiedImageError, OSError, subprocess.SubprocessError):
                return self.send_json(422, {"error": "Não foi possível reconhecer esta captura."})
        return self.send_json(200, result)

    def log_message(self, message, *args):
        print(f"{self.address_string()} - {message % args}")


if __name__ == "__main__":
    if "--import-market" in sys.argv:
        def option(name):
            return sys.argv[sys.argv.index(name) + 1] if name in sys.argv and sys.argv.index(name) + 1 < len(sys.argv) else None
        source = option("--import-market")
        if not source:
            raise SystemExit("Informe o CSV após --import-market")
        print(json.dumps(import_market_csv(Path(source), option("--captured-at"), option("--source-id")), ensure_ascii=False))
        raise SystemExit
    if "--self-test" in sys.argv:
        assert parse_display_number("0,028%", decimal=True) == .028
        assert parse_display_number("0772%", decimal=True) == .772
        assert parse_display_number("17.374") == 17_374
        assert parse_display_number("156,7K") == 156_700
        assert parse_display_number("1567K") == 156_700
        assert parse_faction_points("3BM") == 3_600_000
        assert parse_faction_points("3,55") == 3_600_000
        assert parse_faction_points("B9M") == 6_900_000
        assert parse_faction_points("B,8M") == 6_800_000
        assert parse_faction_points("75m.1") is None
        assert parse_elapsed_seconds("00:00:10") == 10
        assert parse_elapsed_seconds("010203") == 3723
        assert parse_market_number("7.857", "teste", 10**15) == 7.857
        assert parse_market_number("1.250.000", "teste", 10**15) == 1_250_000
        assert clean_mcp_result({"layout": "compact", "elapsedSeconds": 10, "xp": .002, "credits": 1449, "factionPoints": 0, "purpleItems": 0})["credits"] == 1449
        assert clean_state({"history": [], "characters": [], "locations": ["BG 2", "bg-2", "Ruínas"]})["locations"] == ["BG 2", "Ruínas"]
        assert clean_state({"history": [], "characters": [], "locations": [], "spots": ["BG 2", "bg-2"]})["spots"] == ["BG 2"]
        assert clean_state({"history": [], "characters": [], "locations": [], "mobDatabase": [{"id": 1, "location": "BG 2", "mob": "Gunner", "level": 70, "xpPerMob": 11054, "creditsPerMob": 120, "factionPointsPerMob": 900}]})["mobDatabase"][0]["xpPerMob"] == 11054
        assert normalize_search("Habilidade Épica") == "habilidade epica"
        market_sample = parse_market_csv("nome;categoria;subcategoria;refino;preco;maiorpreco;quantidade\nMachado de Palaccia;Arma;Dreadnought;+7;1.250.000;1.500.000;3\n")
        assert market_sample[0]["price"] == 1_250_000 and market_sample[0]["highestPrice"] == 1_500_000
        original_db_path = DB_PATH
        with tempfile.TemporaryDirectory() as temporary:
            DB_PATH = Path(temporary) / "test.db"
            market_path = Path(temporary) / "market.csv"
            market_path.write_text("Name,ItemIndex,Category,Subcategory,Enhance,PricePerUnit,HighestPrice,Qty\nMachado,1000150,Arma,Dreadnought,7,100,200,3\n", encoding="utf-8")
            imported = import_market_csv(market_path, "2026-07-21T18:00:00-03:00", "self-test")
            duplicate = import_market_csv(market_path, "2026-07-21T18:00:00-03:00", "self-test")
            with database() as db:
                stored = db.execute("SELECT lowest_price, highest_price, registered_items FROM market_prices").fetchone()
            assert imported["inserted"] and not duplicate["inserted"]
            assert tuple(stored) == (100, 200, 3)
            history_sample = market_history("1000150")
            assert history_sample["captures"][0]["lowestPrice"] == 100
        DB_PATH = original_db_path
        if GAME_DB_PATH.is_file():
            assert game_summary()["counts"]["item"] > 8_000
            assert game_search("", "npc", 2)[0]["entity_type"] == "npc"
            assert "Provas Arcanas (Fácil)" in game_search("5051211", "npc", 1)[0]["map_names"]
            assert craft_summary()["recipes"] > 1_000
            assert craft_search("Rifle", "Arma", "Punisher", 2)["results"]
        sample = Image.new("RGB", (500, 500), (30, 30, 30))
        sample.paste((140, 20, 180), (30, 285, 70, 325))
        assert count_purple_items(sample) == 1
        print("OCR parser OK")
        raise SystemExit
    with database():
        pass
    ThreadingHTTPServer(("0.0.0.0", 80), Handler).serve_forever()
