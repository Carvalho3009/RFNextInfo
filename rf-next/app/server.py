import csv
import copy
import hashlib
import io
import json
import math
import mimetypes
import os
import re
import secrets
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import threading
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from http.cookies import CookieError, SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import parse_qs, quote, unquote, urlparse

from PIL import Image, ImageOps, UnidentifiedImageError


mimetypes.add_type("image/webp", ".webp")
ROOT = Path(__file__).parent
DB_PATH = Path(os.getenv("RFNEXT_DB", "/data/rfnext.db"))
GAME_DB_PATH = Path(os.getenv("RFNEXT_GAME_DB", ROOT / "rfnext-game-data.sqlite"))
COLLECTION_BONUS_CSV_PATH = Path(os.getenv("RFNEXT_COLLECTION_BONUSES", ROOT / "collection-bonuses.csv"))
MEMORY_CHIP_JSON_PATH = Path(os.getenv("RFNEXT_MEMORY_CHIPS", ROOT / "memory-chips.json"))
CHARACTER_LOADOUT_JSON_PATH = Path(os.getenv("RFNEXT_CHARACTER_LOADOUT", ROOT / "character-loadout.json"))
GAME_NAMES_EN_PATH = Path(os.getenv("RFNEXT_GAME_NAMES_EN", ROOT / "game-names-en.json"))
MARKET_CSV_PATH = Path(os.getenv("RFNEXT_MARKET_CSV", "/data/market.csv"))
MARKET_IMAGE_ROOT = Path(os.getenv("RFNEXT_MARKET_IMAGE_ROOT", "/data/market-images"))
GAME_ICON_ROOT = Path(os.getenv("RFNEXT_GAME_ICON_ROOT", ROOT / "game-icons"))
LOCAL_USER = os.getenv("RFNEXT_LOCAL_USER", "local")
ADMIN_USERS_RAW = os.getenv("RFNEXT_ADMIN_USERS", "")
ACCOUNT_SWITCH_URL = os.getenv(
    "RFNEXT_ACCOUNT_SWITCH_URL",
    "https://auth.karvalho.dev.br/outpost.goauthentik.io/sign_out",
)
ADMIN_PROFILE_COOKIE = "rfnext_admin_profile"
MAX_BODY = 5 * 1024 * 1024
MAX_IMAGE = 12 * 1024 * 1024
MCP_VISION_URL = os.getenv("MCP_VISION_URL", "")
MCP_VISION_TOKEN = os.getenv("MCP_VISION_TOKEN", "")
MCP_VISION_TIMEOUT = int(os.getenv("MCP_VISION_TIMEOUT", "75"))
LICENSE_INTROSPECT_URL = os.getenv("RFNEXT_LICENSE_INTROSPECT_URL", "")
LICENSE_INTROSPECT_TIMEOUT = int(os.getenv("RFNEXT_LICENSE_INTROSPECT_TIMEOUT", "5"))
DISCORD_BRIDGE_SECRET = os.getenv("RFNEXT_DISCORD_BRIDGE_SECRET", "")
USERNAME = re.compile(r"[a-z0-9][a-z0-9_.-]{2,31}")
CHARACTER_SHARE_FIELDS = frozenset({"className", "level", "cp", "codex"})
HISTORY_COLUMN_KEYS = frozenset({
    "createdAt", "subsessionName", "startTime", "endTime", "character", "characterClass", "rover",
    "characterLevel", "characterCp", "minutes", "mobs",
    "mauMinutes", "launcherMinutes", "expPotionQuantity", "location", "mob", "mobLevel", "loot",
    "items", "diamonds", "estimatedMobs", "grossXp", "grossXpHour", "xp", "credits",
    "factionPoints", "purpleItems", "xpHour", "creditsHour", "factionPointsHour",
    "rarity1", "rarity2", "rarity3", "rarity4", "rarity5", "rarity6",
})
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

EQUIPMENT_SLOT_TYPES = {
    "weapon-armor": frozenset({1, 2, 3, 4, 5, 6}),
    "accessory": frozenset({7, 8, 9, 10}),
    "artifact": frozenset({11, 12, 13, 14}),
    "expansion": frozenset({15, 17, 18}),
}
EQUIPMENT_GRADES = frozenset({"C", "UC", "R", "E", "L", "M"})
EQUIPMENT_SLOTS = frozenset().union(*EQUIPMENT_SLOT_TYPES.values())
CAPTURE_RECEIPT_KEYS = frozenset({"character", "collection", "memoryChip"})

ALERT_SOURCE_FIELDS = {
    "market": frozenset({"price", "highestPrice", "quantity", "priceChangePct", "stockChangePct", "opportunityPct", "medianPrice", "historicalLow", "historicalHigh", "captureCount"}),
    "material": frozenset({"bestUnitCost", "sourceCount", "pricedSources", "maxYield", "totalCost", "coveredQuantity", "missingQuantity", "complete"}),
    "salvage": frozenset({"sourcePrice", "sourceQuantity", "knownValue", "missingPrices", "difference", "roiPct", "complete", "profitable"}),
    "craft": frozenset({"materialMarketCost", "pricedMaterials", "materialCount", "complete", "productMarketPrice", "savings", "savingsPct"}),
    "personal-craft": frozenset({"fullPurchaseCost", "neededCost", "ownedMarketValue", "chestSavings", "productMarketValue", "craftFeesCredits", "savings", "savingsPct"}),
}
ALERT_OPERATORS = frozenset({"lt", "lte", "eq", "gte", "gt"})


@lru_cache(maxsize=1)
def game_names_en():
    try:
        value = json.loads(GAME_NAMES_EN_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def game_name_en(entity_type, entity_id):
    return str(game_names_en().get(entity_type, {}).get(str(entity_id), ""))


@lru_cache(maxsize=1)
def character_loadout_catalog():
    try:
        catalog = json.loads(CHARACTER_LOADOUT_JSON_PATH.read_text(encoding="utf-8"))
        if not isinstance(catalog, dict) or not isinstance(catalog.get("items"), dict):
            return {"items": {}}
        for item_id, item in catalog.get("items", {}).items():
            if isinstance(item, dict):
                item["nameEn"] = game_name_en("item", item_id)
        return catalog
    except (OSError, ValueError, json.JSONDecodeError):
        return {"items": {}}


def normalize_user(value):
    value = value.strip().lower()
    return value if USERNAME.fullmatch(value) else None


ADMIN_USERS = frozenset(
    user for value in ADMIN_USERS_RAW.split(",")
    if (user := normalize_user(value))
)


def is_admin_user(user):
    return user in ADMIN_USERS


def normalize_search(value):
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    return re.sub(r"\s+", " ", text.encode("ascii", "ignore").decode()).strip()


def english_entity_keys(search, domains):
    return [
        (domain, entity_id)
        for domain in domains
        for entity_id, name in game_names_en().get(domain, {}).items()
        if search in normalize_search(name)
    ][:500]


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
            "taxonomy": MARKET_TAXONOMY,
        }


def format_codex_bonus(stat_enum, raw_value):
    value = float(raw_value)
    displayed = value / 100 if "RATE" in stat_enum else value
    return f"+{displayed:g}{'%' if 'RATE' in stat_enum else ''}"


CODEX_STAT_NAMES = {
    "STAT_MAXFPRATE": "Aumento de FP Máx.",
    "STAT_ITEMDROPRATEINCRATE": "Aumento da Chance de Drop de Item",
}


@lru_cache(maxsize=1)
def memory_chip_data():
    payload = json.loads(MEMORY_CHIP_JSON_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("chips"), list):
        raise ValueError("Catálogo de Memory Chips inválido.")
    for chip in payload["chips"]:
        chip["nameEn"] = game_name_en("collection", chip.get("id"))
        for fragment in chip.get("fragments", []):
            fragment["nameEn"] = game_name_en("item", fragment.get("itemId"))
    return payload


@lru_cache(maxsize=1)
def codex_catalog_data():
    bonuses = {}
    with COLLECTION_BONUS_CSV_PATH.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            bonuses.setdefault(row["CollectionIndex"], []).append({
                "kind": row["RewardKind"],
                "requiredSlots": int(row["RequiredSlots"]),
                "statType": int(row["StatType"]),
                "statEnum": row["StatEnum"],
                "name": CODEX_STAT_NAMES.get(row["StatEnum"], row["StatNamePTBR"]),
                "rawValue": float(row["StatValue"]),
                "value": format_codex_bonus(row["StatEnum"], row["StatValue"]),
            })
    with game_database() as db:
        meta = dict(db.execute("SELECT key, value FROM meta"))
        change_column = (
            ", (SELECT change_type FROM content_changes c WHERE c.domain='collection' "
            "AND c.entity_id=e.entity_id) change_type"
        ) if game_has_content_changes() else ", NULL change_type"
        rows = db.execute(
            "SELECT e.entity_id, e.name, d.collection_type, d.periodic"
            f"{change_column} "
            "FROM entities e JOIN collection_details d ON d.id = e.entity_id "
            "WHERE e.entity_type = 'collection' ORDER BY CAST(e.entity_id AS INTEGER)"
        )
        collections = {
            row["entity_id"]: {
                "id": row["entity_id"], "name": row["name"], "type": row["collection_type"],
                "nameEn": game_name_en("collection", row["entity_id"]),
                "periodic": bool(row["periodic"]), "requirements": [],
                "changeStatus": row["change_type"],
                "bonuses": bonuses.get(row["entity_id"], []),
            }
            for row in rows
        }
        requirements = {}
        for row in db.execute(
            "SELECT r.collection_id, r.slot, r.required_quantity, r.required_enchant_level, "
            "r.accepted_item_id, r.accepted_item_name, r.accepted_item_grade, r.accepted_item_tier, d.icon "
            "FROM collection_requirements r LEFT JOIN item_details d ON d.id = r.accepted_item_id "
            "ORDER BY CAST(collection_id AS INTEGER), slot, accepted_item_name COLLATE NOCASE"
        ):
            key = (row["collection_id"], row["slot"])
            requirement = requirements.get(key)
            if requirement is None:
                requirement = {
                    "slot": row["slot"], "quantity": row["required_quantity"],
                    "enchant": row["required_enchant_level"], "accepted": [],
                }
                requirements[key] = requirement
                collection = collections.get(row["collection_id"])
                if collection:
                    collection["requirements"].append(requirement)
            requirement["accepted"].append({
                "id": row["accepted_item_id"], "name": row["accepted_item_name"],
                "nameEn": game_name_en("item", row["accepted_item_id"]),
                "grade": row["accepted_item_grade"], "tier": row["accepted_item_tier"],
                "icon": row["icon"],
            })
        return {
            "version": meta.get("source_version", "—"),
            "collections": list(collections.values()),
            "requirementCount": len(requirements),
            "source": "RF_ItemCollection + catálogo de itens extraídos",
        }


def codex_data():
    payload = copy.deepcopy(codex_catalog_data())
    accepted_items = [
        item for collection in payload["collections"]
        for requirement in collection["requirements"] for item in requirement["accepted"]
    ]
    item_meta = market_item_lookup(item["id"] for item in accepted_items)
    prices = latest_market_price_map()
    captured = [value.get("capturedAt") for value in prices.values() if value.get("capturedAt")]
    captured_at = min(captured) if captured else None
    for collection in payload["collections"]:
        priced_requirements = []
        for requirement in collection["requirements"]:
            for item in requirement["accepted"]:
                item.update({key: item_meta.get(item["id"], {}).get(key, default)
                             for key, default in (("prime", False), ("version", "Normal"))})
                item["image"] = market_image_url("", item["id"], item.pop("icon", ""))
                market = prices.get((item["id"], requirement["enchant"]))
                if market is not None:
                    plan = market_purchase_plan(market, requirement["quantity"])
                    item["marketPrice"] = market["price"]
                    item["purchasePlan"] = plan
                    if plan["complete"]:
                        item["marketTotal"] = plan["totalCost"]
            priced = [item for item in requirement["accepted"] if "marketTotal" in item]
            if priced:
                cheapest = min(priced, key=lambda item: item["marketTotal"])
                requirement.update({
                    "marketPrice": cheapest["marketPrice"],
                    "marketTotal": cheapest["marketTotal"],
                    "pricedItemId": cheapest["id"],
                    "pricedItemName": cheapest["name"],
                    "purchasePlan": cheapest["purchasePlan"],
                })
                priced_requirements.append(requirement)
        collection["pricedRequirements"] = len(priced_requirements)
        collection["hasMarket"] = bool(priced_requirements)
        collection["allRequirementsPriced"] = len(priced_requirements) == len(collection["requirements"])
        collection["marketTotal"] = sum(requirement["marketTotal"] for requirement in priced_requirements)
    payload["marketCapturedAt"] = captured_at
    return payload


@lru_cache(maxsize=1)
def item_detail_columns():
    with game_database() as db:
        return {row["name"] for row in db.execute("PRAGMA table_info(item_details)")}


@lru_cache(maxsize=1)
def game_has_npc_exp():
    with game_database() as db:
        return bool(db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='npc_exp'"
        ).fetchone())


@lru_cache(maxsize=1)
def game_has_content_changes():
    with game_database() as db:
        return bool(db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='content_changes'"
        ).fetchone())


def equipment_search(query="", limit=50, equipment_type="", slot=None, grade="", tier=None, prime="", biosuit_type=None):
    raw = str(query or "").strip()[:80]
    search = normalize_search(raw)[:80]
    limit = max(1, min(int(limit), 100))
    equipment_type = str(equipment_type or "").strip()
    grade = str(grade or "").strip().upper()
    prime = str(prime or "").strip().lower()
    slot = int(slot) if slot is not None else None
    tier = int(tier) if tier is not None else None
    biosuit_type = int(biosuit_type) if biosuit_type is not None else None
    if equipment_type and equipment_type not in EQUIPMENT_SLOT_TYPES:
        raise ValueError("Tipo de equipamento inválido")
    if slot is not None and (not equipment_type or slot not in EQUIPMENT_SLOT_TYPES[equipment_type]):
        raise ValueError("Slot incompatível com o tipo")
    if grade and grade not in EQUIPMENT_GRADES:
        raise ValueError("Raridade inválida")
    if tier is not None and not 0 <= tier <= 8:
        raise ValueError("Tier inválido")
    if prime not in ("", "normal", "prime"):
        raise ValueError("Prime inválido")
    if biosuit_type is not None and not 1 <= biosuit_type <= 8:
        raise ValueError("Classe inválida")
    clauses, values = [], []
    if search:
        english_ids = [entity_id for _, entity_id in english_entity_keys(search, ("item",))]
        english_clause = f" OR e.item_id IN ({','.join('?' * len(english_ids))})" if english_ids else ""
        clauses.append(f"(e.search_text LIKE ? OR e.item_id = ?{english_clause})")
        values += [f"%{search}%", raw, *english_ids]
    if equipment_type and slot is None:
        placeholders = ",".join("?" for _ in EQUIPMENT_SLOT_TYPES[equipment_type])
        clauses.append(f"d.equip_part_type IN ({placeholders})")
        values += sorted(EQUIPMENT_SLOT_TYPES[equipment_type])
    if slot is not None:
        clauses.append("d.equip_part_type = ?")
        values.append(slot)
    if grade:
        clauses.append("e.grade = ?")
        values.append(grade)
    if tier is not None:
        clauses.append("e.tier = ?")
        values.append(tier)
    if prime:
        clauses.append("e.version = ?")
        values.append("Prime" if prime == "prime" else "Normal")
    if biosuit_type is not None:
        clauses.append("(d.equip_biosuit = 0 OR d.equip_biosuit = ?)")
        values.append(biosuit_type)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    rank = "CASE WHEN e.name = ? COLLATE NOCASE THEN 0 WHEN e.name LIKE ? COLLATE NOCASE THEN 1 ELSE 2 END" if search else "2"
    rank_values = [raw, f"{raw}%"] if search else []
    with game_database() as db:
        records = db.execute(
            "SELECT e.item_id,e.name,e.part,e.grade,e.tier,e.use_level,e.version,e.icon,"
            "d.equip_part_type,d.equip_biosuit "
            f"FROM equipment_compare e JOIN item_details d ON d.id=e.item_id {where} "
            f"ORDER BY {rank},e.name COLLATE NOCASE,e.item_id LIMIT ?",
            (*values, *rank_values, limit),
        ).fetchall()
    return {"results": [{
        "itemId": row["item_id"], "name": row["name"], "part": row["part"],
        "nameEn": game_name_en("item", row["item_id"]),
        "grade": row["grade"], "tier": row["tier"], "useLevel": row["use_level"],
        "version": row["version"], "slot": row["equip_part_type"],
        "biosuitType": row["equip_biosuit"],
        "image": market_image_url("", row["item_id"], row["icon"]),
    } for row in records]}


def equipment_detail(item_id):
    item_id = str(item_id or "").strip()
    if not item_id.isdigit():
        raise ValueError("Equipamento inválido")
    with game_database() as db:
        row = db.execute(
            "SELECT e.item_id,e.name,e.part,e.grade,e.tier,e.use_level,e.version,e.icon,e.stats_json,"
            "d.equip_part_type,d.equip_biosuit FROM equipment_compare e JOIN item_details d ON d.id=e.item_id "
            "WHERE e.item_id = ?", (item_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "itemId": row["item_id"], "name": row["name"], "part": row["part"],
        "nameEn": game_name_en("item", row["item_id"]),
        "grade": row["grade"], "tier": row["tier"], "useLevel": row["use_level"],
        "version": row["version"], "slot": row["equip_part_type"],
        "biosuitType": row["equip_biosuit"],
        "image": market_image_url("", row["item_id"], row["icon"]),
        "stages": ["Base", *[f"+{level}" for level in range(1, 16)],
                   "Prime", *[f"Prime +{level}" for level in range(1, 16)]],
        "stats": json.loads(row["stats_json"]),
    }


def game_search(query, entity_type, limit=50, offset=0, grade=None, tier=None,
                 use_level_min=None, use_level_max=None, category="", subcategory=""):
    if entity_type and entity_type not in GAME_ENTITY_TYPES:
        raise ValueError("Tipo inválido")
    if category and category not in MARKET_TAXONOMY:
        raise ValueError("Categoria inválida")
    if subcategory and subcategory not in MARKET_TAXONOMY.get(category, []):
        raise ValueError("Subcategoria inválida")

    item_filters = grade is not None or tier is not None or use_level_min is not None or use_level_max is not None or category or subcategory
    if item_filters:
        if entity_type and entity_type != "item":
            grade = tier = use_level_min = use_level_max = None
            category = subcategory = ""
        else:
            entity_type = "item"

    raw = str(query or "").strip()[:80]
    search = normalize_search(query)[:80]
    limit = max(1, min(int(limit), 100))
    offset = max(0, min(int(offset), 1_000_000))

    is_item = entity_type == "item"
    show_item_columns = entity_type in ("", "item")
    columns = item_detail_columns() if show_item_columns else set()
    has_tier = "tier" in columns
    has_use_level = "use_level" in columns

    clauses, values = [], []
    if entity_type:
        clauses.append("e.entity_type = ?")
        values.append(entity_type)
    if search:
        english_keys = [f"{domain}:{entity_id}" for domain, entity_id in english_entity_keys(
            search, (entity_type,) if entity_type else GAME_ENTITY_TYPES
        )]
        english_clause = f" OR (e.entity_type || ':' || e.entity_id) IN ({','.join('?' * len(english_keys))})" if english_keys else ""
        clauses.append(f"(e.search_text LIKE ? OR e.entity_id = ?{english_clause})")
        values += [f"%{search}%", raw, *english_keys]
    if is_item and grade is not None and "grade" in columns:
        clauses.append("d.grade = ?")
        values.append(grade)
    if is_item and tier is not None and has_tier:
        clauses.append("d.tier = ?")
        values.append(tier)
    if is_item and has_use_level and use_level_min is not None:
        clauses.append("d.use_level >= ?")
        values.append(use_level_min)
    if is_item and has_use_level and use_level_max is not None:
        clauses.append("d.use_level <= ?")
        values.append(use_level_max)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    join = " LEFT JOIN item_details d ON e.entity_type = 'item' AND d.id = e.entity_id" if show_item_columns else ""
    change_column = (
        ", (SELECT change_type FROM content_changes c WHERE c.domain=e.entity_type "
        "AND c.entity_id=e.entity_id) change_type"
    ) if game_has_content_changes() else ", NULL change_type"
    item_columns = (
        ", d.grade, " + ("d.tier" if has_tier else "NULL") + " tier, "
        + ("d.use_level" if has_use_level else "NULL") + " use_level, "
        "d.category raw_category, d.subcategory raw_subcategory, d.equip_part_type, d.equip_biosuit, d.icon"
    ) if show_item_columns else ""
    npc_exp_columns = (
        ", (SELECT exp_base FROM npc_exp WHERE npc_id = CAST(e.entity_id AS INTEGER)) exp_base, "
        "(SELECT confidence FROM npc_exp WHERE npc_id = CAST(e.entity_id AS INTEGER)) exp_confidence"
    ) if entity_type != "item" and game_has_npc_exp() else ""
    map_names_sql = (
        "CASE WHEN e.entity_type = 'npc' THEN COALESCE((SELECT group_concat(map_name, ' · ') FROM "
        "(SELECT DISTINCT map_name FROM spawns WHERE npc_id = e.entity_id AND map_name <> '' "
        "ORDER BY map_name LIMIT 5)), '') ELSE '' END"
    )
    if search:
        rank_sql = (
            "CASE WHEN e.name = ? COLLATE NOCASE THEN 0 WHEN e.name LIKE ? COLLATE NOCASE THEN 1 "
            "WHEN e.search_text LIKE ? THEN 2 WHEN e.entity_id = ? THEN 3 ELSE 4 END"
        )
        rank_values = [raw, f"{raw}%", f"%{search}%", raw]
    else:
        rank_sql, rank_values = "4", []

    needs_classification = bool(category or subcategory)
    with game_database() as db:
        if needs_classification:
            sql = (
                f"SELECT e.entity_type, e.entity_id, e.name, e.description, {map_names_sql} map_names"
                f"{item_columns}{npc_exp_columns}{change_column}, {rank_sql} rank_order FROM entities e{join}{where} "
                "ORDER BY rank_order, e.name COLLATE NOCASE, e.entity_id LIMIT 20000"
            )
            rows = db.execute(sql, (*rank_values, *values)).fetchall()
            page_rows, total = [], 0
            for row in rows:
                item = dict(row)
                item_category, item_subcategory = classify_market_item(item)
                if category and item_category != category:
                    continue
                if subcategory and item_subcategory != subcategory:
                    continue
                item["category"], item["subcategory"] = item_category, item_subcategory
                if offset <= total < offset + limit:
                    page_rows.append(item)
                total += 1
        else:
            total = db.execute(f"SELECT COUNT(*) FROM entities e{join}{where}", values).fetchone()[0]
            sql = (
                f"SELECT e.entity_type, e.entity_id, e.name, e.description, {map_names_sql} map_names"
                f"{item_columns}{npc_exp_columns}{change_column}, {rank_sql} rank_order FROM entities e{join}{where} "
                "ORDER BY rank_order, e.name COLLATE NOCASE, e.entity_id LIMIT ? OFFSET ?"
            )
            page_rows = [dict(row) for row in db.execute(sql, (*rank_values, *values, limit, offset)).fetchall()]
            for item in page_rows:
                if item["entity_type"] == "item":
                    item["category"], item["subcategory"] = classify_market_item(item)

    item_meta = market_item_lookup(row["entity_id"] for row in page_rows if row["entity_type"] == "item")
    results = []
    for row in page_rows:
        entry = {
            "entity_type": row["entity_type"], "entity_id": row["entity_id"], "name": row["name"],
            "nameEn": game_name_en(row["entity_type"], row["entity_id"]),
            "description": row["description"], "map_names": row["map_names"],
            "typeLabel": GAME_ENTITY_TYPES[row["entity_type"]][0],
            "changeStatus": row.get("change_type"),
        }
        if row["entity_type"] == "item":
            meta = item_meta.get(row["entity_id"], {})
            entry.update({
                "grade": row.get("grade"), "tier": row.get("tier"), "useLevel": row.get("use_level"),
                "category": row.get("category"), "subcategory": row.get("subcategory"),
                "image": market_image_url("", row["entity_id"], row.get("icon")),
                "iconAsset": row.get("icon") or "",
                "prime": meta.get("prime", False), "version": meta.get("version", "Normal"),
            })
        elif row["entity_type"] == "npc" and row.get("exp_base") is not None:
            entry["expBase"] = row["exp_base"]
            entry["expConfidence"] = row["exp_confidence"]
        results.append(entry)
    return {"results": results, "count": len(results), "total": total, "offset": offset, "limit": limit}


def game_detail(entity_type, entity_id):
    if entity_type not in GAME_ENTITY_TYPES or not 1 <= len(entity_id) <= 80:
        raise ValueError("Entidade inválida")
    label, detail_table = GAME_ENTITY_TYPES[entity_type]
    with game_database() as db:
        change_column = (
            ", (SELECT change_type FROM content_changes c WHERE c.domain=entities.entity_type "
            "AND c.entity_id=entities.entity_id) change_type"
        ) if game_has_content_changes() else ", NULL change_type"
        entity = db.execute(
            "SELECT entity_type, entity_id, name, description, source_table"
            f"{change_column} FROM entities WHERE entity_type = ? AND entity_id = ?",
            (entity_type, entity_id),
        ).fetchone()
        if not entity:
            return None
        detail = db.execute(f"SELECT * FROM {detail_table} WHERE id = ? LIMIT 1", (entity_id,)).fetchone()
        related = {}
        npc_exp = None
        if entity_type == "npc":
            related["spawns"] = [dict(row) for row in db.execute(
                "SELECT map_info_id, map_name, map_index, region_index, position, spawn_value "
                "FROM spawns WHERE npc_id = ? LIMIT 80", (entity_id,)
            )]
            related["lootCandidates"] = [dict(row) for row in db.execute(
                "SELECT reward_item_id, reward_item_name, reward_entity_type, min_value, enchant_level, subgroup_index "
                "FROM loot_candidates WHERE npc_id = ? LIMIT 100", (entity_id,)
            )]
            try:
                exp_row = db.execute(
                    "SELECT exp_base, npc_level, server_boost_exprate, confidence, source "
                    "FROM npc_exp WHERE npc_id = ?",
                    (int(entity_id) if entity_id.isdigit() else entity_id,),
                ).fetchone()
            except sqlite3.OperationalError:
                exp_row = None  # banco sem a tabela npc_exp (pré-F1); degrada sem EXP
            if exp_row:
                boost = exp_row["server_boost_exprate"] or 0
                npc_exp = {
                    "expBase": exp_row["exp_base"],
                    "serverBoostRate": boost,
                    "expWithServerBoost": math.floor(exp_row["exp_base"] * (1 + boost / 10000)),
                    "confidence": exp_row["confidence"],
                    "source": exp_row["source"],
                    "formula": "floor(EXP_base × (1 + Σ EXPDROPINCRATE / 10000))",
                }
        elif entity_type == "item":
            related["lootSources"] = [dict(row) for row in db.execute(
                "SELECT npc_id, npc_name, npc_level, min_value, enchant_level, subgroup_index "
                "FROM loot_candidates WHERE reward_item_id = ? LIMIT 100", (entity_id,)
            )]
            related["collections"] = [dict(row) for row in db.execute(
                "SELECT collection_id, required_quantity, required_enchant_level FROM collection_requirements "
                "WHERE accepted_item_id = ? LIMIT 100", (entity_id,)
            )]
            try:
                for source in related["lootSources"]:
                    maps = [row[0] for row in db.execute(
                        "SELECT DISTINCT map_name FROM spawns WHERE npc_id = ? AND map_name <> '' "
                        "ORDER BY map_name LIMIT 5", (source["npc_id"],),
                    )]
                    source["map_names"] = " · ".join(maps)
                related["craftUses"] = [dict(row) for row in db.execute(
                    "SELECT DISTINCT cm.recipe_key, cr.output_name, cr.category, cr.subcategory, cm.quantity, "
                    "cm.enchant_level FROM craft_materials cm JOIN craft_recipes cr ON cr.recipe_key = cm.recipe_key "
                    "WHERE cm.accepted_item_id = ? ORDER BY cr.output_name COLLATE NOCASE LIMIT 100", (entity_id,)
                )]
                related["craftProduces"] = [dict(row) for row in db.execute(
                    "SELECT DISTINCT crr.recipe_key, cr.output_name, cr.category, cr.subcategory, crr.result_type, "
                    "crr.enchant_level, crr.probability, crr.quantity FROM craft_results crr "
                    "JOIN craft_recipes cr ON cr.recipe_key = crr.recipe_key "
                    "WHERE crr.item_id = ? ORDER BY cr.output_name COLLATE NOCASE LIMIT 100", (entity_id,)
                )]
            except sqlite3.Error:
                related.setdefault("craftUses", [])
                related.setdefault("craftProduces", [])
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
    entity_payload = {**dict(entity), "typeLabel": label}
    entity_payload["nameEn"] = game_name_en(entity_type, entity_id)
    entity_payload["changeStatus"] = entity_payload.pop("change_type", None)
    payload = {"entity": entity_payload, "details": dict(detail) if detail else {}, "related": related}
    if npc_exp:
        payload["exp"] = npc_exp
    if entity_type == "item":
        try:
            item = market_item_lookup([entity_id]).get(entity_id)
            if item:
                payload["entity"]["image"] = market_image_url("", entity_id, item.get("icon"))
                payload["entity"]["iconAsset"] = item.get("icon", "")
                payload["entity"]["prime"] = item.get("prime", False)
                payload["entity"]["version"] = item.get("version", "Normal")
        except (ValueError, sqlite3.Error, OSError):
            pass
        try:
            history = market_history(entity_id)
            if history and history["captures"]:
                latest = history["captures"][0]
                payload["marketPrice"] = {
                    "capturedAt": latest["capturedAt"], "refinement": latest["refinement"],
                    "lowestPrice": latest["lowestPrice"], "highestPrice": latest["highestPrice"],
                    "quantity": latest["quantity"],
                }
        except (ValueError, sqlite3.Error, OSError):
            pass
    return payload


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
                "SELECT d.id, COALESCE(e.name, '') name, d.grade, d.tier, d.category raw_category, "
                "d.subcategory raw_subcategory, d.equip_part_type, d.equip_biosuit, d.icon, "
                "COALESCE(q.version, 'Normal') version "
                "FROM item_details d LEFT JOIN entities e ON e.entity_type = 'item' AND e.entity_id = d.id "
                "LEFT JOIN equipment_compare q ON q.item_id = d.id "
                f"WHERE d.id IN ({placeholders})", batch,
            )
            for row in rows:
                item = dict(row)
                item["nameEn"] = game_name_en("item", item["id"])
                item["prime"] = item["version"] == "Prime"
                item["category"], item["subcategory"] = classify_market_item(item)
                found[item["id"]] = item
    return found


@lru_cache(maxsize=1)
def market_image_names():
    try:
        return {path.name for path in MARKET_IMAGE_ROOT.iterdir() if path.is_file()}
    except OSError:
        return set()


@lru_cache(maxsize=1)
def game_icon_names():
    try:
        return {path.name for path in GAME_ICON_ROOT.iterdir() if path.is_file()}
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
    for stem in (icon_name, str(item_id or ""), str(icon or "")):
        if not stem:
            continue
        candidate = f"{stem}.png"
        if candidate in game_icon_names():
            return f"/game-icons/{quote(candidate, safe='')}"
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
        "rowType": ("rowtype", "tipo"),
        "serverType": ("servertype", "server_type", "tiposervidor"),
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
        row_type = get("rowType").casefold() or "summary"
        if row_type not in {"summary", "offer"}:
            raise ValueError(f"Linha {line}: tipo de registro inválido")
        server_type = parse_market_optional_integer(get("serverType"))
        if server_type is None:
            server_type = 0
        if server_type > 255:
            raise ValueError(f"Linha {line}: ServerType inválido")
        listings.append({
            "listingId": get("listingId") or str(line - 1), "itemId": item_id, "name": name,
            "rowType": row_type, "serverType": server_type,
            "category": category, "subcategory": subcategory, "refinement": refinement,
            "price": price, "highestPrice": highest_price, "quantity": quantity, "salesTotal": sales_total or price * quantity,
            "seller": get("seller")[:120], "image": image,
            "grade": parse_market_optional_integer(get("grade")) or item.get("grade"),
            "prime": item.get("prime", False), "version": item.get("version", "Normal"),
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


def import_market_csv(
    path, captured_at=None, source_id=None, profile=None, defer_notifications=False
):
    raw, listings = read_market_csv(path)
    server_types = {listing["serverType"] for listing in listings}
    if len(server_types) != 1:
        raise ValueError("Cada captura deve conter somente um ServerType.")
    server_type = next(iter(server_types))
    source_id = str(source_id or hashlib.sha256(raw).hexdigest()).strip()
    if not 1 <= len(source_id) <= 128:
        raise ValueError("Identificador da captura inválido")
    captured_at = normalize_market_timestamp(
        captured_at, datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    )
    imported_at = datetime.now(timezone.utc).isoformat()
    summaries = [listing for listing in listings if listing["rowType"] != "offer"]
    offers = [listing for listing in listings if listing["rowType"] == "offer"]
    grouped = {}
    for listing in summaries:
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
    levels = {}
    for listing in offers:
        match = re.search(r"\d+", listing["refinement"])
        key = (listing["itemId"], int(match.group()) if match else 0, listing["price"])
        levels[key] = levels.get(key, 0) + listing["quantity"]

    with database() as db:
        previous = db.execute("SELECT id FROM market_snapshots WHERE source_id = ?", (source_id,)).fetchone()
        if previous:
            if profile:
                db.execute(
                    "UPDATE market_snapshots SET profile=COALESCE(profile, ?) WHERE id=?",
                    (profile, previous[0]),
                )
            db.executemany(
                "INSERT OR REPLACE INTO market_price_levels "
                "(snapshot_id, item_id, refinement, price, quantity) VALUES (?, ?, ?, ?, ?)",
                ((previous[0], item_id, refinement, price, quantity)
                 for (item_id, refinement, price), quantity in levels.items()),
            )
            return {
                "snapshotId": previous[0], "serverType": server_type, "rows": len(grouped),
                "priceLevels": len(levels), "inserted": False,
            }
        cursor = db.execute(
            "INSERT INTO market_snapshots (captured_at, imported_at, source_id, row_count, total_registered, profile, server_type) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (captured_at, imported_at, source_id, len(grouped), sum(row["quantity"] for row in grouped.values()), profile, server_type),
        )
        snapshot_id = cursor.lastrowid
        db.executemany(
            "INSERT INTO market_prices (snapshot_id, item_id, item_name, category, subcategory, refinement, "
            "lowest_price, highest_price, registered_items, grade) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ((snapshot_id, item_id, row["name"], row["category"], row["subcategory"], refinement,
              row["price"], row["highestPrice"], row["quantity"], row["grade"])
             for (item_id, refinement), row in grouped.items()),
        )
        db.executemany(
            "INSERT INTO market_price_levels (snapshot_id, item_id, refinement, price, quantity) "
            "VALUES (?, ?, ?, ?, ?)",
            ((snapshot_id, item_id, refinement, price, quantity)
             for (item_id, refinement, price), quantity in levels.items()),
        )
    result = {
        "snapshotId": snapshot_id, "serverType": server_type, "rows": len(grouped), "priceLevels": len(levels),
        "inserted": True, "capturedAt": captured_at,
    }
    if defer_notifications:
        result["notificationsDeferred"] = True
    else:
        result["notificationsQueued"] = enqueue_market_alerts(snapshot_id)
    return result


def import_market_capture(profile, payload, idempotency_key, defer_notifications=False):
    if not re.fullmatch(r"[A-Fa-f0-9]{64}", idempotency_key or ""):
        raise ValueError("Chave de idempotência inválida.")
    metadata = payload.get("metadata") if isinstance(payload, dict) else None
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(metadata, dict) or not isinstance(rows, list) or not rows:
        raise ValueError("Captura de Mercado inválida.")
    if len(rows) > 100_000:
        raise ValueError("Captura de Mercado excede 100.000 registros.")
    if str(metadata.get("profile") or "").casefold() != profile.casefold():
        raise PermissionError("A captura pertence a outro Profile.")
    server_types = {
        int(row.get("ServerType", 0))
        for row in rows
        if isinstance(row, dict)
    }
    if len(server_types) != 1:
        raise ValueError("Envie cada ServerType em uma captura separada.")
    declared_server_type = metadata.get("market_server_type")
    if declared_server_type is not None and int(declared_server_type) not in server_types:
        raise ValueError("ServerType da captura não corresponde aos registros.")
    validate_capture_license(payload)
    fields = (
        "RowType", "ServerType", "ListingId", "Name", "ItemIndex", "Enhance",
        "PricePerUnit", "Qty", "HighestPrice",
    )
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".csv",
            encoding="utf-8-sig",
            newline="",
            delete=False,
        ) as target:
            temporary_path = Path(target.name)
            writer = csv.DictWriter(target, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError("Registro de Mercado inválido.")
                writer.writerow({field: row.get(field, "") for field in fields})
        return import_market_csv(
            temporary_path,
            metadata.get("captured_at"),
            idempotency_key,
            profile,
            defer_notifications,
        )
    finally:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)


def market_data():
    payload = {"loaded": False, "updatedAt": None, "listings": [], "taxonomy": MARKET_TAXONOMY,
               "requiredColumns": ["Name", "ItemIndex", "Enhance", "PricePerUnit", "Qty", "HighestPrice"]}
    with database() as db:
        snapshot = db.execute(
            "SELECT id, captured_at, row_count, total_registered, profile FROM market_snapshots "
            "ORDER BY captured_at DESC, id DESC LIMIT 1"
        ).fetchone()
        receipt = db.execute(
            "SELECT profile, imported_at FROM market_snapshots WHERE profile IS NOT NULL "
            "ORDER BY datetime(imported_at) DESC, id DESC LIMIT 1"
        ).fetchone()
        snapshot_count = db.execute("SELECT COUNT(*) FROM market_snapshots").fetchone()[0]
        server_summaries = {
            str(row["server_type"]): {
                "updatedAt": row["captured_at"],
                "snapshotCount": row["snapshot_count"],
                "totalRegistered": row["total_registered"],
            }
            for row in db.execute(
                "WITH ranked AS (SELECT server_type, captured_at, total_registered, "
                "COUNT(*) OVER (PARTITION BY server_type) snapshot_count, "
                "ROW_NUMBER() OVER (PARTITION BY server_type ORDER BY captured_at DESC, id DESC) position "
                "FROM market_snapshots) SELECT server_type, captured_at, total_registered, snapshot_count "
                "FROM ranked WHERE position=1"
            )
        }
        total_registered = sum(summary["totalRegistered"] for summary in server_summaries.values())
        if snapshot:
            rows = db.execute(
                "WITH latest_snapshots AS (SELECT id FROM (SELECT id, "
                "ROW_NUMBER() OVER (PARTITION BY server_type ORDER BY captured_at DESC, id DESC) position "
                "FROM market_snapshots) WHERE position=1), "
                "ranked AS (SELECT p.*, s.captured_at, "
                "s.server_type, "
                "ROW_NUMBER() OVER (PARTITION BY s.server_type, p.item_id, p.refinement ORDER BY s.captured_at DESC, s.id DESC) position, "
                "COUNT(*) OVER (PARTITION BY s.server_type, p.item_id, p.refinement) capture_count "
                "FROM market_prices p JOIN market_snapshots s ON s.id = p.snapshot_id) "
                "SELECT server_type, item_id, item_name, category, subcategory, refinement, lowest_price, highest_price, "
                "registered_items, grade, captured_at, capture_count FROM ranked "
                "WHERE position = 1 AND snapshot_id IN (SELECT id FROM latest_snapshots) "
                "ORDER BY server_type, item_id, refinement"
            ).fetchall()
            history = {}
            for row in db.execute(
                "SELECT s.server_type, p.item_id, p.refinement, p.lowest_price, p.registered_items "
                "FROM market_prices p JOIN market_snapshots s ON s.id = p.snapshot_id "
                "ORDER BY s.server_type, p.item_id, p.refinement, s.captured_at, s.id"
            ):
                history.setdefault((row["server_type"], row["item_id"], row["refinement"]), []).append(
                    (row["lowest_price"], row["registered_items"])
                )
            item_lookup = market_item_lookup(row["item_id"] for row in rows)
            listings = []
            for row in rows:
                item = item_lookup.get(row["item_id"], {})
                samples = history.get((row["server_type"], row["item_id"], row["refinement"]), [])
                previous = samples[-2] if len(samples) > 1 else None
                prices = [sample[0] for sample in samples]
                median_price = statistics.median(prices) if prices else row["lowest_price"]
                price_change = ((row["lowest_price"] - previous[0]) / previous[0] * 100) if previous and previous[0] else None
                stock_change = ((row["registered_items"] - previous[1]) / previous[1] * 100) if previous and previous[1] else None
                opportunity = ((median_price - row["lowest_price"]) / median_price * 100) if len(prices) >= 3 and median_price and row["lowest_price"] < median_price else 0
                listings.append({
                    "listingId": f"{row['server_type']}:{row['item_id']}:{row['refinement']}",
                    "serverType": row["server_type"],
                    "itemId": row["item_id"], "name": row["item_name"], "category": row["category"],
                    "nameEn": item.get("nameEn", ""),
                    "prime": item.get("prime", False), "version": item.get("version", "Normal"),
                    "subcategory": row["subcategory"], "refinement": f"+{row['refinement']}" if row["refinement"] else "Sem refino",
                    "price": row["lowest_price"], "highestPrice": row["highest_price"],
                    "quantity": row["registered_items"], "aggregate": True,
                    "seller": "", "image": market_image_url("", row["item_id"], item.get("icon")),
                    "grade": row["grade"], "tier": item.get("tier"), "quality": None, "start": None, "expire": None,
                    "capturedAt": row["captured_at"], "captureCount": row["capture_count"],
                    "iconAsset": item.get("icon", ""),
                    "previousPrice": previous[0] if previous else None,
                    "previousQuantity": previous[1] if previous else None,
                    "medianPrice": median_price,
                    "historicalLow": min(prices) if prices else row["lowest_price"],
                    "historicalHigh": max(prices) if prices else row["lowest_price"],
                    "priceChangePct": price_change,
                    "stockChangePct": stock_change,
                    "opportunityPct": opportunity,
                })
            payload.update({"loaded": True, "updatedAt": snapshot["captured_at"],
                            "lastProfile": receipt["profile"] if receipt else None,
                            "lastReceivedAt": receipt["imported_at"] if receipt else None,
                            "listings": listings,
                            "snapshotCount": snapshot_count, "totalRegistered": total_registered,
                            "serverSummaries": server_summaries,
                            "serverTypes": sorted({row["server_type"] for row in rows})})
            return payload
    if not MARKET_CSV_PATH.is_file():
        return payload
    _, listings = read_market_csv(MARKET_CSV_PATH)
    for listing in listings:
        listing["nameEn"] = game_name_en("item", listing.get("itemId"))
    payload.update({"loaded": True, "updatedAt": datetime.fromtimestamp(MARKET_CSV_PATH.stat().st_mtime, timezone.utc).isoformat(),
                    "listings": listings, "snapshotCount": 0})
    return payload


def market_history(item_id):
    if not re.fullmatch(r"\d{1,12}", item_id):
        raise ValueError("ItemIndex inválido")
    with database() as db:
        rows = db.execute(
            "SELECT s.captured_at, s.server_type, p.item_name, p.refinement, p.lowest_price, p.highest_price, "
            "p.registered_items FROM market_prices p JOIN market_snapshots s ON s.id = p.snapshot_id "
            "WHERE p.item_id = ? ORDER BY s.server_type, s.captured_at DESC, s.id DESC, p.refinement LIMIT 500",
            (item_id,),
        ).fetchall()
    if not rows:
        return None
    item = market_item_lookup([item_id]).get(item_id, {})
    chronological = list(reversed(rows))
    changes = {}
    previous = {}
    for row in chronological:
        key = (row["server_type"], row["refinement"])
        before = previous.get(key)
        changes[(row["captured_at"], *key)] = {
            "priceChangePct": ((row["lowest_price"] - before["price"]) / before["price"] * 100) if before and before["price"] else None,
            "stockChangePct": ((row["registered_items"] - before["quantity"]) / before["quantity"] * 100) if before and before["quantity"] else None,
        }
        previous[key] = {"price": row["lowest_price"], "quantity": row["registered_items"]}
    return {
        "itemId": item_id,
        "name": rows[0]["item_name"],
        "image": market_image_url("", item_id, item.get("icon")),
        "iconAsset": item.get("icon", ""),
        "tier": item.get("tier"),
        "grade": item.get("grade"),
        "prime": item.get("prime", False),
        "version": item.get("version", "Normal"),
        "captures": [{
            "capturedAt": row["captured_at"],
            "serverType": row["server_type"],
            "refinement": f"+{row['refinement']}" if row["refinement"] else "Sem refino",
            "lowestPrice": row["lowest_price"],
            "highestPrice": row["highest_price"],
            "quantity": row["registered_items"],
            **changes[(row["captured_at"], row["server_type"], row["refinement"])],
        } for row in rows],
    }


def latest_market_csv():
    with database() as db:
        snapshot = db.execute(
            "SELECT id, captured_at FROM market_snapshots ORDER BY captured_at DESC, id DESC LIMIT 1"
        ).fetchone()
        if not snapshot:
            return None
        rows = db.execute(
            "SELECT item_id, item_name, category, subcategory, refinement, lowest_price, highest_price, "
            "registered_items FROM market_prices WHERE snapshot_id = ? ORDER BY item_name COLLATE NOCASE, refinement",
            (snapshot["id"],),
        ).fetchall()
    item_lookup = market_item_lookup(row["item_id"] for row in rows)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("CapturedAt", "ItemIndex", "Name", "Category", "Subcategory", "Tier", "Refinement",
                     "LowestPrice", "HighestPrice", "RegisteredAds"))
    for row in rows:
        writer.writerow((
            snapshot["captured_at"], row["item_id"], row["item_name"], row["category"], row["subcategory"],
            item_lookup.get(row["item_id"], {}).get("tier") if item_lookup.get(row["item_id"], {}).get("tier") is not None else "", row["refinement"],
            row["lowest_price"], row["highest_price"], row["registered_items"],
        ))
    return ("\ufeff" + output.getvalue()).encode("utf-8"), snapshot["captured_at"]


def latest_market_price_map():
    with database() as db:
        snapshots = db.execute(
            "SELECT id, captured_at, server_type FROM ("
            "SELECT id, captured_at, server_type, ROW_NUMBER() OVER (PARTITION BY server_type "
            "ORDER BY captured_at DESC, id DESC) position FROM market_snapshots WHERE server_type IN (0,1)"
            ") WHERE position=1"
        ).fetchall()
        if not snapshots:
            return {}
        snapshot_ids = [row["id"] for row in snapshots]
        placeholders = ",".join("?" for _ in snapshot_ids)
        rows = db.execute(
            "SELECT p.item_id, p.refinement, MIN(p.lowest_price) lowest_price, "
            "SUM(p.registered_items) registered_items, MAX(s.captured_at) captured_at "
            "FROM market_prices p JOIN market_snapshots s ON s.id=p.snapshot_id "
            f"WHERE p.snapshot_id IN ({placeholders}) GROUP BY p.item_id, p.refinement",
            snapshot_ids,
        ).fetchall()
        current_rows = db.execute(
            "SELECT p.snapshot_id, s.server_type, p.item_id, p.refinement, p.lowest_price, "
            "p.highest_price, p.registered_items FROM market_prices p "
            "JOIN market_snapshots s ON s.id=p.snapshot_id "
            f"WHERE p.snapshot_id IN ({placeholders})",
            snapshot_ids,
        ).fetchall()
        levels = db.execute(
            "SELECT snapshot_id, item_id, refinement, price, SUM(quantity) quantity FROM market_price_levels "
            f"WHERE snapshot_id IN ({placeholders}) "
            "GROUP BY snapshot_id, item_id, refinement, price ORDER BY price",
            snapshot_ids,
        ).fetchall()
        previous_rows = {}
        for snapshot in snapshots:
            previous = db.execute(
                "SELECT id FROM market_snapshots WHERE server_type=? AND "
                "(captured_at<? OR (captured_at=? AND id<?)) "
                "ORDER BY captured_at DESC, id DESC LIMIT 1",
                (snapshot["server_type"], snapshot["captured_at"], snapshot["captured_at"], snapshot["id"]),
            ).fetchone()
            if not previous:
                continue
            for row in db.execute(
                "SELECT item_id, refinement, lowest_price, highest_price, registered_items "
                "FROM market_prices WHERE snapshot_id=?",
                (previous["id"],),
            ):
                previous_rows[(snapshot["server_type"], str(row["item_id"]), int(row["refinement"]))] = row
    result = {
        (str(row["item_id"]), int(row["refinement"])): {
            "price": row["lowest_price"], "quantity": row["registered_items"],
            "capturedAt": row["captured_at"], "priceLevels": [],
            "fallbackLowestQuantity": 0, "fallbackQuantityBasis": None,
            "detailedCoverageComplete": True,
        }
        for row in rows
    }
    detailed = {
        (row["snapshot_id"], str(row["item_id"]), int(row["refinement"]), row["price"])
        for row in levels
    }
    detailed_snapshots = {
        (row["snapshot_id"], str(row["item_id"]), int(row["refinement"])) for row in levels
    }
    for row in levels:
        key = (str(row["item_id"]), int(row["refinement"]))
        if key in result:
            existing = next((level for level in result[key]["priceLevels"] if level["price"] == row["price"]), None)
            if existing:
                existing["quantity"] += row["quantity"]
            else:
                result[key]["priceLevels"].append({"price": row["price"], "quantity": row["quantity"]})
    for row in current_rows:
        key = (str(row["item_id"]), int(row["refinement"]))
        if key in result and (row["snapshot_id"], key[0], key[1]) not in detailed_snapshots:
            result[key]["detailedCoverageComplete"] = False
        if key not in result or row["lowest_price"] != result[key]["price"]:
            continue
        detail_key = (row["snapshot_id"], key[0], key[1], row["lowest_price"])
        if detail_key in detailed:
            continue
        previous = previous_rows.get((row["server_type"], key[0], key[1]))
        if row["lowest_price"] == row["highest_price"]:
            quantity, basis = row["registered_items"], "exact"
        elif (previous and row["lowest_price"] < previous["lowest_price"]
              and row["registered_items"] > previous["registered_items"]):
            quantity, basis = row["registered_items"] - previous["registered_items"], "inferred"
        else:
            quantity, basis = 1, "minimum"
        result[key]["fallbackLowestQuantity"] += quantity
        bases = {result[key]["fallbackQuantityBasis"], basis} - {None}
        result[key]["fallbackQuantityBasis"] = "minimum" if "minimum" in bases else "inferred" if "inferred" in bases else "exact"
    for market in result.values():
        market["priceLevels"].sort(key=lambda level: level["price"])
    for alias, canonical in market_item_aliases().items():
        for (item_id, refinement), market in list(result.items()):
            if item_id == canonical and (alias, refinement) not in result:
                result[(alias, refinement)] = market
    return result


@lru_cache(maxsize=1)
def market_item_aliases():
    if not GAME_DB_PATH.is_file():
        return {}
    with game_database() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='market_item_aliases'").fetchone():
            return {}
        return {
            str(row["alias_item_id"]): str(row["market_item_id"])
            for row in db.execute("SELECT alias_item_id, market_item_id FROM market_item_aliases")
        }


def market_purchase_plan(market, quantity, require_details=False):
    quantity = int(quantity)
    if quantity < 0:
        raise ValueError("Quantidade de compra inválida")
    levels = []
    if market:
        levels.extend({**level, "quantityBasis": level.get("quantityBasis", "exact")}
                      for level in market.get("priceLevels", []))
        if not require_details:
            fallback = int(market.get("fallbackLowestQuantity") or 0)
            if fallback:
                levels.append({
                    "price": market["price"], "quantity": fallback,
                    "quantityBasis": market.get("fallbackQuantityBasis") or "minimum",
                })
            elif not levels and market.get("price") is not None:
                levels.append({"price": market["price"], "quantity": 1, "quantityBasis": "minimum"})
    grouped = {}
    for level in levels:
        price, available = float(level["price"]), int(level["quantity"])
        if available <= 0:
            continue
        current = grouped.setdefault(price, {"price": price, "quantity": 0, "quantityBasis": "exact"})
        current["quantity"] += available
        if level.get("quantityBasis") != "exact":
            current["quantityBasis"] = level.get("quantityBasis") or "minimum"
    remaining, lines = quantity, []
    for level in sorted(grouped.values(), key=lambda value: value["price"]):
        if remaining <= 0:
            break
        take = min(remaining, level["quantity"])
        lines.append({
            "unitPrice": level["price"], "quantity": take,
            "lineCost": take * level["price"], "quantityBasis": level["quantityBasis"],
        })
        remaining -= take
    covered = quantity - remaining
    return {
        "requestedQuantity": quantity, "coveredQuantity": covered,
        "missingQuantity": remaining, "totalCost": sum(line["lineCost"] for line in lines),
        "complete": remaining == 0, "lines": lines,
        "capturedAt": market.get("capturedAt") if market else None,
        "detailsMissing": bool(
            require_details and market and not market.get(
                "detailedCoverageComplete", bool(market.get("priceLevels"))
            )
        ),
    }


def salvage_data(query="", tier=None, grade=None, enchant=None, status="all",
                 sort="profit", limit=40, offset=0, prime="", internal=False):
    status_values = {"all", "source", "complete", "profitable", "missing"}
    sort_values = {"profit", "roi", "price", "name"}
    if status not in status_values or sort not in sort_values:
        raise ValueError("Filtro de salvage inválido")
    if prime not in {"", "normal", "prime"}:
        raise ValueError("Filtro Prime inválido")
    tier = parse_market_optional_integer(tier)
    grade = parse_market_optional_integer(grade)
    enchant = parse_market_optional_integer(enchant)
    if tier is not None and not 0 <= tier <= 20:
        raise ValueError("Tier inválido")
    if grade is not None and not 1 <= grade <= 20:
        raise ValueError("Raridade inválida")
    if enchant is not None and not 0 <= enchant <= 30:
        raise ValueError("Refino inválido")
    limit = max(1, min(int(limit), 5_000 if internal else 100))
    offset = max(0, min(int(offset), 1_000_000))

    clauses, values = [], []
    if search := normalize_search(query)[:80]:
        clauses.append("i.search_text LIKE ?")
        values.append(f"%{search}%")
    if tier is not None:
        clauses.append("i.tier=?")
        values.append(tier)
    if grade is not None:
        clauses.append("i.grade=?")
        values.append(grade)
    if enchant is not None:
        clauses.append("r.enchant_level=?")
        values.append(enchant)
    if prime:
        clauses.append("LOWER(COALESCE(e.version,'Normal'))=?")
        values.append(prime)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    with game_database() as db:
        meta = dict(db.execute("SELECT key,value FROM meta"))
        rows = db.execute(
            "SELECT r.item_id, i.item_name, i.grade, i.tier, i.icon, r.enchant_level, "
            "r.reward_item_id, o.item_name reward_name, o.grade reward_grade, "
            "o.tier reward_tier, o.icon reward_icon, r.quantity, r.reward_enchant_level, "
            "COALESCE(e.version,'Normal') version "
            "FROM salvage_results r JOIN salvage_items i ON i.item_id=r.item_id "
            "JOIN salvage_items o ON o.item_id=r.reward_item_id "
            "LEFT JOIN equipment_compare e ON e.item_id=r.item_id"
            + where +
            " ORDER BY i.item_name COLLATE NOCASE, r.item_id, r.enchant_level, o.item_name COLLATE NOCASE",
            values,
        ).fetchall()

    prices = latest_market_price_map()
    grouped = {}
    for row in rows:
        item = grouped.setdefault(row["item_id"], {
            "itemId": row["item_id"], "name": row["item_name"], "grade": row["grade"],
            "nameEn": game_name_en("item", row["item_id"]),
            "tier": row["tier"], "icon": row["icon"], "prime": row["version"] == "Prime", "levels": {},
        })
        level = item["levels"].setdefault(row["enchant_level"], {
            "enchant": row["enchant_level"], "outputs": [],
        })
        reward_key = (row["reward_item_id"], row["reward_enchant_level"])
        reward_market = prices.get(reward_key)
        unit_price = None if row["reward_item_id"] == "1" else (reward_market["price"] if reward_market else None)
        level["outputs"].append({
            "itemId": row["reward_item_id"], "name": row["reward_name"],
            "nameEn": game_name_en("item", row["reward_item_id"]),
            "grade": row["reward_grade"], "tier": row["reward_tier"],
            "quantity": row["quantity"], "enchant": row["reward_enchant_level"],
            "unitPrice": unit_price,
            "totalValue": unit_price * row["quantity"] if unit_price is not None else None,
            "priceSource": "market" if unit_price is not None else None,
            "capturedAt": reward_market["capturedAt"] if reward_market else None,
            "image": market_image_url("", row["reward_item_id"], row["reward_icon"]),
        })

    items = []
    for item in grouped.values():
        levels = []
        for level in item["levels"].values():
            source_market = prices.get((item["itemId"], level["enchant"]))
            known_value = sum(output["totalValue"] or 0 for output in level["outputs"])
            missing_prices = sum(output["unitPrice"] is None for output in level["outputs"])
            complete = source_market is not None and missing_prices == 0
            difference = known_value - source_market["price"] if complete else None
            roi = difference / source_market["price"] * 100 if complete and source_market["price"] else None
            level.update({
                "sourcePrice": source_market["price"] if source_market else None,
                "sourceQuantity": source_market["quantity"] if source_market else None,
                "sourceCapturedAt": source_market["capturedAt"] if source_market else None,
                "knownValue": known_value,
                "missingPrices": missing_prices,
                "complete": complete,
                "difference": difference,
                "roiPct": roi,
                "profitable": difference is not None and difference > 0,
            })
            levels.append(level)
        levels.sort(key=lambda value: value["enchant"])
        item["levels"] = levels
        item["pricedLevels"] = sum(level["sourcePrice"] is not None for level in levels)
        item["completeLevels"] = sum(level["complete"] for level in levels)
        item["profitableLevels"] = sum(level["profitable"] for level in levels)
        complete_levels = [level for level in levels if level["complete"]]
        best = max(complete_levels, key=lambda value: value["difference"]) if complete_levels else None
        item["bestDifference"] = best["difference"] if best else None
        item["bestRoiPct"] = best["roiPct"] if best else None
        item["bestEnchant"] = best["enchant"] if best else None
        items.append(item)

    summary = {
        "items": len(items),
        "sourcePriced": sum(item["pricedLevels"] > 0 for item in items),
        "fullyPriced": sum(item["completeLevels"] > 0 for item in items),
        "profitable": sum(item["profitableLevels"] > 0 for item in items),
        "rules": int(meta.get("count_salvage_results", 0)),
        "rewardItems": int(meta.get("count_salvage_reward_items", 0)),
    }
    if status == "source":
        items = [item for item in items if item["pricedLevels"]]
    elif status == "complete":
        items = [item for item in items if item["completeLevels"]]
    elif status == "profitable":
        items = [item for item in items if item["profitableLevels"]]
    elif status == "missing":
        items = [item for item in items if item["completeLevels"] < len(item["levels"])]

    sorters = {
        "profit": lambda item: (item["bestDifference"] is None, -(item["bestDifference"] or 0), item["name"].casefold()),
        "roi": lambda item: (item["bestRoiPct"] is None, -(item["bestRoiPct"] or 0), item["name"].casefold()),
        "price": lambda item: (not item["pricedLevels"], min((level["sourcePrice"] for level in item["levels"] if level["sourcePrice"] is not None), default=math.inf), item["name"].casefold()),
        "name": lambda item: item["name"].casefold(),
    }
    items.sort(key=sorters[sort])
    total = len(items)
    page = items[offset:offset + limit]
    lookup = market_item_lookup(item["itemId"] for item in page)
    for item in page:
        detail = lookup.get(item["itemId"], {})
        item["category"] = detail.get("category", "Outros")
        item["subcategory"] = detail.get("subcategory", "Consumable")
        item["image"] = market_image_url("", item["itemId"], item["icon"])
        del item["icon"]
    return {
        "items": page, "count": len(page), "total": total, "offset": offset,
        "limit": limit, "summary": summary,
        "priceNotice": "Valores brutos pelo menor preço capturado; créditos e diamantes não são convertidos entre si, taxas não estão incluídas.",
    }


def salvage_purchase_plan(sources, target_quantity):
    remaining, lines, offers = target_quantity, [], []
    for source in sources:
        levels = list(source.get("priceLevels") or [])
        fallback_quantity = source.get("fallbackLowestQuantity") or 0
        if source["sourcePrice"] is not None and fallback_quantity:
            levels.append({
                "price": source["sourcePrice"], "quantity": fallback_quantity,
                "quantityBasis": source.get("fallbackQuantityBasis") or "minimum",
            })
        elif source["sourcePrice"] is not None and not levels:
            levels.append({"price": source["sourcePrice"], "quantity": 1, "quantityBasis": "minimum"})
        offers.extend(
            {**source, "sourcePrice": level["price"],
             "availableQuantity": level["quantity"],
             "exactQuantity": level.get("quantityBasis", "exact") == "exact",
             "quantityBasis": level.get("quantityBasis", "exact")}
            for level in levels
        )
    offers.sort(key=lambda source: (
        source["sourcePrice"] / source["quantity"],
        source.get("name", "").casefold(),
        source.get("enchant", 0),
    ))
    for source in offers:
        if remaining <= 0:
            break
        available = source["availableQuantity"]
        buy = min(available, math.ceil(remaining / source["quantity"]))
        received = buy * source["quantity"]
        line_cost = buy * source["sourcePrice"]
        lines.append({
            **source, "buyQuantity": buy, "receivedQuantity": received,
            "lineCost": line_cost, "costPerMaterial": line_cost / received,
        })
        remaining -= received
    covered = sum(line["receivedQuantity"] for line in lines)
    total_cost = sum(line["lineCost"] for line in lines)
    return {
        "targetQuantity": target_quantity,
        "coveredQuantity": covered,
        "missingQuantity": max(0, target_quantity - covered),
        "overageQuantity": max(0, covered - target_quantity),
        "totalCost": total_cost,
        "costPerMaterial": total_cost / target_quantity if target_quantity else None,
        "complete": covered >= target_quantity,
        "lines": lines,
    }


def salvage_material_options():
    with game_database() as db:
        rows = db.execute(
            "SELECT DISTINCT o.item_id, o.item_name, o.grade, o.tier, o.icon, r.reward_enchant_level "
            "FROM salvage_results r JOIN salvage_items o ON o.item_id=r.reward_item_id "
            "WHERE r.reward_item_id<>? ORDER BY o.item_name COLLATE NOCASE, r.reward_enchant_level",
            ("1",),
        ).fetchall()
    return [{
        "itemId": row["item_id"], "name": row["item_name"], "grade": row["grade"],
        "nameEn": game_name_en("item", row["item_id"]),
        "tier": row["tier"], "enchant": row["reward_enchant_level"],
        "image": market_image_url("", row["item_id"], row["icon"]),
    } for row in rows]


def salvage_material_data(query="", tier=None, grade=None, enchant=None, status="all",
                          sort="cost", limit=40, offset=0, target_quantity=None, prime="", internal=False):
    if status not in {"all", "source", "missing"} or sort not in {"cost", "yield", "name"}:
        raise ValueError("Filtro de material inválido")
    if prime not in {"", "normal", "prime"}:
        raise ValueError("Filtro Prime inválido")
    tier = parse_market_optional_integer(tier)
    grade = parse_market_optional_integer(grade)
    enchant = parse_market_optional_integer(enchant)
    target_quantity = parse_market_optional_integer(target_quantity)
    if tier is not None and not 0 <= tier <= 20:
        raise ValueError("Tier inválido")
    if grade is not None and not 1 <= grade <= 20:
        raise ValueError("Raridade inválida")
    if enchant is not None and not 0 <= enchant <= 30:
        raise ValueError("Refino inválido")
    if target_quantity is not None and not 1 <= target_quantity <= 1_000_000:
        raise ValueError("Quantidade desejada inválida")
    limit = max(1, min(int(limit), 5_000 if internal else 100))
    offset = max(0, min(int(offset), 1_000_000))

    clauses, values = ["r.reward_item_id<>?"], ["1"]
    if search := normalize_search(query)[:80]:
        clauses.append("o.item_id=?" if search.isdigit() else "o.search_text LIKE ?")
        values.append(search if search.isdigit() else f"%{search}%")
    if tier is not None:
        clauses.append("i.tier=?")
        values.append(tier)
    if grade is not None:
        clauses.append("i.grade=?")
        values.append(grade)
    if enchant is not None:
        clauses.append("r.enchant_level=?")
        values.append(enchant)
    if prime:
        clauses.append("LOWER(COALESCE(e.version,'Normal'))=?")
        values.append(prime)
    with game_database() as db:
        meta = dict(db.execute("SELECT key,value FROM meta"))
        rows = db.execute(
            "SELECT r.reward_item_id, o.item_name reward_name, o.grade reward_grade, "
            "o.tier reward_tier, o.icon reward_icon, r.reward_enchant_level, "
            "r.item_id, i.item_name, i.grade, i.tier, i.icon, r.enchant_level, r.quantity, "
            "COALESCE(e.version,'Normal') version "
            "FROM salvage_results r JOIN salvage_items i ON i.item_id=r.item_id "
            "JOIN salvage_items o ON o.item_id=r.reward_item_id "
            "LEFT JOIN equipment_compare e ON e.item_id=r.item_id WHERE "
            + " AND ".join(clauses) +
            " ORDER BY o.item_name COLLATE NOCASE, r.reward_item_id, r.reward_enchant_level, "
            "i.item_name COLLATE NOCASE, r.enchant_level",
            values,
        ).fetchall()

    prices = latest_market_price_map()
    grouped = {}
    for row in rows:
        key = (row["reward_item_id"], row["reward_enchant_level"])
        material = grouped.setdefault(key, {
            "itemId": row["reward_item_id"], "name": row["reward_name"],
            "nameEn": game_name_en("item", row["reward_item_id"]),
            "grade": row["reward_grade"], "tier": row["reward_tier"],
            "enchant": row["reward_enchant_level"], "icon": row["reward_icon"], "sources": [],
        })
        market = prices.get((row["item_id"], row["enchant_level"]))
        material["sources"].append({
            "itemId": row["item_id"], "name": row["item_name"], "grade": row["grade"],
            "nameEn": game_name_en("item", row["item_id"]),
            "tier": row["tier"], "enchant": row["enchant_level"], "quantity": row["quantity"],
            "prime": row["version"] == "Prime",
            "sourcePrice": market["price"] if market else None,
            "sourceQuantity": market["quantity"] if market else None,
            "priceLevels": market["priceLevels"] if market else [],
            "fallbackLowestQuantity": market["fallbackLowestQuantity"] if market else 0,
            "fallbackQuantityBasis": market["fallbackQuantityBasis"] if market else None,
            "capturedAt": market["capturedAt"] if market else None,
            "unitCost": market["price"] / row["quantity"] if market else None,
            "icon": row["icon"],
        })

    materials = []
    for material in grouped.values():
        material["sources"].sort(key=lambda source: (
            source["unitCost"] is None, source["unitCost"] or math.inf,
            source["name"].casefold(), source["enchant"],
        ))
        material["sourceCount"] = len(material["sources"])
        priced = [source for source in material["sources"] if source["unitCost"] is not None]
        material["pricedSources"] = len(priced)
        material["bestUnitCost"] = priced[0]["unitCost"] if priced else None
        material["bestSource"] = priced[0]["name"] if priced else None
        material["maxYield"] = max(source["quantity"] for source in material["sources"])
        materials.append(material)

    summary = {
        "items": len(materials),
        "sourcePriced": sum(material["pricedSources"] > 0 for material in materials),
        "fullyPriced": sum(material["pricedSources"] for material in materials),
        "profitable": sum(material["sourceCount"] for material in materials),
        "rules": int(meta.get("count_salvage_results", 0)),
        "rewardItems": int(meta.get("count_salvage_reward_items", 0)),
    }
    if status == "source":
        materials = [material for material in materials if material["pricedSources"]]
    elif status == "missing":
        materials = [material for material in materials if not material["pricedSources"]]
    sorters = {
        "cost": lambda material: (material["bestUnitCost"] is None, material["bestUnitCost"] or math.inf, material["name"].casefold()),
        "yield": lambda material: (-material["maxYield"], material["name"].casefold()),
        "name": lambda material: material["name"].casefold(),
    }
    materials.sort(key=sorters[sort])
    total = len(materials)
    page = materials[offset:offset + limit]
    # ponytail: 50 opções mais baratas por material; paginar fontes se a lista completa virar necessária.
    for material in page:
        if target_quantity is not None:
            material["purchasePlan"] = salvage_purchase_plan(material["sources"], target_quantity)
        material["sources"] = material["sources"][:50]
    source_lookup = market_item_lookup(
        source["itemId"] for material in page
        for source in (
            material["sources"] + (material.get("purchasePlan", {}).get("lines", []))
        )
    )
    for material in page:
        material["image"] = market_image_url("", material["itemId"], material.pop("icon"))
        for source in material["sources"]:
            detail = source_lookup.get(source["itemId"], {})
            source["category"] = detail.get("category", "Outros")
            source["subcategory"] = detail.get("subcategory", "Consumable")
            source["image"] = market_image_url("", source["itemId"], source.pop("icon"))
        for line in material.get("purchasePlan", {}).get("lines", []):
            detail = source_lookup.get(line["itemId"], {})
            line["category"] = detail.get("category", "Outros")
            line["subcategory"] = detail.get("subcategory", "Consumable")
            line["image"] = market_image_url("", line["itemId"], line.pop("icon"))
    return {
        "mode": "material", "items": page, "count": len(page), "total": total,
        "offset": offset, "limit": limit, "summary": summary,
        "priceNotice": "Custo bruto por unidade = menor preço do equipamento ÷ quantidade recebida; outros resultados do salvage não são descontados.",
    }


def upgrade_expected_cost(rules, source_price, upgrader_price, output_quantity):
    reach = 1.0
    expected_attempts = 0.0
    expected_credits = 0.0
    for rule in rules:
        expected_attempts += reach
        expected_credits += reach * rule["creditCost"]
        reach *= rule["successRate"] / 10_000
    if not reach or output_quantity <= 0:
        return None
    return {
        "reachProbability": reach,
        "expectedSourceItems": 1 / reach,
        "expectedUpgraders": expected_attempts / reach,
        "expectedCredits": expected_credits / reach,
        "diamondsPerMaterial": (
            source_price / reach + upgrader_price * expected_attempts / reach
        ) / output_quantity,
    }


def salvage_upgrade_compare(item_id, material_id, material_enchant=0, target=1, upgrader_price=None):
    item_id, material_id = str(item_id), str(material_id)
    if not item_id.isdigit() or not material_id.isdigit():
        raise ValueError("Item inválido")
    target = int(target)
    material_enchant = int(material_enchant)
    if not 1 <= target <= 15 or not 0 <= material_enchant <= 30:
        raise ValueError("Refino inválido")
    if upgrader_price not in (None, ""):
        upgrader_price = float(upgrader_price)
        if not math.isfinite(upgrader_price) or upgrader_price < 0:
            raise ValueError("Preço do upgrader inválido")
    with game_database() as db:
        source = db.execute(
            "SELECT i.item_name, e.version, z.quantity direct_quantity, t.quantity target_quantity "
            "FROM salvage_items i LEFT JOIN equipment_compare e ON e.item_id=i.item_id "
            "LEFT JOIN salvage_results z ON z.item_id=i.item_id AND z.enchant_level=0 "
            "AND z.reward_item_id=? AND z.reward_enchant_level=? "
            "LEFT JOIN salvage_results t ON t.item_id=i.item_id AND t.enchant_level=? "
            "AND t.reward_item_id=? AND t.reward_enchant_level=? WHERE i.item_id=? LIMIT 1",
            (material_id, material_enchant, target, material_id, material_enchant, item_id),
        ).fetchone()
        rules = [dict(row) for row in db.execute(
            "SELECT level, success_rate successRate, break_rate breakRate, credit_cost creditCost, "
            "upgrader_item_group upgraderGroup FROM equipment_upgrade_rules "
            "WHERE item_id=? AND level<? ORDER BY level", (item_id, target)
        )]
        upgrader_ids = [row["item_id"] for row in db.execute(
            "SELECT item_id FROM equipment_upgrader_items WHERE item_group=?",
            (rules[0]["upgraderGroup"],),
        )] if rules else []
    if not source or len(rules) != target or not source["direct_quantity"] or not source["target_quantity"]:
        raise ValueError("Combinação sem regra completa")
    prices = latest_market_price_map()
    source_market = prices.get((item_id, 0))
    market_upgraders = [
        (prices[(upgrader_id, 0)]["price"], upgrader_id)
        for upgrader_id in upgrader_ids if (upgrader_id, 0) in prices
    ]
    market_upgraders.sort()
    effective_upgrader_price = upgrader_price if upgrader_price is not None else (
        market_upgraders[0][0] if market_upgraders else None
    )
    direct_cost = source_market["price"] / source["direct_quantity"] if source_market else None
    refined = upgrade_expected_cost(
        rules, source_market["price"], effective_upgrader_price, source["target_quantity"]
    ) if source_market and effective_upgrader_price is not None else None
    recommendation = None
    if direct_cost is not None and refined:
        recommendation = "refine" if refined["diamondsPerMaterial"] < direct_cost else "direct"
    return {
        "itemId": item_id, "name": source["item_name"], "prime": source["version"] == "Prime",
        "target": target, "directQuantity": source["direct_quantity"],
        "targetQuantity": source["target_quantity"], "sourcePrice": source_market["price"] if source_market else None,
        "upgraderPrice": effective_upgrader_price, "upgraderItemId": market_upgraders[0][1] if market_upgraders else None,
        "directDiamondsPerMaterial": direct_cost, "refined": refined,
        "recommendation": recommendation,
        "notice": "Estimativa com chances estáticas 1.28.5: cada falha quebra o item e cada tentativa usa 1 upgrader. Créditos ficam separados dos diamantes.",
    }


def craft_summary():
    with game_database() as db:
        meta = dict(db.execute("SELECT key, value FROM meta"))
        rows = db.execute("SELECT category, subcategory, COUNT(*) count FROM craft_recipes GROUP BY category, subcategory ORDER BY category, subcategory")
        categories = {}
        for row in rows:
            categories.setdefault(row["category"], {})[row["subcategory"]] = row["count"]
    return {"version": meta.get("source_version", "—"), "recipes": int(meta.get("count_craft_recipes", 0)), "categories": categories}


def latest_market_price_lookup(item_ids):
    item_ids = sorted({str(item_id) for item_id in item_ids if re.fullmatch(r"\d{1,12}", str(item_id))})
    if not item_ids:
        return {}, None
    market = latest_market_price_map()
    prices = {
        (item_id, refinement): value["price"]
        for (item_id, refinement), value in market.items()
        if item_id in item_ids
    }
    captured = [market[key]["capturedAt"] for key in prices if market[key].get("capturedAt")]
    return prices, min(captured) if captured else None


def enrich_craft_materials(materials, prices=None, captured_at=None):
    aliases = market_item_aliases()
    for material in materials:
        deduplicated = {}
        for accepted in material["acceptedItems"]:
            accepted["itemId"] = aliases.get(str(accepted["itemId"]), str(accepted["itemId"]))
            deduplicated.setdefault(accepted["itemId"], accepted)
        material["acceptedItems"] = list(deduplicated.values())
    item_meta = market_item_lookup(
        accepted["itemId"] for material in materials for accepted in material["acceptedItems"]
    )
    if prices is None:
        prices = latest_market_price_map()
        captured = [value.get("capturedAt") for value in prices.values() if value.get("capturedAt")]
        captured_at = min(captured) if captured else None
    for material in materials:
        for accepted in material["acceptedItems"]:
            accepted.update({key: item_meta.get(accepted["itemId"], {}).get(key, default)
                             for key, default in (("prime", False), ("version", "Normal"))})
            accepted["image"] = market_image_url("", accepted["itemId"], accepted.pop("icon", ""))
            market = prices.get((accepted["itemId"], material["enchantLevel"]))
            if market is not None:
                if not isinstance(market, dict):
                    market = {"price": market, "priceLevels": [{"price": market, "quantity": material["quantity"]}]}
                plan = market_purchase_plan(market, material["quantity"])
                accepted["marketPrice"] = market["price"]
                accepted["purchasePlan"] = plan
                if plan["complete"]:
                    accepted["marketTotal"] = plan["totalCost"]
        priced = [accepted for accepted in material["acceptedItems"] if "marketTotal" in accepted]
        if priced:
            cheapest = min(priced, key=lambda accepted: accepted["marketTotal"])
            material.update({
                "marketPrice": cheapest["marketPrice"],
                "marketTotal": cheapest["marketTotal"],
                "pricedItemId": cheapest["itemId"],
                "pricedItemName": cheapest["name"],
                "purchasePlan": cheapest["purchasePlan"],
            })
        else:
            partial = max(
                (accepted for accepted in material["acceptedItems"] if accepted.get("purchasePlan")),
                key=lambda accepted: (accepted["purchasePlan"]["coveredQuantity"], -accepted["purchasePlan"]["totalCost"]),
                default=None,
            )
            if partial:
                material["partialPurchasePlan"] = partial["purchasePlan"]
    return captured_at


def craft_market_summaries(recipe_keys):
    if not recipe_keys:
        return {}
    placeholders = ",".join("?" * len(recipe_keys))
    with game_database() as db:
        rows = db.execute(
            f"SELECT recipe_key, slot, item_group, quantity, enchant_level, accepted_item_id, "
            f"accepted_item_name, accepted_item_grade, accepted_item_tier, icon FROM craft_materials "
            f"WHERE recipe_key IN ({placeholders}) ORDER BY recipe_key, slot, accepted_item_name",
            recipe_keys,
        )
        grouped = {}
        for row in rows:
            materials = grouped.setdefault(row["recipe_key"], [])
            if not materials or materials[-1]["slot"] != row["slot"]:
                materials.append({"slot": row["slot"], "itemGroup": row["item_group"], "quantity": row["quantity"],
                                  "enchantLevel": row["enchant_level"], "acceptedItems": []})
            materials[-1]["acceptedItems"].append({
                "itemId": row["accepted_item_id"], "name": row["accepted_item_name"],
                "grade": row["accepted_item_grade"], "tier": row["accepted_item_tier"], "icon": row["icon"],
            })
    summaries = {}
    prices = latest_market_price_map()
    captured = [value.get("capturedAt") for value in prices.values() if value.get("capturedAt")]
    captured_at = min(captured) if captured else None
    for recipe_key, materials in grouped.items():
        enrich_craft_materials(materials, prices, captured_at)
        priced = [material for material in materials if "marketTotal" in material]
        summaries[recipe_key] = {
            "materialMarketCost": sum(material["marketTotal"] for material in priced),
            "pricedMaterials": len(priced),
            "materialCount": len(materials),
            "marketCapturedAt": captured_at,
        }
    return summaries


def craft_search(query, category, subcategory, limit=60, include_events=True, excluded_categories=(), grade=None, complete_market=False, internal=False):
    if category and category not in MARKET_TAXONOMY:
        raise ValueError("Categoria inválida")
    if subcategory and subcategory not in MARKET_TAXONOMY.get(category, []):
        raise ValueError("Subcategoria inválida")
    excluded_categories = tuple(dict.fromkeys(excluded_categories))
    if any(value not in MARKET_TAXONOMY for value in excluded_categories):
        raise ValueError("Categoria excluída inválida")
    grade = parse_market_optional_integer(grade)
    if grade is not None and not 1 <= grade <= 20:
        raise ValueError("Raridade inválida")
    clauses, values = [], []
    if query := normalize_search(query)[:80]:
        clauses.append("search_text LIKE ?")
        values.append(f"%{query}%")
    if not include_events:
        clauses.append("craft_period = 0")
    if category:
        clauses.append("category = ?")
        values.append(category)
    if subcategory:
        clauses.append("subcategory = ?")
        values.append(subcategory)
    if grade is not None:
        clauses.append("grade = ?")
        values.append(grade)
    if excluded_categories:
        clauses.append(f"category NOT IN ({','.join('?' * len(excluded_categories))})")
        values.extend(excluded_categories)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    limit = max(1, min(int(limit), 5_000 if internal else 100))
    change_column = (
        ", (SELECT change_type FROM content_changes c WHERE c.domain='craft' "
        "AND c.entity_id=CAST(craft_recipes.recipe_key AS TEXT)) change_status"
    ) if game_has_content_changes() else ", NULL change_status"
    select = (
        "SELECT recipe_key, recipe_id, output_item_id, output_name, name_en AS output_name_en, description, category, subcategory, grade, tier, use_level, "
        "icon, cost_type, cost_value, craft_period, output_enchant, normal_probability, better_probability, huge_probability, fail_probability"
        + change_column + " FROM craft_recipes" + where + " ORDER BY output_name COLLATE NOCASE, recipe_id"
    )
    with game_database() as db:
        total = db.execute("SELECT COUNT(*) FROM craft_recipes" + where, values).fetchone()[0]
        rows = db.execute(select + ("" if complete_market else " LIMIT ?"), values if complete_market else (*values, limit)).fetchall()
    results = [dict(row) for row in rows]
    item_meta = market_item_lookup(result["output_item_id"] for result in results)
    market = craft_market_summaries([row["recipe_key"] for row in rows])
    for result in results:
        result.update({key: item_meta.get(result["output_item_id"], {}).get(key, default)
                       for key, default in (("prime", False), ("version", "Normal"))})
        result["image"] = market_image_url("", result["output_item_id"], result.pop("icon", ""))
        result["event"] = bool(result.pop("craft_period"))
        result["changeStatus"] = result.pop("change_status", None)
        result.update(market.get(result["recipe_key"], {
            "materialMarketCost": 0, "pricedMaterials": 0, "materialCount": 0, "marketCapturedAt": None,
        }))
    if complete_market:
        results = [result for result in results if result["materialCount"] and result["pricedMaterials"] == result["materialCount"]]
        total = len(results)
        results = results[:limit]
    return {"results": results, "count": len(results), "total": total}


def craft_detail(recipe_key):
    try:
        recipe_key = int(recipe_key)
    except (TypeError, ValueError) as exc:
        raise ValueError("Receita inválida") from exc
    with game_database() as db:
        change_column = (
            ", (SELECT change_type FROM content_changes c WHERE c.domain='craft' "
            "AND c.entity_id=CAST(craft_recipes.recipe_key AS TEXT)) change_status"
        ) if game_has_content_changes() else ", NULL change_status"
        recipe = db.execute(
            "SELECT craft_recipes.*" + change_column + " FROM craft_recipes WHERE recipe_key = ?",
            (recipe_key,),
        ).fetchone()
        if not recipe:
            return None
        results = [dict(row) for row in db.execute(
            "SELECT result_type, item_id, item_name, name_en, enchant_level, probability, quantity, grade, tier, icon FROM craft_results WHERE recipe_key = ? ORDER BY CASE result_type WHEN 'normal' THEN 1 WHEN 'better' THEN 2 ELSE 3 END",
            (recipe_key,),
        )]
        material_rows = db.execute(
            "SELECT slot, item_group, quantity, enchant_level, accepted_item_id, accepted_item_name, name_en, accepted_item_grade, accepted_item_tier, icon FROM craft_materials WHERE recipe_key = ? ORDER BY slot, accepted_item_name",
            (recipe_key,),
        )
        materials = []
        for row in material_rows:
            if not materials or materials[-1]["slot"] != row["slot"]:
                materials.append({"slot": row["slot"], "itemGroup": row["item_group"], "quantity": row["quantity"],
                                  "enchantLevel": row["enchant_level"], "acceptedItems": []})
            materials[-1]["acceptedItems"].append({"itemId": row["accepted_item_id"], "name": row["accepted_item_name"],
                                                    "nameEn": row["name_en"],
                                                    "grade": row["accepted_item_grade"], "tier": row["accepted_item_tier"],
                                                    "icon": row["icon"]})
    item_meta = market_item_lookup([recipe["output_item_id"], *(result["item_id"] for result in results)])
    for result in results:
        result.update({key: item_meta.get(result["item_id"], {}).get(key, default)
                       for key, default in (("prime", False), ("version", "Normal"))})
        result["image"] = market_image_url("", result["item_id"], result.pop("icon", ""))
    captured_at = enrich_craft_materials(materials)
    priced = [material for material in materials if "marketTotal" in material]
    recipe = dict(recipe)
    recipe.update({key: item_meta.get(recipe["output_item_id"], {}).get(key, default)
                   for key, default in (("prime", False), ("version", "Normal"))})
    recipe["image"] = market_image_url("", recipe["output_item_id"], recipe.pop("icon", ""))
    recipe["event"] = bool(recipe.pop("craft_period"))
    recipe["changeStatus"] = recipe.pop("change_status", None)
    return {
        "recipe": recipe, "results": results, "materials": materials,
        "marketCapturedAt": captured_at,
        "materialMarketCost": sum(material["marketTotal"] for material in priced),
        "pricedMaterials": len(priced),
        "materialCount": len(materials),
    }


def tri_plate_data(quantity=1, target="stable"):
    quantity = int(quantity)
    if not 1 <= quantity <= 100_000 or target not in {"unstable", "stable"}:
        raise ValueError("Cálculo de Tri-Plate inválido")
    with game_database() as db:
        recipes = [dict(row) for row in db.execute(
            "SELECT recipe_key, output_item_id, output_name, name_en, cost_value, output_enchant "
            "FROM craft_recipes WHERE (name_en LIKE 'Unstable Dimensional Tri-Plate (%' "
            "OR name_en LIKE 'Stable Dimensional Tri-Plate (%') "
            "AND name_en NOT LIKE '%Chest%' ORDER BY name_en, recipe_key"
        )]
        recipe_keys = [recipe["recipe_key"] for recipe in recipes]
        if not recipe_keys:
            return {"quantity": quantity, "target": target, "variants": [], "marketCapturedAt": None}
        material_rows = list(db.execute(
            f"SELECT recipe_key, slot, quantity, enchant_level, accepted_item_id, accepted_item_name, "
            f"name_en, accepted_item_grade, accepted_item_tier, icon FROM craft_materials "
            f"WHERE recipe_key IN ({','.join('?' * len(recipe_keys))}) ORDER BY recipe_key, slot, accepted_item_id",
            recipe_keys,
        ))
    aliases, prices = market_item_aliases(), latest_market_price_map()
    captured = [value.get("capturedAt") for value in prices.values() if value.get("capturedAt")]
    captured_at = min(captured) if captured else None
    by_recipe = {}
    for row in material_rows:
        canonical = aliases.get(str(row["accepted_item_id"]), str(row["accepted_item_id"]))
        key = (row["recipe_key"], row["slot"], canonical)
        by_recipe.setdefault(key, {
            "itemId": canonical, "name": row["accepted_item_name"], "nameEn": row["name_en"],
            "grade": row["accepted_item_grade"], "tier": row["accepted_item_tier"], "icon": row["icon"],
            "quantity": int(row["quantity"]), "enchant": int(row["enchant_level"]),
        })
    materials = {}
    for (recipe_key, _slot, _canonical), material in by_recipe.items():
        materials.setdefault(recipe_key, []).append(material)

    def variant_name(recipe):
        match = re.search(r"\((.+)\)$", recipe["name_en"])
        return match.group(1) if match else recipe["output_item_id"]

    def shopping_lines(plan, item):
        image = market_image_url("", item["itemId"], item.get("icon", ""))
        return [{
            "itemId": item["itemId"], "name": item["name"], "nameEn": item.get("nameEn", ""),
            "grade": item.get("grade"), "tier": item.get("tier"), "enchant": item.get("enchant", 0),
            "image": image, **line,
        } for line in plan["lines"]]

    unstable = {}
    stable = {}
    for recipe in recipes:
        target_map = unstable if recipe["name_en"].startswith("Unstable ") else stable
        target_map.setdefault(variant_name(recipe), []).append(recipe)
    variants = []
    output_meta = market_item_lookup(recipe["output_item_id"] for recipe in recipes)
    for variant in sorted(set(unstable) & set(stable)):
        unstable_recipe = unstable[variant][0]
        stable_recipe = stable[variant][0]
        stable_materials = materials.get(stable_recipe["recipe_key"], [])
        stable_unstable_quantity = stable_materials[0]["quantity"] if len(stable_materials) == 1 else 20
        unstable_runs = quantity if target == "unstable" else quantity * stable_unstable_quantity
        route_results = []
        for recipe in unstable[variant]:
            recipe_materials = materials.get(recipe["recipe_key"], [])
            if len(recipe_materials) != 1:
                continue
            material = recipe_materials[0]
            needed = material["quantity"] * unstable_runs
            plan = market_purchase_plan(
                prices.get((material["itemId"], material["enchant"])), needed, require_details=True
            )
            route_results.append({
                "recipeKey": recipe["recipe_key"], "blueprint": {
                    **{key: material.get(key) for key in ("itemId", "name", "nameEn", "grade", "tier", "enchant")},
                    "quantity": needed,
                },
                "purchasePlan": plan, "shoppingLines": shopping_lines(plan, material),
                "diamondCost": plan["totalCost"] if plan["complete"] else None,
                "knownCost": plan["totalCost"], "craftCredits": recipe["cost_value"] * unstable_runs,
            })
        route_results.sort(key=lambda route: (
            not route["purchasePlan"]["complete"],
            route["diamondCost"] if route["diamondCost"] is not None else math.inf,
            -route["purchasePlan"]["coveredQuantity"], route["knownCost"],
        ))
        unstable_item = {
            "itemId": unstable_recipe["output_item_id"], "name": unstable_recipe["output_name"],
            "nameEn": unstable_recipe["name_en"], "enchant": unstable_recipe["output_enchant"],
            **{key: output_meta.get(unstable_recipe["output_item_id"], {}).get(key)
               for key in ("grade", "tier", "icon")},
        }
        stable_item = {
            "itemId": stable_recipe["output_item_id"], "name": stable_recipe["output_name"],
            "nameEn": stable_recipe["name_en"], "enchant": stable_recipe["output_enchant"],
            **{key: output_meta.get(stable_recipe["output_item_id"], {}).get(key)
               for key in ("grade", "tier", "icon")},
        }
        unstable_buy_quantity = quantity if target == "unstable" else quantity * stable_unstable_quantity
        unstable_market = market_purchase_plan(
            prices.get((unstable_item["itemId"], unstable_item["enchant"])), unstable_buy_quantity,
            require_details=True,
        )
        stable_market = market_purchase_plan(
            prices.get((stable_item["itemId"], stable_item["enchant"])), quantity,
            require_details=True,
        ) if target == "stable" else None
        options = [{
            "key": f"blueprints:{route['recipeKey']}",
            "label": f"Craftar com {route['blueprint']['name']}",
            "diamondCost": route["diamondCost"], "knownCost": route["knownCost"],
            "complete": route["purchasePlan"]["complete"],
            "missingQuantity": route["purchasePlan"]["missingQuantity"],
            "detailsMissing": route["purchasePlan"]["detailsMissing"],
            "detailMaterial": route["blueprint"]["name"],
            "craftCredits": route["craftCredits"] + (stable_recipe["cost_value"] * quantity if target == "stable" else 0),
            "shoppingLines": route["shoppingLines"],
        } for route in route_results]
        options.append({
            "key": "unstable-market", "label": "Comprar Unstable" if target == "stable" else "Comprar pronta",
            "diamondCost": unstable_market["totalCost"] if unstable_market["complete"] else None,
            "knownCost": unstable_market["totalCost"], "complete": unstable_market["complete"],
            "missingQuantity": unstable_market["missingQuantity"],
            "detailsMissing": unstable_market["detailsMissing"], "detailMaterial": unstable_item["name"],
            "craftCredits": stable_recipe["cost_value"] * quantity if target == "stable" else 0,
            "shoppingLines": shopping_lines(unstable_market, unstable_item),
        })
        if stable_market:
            options.append({
                "key": "stable-market", "label": "Comprar Stable pronta",
                "diamondCost": stable_market["totalCost"] if stable_market["complete"] else None,
                "knownCost": stable_market["totalCost"], "complete": stable_market["complete"],
                "missingQuantity": stable_market["missingQuantity"], "craftCredits": 0,
                "detailsMissing": stable_market["detailsMissing"], "detailMaterial": stable_item["name"],
                "shoppingLines": shopping_lines(stable_market, stable_item),
            })
        complete_options = [option for option in options if option["complete"]]
        cheapest = min(complete_options, key=lambda option: option["diamondCost"])["key"] if complete_options else None
        variants.append({
            "variant": variant, "unstable": {**unstable_item, "image": market_image_url("", unstable_item["itemId"], unstable_item.get("icon", ""))},
            "stable": {**stable_item, "image": market_image_url("", stable_item["itemId"], stable_item.get("icon", ""))},
            "unstablePerStable": stable_unstable_quantity,
            "unstableRoutes": route_results, "options": options, "cheapestOption": cheapest,
        })
    return {
        "quantity": quantity, "target": target, "variants": variants, "marketCapturedAt": captured_at,
        "notice": "Custos em diamantes consomem as faixas capturadas; créditos de craft permanecem separados. Cobertura parcial nunca é tratada como custo completo.",
    }


def craft_material_search(query, limit=30):
    query = market_key(query)[:80]
    limit = max(1, min(int(limit), 100))
    with game_database() as db:
        rows = db.execute(
            """SELECT accepted_item_id item_id,accepted_item_name name,name_en,
                       accepted_item_grade grade,accepted_item_tier tier,MAX(icon) icon
                FROM craft_materials
                GROUP BY accepted_item_id,accepted_item_name,name_en,
                         accepted_item_grade,accepted_item_tier
                ORDER BY accepted_item_name COLLATE NOCASE"""
        ).fetchall()
    if query:
        rows = [row for row in rows if query == row["item_id"] or query in market_key(row["name"]) or query in market_key(row["name_en"])]
    rows = rows[:limit]
    prices, captured_at = latest_market_price_lookup(row["item_id"] for row in rows)
    item_meta = market_item_lookup(row["item_id"] for row in rows)
    return {
        "results": [{
            "itemId": row["item_id"], "name": row["name"], "nameEn": row["name_en"],
            "grade": row["grade"], "tier": row["tier"],
            "prime": item_meta.get(row["item_id"], {}).get("prime", False),
            "version": item_meta.get(row["item_id"], {}).get("version", "Normal"),
            "image": market_image_url("", row["item_id"], row["icon"]),
            "marketPrice": prices.get((row["item_id"], 0)),
        } for row in rows],
        "marketCapturedAt": captured_at,
    }


def clean_personal_craft_inventory(value):
    if value in (None, {}):
        return {"materials": [], "chests": []}
    if not isinstance(value, dict):
        raise ValueError("Estoque do Craft Pessoal inválido")
    materials, chests = value.get("materials", []), value.get("chests", [])
    if not isinstance(materials, list) or not isinstance(chests, list) or len(materials) > 500 or len(chests) > 20:
        raise ValueError("Estoque do Craft Pessoal inválido")
    clean_materials = {}
    for material in materials:
        if not isinstance(material, dict):
            raise ValueError("Material do Craft Pessoal inválido")
        item_id = str(material.get("itemId", "")).strip()
        name = str(material.get("name", "")).strip()[:120]
        try:
            grade = int(material.get("grade", 0))
            quantity = int(material.get("quantity", 0))
        except (TypeError, ValueError):
            raise ValueError("Material do Craft Pessoal inválido")
        if not item_id.isdigit() or len(item_id) > 12 or not 1 <= grade <= 20 or not 1 <= quantity <= 1_000_000_000:
            raise ValueError("Material do Craft Pessoal inválido")
        clean_materials[item_id] = {"itemId": item_id, "name": name or f"Item {item_id}", "grade": grade, "quantity": quantity}
    clean_chests = {}
    for chest in chests:
        if not isinstance(chest, dict):
            raise ValueError("Baú do Craft Pessoal inválido")
        try:
            grade = int(chest.get("grade", 0))
            quantity = int(chest.get("quantity", 0))
        except (TypeError, ValueError):
            raise ValueError("Baú do Craft Pessoal inválido")
        if not 1 <= grade <= 20 or not 1 <= quantity <= 1_000_000_000:
            raise ValueError("Baú do Craft Pessoal inválido")
        clean_chests[grade] = {"grade": grade, "quantity": quantity}
    return {"materials": list(clean_materials.values()), "chests": list(clean_chests.values())}


def clean_personal_craft_recipes(value):
    if value in (None, []):
        return []
    if not isinstance(value, list) or len(value) > 50:
        raise ValueError("Receitas do Craft Pessoal inválidas")
    clean = {}
    for selected in value:
        if not isinstance(selected, dict):
            raise ValueError("Receita do Craft Pessoal inválida")
        try:
            recipe_key = int(selected.get("recipeKey", 0))
            runs = int(selected.get("runs", 0))
        except (TypeError, ValueError):
            raise ValueError("Receita do Craft Pessoal inválida")
        if recipe_key < 1 or not 1 <= runs <= 1_000_000:
            raise ValueError("Receita do Craft Pessoal inválida")
        name = str(selected.get("name", "")).strip()[:120]
        clean[recipe_key] = {"recipeKey": recipe_key, "runs": runs, **({"name": name} if name else {})}
    return list(clean.values())


def clean_manual_shopping(value):
    if value in (None, {}):
        return {}
    if not isinstance(value, dict) or len(value) > 200:
        raise ValueError("Lista de compra externa inválida")
    clean = {}
    for character, items in value.items():
        name = str(character).strip()
        if not 1 <= len(name) <= 80 or not isinstance(items, list) or len(items) > 1_000:
            raise ValueError("Lista de compra externa inválida")
        rows = {}
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Item da lista de compra inválido")
            item_id = str(item.get("itemId", "")).strip()
            item_name = str(item.get("name", "")).strip()[:120]
            source = str(item.get("source", "")).strip()[:160]
            image = str(item.get("image", "")).strip()[:500]
            prime = item.get("prime") is True
            try:
                enchant = int(item.get("enchant", 0))
                quantity = int(item.get("quantity", 0))
                grade = int(item.get("grade", 0))
                tier = int(item.get("tier", 0))
                unit_price = item.get("unitPrice")
                unit_price = None if unit_price in (None, "") else float(unit_price)
            except (TypeError, ValueError):
                raise ValueError("Item da lista de compra inválido")
            if (not item_id.isdigit() or len(item_id) > 12 or not source
                    or not 0 <= enchant <= 30 or not 1 <= quantity <= 1_000_000_000
                    or not 0 <= grade <= 20 or not 0 <= tier <= 20
                    or unit_price is not None and (not math.isfinite(unit_price) or not 0 <= unit_price <= 10**15)
                    or image and not image.lstrip("/").startswith(("api/", "game-icons/", "market-images/"))):
                raise ValueError("Item da lista de compra inválido")
            rows[(item_id, enchant, prime, source.casefold())] = {
                "itemId": item_id, "name": item_name or f"Item {item_id}", "source": source,
                "enchant": enchant, "quantity": quantity, "grade": grade, "tier": tier,
                "unitPrice": unit_price, "prime": prime, "bought": item.get("bought") is True,
                **({"image": image} if image else {}),
            }
        if rows:
            clean[name] = list(rows.values())
    return clean


def personal_craft_analysis(payload):
    if not isinstance(payload, dict):
        raise ValueError("Análise do Craft Pessoal inválida")
    selections = clean_personal_craft_recipes(payload.get("recipes"))
    inventories = payload.get("inventories", [])
    if not selections or not isinstance(inventories, list) or len(inventories) > 200:
        raise ValueError("Análise do Craft Pessoal inválida")
    stock, chest_stock = {}, {}
    for entry in inventories:
        character = str(entry.get("character", "")).strip() if isinstance(entry, dict) else ""
        if not 1 <= len(character) <= 80:
            raise ValueError("Personagem do Craft Pessoal inválido")
        inventory = clean_personal_craft_inventory(entry.get("inventory"))
        for material in inventory["materials"]:
            stock.setdefault(material["itemId"], []).append({"character": character, **material})
        for chest in inventory["chests"]:
            chest_stock.setdefault(chest["grade"], []).append({"character": character, "quantity": chest["quantity"]})

    with game_database() as game_db:
        recipe_rows = {row["recipe_key"]: dict(row) for row in game_db.execute(
            f"SELECT * FROM craft_recipes WHERE recipe_key IN ({','.join('?' * len(selections))})",
            [selected["recipeKey"] for selected in selections],
        )}
        if len(recipe_rows) != len(selections):
            raise ValueError("Receita do Craft Pessoal não encontrada")
        all_item_ids = [row[0] for row in game_db.execute(
            "SELECT DISTINCT accepted_item_id FROM craft_materials UNION SELECT DISTINCT item_id FROM craft_results"
        )]
        prices = latest_market_price_map()
        aliases = market_item_aliases()
        captured = [value.get("capturedAt") for value in prices.values() if value.get("capturedAt")]
        captured_at = min(captured) if captured else None
        recipe_cache = {}
        producer_cache = {}

        def recipe_data(recipe_key):
            if recipe_key not in recipe_cache:
                recipe = game_db.execute("SELECT * FROM craft_recipes WHERE recipe_key=?", (recipe_key,)).fetchone()
                if not recipe:
                    return None
                materials = []
                for row in game_db.execute(
                    "SELECT * FROM craft_materials WHERE recipe_key=? ORDER BY slot,accepted_item_name", (recipe_key,)
                ):
                    if not materials or materials[-1]["slot"] != row["slot"]:
                        materials.append({"slot": row["slot"], "quantity": row["quantity"], "enchant": row["enchant_level"], "accepted": []})
                    item_id = aliases.get(str(row["accepted_item_id"]), str(row["accepted_item_id"]))
                    if not any(option["itemId"] == item_id for option in materials[-1]["accepted"]):
                        materials[-1]["accepted"].append({"itemId": item_id, "name": row["accepted_item_name"], "grade": row["accepted_item_grade"]})
                results = [dict(row) for row in game_db.execute("SELECT * FROM craft_results WHERE recipe_key=?", (recipe_key,))]
                recipe_cache[recipe_key] = {"recipe": dict(recipe), "materials": materials, "results": results}
            return recipe_cache[recipe_key]

        def producers(item_ids):
            key = tuple(sorted(item_ids))
            if key not in producer_cache:
                producer_cache[key] = [row[0] for row in game_db.execute(
                    f"""SELECT DISTINCT r.recipe_key FROM craft_recipes r
                        JOIN craft_results o ON o.recipe_key=r.recipe_key
                        WHERE r.craft_period=0 AND o.item_id IN ({','.join('?' * len(key))})""", key
                )] if key else []
            return producer_cache[key]

        def priced_line(options, enchant, quantity):
            candidates = []
            for option in options:
                market = prices.get((option["itemId"], enchant))
                plan = market_purchase_plan(market, quantity)
                candidates.append({**option, "market": market, "purchasePlan": plan})
            complete = [option for option in candidates if option["purchasePlan"]["complete"]]
            chosen = min(complete, key=lambda option: option["purchasePlan"]["totalCost"]) if complete else max(
                candidates, key=lambda option: (option["purchasePlan"]["coveredQuantity"], -option["purchasePlan"]["totalCost"])
            )
            plan = chosen["purchasePlan"]
            return {
                "accepted": options, "itemId": chosen["itemId"], "name": chosen["name"], "grade": chosen["grade"],
                "quantity": quantity, "unitPrice": chosen["market"]["price"] if chosen["market"] else None,
                "marketTotal": plan["totalCost"] if plan["complete"] else None,
                "purchasePlan": plan, "enchant": enchant,
            }

        def direct_line(material, quantity):
            return priced_line(material["accepted"], material["enchant"], quantity)

        def merge_lines(lines):
            merged = {}
            for line in lines:
                key = (tuple(option["itemId"] for option in line["accepted"]), line["enchant"], line["grade"])
                if key not in merged:
                    merged[key] = copy.deepcopy(line)
                else:
                    merged[key]["quantity"] += line["quantity"]
            return [priced_line(line["accepted"], line["enchant"], line["quantity"]) for line in merged.values()]

        # ponytail: escolhe o subcraft pelo custo do snapshot; um otimizador global só vale quando estoque misto provar diferença relevante.
        def market_plan(recipe_key, runs, stack=()):
            data = recipe_data(recipe_key)
            if not data or recipe_key in stack or len(stack) >= 8:
                return {"lines": [], "fees": 0, "steps": [], "known": False}
            lines, fees, steps, known = [], data["recipe"]["cost_value"] * runs, [], True
            steps.append({"recipeKey": recipe_key, "name": data["recipe"]["output_name"], "runs": runs,
                          "feeCredits": data["recipe"]["cost_value"] * runs})
            for material in data["materials"]:
                quantity = material["quantity"] * runs
                direct = direct_line(material, quantity)
                best = {"lines": [direct], "fees": 0, "steps": [], "known": direct["marketTotal"] is not None,
                        "diamonds": direct["marketTotal"] if direct["marketTotal"] is not None else math.inf}
                accepted_ids = {option["itemId"] for option in material["accepted"]}
                for producer in producers(accepted_ids):
                    produced = sum(
                        float(result["probability"] or 0) / 10_000 * int(result["quantity"] or 0)
                        for result in recipe_data(producer)["results"] if result["item_id"] in accepted_ids
                    )
                    if produced <= 0:
                        continue
                    child = market_plan(producer, math.ceil(quantity / produced), (*stack, recipe_key))
                    child_cost = sum(
                        line["marketTotal"] for line in child["lines"] if line["marketTotal"] is not None
                    ) if child["known"] else math.inf
                    if child_cost < best["diamonds"]:
                        best = {**child, "diamonds": child_cost}
                lines.extend(best["lines"]); fees += best["fees"]; steps.extend(best["steps"]); known &= best["known"]
            return {"lines": merge_lines(lines), "fees": fees, "steps": steps, "known": known}

        full_lines, planned_lines, steps, fees, products = [], [], [], 0, []
        for selected in selections:
            data = recipe_data(selected["recipeKey"]); runs = selected["runs"]
            for material in data["materials"]:
                full_lines.append(direct_line(material, material["quantity"] * runs))
            plan = market_plan(selected["recipeKey"], runs)
            planned_lines.extend(plan["lines"]); steps.extend(plan["steps"]); fees += plan["fees"]
            recipe = data["recipe"]
            normal = next((result for result in data["results"] if result["result_type"] == "normal"), None)
            output_quantity = runs * int(normal["quantity"] if normal else 1)
            output_market = prices.get((recipe["output_item_id"], recipe["output_enchant"]))
            output_plan = market_purchase_plan(output_market, output_quantity)
            output_price = output_plan["totalCost"] / output_quantity if output_plan["complete"] and output_quantity else None
            products.append({"recipeKey": selected["recipeKey"], "name": recipe["output_name"], "runs": runs,
                             "quantity": output_quantity, "unitPrice": output_price,
                             "marketTotal": output_plan["totalCost"] if output_plan["complete"] else None,
                             "purchasePlan": output_plan})

    full_lines, planned_lines = merge_lines(full_lines), merge_lines(planned_lines)
    owned_value, owned_unknown = 0, False
    for line in planned_lines:
        remaining, origins = line["quantity"], []
        for option in line["accepted"]:
            for source in stock.get(option["itemId"], []):
                used = min(remaining, source["quantity"])
                if not used:
                    continue
                source["quantity"] -= used; remaining -= used
                market = prices.get((option["itemId"], line["enchant"]))
                unit_price = market["price"] if market else None
                owned_unknown |= unit_price is None
                owned_value += (unit_price or 0) * used
                origins.append({"character": source["character"], "itemId": option["itemId"], "quantity": used})
                if not remaining:
                    break
            if not remaining:
                break
        line.update({"ownedQuantity": line["quantity"] - remaining, "origins": origins, "purchaseQuantity": remaining,
                     "chestQuantity": 0, "chestOrigins": [], "chestUnitPrice": line["unitPrice"]})

    for grade, sources in chest_stock.items():
        candidates = sorted(
            (line for line in planned_lines if line["grade"] == grade and line["purchaseQuantity"] and line["unitPrice"] is not None),
            key=lambda line: line["unitPrice"], reverse=True,
        )
        for line in candidates:
            for source in sources:
                used = min(line["purchaseQuantity"], source["quantity"])
                if not used:
                    continue
                source["quantity"] -= used; line["purchaseQuantity"] -= used; line["chestQuantity"] += used
                line["chestOrigins"].append({"character": source["character"], "quantity": used})

    for line in planned_lines:
        plan = market_purchase_plan(prices.get((line["itemId"], line["enchant"])), line["purchaseQuantity"])
        line["purchasePlan"] = plan
        line["purchaseCost"] = plan["totalCost"] if plan["complete"] else None
        line["unitPrice"] = plan["totalCost"] / line["purchaseQuantity"] if plan["complete"] and line["purchaseQuantity"] else None
        line.pop("accepted", None)
    full_known = all(line["marketTotal"] is not None for line in full_lines)
    need_known = all(line["purchaseCost"] is not None or not line["purchaseQuantity"] for line in planned_lines)
    full_cost = sum(line["marketTotal"] for line in full_lines) if full_known else None
    needed_cost = sum(line["purchaseCost"] or 0 for line in planned_lines) if need_known else None
    chest_savings = sum(line["chestQuantity"] * (line["chestUnitPrice"] or 0) for line in planned_lines)
    product_known = all(product["marketTotal"] is not None for product in products)
    return {
        "marketCapturedAt": captured_at,
        "summary": {"fullPurchaseCost": full_cost, "neededCost": needed_cost,
                    "ownedMarketValue": None if owned_unknown else owned_value, "chestSavings": chest_savings,
                    "productMarketValue": sum(product["marketTotal"] for product in products) if product_known else None,
                    "craftFeesCredits": fees},
        "products": products, "requirements": planned_lines, "steps": steps,
        "notice": "Diamantes consomem as faixas disponíveis do último Local + Global; taxas de craft permanecem separadas em créditos.",
    }


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
        CREATE TABLE IF NOT EXISTS profile_tokens (
            token_hash TEXT PRIMARY KEY,
            profile TEXT NOT NULL,
            created_at TEXT NOT NULL,
            revoked_at TEXT,
            last_used_at TEXT
        );
        CREATE INDEX IF NOT EXISTS profile_tokens_profile
            ON profile_tokens (profile, revoked_at);
        CREATE TABLE IF NOT EXISTS profile_imports (
            profile TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            PRIMARY KEY (profile, idempotency_key)
        );
        CREATE TABLE IF NOT EXISTS market_snapshots (
            id INTEGER PRIMARY KEY,
            captured_at TEXT NOT NULL,
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source_id TEXT NOT NULL UNIQUE,
            row_count INTEGER NOT NULL,
            total_registered INTEGER NOT NULL,
            server_type INTEGER NOT NULL DEFAULT 0
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
        CREATE TABLE IF NOT EXISTS market_price_levels (
            snapshot_id INTEGER NOT NULL REFERENCES market_snapshots(id) ON DELETE CASCADE,
            item_id TEXT NOT NULL,
            refinement INTEGER NOT NULL,
            price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            PRIMARY KEY (snapshot_id, item_id, refinement, price)
        );
        CREATE TABLE IF NOT EXISTS discord_links (
            profile TEXT PRIMARY KEY,
            discord_user_id TEXT NOT NULL UNIQUE,
            discord_guild_id TEXT NOT NULL,
            dm_opt_in INTEGER NOT NULL DEFAULT 0,
            linked_at TEXT NOT NULL,
            last_delivery_at TEXT
        );
        CREATE TABLE IF NOT EXISTS discord_link_tokens (
            token_hash TEXT PRIMARY KEY,
            profile TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT
        );
        CREATE INDEX IF NOT EXISTS discord_link_tokens_profile
            ON discord_link_tokens (profile, used_at, expires_at);
        CREATE TABLE IF NOT EXISTS market_alert_state (
            profile TEXT NOT NULL,
            alert_id TEXT NOT NULL,
            hit INTEGER NOT NULL DEFAULT 0,
            last_price REAL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (profile, alert_id)
        );
        CREATE TABLE IF NOT EXISTS discord_outbox (
            id INTEGER PRIMARY KEY,
            profile TEXT NOT NULL,
            discord_user_id TEXT NOT NULL,
            alert_id TEXT NOT NULL,
            dedupe_key TEXT NOT NULL UNIQUE,
            payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            sent_at TEXT,
            last_error TEXT
        );
        CREATE INDEX IF NOT EXISTS discord_outbox_status
            ON discord_outbox (status, id);
    """)
    if "archived_at" not in {row["name"] for row in connection.execute("PRAGMA table_info(users)")}:
        connection.execute("ALTER TABLE users ADD COLUMN archived_at TEXT")
    if "profile" not in {row["name"] for row in connection.execute("PRAGMA table_info(market_snapshots)")}:
        connection.execute("ALTER TABLE market_snapshots ADD COLUMN profile TEXT")
    if "server_type" not in {row["name"] for row in connection.execute("PRAGMA table_info(market_snapshots)")}:
        connection.execute("ALTER TABLE market_snapshots ADD COLUMN server_type INTEGER NOT NULL DEFAULT 0")
    alert_state_columns = {row["name"] for row in connection.execute("PRAGMA table_info(market_alert_state)")}
    if "last_signature" not in alert_state_columns:
        connection.execute("ALTER TABLE market_alert_state ADD COLUMN last_signature TEXT")
    if "last_sent_at" not in alert_state_columns:
        connection.execute("ALTER TABLE market_alert_state ADD COLUMN last_sent_at TEXT")
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


def clean_character_loadout(value):
    if value in (None, {}):
        return {}
    if not isinstance(value, dict):
        raise ValueError("Equipamentos do personagem inválidos")

    def clean_item(item, kind, slot=None):
        if item in (None, "", 0, "0"):
            return None
        item = {"itemIndex": item} if isinstance(item, (int, str)) else item
        if not isinstance(item, dict):
            raise ValueError("Item equipado inválido")
        item_index = str(item.get("itemIndex") or item.get("item_index") or "").strip()
        if not item_index.isdigit() or not 1 <= len(item_index) <= 12:
            raise ValueError("Item equipado inválido")
        clean = {"itemIndex": item_index}
        name = str(item.get("name") or "").strip()
        if name:
            clean["name"] = name[:120]
        if kind == "equipment":
            slot = item.get("slot", item.get("slot_id", slot))
            try:
                slot = int(slot)
                refinement = int(item.get("refinement", item.get("refine", 0)) or 0)
            except (TypeError, ValueError):
                raise ValueError("Equipamento equipado inválido")
            if slot not in EQUIPMENT_SLOTS or not 0 <= refinement <= 30:
                raise ValueError("Equipamento equipado inválido")
            clean.update({"slot": slot, "refinement": refinement, "prime": item.get("prime") is True})
        return clean

    biosuit = clean_item(value.get("biosuit") or value.get("biosuit_equipped"), "biosuit")
    rover = clean_item(value.get("rover") or value.get("hover") or value.get("rover_equipped"), "rover")
    equipment = value.get("equipment", value.get("equipment_items", []))
    if not isinstance(equipment, list) or len(equipment) > len(EQUIPMENT_SLOTS):
        raise ValueError("Equipamentos do personagem inválidos")
    by_slot = {}
    for item in equipment:
        clean = clean_item(item, "equipment")
        if clean:
            by_slot[clean["slot"]] = clean
    result = {"equipment": [by_slot[slot] for slot in sorted(by_slot)]}
    if biosuit:
        result["biosuit"] = biosuit
    if rover:
        result["rover"] = rover
    updated_at = str(value.get("updatedAt") or value.get("updated_at") or "").strip()
    if updated_at:
        result["updatedAt"] = updated_at[:40]
    return result


def merge_character_loadout(previous, current):
    previous = clean_character_loadout(previous)
    current = clean_character_loadout(current)
    if not previous:
        return current
    merged = dict(previous)
    for key in ("biosuit", "rover", "equipment", "updatedAt"):
        if current.get(key):
            merged[key] = current[key]
    return merged


def clean_capture_receipts(value):
    if value in (None, {}):
        return {}
    if not isinstance(value, dict) or any(key not in CAPTURE_RECEIPT_KEYS for key in value):
        raise ValueError("Datas de recebimento inválidas")
    return {
        key: normalize_market_timestamp(str(received_at), datetime.now(timezone.utc))
        for key, received_at in value.items()
        if received_at
    }


def codex_receipt_keys(marks, collection_types=()):
    keys = set()
    types = {int(value) for value in collection_types if str(value).isdigit()}
    if 1 in types:
        keys.add("collection")
    if 2 in types:
        keys.add("memoryChip")
    if not types and marks:
        memory_ids = {str(chip["id"]) for chip in memory_chip_data()["chips"]}
        if any(str(item_id) in memory_ids for item_id in marks):
            keys.add("memoryChip")
        if any(str(item_id) not in memory_ids for item_id in marks):
            keys.add("collection")
    return keys


def clean_alert_rule(alert):
    if not isinstance(alert, dict):
        raise ValueError("Alerta inválido")
    alert_id = str(alert.get("id", ""))[:64]
    name = str(alert.get("name", "Alerta personalizado")).strip()[:80]
    source = str(alert.get("source", "market"))
    selectors = alert.get("selectors", {})
    conditions = alert.get("conditions", [])
    delivery = alert.get("delivery", {})
    if (not re.fullmatch(r"[\w:.-]{1,64}", alert_id) or not name
            or source not in ALERT_SOURCE_FIELDS or not isinstance(selectors, dict)
            or not isinstance(conditions, list) or not 1 <= len(conditions) <= 8
            or not isinstance(delivery, dict)):
        raise ValueError("Alerta personalizado inválido")

    def integers(key, low, high, maximum=100):
        values = selectors.get(key, [])
        if values in (None, ""):
            values = []
        if not isinstance(values, list) or len(values) > maximum:
            raise ValueError("Filtro do alerta inválido")
        try:
            result = sorted({int(value) for value in values})
        except (TypeError, ValueError):
            raise ValueError("Filtro do alerta inválido")
        if any(not low <= value <= high for value in result):
            raise ValueError("Filtro do alerta inválido")
        return result

    item_ids = selectors.get("itemIds", [])
    if not isinstance(item_ids, list) or len(item_ids) > 100:
        raise ValueError("Itens do alerta inválidos")
    item_ids = sorted({str(value) for value in item_ids})
    if any(not value.isdigit() or len(value) > 12 for value in item_ids):
        raise ValueError("Itens do alerta inválidos")

    def strings(key, legacy_key, allowed):
        values = selectors.get(key)
        if values is None:
            legacy = str(selectors.get(legacy_key, ""))
            values = [legacy] if legacy else []
        if not isinstance(values, list) or len(values) > 100:
            raise ValueError("Filtro do alerta inválido")
        result = sorted({str(value) for value in values if str(value)})
        if any(value not in allowed for value in result):
            raise ValueError("Filtro do alerta inválido")
        return result

    categories = strings("categories", "category", set(MARKET_TAXONOMY))
    subcategories = strings(
        "subcategories", "subcategory",
        {value for values in MARKET_TAXONOMY.values() for value in values},
    )
    prime = str(selectors.get("prime", ""))
    refinement_mode = str(selectors.get("refinementMode", "any"))
    refinements = integers("refinements", 0, 30, 31)
    if prime not in {"", "normal", "prime"} or refinement_mode not in {"any", "exact", "selected", "between", "up-to", "above", "greater-than"}:
        raise ValueError("Filtro do alerta inválido")
    if refinement_mode != "any" and not refinements:
        raise ValueError("Informe o refino do alerta")
    if refinement_mode in {"exact", "up-to", "above", "greater-than"} and len(refinements) != 1:
        raise ValueError("Informe um único refino")
    if refinement_mode == "between" and len(refinements) != 2:
        raise ValueError("Informe o início e o fim do refino")
    try:
        target_quantity = int(selectors.get("targetQuantity", 1))
    except (TypeError, ValueError):
        raise ValueError("Quantidade do alerta inválida")
    if not 1 <= target_quantity <= 1_000_000:
        raise ValueError("Quantidade do alerta inválida")
    clean_selectors = {
        "query": str(selectors.get("query", "")).strip()[:80],
        "itemIds": item_ids, "categories": categories, "subcategories": subcategories,
        "serverTypes": integers("serverTypes", 0, 1, 2),
        "tiers": integers("tiers", 0, 20, 21), "grades": integers("grades", 0, 20, 21),
        "prime": prime, "refinementMode": refinement_mode, "refinements": refinements,
        "targetQuantity": target_quantity, "includeEvents": selectors.get("includeEvents") is not False,
    }
    clean_conditions = []
    for condition in conditions:
        if not isinstance(condition, dict):
            raise ValueError("Condição do alerta inválida")
        field = str(condition.get("field", ""))
        operator = str(condition.get("operator", ""))
        try:
            value = float(condition.get("value"))
        except (TypeError, ValueError):
            raise ValueError("Valor da condição inválido")
        if field not in ALERT_SOURCE_FIELDS[source] or operator not in ALERT_OPERATORS or not math.isfinite(value) or abs(value) > 10**15:
            raise ValueError("Condição do alerta inválida")
        clean_conditions.append({"field": field, "operator": operator, "value": value})
    condition_mode = str(alert.get("conditionMode", "all"))
    repeat = str(delivery.get("repeat", "transition"))
    destination = str(delivery.get("destination", "dm"))
    language = str(delivery.get("language", "pt"))
    try:
        cooldown = int(delivery.get("cooldownMinutes", 0))
        result_limit = int(delivery.get("resultLimit", 10))
    except (TypeError, ValueError):
        raise ValueError("Entrega do alerta inválida")
    if condition_mode not in {"all", "any"} or repeat not in {"transition", "improve", "capture", "cooldown"} or destination not in {"dm", "channel"} or language not in {"pt", "en"} or not 0 <= cooldown <= 10_080 or not 1 <= result_limit <= 20:
        raise ValueError("Entrega do alerta inválida")
    return {
        "schemaVersion": 2, "id": alert_id, "name": name, "source": source,
        "enabled": alert.get("enabled") is not False, "selectors": clean_selectors,
        "conditionMode": condition_mode, "conditions": clean_conditions,
        "delivery": {"destination": destination, "repeat": repeat, "cooldownMinutes": cooldown, "resultLimit": result_limit, "language": language},
    }


def clean_history_column_layout(value):
    if not isinstance(value, dict):
        raise ValueError("Configuração das colunas inválida")
    order, widths, hidden = value.get("order", []), value.get("widths", {}), value.get("hidden", [])
    if not isinstance(order, list) or not isinstance(widths, dict) or not isinstance(hidden, list):
        raise ValueError("Configuração das colunas inválida")
    if len(order) > len(HISTORY_COLUMN_KEYS) or len(widths) > len(HISTORY_COLUMN_KEYS) or len(hidden) > len(HISTORY_COLUMN_KEYS):
        raise ValueError("Configuração das colunas inválida")
    clean_order = list(dict.fromkeys(str(key) for key in order if str(key) in HISTORY_COLUMN_KEYS))
    clean_hidden = list(dict.fromkeys(str(key) for key in hidden if str(key) in HISTORY_COLUMN_KEYS))
    clean_widths = {}
    for key, width in widths.items():
        key = str(key)
        try:
            width = round(float(width))
        except (TypeError, ValueError):
            raise ValueError("Configuração das colunas inválida")
        if key not in HISTORY_COLUMN_KEYS or not 70 <= width <= 2_000:
            raise ValueError("Configuração das colunas inválida")
        clean_widths[key] = width
    return {"order": clean_order, "widths": clean_widths, "hidden": clean_hidden}


def clean_state(value):
    if not isinstance(value, dict):
        raise ValueError("Estado inválido")
    history = value.get("history", [])
    characters = value.get("characters", [])
    locations = value.get("locations", [])
    spots = value.get("spots")
    mob_database = value.get("mobDatabase", [])
    codex = value.get("codex", {})
    codex_shopping = value.get("codexShopping", {})
    codex_shopping_bought = value.get("codexShoppingBought", {})
    codex_snapshots = value.get("codexSnapshots", {})
    salvage_watched_materials = value.get("salvageWatchedMaterials", [])
    market_favorites = value.get("marketFavorites", [])
    market_alerts = value.get("marketAlerts", [])
    character_shares = value.get("characterShares", {})
    archived_characters = value.get("archivedCharacters", [])
    capture_receipts = value.get("captureReceipts", {})
    personal_craft_recipes = value.get("personalCraftRecipes", [])
    manual_shopping = value.get("manualShopping", {})
    history_column_layout = value.get("historyColumnLayout", {})
    if not isinstance(history, list) or not isinstance(characters, list) or not isinstance(locations, list) or (spots is not None and not isinstance(spots, list)) or not isinstance(mob_database, list) or not isinstance(codex, dict) or not isinstance(codex_shopping, dict) or not isinstance(codex_shopping_bought, dict) or not isinstance(codex_snapshots, dict) or not isinstance(salvage_watched_materials, list) or not isinstance(market_favorites, list) or not isinstance(market_alerts, list) or not isinstance(character_shares, dict) or not isinstance(archived_characters, list):
        raise ValueError("Estado inválido")
    if len(history) > 10_000 or len(characters) > 200 or len(locations) > 500 or len(spots or []) > 500 or len(mob_database) > 5_000 or len(codex) > 200 or len(codex_shopping) > 200 or len(codex_shopping_bought) > 200 or len(codex_snapshots) > 200 or len(salvage_watched_materials) > 50 or len(market_favorites) > 1_000 or len(market_alerts) > 200 or len(character_shares) > 200 or len(archived_characters) > 200:
        raise ValueError("Limite de dados excedido")
    clean_watched_materials = []
    seen_watched_materials = set()
    for watched in salvage_watched_materials:
        if not isinstance(watched, dict):
            raise ValueError("Material monitorado inválido")
        item_id = str(watched.get("itemId", ""))
        try:
            enchant = int(watched.get("enchant", 0))
            target_quantity = int(watched.get("targetQuantity", 1))
        except (TypeError, ValueError):
            raise ValueError("Material monitorado inválido")
        key = (item_id, enchant)
        if not item_id.isdigit() or len(item_id) > 12 or not 0 <= enchant <= 30 or not 1 <= target_quantity <= 1_000_000:
            raise ValueError("Material monitorado inválido")
        if key not in seen_watched_materials:
            clean_watched_materials.append({"itemId": item_id, "enchant": enchant, "targetQuantity": target_quantity})
            seen_watched_materials.add(key)
    clean_characters = []
    for profile in characters:
        if not isinstance(profile, dict):
            raise ValueError("Personagem inválido")
        profile = dict(profile)
        if "loadout" in profile:
            profile["loadout"] = clean_character_loadout(profile["loadout"])
        if "craftInventory" in profile:
            profile["craftInventory"] = clean_personal_craft_inventory(profile["craftInventory"])
        character_uid = str(profile.get("characterUid") or profile.get("character_uid") or "").strip()
        if character_uid:
            if not character_uid.isdigit() or len(character_uid) > 20:
                raise ValueError("UID do personagem inválido")
            profile["characterUid"] = character_uid
            profile.pop("character_uid", None)
        clean_characters.append(profile)
    character_names = {
        str(character.get("name", "")).strip().casefold()
        for character in clean_characters
    }
    clean_archived_characters = []
    seen_archived_characters = set()
    for character in archived_characters:
        name = str(character).strip()
        key = name.casefold()
        if not 1 <= len(name) <= 80:
            raise ValueError("Personagem arquivado inválido")
        if key in character_names and key not in seen_archived_characters:
            clean_archived_characters.append(name)
            seen_archived_characters.add(key)
    clean_shares = {}
    for character, access in character_shares.items():
        name = str(character).strip()
        if not 1 <= len(name) <= 80 or not isinstance(access, dict):
            raise ValueError("Compartilhamento de personagem inválido")
        recipients = access.get("recipients", [])
        fields = access.get("fields", [])
        if not isinstance(recipients, list) or not isinstance(fields, list) or len(recipients) > 50:
            raise ValueError("Compartilhamento de personagem inválido")
        clean_recipients = []
        for recipient in recipients:
            recipient = normalize_user(recipient) if isinstance(recipient, str) else None
            if not recipient:
                raise ValueError("Perfil destinatário inválido")
            clean_recipients.append(recipient)
        if any(field not in CHARACTER_SHARE_FIELDS for field in fields):
            raise ValueError("Campo compartilhado inválido")
        clean_fields = sorted(set(fields))
        clean_recipients = sorted(set(clean_recipients))
        if clean_fields and clean_recipients:
            clean_shares[name] = {"recipients": clean_recipients, "fields": clean_fields}
    clean_favorites = sorted({str(item_id) for item_id in market_favorites if str(item_id).isdigit() and len(str(item_id)) <= 12})
    clean_alerts = []
    for alert in market_alerts:
        if isinstance(alert, dict) and int(alert.get("schemaVersion", 1) or 1) == 2:
            clean_alerts.append(clean_alert_rule(alert))
            continue
        if not isinstance(alert, dict):
            raise ValueError("Alerta de preço inválido")
        item_id = str(alert.get("itemId", ""))
        alert_id = str(alert.get("id", ""))[:64]
        try:
            refinement = int(alert.get("refinement", 0))
            target_price = float(alert.get("targetPrice", 0))
        except (TypeError, ValueError):
            raise ValueError("Alerta de preço inválido")
        kind = str(alert.get("kind", "market"))
        prime = str(alert.get("prime", ""))
        refinement_mode = str(alert.get("refinementMode", "exact"))
        try:
            refinements = sorted({int(value) for value in alert.get("refinements", [])})
        except (TypeError, ValueError):
            raise ValueError("Alerta de preço inválido")
        if not item_id.isdigit() or len(item_id) > 12 or not re.fullmatch(r"[\w:.-]{1,64}", alert_id) or not 0 <= refinement <= 30 or any(not 0 <= value <= 30 for value in refinements) or not math.isfinite(target_price) or not 0 < target_price <= 10**15 or kind not in {"market", "material-unit"} or prime not in {"", "normal", "prime"} or refinement_mode not in {"any", "exact", "selected", "up-to", "above"} or (refinement_mode == "selected" and not refinements):
            raise ValueError("Alerta de preço inválido")
        clean_alerts.append({
            "id": alert_id, "itemId": item_id, "refinement": refinement,
            "refinementMode": refinement_mode, "refinements": refinements,
            "targetPrice": target_price, "enabled": alert.get("enabled") is not False,
            "kind": kind, "prime": prime,
        })
    def clean_codex_marks(source):
        clean = {}
        for character, marks in source.items():
            name = str(character).strip()
            if not 1 <= len(name) <= 80 or not isinstance(marks, dict) or len(marks) > 5_000:
                raise ValueError("Progresso de coleção inválido")
            clean_marks = {}
            for collection_id, slots in marks.items():
                collection_id = str(collection_id)
                if not collection_id.isdigit() or len(collection_id) > 20 or not isinstance(slots, list):
                    raise ValueError("Progresso de coleção inválido")
                clean_slots = sorted({int(slot) for slot in slots if str(slot).isdigit() and 1 <= int(slot) <= 10})
                if clean_slots:
                    clean_marks[collection_id] = clean_slots
            clean[name] = clean_marks
        return clean
    clean_codex = clean_codex_marks(codex)
    clean_codex_shopping = clean_codex_marks(codex_shopping)
    clean_codex_shopping_bought = clean_codex_marks(codex_shopping_bought)
    clean_codex_snapshots = {}
    for character, snapshot in codex_snapshots.items():
        name = str(character).strip()
        if not 1 <= len(name) <= 80 or not isinstance(snapshot, dict):
            raise ValueError("Snapshot do Codex inválido")
        captured_at = str(snapshot.get("capturedAt", ""))[:40]
        collection_ids = snapshot.get("collections", [])
        if not isinstance(collection_ids, list) or len(collection_ids) > 5_000:
            raise ValueError("Snapshot do Codex inválido")
        clean_codex_snapshots[name] = {
            "capturedAt": captured_at,
            "collections": sorted({
                str(collection_id) for collection_id in collection_ids
                if str(collection_id).isdigit() and len(str(collection_id)) <= 20
            }, key=int),
            "marks": clean_codex_marks({name: snapshot.get("marks", {})})[name],
        }
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
    return {"history": history, "characters": clean_characters, "archivedCharacters": clean_archived_characters, "locations": clean_locations(locations), "spots": clean_locations(spots) if spots is not None else None, "mobDatabase": clean_mobs, "codex": clean_codex, "codexShopping": clean_codex_shopping, "codexShoppingBought": clean_codex_shopping_bought, "codexSnapshots": clean_codex_snapshots, "salvageWatchedMaterials": clean_watched_materials, "personalCraftRecipes": clean_personal_craft_recipes(personal_craft_recipes), "manualShopping": clean_manual_shopping(manual_shopping), "marketFavorites": clean_favorites, "marketAlerts": clean_alerts, "characterShares": clean_shares, "captureReceipts": clean_capture_receipts(capture_receipts), "historyColumnLayout": clean_history_column_layout(history_column_layout)}


def preserve_newer_character_capture(current, incoming):
    current_at = current["captureReceipts"].get("character", "")
    incoming_at = incoming["captureReceipts"].get("character", "")
    if not current_at or current_at <= incoming_at:
        return incoming
    for captured in current["characters"]:
        uid = str(captured.get("characterUid") or "")
        target = next((item for item in incoming["characters"] if uid and str(item.get("characterUid") or "") == uid), None)
        target = target or next((item for item in incoming["characters"] if item["name"].casefold() == captured["name"].casefold()), None)
        if not target:
            incoming["characters"].append(captured)
            continue
        for key in ("characterUid", "className", "level", "cp", "loadout"):
            if key in captured:
                target[key] = captured[key]
    incoming["captureReceipts"]["character"] = current_at
    return incoming


def shared_character_views(recipient, rows):
    views = []
    for owner, raw_state in rows:
        if owner == recipient:
            continue
        try:
            state = clean_state(json.loads(raw_state or "{}"))
        except (ValueError, json.JSONDecodeError):
            continue
        archived = {name.casefold() for name in state["archivedCharacters"]}
        for character, access in state["characterShares"].items():
            if character.casefold() in archived:
                continue
            if recipient not in access["recipients"]:
                continue
            profile = next(
                (
                    item for item in state["characters"]
                    if isinstance(item, dict)
                    and str(item.get("name", "")).casefold() == character.casefold()
                ),
                None,
            )
            if not profile:
                continue
            fields = set(access["fields"])
            view = {"owner": owner, "name": str(profile.get("name", character))[:80]}
            if "className" in fields:
                view["className"] = str(profile.get("className", ""))[:40]
            for field in ("level", "cp"):
                value = profile.get(field)
                if field in fields and isinstance(value, (int, float)) and not isinstance(value, bool):
                    view[field] = int(value)
            if "codex" in fields:
                marks = next(
                    (
                        value for name, value in state["codex"].items()
                        if name.casefold() == character.casefold()
                    ),
                    {},
                )
                view["codex"] = {
                    "collections": len(marks),
                    "items": sum(len(slots) for slots in marks.values()),
                }
            views.append(view)
    return sorted(views, key=lambda item: (item["owner"], item["name"].casefold()))


def parse_codex_snapshot(path, character=None):
    if path.stat().st_size > MAX_BODY:
        raise ValueError("Snapshot da coleção excede 5 MB")
    detected_characters = set()
    seen_types = set()
    ended_types = set()
    records = {}
    unknown_catalog = 0
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSONL inválido na linha {line_number}") from exc
            decoded = row.get("decoded", {})
            if decoded.get("type") == "world_info_prefix":
                name = str(decoded.get("fields", {}).get("character_name", "")).strip()
                if name:
                    detected_characters.add(name)
            chunk = row.get("collection", {})
            if chunk.get("type") != "collection_snapshot_chunk":
                continue
            collection_type = int(chunk.get("collection_type", -1))
            if collection_type in ended_types:
                raise ValueError(f"Bloco após o fim da coleção tipo {collection_type}")
            chunk_records = chunk.get("records")
            if not isinstance(chunk_records, list) or len(chunk_records) != int(chunk.get("record_count", -1)):
                raise ValueError(f"Contagem inválida na linha {line_number}")
            seen_types.add(collection_type)
            for record in chunk_records:
                collection_id = str(record.get("collection_index", ""))
                if not collection_id.isdigit() or collection_id in records:
                    raise ValueError(f"Coleção inválida ou duplicada: {collection_id}")
                if int(record.get("collection_type", -1)) != collection_type:
                    raise ValueError(f"Tipo divergente na coleção {collection_id}")
                if record.get("catalog_known") is False:
                    unknown_catalog += 1
                    records[collection_id] = []
                    continue
                completed = record.get("completed_slots")
                if not isinstance(completed, list):
                    raise ValueError(f"Conclusão ausente na coleção {collection_id}")
                records[collection_id] = sorted({
                    int(slot) + 1 for slot in completed if 0 <= int(slot) < 10
                })
            if chunk.get("is_end") is True:
                ended_types.add(collection_type)
    if not records:
        raise ValueError("Nenhum snapshot de coleção encontrado")
    if seen_types != ended_types:
        pending = ", ".join(map(str, sorted(seen_types - ended_types)))
        raise ValueError(f"Snapshot incompleto para os tipos: {pending}")
    selected_character = str(character or "").strip()
    if not selected_character:
        if len(detected_characters) != 1:
            raise ValueError("Informe o personagem para associar o snapshot")
        selected_character = detected_characters.pop()
    marks = {collection_id: slots for collection_id, slots in records.items() if slots}
    return {
        "character": selected_character,
        "marks": marks,
        "active_collections": sorted(records, key=int),
        "record_count": len(records),
        "marked_collections": len(marks),
        "unknown_catalog": unknown_catalog,
        "collection_types": sorted(seen_types),
    }


def import_codex_snapshot(path, character=None, user=None):
    snapshot = parse_codex_snapshot(path, character)
    received_at = datetime.now(timezone.utc).isoformat()
    requested_user = str(user or "").strip()
    if len(requested_user) > 254:
        raise ValueError("Usuário inválido")
    with database() as db:
        if not requested_user:
            candidates = []
            for candidate in db.execute("SELECT id, state FROM users"):
                try:
                    candidate_state = clean_state(json.loads(candidate["state"] or "{}"))
                except (ValueError, json.JSONDecodeError):
                    continue
                for profile in candidate_state["characters"]:
                    if (
                        isinstance(profile, dict)
                        and str(profile.get("name", "")).casefold()
                        == snapshot["character"].casefold()
                    ):
                        score = sum(bool(profile.get(field)) for field in ("level", "cp", "className"))
                        candidates.append((score, candidate["id"]))
                        break
            if candidates:
                best_score = max(score for score, _ in candidates)
                best_users = sorted({name for score, name in candidates if score == best_score})
                if len(best_users) != 1:
                    raise ValueError("Informe o usuário para associar o snapshot")
                requested_user = best_users[0]
            else:
                requested_user = LOCAL_USER
        user = requested_user
        if not user:
            raise ValueError("Usuário inválido")
        row = db.execute("SELECT share, state FROM users WHERE id = ?", (user,)).fetchone()
        share, raw_state = (row["share"], row["state"]) if row else (0, "{}")
        state = clean_state(json.loads(raw_state or "{}"))
        target = next(
            (
                profile.get("name")
                for profile in state["characters"]
                if isinstance(profile, dict)
                and str(profile.get("name", "")).casefold() == snapshot["character"].casefold()
            ),
            None,
        )
        if not target:
            target = snapshot["character"]
            state["characters"].append({"name": target})
        for name in list(state["codex"]):
            if name.casefold() == target.casefold():
                del state["codex"][name]
        state["codex"][target] = snapshot["marks"]
        for name in list(state["codexSnapshots"]):
            if name.casefold() == target.casefold():
                del state["codexSnapshots"][name]
        state["codexSnapshots"][target] = {
            "capturedAt": received_at,
            "collections": snapshot["active_collections"],
            "marks": snapshot["marks"],
        }
        for key in codex_receipt_keys(snapshot["marks"], snapshot["collection_types"]):
            state["captureReceipts"][key] = received_at
        state = clean_state(state)
        db.execute(
            "INSERT INTO users(id, share, state) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET share=excluded.share, state=excluded.state",
            (user, share, json.dumps(state, ensure_ascii=False, separators=(",", ":"))),
        )
    return {
        key: value for key, value in {**snapshot, "character": target, "user": user}.items()
        if key != "marks"
    }


def capture_license_claim(payload):
    metadata = payload.get("metadata") if isinstance(payload, dict) else None
    metadata = metadata if isinstance(metadata, dict) else {}
    if payload.get("requires_site_review") is True or metadata.get("requires_site_review") is True:
        raise ValueError("A captura precisa ser separada por personagem antes da importação.")
    identification = payload.get("identification_status") or metadata.get("identification_status")
    if identification == "unresolved":
        raise ValueError("A captura não possui identificação suficiente para importação.")
    lease = payload.get("lease") or payload.get("license_lease") or metadata.get("license_lease")
    installation_id = payload.get("installation_id") or metadata.get("installation_id")
    if not isinstance(lease, str) or not 20 <= len(lease) <= 4096:
        raise ValueError("Comprovante de licença ausente")
    if installation_id is not None and (not isinstance(installation_id, str) or len(installation_id) > 200):
        raise ValueError("Instalação inválida")
    return lease, installation_id


def parse_capture_csv(payload):
    text = payload.decode("utf-8-sig") if isinstance(payload, bytes) else str(payload)
    reader = csv.DictReader(io.StringIO(text))
    required = {
        "profile",
        "character_name",
        "identification_status",
        "requires_site_review",
        "installation_id",
        "license_lease",
        "codex_marks",
        "session_id",
    }
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError("CSV de captura inválido ou gerado por uma versão antiga.")
    row = next(reader, None)
    if not row:
        raise ValueError("CSV de captura vazio.")
    name = str(row.get("character_name") or "").strip()
    if not 1 <= len(name) <= 80:
        raise ValueError("Personagem ausente no CSV de captura.")
    character_uid = str(row.get("character_uid") or "").strip()
    if character_uid and (not character_uid.isdigit() or len(character_uid) > 20):
        raise ValueError("UID do personagem inválido no CSV de captura.")
    try:
        marks = json.loads(row.get("codex_marks") or "")
        marks = clean_state({"codex": {name: marks}})["codex"][name]
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("Marcações de Codex inválidas no CSV de captura.") from error
    try:
        loadout = clean_character_loadout(json.loads(row.get("loadout") or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("Equipamentos inválidos no CSV de captura.") from error
    return {
        "metadata": {
            "installation_id": row.get("installation_id"),
            "license_lease": row.get("license_lease"),
            "identification_status": row.get("identification_status"),
            "requires_site_review": str(
                row.get("requires_site_review") or ""
            ).strip().casefold() in {"1", "true", "sim", "yes"},
        },
        "profiles": [{
            "profile": str(row.get("profile") or "").strip(),
            "name": name,
            "marks": marks,
            **({"character_uid": character_uid} if character_uid else {}),
            **({"loadout": loadout} if loadout else {}),
        }],
    }


def introspect_license_lease(lease):
    if not LICENSE_INTROSPECT_URL:
        raise OSError("Validação de licença não configurada")
    body = json.dumps({"lease": lease}, separators=(",", ":")).encode()
    request = urlrequest.Request(
        LICENSE_INTROSPECT_URL,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urlrequest.urlopen(request, timeout=LICENSE_INTROSPECT_TIMEOUT) as response:
        result = json.loads(response.read(8192))
    if not isinstance(result, dict) or not isinstance(result.get("active"), bool):
        raise OSError("Resposta inválida do servidor de licença")
    return result


def validate_capture_license(payload):
    lease, installation_id = capture_license_claim(payload)
    result = introspect_license_lease(lease)
    if not result["active"] or (
        installation_id and result.get("installation_id") != installation_id
    ):
        raise PermissionError("Licença inativa ou expirada.")
    return {
        "active": True,
        "installation_id": result.get("installation_id"),
        "valid_until": result.get("valid_until"),
    }


def profile_for_token(token):
    if not token or not 20 <= len(token) <= 256:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    with database() as db:
        row = db.execute(
            """SELECT profile FROM profile_tokens
               WHERE token_hash=? AND revoked_at IS NULL""",
            (token_hash,),
        ).fetchone()
        if row:
            db.execute(
                "UPDATE profile_tokens SET last_used_at=? WHERE token_hash=?",
                (now, token_hash),
            )
    return row["profile"] if row else None


def create_profile_token(profile):
    token = "krv_profile_" + secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc).isoformat()
    with database() as db:
        db.execute(
            """UPDATE profile_tokens SET revoked_at=?
               WHERE profile=? AND revoked_at IS NULL""",
            (now, profile),
        )
        db.execute(
            """INSERT INTO profile_tokens(token_hash,profile,created_at)
               VALUES(?,?,?)""",
            (hashlib.sha256(token.encode()).hexdigest(), profile, now),
        )
    return token


def create_discord_link_token(profile):
    token = "krv_discord_" + secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    with database() as db:
        db.execute(
            "UPDATE discord_link_tokens SET used_at=? WHERE profile=? AND used_at IS NULL",
            (now.isoformat(), profile),
        )
        db.execute(
            "INSERT INTO discord_link_tokens(token_hash,profile,created_at,expires_at) VALUES(?,?,?,?)",
            (
                hashlib.sha256(token.encode()).hexdigest(), profile, now.isoformat(),
                datetime.fromtimestamp(now.timestamp() + 600, timezone.utc).isoformat(),
            ),
        )
    return token


def link_discord_user(token, discord_user_id, discord_guild_id):
    token_hash = hashlib.sha256(str(token).encode()).hexdigest()
    discord_user_id = str(discord_user_id).strip()
    discord_guild_id = str(discord_guild_id).strip()
    if not re.fullmatch(r"\d{1,30}", discord_user_id) or not re.fullmatch(r"\d{1,30}", discord_guild_id):
        raise ValueError("Identificador Discord inválido.")
    now = datetime.now(timezone.utc).isoformat()
    with database() as db:
        row = db.execute(
            "SELECT profile FROM discord_link_tokens WHERE token_hash=? AND used_at IS NULL AND expires_at>?",
            (token_hash, now),
        ).fetchone()
        if not row:
            raise ValueError("Vínculo Discord inválido ou expirado.")
        existing = db.execute(
            "SELECT profile FROM discord_links WHERE discord_user_id=?",
            (discord_user_id,),
        ).fetchone()
        if existing and existing["profile"] != row["profile"]:
            raise ValueError("Usuário Discord já vinculado a outro Profile.")
        db.execute(
            "INSERT INTO discord_links(profile,discord_user_id,discord_guild_id,linked_at) VALUES(?,?,?,?) "
            "ON CONFLICT(profile) DO UPDATE SET discord_user_id=excluded.discord_user_id, "
            "discord_guild_id=excluded.discord_guild_id, linked_at=excluded.linked_at, dm_opt_in=0",
            (row["profile"], discord_user_id, discord_guild_id, now),
        )
        db.execute("UPDATE discord_link_tokens SET used_at=? WHERE token_hash=?", (now, token_hash))
    return {"profile": row["profile"], "discordUserId": discord_user_id, "discordGuildId": discord_guild_id}


def set_discord_opt_in(discord_user_id, enabled):
    with database() as db:
        changed = db.execute(
            "UPDATE discord_links SET dm_opt_in=? WHERE discord_user_id=?",
            (1 if enabled else 0, str(discord_user_id)),
        ).rowcount
    if not changed:
        raise ValueError("Usuário Discord não vinculado.")
    return {"discordUserId": str(discord_user_id), "dmOptIn": bool(enabled)}


def material_unit_alert_offer(material, alert):
    lines = material.get("purchasePlan", {}).get("lines", [])
    priced = [line for line in lines if float(line.get("costPerMaterial") or 0) > 0]
    if not priced:
        return None
    cheapest = min(priced, key=lambda line: float(line["costPerMaterial"]))
    return {
        "item_id": alert["itemId"], "item_name": material.get("name") or alert["itemId"],
        "refinement": alert["refinement"], "lowest_price": float(cheapest["costPerMaterial"]),
        "captured_at": cheapest.get("capturedAt"),
    }


def material_unit_alert_price(alert):
    data = salvage_material_data(
        query=alert["itemId"], status="all", sort="cost", limit=20,
        target_quantity=1, prime=alert.get("prime", ""),
    )
    material = next((item for item in data["items"] if str(item["itemId"]) == alert["itemId"]), None)
    return material_unit_alert_offer(material, alert) if material else None


def alert_refinement_matches(selectors, refinement):
    mode, values = selectors.get("refinementMode", "any"), selectors.get("refinements", [])
    if mode == "any":
        return True
    if mode in {"exact", "selected"}:
        return refinement in values
    if mode == "between":
        return values[0] <= refinement <= values[1]
    if mode == "up-to":
        return refinement <= values[0]
    if mode == "greater-than":
        return refinement > values[0]
    return refinement >= values[0]


def alert_selector_matches(candidate, selectors):
    search = normalize_search(selectors.get("query", ""))
    searchable = normalize_search(f"{candidate.get('name', '')} {candidate.get('nameEn', '')} {candidate.get('itemId', '')}")
    return (
        (not search or search in searchable)
        and (not selectors["itemIds"] or str(candidate.get("itemId", "")) in selectors["itemIds"])
        and (not selectors["categories"] or candidate.get("category") in selectors["categories"])
        and (not selectors["subcategories"] or candidate.get("subcategory") in selectors["subcategories"])
        and (not selectors["serverTypes"] or candidate.get("serverType") in selectors["serverTypes"])
        and (not selectors["tiers"] or candidate.get("tier") in selectors["tiers"])
        and (not selectors["grades"] or candidate.get("grade") in selectors["grades"])
        and (not selectors["prime"] or selectors["prime"] == ("prime" if candidate.get("prime") else "normal"))
        and alert_refinement_matches(selectors, int(candidate.get("refinement", 0) or 0))
    )


def alert_condition_matches(value, operator, target):
    if value is None or isinstance(value, bool) and not isinstance(target, bool):
        value = int(value) if value is not None else None
    if value is None:
        return False
    return {"lt": value < target, "lte": value <= target, "eq": value == target,
            "gte": value >= target, "gt": value > target}[operator]


def material_alert_source(item):
    lines = item.get("purchasePlan", {}).get("lines", [])
    priced = [line for line in lines if float(line.get("costPerMaterial") or 0) > 0]
    if not priced:
        return None
    source = min(priced, key=lambda line: float(line["costPerMaterial"]))
    return {
        "itemId": source.get("itemId"), "name": source.get("name"),
        "nameEn": source.get("nameEn", ""), "refinement": source.get("enchant", 0),
        "prime": source.get("prime", False), "price": source.get("sourcePrice"),
    }


def alert_rule_candidates(profile, state, alert):
    source, selectors = alert["source"], alert["selectors"]
    query = selectors["query"] or (selectors["itemIds"][0] if len(selectors["itemIds"]) == 1 else "")
    if source == "market":
        candidates = [{
            "key": listing["listingId"], "itemId": listing["itemId"], "name": listing["name"],
            "nameEn": listing.get("nameEn", ""), "category": listing["category"],
            "subcategory": listing["subcategory"], "tier": listing.get("tier"),
            "grade": listing.get("grade"), "prime": listing.get("prime", False),
            "serverType": listing.get("serverType"),
            "refinement": refinement_number(listing["refinement"]), "capturedAt": listing.get("capturedAt"),
            "metrics": {field: listing.get(field) for field in ALERT_SOURCE_FIELDS["market"]},
        } for listing in market_data()["listings"]]
    elif source == "material":
        data = salvage_material_data(query=query, status="all", sort="cost", limit=5_000,
                                     target_quantity=selectors["targetQuantity"], prime=selectors["prime"], internal=True)
        candidates = [{
            "key": f"material:{item['itemId']}:{item['enchant']}", "itemId": item["itemId"],
            "name": item["name"], "nameEn": item.get("nameEn", ""), "category": "Material",
            "subcategory": "Powerup Materials", "tier": item.get("tier"), "grade": item.get("grade"),
            "prime": selectors["prime"] == "prime", "refinement": item.get("enchant", 0),
            "capturedAt": next((source.get("capturedAt") for source in item["sources"] if source.get("capturedAt")), None),
            "source": material_alert_source(item),
            "metrics": {"bestUnitCost": item.get("bestUnitCost"), "sourceCount": item.get("sourceCount"),
                        "pricedSources": item.get("pricedSources"), "maxYield": item.get("maxYield"),
                        "totalCost": item.get("purchasePlan", {}).get("totalCost"),
                        "coveredQuantity": item.get("purchasePlan", {}).get("coveredQuantity"),
                        "missingQuantity": item.get("purchasePlan", {}).get("missingQuantity"),
                        "complete": int(item.get("purchasePlan", {}).get("complete", False))},
        } for item in data["items"]]
    elif source == "salvage":
        data = salvage_data(query=query, tier=selectors["tiers"][0] if len(selectors["tiers"]) == 1 else None,
                            grade=selectors["grades"][0] if len(selectors["grades"]) == 1 else None,
                            enchant=selectors["refinements"][0] if selectors["refinementMode"] == "exact" else None,
                            status="all", sort="profit", limit=5_000, prime=selectors["prime"], internal=True)
        candidates = []
        for item in data["items"]:
            for level in item["levels"]:
                candidates.append({
                    "key": f"salvage:{item['itemId']}:{level['enchant']}", "itemId": item["itemId"],
                    "name": item["name"], "nameEn": item.get("nameEn", ""), "category": item.get("category"),
                    "subcategory": item.get("subcategory"), "tier": item.get("tier"), "grade": item.get("grade"),
                    "prime": item.get("prime", False), "refinement": level["enchant"],
                    "capturedAt": level.get("sourceCapturedAt"),
                    "metrics": {field: level.get(field) for field in ALERT_SOURCE_FIELDS["salvage"]},
                })
    elif source == "craft":
        data = craft_search(query, selectors["categories"][0] if len(selectors["categories"]) == 1 else "",
                            selectors["subcategories"][0] if len(selectors["subcategories"]) == 1 else "", limit=5_000,
                            include_events=selectors["includeEvents"], grade=selectors["grades"][0] if len(selectors["grades"]) == 1 else None,
                            complete_market=False, internal=True)
        product_prices, captured_at = latest_market_price_lookup(result["output_item_id"] for result in data["results"])
        candidates = []
        for result in data["results"]:
            product_price = product_prices.get((result["output_item_id"], result["output_enchant"]))
            cost = result.get("materialMarketCost") if result.get("pricedMaterials") == result.get("materialCount") else None
            savings = product_price - cost if product_price is not None and cost is not None else None
            candidates.append({
                "key": f"craft:{result['recipe_key']}", "itemId": result["output_item_id"], "name": result["output_name"],
                "nameEn": result.get("output_name_en", ""), "category": result["category"], "subcategory": result["subcategory"],
                "tier": result.get("tier"), "grade": result.get("grade"), "prime": result.get("prime", False),
                "refinement": result.get("output_enchant", 0), "capturedAt": captured_at,
                "metrics": {"materialMarketCost": cost, "pricedMaterials": result.get("pricedMaterials"),
                            "materialCount": result.get("materialCount"), "complete": int(cost is not None),
                            "productMarketPrice": product_price, "savings": savings,
                            "savingsPct": savings / product_price * 100 if savings is not None and product_price else None},
            })
    else:
        recipes = state.get("personalCraftRecipes", [])
        inventories = [{"character": character.get("name", ""), "inventory": character.get("craftInventory", {})}
                       for character in state.get("characters", []) if character.get("name")]
        if not recipes or not inventories:
            return []
        analysis = personal_craft_analysis({"recipes": recipes, "inventories": inventories})
        summary = analysis["summary"]
        savings = (summary["productMarketValue"] - summary["neededCost"]
                   if summary["productMarketValue"] is not None and summary["neededCost"] is not None else None)
        candidates = [{
            "key": f"personal-craft:{profile}", "itemId": "", "name": "Craft Pessoal",
            "nameEn": "Personal Craft", "category": "", "subcategory": "", "tier": None,
            "grade": None, "prime": False, "refinement": 0, "capturedAt": analysis.get("marketCapturedAt"),
            "metrics": {**summary, "savings": savings,
                        "savingsPct": savings / summary["productMarketValue"] * 100
                        if savings is not None and summary["productMarketValue"] else None},
        }]
    return [candidate for candidate in candidates if alert_selector_matches(candidate, selectors)]


def refinement_number(value):
    digits = re.sub(r"\D", "", str(value or ""))
    return int(digits) if digits else 0


def evaluate_alert_rule(profile, state, alert):
    candidates = alert_rule_candidates(profile, state, alert)
    matches = []
    for candidate in candidates:
        results = [alert_condition_matches(candidate["metrics"].get(condition["field"]), condition["operator"], condition["value"])
                   for condition in alert["conditions"]]
        if (all(results) if alert["conditionMode"] == "all" else any(results)):
            matches.append(candidate)
    first = alert["conditions"][0]
    reverse = first["operator"] in {"gte", "gt"}
    matches.sort(key=lambda candidate: (candidate["metrics"].get(first["field"]) is None,
                                        candidate["metrics"].get(first["field"]) or 0), reverse=reverse)
    limited = matches[:alert["delivery"]["resultLimit"]]
    signature = hashlib.sha256(json.dumps(
        [(candidate["key"], candidate["metrics"].get(first["field"])) for candidate in limited],
        separators=(",", ":"), sort_keys=True,
    ).encode()).hexdigest()
    return {"candidates": len(candidates), "matches": limited, "matchCount": len(matches),
            "signature": signature, "primaryValue": limited[0]["metrics"].get(first["field"]) if limited else None}


def market_alert_refinement_matches(alert, refinement):
    mode = alert.get("refinementMode", "exact")
    if mode == "any":
        return True
    if mode == "selected":
        return refinement in alert.get("refinements", [])
    if mode == "up-to":
        return refinement <= alert["refinement"]
    if mode == "above":
        return refinement >= alert["refinement"]
    return refinement == alert["refinement"]


def enqueue_market_alerts(snapshot_id):
    queued = 0
    now = datetime.now(timezone.utc).isoformat()
    with database() as db:
        prices = {
            (row["item_id"], row["refinement"]): dict(row)
            for row in db.execute(
                "SELECT item_id,item_name,refinement,lowest_price,captured_at FROM market_prices "
                "JOIN market_snapshots ON market_snapshots.id=market_prices.snapshot_id WHERE snapshot_id=?",
                (snapshot_id,),
            )
        }
        links = db.execute(
            "SELECT profile,discord_user_id,discord_guild_id,dm_opt_in FROM discord_links"
        ).fetchall()
        item_meta = {}
        for link in links:
            row = db.execute("SELECT state FROM users WHERE id=?", (link["profile"],)).fetchone()
            try:
                state = clean_state(json.loads(row["state"] if row else "{}"))
                alerts = state["marketAlerts"]
            except (ValueError, json.JSONDecodeError):
                continue
            for alert in alerts:
                if alert.get("schemaVersion") == 2:
                    destination = alert["delivery"]["destination"]
                    if not alert["enabled"] or destination == "dm" and not link["dm_opt_in"]:
                        continue
                    try:
                        result = evaluate_alert_rule(link["profile"], state, alert)
                    except (ValueError, OSError, sqlite3.Error):
                        continue
                    hit = result["matchCount"] > 0
                    previous = db.execute(
                        "SELECT hit,last_price,last_signature,last_sent_at FROM market_alert_state WHERE profile=? AND alert_id=?",
                        (link["profile"], alert["id"]),
                    ).fetchone()
                    repeat = alert["delivery"]["repeat"]
                    should_queue = hit and (not previous or not previous["hit"])
                    if hit and previous and previous["hit"]:
                        if repeat == "capture":
                            should_queue = True
                        elif repeat == "improve" and result["primaryValue"] is not None and previous["last_price"] is not None:
                            operator = alert["conditions"][0]["operator"]
                            should_queue = result["primaryValue"] < previous["last_price"] if operator in {"lt", "lte"} else result["primaryValue"] > previous["last_price"]
                        elif repeat == "cooldown" and previous["last_sent_at"]:
                            elapsed = datetime.now(timezone.utc) - datetime.fromisoformat(previous["last_sent_at"])
                            should_queue = elapsed >= timedelta(minutes=alert["delivery"]["cooldownMinutes"])
                    sent_at = previous["last_sent_at"] if previous else None
                    if should_queue:
                        payload = {
                            "type": "rule_alert", "profile": link["profile"], "alertId": alert["id"],
                            "alertName": alert["name"], "source": alert["source"], "destination": destination,
                            "language": alert["delivery"]["language"],
                            "discordGuildId": link["discord_guild_id"], "matchCount": result["matchCount"],
                            "results": [{"name": candidate["name"], "nameEn": candidate.get("nameEn", ""), "itemId": candidate["itemId"],
                                         "refinement": candidate["refinement"], "metrics": candidate["metrics"],
                                         "source": candidate.get("source"),
                                         "primaryField": alert["conditions"][0]["field"],
                                         "primaryValue": candidate["metrics"].get(alert["conditions"][0]["field"])}
                                        for candidate in result["matches"]],
                            "conditions": alert["conditions"],
                            "capturedAt": next((candidate.get("capturedAt") for candidate in result["matches"] if candidate.get("capturedAt")), now),
                        }
                        dedupe = f"rule:{link['profile']}:{alert['id']}:{snapshot_id}:{result['signature']}"
                        cursor = db.execute(
                            "INSERT OR IGNORE INTO discord_outbox(profile,discord_user_id,alert_id,dedupe_key,payload,created_at) VALUES(?,?,?,?,?,?)",
                            (link["profile"], link["discord_user_id"], alert["id"], dedupe,
                             json.dumps(payload, ensure_ascii=False, separators=(",", ":")), now),
                        )
                        queued += cursor.rowcount
                        if cursor.rowcount:
                            sent_at = now
                    db.execute(
                        "INSERT INTO market_alert_state(profile,alert_id,hit,last_price,updated_at,last_signature,last_sent_at) VALUES(?,?,?,?,?,?,?) "
                        "ON CONFLICT(profile,alert_id) DO UPDATE SET hit=excluded.hit,last_price=excluded.last_price,updated_at=excluded.updated_at,last_signature=excluded.last_signature,last_sent_at=excluded.last_sent_at",
                        (link["profile"], alert["id"], int(hit), result["primaryValue"], now, result["signature"], sent_at),
                    )
                    continue
                if not link["dm_opt_in"]:
                    continue
                matches = []
                if alert["kind"] == "material-unit":
                    price = material_unit_alert_price(alert)
                    matches = [price] if price else []
                else:
                    if alert["itemId"] not in item_meta:
                        item_meta.update(market_item_lookup([alert["itemId"]]))
                    meta = item_meta.get(alert["itemId"], {})
                    version_matches = not alert.get("prime") or alert["prime"] == ("prime" if meta.get("prime") else "normal")
                    matches = [row for (item_id, refinement), row in prices.items()
                               if version_matches and item_id == alert["itemId"]
                               and market_alert_refinement_matches(alert, refinement)]
                    price = min(matches, key=lambda row: row["lowest_price"]) if matches else None
                hit = bool(alert["enabled"] and price and price["lowest_price"] <= alert["targetPrice"])
                hit_matches = sorted((row for row in matches if row["lowest_price"] <= alert["targetPrice"]), key=lambda row: row["refinement"])
                previous = db.execute(
                    "SELECT hit,last_price FROM market_alert_state WHERE profile=? AND alert_id=?",
                    (link["profile"], alert["id"]),
                ).fetchone()
                should_queue = hit and (not previous or not previous["hit"] or price["lowest_price"] < previous["last_price"])
                if should_queue:
                    payload = {
                        "type": "market_alert", "profile": link["profile"], "alertId": alert["id"],
                        "itemId": alert["itemId"], "itemName": price["item_name"],
                        "refinement": alert["refinement"], "price": price["lowest_price"],
                        "prime": alert.get("prime", ""),
                        "matches": [{"refinement": row["refinement"], "price": row["lowest_price"]} for row in hit_matches],
                        "targetPrice": alert["targetPrice"], "capturedAt": price["captured_at"],
                    }
                    cursor = db.execute(
                        "INSERT OR IGNORE INTO discord_outbox(profile,discord_user_id,alert_id,dedupe_key,payload,created_at) "
                        "VALUES(?,?,?,?,?,?)",
                        (link["profile"], link["discord_user_id"], alert["id"],
                         f"market:{link['profile']}:{alert['id']}:{price['lowest_price']}",
                         json.dumps(payload, ensure_ascii=False, separators=(",", ":")), now),
                    )
                    queued += cursor.rowcount
                db.execute(
                    "INSERT INTO market_alert_state(profile,alert_id,hit,last_price,updated_at) VALUES(?,?,?,?,?) "
                    "ON CONFLICT(profile,alert_id) DO UPDATE SET hit=excluded.hit,last_price=excluded.last_price,updated_at=excluded.updated_at",
                    (link["profile"], alert["id"], int(hit), price["lowest_price"] if price else None, now),
                )
    return queued


def enqueue_market_alerts_async(snapshot_id):
    def worker():
        try:
            queued = enqueue_market_alerts(snapshot_id)
            print(
                f"market_alerts_completed snapshot_id={snapshot_id} queued={queued}",
                flush=True,
            )
        except Exception as error:
            print(
                f"market_alerts_failed snapshot_id={snapshot_id} "
                f"error_type={type(error).__name__}",
                flush=True,
            )

    threading.Thread(
        target=worker,
        name=f"market-alerts-{snapshot_id}",
        daemon=True,
    ).start()


def enqueue_discord_test_alert(profile):
    now = datetime.now(timezone.utc).isoformat()
    with database() as db:
        link = db.execute(
            "SELECT discord_user_id FROM discord_links WHERE profile=? AND dm_opt_in=1",
            (profile,),
        ).fetchone()
        if not link:
            raise ValueError("Profile sem Discord vinculado ou DM ativa.")
        payload = {
            "type": "test_alert", "profile": profile,
            "title": "Teste de alerta RF NEXT",
            "message": "A integração site → bot → DM está funcionando.",
            "createdAt": now,
        }
        cursor = db.execute(
            "INSERT INTO discord_outbox(profile,discord_user_id,alert_id,dedupe_key,payload,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (profile, link["discord_user_id"], "test", f"test:{profile}:{now}",
             json.dumps(payload, ensure_ascii=False, separators=(",", ":")), now),
        )
    return {"ok": True, "outboxId": cursor.lastrowid}


def enqueue_admin_discord_message(actor, profiles, message):
    actor = normalize_user(actor or "")
    message = str(message or "").strip()
    if not actor or not isinstance(profiles, list) or not 1 <= len(profiles) <= 100 or not 1 <= len(message) <= 1_800:
        raise ValueError("Mensagem administrativa inválida.")
    selected_values = {normalize_user(str(profile)) for profile in profiles}
    if None in selected_values:
        raise ValueError("Profile destinatário inválido.")
    selected = sorted(selected_values)
    now = datetime.now(timezone.utc).isoformat()
    queued = []
    with database() as db:
        links = {
            row["profile"]: row for row in db.execute(
                f"SELECT profile,discord_user_id FROM discord_links WHERE dm_opt_in=1 AND profile IN ({','.join('?' for _ in selected)})",
                selected,
            )
        }
        for profile in selected:
            link = links.get(profile)
            if not link:
                continue
            payload = {"type": "admin_message", "profile": profile, "message": message, "createdAt": now}
            db.execute(
                "INSERT INTO discord_outbox(profile,discord_user_id,alert_id,dedupe_key,payload,created_at) VALUES(?,?,?,?,?,?)",
                (profile, link["discord_user_id"], "admin-message", f"admin:{actor}:{profile}:{now}",
                 json.dumps(payload, ensure_ascii=False, separators=(",", ":")), now),
            )
            queued.append(profile)
    return {"ok": True, "queued": queued, "skipped": [profile for profile in selected if profile not in queued]}


def claim_discord_outbox(limit=50):
    limit = max(1, min(int(limit), 100))
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    with database() as db:
        db.execute(
            "UPDATE discord_outbox SET status='pending' WHERE status='sending' AND sent_at IS NULL AND created_at<?",
            (cutoff,),
        )
        rows = db.execute(
            "SELECT id,profile,discord_user_id,alert_id,payload FROM discord_outbox "
            "WHERE status='pending' ORDER BY id LIMIT ?", (limit,),
        ).fetchall()
        if rows:
            db.executemany("UPDATE discord_outbox SET status='sending' WHERE id=?", ((row["id"],) for row in rows))
    return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]


def ack_discord_outbox(outbox_id, status, error=""):
    if status not in {"sent", "failed"}:
        raise ValueError("Status de entrega inválido.")
    sent_at = datetime.now(timezone.utc).isoformat() if status == "sent" else None
    with database() as db:
        row = db.execute(
            "SELECT discord_user_id FROM discord_outbox WHERE id=? AND status='sending'",
            (int(outbox_id),),
        ).fetchone()
        changed = db.execute(
            "UPDATE discord_outbox SET status=?, sent_at=?, last_error=? WHERE id=? AND status='sending'",
            (status, sent_at, str(error)[:500], int(outbox_id)),
        ).rowcount
        if changed and sent_at:
            db.execute(
                "UPDATE discord_links SET last_delivery_at=? WHERE discord_user_id=?",
                (sent_at, row["discord_user_id"]),
            )
    if not changed:
        raise ValueError("Mensagem da outbox não encontrada ou já processada.")
    return {"ok": True, "id": int(outbox_id), "status": status}


def manage_profile(actor, profile, action):
    actor = normalize_user(actor or "")
    profile = normalize_user(profile or "")
    if not actor or not profile or action not in {"archive", "restore", "delete"}:
        raise ValueError("Ação de profile inválida.")
    if profile in {actor, LOCAL_USER}:
        raise PermissionError("O profile administrativo atual não pode ser alterado.")
    now = datetime.now(timezone.utc).isoformat()
    with database() as db:
        row = db.execute("SELECT archived_at FROM users WHERE id=?", (profile,)).fetchone()
        if not row:
            raise LookupError("Profile não encontrado.")
        if action == "archive":
            db.execute("UPDATE users SET archived_at=? WHERE id=?", (now, profile))
            db.execute(
                "UPDATE profile_tokens SET revoked_at=? WHERE profile=? AND revoked_at IS NULL",
                (now, profile),
            )
        elif action == "restore":
            db.execute("UPDATE users SET archived_at=NULL WHERE id=?", (profile,))
        else:
            for other in db.execute("SELECT id,state FROM users WHERE id<>?", (profile,)).fetchall():
                try:
                    state = json.loads(other["state"] or "{}")
                    shares = state.get("characterShares", {})
                    changed = False
                    for character, access in list(shares.items()):
                        recipients = access.get("recipients", []) if isinstance(access, dict) else []
                        clean = [recipient for recipient in recipients if str(recipient).casefold() != profile.casefold()]
                        if clean != recipients:
                            changed = True
                            if clean:
                                access["recipients"] = clean
                            else:
                                del shares[character]
                    if changed:
                        db.execute(
                            "UPDATE users SET state=? WHERE id=?",
                            (json.dumps(clean_state(state), ensure_ascii=False, separators=(",", ":")), other["id"]),
                        )
                except (ValueError, json.JSONDecodeError):
                    continue
            db.execute("DELETE FROM profile_tokens WHERE profile=?", (profile,))
            db.execute("DELETE FROM profile_imports WHERE profile=?", (profile,))
            db.execute("DELETE FROM users WHERE id=?", (profile,))
    return {"ok": True, "profile": profile, "action": action}


def farm_location_parts(value, map_name="", spot_name=""):
    map_name, spot_name = str(map_name or "").strip(), str(spot_name or "").strip()
    value = str(value or "").strip()
    if not map_name and not spot_name:
        parts = [part.strip() for part in re.split(r"\s+(?:\+|—)\s+|\s+-\s+", value) if part.strip()]
        if len(parts) >= 2:
            map_name, spot_name = parts[:2]
        else:
            map_name = value
    if map_name and spot_name and normalize_search(spot_name).startswith(normalize_search(map_name)):
        spot_name = spot_name[len(map_name):].strip(" -–—+")
    label = " — ".join(part for part in (map_name, spot_name) if part) or value or "Não informado"
    return map_name[:80], spot_name[:80], label[:160]


def farm_mob_list(report):
    raw = report.get("mob_list") or report.get("mobs") or []
    if isinstance(raw, str):
        raw = [name.strip() for name in raw.split(",") if name.strip()]
    if not isinstance(raw, list) or len(raw) > 100:
        raise ValueError("Lista de mobs inválida.")
    levels = report.get("mob_levels") if isinstance(report.get("mob_levels"), dict) else {}
    result, seen = [], set()
    for value in raw:
        source = value if isinstance(value, dict) else {"name": value}
        name = str(source.get("name") or source.get("mob") or "").strip()
        if not 1 <= len(name) <= 80:
            continue
        level = source.get("level", levels.get(name, report.get("mob_level")))
        try:
            level = int(level) if level not in (None, "") else None
        except (TypeError, ValueError):
            level = None
        key = (normalize_search(name), level)
        if key in seen:
            continue
        seen.add(key)
        result.append({
            "name": name,
            "level": level,
            **({"npcId": str(source.get("npcId") or source.get("npc_id") or source.get("id"))}
               if source.get("npcId") or source.get("npc_id") or source.get("id") else {}),
        })
    return result


def farm_loot_list(raw):
    if not isinstance(raw, list) or len(raw) > 5_000:
        raise ValueError("Lista de loot inválida.")
    item_ids = [
        str(item.get("itemIndex") or item.get("item_index") or "")
        for item in raw if isinstance(item, dict)
    ]
    grades = {}
    if item_ids and GAME_DB_PATH.is_file():
        placeholders = ",".join("?" for _ in item_ids)
        with game_database() as db:
            grades = {
                str(row["id"]): int(row["grade"])
                for row in db.execute(
                    f"SELECT id,grade FROM item_details WHERE id IN ({placeholders})", item_ids
                )
            }
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("itemIndex") or item.get("item_index") or "").strip()
        name = str(item.get("name") or item.get("item") or item.get("nome") or (f"Item {item_id}" if item_id else "Item")).strip()[:160]
        try:
            quantity = int(item.get("quantity") or item.get("count") or 0)
            rarity = int(item.get("rarity") or item.get("grade") or grades.get(item_id) or 0)
        except (TypeError, ValueError):
            raise ValueError("Item de loot inválido.") from None
        if quantity < 1 or quantity > 1_000_000_000 or rarity not in range(7):
            raise ValueError("Item de loot inválido.")
        result.append({"itemIndex": item_id, "name": name, "quantity": quantity, "rarity": rarity or None})
    return result


def farm_rarity_counts(loot):
    return {str(rarity): sum(item["quantity"] for item in loot if item.get("rarity") == rarity) for rarity in range(1, 7)}


def farm_record_id(character_uid, character, report, started_at, ended_at):
    supplied = str(report.get("subsession_id") or report.get("farm_id") or "").strip()
    if re.fullmatch(r"[A-Fa-f0-9]{24,64}", supplied):
        return supplied.lower()
    identity = json.dumps(
        [str(character_uid or character), str(report.get("id") or report.get("name") or ""), started_at, ended_at],
        ensure_ascii=False, separators=(",", ":"),
    )
    return hashlib.sha256(identity.encode()).hexdigest()


def import_farm_session(profile, payload, idempotency_key):
    if not re.fullmatch(r"[A-Fa-f0-9]{64}", idempotency_key or ""):
        raise ValueError("Chave de idempotência inválida.")
    metadata = payload.get("metadata") if isinstance(payload, dict) else None
    profiles = payload.get("profiles") if isinstance(payload, dict) else None
    reports = payload.get("subsession_reports") if isinstance(payload, dict) else None
    if (
        not isinstance(metadata, dict)
        or not isinstance(profiles, list)
        or not isinstance(reports, list)
        or len(profiles) != 1
        or not isinstance(profiles[0], dict)
        or len(reports) > 500
    ):
        raise ValueError("Sessão de farm inválida.")
    requested = str(profiles[0].get("profile") or metadata.get("profile") or "")
    if requested.casefold() != profile.casefold():
        raise PermissionError("O arquivo pertence a outro Profile.")
    validate_capture_license(payload)
    marks_mode = str(metadata.get("marks_mode") or "replace")
    if marks_mode not in {"replace", "merge"}:
        raise ValueError("Modo de atualização do Codex inválido.")
    character = str(
        profiles[0].get("name") or metadata.get("character_name") or ""
    ).strip()
    if not 1 <= len(character) <= 80:
        raise ValueError("Personagem inválido.")
    marks_received = "marks" in profiles[0] or "codex_marks" in metadata
    collection_types = profiles[0].get("collection_types") or metadata.get("collection_types") or ()
    raw_marks = profiles[0].get("marks") if "marks" in profiles[0] else metadata.get("codex_marks", {})
    active_collections = [str(collection_id) for collection_id in raw_marks] if isinstance(raw_marks, dict) else []
    marks = clean_state({"codex": {character: raw_marks or {}}})["codex"][character]
    capture = payload.get("capture") if isinstance(payload.get("capture"), dict) else {}
    capture_loadout = capture.get("loadout") or {
        "biosuit": capture.get("biosuit_item_index"),
        "rover": capture.get("rover_item_index"),
        "equipment": capture.get("equipment") or [],
    }
    loadout = clean_character_loadout(
        profiles[0].get("loadout") or payload.get("loadout") or capture_loadout
    )
    character_uid = str(profiles[0].get("character_uid") or "").strip()
    if character_uid and (not character_uid.isdigit() or len(character_uid) > 20):
        raise ValueError("UID do personagem inválido.")
    class_name = str(
        profiles[0].get("className")
        or profiles[0].get("class_name")
        or capture.get("character_class")
        or ""
    ).strip()[:40]
    biosuit = loadout.get("biosuit")
    if biosuit:
        class_name = str(
            character_loadout_catalog()["items"].get(biosuit["itemIndex"], {}).get("className")
            or class_name
        )[:40]
    raw_cp = profiles[0].get("cp", profiles[0].get("combat_power", capture.get("combat_power")))
    try:
        character_cp = int(raw_cp) if raw_cp not in (None, "") else None
    except (TypeError, ValueError):
        raise ValueError("CP do personagem inválido.") from None
    if character_cp is not None and character_cp < 0:
        raise ValueError("CP do personagem inválido.")
    rover_item = loadout.get("rover")
    rover = None
    if rover_item:
        rover_catalog = character_loadout_catalog()["items"].get(rover_item["itemIndex"], {})
        rover = {
            "itemIndex": rover_item["itemIndex"],
            "name": str(rover_catalog.get("name") or rover_item.get("name") or f"Rover #{rover_item['itemIndex']}")[:80],
        }
    records = []
    level = capture.get("level") if isinstance(capture.get("level"), int) else None
    for index, report in enumerate(reports):
        summary = report.get("summary") if isinstance(report, dict) else None
        if not isinstance(summary, dict):
            raise ValueError("Subsessão inválida.")
        duration = int(report.get("duration_seconds") or 0)
        if not 1 <= duration <= 31_536_000:
            raise ValueError("Duração da subsessão inválida.")
        level = summary.get("level") if isinstance(summary.get("level"), int) else level
        started_at = int(report.get("started_ns") or 0) // 1_000_000
        created_at = started_at or int(datetime.now(timezone.utc).timestamp() * 1000) + index
        ended_at = int(report.get("ended_ns") or 0) // 1_000_000 or created_at + duration * 1_000
        exp = float(summary.get("exp_gained") or 0)
        credits = float(summary.get("credits") or 0)
        contribution = float(summary.get("contribution") or 0)
        if not all(map(math.isfinite, (exp, credits, contribution))) or min(exp, credits, contribution) < 0:
            raise ValueError("Totais da subsessão inválidos.")
        hours = duration / 3600
        location_map, location_spot, location = farm_location_parts(
            report.get("location"), report.get("location_map"), report.get("location_spot")
        )
        mobs = farm_mob_list(report)
        primary_mob = mobs[0] if mobs else {"name": "Não informado", "level": None}
        loot = farm_loot_list(summary.get("loot") or [])
        rarity_counts = farm_rarity_counts(loot)
        xp_percent = summary.get("exp_percent_total", summary.get("exp_percent"))
        xp_percent_hour = summary.get("exp_percent_per_hour")
        try:
            xp_percent = float(xp_percent) if xp_percent not in (None, "") else None
            xp_percent_hour = float(xp_percent_hour) if xp_percent_hour not in (None, "") else None
        except (TypeError, ValueError):
            raise ValueError("Percentual de EXP inválido.") from None
        if any(value is not None and (not math.isfinite(value) or value < 0) for value in (xp_percent, xp_percent_hour)):
            raise ValueError("Percentual de EXP inválido.")
        farm_id = farm_record_id(character_uid, character, report, created_at, ended_at)
        records.append({
            "id": created_at,
            "date": datetime.fromtimestamp(created_at / 1000).astimezone().strftime("%d/%m"),
            "createdAt": created_at,
            "startedAt": created_at,
            "endedAt": ended_at,
            "subsessionName": str(report.get("name") or report.get("id") or f"Subsessão {index + 1}")[:80],
            "farmId": farm_id,
            "source": "rf-next-info",
            "sourceReportId": farm_id,
            "sourceCharacterId": str(character_uid or character),
            "minutes": duration / 60,
            "timeFormatted": str(report.get("duration_hms") or f"{duration // 60} min")[:20],
            "xp": xp_percent,
            "credits": credits,
            "factionPoints": contribution,
            "purpleItems": rarity_counts["4"],
            "diamonds": 0,
            "mauUsed": False,
            "mauMinutes": 0,
            "launcherUsed": False,
            "launcherMinutes": 0,
            "expPotionUsed": False,
            "expPotionQuantity": 0,
            "expPotionPercent": 0,
            "character": character,
            "characterClass": class_name,
            "rover": rover,
            "characterLevel": level,
            "characterCp": character_cp,
            "location": location,
            "locationMap": location_map,
            "locationSpot": location_spot,
            "mobs": mobs,
            "mob": primary_mob["name"],
            "mobLevel": primary_mob["level"],
            "loot": "Com loot" if loot else "Sem loot",
            "lootDetails": loot,
            "rarityCounts": rarity_counts,
            **{f"rarity{rarity}": rarity_counts[str(rarity)] for rarity in range(1, 7)},
            "xpHour": xp_percent_hour,
            "creditsHour": round(credits / hours) if hours else 0,
            "factionPointsHour": round(contribution / hours) if hours else 0,
            "estimatedMobs": int(summary.get("kills") or 0),
            "grossXp": exp,
            "grossXpHour": round(exp / hours) if hours else 0,
            "mobEstimateByCredits": None,
            "mobEstimateByFaction": None,
        })
    with database() as db:
        if db.execute(
            """SELECT 1 FROM profile_imports
               WHERE profile=? AND idempotency_key=?""",
            (profile, idempotency_key),
        ).fetchone():
            return {"ok": True, "duplicate": True, "records": 0}
        row = db.execute(
            "SELECT share,state FROM users WHERE id=?", (profile,)
        ).fetchone()
        share, raw_state = (row["share"], row["state"]) if row else (0, "{}")
        state = clean_state(json.loads(raw_state or "{}"))
        by_uid = character_uid and next(
            (
                item for item in state["characters"]
                if str(item.get("characterUid") or "") == character_uid
            ),
            None,
        )
        by_name = next(
            (
                item for item in state["characters"]
                if str(item.get("name", "")).casefold() == character.casefold()
            ),
            None,
        )
        if (
            (by_uid and by_name and by_uid is not by_name)
            or (
                by_name
                and by_name.get("characterUid")
                and character_uid
                and str(by_name["characterUid"]) != character_uid
            )
        ):
            raise ValueError(
                f"O nome e o UID de {character} pertencem a personagens diferentes."
            )
        existing = by_uid or by_name
        if not existing and not character_uid:
            raise ValueError(
                f"{character} não está cadastrado e o arquivo não possui o UID do personagem."
            )
        if existing and character != existing["name"]:
            character = existing["name"]
            for item in records:
                item["character"] = character
        for record in records:
            for mob in record["mobs"]:
                linked = next((candidate for candidate in state["mobDatabase"] if
                    normalize_search(farm_location_parts(candidate.get("location"))[2]) == normalize_search(record["location"])
                    and normalize_search(candidate.get("mob")) == normalize_search(mob["name"])
                    and candidate.get("level") == mob.get("level")
                ), None)
                if linked is not None:
                    mob["databaseId"] = linked.get("id")
        known_ids = {
            str(item.get("farmId")) for item in state["history"]
            if isinstance(item, dict) and item.get("farmId")
        }
        known = {
            (item.get("sourceReportId"), item.get("sourceCharacterId"))
            for item in state["history"]
            if isinstance(item, dict)
        }
        fresh = [
            item
            for item in records
            if item["farmId"] not in known_ids
            and (item["sourceReportId"], item["sourceCharacterId"]) not in known
        ]
        state["history"] = fresh + state["history"]
        received_at = datetime.now(timezone.utc).isoformat()
        if metadata.get("capture_mode") not in {"codex", "memory_chips"}:
            state["captureReceipts"]["character"] = received_at
        if marks_received:
            for key in codex_receipt_keys(marks, collection_types):
                state["captureReceipts"][key] = received_at
        if marks_mode == "merge":
            state["codex"][character] = {
                **state["codex"].get(character, {}),
                **marks,
            }
        else:
            state["codex"][character] = marks
        if marks_received:
            previous_snapshot = state["codexSnapshots"].get(character, {})
            snapshot_collections = set(previous_snapshot.get("collections", [])) if marks_mode == "merge" else set()
            snapshot_marks = dict(previous_snapshot.get("marks", {})) if marks_mode == "merge" else {}
            refreshed_types = {int(value) for value in collection_types if str(value).isdigit()}
            if refreshed_types:
                memory_ids = {str(chip["id"]) for chip in memory_chip_data()["chips"]}
                snapshot_collections = {
                    collection_id for collection_id in snapshot_collections
                    if (2 if collection_id in memory_ids else 1) not in refreshed_types
                }
                snapshot_marks = {
                    collection_id: slots for collection_id, slots in snapshot_marks.items()
                    if (2 if collection_id in memory_ids else 1) not in refreshed_types
                }
            snapshot_collections.update(active_collections)
            snapshot_marks.update(marks)
            state["codexSnapshots"][character] = {
                "capturedAt": received_at,
                "collections": sorted(snapshot_collections, key=int),
                "marks": snapshot_marks,
            }
        if existing:
            if level:
                existing["level"] = level
            if class_name:
                existing["className"] = class_name
            if character_cp is not None:
                existing["cp"] = character_cp
            if character_uid:
                existing["characterUid"] = character_uid
            if loadout:
                existing["loadout"] = merge_character_loadout(existing.get("loadout"), loadout)
        elif not existing:
            state["characters"].append(
                {
                    "name": character,
                    "className": class_name,
                    "level": level,
                    "cp": character_cp,
                    **({"characterUid": character_uid} if character_uid else {}),
                    **({"loadout": loadout} if loadout else {}),
                }
            )
        state = clean_state(state)
        db.execute(
            """INSERT INTO users(id,share,state) VALUES(?,?,?)
               ON CONFLICT(id) DO UPDATE SET state=excluded.state""",
            (profile, share, json.dumps(state, ensure_ascii=False, separators=(",", ":"))),
        )
        db.execute(
            """INSERT INTO profile_imports(profile,idempotency_key,imported_at)
               VALUES(?,?,?)""",
            (profile, idempotency_key, received_at),
        )
    return {"ok": True, "duplicate": False, "records": len(fresh)}


class Handler(SimpleHTTPRequestHandler):
    def actor_identity(self):
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

    def selected_admin_profile(self, actor):
        if not is_admin_user(actor):
            return None
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except CookieError:
            return None
        selected = cookie.get(ADMIN_PROFILE_COOKIE)
        profile = normalize_user(selected.value) if selected else None
        if not profile or profile == LOCAL_USER:
            return None
        with database() as db:
            return profile if db.execute(
                "SELECT 1 FROM users WHERE id=? AND archived_at IS NULL", (profile,)
            ).fetchone() else None

    def identity(self):
        actor = self.actor_identity()
        return self.selected_admin_profile(actor) or actor

    def profile_cookie(self, profile=None):
        value = profile or ""
        max_age = 28_800 if profile else 0
        cookie = f"{ADMIN_PROFILE_COOKIE}={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}"
        if self.headers.get("X-Forwarded-Proto", "").lower() == "https":
            cookie += "; Secure"
        return cookie

    def send_json(self, status, payload, headers=None):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def require_identity(self):
        user = self.identity()
        if not user:
            self.send_json(401, {"error": "Entre pelo Cloudflare Access para usar o aplicativo."})
        return user

    def bearer_profile(self):
        authorization = self.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return None
        return profile_for_token(authorization[7:].strip())

    def require_discord_bridge(self):
        if len(DISCORD_BRIDGE_SECRET) < 32:
            self.send_json(503, {"error": "Ponte Discord não configurada."})
            return False
        authorization = self.headers.get("Authorization", "")
        if not authorization.startswith("Bearer ") or not secrets.compare_digest(
            authorization[7:].strip(), DISCORD_BRIDGE_SECRET
        ):
            self.send_json(401, {"error": "Ponte Discord não autorizada."})
            return False
        return True

    def require_admin(self):
        actor = self.actor_identity()
        if not actor:
            self.send_json(401, {"error": "Autenticação necessária."})
            return None
        if not is_admin_user(actor):
            self.send_json(403, {"error": "Acesso exclusivo do administrador."})
            return None
        return actor

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

    def send_game_icon(self, encoded_name):
        name = unquote(encoded_name)
        if Path(name).name != name or not re.fullmatch(r"[\w .()\-]+\.(?:png|jpe?g|webp|gif|avif)", name, re.IGNORECASE):
            return self.send_json(404, {"error": "Ícone não encontrado."})
        target = GAME_ICON_ROOT / name
        if not target.is_file():
            return self.send_json(404, {"error": "Ícone não encontrado."})
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
        if path == "/account/switch":
            self.send_response(302)
            self.send_header("Location", ACCOUNT_SWITCH_URL)
            self.send_header("Set-Cookie", self.profile_cookie())
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return

        if path.startswith("/market-images/"):
            if not self.require_identity():
                return
            return self.send_market_image(path.removeprefix("/market-images/"))

        if path.startswith("/game-icons/"):
            if not self.require_identity():
                return
            return self.send_game_icon(path.removeprefix("/game-icons/"))

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

        if path == "/api/market/export":
            if not self.require_identity():
                return
            try:
                exported = latest_market_csv()
                if not exported:
                    return self.send_json(404, {"error": "Nenhuma captura do Mercado disponível."})
                body, captured_at = exported
                stamp = re.sub(r"\D", "", captured_at)[:14]
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="rfnext-market-{stamp}.csv"')
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            except (OSError, sqlite3.Error):
                return self.send_json(503, {"error": "Exportação do Mercado indisponível."})

        if path == "/api/salvage/materials":
            if not self.require_identity():
                return
            try:
                return self.send_json(200, {"materials": salvage_material_options()})
            except (OSError, sqlite3.Error):
                return self.send_json(503, {"error": "Materiais de salvage indisponíveis."})

        if path == "/api/salvage/upgrade":
            if not self.require_identity():
                return
            params = parse_qs(request_url.query)
            try:
                return self.send_json(200, salvage_upgrade_compare(
                    params.get("itemId", [""])[0], params.get("materialId", [""])[0],
                    params.get("materialEnchant", ["0"])[0], params.get("target", ["1"])[0],
                    params.get("upgraderPrice", [None])[0],
                ))
            except (ValueError, TypeError):
                return self.send_json(400, {"error": "Comparação de refino indisponível para esta combinação."})
            except (OSError, sqlite3.Error):
                return self.send_json(503, {"error": "Dados de refino indisponíveis."})

        if path == "/api/salvage":
            if not self.require_identity():
                return
            params = parse_qs(request_url.query)
            try:
                mode = params.get("mode", ["source"])[0]
                if mode not in {"source", "material"}:
                    raise ValueError("Modo de salvage inválido")
                arguments = (
                    params.get("q", [""])[0],
                    params.get("tier", [None])[0],
                    params.get("grade", [None])[0],
                    params.get("enchant", [None])[0],
                    params.get("status", ["all"])[0],
                    params.get("sort", ["cost" if mode == "material" else "profit"])[0],
                    params.get("limit", ["40"])[0],
                    params.get("offset", ["0"])[0],
                )
                if mode == "material":
                    return self.send_json(200, salvage_material_data(
                        *arguments, target_quantity=params.get("targetQuantity", [None])[0],
                        prime=params.get("prime", [""])[0]
                    ))
                return self.send_json(200, salvage_data(*arguments, prime=params.get("prime", [""])[0]))
            except (ValueError, TypeError):
                return self.send_json(400, {"error": "Consulta de salvage inválida."})
            except (OSError, sqlite3.Error):
                return self.send_json(503, {"error": "Dados de salvage indisponíveis."})

        if path.startswith("/api/craft/"):
            if not self.require_identity():
                return
            try:
                if path == "/api/craft/summary":
                    return self.send_json(200, craft_summary())
                params = parse_qs(request_url.query)
                if path == "/api/craft/tri-plates":
                    return self.send_json(200, tri_plate_data(
                        params.get("quantity", ["1"])[0], params.get("target", ["stable"])[0]
                    ))
                if path == "/api/craft/search":
                    return self.send_json(200, craft_search(params.get("q", [""])[0], params.get("category", [""])[0],
                                                            params.get("subcategory", [""])[0], params.get("limit", ["60"])[0],
                                                            params.get("events", ["1"])[0] != "0",
                                                            params.get("excludeCategory", []), params.get("grade", [None])[0],
                                                            params.get("completeMarket", ["0"])[0] == "1"))
                if path == "/api/craft/materials":
                    return self.send_json(200, craft_material_search(
                        params.get("q", [""])[0], params.get("limit", ["30"])[0]
                    ))
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
                    return self.send_json(200, game_search(
                        params.get("q", [""])[0],
                        params.get("type", [""])[0],
                        params.get("limit", ["50"])[0],
                        params.get("offset", ["0"])[0],
                        parse_market_optional_integer(params.get("grade", [""])[0]),
                        parse_market_optional_integer(params.get("tier", [""])[0]),
                        parse_market_optional_integer(params.get("useLevelMin", [""])[0]),
                        parse_market_optional_integer(params.get("useLevelMax", [""])[0]),
                        params.get("category", [""])[0],
                        params.get("subcategory", [""])[0],
                    ))
                if path == "/api/game-data/detail":
                    detail = game_detail(params.get("type", [""])[0], params.get("id", [""])[0])
                    return self.send_json(200, detail) if detail else self.send_json(404, {"error": "Registro não encontrado."})
            except (ValueError, TypeError):
                return self.send_json(400, {"error": "Consulta inválida."})
            except (OSError, sqlite3.Error):
                return self.send_json(503, {"error": "Banco extraído indisponível."})
            return self.send_json(404, {"error": "Rota não encontrada."})

        if path.startswith("/api/equipment/"):
            if not self.require_identity():
                return
            try:
                params = parse_qs(request_url.query)
                if path == "/api/equipment/search":
                    return self.send_json(200, equipment_search(
                        params.get("q", [""])[0], params.get("limit", ["50"])[0],
                        params.get("equipmentType", [""])[0],
                        parse_market_optional_integer(params.get("slot", [""])[0]),
                        params.get("grade", [""])[0],
                        parse_market_optional_integer(params.get("tier", [""])[0]),
                        params.get("prime", [""])[0],
                        parse_market_optional_integer(params.get("biosuitType", [""])[0]),
                    ))
                if path == "/api/equipment/detail":
                    detail = equipment_detail(params.get("id", [""])[0])
                    return self.send_json(200, detail) if detail else self.send_json(404, {"error": "Equipamento não encontrado."})
            except (ValueError, TypeError):
                return self.send_json(400, {"error": "Consulta inválida."})
            except (OSError, sqlite3.Error, json.JSONDecodeError):
                return self.send_json(503, {"error": "Comparador de equipamentos indisponível."})
            return self.send_json(404, {"error": "Rota não encontrada."})

        if path == "/api/character-loadout":
            if not self.require_identity():
                return
            catalog = character_loadout_catalog()
            return self.send_json(200, catalog) if catalog["items"] else self.send_json(
                503, {"error": "Catálogo de Biosuits e Rovers indisponível."}
            )

        if path == "/api/memory-chips":
            if not self.require_identity():
                return
            try:
                return self.send_json(200, memory_chip_data())
            except (OSError, ValueError):
                return self.send_json(503, {"error": "Catálogo de Memory Chips indisponível."})

        if path == "/api/codex":
            if not self.require_identity():
                return
            try:
                return self.send_json(200, codex_data())
            except (OSError, sqlite3.Error):
                return self.send_json(503, {"error": "Catálogo de coleções indisponível."})

        if path == "/api/discord/status":
            profile = self.require_identity()
            if not profile:
                return
            with database() as db:
                row = db.execute(
                    "SELECT discord_user_id,discord_guild_id,dm_opt_in,linked_at,last_delivery_at "
                    "FROM discord_links WHERE profile=?", (profile,)
                ).fetchone()
            return self.send_json(200, {
                "linked": bool(row),
                "discordUserId": row["discord_user_id"] if row else None,
                "discordGuildId": row["discord_guild_id"] if row else None,
                "dmOptIn": bool(row["dm_opt_in"]) if row else False,
                "linkedAt": row["linked_at"] if row else None,
                "lastDeliveryAt": row["last_delivery_at"] if row else None,
            })

        if path == "/api/alerts/history":
            profile = self.require_identity()
            if not profile:
                return
            with database() as db:
                rows = db.execute(
                    "SELECT id,alert_id,payload,status,created_at,sent_at,last_error FROM discord_outbox "
                    "WHERE profile=? ORDER BY id DESC LIMIT 100", (profile,),
                ).fetchall()
            return self.send_json(200, {"events": [
                {"id": row["id"], "alertId": row["alert_id"], "payload": json.loads(row["payload"]),
                 "status": row["status"], "createdAt": row["created_at"], "sentAt": row["sent_at"],
                 "error": row["last_error"] or ""} for row in rows
            ]})

        if path == "/api/admin/alerts":
            if not self.require_admin():
                return
            with database() as db:
                totals = {row["status"]: row["count"] for row in db.execute(
                    "SELECT status,COUNT(*) count FROM discord_outbox GROUP BY status"
                )}
                recent = [dict(row) for row in db.execute(
                    "SELECT profile,alert_id,status,created_at,sent_at,last_error FROM discord_outbox ORDER BY id DESC LIMIT 50"
                )]
                profiles = [dict(row) for row in db.execute(
                    "SELECT profile,dm_opt_in FROM discord_links ORDER BY profile COLLATE NOCASE"
                )]
                linked = db.execute("SELECT COUNT(*) FROM discord_links").fetchone()[0]
                opted = db.execute("SELECT COUNT(*) FROM discord_links WHERE dm_opt_in=1").fetchone()[0]
            return self.send_json(200, {"totals": totals, "linkedProfiles": linked, "dmOptIns": opted, "profiles": profiles, "recent": recent})

        if path == "/api/state":
            user = self.require_identity()
            if not user:
                return
            actor = self.actor_identity()
            with database() as db:
                row = db.execute("SELECT share, state FROM users WHERE id = ?", (user,)).fetchone()
                if not row:
                    db.execute("INSERT INTO users(id) VALUES (?)", (user,))
                    row = (0, "{}")
                market_receipt = db.execute(
                    "SELECT profile, imported_at FROM market_snapshots WHERE profile IS NOT NULL "
                    "ORDER BY datetime(imported_at) DESC, id DESC LIMIT 1"
                ).fetchone()
            state = clean_state(json.loads(row[1] or "{}"))
            return self.send_json(200, {
                "user": user.split("@", 1)[0],
                "actor": actor.split("@", 1)[0],
                "admin": is_admin_user(actor),
                "share": bool(row[0]),
                "marketReceipt": {
                    "profile": market_receipt["profile"],
                    "receivedAt": market_receipt["imported_at"],
                } if market_receipt else None,
                **state,
            })

        if path == "/api/admin/profiles":
            actor = self.require_admin()
            if not actor:
                return
            with database() as db:
                profiles = [
                    {"id": row["id"], "archived": bool(row["archived_at"])}
                    for row in db.execute("SELECT id,archived_at FROM users ORDER BY id")
                    if row["id"] != LOCAL_USER
                ]
            return self.send_json(200, {
                "actor": actor,
                "active": self.identity(),
                "profiles": profiles,
            })

        if path == "/api/profiles":
            user = self.require_identity()
            if not user:
                return
            with database() as db:
                profiles = [
                    row["id"] for row in db.execute(
                        "SELECT id FROM users WHERE archived_at IS NULL ORDER BY id"
                    )
                    if row["id"] != user and row["id"] != LOCAL_USER and normalize_user(row["id"])
                ]
            return self.send_json(200, {"profiles": profiles})

        if path == "/api/characters/shared":
            user = self.require_identity()
            if not user:
                return
            with database() as db:
                rows = db.execute("SELECT id, state FROM users").fetchall()
            return self.send_json(200, {"characters": shared_character_views(user, rows)})

        if path == "/api/history/general":
            profile = self.require_identity()
            if not profile:
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
                for item in state["history"]:
                    if not isinstance(item, dict):
                        continue
                    public = {key: value for key, value in item.items() if key not in {
                        "farmId", "sourceReportId", "sourceCharacterId", "lootDetails", "items"
                    }}
                    records.append({**public, "owner": owner})
            records.sort(key=lambda item: item.get("createdAt") or item.get("id") or 0, reverse=True)
            return self.send_json(200, {"history": records})

        if path.startswith("/api/"):
            return self.send_json(404, {"error": "Rota não encontrada."})
        self.path = path if path in {
            "/karvalho-logo.png",
            "/karvalho-primary-gold.png",
            "/rf-next-qol-logo.png",
            "/market-template.csv",
            "/fonts/Saira.ttf",
            "/fonts/SairaSemiCondensed-Bold.ttf",
        } else "/index.html"
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
            if any(alert.get("schemaVersion") == 2 and alert["delivery"]["destination"] == "channel" for alert in state["marketAlerts"]):
                if not is_admin_user(self.actor_identity()):
                    raise PermissionError("Somente administradores podem publicar alertas no canal.")
            share = 1 if payload.get("share") is True else 0
        except PermissionError as error:
            return self.send_json(403, {"error": str(error)})
        except (ValueError, json.JSONDecodeError):
            return self.send_json(400, {"error": "Dados inválidos."})
        with database() as db:
            current = db.execute("SELECT state FROM users WHERE id=?", (user,)).fetchone()
            if current:
                state = preserve_newer_character_capture(clean_state(json.loads(current["state"] or "{}")), state)
            db.execute(
                "INSERT INTO users(id, share, state) VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET share=excluded.share, state=excluded.state",
                (user, share, json.dumps(state, ensure_ascii=False, separators=(",", ":"))),
            )
        return self.send_json(200, {"ok": True})

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        if path == "/api/alerts/preview":
            profile = self.require_identity()
            if not profile:
                return
            try:
                alert = clean_alert_rule(self.read_json())
                if alert["delivery"]["destination"] == "channel" and not is_admin_user(self.actor_identity()):
                    raise PermissionError("Somente administradores podem publicar alertas no canal.")
                with database() as db:
                    row = db.execute("SELECT state FROM users WHERE id=?", (profile,)).fetchone()
                state = clean_state(json.loads(row["state"] if row else "{}"))
                result = evaluate_alert_rule(profile, state, alert)
                return self.send_json(200, {
                    "candidates": result["candidates"], "matchCount": result["matchCount"],
                    "matches": result["matches"],
                })
            except PermissionError as error:
                return self.send_json(403, {"error": str(error)})
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                return self.send_json(400, {"error": str(error)})
            except (OSError, sqlite3.Error):
                return self.send_json(503, {"error": "Não foi possível avaliar o alerta."})

        if path == "/api/discord/link-token":
            profile = self.require_identity()
            if not profile:
                return
            return self.send_json(200, {"token": create_discord_link_token(profile), "expiresIn": 600})

        if path == "/api/admin/discord-message":
            if not self.require_admin():
                return
            try:
                payload = self.read_json()
                return self.send_json(200, enqueue_admin_discord_message(
                    self.actor_identity(), payload.get("profiles"), payload.get("message")
                ))
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                return self.send_json(400, {"error": str(error)})

        if path == "/api/discord/link":
            if not self.require_discord_bridge():
                return
            try:
                payload = self.read_json()
                result = link_discord_user(
                    payload.get("token"), payload.get("discordUserId"), payload.get("discordGuildId")
                )
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                return self.send_json(400, {"error": str(error)})
            return self.send_json(200, {"ok": True, **result})

        if path == "/api/discord/opt-in":
            if not self.require_discord_bridge():
                return
            try:
                payload = self.read_json()
                result = set_discord_opt_in(payload.get("discordUserId"), payload.get("enabled") is True)
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                return self.send_json(400, {"error": str(error)})
            return self.send_json(200, {"ok": True, **result})

        if path == "/api/discord/outbox":
            if not self.require_discord_bridge():
                return
            try:
                payload = self.read_json() if int(self.headers.get("Content-Length", 0)) else {}
                messages = claim_discord_outbox(payload.get("limit", 50))
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                return self.send_json(400, {"error": str(error)})
            return self.send_json(200, {"messages": messages})

        if path == "/api/discord/outbox/ack":
            if not self.require_discord_bridge():
                return
            try:
                payload = self.read_json()
                result = ack_discord_outbox(payload.get("id"), payload.get("status"), payload.get("error", ""))
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                return self.send_json(400, {"error": str(error)})
            return self.send_json(200, result)

        if path == "/api/craft/personal/analyze":
            if not self.require_identity():
                return
            try:
                return self.send_json(200, personal_craft_analysis(self.read_json()))
            except (ValueError, TypeError) as error:
                return self.send_json(400, {"error": str(error)})
            except (OSError, sqlite3.Error):
                return self.send_json(503, {"error": "Dados do Craft Pessoal indisponíveis."})

        if path == "/api/profile-token":
            profile = self.require_identity()
            if not profile:
                return
            token = create_profile_token(profile)
            return self.send_json(
                200,
                {
                    "ok": True,
                    "profile": profile,
                    "token": token,
                    "warning": "Copie agora. O token não será exibido novamente.",
                },
            )

        if path == "/api/profile-token/revoke":
            profile = self.require_identity()
            if not profile:
                return
            with database() as db:
                changed = db.execute(
                    """UPDATE profile_tokens
                       SET revoked_at=? WHERE profile=? AND revoked_at IS NULL""",
                    (datetime.now(timezone.utc).isoformat(), profile),
                ).rowcount
            return self.send_json(200, {"ok": True, "revoked": changed})

        if path == "/api/profile-token/validate":
            profile = self.bearer_profile()
            if not profile:
                return self.send_json(401, {"error": "Token inválido ou revogado."})
            try:
                requested = str(self.read_json().get("profile") or "")
            except (ValueError, json.JSONDecodeError):
                return self.send_json(400, {"error": "Profile inválido."})
            if requested.casefold() != profile.casefold():
                return self.send_json(403, {"error": "O token pertence a outro Profile."})
            return self.send_json(200, {"ok": True, "profile": profile})

        if path == "/api/import/farm-session":
            profile = self.bearer_profile()
            if not profile:
                return self.send_json(401, {"error": "Token inválido ou revogado."})
            try:
                result = import_farm_session(
                    profile,
                    self.read_json(),
                    self.headers.get("Idempotency-Key", ""),
                )
            except ValueError as error:
                return self.send_json(422, {"error": str(error)})
            except PermissionError as error:
                return self.send_json(403, {"error": str(error)})
            except urlerror.HTTPError as error:
                if error.code == 429:
                    return self.send_json(429, {"error": "Muitas validações. Aguarde e tente novamente."})
                if 400 <= error.code < 500:
                    return self.send_json(403, {"error": "Licença inativa ou expirada."})
                return self.send_json(503, {"error": "Servidor de licença temporariamente indisponível."})
            except (OSError, TimeoutError, urlerror.URLError, json.JSONDecodeError):
                return self.send_json(503, {"error": "Importação temporariamente indisponível."})
            return self.send_json(200, result)

        if path == "/api/admin/profile":
            actor = self.require_admin()
            if not actor:
                return
            try:
                requested = normalize_user(str(self.read_json().get("profile", "")))
            except (ValueError, json.JSONDecodeError):
                return self.send_json(400, {"error": "Profile inválido."})
            profile = requested or actor
            if profile != actor:
                with database() as db:
                    if not db.execute(
                        "SELECT 1 FROM users WHERE id = ? AND id <> ? AND archived_at IS NULL",
                        (profile, LOCAL_USER),
                    ).fetchone():
                        return self.send_json(404, {"error": "Profile não encontrado."})
            selected = None if profile == actor else profile
            return self.send_json(
                200,
                {"ok": True, "profile": profile},
                {"Set-Cookie": self.profile_cookie(selected)},
            )

        if path == "/api/admin/profile/manage":
            actor = self.require_admin()
            if not actor:
                return
            try:
                payload = self.read_json()
                profile = str(payload.get("profile", ""))
                action = str(payload.get("action", ""))
                selected_profile = self.selected_admin_profile(actor)
                result = manage_profile(actor, profile, action)
            except (ValueError, json.JSONDecodeError) as error:
                return self.send_json(400, {"error": str(error)})
            except PermissionError as error:
                return self.send_json(403, {"error": str(error)})
            except LookupError as error:
                return self.send_json(404, {"error": str(error)})
            clear_selection = normalize_user(profile) == selected_profile
            return self.send_json(
                200,
                result,
                {"Set-Cookie": self.profile_cookie()} if clear_selection else None,
            )

        if path == "/api/import/capture":
            if not self.require_identity():
                return
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0]
            length = int(self.headers.get("Content-Length", 0))
            if content_type != "text/csv" or length <= 0 or length > 20 * 1024 * 1024:
                return self.send_json(400, {"error": "Envie um CSV de captura de até 20 MB."})
            try:
                payload = parse_capture_csv(self.rfile.read(length))
                license_result = validate_capture_license(payload)
            except ValueError as error:
                return self.send_json(422, {"error": str(error)})
            except PermissionError as error:
                return self.send_json(403, {"error": str(error)})
            except urlerror.HTTPError as error:
                if error.code == 429:
                    return self.send_json(429, {"error": "Muitas validações. Aguarde e tente novamente."})
                if 400 <= error.code < 500:
                    return self.send_json(403, {"error": "Licença inativa ou expirada."})
                return self.send_json(503, {"error": "Servidor de licença temporariamente indisponível."})
            except (OSError, TimeoutError, urlerror.URLError, json.JSONDecodeError):
                return self.send_json(503, {"error": "Servidor de licença temporariamente indisponível."})
            return self.send_json(200, {**payload, "license": license_result})

        if path == "/api/import/market":
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0]
            if content_type == "application/json":
                profile = self.bearer_profile()
                if not profile:
                    return self.send_json(
                        401, {"error": "Token inválido ou revogado."}
                    )
                try:
                    result = import_market_capture(
                        profile,
                        self.read_json(),
                        self.headers.get("Idempotency-Key", ""),
                        defer_notifications=True,
                    )
                except ValueError as error:
                    return self.send_json(422, {"error": str(error)})
                except PermissionError as error:
                    return self.send_json(403, {"error": str(error)})
                except urlerror.HTTPError as error:
                    if error.code == 429:
                        return self.send_json(
                            429,
                            {
                                "error": (
                                    "Muitas validações. Aguarde e tente "
                                    "novamente."
                                )
                            },
                        )
                    if 400 <= error.code < 500:
                        return self.send_json(
                            403, {"error": "Licença inativa ou expirada."}
                        )
                    return self.send_json(
                        503,
                        {
                            "error": (
                                "Servidor de licença temporariamente "
                                "indisponível."
                            )
                        },
                    )
                except (
                    OSError,
                    TimeoutError,
                    urlerror.URLError,
                    json.JSONDecodeError,
                    sqlite3.Error,
                ):
                    return self.send_json(
                        503,
                        {"error": "Importação do Mercado indisponível."},
                    )
                try:
                    return self.send_json(200, result)
                finally:
                    if result.get("inserted"):
                        enqueue_market_alerts_async(result["snapshotId"])
            profile = self.require_identity()
            if not profile:
                return
            length = int(self.headers.get("Content-Length", 0))
            if content_type != "text/csv" or length <= 0 or length > 20 * 1024 * 1024:
                return self.send_json(400, {"error": "Envie um CSV de até 20 MB."})
            temporary_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as target:
                    temporary_path = Path(target.name)
                    target.write(self.rfile.read(length))
                result = import_market_csv(
                    temporary_path, profile=profile, defer_notifications=True
                )
            except (ValueError, csv.Error) as exc:
                return self.send_json(422, {"error": str(exc)})
            except (OSError, sqlite3.Error):
                return self.send_json(503, {"error": "Importação do Mercado indisponível."})
            finally:
                if temporary_path:
                    temporary_path.unlink(missing_ok=True)
            try:
                return self.send_json(200, result)
            finally:
                if result.get("inserted"):
                    enqueue_market_alerts_async(result["snapshotId"])

        if path == "/api/capture/validate":
            if not self.require_identity():
                return
            try:
                result = validate_capture_license(self.read_json())
            except ValueError as error:
                return self.send_json(422, {"error": str(error)})
            except PermissionError as error:
                return self.send_json(403, {"error": str(error)})
            except json.JSONDecodeError:
                return self.send_json(400, {"error": "Arquivo sem comprovante de licença válido."})
            except urlerror.HTTPError as error:
                if error.code == 429:
                    return self.send_json(429, {"error": "Muitas validações. Aguarde e tente novamente."})
                if 400 <= error.code < 500:
                    return self.send_json(403, {"error": "Licença inativa ou expirada."})
                return self.send_json(503, {"error": "Servidor de licença temporariamente indisponível."})
            except (OSError, TimeoutError, urlerror.URLError, json.JSONDecodeError):
                return self.send_json(503, {"error": "Servidor de licença temporariamente indisponível."})
            return self.send_json(200, result)

        if path != "/api/ocr":
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
    def option(name):
        return sys.argv[sys.argv.index(name) + 1] if name in sys.argv and sys.argv.index(name) + 1 < len(sys.argv) else None

    if "--import-codex" in sys.argv:
        source = option("--import-codex")
        if not source:
            raise SystemExit("Informe o JSONL após --import-codex")
        print(json.dumps(
            import_codex_snapshot(Path(source), option("--character"), option("--user")),
            ensure_ascii=False,
        ))
        raise SystemExit
    if "--import-market" in sys.argv:
        source = option("--import-market")
        if not source:
            raise SystemExit("Informe o CSV após --import-market")
        print(json.dumps(import_market_csv(Path(source), option("--captured-at"), option("--source-id")), ensure_ascii=False))
        raise SystemExit
    if "--discord-test" in sys.argv:
        profile = option("--discord-test")
        if not profile:
            raise SystemExit("Informe o Profile após --discord-test")
        print(json.dumps(enqueue_discord_test_alert(profile), ensure_ascii=False))
        raise SystemExit
    if "--self-test" in sys.argv:
        assert all(normalize_user(user) for user in ADMIN_USERS)
        assert not is_admin_user("perfil-inexistente")
        prime_items = market_item_lookup(["1000594", "1000111"])
        assert prime_items["1000594"]["prime"] is True
        assert prime_items["1000111"]["prime"] is False
        collection_1336 = next(
            collection for collection in codex_catalog_data()["collections"]
            if collection["id"] == "1336"
        )
        assert {
            (bonus["kind"], bonus["name"], bonus["value"])
            for bonus in collection_1336["bonuses"]
        } == {
            ("partial", "Res. Dano Fixo", "+4"),
            ("complete", "FP Máx.", "+20"),
        }
        sample_lease = "a" * 20
        assert capture_license_claim({
            "metadata": {"license_lease": sample_lease, "installation_id": "install-1"}
        }) == (sample_lease, "install-1")
        capture_csv = (
            "profile,character_name,identification_status,requires_site_review,"
            "installation_id,license_lease,codex_marks,loadout,session_id\n"
            'kojiro,Ottus,confirmed_uid,False,install-1,'
            + sample_lease
            + ',"{""1001"":[1,3]}",'
            '"{""biosuit"":2075041,""equipment"":[{""itemIndex"":1000078,'
            '""slot"":1,""refinement"":7}]}",session-1\n'
        )
        parsed_capture = parse_capture_csv(capture_csv)
        assert parsed_capture["profiles"][0]["marks"] == {"1001": [1, 3]}
        assert parsed_capture["profiles"][0]["loadout"]["equipment"][0] == {
            "itemIndex": "1000078", "slot": 1, "refinement": 7, "prime": False,
        }
        assert capture_license_claim(parsed_capture) == (sample_lease, "install-1")
        try:
            capture_license_claim({"metadata": {}})
            raise AssertionError("Comprovante ausente foi aceito")
        except ValueError:
            pass
        try:
            capture_license_claim({
                "license_lease": sample_lease,
                "requires_site_review": True,
            })
            raise AssertionError("Captura ambígua foi aceita")
        except ValueError:
            pass
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
        assert clean_state({"history": [], "characters": [], "locations": [], "codex": {"Teste": {"1001": [2, 1, 2, 99]}}})["codex"]["Teste"]["1001"] == [1, 2]
        assert clean_state({"history": [], "characters": [], "locations": [], "codexShopping": {"Teste": {"1001": [2, 2]}}})["codexShopping"]["Teste"]["1001"] == [2]
        assert clean_state({"historyColumnLayout": {"order": ["mob", "createdAt", "mob"], "widths": {"mob": 240}, "hidden": ["credits", "credits"]}})["historyColumnLayout"] == {"order": ["mob", "createdAt"], "widths": {"mob": 240}, "hidden": ["credits"]}
        assert clean_state({"codexShoppingBought": {"Teste": {"1001": [2, 2]}}})["codexShoppingBought"]["Teste"]["1001"] == [2]
        shopping_state = clean_state({"manualShopping": {"Teste": [{"itemId": "1000111", "name": "Cross Combat Axe", "source": "Arcane Node", "quantity": 1, "prime": True, "image": "/market-images/1000111.png"}]}})["manualShopping"]["Teste"][0]
        assert shopping_state["prime"] is True and shopping_state["image"] == "/market-images/1000111.png"
        assert clean_state({"salvageWatchedMaterials": [{"itemId": "1990000", "enchant": 0, "targetQuantity": 100}]})["salvageWatchedMaterials"][0]["targetQuantity"] == 100
        personal_state = clean_state({"characters": [{"name": "Teste", "craftInventory": {
            "materials": [{"itemId": "270045", "name": "Liga", "grade": 3, "quantity": 2}],
            "chests": [{"grade": 3, "quantity": 1}],
        }}], "personalCraftRecipes": [{"recipeKey": 19, "runs": 1, "name": "Teste"}]})
        assert personal_state["characters"][0]["craftInventory"]["materials"][0]["quantity"] == 2
        assert personal_state["personalCraftRecipes"] == [{"recipeKey": 19, "runs": 1, "name": "Teste"}]
        assert CODEX_STAT_NAMES["STAT_MAXFPRATE"] != CODEX_STAT_NAMES["STAT_ITEMDROPRATEINCRATE"]
        assert clean_state({"history": [], "characters": [{"name": "Teste"}], "locations": [], "archivedCharacters": ["Teste", "teste", "Inexistente"]})["archivedCharacters"] == ["Teste"]
        loadout_state = clean_state({"characters": [{
            "name": "Teste",
            "character_uid": 123,
            "loadout": {
                "biosuit": {"item_index": 2075041},
                "hover": 4400011,
                "equipment_items": [
                    {"item_index": 1000078, "slot_id": 1, "refine": 7, "prime": True},
                    {"itemIndex": 1000001, "slot": 1},
                ],
            },
        }]})["characters"][0]
        assert loadout_state["characterUid"] == "123"
        assert loadout_state["loadout"]["biosuit"]["itemIndex"] == "2075041"
        assert loadout_state["loadout"]["rover"]["itemIndex"] == "4400011"
        assert loadout_state["loadout"]["equipment"] == [{
            "itemIndex": "1000001", "slot": 1, "refinement": 0, "prime": False,
        }]
        partial_loadout = merge_character_loadout(
            loadout_state["loadout"],
            {"biosuit": 2075042, "equipment": [], "updatedAt": "2026-08-05T12:00:00+00:00"},
        )
        assert partial_loadout["biosuit"]["itemIndex"] == "2075042"
        assert partial_loadout["equipment"] == loadout_state["loadout"]["equipment"]
        assert partial_loadout["updatedAt"] == "2026-08-05T12:00:00+00:00"
        newer_capture = clean_state({"characters": [{"name": "Teste", "characterUid": "123", "level": 70, "loadout": {"equipment": [{"itemIndex": "1000078", "slot": 1, "refinement": 7}]}}], "captureReceipts": {"character": "2026-08-04T12:00:00+00:00"}})
        stale_browser = clean_state({"characters": [{"name": "Teste", "level": 60, "craftInventory": {"materials": [], "chests": []}}], "captureReceipts": {"character": "2026-08-04T11:00:00+00:00"}})
        merged_capture = preserve_newer_character_capture(newer_capture, stale_browser)["characters"][0]
        assert merged_capture["level"] == 70 and merged_capture["loadout"]["equipment"][0]["refinement"] == 7 and "craftInventory" in merged_capture
        assert character_loadout_catalog()["items"]["2075041"]["className"] == "Arbiter"
        receipt_state = clean_state({"captureReceipts": {
            "character": "2026-07-30T12:34:56-03:00",
        }})
        assert receipt_state["captureReceipts"]["character"] == "2026-07-30T15:34:56+00:00"
        snapshot_state = clean_state({"codexSnapshots": {"Carvalho": {
            "capturedAt": "2026-07-31T12:00:00-03:00",
            "collections": ["500170", "1001", "500170"],
            "marks": {"1001": [2, 1, 2]},
        }}})
        assert snapshot_state["codexSnapshots"]["Carvalho"]["collections"] == ["1001", "500170"]
        assert snapshot_state["codexSnapshots"]["Carvalho"]["marks"] == {"1001": [1, 2]}
        assert codex_receipt_keys({"1001": [1]}) == {"collection"}
        assert codex_receipt_keys({"2000000": [1]}) == {"memoryChip"}
        shared_state = clean_state({
            "characters": [{"name": "Carvalho", "className": "Arbiter", "level": 75, "cp": 999}],
            "characterShares": {
                "Carvalho": {"recipients": ["amigo"], "fields": ["level", "codex"]}
            },
            "codex": {"Carvalho": {"1001": [1, 3]}},
        })
        assert shared_state["characterShares"]["Carvalho"]["fields"] == ["codex", "level"]
        shared_views = shared_character_views(
            "amigo",
            [("dono", json.dumps(shared_state)), ("amigo", json.dumps(shared_state))],
        )
        assert shared_views == [{
            "owner": "dono", "name": "Carvalho", "level": 75,
            "codex": {"collections": 1, "items": 2},
        }]
        market_state = clean_state({"history": [], "characters": [], "locations": [], "marketFavorites": ["1000150", "1000150"], "marketAlerts": [{"id": "1000150:7", "itemId": "1000150", "refinement": 7, "targetPrice": 100, "enabled": True}]})
        assert market_state["marketFavorites"] == ["1000150"] and market_state["marketAlerts"][0]["targetPrice"] == 100
        assert clean_state({"marketAlerts": [{"id": "material-unit:19001", "itemId": "19001", "refinement": 0, "targetPrice": .2, "kind": "material-unit", "prime": "prime"}]})["marketAlerts"][0]["prime"] == "prime"
        range_alert = clean_state({"marketAlerts": [{"id": "range:1", "itemId": "1000150", "refinement": 8, "refinementMode": "selected", "refinements": [9, 7, 8, 8], "targetPrice": 100, "prime": "prime"}]})["marketAlerts"][0]
        assert range_alert["refinements"] == [7, 8, 9]
        assert market_alert_refinement_matches(range_alert, 8) and not market_alert_refinement_matches(range_alert, 6)
        custom_alert = clean_alert_rule({
            "schemaVersion": 2, "id": "rule:test", "name": "Prime barato", "source": "market",
            "selectors": {"category": "Arma", "prime": "prime", "refinementMode": "between", "refinements": [9, 7]},
            "conditionMode": "all", "conditions": [{"field": "price", "operator": "lte", "value": 100}],
            "delivery": {"destination": "dm", "repeat": "transition", "resultLimit": 5, "language": "en"},
        })
        assert custom_alert["selectors"]["refinements"] == [7, 9] and custom_alert["delivery"]["language"] == "en"
        assert alert_selector_matches({"name": "Machado", "itemId": "100", "category": "Arma", "subcategory": "Dreadnought", "tier": 5, "grade": 4, "prime": True, "refinement": 8}, custom_alert["selectors"])
        multi_alert = clean_alert_rule({
            "id": "rule:multi", "name": "Filtros", "source": "market",
            "selectors": {"categories": ["Arma", "Acessório"], "subcategories": ["Dreadnought"], "serverTypes": [0], "refinementMode": "greater-than", "refinements": [7]},
            "conditions": [{"field": "price", "operator": "lte", "value": 100}], "delivery": {},
        })
        assert alert_selector_matches({"name": "Machado", "itemId": "100", "category": "Arma", "subcategory": "Dreadnought", "serverType": 0, "tier": 5, "grade": 4, "prime": False, "refinement": 8}, multi_alert["selectors"])
        assert not alert_selector_matches({"name": "Machado", "itemId": "100", "category": "Arma", "subcategory": "Dreadnought", "serverType": 1, "tier": 5, "grade": 4, "prime": False, "refinement": 8}, multi_alert["selectors"])
        assert alert_condition_matches(99, "lte", 100) and not alert_condition_matches(101, "lte", 100)
        assert material_alert_source({"purchasePlan": {"lines": [
            {"itemId": "100", "name": "Caro", "sourcePrice": 20, "costPerMaterial": .2},
            {"itemId": "200", "name": "Barato", "nameEn": "Cheap", "enchant": 7,
             "prime": True, "sourcePrice": 15, "costPerMaterial": .15},
        ]}}) == {"itemId": "200", "name": "Barato", "nameEn": "Cheap", "refinement": 7,
                  "prime": True, "price": 15}
        assert material_unit_alert_offer({"name": "Arcane Node", "purchasePlan": {"lines": [
            {"costPerMaterial": .2, "capturedAt": "older"}, {"costPerMaterial": .153, "capturedAt": "latest"},
        ]}}, {"itemId": "19001", "refinement": 0})["lowest_price"] == .153
        assert normalize_search("Habilidade Épica") == "habilidade epica"
        market_sample = parse_market_csv("nome;categoria;subcategoria;refino;preco;maiorpreco;quantidade\nMachado de Palaccia;Arma;Dreadnought;+7;1.250.000;1.500.000;3\n")
        assert market_sample[0]["price"] == 1_250_000 and market_sample[0]["highestPrice"] == 1_500_000
        partial_plan = salvage_purchase_plan([{
            "sourceQuantity": 1, "sourcePrice": 10, "quantity": 30,
        }], 100)
        assert not partial_plan["complete"] and partial_plan["coveredQuantity"] == 30 and partial_plan["missingQuantity"] == 70
        exact_plan = salvage_purchase_plan([{
            "name": "Carregador", "enchant": 0, "sourcePrice": 10, "quantity": 30,
            "priceLevels": [{"price": 10, "quantity": 2}, {"price": 12, "quantity": 2}],
        }], 100)
        assert exact_plan["complete"] and exact_plan["totalCost"] == 44
        assert [line["buyQuantity"] for line in exact_plan["lines"]] == [2, 2]
        assert math.isclose(exact_plan["costPerMaterial"], 44 / 100)
        assert [line["costPerMaterial"] for line in exact_plan["lines"]] == [10 / 30, 12 / 30]
        aggregate_plan = salvage_purchase_plan([{
            "name": "Carregador", "enchant": 0, "sourcePrice": 10,
            "sourceQuantity": 4, "quantity": 30,
        }], 100)
        assert not aggregate_plan["complete"] and aggregate_plan["totalCost"] == 10
        assert aggregate_plan["lines"][0]["buyQuantity"] == 1
        inferred_plan = salvage_purchase_plan([{
            "name": "Carregador", "enchant": 0, "sourcePrice": 10,
            "sourceQuantity": 89, "fallbackLowestQuantity": 2,
            "fallbackQuantityBasis": "inferred", "quantity": 30,
        }], 100)
        assert not inferred_plan["complete"] and inferred_plan["coveredQuantity"] == 60
        assert inferred_plan["lines"][0]["buyQuantity"] == 2
        upgrade_check = upgrade_expected_cost([
            {"successRate": 10_000, "creditCost": 100},
            {"successRate": 5_000, "creditCost": 200},
        ], 1_000, 100, 10)
        assert upgrade_check["reachProbability"] == .5
        assert upgrade_check["expectedSourceItems"] == 2
        assert upgrade_check["expectedUpgraders"] == 4
        assert upgrade_check["diamondsPerMaterial"] == 240
        original_db_path = DB_PATH
        with tempfile.TemporaryDirectory() as temporary:
            DB_PATH = Path(temporary) / "test.db"
            codex_path = Path(temporary) / "collection.jsonl"
            codex_path.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in (
                    {"decoded": {"type": "world_info_prefix", "fields": {"character_name": "Carvalho"}}},
                    {"collection": {
                        "type": "collection_snapshot_chunk", "collection_type": 1,
                        "record_count": 2, "is_end": True,
                        "records": [
                            {"collection_index": 1001, "collection_type": 1, "catalog_known": True, "completed_slots": [0, 2]},
                            {"collection_index": 1002, "collection_type": 1, "catalog_known": False, "completed_slots": []},
                        ],
                    }},
                )) + "\n",
                encoding="utf-8",
            )
            with database() as db:
                db.execute(
                    "INSERT INTO users(id, state) VALUES (?, ?)",
                    ("carvalho", json.dumps({
                        "characters": [{"name": "Carvalho", "level": 66, "className": "Arbiter"}]
                    })),
                )
            profile_token = create_profile_token("carvalho")
            assert profile_for_token(profile_token) == "carvalho"
            assert profile_for_token("token-invalido") is None
            with database() as db:
                db.execute(
                    "UPDATE users SET state=? WHERE id=?",
                    (json.dumps({"marketAlerts": [{"id": "1000150:7", "itemId": "1000150", "refinement": 7, "targetPrice": 100, "enabled": True}]}), "carvalho"),
                )
            discord_token = create_discord_link_token("carvalho")
            discord_link = link_discord_user(discord_token, "123456789", "987654321")
            assert discord_link["profile"] == "carvalho"
            assert set_discord_opt_in("123456789", True)["dmOptIn"]
            test_alert = enqueue_discord_test_alert("carvalho")
            test_messages = claim_discord_outbox()
            assert test_alert["outboxId"] == test_messages[0]["id"]
            assert test_messages[0]["payload"]["type"] == "test_alert"
            ack_discord_outbox(test_messages[0]["id"], "sent")
            admin_message = enqueue_admin_discord_message("carvalho", ["carvalho"], "Manutenção às 22h")
            admin_messages = claim_discord_outbox()
            assert admin_message["queued"] == ["carvalho"] and admin_messages[0]["payload"]["type"] == "admin_message"
            ack_discord_outbox(admin_messages[0]["id"], "sent")
            original_introspect = introspect_license_lease
            introspect_license_lease = lambda _lease: {
                "active": True,
                "installation_id": "install-1",
                "valid_until": "2026-12-31T00:00:00Z",
            }
            farm_payload = {
                    "metadata": {
                        "profile": "carvalho",
                        "license_lease": "lease-" + "x" * 32,
                        "installation_id": "install-1",
                    },
                    "profiles": [
                        {
                            "profile": "carvalho",
                            "name": "Carvalho",
                            "character_uid": "6150132606160031134",
                            "cp": 123456,
                            "marks": {"1001": [1], "1003": []},
                            "collection_types": [1],
                            "loadout": {
                                "biosuit": {"item_index": 2075041},
                                "rover": {"item_index": 4400011},
                                "equipment": [{"item_index": 1000078, "slot": 1, "refinement": 7}],
                            },
                        }
                    ],
                    "subsession_reports": [
                        {
                            "id": "sub-1",
                            "started_ns": 1_700_000_000_000_000_000,
                            "duration_seconds": 60,
                            "name": "Farm Abismo",
                            "location": "Secret Nemesis Base + Secret Nemesis Base 3F",
                            "mobs": ["Bellato", "Gunner"],
                            "mob_levels": {"Bellato": 65, "Gunner": 66},
                            "summary": {
                                "level": 66,
                                "exp_gained": 1000,
                                "exp_percent_total": 2.5,
                                "exp_percent_per_hour": 150,
                                "credits": 200,
                                "contribution": 50,
                                "kills": 3,
                                "loot": [{"item_index": 42, "item": "Loot teste", "count": 2, "rarity": 4}],
                            },
                        }
                    ],
                }
            farm_import = import_farm_session("carvalho", farm_payload, "a" * 64)
            duplicate_farm = import_farm_session("carvalho", farm_payload, "f" * 64)
            merged_marks = import_farm_session(
                "carvalho",
                {
                    "metadata": {
                        "profile": "carvalho",
                        "character_name": "Carvalho",
                        "license_lease": "lease-" + "x" * 32,
                        "installation_id": "install-1",
                        "marks_mode": "merge",
                    },
                    "profiles": [
                        {
                            "profile": "carvalho",
                            "name": "Carvalho",
                            "marks": {"2000000": [2]},
                            "collection_types": [2],
                        }
                    ],
                    "subsession_reports": [],
                },
                "b" * 64,
            )
            capture_fallback = import_farm_session(
                "carvalho",
                {
                    "metadata": {
                        "profile": "carvalho",
                        "character_name": "Carvalho",
                        "license_lease": "lease-" + "x" * 32,
                        "installation_id": "install-1",
                        "marks_mode": "merge",
                    },
                    "profiles": [
                        {
                            "profile": "carvalho",
                            "name": "Carvalho",
                            "character_uid": "6150132606160031134",
                        }
                    ],
                    "capture": {
                        "character_class": "Arbiter",
                        "level": 67,
                        "biosuit_item_index": 2075041,
                        "rover_item_index": 4400011,
                        "equipment": [
                            {
                                "item_index": 1000078,
                                "slot": 1,
                                "refinement": 7,
                            }
                        ],
                    },
                    "subsession_reports": [],
                },
                "c" * 64,
            )
            unknown_character = import_farm_session(
                "carvalho",
                {
                    "metadata": {
                        "profile": "carvalho",
                        "license_lease": "lease-" + "x" * 32,
                        "installation_id": "install-1",
                    },
                    "profiles": [{
                        "profile": "carvalho",
                        "name": "NovoHeroi",
                        "character_uid": "222",
                    }],
                    "subsession_reports": [],
                },
                "d" * 64,
            )
            try:
                import_farm_session(
                    "carvalho",
                    {
                        "metadata": {
                            "profile": "carvalho",
                            "license_lease": "lease-" + "x" * 32,
                            "installation_id": "install-1",
                        },
                        "profiles": [{
                            "profile": "carvalho",
                            "name": "NovoHeroi",
                            "character_uid": "333",
                        }],
                        "subsession_reports": [],
                    },
                    "e" * 64,
                )
                raise AssertionError("Conflito entre nome e UID foi aceito")
            except ValueError as error:
                assert "nome e o UID" in str(error)
            introspect_license_lease = original_introspect
            assert farm_import["records"] == 1
            assert duplicate_farm["records"] == 0
            assert merged_marks["records"] == 0
            assert capture_fallback["records"] == 0
            assert unknown_character["records"] == 0
            with database() as db:
                farm_state = json.loads(
                    db.execute(
                        "SELECT state FROM users WHERE id='carvalho'"
                    ).fetchone()[0]
                )
            assert farm_state["history"][0]["creditsHour"] == 12000
            assert farm_state["history"][0]["subsessionName"] == "Farm Abismo"
            assert farm_state["history"][0]["location"] == "Secret Nemesis Base — 3F"
            assert [mob["name"] for mob in farm_state["history"][0]["mobs"]] == ["Bellato", "Gunner"]
            assert farm_state["history"][0]["rarityCounts"]["4"] == 2
            assert farm_state["history"][0]["xp"] == 2.5
            assert farm_state["history"][0]["characterClass"] == "Arbiter"
            assert farm_state["history"][0]["characterCp"] == 123456
            assert farm_state["history"][0]["rover"]["itemIndex"] == "4400011"
            assert len(farm_state["history"][0]["farmId"]) == 64
            assert farm_state["codex"]["Carvalho"] == {
                "1001": [1],
                "2000000": [2],
            }
            assert farm_state["codexSnapshots"]["Carvalho"]["collections"] == ["1001", "1003", "2000000"]
            assert farm_state["codexSnapshots"]["Carvalho"]["marks"] == farm_state["codex"]["Carvalho"]
            assert farm_state["characters"][0]["className"] == "Arbiter"
            assert farm_state["characters"][0]["level"] == 67
            assert farm_state["characters"][0]["characterUid"] == "6150132606160031134"
            assert farm_state["characters"][1]["name"] == "NovoHeroi"
            assert farm_state["characters"][1]["characterUid"] == "222"
            assert farm_state["characters"][0]["loadout"]["rover"]["itemIndex"] == "4400011"
            assert farm_state["characters"][0]["loadout"]["equipment"][0] == {
                "itemIndex": "1000078",
                "slot": 1,
                "refinement": 7,
                "prime": False,
            }
            assert {"character", "collection"} <= farm_state["captureReceipts"].keys()
            codex_import = import_codex_snapshot(codex_path)
            assert codex_import["character"] == "Carvalho"
            assert codex_import["user"] == "carvalho"
            assert codex_import["marked_collections"] == 1
            with database() as db:
                codex_state = json.loads(db.execute("SELECT state FROM users WHERE id='carvalho'").fetchone()[0])
            assert codex_state["characters"][0]["name"] == "Carvalho"
            assert codex_state["characters"][0]["loadout"]["biosuit"]["itemIndex"] == "2075041"
            assert codex_state["codex"]["Carvalho"] == {"1001": [1, 3]}
            assert "collection" in codex_state["captureReceipts"]
            market_path = Path(temporary) / "market.csv"
            credit_salvage = None
            if GAME_DB_PATH.is_file():
                with game_database() as db:
                    credit_salvage = db.execute(
                        "SELECT item_id, enchant_level FROM salvage_results WHERE reward_item_id=? LIMIT 1", ("1",)
                    ).fetchone()
            credit_rows = (
                f"CreditSource,{credit_salvage['item_id']},Outros,Consumable,{credit_salvage['enchant_level']},100,100,1,summary,\n"
                "Credits,1,Material,Material,0,5,5,1,summary,\n"
            ) if credit_salvage else ""
            market_path.write_text(
                "Name,ItemIndex,Category,Subcategory,Enhance,PricePerUnit,HighestPrice,Qty,RowType,ListingId\n"
                "Machado,1000150,Arma,Dreadnought,7,100,200,3,summary,\n"
                "Machado,1000150,Arma,Dreadnought,7,100,100,1,offer,9001\n"
                "Machado,1000150,Arma,Dreadnought,7,120,120,2,offer,9002\n"
                "Liga,270045,Material,Material,0,1000,1000,2,summary,\n"
                "Nódulo,19001,Material,Material,0,2,2,500,summary,\n"
                + credit_rows,
                encoding="utf-8",
            )
            imported = import_market_csv(market_path, "2026-07-21T18:00:00-03:00", "self-test", "carvalho")
            duplicate = import_market_csv(market_path, "2026-07-21T18:00:00-03:00", "self-test", "carvalho")
            with database() as db:
                stored = db.execute(
                    "SELECT p.lowest_price,p.highest_price,p.registered_items,s.profile,s.server_type "
                    "FROM market_prices p JOIN market_snapshots s ON s.id=p.snapshot_id"
                ).fetchone()
                stored_levels = db.execute(
                    "SELECT price, quantity FROM market_price_levels "
                    "WHERE item_id='1000150' ORDER BY price"
                ).fetchall()
            assert imported["inserted"] and imported["notificationsQueued"] == 1 and not duplicate["inserted"]
            queued_messages = claim_discord_outbox()
            assert len(queued_messages) == 1 and queued_messages[0]["discord_user_id"] == "123456789"
            assert ack_discord_outbox(queued_messages[0]["id"], "sent")["status"] == "sent"
            assert tuple(stored) == (100, 200, 3, "carvalho", 0)
            assert market_data()["lastProfile"] == "carvalho"
            assert market_data()["serverSummaries"]["0"]["snapshotCount"] == 1
            assert [tuple(row) for row in stored_levels] == [(100, 1), (120, 2)]
            with database() as db:
                global_snapshot = db.execute(
                    "INSERT INTO market_snapshots (captured_at, imported_at, source_id, row_count, total_registered, profile, server_type) "
                    "VALUES (?,?,?,?,?,?,?)",
                    ("2026-07-21T21:00:00+00:00", datetime.now(timezone.utc).isoformat(), "self-test-global", 1, 2, "carvalho", 1),
                ).lastrowid
                db.execute(
                    "INSERT INTO market_prices (snapshot_id,item_id,item_name,category,subcategory,refinement,lowest_price,highest_price,registered_items) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (global_snapshot, "1000150", "Machado", "Arma", "Dreadnought", 7, 110, 110, 2),
                )
                db.execute(
                    "INSERT INTO market_price_levels (snapshot_id,item_id,refinement,price,quantity) VALUES (?,?,?,?,?)",
                    (global_snapshot, "1000150", 7, 110, 2),
                )
            combined_market = latest_market_price_map()[("1000150", 7)]
            assert combined_market["price"] == 100 and combined_market["quantity"] == 5
            assert combined_market["priceLevels"] == [
                {"price": 100, "quantity": 1}, {"price": 110, "quantity": 2}, {"price": 120, "quantity": 2},
            ]
            demand_plan = market_purchase_plan(combined_market, 5)
            assert demand_plan["complete"] and demand_plan["totalCost"] == 560
            assert [(line["quantity"], line["unitPrice"]) for line in demand_plan["lines"]] == [(1, 100), (2, 110), (2, 120)]
            example_plan = market_purchase_plan({
                "price": 10, "priceLevels": [
                    {"price": 10, "quantity": 2}, {"price": 15, "quantity": 2}, {"price": 50, "quantity": 1},
                ],
            }, 5)
            assert example_plan["complete"] and example_plan["totalCost"] == 100
            assert market_purchase_plan({"price": 10, "priceLevels": [
                {"price": 10, "quantity": 2}, {"price": 15, "quantity": 2}, {"price": 50, "quantity": 1},
            ]}, 3)["totalCost"] == 35
            short_plan = market_purchase_plan({"price": 10, "priceLevels": [
                {"price": 10, "quantity": 2}, {"price": 15, "quantity": 2}, {"price": 50, "quantity": 1},
            ]}, 6)
            assert not short_plan["complete"] and short_plan["missingQuantity"] == 1 and short_plan["totalCost"] == 100
            if market_item_aliases().get("275045") == "270045":
                assert latest_market_price_map()[("275045", 0)]["price"] == 1000
            summary_only = latest_market_price_map()[("270045", 0)]
            summary_plan = market_purchase_plan(summary_only, 2)
            assert summary_plan["complete"] and summary_plan["coveredQuantity"] == 2
            strict_summary_plan = market_purchase_plan(summary_only, 2, require_details=True)
            assert not strict_summary_plan["complete"] and strict_summary_plan["coveredQuantity"] == 0
            assert strict_summary_plan["missingQuantity"] == 2 and strict_summary_plan["detailsMissing"]
            strict_detailed_plan = market_purchase_plan({
                "price": 10, "priceLevels": [
                    {"price": 10, "quantity": 2}, {"price": 15, "quantity": 3},
                ],
            }, 5, require_details=True)
            assert strict_detailed_plan["complete"] and strict_detailed_plan["totalCost"] == 65
            assert not strict_detailed_plan["detailsMissing"]
            strict_partial_plan = market_purchase_plan({
                "price": 10, "priceLevels": [{"price": 10, "quantity": 2}],
                "detailedCoverageComplete": False,
            }, 3, require_details=True)
            assert strict_partial_plan["coveredQuantity"] == 2 and strict_partial_plan["missingQuantity"] == 1
            assert strict_partial_plan["detailsMissing"]
            with database() as db:
                newer_global_snapshot = db.execute(
                    "INSERT INTO market_snapshots (captured_at, imported_at, source_id, row_count, total_registered, profile, server_type) "
                    "VALUES (?,?,?,?,?,?,?)",
                    ("2026-07-21T22:00:00+00:00", datetime.now(timezone.utc).isoformat(), "self-test-global-newer", 0, 0, "carvalho", 1),
                ).lastrowid
            assert not any(listing["serverType"] == 1 and listing["itemId"] == "1000150" for listing in market_data()["listings"])
            lookup_after_empty_global, _ = latest_market_price_lookup(["1000150"])
            assert lookup_after_empty_global[("1000150", 7)] == 100
            with database() as db:
                db.execute("DELETE FROM market_snapshots WHERE id=?", (newer_global_snapshot,))
            with database() as db:
                db.execute("DELETE FROM market_price_levels WHERE snapshot_id=?", (global_snapshot,))
                db.execute("DELETE FROM market_prices WHERE snapshot_id=?", (global_snapshot,))
                db.execute("DELETE FROM market_snapshots WHERE id=?", (global_snapshot,))
            history_sample = market_history("1000150")
            assert history_sample["captures"][0]["lowestPrice"] == 100
            exported, _ = latest_market_csv()
            assert b"RegisteredAds" in exported and b"1000150" in exported
            introspect_license_lease = lambda _lease: {
                "active": True,
                "installation_id": "install-1",
                "valid_until": "2026-12-31T00:00:00Z",
            }
            live_market = {
                "metadata": {
                    "profile": "carvalho",
                    "license_lease": "lease-" + "x" * 32,
                    "installation_id": "install-1",
                    "captured_at": "2026-07-21T17:00:00-03:00",
                    "market_server_type": 2,
                },
                "rows": [
                    {
                        "RowType": "summary",
                        "ServerType": 2,
                        "ListingId": "",
                        "Name": "",
                        "ItemIndex": 1000150,
                        "Enhance": 7,
                        "PricePerUnit": 100,
                        "Qty": 3,
                        "HighestPrice": 200,
                    }
                ],
            }
            live_import = import_market_capture(
                "carvalho", live_market, "c" * 64, defer_notifications=True
            )
            live_duplicate = import_market_capture(
                "carvalho", live_market, "c" * 64
            )
            introspect_license_lease = original_introspect
            assert live_import["inserted"] and not live_duplicate["inserted"]
            assert live_import["notificationsDeferred"] is True
            assert live_import["serverType"] == 2
            if GAME_DB_PATH.is_file():
                personal = personal_craft_analysis({
                    "recipes": [{"recipeKey": 19, "runs": 1}],
                    "inventories": [{"character": "Carvalho", "inventory": {
                        "materials": [{"itemId": "270045", "name": "Liga", "grade": 3, "quantity": 1}],
                    }}, {"character": "Alt", "inventory": {
                        "materials": [{"itemId": "270045", "name": "Liga", "grade": 3, "quantity": 1}],
                        "chests": [{"grade": 3, "quantity": 1}],
                    }}],
                })
                personal_liga = next(line for line in personal["requirements"] if line["itemId"] == "270045")
                assert personal_liga["ownedQuantity"] == 2 and [origin["character"] for origin in personal_liga["origins"]] == ["Carvalho", "Alt"]
                assert personal_liga["chestQuantity"] == 1 and personal_liga["chestOrigins"][0]["character"] == "Alt"
                assert personal["summary"]["chestSavings"] == 1000
                salvage_sample = salvage_data("1000150", enchant=7, limit=1)
                salvage_level = salvage_sample["items"][0]["levels"][0]
                assert salvage_level["sourcePrice"] == 100
                assert salvage_level["missingPrices"] == 0
                assert salvage_level["knownValue"] == sum(output["totalValue"] for output in salvage_level["outputs"])
                assert salvage_level["difference"] == salvage_level["knownValue"] - 100
                arcane_node = salvage_material_data("arcane node", enchant=7, limit=10, target_quantity=200)
                arcane_source = next(
                    source for material in arcane_node["items"] for source in material["sources"]
                    if source["itemId"] == "1000150"
                )
                assert arcane_source["sourcePrice"] == 100
                assert arcane_source["unitCost"] == 100 / arcane_source["quantity"]
                arcane_plan = arcane_node["items"][0]["purchasePlan"]
                assert arcane_plan["complete"] and arcane_plan["coveredQuantity"] >= 200
                assert all(line["buyQuantity"] == 1 for line in arcane_plan["lines"])
                assert arcane_plan["totalCost"] == sum(line["lineCost"] for line in arcane_plan["lines"])
                if credit_salvage:
                    credit_item = next(item for item in salvage_data(
                        credit_salvage["item_id"], enchant=credit_salvage["enchant_level"], limit=100
                    )["items"] if item["itemId"] == credit_salvage["item_id"])
                    credit_output = next(output for output in credit_item["levels"][0]["outputs"] if output["itemId"] == "1")
                    assert credit_output["unitPrice"] is None and credit_output["totalValue"] is None
            with database() as db:
                db.execute(
                    "INSERT INTO users(id,state) VALUES (?,?)",
                    ("jogador", json.dumps({"characters": [{"name": "J"}]})),
                )
                owner_state = json.loads(db.execute("SELECT state FROM users WHERE id='carvalho'").fetchone()[0])
                owner_state["characterShares"] = {
                    "Carvalho": {"recipients": ["jogador"], "fields": ["level"]}
                }
                db.execute("UPDATE users SET state=? WHERE id='carvalho'", (json.dumps(owner_state),))
            jogador_token = create_profile_token("jogador")
            assert manage_profile("carvalho", "jogador", "archive")["action"] == "archive"
            assert profile_for_token(jogador_token) is None
            assert manage_profile("carvalho", "jogador", "restore")["action"] == "restore"
            assert manage_profile("carvalho", "jogador", "delete")["action"] == "delete"
            with database() as db:
                assert not db.execute("SELECT 1 FROM users WHERE id='jogador'").fetchone()
                cleaned_owner_state = json.loads(db.execute("SELECT state FROM users WHERE id='carvalho'").fetchone()[0])
            assert not cleaned_owner_state.get("characterShares")
        DB_PATH = original_db_path
        if GAME_DB_PATH.is_file():
            assert game_summary()["counts"]["item"] > 8_000
            assert game_name_en("collection", "1001") == "Armory Collectibles 1"
            assert game_search("Armory Collectibles 1", "collection", 5)["results"][0]["entity_id"] == "1001"
            assert any(row["itemId"] == "1000078" for row in equipment_search("Specter Combat Rifle", 10)["results"])
            memory_chip_sample = memory_chip_data()
            assert memory_chip_sample["counts"]["chips"] == len(memory_chip_sample["chips"]) == 120
            assert memory_chip_sample["counts"]["fragments"] == sum(
                len(chip["fragments"]) for chip in memory_chip_sample["chips"]
            )
            assert memory_chip_sample["chips"][0]["icon"].endswith(".webp")
            material_options = salvage_material_options()
            assert material_options and all(material["itemId"] != "1" for material in material_options)
            assert any(material["name"] == "Nódulo Arcano" for material in material_options)
            codex_sample = codex_data()
            assert len(codex_sample["collections"]) == game_summary()["counts"]["collection"]
            assert codex_sample["requirementCount"] == sum(
                len(collection["requirements"]) for collection in codex_sample["collections"]
            )
            assert codex_sample["collections"][0]["bonuses"] and "image" in codex_sample["collections"][0]["requirements"][0]["accepted"][0]
            npc_page = game_search("", "npc", 2)
            assert npc_page["results"][0]["entity_type"] == "npc" and npc_page["total"] >= npc_page["count"]
            assert "Provas Arcanas (Fácil)" in game_search("5051211", "npc", 1)["results"][0]["map_names"]
            assert craft_summary()["recipes"] > 1_000
            assert craft_search("Rifle", "Arma", "Punisher", 2)["results"]
            without_events = craft_search("", "", "", 100, False)
            assert without_events["results"] and all(not row["event"] for row in without_events["results"])
            without_weapons = craft_search("", "", "", 100, True, ("Arma",))
            assert all(row["category"] != "Arma" for row in without_weapons["results"])
            grade_three = craft_search("", "", "", 10, True, (), 3)
            assert grade_three["results"] and all(row["grade"] == 3 for row in grade_three["results"])
            original_craft_market_summaries = craft_market_summaries
            try:
                def one_complete_recipe(keys):
                    return {keys[0]: {"materialMarketCost": 1, "pricedMaterials": 1, "materialCount": 1, "marketCapturedAt": "snapshot"}} if keys else {}
                globals()["craft_market_summaries"] = one_complete_recipe
                complete_market = craft_search("", "", "", 10, True, (), 1, True)
                assert complete_market["count"] == complete_market["total"] == 1
                assert complete_market["results"][0]["grade"] == 1
            finally:
                globals()["craft_market_summaries"] = original_craft_market_summaries
            with game_database() as db:
                english_name = db.execute(
                    "SELECT name_en FROM craft_recipes WHERE name_en <> '' AND name_en <> output_name LIMIT 1"
                ).fetchone()[0]
            assert craft_search(english_name, "", "", 5)["results"]
            tri_plate_sample = tri_plate_data(1, "stable")
            assert len(tri_plate_sample["variants"]) == 10
            assert all(variant["unstablePerStable"] == 20 and variant["options"] for variant in tri_plate_sample["variants"])
            assert all(
                "detailsMissing" in option and option["detailMaterial"]
                for variant in tri_plate_sample["variants"] for option in variant["options"]
            )
            material_sample = [{"slot": 1, "quantity": 3, "enchantLevel": 0, "acceptedItems": [
                {"itemId": "1", "name": "A", "icon": ""}, {"itemId": "2", "name": "B", "icon": ""}
            ]}]
            enrich_craft_materials(material_sample, {("1", 0): 10, ("2", 0): 7}, "snapshot")
            assert material_sample[0]["marketPrice"] == 7 and material_sample[0]["marketTotal"] == 21
            item_page = game_search("", "item", 3, 0)
            assert item_page["total"] > 8_000 and len(item_page["results"]) <= 3
            assert all("category" in row and "grade" in row for row in item_page["results"])
            item_page_2 = game_search("", "item", 3, 3)
            assert item_page_2["results"] and item_page_2["results"][0]["entity_id"] != item_page["results"][0]["entity_id"]
            graded_items = game_search("", "item", 5, 0, grade=1)
            assert graded_items["total"] == 0 or all(row["grade"] == 1 for row in graded_items["results"])
            categorized_items = game_search("", "item", 5, 0, category=next(iter(MARKET_TAXONOMY)))
            assert all(row["category"] == next(iter(MARKET_TAXONOMY)) for row in categorized_items["results"])
            item_detail_sample = game_detail("item", item_page["results"][0]["entity_id"])
            assert item_detail_sample and "craftUses" in item_detail_sample["related"] and "craftProduces" in item_detail_sample["related"]
            equipment_page = equipment_search("", 2)
            assert len(equipment_page["results"]) == 2
            equipment_sample = equipment_detail(equipment_page["results"][0]["itemId"])
            assert equipment_sample and len(equipment_sample["stages"]) == 32 and equipment_sample["stats"]
            assert {"statId", "statEnum", "name", "regular", "prime"} <= equipment_sample["stats"][0].keys()
            assert equipment_detail("1000078")["grade"] == "R"
            assert all(row["grade"] == "C" for row in equipment_search("", 5, grade="C")["results"])
            assert all(row["biosuitType"] in (0, 6) for row in equipment_search(
                "", 10, "weapon-armor", 1, biosuit_type=6
            )["results"])
            weapon_page = equipment_search("", 5, "weapon-armor", 1, "", 5, "prime")
            assert weapon_page["results"] and all(
                row["slot"] == 1 and row["tier"] == 5 and row["version"] == "Prime"
                and 1 <= row["biosuitType"] <= 8
                for row in weapon_page["results"]
            )
            if game_has_content_changes():
                with game_database() as db:
                    new_item = db.execute(
                        "SELECT entity_id FROM content_changes "
                        "WHERE domain='item' AND change_type='new' ORDER BY entity_id LIMIT 1"
                    ).fetchone()
                    assert new_item and db.execute(
                        "SELECT COUNT(*) FROM content_changes WHERE change_type='new'"
                    ).fetchone()[0] > 0
                assert game_search(new_item[0], "item", 1)["results"][0]["changeStatus"] == "new"
        sample = Image.new("RGB", (500, 500), (30, 30, 30))
        sample.paste((140, 20, 180), (30, 285, 70, 325))
        assert count_purple_items(sample) == 1
        print("OCR parser OK")
        raise SystemExit
    with database():
        pass
    ThreadingHTTPServer(("0.0.0.0", 80), Handler).serve_forever()
