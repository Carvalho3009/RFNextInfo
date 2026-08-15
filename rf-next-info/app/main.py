from __future__ import annotations

import ctypes
import copy
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, Y, filedialog, messagebox, simpledialog, ttk
from typing import Any
import tkinter as tk

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.license import LicenseClient
from app.paths import (
    CAPTURE_DIR,
    DB_PATH,
    LOG_PATH,
    MACHINE_STATE_DIR,
    PREFERENCES_PATH,
    PREVIEW_DIR,
    STATE_DIR,
    UPDATES_DIR,
    ensure_runtime_layout,
)
from app.site_profile import SiteProfileClient
from app.support_log import configure as configure_log, recent_lines
from app.updater import (
    UPDATE_MODE,
    backup_database,
    cached_rollback,
    download_release_with_rollback,
    latest,
    verify_downloaded,
    verify_manifest,
)
from core.capture import GIB, PktmonCapture
from core.connections import (
    clients_for_executable,
    connected_processes,
    ports_for_executable,
)
from core.ingest import DEFAULT_PORTS
from core.pktmon_realtime import RealtimeCapture
from core.rfnext_frame_decode import (
    DecodeError,
    latest_market_offer_rows,
    latest_market_rows,
)
from core.store import LEVEL_CURVE, CaptureStore

VERSION = "1.0.9"
RELEASE_SEQUENCE = 10
DISCORD_URL = "https://discord.gg/D3hhdMgkj"
ASSETS = ROOT / "assets"

CLASS_ICON_FILES = {
    "Punisher": "punisher.png",
    "Phantom": "phantom.png",
    "Enforcer": "enforcer.png",
    "Psypher": "psypher.png",
    "Dreadnought": "dreadnought.png",
    "Technician": "technician.png",
    "Arbiter": "arbiter.png",
    "Demolisher": "demolisher.png",
}

RARITY_COLORS = {
    1: "#aeb7c2",
    2: "#58c96b",
    3: "#4d9fff",
    4: "#b66cff",
    5: "#f0b84a",
    6: "#ff6547",
}


def _configured_capture_dir(
    preferences_path: Path | None = None,
) -> Path:
    try:
        preferences = json.loads(
            (preferences_path or PREFERENCES_PATH).read_text(encoding="utf-8")
        )
        candidate = Path(str(preferences.get("capture_directory") or ""))
        if candidate.is_absolute():
            return candidate
    except (OSError, ValueError, TypeError):
        pass
    return CAPTURE_DIR


def _biosuit_catalog() -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(
            (ROOT / "core" / "biosuits.json").read_text(encoding="utf-8")
        )
        return data["biosuits"]
    except (OSError, ValueError, KeyError, TypeError):
        return {}


BIOSUITS = _biosuit_catalog()


def _rover_catalog() -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(
            (ROOT / "core" / "rovers.json").read_text(encoding="utf-8")
        )
        return data["rovers"]
    except (OSError, ValueError, KeyError, TypeError):
        return {}


ROVERS = _rover_catalog()


def _farm_catalog(
    filename: str = "catalogo.csv",
) -> dict[str, dict[str, dict[str, tuple[int, ...]]]]:
    catalog: dict[str, dict[str, dict[str, set[int]]]] = {}
    try:
        with (ROOT / "core" / filename).open(
            encoding="utf-8-sig", newline=""
        ) as source:
            for row in csv.DictReader(source):
                map_name = str(
                    row.get("mapa")
                    or row.get("map_name_ptbr")
                    or row.get("content_name_ptbr")
                    or ""
                ).strip()
                spot_name = str(
                    row.get("spot_andar")
                    or row.get("spot_name_ptbr")
                    or row.get("floor_or_difficulty_ptbr")
                    or ""
                ).strip()
                mob = str(
                    row.get("mob_name") or row.get("mob_name_ptbr") or ""
                ).strip()
                level = int(row.get("mob_level") or 0)
                if map_name and spot_name and mob and 1 <= level <= 999:
                    catalog.setdefault(map_name, {}).setdefault(
                        spot_name, {}
                    ).setdefault(mob, set()).add(level)
    except (OSError, TypeError, ValueError, csv.Error):
        return {}
    return {
        map_name: {
            spot_name: {
                mob: tuple(sorted(levels))
                for mob, levels in sorted(
                    mobs.items(), key=lambda item: item[0].casefold()
                )
            }
            for spot_name, mobs in sorted(
                spots.items(), key=lambda item: item[0].casefold()
            )
        }
        for map_name, spots in sorted(
            catalog.items(), key=lambda item: item[0].casefold()
        )
    }


FARM_CATALOG = _farm_catalog()
FARM_CATALOG_EN = _farm_catalog("catalogo_en.csv")


def _farm_label_translations() -> tuple[dict, dict]:
    try:
        with (ROOT / "core" / "catalogo.csv").open(
            encoding="utf-8-sig", newline=""
        ) as source:
            pt_rows = list(csv.DictReader(source))
        with (ROOT / "core" / "catalogo_en.csv").open(
            encoding="utf-8-sig", newline=""
        ) as source:
            en_rows = list(csv.DictReader(source))
    except (OSError, csv.Error):
        return {}, {}
    forward = {}
    reverse = {}
    for pt, en in zip(pt_rows, en_rows):
        pt_key = (pt["mapa"], pt["spot_andar"])
        en_key = (en["mapa"], en["spot_andar"])
        forward[pt_key] = en_key
        reverse[en_key] = pt_key
    return forward, reverse


FARM_LABELS_PT_EN, FARM_LABELS_EN_PT = _farm_label_translations()


def _register_private_fonts() -> None:
    if os.name != "nt":
        return
    add_font = ctypes.windll.gdi32.AddFontResourceExW
    for path in ASSETS.glob("*.ttf"):
        add_font(str(path), 0x10, None)


def _enable_dark_titlebar(window: tk.Tk) -> None:
    if os.name != "nt":
        return
    window.update_idletasks()
    hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
    enabled = ctypes.c_int(1)
    for attribute in (20, 19):
        if (
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                attribute,
                ctypes.byref(enabled),
                ctypes.sizeof(enabled),
            )
            == 0
        ):
            break


def _enable_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass


def _item_names(filename: str = "item_names.json") -> dict[str, str]:
    try:
        return json.loads(
            (ROOT / "core" / filename).read_text(encoding="utf-8-sig")
        )
    except (OSError, ValueError):
        return {}


ITEM_NAMES = _item_names()
ITEM_NAMES_EN = _item_names("item_names_en.json")
ITEM_NAMES_PT_RESOLVED = {**ITEM_NAMES_EN, **ITEM_NAMES}
ITEM_NAMES_EN_RESOLVED = {**ITEM_NAMES, **ITEM_NAMES_EN}


def game_data_language(language: object) -> str:
    """Normaliza a preferência usada somente pelos nomes dos dados do jogo."""
    return "en" if language == "en" else "pt"


def item_names_for_language(language: object) -> dict[str, str]:
    """Retorna o catálogo escolhido com fallback para o outro idioma."""
    return (
        ITEM_NAMES_EN_RESOLVED
        if game_data_language(language) == "en"
        else ITEM_NAMES_PT_RESOLVED
    )


def game_catalog_name(entry: dict[str, Any], language: object) -> str:
    """Resolve um nome localizado sem ocultar dados ausentes em um catálogo."""
    primary = "name_en" if game_data_language(language) == "en" else "name"
    fallback = "name" if primary == "name_en" else "name_en"
    return str(entry.get(primary) or entry.get(fallback) or "")


def _item_grades() -> dict[str, int]:
    try:
        return json.loads(
            (ROOT / "core" / "item_grades.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return {}


ITEM_GRADES = _item_grades()
INVENTORY_CATEGORIES = (
    ("equipment", "Equipamentos"),
    ("consumables", "Consumíveis"),
    ("materials", "Materiais"),
    ("talics", "Talicas"),
    ("rover_parts", "Partes de Rover"),
    ("other", "Outros"),
)


def _item_categories() -> dict[str, str]:
    try:
        data = json.loads(
            (ROOT / "core" / "item_categories.json").read_text(
                encoding="utf-8"
            )
        )
        return {
            str(item_index): str(category)
            for item_index, category in data["categories"].items()
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {}


ITEM_CATEGORIES = _item_categories()


def inventory_category(item_index: object, kind: object = "") -> str:
    """Classifica um item pelo catálogo oficial, com fallback conservador."""
    category = ITEM_CATEGORIES.get(str(item_index))
    if category:
        return category
    return "equipment" if kind == "equipment" else "other"


LOOT_RARITIES = {
    1: ("common", "Comum"),
    2: ("uncommon", "Incomum"),
    3: ("rare", "Raro"),
    4: ("epic", "Épico"),
}
LOOT_RARITY_LABELS_EN = {
    1: "Common",
    2: "Uncommon",
    3: "Rare",
    4: "Epic",
}


def _format_bytes(value: int) -> str:
    number = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if number < 1024 or unit == "TB":
            return f"{number:.1f} {unit}" if unit != "B" else f"{int(number)} B"
        number /= 1024
    return f"{number:.1f} TB"


def _safe_name(value: str, fallback: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", value.strip())
    value = re.sub(r"\s+", "-", value).strip(".- ")
    return (value or fallback)[:50]


def _capture_prefix(session_id: str) -> str | None:
    match = re.search(r"-(\d{8}-\d{6})-(\d+)$", session_id)
    return f"rfnext-{match.group(1)}-{int(match.group(2)):03d}" if match else None


def _session_elapsed(session_id: str, active: bool, now: datetime) -> int:
    if not active:
        return 0
    match = re.search(r"-(\d{8}-\d{6})-\d+$", session_id)
    if not match:
        return 0
    try:
        started = datetime.strptime(match.group(1), "%Y%m%d-%H%M%S")
    except ValueError:
        return 0
    return max(0, int((now - started).total_seconds()))


def _filter_subsessions(items: list[dict], view: str) -> list[dict]:
    if view == "Cliente A":
        return [item for item in items if item.get("client_key") != "client:b"]
    if view == "Cliente B":
        return [item for item in items if item.get("client_key") == "client:b"]
    if view == "Em andamento":
        return [item for item in items if item.get("ended_ns") is None]
    if view == "Encerradas":
        return [item for item in items if item.get("ended_ns") is not None]
    if view == "Enviadas":
        return [item for item in items if item.get("upload_state") == "sent"]
    if view == "Não enviadas":
        return [item for item in items if item.get("upload_state") != "sent"]
    return items


def _merge_client_routes(
    pids: list[int],
    port_groups: list[tuple[int, ...]],
    connections: list[dict[str, object]],
    limit: int = 2,
) -> tuple[list[int], list[tuple[int, ...]]]:
    merged_pids = list(pids[:limit])
    merged_ports = [set(group) for group in port_groups[:limit]]
    while len(merged_ports) < len(merged_pids):
        merged_ports.append(set())
    active_pids = {int(connection["pid"]) for connection in connections}
    for connection in connections:
        pid = int(connection["pid"])
        if pid in merged_pids:
            index = merged_pids.index(pid)
        elif len(merged_pids) < limit:
            merged_pids.append(pid)
            merged_ports.append(set())
            index = len(merged_pids) - 1
        else:
            inactive = next(
                (
                    index
                    for index, old_pid in enumerate(merged_pids)
                    if old_pid not in active_pids
                ),
                None,
            )
            if inactive is None:
                continue
            index = inactive
            merged_pids[index] = pid
        merged_ports[index].update(connection["local_ports"])
    return merged_pids, [
        tuple(sorted(ports)) for ports in merged_ports[:limit]
    ]


def _safe_error_code(error: Exception) -> str:
    text = str(error).casefold()
    for marker, code in (
        ("pcapng sem pacotes", "empty_capture"),
        ("captura já está ativa", "already_active"),
        ("outra captura pktmon", "external_pktmon"),
        ("acesso negado", "access_denied"),
        ("access is denied", "access_denied"),
        ("não respondeu", "pktmon_timeout"),
        ("espaço livre", "low_disk_space"),
    ):
        if marker in text:
            return code
    return type(error).__name__


def _capture_summary(
    envelope: dict,
    character_uid: str | None = None,
    character_name: str = "",
    item_names: dict[str, str] | None = None,
    *,
    game_language: str = "pt",
    _state: dict[str, Any] | None = None,
    _return_state: bool = False,
) -> tuple:
    item_names = (
        item_names_for_language(game_language)
        if item_names is None
        else item_names
    )
    empty_summary = {
        "character": "",
        "character_class": "",
        "biosuit_item_index": None,
        "biosuit_name": "",
        "biosuit_type": None,
        "biosuit_grade": None,
        "rover_item_index": None,
        "rover_name": "",
        "rover_grade": None,
        "equipment": [],
        "loadout": {},
        "level": None,
        "exp": None,
        "exp_missing": None,
        "exp_percent": None,
        "exp_gained": 0,
        "exp_gained_percent": None,
        "credits": 0,
        "diamonds": None,
        "contribution": None,
        "market_events": 0,
        "kills": 0,
        "finalizations": 0,
        "loot": [],
        "loot_by_rarity": {
            key: 0 for key, _label in LOOT_RARITIES.values()
        },
    }
    state = _state or {}
    summary = copy.deepcopy(state.get("summary", empty_summary))
    observed_exp_gained = state.get("observed_exp_gained", 0)
    observed_finalizations = state.get("observed_finalizations", 0)
    reward_finalizations = state.get("reward_finalizations", 0)
    reward_exp = state.get("reward_exp", 0)
    reward_credits = state.get("reward_credits", 0)
    reward_contribution = state.get("reward_contribution", 0)
    reward_exp_seen = state.get("reward_exp_seen", False)
    reward_credits_seen = state.get("reward_credits_seen", False)
    reward_contribution_seen = state.get("reward_contribution_seen", False)
    contribution_last = state.get("contribution_last")
    contribution_delta = state.get("contribution_delta", 0)
    contribution_samples = state.get("contribution_samples", 0)
    for event in envelope.get("events", []):
        data = event.get("data") or {}
        fields = data.get("fields") if isinstance(data.get("fields"), dict) else data
        observed_uid = fields.get("character_uid")
        event_uid = event.get("character_uid")
        target_uid = str(character_uid) if character_uid else ""
        uid_matches = bool(
            not target_uid
            or str(event_uid if event_uid is not None else observed_uid)
            == target_uid
        )
        observed_name = str(fields.get("character_name") or "").strip()
        own_appearance = event.get("type") == "appear_player_prefix" and (
            (
                character_uid
                and not character_uid.startswith("client:")
                and str(observed_uid) == character_uid
            )
            or (
                character_name
                and observed_name.casefold() == character_name.casefold()
            )
        )
        if event.get("type") != "appear_player_prefix" or own_appearance:
            summary["character"] = str(
                fields.get("character_name")
                or fields.get("character")
                or summary["character"]
            )
            summary["character_class"] = str(
                fields.get("class_name")
                or fields.get("character_class")
                or summary["character_class"]
            )
            event_type = event.get("type")
            confirmed_biosuit = event_type != "change_biosuit_request" and (
                event_type != "change_biosuit_response"
                or fields.get("result") == 0
            )
            biosuit_item_index = fields.get("biosuit_item_index")
            if confirmed_biosuit and isinstance(biosuit_item_index, int):
                summary["biosuit_item_index"] = biosuit_item_index
                biosuit = BIOSUITS.get(str(biosuit_item_index))
                if biosuit:
                    summary["biosuit_name"] = game_catalog_name(
                        biosuit, game_language
                    )
                    summary["biosuit_type"] = biosuit.get("biosuit_type")
                    summary["biosuit_grade"] = biosuit.get("grade")
                    summary["character_class"] = str(
                        biosuit.get("class_name")
                        or summary["character_class"]
                    )
            summary["level"] = fields.get("level", summary["level"])
            summary["exp"] = fields.get("exp", summary["exp"])
            summary["exp_percent"] = fields.get(
                "exp_percent", summary["exp_percent"]
            )
            if isinstance(fields.get("diamonds"), (int, float)):
                summary["diamonds"] = fields["diamonds"]
        confirmed_rover = (
            (
                event.get("type") == "player_equip_update"
                and (
                    not target_uid
                    or observed_uid is not None
                    and str(observed_uid) == target_uid
                )
            )
            or (
                event.get("type") == "change_rover_response"
                and fields.get("result") == 0
                and uid_matches
            )
            or (
                event.get("type") == "appear_player_prefix"
                and own_appearance
            )
        )
        rover_item_index = fields.get("rover_item_index")
        if confirmed_rover and isinstance(rover_item_index, int):
            rover = ROVERS.get(str(rover_item_index))
            if rover:
                summary["rover_item_index"] = rover_item_index
                summary["rover_name"] = game_catalog_name(
                    rover, game_language
                )
                summary["rover_grade"] = rover.get("grade")
        active_equipment = fields.get("active_equipment")
        equipment_uid_matches = bool(
            isinstance(active_equipment, dict)
            and target_uid
            and str(active_equipment.get("character_uid")) == target_uid
        )
        if isinstance(active_equipment, dict) and (
            uid_matches or own_appearance or equipment_uid_matches
        ):
            equipment = []
            for slot in active_equipment.get("slots", []):
                if not isinstance(slot, dict):
                    continue
                item = slot.get("item")
                slot_id = slot.get("equip_part_type")
                item_index = item.get("item_index") if isinstance(item, dict) else None
                if (
                    slot.get("resolved") is True
                    and slot_id in {*range(1, 16), 17, 18}
                    and isinstance(item_index, int)
                    and item_index > 0
                ):
                    equipment.append(
                        {
                            "item_index": item_index,
                            "slot": slot_id,
                            "refinement": int(item.get("enchant_level") or 0),
                        }
                    )
            if equipment:
                summary["equipment"] = equipment
        if isinstance(fields.get("gain_exp"), (int, float)):
            gained = fields["gain_exp"]
            observed_exp_gained += gained
            if fields.get("action_code") == 1006:
                observed_finalizations += 1
            gain_level = fields.get("level")
            gain_required = (
                LEVEL_CURVE.get(gain_level + 1)
                if isinstance(gain_level, int)
                else None
            )
            if gain_required:
                summary["exp_gained_percent"] = (
                    float(summary["exp_gained_percent"] or 0)
                    + gained * 100 / gain_required
                )
        for credit_key in ("gain_credit", "credit_gain", "credits"):
            if isinstance(fields.get(credit_key), (int, float)):
                summary["credits"] += fields[credit_key]
                break
        if isinstance(fields.get("contribution_total"), (int, float)):
            current_contribution = fields["contribution_total"]
            if contribution_last is not None:
                contribution_delta += max(
                    0, current_contribution - contribution_last
                )
            contribution_last = current_contribution
            contribution_samples += 1
        kind = str(event.get("type", "")).lower()
        if "exchange" in kind or "market" in kind:
            summary["market_events"] += 1
        if event.get("type") == "drop_item_field":
            kill_reward = False
            for item in data.get("results", []):
                item_index = item.get("item_index")
                count = item.get("count")
                if item_index == 900 and isinstance(count, (int, float)):
                    kill_reward = True
                    reward_exp += (
                        count // 10
                        if item.get("action_code") == 1006
                        else count
                    )
                    reward_exp_seen = True
                    if item.get("action_code") == 1006:
                        reward_finalizations += 1
                    continue
                if item_index == 1 and isinstance(count, (int, float)):
                    reward_credits += count
                    reward_credits_seen = True
                    continue
                if item_index == 1701 and isinstance(count, (int, float)):
                    reward_contribution += count
                    reward_contribution_seen = True
                    continue
                grade = ITEM_GRADES.get(str(item_index))
                rarity = LOOT_RARITIES.get(grade)
                if rarity and isinstance(count, (int, float)):
                    summary["loot_by_rarity"][rarity[0]] += count
                loot_item = {
                        "item_index": item_index,
                        "item": (
                            item_names.get(str(item_index))
                            or item.get("item_name")
                            or item_index
                        ),
                        "count": count,
                        "gain_total": item.get("gain_total"),
                        "grade": grade,
                        "rarity": (
                            LOOT_RARITY_LABELS_EN.get(grade)
                            if game_data_language(game_language) == "en"
                            else rarity[1] if rarity else None
                        ),
                    }
                loot_limit = state.get("loot_limit")
                if loot_limit is None or len(summary["loot"]) < loot_limit:
                    summary["loot"].append(loot_item)
            summary["kills"] += int(kill_reward)
    marks = dict(state.get("marks", {}))
    new_marks, _collection_types = _collection_marks(envelope)
    marks.update(new_marks)
    state.update(
        {
            "summary": copy.deepcopy(summary),
            "observed_exp_gained": observed_exp_gained,
            "observed_finalizations": observed_finalizations,
            "reward_finalizations": reward_finalizations,
            "reward_exp": reward_exp,
            "reward_credits": reward_credits,
            "reward_contribution": reward_contribution,
            "reward_exp_seen": reward_exp_seen,
            "reward_credits_seen": reward_credits_seen,
            "reward_contribution_seen": reward_contribution_seen,
            "contribution_last": contribution_last,
            "contribution_delta": contribution_delta,
            "contribution_samples": contribution_samples,
            "marks": marks,
        }
    )
    summary = copy.deepcopy(summary)
    required = (
        LEVEL_CURVE.get(summary["level"] + 1)
        if isinstance(summary["level"], int)
        else None
    )
    if required and isinstance(summary["exp"], (int, float)):
        summary["exp_missing"] = max(0, required - summary["exp"])
    summary["exp_gained"] = (
        reward_exp if reward_exp_seen else observed_exp_gained
    )
    summary["finalizations"] = reward_finalizations or observed_finalizations
    if reward_exp_seen:
        summary["exp_gained_percent"] = (
            reward_exp * 100 / required if required else None
        )
    if reward_credits_seen:
        summary["credits"] = reward_credits
    if reward_contribution_seen:
        summary["contribution"] = reward_contribution
    elif contribution_samples > 1:
        summary["contribution"] = contribution_delta
    loadout = {"equipment": summary["equipment"]}
    if summary["biosuit_item_index"]:
        loadout["biosuit"] = {
            "item_index": summary["biosuit_item_index"],
            "name": summary["biosuit_name"],
        }
    if summary["rover_item_index"]:
        loadout["rover"] = {
            "item_index": summary["rover_item_index"],
            "name": summary["rover_name"],
        }
    if summary["equipment"] or len(loadout) > 1:
        summary["loadout"] = loadout
    return (summary, marks, state) if _return_state else (summary, marks)


def _collection_marks(
    envelope: dict, allowed_types: set[int] | None = None
) -> tuple[dict[str, list[int]], list[int]]:
    marks: dict[str, list[int]] = {}
    seen_types: set[int] = set()
    for event in envelope.get("events", []):
        data = event.get("data") or {}
        records = data.get("records")
        if event.get("type") == "collection_add_response":
            collection_type = data.get("collection_type")
            if isinstance(collection_type, int):
                seen_types.add(collection_type)
            if (
                data.get("result_code") == 0
                and data.get("item_complete") is True
                and (allowed_types is None or collection_type in allowed_types)
                and isinstance(data.get("collection_index"), int)
                and isinstance(data.get("slot_index"), int)
                and 0 <= data["slot_index"] < 10
            ):
                key = str(data["collection_index"])
                marks[key] = sorted(
                    {*marks.get(key, []), data["slot_index"] + 1}
                )
            continue
        if not isinstance(records, list):
            continue
        event_type = data.get("collection_type")
        for record in records:
            collection_type = record.get("collection_type", event_type)
            if isinstance(collection_type, int):
                seen_types.add(collection_type)
            if allowed_types is not None and collection_type not in allowed_types:
                continue
            collection_id = record.get("collection_index")
            slots = record.get("completed_slots")
            if collection_id is not None and isinstance(slots, list):
                marks[str(collection_id)] = sorted(
                    {
                        int(slot) + 1
                        for slot in slots
                        if isinstance(slot, int) and 0 <= slot < 10
                    }
                )
    return marks, sorted(seen_types)


def _market_rows(
    envelope: dict,
    item_names: dict[str, str] | None = None,
) -> list[dict]:
    infos = [
        {"exchange": event.get("data") or {}}
        for event in envelope.get("events", [])
    ]
    rows = latest_market_rows(infos) + latest_market_offer_rows(infos)
    for row in rows:
        price = row.get("PricePerUnit")
        highest = row.get("HighestPrice")
        if isinstance(price, (int, float)) and (
            not isinstance(highest, (int, float)) or highest < price
        ):
            row["HighestPrice"] = price
        if item_names:
            name = item_names.get(str(row.get("ItemIndex")))
            if name:
                row["Name"] = name
    return rows


def _recycle(paths: list[Path]) -> bool:
    existing = [str(path.resolve()) for path in paths if path.exists()]
    if not existing:
        return True

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.c_void_p),
            ("wFunc", ctypes.c_uint),
            ("pFrom", ctypes.c_wchar_p),
            ("pTo", ctypes.c_wchar_p),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", ctypes.c_bool),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", ctypes.c_wchar_p),
        ]

    operation = SHFILEOPSTRUCTW(
        None,
        3,
        "\0".join(existing) + "\0\0",
        None,
        0x0040 | 0x0010 | 0x0400,
        False,
        None,
        None,
    )
    return (
        ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation)) == 0
        and not operation.fAnyOperationsAborted
    )


class App(tk.Tk):
    def __init__(self, *, ui_self_test: bool = False) -> None:
        super().__init__()
        if ui_self_test:
            self.withdraw()
        _register_private_fonts()
        self.title("RF QOL")
        self.geometry("1440x810")
        self.minsize(1180, 664)
        self.configure(bg="#070909")
        ensure_runtime_layout()
        self.capture_dir = (
            CAPTURE_DIR if ui_self_test else _configured_capture_dir()
        )
        try:
            self.capture_dir.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise OSError(
                f"Não foi possível usar a pasta de capturas: {self.capture_dir}"
            ) from error
        self.log = configure_log(
            STATE_DIR / "logs" / "self-test.log" if ui_self_test else LOG_PATH,
            VERSION,
        )
        self.license = LicenseClient(
            MACHINE_STATE_DIR, version=VERSION
        )
        self.license.record_release_sequence(RELEASE_SEQUENCE)
        self.site_profile = SiteProfileClient(
            STATE_DIR, version=VERSION
        )
        self.log.info(
            "license_state_loaded source=%s has_lease=%s",
            self.license.load_status,
            bool(self.license.lease),
        )
        self.capture = PktmonCapture(self.capture_dir)
        self.store = CaptureStore(DB_PATH)
        self.last_files: list[Path] = []
        self.capture_allowed = False
        self.current_session = self.store.latest_session()
        self.tray = None
        self._ingesting = False
        self._live_ingesting = False
        self._stop_after_live_ingest = False
        self._exit_after_live_ingest = False
        self._live_capture: RealtimeCapture | None = None
        self._live_files: list[Path] = []
        self._live_ports: tuple[int, ...] = ()
        self._client_ports: list[tuple[int, ...]] = []
        self._client_pids: list[int] = []
        self._live_index = 0
        self._ingest_lock = threading.Lock()
        self._next_live_decode = time.monotonic() + 30
        self._last_live_decode = "Ainda não executada"
        self._last_poll_error = ""
        self._last_packet_count: int | None = None
        self._last_game_signature = None
        self._active_quick_mode: str | None = None
        self._pending_send_mode: str | None = None
        self._pending_send_client_index: int | None = None
        self._pending_send_notify = True
        self._send_uploading = False
        self._quick_uploading = False
        self._start_after_ingest = False
        self._pause_requested = False
        self._paused = False
        self._paused_at: datetime | None = None
        self._paused_total_seconds = 0
        self.active_character_uid: str | None = None
        self._active_client_index = 0
        self._game_choices: dict[str, str] = {}
        self._selected_game_path = ""
        self.prefs: dict = {}
        self.item_name_language = tk.StringVar(value="pt")
        self.auto_subsession = tk.BooleanVar(value=False)
        self.auto_subsession_minutes = tk.IntVar(value=30)
        self._last_session_stats = {
            "recognized": 0,
            "unknown": 0,
            "unassigned": 0,
            "raw_bytes": 0,
        }
        self._last_kills = 0
        self._info_refresh_generation = 0
        self._info_refresh_running = False
        self._info_refresh_pending = False
        self._info_snapshot: dict[str, Any] | None = None
        self._info_worker_cache: dict[str, Any] = {}
        self._runtime_refresh_running = False
        self._next_runtime_refresh = 0.0
        self._license_refresh_running = False
        self._next_license_refresh = 0.0
        self._runtime_snapshot = {
            "total_bytes": 0,
            "free_bytes": 0,
            "disk_total": 0,
            "packet_count": None,
            "connections": None,
        }
        self._style()
        self._build()
        self.bind_all("<MouseWheel>", self._scroll_active_page, add="+")
        self.after(0, lambda: _enable_dark_titlebar(self))
        if ui_self_test:
            self.update_idletasks()
            self.store.close()
            self.destroy()
            return
        self._load_preferences()
        self._refresh_info()
        self._run(
            lambda: self.license.refresh_if_due(VERSION),
            self._license_checked,
        )
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Control-F8>", lambda _: self.start_capture())
        self.bind("<Control-F9>", lambda _: self.stop_capture())
        self.after(1000, self._upload_pending_quick_captures)
        self.after(600, self._poll)

    def _style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            ".",
            background="#070909",
            foreground="#F4F2EB",
            font=("Saira", 9),
        )
        style.configure("TFrame", background="#070909")
        style.configure("Topbar.TFrame", background="#0a0d0c")
        style.configure("Sidebar.TFrame", background="#0a0d0c")
        style.configure("Workspace.TFrame", background="#090c0b")
        style.configure("Statusbar.TFrame", background="#0a0d0c")
        style.configure(
            "Panel.TFrame",
            background="#0d1110",
            bordercolor="#2b3330",
            borderwidth=1,
            relief="solid",
        )
        style.configure(
            "AccentPanel.TFrame",
            background="#0d1110",
            bordercolor="#6d5428",
            borderwidth=1,
            relief="solid",
        )
        style.configure("PanelBody.TFrame", background="#0d1110")
        style.configure("TLabel", background="#070909", foreground="#F4F2EB")
        style.configure(
            "Muted.TLabel",
            foreground="#b9b5aa",
            font=("Saira", 8),
        )
        style.configure(
            "Panel.TLabel",
            background="#0d1110",
            foreground="#F4F2EB",
        )
        style.configure(
            "PanelMuted.TLabel",
            background="#0d1110",
            foreground="#b9b5aa",
            font=("Saira", 8),
        )
        style.configure(
            "Gold.TLabel",
            background="#0d1110",
            foreground="#D4A64D",
            font=("Saira SemiCondensed", 11, "bold"),
        )
        style.configure(
            "Class.TLabel",
            background="#111614",
            foreground="#D4A64D",
            font=("Saira SemiCondensed", 16, "bold"),
        )
        style.configure(
            "PanelTitle.TLabel",
            background="#0d1110",
            foreground="#F4F2EB",
            font=("Saira SemiCondensed", 12, "bold"),
        )
        style.configure(
            "QuickTitle.TLabel",
            background="#0d1110",
            foreground="#F4F2EB",
            font=("Saira SemiCondensed", 9, "bold"),
        )
        style.configure(
            "Shortcut.TLabel",
            background="#272319",
            foreground="#D4A64D",
            bordercolor="#6d5428",
            borderwidth=1,
            relief="solid",
            padding=(6, 1),
            font=("Saira SemiCondensed", 8, "bold"),
        )
        style.configure(
            "Data.TLabel",
            background="#0d1110",
            foreground="#63b9f3",
            font=("Saira SemiCondensed", 10, "bold"),
        )
        style.configure(
            "Metric.TLabel",
            background="#0d1110",
            foreground="#A8FF16",
            font=("Saira SemiCondensed", 12, "bold"),
        )
        style.configure(
            "Confirmed.TLabel",
            background="#0d1110",
            foreground="#b9b5aa",
            font=("Saira", 7),
        )
        style.configure(
            "ActiveBadge.TLabel",
            background="#0d1110",
            foreground="#58c96b",
            font=("Saira", 7, "bold"),
        )
        style.configure(
            "Title.TLabel",
            foreground="#F4F2EB",
            font=("Saira SemiCondensed", 18, "bold"),
        )
        style.configure(
            "Product.TLabel",
            background="#0a0d0c",
            foreground="#F4F2EB",
            font=("Saira SemiCondensed", 10, "bold"),
        )
        style.configure(
            "HeaderMuted.TLabel",
            background="#0a0d0c",
            foreground="#b9b5aa",
            font=("Saira", 8),
        )
        style.configure(
            "Version.TLabel",
            background="#0a0d0c",
            foreground="#D4A64D",
            font=("Consolas", 8),
        )
        style.configure(
            "Topbar.TLabel",
            background="#0a0d0c",
            foreground="#b9b5aa",
            font=("Saira", 7),
        )
        style.configure(
            "TopbarData.TLabel",
            background="#0a0d0c",
            foreground="#63b9f3",
            font=("Saira", 7),
        )
        style.configure(
            "TopbarOk.TLabel",
            background="#0a0d0c",
            foreground="#58c96b",
            font=("Saira", 7),
        )
        style.configure(
            "Sidebar.TLabel",
            background="#0a0d0c",
            foreground="#F4F2EB",
        )
        style.configure(
            "TButton",
            background="#D4A64D",
            foreground="#070909",
            bordercolor="#D4A64D",
            lightcolor="#D4A64D",
            darkcolor="#D4A64D",
            borderwidth=1,
            relief="flat",
            focusthickness=0,
            focuscolor="#D4A64D",
            padding=(12, 7),
            font=("Saira", 9, "bold"),
        )
        style.map(
            "TButton",
            background=[
                ("active", "#e1b75f"),
                ("disabled", "#6d5428"),
            ],
            foreground=[("disabled", "#b9b5aa")],
        )
        style.configure(
            "Quiet.TButton",
            background="#111614",
            foreground="#F4F2EB",
            bordercolor="#343c39",
            lightcolor="#343c39",
            darkcolor="#343c39",
        )
        style.configure(
            "Rename.TButton",
            background="#111614",
            foreground="#b9b5aa",
            bordercolor="#343c39",
            lightcolor="#343c39",
            darkcolor="#343c39",
            padding=(8, 5),
            font=("Saira", 8, "bold"),
        )
        style.configure(
            "Client.TButton",
            background="#111614",
            foreground="#F4F2EB",
            bordercolor="#343c39",
            lightcolor="#343c39",
            darkcolor="#343c39",
            padding=(10, 5),
            font=("Saira", 8),
        )
        style.map(
            "Client.TButton",
            background=[("active", "#1a211e")],
            bordercolor=[("active", "#D4A64D")],
        )
        style.configure(
            "ClientActive.TButton",
            background="#272319",
            foreground="#D4A64D",
            bordercolor="#D4A64D",
            lightcolor="#D4A64D",
            darkcolor="#D4A64D",
            padding=(10, 5),
            font=("Saira", 8, "bold"),
        )
        style.map(
            "Quiet.TButton",
            background=[("active", "#1a211e")],
            bordercolor=[("active", "#D4A64D")],
        )
        style.configure(
            "Danger.TButton",
            background="#17110f",
            foreground="#ff6547",
            bordercolor="#6d382c",
            lightcolor="#6d382c",
            darkcolor="#6d382c",
        )
        style.configure(
            "Nav.TButton",
            background="#0a0d0c",
            foreground="#b9b5aa",
            borderwidth=0,
            anchor="w",
            padding=(14, 9),
            font=("Saira", 8),
        )
        style.map(
            "Nav.TButton",
            background=[("active", "#111614")],
            foreground=[("active", "#F4F2EB")],
        )
        style.configure(
            "NavActive.TButton",
            background="#272319",
            foreground="#D4A64D",
            bordercolor="#4a3a1f",
            lightcolor="#4a3a1f",
            darkcolor="#4a3a1f",
            borderwidth=1,
            anchor="w",
            padding=(14, 9),
            font=("Saira", 8, "bold"),
        )
        style.map(
            "NavActive.TButton",
            background=[("active", "#30291b")],
            foreground=[("active", "#D4A64D")],
        )
        style.configure(
            "TEntry",
            fieldbackground="#0a0d0c",
            foreground="#F4F2EB",
            insertcolor="#F4F2EB",
            bordercolor="#6d5428",
            lightcolor="#6d5428",
            darkcolor="#6d5428",
            padding=6,
        )
        style.configure(
            "TCombobox",
            fieldbackground="#0a0d0c",
            background="#111614",
            foreground="#F4F2EB",
            arrowcolor="#D4A64D",
            bordercolor="#6d5428",
            padding=5,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", "#F4F2EB")],
            foreground=[("readonly", "#070909")],
            selectbackground=[("readonly", "#F4F2EB")],
            selectforeground=[("readonly", "#070909")],
        )
        self.option_add("*TCombobox*Listbox.background", "#F4F2EB")
        self.option_add("*TCombobox*Listbox.foreground", "#070909")
        self.option_add("*TCombobox*Listbox.selectBackground", "#D4A64D")
        self.option_add("*TCombobox*Listbox.selectForeground", "#070909")
        style.configure(
            "Shortcut.TCombobox",
            fieldbackground="#111614",
            background="#111614",
            foreground="#D4A64D",
            arrowcolor="#D4A64D",
            bordercolor="#6d5428",
            padding=5,
            font=("Saira SemiCondensed", 9, "bold"),
        )
        style.map(
            "Shortcut.TCombobox",
            fieldbackground=[("readonly", "#111614")],
            foreground=[("readonly", "#D4A64D")],
            selectbackground=[("readonly", "#111614")],
            selectforeground=[("readonly", "#D4A64D")],
        )
        style.configure(
            "TSpinbox",
            fieldbackground="#0a0d0c",
            foreground="#F4F2EB",
            arrowcolor="#D4A64D",
            bordercolor="#6d5428",
            padding=5,
        )
        style.map(
            "TSpinbox",
            fieldbackground=[("readonly", "#F4F2EB"), ("disabled", "#d8d5ce")],
            foreground=[("readonly", "#070909"), ("disabled", "#353a38")],
        )
        style.configure(
            "TCheckbutton",
            background="#0d1110",
            foreground="#b9b5aa",
        )
        style.configure(
            "TRadiobutton",
            background="#0d1110",
            foreground="#F4F2EB",
        )
        style.configure(
            "Horizontal.TProgressbar",
            background="#D4A64D",
            troughcolor="#111614",
            bordercolor="#6d5428",
        )
        style.configure(
            "Treeview",
            background="#0a0d0c",
            fieldbackground="#0a0d0c",
            foreground="#F4F2EB",
            bordercolor="#6d5428",
            rowheight=24,
            font=("Saira", 8),
        )
        style.configure(
            "Treeview.Heading",
            background="#111614",
            foreground="#D4A64D",
            bordercolor="#6d5428",
            font=("Saira", 8, "bold"),
        )
        style.map(
            "Treeview",
            background=[("selected", "#272319")],
            foreground=[("selected", "#F4F2EB")],
        )

    def _build(self) -> None:
        topbar = ttk.Frame(self, style="Topbar.TFrame")
        topbar.pack(fill=X)
        product = ttk.Frame(
            topbar, style="Topbar.TFrame", width=210, padding=(14, 6)
        )
        product.pack(side=LEFT, fill=Y)
        product.pack_propagate(False)
        ttk.Label(
            product,
            text="RF QOL",
            style="Product.TLabel",
        ).pack(side=LEFT)
        indicators = ttk.Frame(
            topbar, style="Topbar.TFrame", padding=(14, 6)
        )
        indicators.pack(side=LEFT, fill=BOTH, expand=True)
        self.top_license = ttk.Label(
            indicators,
            text="• Licença verificando",
            style="Topbar.TLabel",
        )
        self.top_license.pack(side=LEFT, padx=(0, 16))
        self.top_capture = ttk.Label(
            indicators,
            text="• Captura parada",
            style="Topbar.TLabel",
        )
        self.top_capture.pack(side=LEFT, padx=(0, 16))
        self.top_decode = ttk.Label(
            indicators,
            text="Último decode: —",
            style="TopbarData.TLabel",
        )
        self.top_decode.pack(side=LEFT, padx=(0, 16))
        self.top_next_decode = ttk.Label(
            indicators,
            text="Próx. atualização: —",
            style="Topbar.TLabel",
        )
        self.top_next_decode.pack(side=LEFT, padx=(0, 16))
        self.top_storage = ttk.Label(
            indicators,
            text="Armazenado: calculando",
            style="Topbar.TLabel",
        )
        self.top_storage.pack(side=LEFT)
        top_controls = ttk.Frame(topbar, style="Topbar.TFrame", padding=(6, 5))
        top_controls.pack(side=RIGHT)
        self.start_button = ttk.Button(
            top_controls,
            text="Iniciar · Ctrl+F8",
            command=self.start_capture,
        )
        self.start_button.grid(row=0, column=0, padx=(0, 5))
        self.pause_button = ttk.Button(
            top_controls,
            text="Pausar",
            style="Quiet.TButton",
            command=self.pause_capture,
        )
        self.pause_button.grid(row=0, column=0, padx=(0, 5))
        self.pause_button.grid_remove()
        self.stop_button = ttk.Button(
            top_controls,
            text="Encerrar · Ctrl+F9",
            style="Danger.TButton",
            command=self.stop_capture,
        )
        self.stop_button.grid(row=0, column=1)

        body = ttk.Frame(self, style="Workspace.TFrame")
        body.pack(fill=BOTH, expand=True)
        sidebar = ttk.Frame(
            body,
            style="Sidebar.TFrame",
            width=210,
            padding=(10, 8),
        )
        sidebar.pack(side=LEFT, fill=Y)
        sidebar.pack_propagate(False)
        self.class_icons = {}
        self.rover_icons = {}
        try:
            from PIL import Image, ImageDraw, ImageTk

            with Image.open(ASSETS / "karvalho-symbol-gold.png") as source:
                source = source.crop(source.getbbox())
                source.thumbnail((32, 32), Image.Resampling.LANCZOS)
                self.app_icon = ImageTk.PhotoImage(source.copy())
            self.iconphoto(True, self.app_icon)
            with Image.open(ASSETS / "karvalho-symbol-gold.png") as source:
                source = source.crop(source.getbbox())
                source.thumbnail((54, 54), Image.Resampling.LANCZOS)
                self.logo = ImageTk.PhotoImage(source.copy())
            with Image.open(ASSETS / "karvalho-primary-gold.png") as source:
                source = source.crop(source.getbbox())
                source.thumbnail((166, 42), Image.Resampling.LANCZOS)
                self.product_logo = ImageTk.PhotoImage(source.copy())
            for class_name, filename in CLASS_ICON_FILES.items():
                with Image.open(ASSETS / "class-icons" / filename) as source:
                    source = source.convert("RGBA")
                    source.thumbnail((40, 40), Image.Resampling.LANCZOS)
                    self.class_icons[(class_name, 0)] = ImageTk.PhotoImage(
                        source
                    )
                    alpha = source.getchannel("A")
                    for grade, color in RARITY_COLORS.items():
                        tinted = Image.new("RGBA", source.size, color)
                        tinted.putalpha(alpha)
                        self.class_icons[(class_name, grade)] = (
                            ImageTk.PhotoImage(tinted)
                        )
            for grade, color in {0: "#6b7470", **RARITY_COLORS}.items():
                rover = Image.new("RGBA", (40, 40))
                draw = ImageDraw.Draw(rover)
                draw.rounded_rectangle(
                    (4, 8, 35, 27), radius=7, outline=color, width=3
                )
                draw.ellipse((8, 25, 16, 33), fill=color)
                draw.ellipse((24, 25, 32, 33), fill=color)
                self.rover_icons[grade] = ImageTk.PhotoImage(rover)
            ttk.Label(
                sidebar,
                image=self.logo,
                style="Sidebar.TLabel",
            ).pack(pady=(2, 4))
            ttk.Label(
                sidebar,
                image=self.product_logo,
                style="Sidebar.TLabel",
            ).pack(pady=(0, 18))
        except (OSError, tk.TclError):
            ttk.Label(sidebar, text="RF QOL", style="Version.TLabel").pack(
                pady=(0, 10)
            )

        workspace = ttk.Frame(body, style="Workspace.TFrame")
        workspace.pack(side=LEFT, fill=BOTH, expand=True)
        sessionbar = ttk.Frame(
            workspace,
            style="Workspace.TFrame",
            padding=(12, 7),
        )
        sessionbar.pack(fill=X)
        self.client_buttons = []
        self.client_rename_buttons = []
        for index in range(2):
            client = ttk.Frame(sessionbar, style="Workspace.TFrame")
            client.pack(side=LEFT, padx=(0, 6))
            button = ttk.Button(
                client,
                text=f"Cliente {chr(65 + index)} · definir nome",
                style="Client.TButton",
                command=lambda selected=index: self._select_character(selected),
            )
            button.pack(side=LEFT)
            rename = ttk.Button(
                client,
                text="Renomear",
                style="Rename.TButton",
                command=lambda selected=index: self._rename_character(selected),
            )
            rename.pack(side=LEFT, padx=(3, 0))
            self.client_buttons.append(button)
            self.client_rename_buttons.append(rename)

        page_host = ttk.Frame(workspace, style="Workspace.TFrame")
        page_host.pack(fill=BOTH, expand=True)
        scroll_pages = [self._scrollable_page(page_host) for _ in range(6)]
        (
            self.info_tab,
            self.capture_tab,
            self.subsessions_tab,
            self.settings_tab,
            self.license_tab,
            self.tutorial_tab,
        ) = tuple(content for _page, content, _canvas in scroll_pages)
        self._page_canvases = [
            canvas for _page, _content, canvas in scroll_pages
        ]
        pages = (
            ("◉  Visão geral", scroll_pages[0][0]),
            ("▣  Envios", scroll_pages[1][0]),
            ("▤  Subsessões", scroll_pages[2][0]),
            ("⚙  Configurações", scroll_pages[3][0]),
            ("ⓘ  Licença e suporte", scroll_pages[4][0]),
            ("▥  Tutorial", scroll_pages[5][0]),
        )
        self.pages = []
        self.nav_buttons = []
        for index, (label, page) in enumerate(pages):
            page.place(x=0, y=0, relwidth=1, relheight=1)
            self.pages.append(page)
            button = ttk.Button(
                sidebar,
                text=label,
                style="Nav.TButton",
                command=lambda selected=index: self._select_page(selected),
            )
            button.pack(fill=X, pady=1)
            self.nav_buttons.append(button)
        self._capture_ui()
        self._info_ui()
        self._settings_ui()
        self._subsessions_ui()
        self._license_ui()
        self._tutorial_ui()
        self._select_page(0)

        statusbar = ttk.Frame(self, style="Statusbar.TFrame", padding=(10, 3))
        statusbar.pack(side=tk.BOTTOM, fill=X)
        self.bottom_capture = ttk.Label(
            statusbar,
            text="• Captura parada",
            style="TopbarOk.TLabel",
        )
        self.bottom_capture.pack(side=LEFT)
        ttk.Label(
            statusbar,
            text=f"v{VERSION}",
            style="Version.TLabel",
        ).pack(side=RIGHT)

    def _scrollable_page(self, parent) -> tuple[ttk.Frame, ttk.Frame, tk.Canvas]:
        page = ttk.Frame(parent, style="Workspace.TFrame")
        canvas = tk.Canvas(
            page,
            background="#090c0b",
            highlightthickness=0,
            takefocus=False,
        )
        vertical = ttk.Scrollbar(page, orient="vertical", command=canvas.yview)
        horizontal = ttk.Scrollbar(
            page, orient="horizontal", command=canvas.xview
        )
        canvas.configure(
            yscrollcommand=vertical.set,
            xscrollcommand=horizontal.set,
        )
        vertical.pack(side=RIGHT, fill=Y)
        horizontal.pack(side=tk.BOTTOM, fill=X)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        content = ttk.Frame(
            canvas, style="Workspace.TFrame", padding=(12, 8)
        )
        window = canvas.create_window((0, 0), window=content, anchor="nw")

        def resize_content(_event=None) -> None:
            canvas.itemconfigure(
                window,
                width=max(canvas.winfo_width(), content.winfo_reqwidth()),
            )
            canvas.configure(scrollregion=canvas.bbox("all"))

        content.bind(
            "<Configure>",
            resize_content,
        )
        canvas.bind(
            "<Configure>",
            resize_content,
        )
        return page, content, canvas

    def _scroll_active_page(self, event) -> str | None:
        if not getattr(self, "_page_canvases", None):
            return None
        canvas = self._page_canvases[self._active_page_index]
        try:
            widget = self.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError):
            return None
        while widget is not None and widget is not canvas:
            widget = getattr(widget, "master", None)
        if widget is not canvas or not event.delta:
            return None
        direction = -1 if event.delta > 0 else 1
        if event.state & 0x0001:
            canvas.xview_scroll(direction, "units")
        else:
            canvas.yview_scroll(direction, "units")
        return "break"

    def _select_page(self, index: int) -> None:
        self._active_page_index = index
        self.pages[index].tkraise()
        for current, button in enumerate(self.nav_buttons):
            button.configure(
                style="NavActive.TButton" if current == index else "Nav.TButton"
            )
        if index == 2:
            self._refresh_subsessions()

    def _select_character(self, index: int) -> None:
        self._active_client_index = index
        profiles = getattr(self, "_current_profiles", [])
        client_key = f"client:{chr(97 + index)}"
        profile = next(
            (
                item
                for item in profiles
                if item.get("client_key") == client_key
            ),
            None,
        )
        if profile is None and not any(
            item.get("client_key") for item in profiles
        ) and index < len(profiles):
            profile = profiles[index]
        self.active_character_uid = profile["uid"] if profile else None
        if hasattr(self, "subsession_client"):
            self.subsession_client.set(f"Cliente {chr(65 + index)}")
        self._refresh_info()

    def _client_uid(self, index: int) -> str | None:
        client_key = f"client:{chr(97 + index)}"
        profiles = getattr(self, "_current_profiles", [])
        profile = next(
            (item for item in profiles if item.get("client_key") == client_key),
            None,
        )
        if profile is None and not any(item.get("client_key") for item in profiles):
            profile = profiles[index] if index < len(profiles) else None
        return str(profile["uid"]) if profile and profile.get("uid") else None

    def _rename_character(self, index: int) -> None:
        field = self.character1 if index == 0 else self.character2
        name = simpledialog.askstring(
            "Nome do personagem",
            f"Nome exibido no Cliente {chr(65 + index)}:",
            initialvalue=field.get().strip(),
            parent=self,
        )
        if not name or not name.strip():
            return
        field.set(name.strip())
        self._save_preferences()
        self._refresh_info()

    def _client_display_name(
        self, index: int, profiles: list[dict[str, str]]
    ) -> str:
        client_key = f"client:{chr(97 + index)}"
        item = next(
            (
                profile
                for profile in profiles
                if profile.get("client_key") == client_key
            ),
            None,
        )
        if item is None and not any(
            profile.get("client_key") for profile in profiles
        ) and index < len(profiles):
            item = profiles[index]
        manual = (
            self.character1.get().strip()
            if index == 0
            else self.character2.get().strip()
        )
        captured = str(item.get("name") or "").strip() if item else ""
        names = [manual] if manual else []
        if captured and all(
            captured.casefold() != name.casefold() for name in names
        ):
            names.append(captured)
        return " · ".join(names)

    def _refresh_client_buttons(self, profiles: list[dict[str, str]]) -> None:
        self._current_profiles = profiles[:2]
        active_key = f"client:{chr(97 + self._active_client_index)}"
        active_profile = next(
            (
                item
                for item in profiles
                if item.get("client_key") == active_key
            ),
            None,
        )
        if active_profile:
            self.active_character_uid = active_profile["uid"]
        elif self.active_character_uid not in {
            item["uid"] for item in profiles
        }:
            self.active_character_uid = None
        if profiles and not any(item.get("client_key") for item in profiles):
            self.active_character_uid = profiles[0]["uid"]
            self._active_client_index = 0
        for index, button in enumerate(self.client_buttons):
            client_key = f"client:{chr(97 + index)}"
            item = next(
                (
                    profile
                    for profile in profiles
                    if profile.get("client_key") == client_key
                ),
                None,
            )
            if item is None and not any(
                profile.get("client_key") for profile in profiles
            ) and index < len(profiles):
                item = profiles[index]
            name = self._client_display_name(index, profiles)
            if item:
                button.configure(
                    text=(
                        f"Cliente {chr(65 + index)} · "
                        f"{name or f'Cliente {chr(65 + index)}'}"
                    ),
                    style=(
                        "ClientActive.TButton"
                        if index == self._active_client_index
                        else "Client.TButton"
                    ),
                )
            else:
                button.configure(
                    text=f"Cliente {chr(65 + index)} · {name or 'definir nome'}",
                    style=(
                        "ClientActive.TButton"
                        if (
                            index == self._active_client_index
                            and self.active_character_uid is None
                        )
                        else "Client.TButton"
                    ),
                )

    def _capture_ui(self) -> None:
        self.decode_interval = tk.IntVar(value=30)
        self.quick_capture_seconds = {
            mode: tk.IntVar(value=10)
            for mode in ("character", "market", "codex", "memory_chips")
        }
        self.profile = tk.StringVar()
        self.character1 = tk.StringVar()
        self.character2 = tk.StringVar()
        self.auto_export = tk.BooleanVar(value=False)
        self.delete_after_export = tk.BooleanVar(value=False)

        heading = ttk.Frame(self.capture_tab, style="Workspace.TFrame")
        heading.pack(fill=X, pady=(0, 8))
        ttk.Button(
            heading,
            text="Como funciona",
            style="Quiet.TButton",
            command=lambda: self._select_page(5),
        ).pack(side=RIGHT)
        ttk.Label(heading, text="Envios", style="Title.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            heading,
            text="Capture continuamente e envie os dados já lidos quando quiser.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        continuous = ttk.Frame(
            self.capture_tab, style="Panel.TFrame", padding=(12, 10)
        )
        continuous.pack(fill=X, pady=(0, 8))
        ttk.Label(
            continuous, text="EXP e Loot · Contínuo", style="PanelTitle.TLabel"
        ).grid(row=0, column=0, sticky="w")
        self.capture_badge = ttk.Label(
            continuous, text="PARADO", style="Data.TLabel"
        )
        self.capture_badge.grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.capture_state = ttk.Label(
            continuous, text="Pronto para iniciar", style="PanelMuted.TLabel"
        )
        self.capture_state.grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.ingest_progress = ttk.Progressbar(
            continuous, mode="determinate", maximum=100
        )
        self.ingest_progress.grid(
            row=3, column=0, columnspan=5, sticky="ew", pady=(8, 0)
        )
        self.ingest_progress.grid_remove()
        self.discard_previous = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            continuous,
            text=(
                "Descartar a sessão anterior ao iniciar, inclusive arquivos "
                "ainda não decodificados"
            ),
            variable=self.discard_previous,
        ).grid(row=2, column=0, columnspan=5, sticky="w", pady=(8, 0))
        self.capture_elapsed = ttk.Label(
            continuous, text="Tempo decorrido\n00:00:00", style="PanelMuted.TLabel"
        )
        self.capture_elapsed.grid(row=0, column=2, rowspan=2, padx=16)
        self.capture_size = ttk.Label(
            continuous, text="Arquivo atual\n0 B", style="PanelMuted.TLabel"
        )
        self.capture_size.grid(row=0, column=3, rowspan=2, padx=(0, 16))
        continuous.columnconfigure(0, weight=1)

        content = ttk.Frame(self.capture_tab, style="Workspace.TFrame")
        content.pack(fill=BOTH, expand=True)
        quick = ttk.Frame(content, style="AccentPanel.TFrame", padding=8)
        quick.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ttk.Label(
            quick,
            text="Envios rápidos",
            style="PanelTitle.TLabel",
        ).grid(row=0, column=0, columnspan=4, sticky="w")
        self.quick_duration_label = ttk.Label(
            quick,
            text="Envia os dados já lidos pela captura contínua",
            style="PanelMuted.TLabel",
        )
        self.quick_duration_label.grid(
            row=1, column=0, columnspan=4, sticky="w", pady=(1, 8)
        )
        self.quick_mode_labels = {}
        self.quick_buttons = {}
        for column, (mode, label, description) in enumerate(
            (
                (
                    "character",
                    "Personagem",
                    "Envie o personagem e os equipamentos detectados.",
                ),
                ("market", "Mercado", "Envie os eventos de mercado já lidos."),
                ("codex", "Codex", "Envie os dados de Codex já lidos."),
                ("memory_chips", "Memory Chips", "Envie os Memory Chips já lidos."),
            )
        ):
            card = ttk.Frame(quick, style="Panel.TFrame", padding=7)
            card.grid(
                row=2,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 4, 0),
            )
            card_header = ttk.Frame(card, style="PanelBody.TFrame")
            card_header.grid(row=0, column=0, sticky="ew")
            ttk.Label(
                card_header, text=label, style="QuickTitle.TLabel"
            ).pack(side=LEFT)
            state = ttk.Label(
                card,
                text="Pronto",
                style="Data.TLabel",
            )
            ttk.Label(
                card,
                text=description,
                style="PanelMuted.TLabel",
                wraplength=130,
            ).grid(row=1, column=0, sticky="nw", pady=(4, 6))
            state.grid(row=2, column=0, pady=(2, 6))
            actions = ttk.Frame(card, style="PanelBody.TFrame")
            actions.grid(row=3, column=0, sticky="ew")
            if mode == "market":
                button = ttk.Button(
                    actions,
                    text="Enviar Mercado · geral",
                    command=lambda selected=mode: self.send_mode_now(selected),
                )
                button.pack(fill=X)
                self.quick_buttons[mode] = button
            else:
                for client_index in range(2):
                    button = ttk.Button(
                        actions,
                        text=f"Enviar Cliente {chr(65 + client_index)}",
                        command=lambda selected=mode, index=client_index: (
                            self.send_mode_now(selected, index)
                        ),
                    )
                    button.pack(side=LEFT, fill=X, expand=True, padx=(
                        0 if client_index == 0 else 3, 0
                    ))
                    self.quick_buttons[f"{mode}:{client_index}"] = button
            card.columnconfigure(0, weight=1)
            card.rowconfigure(1, minsize=64)
            self.quick_mode_labels[mode] = state
            quick.columnconfigure(column, weight=1, uniform="quick-send")

        queue = ttk.Frame(content, style="Panel.TFrame", padding=10)
        queue.grid(row=0, column=1, sticky="nsew")
        ttk.Label(
            queue, text="Últimos envios", style="PanelTitle.TLabel"
        ).pack(anchor="w", pady=(0, 10))
        self.queue_mode_times = {}
        self.queue_mode_labels = {}
        for mode, label in (
            ("continuous", "EXP e Loot · Contínuo"),
            ("character", "Personagem"),
            ("market", "Mercado"),
            ("codex", "Codex"),
            ("memory_chips", "Memory Chips"),
        ):
            row = ttk.Frame(queue, style="PanelBody.TFrame")
            row.pack(fill=X, pady=2)
            label_widget = ttk.Label(
                row, text=f"• {label}", style="PanelMuted.TLabel"
            )
            label_widget.pack(side=LEFT)
            value = ttk.Label(row, text="—", style="PanelMuted.TLabel")
            value.pack(side=RIGHT)
            self.queue_mode_times[mode] = value
            if mode != "continuous":
                self.queue_mode_labels[mode] = label_widget
        self.live_decode_state = ttk.Label(
            queue,
            text="Próximo decode automático\n30 s",
            style="Data.TLabel",
        )
        self.live_decode_state.pack(anchor="w", pady=(18, 8))
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        self.metrics = tk.Text(
            self.capture_tab, height=1, width=1, state="disabled"
        )

    def _info_ui(self) -> None:
        ttk.Label(
            self.info_tab, text="Visão geral", style="Title.TLabel"
        ).pack(anchor="w")
        ttk.Label(
            self.info_tab,
            text="Dados em tempo real da sessão atual.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 8))

        self.overview_single = ttk.Frame(
            self.info_tab, style="Workspace.TFrame"
        )
        self.overview_single.pack(fill=BOTH, expand=True)

        character = ttk.Frame(
            self.overview_single, style="AccentPanel.TFrame", padding=(12, 9)
        )
        character.pack(fill=X)
        rover_badge = ttk.Frame(
            character, style="PanelBody.TFrame", width=174, height=48
        )
        rover_badge.grid(
            row=0, column=0, rowspan=2, sticky="w", padx=(0, 12)
        )
        rover_badge.pack_propagate(False)
        self.overview_rover_symbol = ttk.Label(
            rover_badge,
            text="",
            style="Class.TLabel",
            anchor="center",
        )
        self.overview_rover_symbol.pack(side=LEFT)
        self.overview_rover_name = ttk.Label(
            rover_badge,
            text="Rover —",
            style="PanelMuted.TLabel",
            wraplength=120,
        )
        self.overview_rover_name.pack(side=LEFT, padx=(7, 0))
        class_badge = ttk.Frame(
            character, style="Panel.TFrame", width=48, height=48
        )
        class_badge.grid(
            row=0, column=1, rowspan=2, sticky="w", padx=(0, 12)
        )
        class_badge.pack_propagate(False)
        self.overview_class_symbol = ttk.Label(
            class_badge,
            text="—",
            style="Class.TLabel",
            anchor="center",
        )
        self.overview_class_symbol.pack(fill=BOTH, expand=True)
        self.overview_character = ttk.Label(
            character,
            text="Aguardando personagem",
            style="PanelTitle.TLabel",
        )
        self.overview_character.grid(row=0, column=2, sticky="w")
        self.overview_level = ttk.Label(
            character,
            text="Nível —",
            style="PanelMuted.TLabel",
        )
        self.overview_level.grid(row=1, column=2, sticky="w", pady=(3, 0))
        exp_heading = ttk.Frame(character, style="PanelBody.TFrame")
        exp_heading.grid(row=0, column=3, sticky="e")
        ttk.Label(
            exp_heading,
            text="EXP do nível",
            style="Panel.TLabel",
        ).pack(side=LEFT)
        self.overview_exp = ttk.Label(
            exp_heading,
            text="—",
            style="Panel.TLabel",
        )
        self.overview_exp.pack(side=RIGHT, padx=(44, 0))
        self.overview_exp_progress = ttk.Progressbar(
            character, maximum=100, mode="determinate", length=520
        )
        self.overview_exp_progress.grid(
            row=1, column=3, sticky="e", padx=(24, 0), pady=(4, 0)
        )
        character.columnconfigure(3, weight=1)

        stats = ttk.Frame(self.overview_single, style="Workspace.TFrame")
        stats.pack(fill=X, pady=(6, 6))
        self.overview_values = {}
        for column, (key, label) in enumerate(
            (
                ("exp", "EXP atual"),
                ("exp_missing", "EXP faltante"),
                ("credits", "Créditos"),
                ("diamonds", "Diamantes"),
                ("contribution", "Contribuição"),
            )
        ):
            card = ttk.Frame(stats, style="Panel.TFrame", padding=(8, 6))
            card.grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 4, 0),
            )
            ttk.Label(card, text=label, style="PanelMuted.TLabel").pack()
            value = ttk.Label(card, text="—", style="Metric.TLabel")
            value.pack(pady=(3, 0))
            ttk.Label(
                card, text="Confirmado", style="Confirmed.TLabel"
            ).pack(pady=(2, 0))
            self.overview_values[key] = value
            stats.columnconfigure(column, weight=1)

        panel = ttk.Frame(
            self.overview_single, style="AccentPanel.TFrame", padding=10
        )
        panel.pack(fill=BOTH, expand=True)
        session_heading = ttk.Frame(panel, style="PanelBody.TFrame")
        session_heading.pack(fill=X, pady=(0, 6))
        ttk.Label(
            session_heading,
            text="Sessão atual",
            style="PanelTitle.TLabel",
        ).pack(side=LEFT)
        ttk.Button(
            session_heading,
            text="Iniciar subsessão",
            command=lambda: self._select_page(2),
        ).pack(side=RIGHT)
        self.session_since = ttk.Label(
            panel, text="Desde 00:00:00", style="PanelMuted.TLabel"
        )
        self.session_since.pack(anchor="w", pady=(0, 6))
        self.overview_active_subsession = ttk.Label(
            panel,
            text="Subsessão ativa: nenhuma",
            style="Data.TLabel",
        )
        self.overview_active_subsession.pack(anchor="w", pady=(0, 6))
        session_stats = ttk.Frame(panel, style="PanelBody.TFrame")
        session_stats.pack(fill=X)
        for column, (key, label) in enumerate(
            (
                ("kills", "Abates estimados"),
                ("exp_gained", "EXP total"),
                ("exp_hour", "EXP/h"),
                ("exp_hour_percent", "EXP/h (%)"),
                ("credits_hour", "Crédito/h"),
                ("contribution_hour", "Contribuição/h"),
                ("finalizations", "Finalizações"),
                ("loot", "Loot"),
            )
        ):
            card = ttk.Frame(
                session_stats, style="Panel.TFrame", padding=(6, 8)
            )
            card.grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 4, 0),
            )
            ttk.Label(card, text=label, style="PanelMuted.TLabel").pack()
            value = ttk.Label(card, text="—", style="Metric.TLabel")
            value.pack(pady=(5, 0))
            ttk.Label(
                card, text="Confirmado", style="Confirmed.TLabel"
            ).pack(pady=(2, 0))
            self.overview_values[key] = value
            session_stats.columnconfigure(column, weight=1)

        self.info_text = tk.Text(
            self.info_tab,
            height=1,
            width=1,
            state="disabled",
        )
        self.overview_split = ttk.Frame(
            self.info_tab, style="Workspace.TFrame"
        )
        self.split_overviews = []
        for index in range(2):
            card = ttk.Frame(
                self.overview_split,
                style="AccentPanel.TFrame",
                padding=14,
            )
            card.grid(
                row=0,
                column=index,
                sticky="nsew",
                padx=(0 if index == 0 else 5, 5 if index == 0 else 0),
            )
            header = ttk.Frame(card, style="PanelBody.TFrame")
            header.pack(fill=X)
            class_icon = ttk.Label(
                header, text="—", style="Class.TLabel", anchor="center"
            )
            class_icon.pack(side=LEFT, padx=(0, 8))
            rover_icon = ttk.Label(
                header, text="", style="Class.TLabel", anchor="center"
            )
            rover_icon.pack(side=LEFT, padx=(0, 8))
            identity = ttk.Frame(header, style="PanelBody.TFrame")
            identity.pack(side=LEFT, fill=X, expand=True)
            name = ttk.Label(
                identity,
                text=f"Cliente {chr(65 + index)} · aguardando personagem",
                style="PanelTitle.TLabel",
            )
            name.pack(anchor="w")
            equipment = ttk.Label(
                identity, text="Classe — · Rover —", style="PanelMuted.TLabel"
            )
            equipment.pack(anchor="w", pady=(4, 0))
            progress = ttk.Progressbar(card, maximum=100, mode="determinate")
            progress.pack(fill=X, pady=(10, 8))
            metrics_frame = ttk.Frame(card, style="PanelBody.TFrame")
            metrics_frame.pack(fill=X)
            metrics = {}
            for position, (key, label) in enumerate(
                (
                    ("exp", "EXP atual"),
                    ("exp_missing", "EXP faltante"),
                    ("credits", "Créditos"),
                    ("diamonds", "Diamantes"),
                    ("contribution", "Contribuição"),
                    ("kills", "Abates"),
                    ("exp_hour", "EXP/h"),
                    ("credits_hour", "Crédito/h"),
                    ("contribution_hour", "Contribuição/h"),
                    ("loot", "Loot por raridade"),
                )
            ):
                metric = ttk.Frame(
                    metrics_frame, style="Panel.TFrame", padding=(6, 5)
                )
                metric.grid(
                    row=position // 2,
                    column=position % 2,
                    sticky="nsew",
                    padx=(0 if position % 2 == 0 else 4, 0),
                    pady=(0, 4),
                )
                ttk.Label(metric, text=label, style="PanelMuted.TLabel").pack()
                value = ttk.Label(metric, text="—", style="Metric.TLabel")
                value.pack(pady=(2, 0))
                metrics[key] = value
            metrics_frame.columnconfigure(0, weight=1, uniform="split-metric")
            metrics_frame.columnconfigure(1, weight=1, uniform="split-metric")
            subsession = ttk.Label(
                card,
                text="Subsessão ativa: nenhuma",
                style="Confirmed.TLabel",
            )
            subsession.pack(anchor="w", pady=(12, 0))
            self.split_overviews.append(
                {
                    "class_icon": class_icon,
                    "rover_icon": rover_icon,
                    "name": name,
                    "equipment": equipment,
                    "progress": progress,
                    "metrics": metrics,
                    "subsession": subsession,
                }
            )
            self.overview_split.columnconfigure(index, weight=1)
        self.overview_split.rowconfigure(0, weight=1)
        self._overview_split_visible = False
        self.bind("<Configure>", self._sync_overview_layout, add="+")

    def _subsessions_ui(self) -> None:
        heading = ttk.Frame(self.subsessions_tab, style="Workspace.TFrame")
        heading.pack(fill=X)
        ttk.Label(heading, text="Subsessões", style="Title.TLabel").pack(
            side=LEFT
        )
        ttk.Label(
            self.subsessions_tab,
            text="Crie e gerencie subsessões para organizar seus dados.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(3, 8))
        content = ttk.Frame(self.subsessions_tab, style="Workspace.TFrame")
        content.pack(fill=BOTH, expand=True)

        self.subsession_form_toggle = ttk.Button(
            content,
            text="◀",
            width=3,
            style="Quiet.TButton",
            command=self._toggle_subsession_form,
        )
        self.subsession_form_toggle.pack(side=LEFT, fill=Y, padx=(0, 4))
        form = ttk.Frame(content, style="AccentPanel.TFrame", padding=10)
        self.subsession_form = form
        self._subsession_form_visible = True
        form.pack(side=LEFT, fill=Y, padx=(0, 8))
        ttk.Label(form, text="Nova subsessão", style="PanelTitle.TLabel").pack(
            anchor="w", pady=(0, 8)
        )
        self._editing_subsession_id: str | None = None
        self.subsession_client = ttk.Combobox(
            form,
            width=30,
            state="readonly",
            values=("Cliente A", "Cliente B"),
        )
        self.subsession_client.set("Cliente A")
        self.subsession_name = ttk.Entry(form, width=30)
        self.subsession_map = ttk.Combobox(
            form, width=30, state="readonly"
        )
        self.subsession_spot = ttk.Combobox(
            form, width=30, state="readonly"
        )
        self.subsession_mobs = ttk.Frame(form, style="PanelBody.TFrame")
        for column in range(3):
            self.subsession_mobs.columnconfigure(column, weight=1)
        self.subsession_mob_vars: dict[str, tk.BooleanVar] = {}
        self.subsession_select_all = tk.BooleanVar(value=False)
        self.subsession_other_mob = ttk.Entry(form, width=30)
        level_range = ttk.Frame(form, style="PanelBody.TFrame")
        self.subsession_level = ttk.Spinbox(
            level_range, from_=1, to=999, width=7
        )
        self.subsession_level.pack(side=LEFT, fill=X, expand=True)
        ttk.Label(
            level_range, text="até", style="PanelMuted.TLabel"
        ).pack(side=LEFT, padx=6)
        self.subsession_level_to = ttk.Spinbox(
            level_range, from_=1, to=999, width=7
        )
        self.subsession_level_to.pack(side=LEFT, fill=X, expand=True)
        duration = ttk.Frame(form, style="PanelBody.TFrame")
        self.subsession_duration_minutes = tk.IntVar(value=30)
        ttk.Spinbox(
            duration,
            from_=0,
            to=1440,
            increment=5,
            width=7,
            textvariable=self.subsession_duration_minutes,
            command=self._save_preferences,
        ).pack(side=LEFT, fill=X, expand=True)
        ttk.Label(
            duration, text="min", style="PanelMuted.TLabel"
        ).pack(side=LEFT, padx=(6, 0))
        for label, widget in (
            ("Cliente", self.subsession_client),
            ("Mapa", self.subsession_map),
            ("Spot", self.subsession_spot),
            ("Mobs do spot", self.subsession_mobs),
            ("Mob extra", self.subsession_other_mob),
            ("Nível dos mobs", level_range),
            ("Duração (0 = encerrar manualmente)", duration),
            ("Observação (opcional)", self.subsession_name),
        ):
            ttk.Label(form, text=label, style="PanelMuted.TLabel").pack(
                anchor="w", pady=(6, 2)
            )
            widget.pack(fill=X)
        ttk.Checkbutton(
            form,
            text="Selecionar todos os mobs",
            variable=self.subsession_select_all,
            command=self._toggle_all_subsession_mobs,
        ).pack(anchor="w", pady=(4, 0))
        automatic = ttk.Frame(form, style="PanelBody.TFrame")
        ttk.Checkbutton(
            automatic,
            text="Criar a próxima automaticamente",
            variable=self.auto_subsession,
            command=self._save_preferences,
        ).pack(side=LEFT)
        ttk.Label(
            automatic, text="a cada", style="PanelMuted.TLabel"
        ).pack(side=LEFT, padx=(10, 4))
        ttk.Spinbox(
            automatic,
            from_=5,
            to=240,
            increment=5,
            width=6,
            textvariable=self.auto_subsession_minutes,
            command=self._save_preferences,
        ).pack(side=LEFT)
        ttk.Label(automatic, text="min", style="PanelMuted.TLabel").pack(
            side=LEFT, padx=(4, 0)
        )
        ttk.Label(
            form, text="Subsessão automática", style="PanelMuted.TLabel"
        ).pack(anchor="w", pady=(8, 2))
        automatic.pack(fill=X)
        self.subsession_map.bind(
            "<<ComboboxSelected>>", self._subsession_map_changed
        )
        self.subsession_spot.bind(
            "<<ComboboxSelected>>", self._subsession_spot_changed
        )
        self.subsession_start_button = ttk.Button(
            form,
            text="Iniciar subsessão",
            command=self.start_subsession,
        )
        self.subsession_start_button.pack(fill=X, pady=(12, 5))
        self.subsession_end_button = ttk.Button(
            form,
            text="Encerrar subsessão",
            style="Danger.TButton",
            command=self.end_subsession,
        )
        self.subsession_end_button.pack(fill=X)
        timing = ttk.Frame(form, style="PanelBody.TFrame")
        timing.pack(fill=X, pady=(12, 0))
        self.subsession_started = ttk.Label(
            timing, text="Início\n—", style="PanelMuted.TLabel"
        )
        self.subsession_started.pack(side=LEFT)
        self.subsession_ended = ttk.Label(
            timing, text="Fim\n—", style="PanelMuted.TLabel"
        )
        self.subsession_ended.pack(side=RIGHT)

        history = ttk.Frame(
            content, style="AccentPanel.TFrame", padding=10
        )
        self.subsession_history = history
        history.pack(side=LEFT, fill=BOTH, expand=True)
        history_heading = ttk.Frame(history, style="PanelBody.TFrame")
        history_heading.pack(fill=X, pady=(0, 8))
        ttk.Label(
            history_heading,
            text="Histórico de subsessões",
            style="PanelTitle.TLabel",
        ).pack(side=LEFT)
        self.subsession_search = ttk.Entry(history_heading, width=22)
        self.subsession_search.pack(side=RIGHT)
        self.subsession_search.insert(0, "")
        self.subsession_search.bind(
            "<KeyRelease>", lambda _event: self._set_subsession_page(1)
        )
        ttk.Label(
            history_heading, text="Buscar", style="PanelMuted.TLabel"
        ).pack(side=RIGHT, padx=(0, 6))
        self.subsession_page_size = tk.IntVar(value=10)
        page_size = ttk.Combobox(
            history_heading,
            width=4,
            state="readonly",
            textvariable=self.subsession_page_size,
            values=(5, 10, 20, 50),
        )
        page_size.pack(side=RIGHT, padx=(0, 10))
        page_size.bind(
            "<<ComboboxSelected>>", lambda _event: self._set_subsession_page(1)
        )
        ttk.Label(
            history_heading, text="Por página", style="PanelMuted.TLabel"
        ).pack(side=RIGHT, padx=(0, 6))
        self.subsession_filter = tk.StringVar(value="Todas")
        subsession_filter = ttk.Combobox(
            history_heading,
            width=14,
            state="readonly",
            textvariable=self.subsession_filter,
            values=(
                "Todas",
                "Cliente A",
                "Cliente B",
                "Em andamento",
                "Encerradas",
                "Enviadas",
                "Não enviadas",
            ),
        )
        subsession_filter.pack(side=RIGHT, padx=(0, 10))
        subsession_filter.bind(
            "<<ComboboxSelected>>", lambda _event: self._set_subsession_page(1)
        )
        ttk.Label(
            history_heading, text="Exibir", style="PanelMuted.TLabel"
        ).pack(side=RIGHT, padx=(0, 6))
        self._selected_subsession_ids: set[str] = set()
        self.subsession_table = ttk.Treeview(
            history,
            columns=(
                "selected",
                "client",
                "character",
                "location",
                "duration",
                "kills",
                "exp_total",
                "exp_total_percent",
                "exp_hour",
                "exp_hour_percent",
                "credits_hour",
                "contribution_total",
                "contribution_hour",
                "sent",
                "actions",
            ),
            show="headings",
            height=12,
            selectmode="extended",
        )
        for column, label, width in (
            ("selected", "☐", 44),
            ("client", "Cliente", 80),
            ("character", "Personagem", 120),
            ("location", "Localização", 160),
            ("duration", "Duração", 90),
            ("kills", "Mobs (estim.)", 95),
            ("exp_total", "EXP total", 110),
            ("exp_total_percent", "EXP total (%)", 100),
            ("exp_hour", "EXP/h", 100),
            ("exp_hour_percent", "EXP/h (%)", 90),
            ("credits_hour", "Crédito/h", 100),
            ("contribution_total", "Contribuição", 110),
            ("contribution_hour", "Contribuição/h", 110),
            ("sent", "Enviado", 70),
            ("actions", "Ações", 80),
        ):
            self.subsession_table.heading(column, text=label, anchor="center")
            self.subsession_table.column(column, width=width, anchor="center")
        self.subsession_table.bind(
            "<Button-1>", self._toggle_subsession_checkbox, add="+"
        )
        self.subsession_table.bind(
            "<<TreeviewSelect>>", self._sync_subsession_selection, add="+"
        )
        self.subsession_table.pack(fill=BOTH, expand=True)
        subsession_scroll = ttk.Scrollbar(
            history,
            orient="horizontal",
            command=self.subsession_table.xview,
        )
        self.subsession_table.configure(
            xscrollcommand=subsession_scroll.set
        )
        subsession_scroll.pack(fill=X)
        pagination = ttk.Frame(history, style="PanelBody.TFrame")
        pagination.pack(fill=X, pady=(8, 0))
        self.subsession_page = 1
        self.subsession_page_status = ttk.Label(
            pagination, text="Nenhum registro", style="PanelMuted.TLabel"
        )
        self.subsession_page_status.pack(side=LEFT)
        self.subsession_upload_button = ttk.Button(
            pagination,
            text="Enviar selecionadas",
            command=self.send_selected_subsessions,
        )
        self.subsession_upload_button.pack(side=LEFT, padx=(10, 0))
        ttk.Button(
            pagination,
            text="Selecionar visíveis",
            style="Quiet.TButton",
            command=self.toggle_visible_subsessions,
        ).pack(side=LEFT, padx=(8, 0))
        ttk.Button(
            pagination,
            text="Editar",
            style="Quiet.TButton",
            command=self.edit_selected_subsession,
        ).pack(side=LEFT, padx=(8, 0))
        ttk.Button(
            pagination,
            text="Renomear",
            style="Quiet.TButton",
            command=self.rename_selected_subsession,
        ).pack(side=LEFT, padx=(8, 0))
        ttk.Button(
            pagination,
            text="Excluir",
            style="Danger.TButton",
            command=self.delete_selected_subsessions,
        ).pack(side=LEFT, padx=(6, 0))
        page_controls = ttk.Frame(pagination, style="PanelBody.TFrame")
        page_controls.pack(side=RIGHT)
        ttk.Button(
            page_controls,
            text="‹",
            style="Quiet.TButton",
            command=lambda: self._set_subsession_page(
                self.subsession_page - 1
            ),
        ).pack(side=LEFT)
        self.subsession_page_buttons = []
        for page in range(1, 6):
            button = ttk.Button(
                page_controls,
                text=str(page),
                style="Quiet.TButton",
                command=lambda selected=page: self._set_subsession_page(
                    selected
                ),
            )
            button.pack(side=LEFT, padx=1)
            self.subsession_page_buttons.append(button)
        ttk.Button(
            page_controls,
            text="›",
            style="Quiet.TButton",
            command=lambda: self._set_subsession_page(
                self.subsession_page + 1
            ),
        ).pack(side=LEFT)

    def _settings_ui(self) -> None:
        ttk.Label(
            self.settings_tab,
            text="Configurações e envio",
            style="Title.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            self.settings_tab,
            text="Ajuste a leitura, as subsessões e a integração com seu Profile.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(3, 8))
        columns = ttk.Frame(self.settings_tab, style="Workspace.TFrame")
        columns.pack(fill=BOTH, expand=True)

        preferences = ttk.Frame(
            columns, style="AccentPanel.TFrame", padding=10
        )
        preferences.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ttk.Label(
            preferences,
            text="Atualizações",
            style="PanelTitle.TLabel",
        ).pack(anchor="w")
        interval = ttk.Frame(preferences, style="PanelBody.TFrame")
        interval.pack(fill=X, pady=(10, 4))
        ttk.Label(
            interval,
            text="Atualizar informações a cada (s)",
            style="PanelMuted.TLabel",
        ).pack(side=LEFT)
        ttk.Spinbox(
            interval,
            from_=15,
            to=300,
            increment=5,
            width=6,
            textvariable=self.decode_interval,
            command=self._decode_interval_changed,
        ).pack(side=RIGHT)
        names = ttk.Frame(preferences, style="PanelBody.TFrame")
        names.pack(fill=X, pady=(4, 0))
        ttk.Label(
            names,
            text="Idioma dos dados do jogo",
            style="PanelMuted.TLabel",
        ).pack(side=LEFT)
        item_language = ttk.Combobox(
            names,
            state="readonly",
            width=12,
            values=("Português", "English"),
        )
        item_language.set("Português")
        item_language.pack(side=RIGHT)
        item_language.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._item_language_changed(item_language.get()),
        )
        self.item_language_field = item_language

        profile = ttk.Frame(
            columns, style="AccentPanel.TFrame", padding=10
        )
        profile.grid(row=0, column=1, sticky="nsew", padx=(0, 8))
        ttk.Label(
            profile,
            text="Integração com o Profile",
            style="PanelTitle.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            profile,
            text="O token é gerado no site e protegido pelo Windows neste computador.",
            style="PanelMuted.TLabel",
            wraplength=420,
        ).pack(anchor="w", pady=(4, 10))
        self.site_profile_name = ttk.Entry(profile, textvariable=self.profile)
        self.site_profile_token = ttk.Entry(profile, show="•")
        for label, widget in (
            ("Nome do Profile", self.site_profile_name),
            ("Token do Profile", self.site_profile_token),
        ):
            ttk.Label(profile, text=label, style="PanelMuted.TLabel").pack(
                anchor="w", pady=(6, 2)
            )
            widget.pack(fill=X)
        actions = ttk.Frame(profile, style="PanelBody.TFrame")
        actions.pack(fill=X, pady=(12, 6))
        ttk.Button(
            actions,
            text="Validar token",
            command=self.connect_site_profile,
        ).pack(side=LEFT)
        ttk.Button(
            actions,
            text="Revogar localmente",
            style="Quiet.TButton",
            command=self.disconnect_site_profile,
        ).pack(side=LEFT, padx=(8, 0))
        self.site_profile_status = ttk.Label(
            profile,
            text="Não conectado",
            style="PanelMuted.TLabel",
        )
        self.site_profile_status.pack(anchor="w", pady=(4, 14))
        ttk.Button(
            profile,
            text="Exportar e enviar agora",
            command=self.export_and_upload,
        ).pack(fill=X)

        right_column = ttk.Frame(columns, style="Workspace.TFrame")
        right_column.grid(row=0, column=2, sticky="nsew")
        storage = ttk.Frame(
            right_column, style="AccentPanel.TFrame", padding=10
        )
        storage.pack(fill=X)
        ttk.Label(
            storage, text="Armazenamento local", style="PanelTitle.TLabel"
        ).pack(anchor="w")
        self.settings_storage_state = ttk.Label(
            storage,
            text="Calculando tamanho atual…",
            style="PanelMuted.TLabel",
            wraplength=320,
        )
        self.settings_storage_state.pack(anchor="w", pady=(6, 14))
        ttk.Label(
            storage,
            text="Pasta das capturas",
            style="PanelMuted.TLabel",
        ).pack(anchor="w")
        self.capture_directory_state = ttk.Label(
            storage,
            text=str(self.capture_dir),
            style="PanelMuted.TLabel",
            wraplength=320,
        )
        self.capture_directory_state.pack(anchor="w", pady=(2, 6))
        ttk.Button(
            storage,
            text="Escolher pasta",
            style="Quiet.TButton",
            command=self._choose_capture_directory,
        ).pack(fill=X, pady=(0, 12))
        ttk.Label(
            storage,
            text="Retenção dos dados: até exclusão manual",
            style="PanelMuted.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        ttk.Label(
            storage,
            text=(
                "Os dados só são apagados depois de uma exportação "
                "validada e com sua autorização."
            ),
            style="PanelMuted.TLabel",
            wraplength=320,
        ).pack(anchor="w", pady=(0, 10))
        ttk.Checkbutton(
            storage,
            text="Exportar automaticamente ao parar",
            variable=self.auto_export,
            command=self._save_preferences,
        ).pack(anchor="w", pady=(0, 10))
        ttk.Button(
            storage,
            text="Exportar agora",
            command=self.export,
        ).pack(fill=X)
        ttk.Checkbutton(
            storage,
            text="Excluir após exportar",
            variable=self.delete_after_export,
            command=self._save_preferences,
        ).pack(anchor="w", pady=(8, 0))
        privacy = ttk.Frame(
            right_column, style="AccentPanel.TFrame", padding=10
        )
        privacy.pack(fill=X, pady=(8, 0))
        ttk.Label(
            privacy,
            text="Privacidade e segurança",
            style="PanelTitle.TLabel",
        ).pack(anchor="w", pady=(0, 4))
        ttk.Label(
            privacy,
            text=(
                "Payloads sensíveis não são salvos nem enviados. "
                "Somente dados decodificados e autorizados saem deste computador."
            ),
            style="PanelMuted.TLabel",
            wraplength=320,
        ).pack(anchor="w")

        for column, weight in enumerate((3, 4, 5)):
            columns.columnconfigure(column, weight=weight)
        columns.rowconfigure(0, weight=1)

    def _license_ui(self) -> None:
        ttk.Label(
            self.license_tab, text="Licença e suporte", style="Title.TLabel"
        ).pack(anchor="w")
        activation = ttk.Frame(
            self.license_tab,
            style="AccentPanel.TFrame",
            padding=14,
        )
        activation.pack(fill=X, pady=(8, 12))
        ttk.Label(
            activation,
            text=(
                "A ativação fica lembrada neste computador e é preservada nas "
                "atualizações. A chave é enviada uma vez e não fica salva; "
                "a licença valida a cada 24 horas e possui até 24 horas offline."
            ),
            style="PanelMuted.TLabel",
            wraplength=820,
        ).pack(anchor="w", pady=(0, 14))
        self.key_entry = ttk.Entry(activation, show="•")
        self.key_entry.pack(fill=X)
        ttk.Button(
            activation,
            text="Ativar licença",
            command=self.activate,
        ).pack(anchor="w", pady=12)
        self.activation_status = ttk.Label(
            activation,
            text="",
            style="PanelMuted.TLabel",
            wraplength=820,
        )
        self.activation_status.pack(anchor="w")
        ttk.Label(
            activation,
            text="Suporte: Discord Carvalho · carvalho@tuta.com",
            style="PanelMuted.TLabel",
        ).pack(anchor="w", pady=(8, 0))
        ttk.Label(
            activation,
            text=f"Versão instalada: {VERSION} · log técnico ativo",
            style="PanelMuted.TLabel",
        ).pack(anchor="w", pady=(8, 4))
        support_buttons = ttk.Frame(activation, style="PanelBody.TFrame")
        support_buttons.pack(anchor="w")
        ttk.Button(
            support_buttons,
            text="Enviar log técnico",
            style="Quiet.TButton",
            command=self.send_diagnostic,
        ).pack(side=LEFT)
        ttk.Button(
            support_buttons,
            text="Abrir pasta do log",
            style="Quiet.TButton",
            command=self.open_log_folder,
        ).pack(side=LEFT, padx=10)
        ttk.Button(
            support_buttons,
            text="Salvar cópia do log",
            style="Quiet.TButton",
            command=self.save_log_copy,
        ).pack(side=LEFT)
        updates = ttk.Frame(
            self.license_tab, style="AccentPanel.TFrame", padding=14
        )
        updates.pack(fill=X)
        ttk.Label(
            updates, text="Atualizações do programa", style="PanelTitle.TLabel"
        ).pack(anchor="w")
        self.channel = tk.StringVar(value="stable")
        manual_update = UPDATE_MODE == "manual"
        ttk.Radiobutton(
            updates,
            text="Estável",
            value="stable",
            variable=self.channel,
            command=self._save_preferences,
            state="disabled" if manual_update else "normal",
        ).pack(anchor="w", pady=(8, 0))
        ttk.Radiobutton(
            updates,
            text="Beta",
            value="beta",
            variable=self.channel,
            command=self._save_preferences,
            state="disabled" if manual_update else "normal",
        ).pack(anchor="w")
        self.update_button = ttk.Button(
            updates,
            text=("Abrir Discord para atualizações" if manual_update else "Verificar atualização"),
            style="Quiet.TButton",
            command=(lambda: webbrowser.open(DISCORD_URL)) if manual_update else self.check_update,
        )
        self.update_button.pack(anchor="w", pady=(10, 6))
        self.update_progress = ttk.Progressbar(
            updates, mode="determinate", maximum=100
        )
        self.update_progress.pack(fill=X)
        self.update_status = ttk.Label(
            updates,
            text=(
                "Atualização automática desativada. Instale novas versões manualmente."
                if manual_update else ""
            ),
            style="PanelMuted.TLabel",
        )
        self.update_status.pack(anchor="w", pady=(4, 8))
        self.rollback_button = ttk.Button(
            updates,
            text="Rollback somente por instalação manual" if manual_update else "Abrir versão anterior",
            style="Quiet.TButton",
            command=self.rollback,
            state="disabled" if manual_update else "normal",
        )
        self.rollback_button.pack(anchor="w")

    def _tutorial_ui(self) -> None:
        text = (
            "1. Ative esta instalação na aba Licença. A ativação será lembrada nas próximas aberturas.\n\n"
            "2. Abra o RF NEXT. O programa detecta automaticamente até dois clientes e separa as conexões de cada um.\n\n"
            "3. Use os botões Cliente A e Cliente B para alternar a visão. Se o nome não for identificado, use o botão Renomear ao lado do cliente.\n\n"
            "4. Em Envios, use os botões Personagem, Mercado, Codex e Memory Chips para enviar ao site os dados já lidos; eles não iniciam outra captura.\n\n"
            "5. Em Configurações, informe o Profile e o token gerado pelo site. No histórico, selecione subsessões encerradas para enviá-las sem duplicidade.\n\n"
            "6. Cada parada encerra uma sessão independente. Confira o tamanho antes de exportar; depois da exportação validada, o programa pode enviar os segmentos brutos à Lixeira.\n\n"
            "Privacidade: captura passiva limitada às portas conhecidas do RF NEXT e às conexões detectadas do jogo, sem captura geral da rede, injeção, token de sessão, atualização silenciosa ou telemetria."
        )
        ttk.Label(
            self.tutorial_tab, text="Comece em seis passos", style="Title.TLabel"
        ).pack(anchor="w")
        panel = ttk.Frame(
            self.tutorial_tab,
            style="AccentPanel.TFrame",
            padding=14,
        )
        panel.pack(fill=BOTH, expand=True, pady=(8, 0))
        ttk.Label(
            panel,
            text=text,
            wraplength=1000,
            justify=LEFT,
            style="PanelMuted.TLabel",
        ).pack(anchor="w")

    def _load_preferences(self) -> None:
        try:
            self.prefs = json.loads(PREFERENCES_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.prefs = {}
        for obsolete in (
            "character1_pid",
            "character2_pid",
            "capture_pid_uids",
            "capture_port_uids",
        ):
            self.prefs.pop(obsolete, None)
        if "minimize_to_tray" not in self.prefs:
            self.prefs["minimize_to_tray"] = messagebox.askyesno(
                "Comportamento ao fechar",
                "Ao fechar a janela, manter a captura visível na área de notificação?\n\n"
                "Você poderá encerrar pelo ícone RF QOL.",
            )
        self.minimize_to_tray = bool(self.prefs["minimize_to_tray"])
        self.profile.set(str(self.prefs.get("profile", "")))
        self.character1.set(str(self.prefs.get("character1", "")))
        self.character2.set(str(self.prefs.get("character2", "")))
        self._client_ports = [
            tuple(int(port) for port in group)
            for group in self.prefs.get("capture_client_ports", [])
            if isinstance(group, list)
        ][:2]
        self._client_pids = [
            int(pid)
            for pid in self.prefs.get("capture_client_pids", [])
            if isinstance(pid, int)
        ][:2]
        self.auto_export.set(bool(self.prefs.get("auto_export", False)))
        self.delete_after_export.set(
            bool(self.prefs.get("delete_after_export", False))
        )
        self.auto_subsession.set(
            bool(self.prefs.get("auto_subsession", False))
        )
        try:
            automatic_minutes = int(
                self.prefs.get("auto_subsession_minutes", 30)
            )
        except (TypeError, ValueError):
            automatic_minutes = 30
        self.auto_subsession_minutes.set(
            max(5, min(240, automatic_minutes))
        )
        try:
            subsession_minutes = int(
                self.prefs.get("subsession_duration_minutes", 30)
            )
        except (TypeError, ValueError):
            subsession_minutes = 30
        self.subsession_duration_minutes.set(
            max(0, min(1440, subsession_minutes))
        )
        saved_quick_seconds = self.prefs.get("quick_capture_seconds", 10)
        for mode, variable in self.quick_capture_seconds.items():
            try:
                quick_seconds = int(
                    saved_quick_seconds.get(mode, 10)
                    if isinstance(saved_quick_seconds, dict)
                    else saved_quick_seconds
                )
            except (TypeError, ValueError):
                quick_seconds = 10
            variable.set(max(10, min(300, quick_seconds)))
        self._refresh_quick_duration_ui()
        language = (
            "en" if self.prefs.get("item_name_language") == "en" else "pt"
        )
        self.item_name_language.set(language)
        self.item_language_field.set(
            "English" if language == "en" else "Português"
        )
        saved_map = str(self.prefs.get("subsession_map") or "").strip()
        self._refresh_farm_choices(
            saved_map,
            str(self.prefs.get("subsession_spot") or "").strip(),
        )
        if self.site_profile.connected:
            self.profile.set(self.site_profile.profile)
            self.site_profile_status.configure(
                text=f"Conectado ao Profile {self.site_profile.profile}",
                style="Data.TLabel",
            )
        try:
            interval = int(self.prefs.get("decode_interval_seconds", 30))
        except (TypeError, ValueError):
            interval = 30
        self.decode_interval.set(max(15, min(300, interval)))
        self._next_live_decode = (
            time.monotonic() + self.decode_interval.get()
        )
        self.channel.set(
            self.prefs.get("channel")
            if self.prefs.get("channel") in {"stable", "beta"}
            else "stable"
        )
        self._selected_game_path = str(
            self.prefs.get("game_executable") or ""
        )
        if self._selected_game_path:
            display = f"{Path(self._selected_game_path).name} · salvo"
            self._game_choices = {display: self._selected_game_path}
        last_session = str(self.prefs.get("last_session") or "")
        if _capture_prefix(last_session):
            self.current_session = last_session
        try:
            running = self.capture.system_running()
            prefix = str(self.prefs.get("capture_prefix") or "")
            files = (
                tuple(self.capture_dir.glob(f"{prefix}*.etl"))
                if prefix
                else ()
            )
            if running and not files:
                candidates = sorted(
                    self.capture_dir.glob("rfnext-*.etl"),
                    key=lambda path: path.stat().st_mtime_ns,
                    reverse=True,
                )
                if candidates:
                    match = re.match(
                        r"^(rfnext-\d{8}-\d{6}-\d{3})\d*\.etl$",
                        candidates[0].name,
                    )
                    if not match:
                        match = re.match(
                            r"^(rfnext-\d{8}-\d{6})\d+\.etl$",
                            candidates[0].name,
                        )
                    prefix = match.group(1) if match else ""
                    files = (
                        tuple(self.capture_dir.glob(f"{prefix}*.etl"))
                        if prefix
                        else ()
                    )
            if prefix and files and (
                running or bool(self.prefs.get("capture_pending"))
            ):
                match = re.match(
                    r"^rfnext-(\d{8}-\d{6})-(\d{3})$", prefix
                )
                if match and _capture_prefix(self.current_session or "") != prefix:
                    profile = _safe_name(
                        self.profile.get().strip(), "Profile"
                    )
                    self.current_session = (
                        f"{profile}-{match.group(1)}-{int(match.group(2)):03d}"
                    )
                else:
                    legacy = re.match(r"^rfnext-(\d{8}-\d{6})$", prefix)
                    if legacy and legacy.group(1) not in (
                        self.current_session or ""
                    ):
                        profile = _safe_name(
                            self.profile.get().strip(), "Profile"
                        )
                        counter = int(self.prefs.get("session_counter", 0))
                        self.current_session = (
                            f"{profile}-{legacy.group(1)}-{counter:03d}"
                        )
                status = self.capture.attach(
                    prefix, tuple(self.prefs.get("capture_ports") or ())
                )
                self.last_files = list(status.files)
                self.prefs.update(
                    capture_prefix=prefix,
                    capture_pending=True,
                )
                self.capture_state.configure(
                    text=(
                        f"Captura pendente recuperada · {len(status.files)} "
                        "segmento(s) · clique Parar para analisar"
                    )
                )
                self.log.info(
                    "capture_recovered active=%s segments=%d",
                    status.active,
                    len(status.files),
                )
                self._recover_pending_character_uid(tuple(status.files))
        except Exception:
            self.log.exception("capture_recovery_failed")
        self._save_preferences()
        self.after(250, lambda: self.refresh_game_choices(False))

    def _save_preferences(self) -> None:
        self.prefs.update(
            {
                "profile": self.profile.get().strip(),
                "character1": self.character1.get().strip(),
                "character2": self.character2.get().strip(),
                "auto_export": self.auto_export.get(),
                "delete_after_export": self.delete_after_export.get(),
                "decode_interval_seconds": self._decode_interval_seconds(),
                "item_name_language": self.item_name_language.get(),
                "channel": self.channel.get(),
                "last_session": self.current_session,
                "game_executable": self._selected_game_path,
                "capture_directory": str(self.capture_dir),
                "auto_subsession": self.auto_subsession.get(),
                "auto_subsession_minutes": max(
                    5, min(240, int(self.auto_subsession_minutes.get()))
                ),
                "subsession_duration_minutes": max(
                    0, min(1440, int(self.subsession_duration_minutes.get()))
                ),
                "subsession_map": self.subsession_map.get().strip(),
                "subsession_spot": self.subsession_spot.get().strip(),
                "quick_capture_seconds": {
                    mode: self._quick_capture_duration(mode)
                    for mode in self.quick_capture_seconds
                },
            }
        )
        shortcuts = self.prefs.get("shortcuts")
        if isinstance(shortcuts, dict):
            self.prefs["shortcuts"] = {
                mode: value
                for mode, value in shortcuts.items()
                if str(mode).startswith("monitor_")
            }
        PREFERENCES_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = PREFERENCES_PATH.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self.prefs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, PREFERENCES_PATH)

    def _choose_capture_directory(self) -> None:
        if self._capture_is_active() or self.prefs.get("capture_pending"):
            return messagebox.showwarning(
                "Pasta das capturas",
                "Pare e conclua a leitura da captura atual antes de trocar a pasta.",
            )
        selected = filedialog.askdirectory(
            title="Escolha a pasta das capturas",
            initialdir=str(self.capture_dir),
        )
        if not selected:
            return
        try:
            destination = Path(selected).resolve()
            destination.mkdir(parents=True, exist_ok=True)
            shutil.disk_usage(destination)
        except OSError as error:
            self.log.warning(
                "capture_directory_rejected reason=%s",
                _safe_error_code(error),
            )
            return messagebox.showerror(
                "Pasta das capturas",
                "Não foi possível usar a pasta selecionada.",
            )
        if destination == self.capture_dir:
            return
        self.capture_dir = destination
        self.capture = PktmonCapture(destination)
        self.capture_directory_state.configure(text=str(destination))
        self._save_preferences()
        self.log.info("capture_directory_changed")

    def _decode_interval_seconds(self) -> int:
        try:
            return max(15, min(300, int(self.decode_interval.get())))
        except (tk.TclError, TypeError, ValueError):
            return 30

    def _decode_interval_changed(self, _event=None) -> None:
        interval = self._decode_interval_seconds()
        self.decode_interval.set(interval)
        self._next_live_decode = time.monotonic() + interval
        self._save_preferences()

    def _item_language_changed(self, label: str) -> None:
        old_language = self.item_name_language.get()
        new_language = "en" if label == "English" else "pt"
        current = (
            self.subsession_map.get().strip(),
            self.subsession_spot.get().strip(),
        )
        translated = (
            FARM_LABELS_PT_EN.get(current, current)
            if old_language == "pt" and new_language == "en"
            else FARM_LABELS_EN_PT.get(current, current)
            if old_language == "en" and new_language == "pt"
            else current
        )
        self.item_name_language.set(new_language)
        self._refresh_farm_choices(*translated)
        self._save_preferences()
        self._refresh_info()

    def _capture_summary_for_language(
        self,
        envelope: dict,
        character_uid: str | None = None,
        character_name: str = "",
    ) -> tuple[dict, dict[str, list[int]]]:
        return _capture_summary(
            envelope,
            character_uid,
            character_name,
            item_names=self._selected_item_names(),
            game_language=self.item_name_language.get(),
        )

    def _selected_item_names(self) -> dict[str, str]:
        return item_names_for_language(self.item_name_language.get())

    def _selected_farm_catalog(
        self,
    ) -> dict[str, dict[str, dict[str, tuple[int, ...]]]]:
        return (
            FARM_CATALOG_EN
            if self.item_name_language.get() == "en"
            else FARM_CATALOG
        )

    def _refresh_farm_choices(
        self, preferred_map: str = "", preferred_spot: str = ""
    ) -> None:
        catalog = self._selected_farm_catalog()
        maps = tuple(sorted(catalog, key=str.casefold))
        self.subsession_map.configure(values=maps)
        self.subsession_map.set(
            preferred_map
            if preferred_map in catalog
            else maps[0] if maps else ""
        )
        self._subsession_map_changed(preferred_spot=preferred_spot)

    def _quick_capture_duration(self, mode: str) -> int:
        try:
            return max(
                10,
                min(300, int(self.quick_capture_seconds[mode].get())),
            )
        except (tk.TclError, TypeError, ValueError):
            return 10

    def _refresh_quick_duration_ui(self) -> None:
        self.quick_duration_label.configure(
            text="Envia os dados já lidos pela captura contínua"
        )
        for mode, label in (
            ("character", "Personagem"),
            ("market", "Mercado"),
            ("codex", "Codex"),
            ("memory_chips", "Memory Chips"),
        ):
            self.queue_mode_labels[mode].configure(
                text=f"• {label}"
            )

    def _quick_duration_changed(self, mode: str) -> None:
        self.quick_capture_seconds[mode].set(
            self._quick_capture_duration(mode)
        )
        self._refresh_quick_duration_ui()
        self._save_preferences()

    def send_mode_now(
        self,
        mode: str,
        client_index: int | None = None,
        *,
        notify: bool = True,
    ) -> None:
        if not self._authorize_or_warn("enviar dados", "Envio bloqueado"):
            return
        if mode not in self.quick_mode_labels:
            return
        if self._send_uploading or self._pending_send_mode:
            self.quick_mode_labels[mode].configure(text="Envio em andamento")
            if notify:
                return messagebox.showwarning(
                    "Envio", "Aguarde o envio atual terminar."
                )
            return
        if not self.site_profile.connected:
            self.quick_mode_labels[mode].configure(text="Token não validado")
            if notify:
                return messagebox.showwarning(
                    "Envio", "Valide o token do Profile antes de enviar."
                )
            return
        if not self.current_session:
            self.quick_mode_labels[mode].configure(text="Sem sessão")
            if notify:
                return messagebox.showwarning(
                    "Envio", "Ainda não existem dados de uma sessão para enviar."
                )
            return
        target_index = self._active_client_index if client_index is None else client_index
        target_label = (
            "Mercado geral"
            if mode == "market"
            else f"Cliente {chr(65 + target_index)}"
        )
        self.quick_mode_labels[mode].configure(
            text=f"Atualizando {target_label}…"
        )
        if self._capture_is_active() and self._live_capture:
            self._pending_send_mode = mode
            self._pending_send_client_index = client_index
            self._pending_send_notify = notify
            self._next_live_decode = 0
            self._maybe_decode_live()
            if self._live_ingesting:
                return
            self._pending_send_mode = None
            self._pending_send_client_index = None
            self._pending_send_notify = True
        if client_index is None:
            self._send_mode_snapshot(mode, notify=notify)
        else:
            self._send_mode_snapshot(mode, client_index, notify=notify)

    def _send_mode_snapshot(
        self,
        mode: str,
        client_index: int | None = None,
        *,
        notify: bool = True,
    ) -> None:
        session_id = self.current_session
        if not session_id:
            return
        profile = self.site_profile.profile
        character = ""
        uid = None
        metadata = {
            "profile": profile,
            "character_name": "",
            "installation_id": self.license.installation_id,
            "license_lease": self.license.lease,
            "app_version": VERSION,
            "capture_mode": mode,
            "captured_at": datetime.now().astimezone().isoformat(),
        }
        if mode == "market":
            envelope = self.store.session_envelope(
                session_id, None, include_unassigned=True
            )
            try:
                rows = _market_rows(envelope, self._selected_item_names())
            except DecodeError:
                rows = []
            if not rows:
                self.quick_mode_labels[mode].configure(text="Sem dados")
                if notify:
                    return messagebox.showinfo(
                        "Envio", "Ainda não existem eventos de Mercado para enviar."
                    )
                return
            payload = {"metadata": metadata, "rows": rows}
        else:
            candidates = [
                item for item in self._character_exports() if item.get("uid")
            ]
            selected_index = (
                self._active_client_index
                if client_index is None
                else client_index
            )
            client_key = f"client:{chr(97 + selected_index)}"
            selected = next(
                (
                    item
                    for item in candidates
                    if item.get("client_key") == client_key
                ),
                next(
                    (
                        item
                        for item in candidates
                        if client_index is None
                        and item["uid"] == self.active_character_uid
                    ),
                    candidates[0] if len(candidates) == 1 else None,
                ),
            )
            if not selected:
                self.quick_mode_labels[mode].configure(text="Sem personagem")
                if notify:
                    return messagebox.showwarning(
                        "Envio",
                        "O cliente selecionado ainda não possui personagem identificado.",
                    )
                return
            uid = str(selected["uid"])
            character = str(selected["name"])
            envelope = self.store.session_envelope(
                session_id,
                uid,
                bool(selected["include_unassigned"]),
                bool(selected["only_unassigned"]),
            )
            summary, _marks = self._capture_summary_for_language(
                envelope, uid, character
            )
            metadata["character_name"] = character
            metadata["marks_mode"] = "merge"
            profile_data = {
                "profile": profile,
                "name": character,
                "character_uid": uid,
            }
            if mode == "character":
                profile_data["className"] = summary["character_class"]
                profile_data["loadout"] = summary["loadout"]
            else:
                requested_types = {1} if mode == "codex" else {2}
                marks, seen_types = _collection_marks(
                    envelope, requested_types
                )
                if not marks:
                    self.quick_mode_labels[mode].configure(text="Sem dados")
                    if notify:
                        return messagebox.showinfo(
                            "Envio",
                            "Ainda não existem dados deste tipo para enviar.",
                        )
                    return
                profile_data["marks"] = marks
                profile_data["collection_types"] = sorted(
                    requested_types.intersection(seen_types)
                )
            payload = {
                "metadata": metadata,
                "profiles": [profile_data],
                "capture": summary if mode == "character" else {},
                "loadout": summary["loadout"] if mode == "character" else {},
                "subsession_reports": [],
            }
        stable_payload = {
            **payload,
            "metadata": {
                key: value
                for key, value in payload["metadata"].items()
                if key != "captured_at"
            },
        }
        key = hashlib.sha256(
            json.dumps(
                {
                    "session_id": session_id,
                    "mode": mode,
                    "payload": stable_payload,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        self._send_uploading = True
        target_label = "Mercado geral" if mode == "market" else f"Cliente {chr(65 + selected_index)}"
        self.quick_mode_labels[mode].configure(text=f"Enviando {target_label}…")

        def done(result, error):
            self._send_uploading = False
            if error:
                self.quick_mode_labels[mode].configure(text="Falha no envio")
                self.log.warning(
                    "snapshot_upload_failed mode=%s reason=%s",
                    mode,
                    _safe_error_code(error),
                )
                if notify:
                    return messagebox.showerror("Envio falhou", str(error))
                return
            sent_at = datetime.now().strftime("%H:%M:%S")
            self.quick_mode_labels[mode].configure(text=f"{target_label} enviado")
            self.queue_mode_times[mode].configure(text=sent_at)
            self.log.info(
                "snapshot_upload_completed mode=%s character_uid=%s receipt=%s",
                mode,
                uid or "",
                result.get("receipt", ""),
            )

        self._run(
            lambda: self.site_profile.upload_live(mode, payload, key),
            done,
        )

    def quick_capture(self, mode: str) -> None:
        if mode not in self.quick_mode_labels:
            return
        if self._active_quick_mode:
            return messagebox.showwarning(
                "Captura rápida",
                "Aguarde a captura rápida atual terminar.",
            )
        if not self._capture_is_active():
            return messagebox.showwarning(
                "Captura rápida",
                "Inicie a captura contínua de EXP e Loot primeiro.",
            )
        self._active_quick_mode = mode
        started_ns = time.time_ns()
        character_uid = self.active_character_uid
        duration = self._quick_capture_duration(mode)

        def tick(remaining: int) -> None:
            if self._active_quick_mode != mode:
                return
            self.quick_mode_labels[mode].configure(
                text=f"Capturando · {remaining:02d} s"
            )
            if remaining:
                self.after(1000, lambda: tick(remaining - 1))
                return
            self.store.add_capture_window(
                self.current_session,
                mode,
                started_ns,
                time.time_ns(),
                character_uid,
            )
            self._active_quick_mode = None
            self.quick_mode_labels[mode].configure(
                text="Concluída"
            )
            if mode in self.queue_mode_times:
                self.queue_mode_times[mode].configure(
                    text=datetime.now().strftime("%H:%M:%S")
                )
            self._next_live_decode = 0
            self._maybe_decode_live()
            self.log.info("quick_capture_completed mode=%s", mode)

        tick(duration)

    def _subsession_map_changed(
        self, _event=None, preferred_spot: str = ""
    ) -> None:
        catalog = self._selected_farm_catalog()
        spots = tuple(
            sorted(
                catalog.get(self.subsession_map.get().strip(), {}),
                key=str.casefold,
            )
        )
        self.subsession_spot.configure(values=spots)
        current = preferred_spot or self.subsession_spot.get().strip()
        self.subsession_spot.set(
            current if current in spots else spots[0] if spots else ""
        )
        self._subsession_spot_changed()

    def _subsession_spot_changed(self, _event=None) -> None:
        mobs = self._selected_farm_catalog().get(
            self.subsession_map.get().strip(), {}
        ).get(self.subsession_spot.get().strip(), {})
        self._set_subsession_mob_choices(mobs)

    def _set_subsession_mob_choices(self, mobs) -> None:
        for child in self.subsession_mobs.winfo_children():
            child.destroy()
        self.subsession_mob_vars = {}
        self.subsession_select_all.set(False)
        for index, mob in enumerate(mobs):
            name = re.sub(r"^\s*(?:\[?\d+\]?\s*[-:|]\s*)+", "", str(mob)).strip()
            if not name:
                continue
            variable = tk.BooleanVar(value=False)
            self.subsession_mob_vars[str(mob)] = variable
            ttk.Checkbutton(
                self.subsession_mobs,
                text=name,
                variable=variable,
                command=self._subsession_mobs_changed,
            ).grid(row=index // 3, column=index % 3, sticky="w", padx=(0, 10))

    def _toggle_all_subsession_mobs(self) -> None:
        selected = self.subsession_select_all.get()
        for variable in self.subsession_mob_vars.values():
            variable.set(selected)
        self._subsession_mobs_changed()

    def _toggle_subsession_form(self) -> None:
        if self._subsession_form_visible:
            self.subsession_form.pack_forget()
            self.subsession_form_toggle.configure(text="▶")
        else:
            self.subsession_form.pack(
                side=LEFT,
                before=self.subsession_history,
                fill=Y,
                padx=(0, 8),
            )
            self.subsession_form_toggle.configure(text="◀")
        self._subsession_form_visible = not self._subsession_form_visible

    def _selected_subsession_mobs(self) -> list[str]:
        return [
            mob for mob, variable in self.subsession_mob_vars.items()
            if variable.get()
        ]

    def _subsession_mobs_changed(self, _event=None) -> None:
        spot_catalog = self._selected_farm_catalog().get(
            self.subsession_map.get().strip(), {}
        ).get(self.subsession_spot.get().strip(), {})
        levels = [
            level
            for mob in self._selected_subsession_mobs()
            for level in spot_catalog.get(mob, ())
        ]
        if not levels:
            return
        for field, value in (
            (self.subsession_level, min(levels)),
            (self.subsession_level_to, max(levels)),
        ):
            field.delete(0, END)
            field.insert(0, str(value))

    def start_subsession(self) -> None:
        if not self._capture_is_active():
            return messagebox.showwarning(
                "Subsessão",
                "Inicie a captura contínua antes de criar uma subsessão.",
            )
        map_name = self.subsession_map.get().strip()
        spot_name = self.subsession_spot.get().strip()
        if not map_name or not spot_name:
            return messagebox.showwarning(
                "Subsessão", "Selecione o mapa e o spot."
            )
        name = self.subsession_name.get().strip() or spot_name
        mobs = self._selected_subsession_mobs()
        other_mob = self.subsession_other_mob.get().strip()
        if other_mob:
            mobs.append(other_mob)
        try:
            level_from = int(self.subsession_level.get())
            level_to = int(self.subsession_level_to.get() or level_from)
        except (tk.TclError, ValueError):
            level_from = level_to = 0
        if level_from and level_to and level_from > level_to:
            return messagebox.showwarning(
                "Subsessão",
                "O nível inicial dos mobs não pode ser maior que o final.",
            )
        catalog_mobs = self._selected_farm_catalog().get(
            map_name, {}
        ).get(spot_name, {})
        manual_level = (
            level_from
            if level_from == level_to
            else f"{level_from}-{level_to}"
        )
        levels = {}
        for mob in mobs:
            known = catalog_mobs.get(mob, ())
            if known:
                levels[mob] = (
                    known[0]
                    if len(known) == 1
                    else f"{known[0]}-{known[-1]}"
                )
            elif 1 <= level_from <= level_to <= 999:
                levels[mob] = manual_level
        identifier = (
            f"{_safe_name(self.current_session, 'sessao')}-sub-"
            f"{time.time_ns()}"
        )
        try:
            duration_minutes = max(
                0, min(1440, int(self.subsession_duration_minutes.get()))
            )
        except (tk.TclError, TypeError, ValueError):
            duration_minutes = 0
        client_index = 1 if self.subsession_client.get().endswith("B") else 0
        client_key = f"client:{chr(97 + client_index)}"
        character_uid = self._client_uid(client_index)
        try:
            values = dict(
                name=name,
                character_uid=character_uid,
                client_key=client_key,
                location=" > ".join(
                    value for value in (map_name, spot_name) if value
                ),
                map_name=map_name,
                spot_name=spot_name,
                mobs=mobs,
                mob_levels=levels,
                duration_minutes=duration_minutes,
            )
            if self._editing_subsession_id:
                self.store.update_subsession(
                    self._editing_subsession_id, **values
                )
            else:
                self.store.start_subsession(
                    identifier,
                    self.current_session,
                    started_ns=time.time_ns(),
                    **values,
                )
        except ValueError as error:
            return messagebox.showwarning("Subsessão", str(error))
        self._editing_subsession_id = None
        self.subsession_start_button.configure(text="Iniciar subsessão")
        self.subsession_other_mob.delete(0, END)
        self._save_preferences()
        self._refresh_info()

    def end_subsession(self) -> None:
        client_index = 1 if self.subsession_client.get().endswith("B") else 0
        client_key = f"client:{chr(97 + client_index)}"
        active = next(
            (
                item
                for item in self.store.subsessions(self.current_session or "")
                if item["ended_ns"] is None
                and (
                    item.get("client_key") == client_key
                    or (
                        not item.get("client_key")
                        and item["character_uid"] == self._client_uid(client_index)
                    )
                )
            ),
            None,
        )
        if not active:
            return messagebox.showinfo(
                "Subsessão", "Não existe subsessão ativa neste cliente."
            )
        self.store.end_subsession(active["id"], time.time_ns())
        self._refresh_info()

    def toggle_visible_subsessions(self) -> None:
        visible = set(self.subsession_table.get_children())
        if not visible:
            return
        if visible.issubset(self._selected_subsession_ids):
            self._selected_subsession_ids.difference_update(visible)
            self.subsession_table.selection_remove(*visible)
        else:
            self._selected_subsession_ids.update(visible)
            self.subsession_table.selection_set(visible)
        self._render_subsession_checks()

    def _toggle_subsession_checkbox(self, event) -> str | None:
        if self.subsession_table.identify_column(event.x) != "#1":
            return None
        identifier = self.subsession_table.identify_row(event.y)
        if not identifier:
            return "break"
        if identifier in self._selected_subsession_ids:
            self._selected_subsession_ids.remove(identifier)
            self.subsession_table.selection_remove(identifier)
        else:
            self._selected_subsession_ids.add(identifier)
            self.subsession_table.selection_add(identifier)
        self._render_subsession_checks()
        return "break"

    def _sync_subsession_selection(self, _event=None) -> None:
        visible = set(self.subsession_table.get_children())
        self._selected_subsession_ids.difference_update(visible)
        self._selected_subsession_ids.update(self.subsession_table.selection())
        self._render_subsession_checks()

    def _render_subsession_checks(self) -> None:
        for identifier in self.subsession_table.get_children():
            self.subsession_table.set(
                identifier,
                "selected",
                "☑" if identifier in self._selected_subsession_ids else "☐",
            )

    def edit_selected_subsession(self) -> None:
        selected = tuple(self._selected_subsession_ids)
        if len(selected) != 1:
            return messagebox.showinfo(
                "Subsessão", "Selecione uma única subsessão para editar."
            )
        item = next(
            (
                value
                for value in self.store.subsessions(self.current_session or "")
                if value["id"] == selected[0]
            ),
            None,
        )
        if not item:
            return
        self._editing_subsession_id = item["id"]
        self.subsession_client.set(
            "Cliente B" if item.get("client_key") == "client:b" else "Cliente A"
        )
        self.subsession_map.set(item.get("map_name") or "")
        self._subsession_map_changed()
        self.subsession_spot.set(item.get("spot_name") or "")
        self._subsession_spot_changed()
        selected_mobs = set(item.get("mobs") or [])
        for mob, variable in self.subsession_mob_vars.items():
            variable.set(mob in selected_mobs)
        known_mobs = set(self.subsession_mob_vars)
        self.subsession_other_mob.delete(0, END)
        self.subsession_other_mob.insert(
            0, ", ".join(sorted(selected_mobs - known_mobs))
        )
        levels = list((item.get("mob_levels") or {}).values())
        numeric = [value for value in levels if isinstance(value, int)]
        if numeric:
            for field, value in (
                (self.subsession_level, min(numeric)),
                (self.subsession_level_to, max(numeric)),
            ):
                field.delete(0, END)
                field.insert(0, str(value))
        self.subsession_duration_minutes.set(item.get("duration_minutes") or 0)
        self.subsession_name.delete(0, END)
        self.subsession_name.insert(0, item["name"])
        self.subsession_start_button.configure(text="Salvar alterações")

    def rename_selected_subsession(self) -> None:
        selected = tuple(self._selected_subsession_ids)
        if len(selected) != 1:
            return messagebox.showinfo(
                "Subsessão", "Selecione uma única subsessão para renomear."
            )
        current = next(
            (
                item for item in self.store.subsessions(self.current_session or "")
                if item["id"] == selected[0]
            ),
            None,
        )
        if not current:
            return
        name = simpledialog.askstring(
            "Renomear subsessão", "Nome da subsessão:", initialvalue=current["name"]
        )
        if name is None:
            return
        try:
            self.store.rename_subsession(selected[0], name)
        except ValueError as error:
            return messagebox.showwarning("Subsessão", str(error))
        self._refresh_info()

    def delete_selected_subsessions(self) -> None:
        selected = tuple(self._selected_subsession_ids)
        if not selected:
            return messagebox.showinfo(
                "Subsessão", "Selecione ao menos uma subsessão para excluir."
            )
        if not messagebox.askyesno(
            "Excluir subsessões",
            f"Excluir {len(selected)} subsessão(ões) localmente? "
            "Os eventos da captura e dados já enviados ao site não serão apagados.",
        ):
            return
        self.store.delete_subsessions(selected)
        self._selected_subsession_ids.difference_update(selected)
        self._refresh_info()

    def _subsession_report(
        self, subsession: dict, character_uid: str | None
    ) -> dict:
        ended_ns = subsession["ended_ns"] or time.time_ns()
        interval_envelope = self.store.interval_envelope(
            self.current_session or "",
            character_uid,
            subsession["started_ns"],
            ended_ns,
        )
        summary, _marks = self._capture_summary_for_language(
            interval_envelope
        )
        seconds = max(
            1,
            int(
                (ended_ns - subsession["started_ns"])
                / 1_000_000_000
            ),
        )
        hours = seconds / 3600
        exp_total_percent = summary["exp_gained_percent"]
        return {
            **subsession,
            "character_uid": character_uid,
            "source_subsession_id": (
                f"{self.license.installation_id}:{subsession['sequence']}"
            ),
            "ended_ns": ended_ns,
            "duration_seconds": seconds,
            "mob_kills_estimated": int(summary.get("kills") or 0),
            "exp_total": summary["exp_gained"],
            "exp_total_percent": exp_total_percent,
            "exp_hour": round(summary["exp_gained"] / hours),
            "exp_hour_percent": (
                exp_total_percent / hours
                if isinstance(exp_total_percent, (int, float))
                else None
            ),
            "summary": summary,
        }

    def send_selected_subsessions(self) -> None:
        if not self._authorize_or_warn("enviar subsessões", "Envio bloqueado"):
            return
        if self._send_uploading:
            return messagebox.showwarning(
                "Envio", "Aguarde o envio atual terminar."
            )
        if not self.site_profile.connected:
            return messagebox.showwarning(
                "Envio", "Valide o token do Profile antes de enviar."
            )
        selected_ids = set(self._selected_subsession_ids)
        if not selected_ids:
            return messagebox.showinfo(
                "Subsessões", "Selecione ao menos uma subsessão encerrada."
            )
        subsessions = {
            item["id"]: item
            for item in self.store.subsessions(self.current_session or "")
            if item["id"] in selected_ids
        }
        if any(not item["ended_ns"] for item in subsessions.values()):
            return messagebox.showwarning(
                "Subsessões",
                "Encerre as subsessões selecionadas antes de enviar.",
            )
        profiles = {
            str(item["uid"]): str(item.get("name") or "").strip()
            for item in self.store.session_profiles(self.current_session or "")
        }
        client_uids = {
            f"client:{chr(97 + index)}": self._client_uid(index)
            for index in range(2)
        }
        jobs = []
        for subsession in subsessions.values():
            uid = (
                client_uids.get(subsession.get("client_key"))
                or subsession.get("character_uid")
            )
            report = self._subsession_report(subsession, uid)
            character = profiles.get(str(uid), "") or str(
                report["summary"].get("character") or ""
            )
            if not uid or not character:
                return messagebox.showwarning(
                    "Subsessões",
                    "Uma subsessão selecionada ainda não possui personagem "
                    "identificado.",
                )
            metadata = {
                "profile": self.site_profile.profile,
                "character_name": character,
                "installation_id": self.license.installation_id,
                "license_lease": self.license.lease,
                "app_version": VERSION,
                "capture_mode": "subsession",
                "captured_at": datetime.fromtimestamp(
                    report["ended_ns"] / 1_000_000_000
                ).astimezone().isoformat(),
                "marks_mode": "merge",
            }
            payload = {
                "metadata": metadata,
                "profiles": [
                    {
                        "profile": self.site_profile.profile,
                        "name": character,
                        "character_uid": uid,
                        "marks": {},
                    }
                ],
                "capture": report["summary"],
                "subsession_reports": [report],
            }
            key = hashlib.sha256(
                (
                    f"{self.site_profile.profile}\0"
                    f"{self.license.installation_id}\0subsession\0"
                    f"{subsession['sequence']}"
                ).encode()
            ).hexdigest()
            jobs.append((subsession["id"], payload, key))
        self._send_uploading = True
        self.subsession_upload_button.configure(state="disabled")

        def upload():
            completed = []
            for identifier, payload, key in jobs:
                try:
                    response = self.site_profile.upload_live(
                        "subsession", payload, key
                    )
                    completed.append((identifier, response, None))
                except Exception as error:
                    completed.append((identifier, None, error))
            return completed

        def done(result, error):
            self._send_uploading = False
            self.subsession_upload_button.configure(state="normal")
            if error:
                return messagebox.showerror("Envio falhou", str(error))
            failures = []
            for identifier, _response, upload_error in result:
                if upload_error:
                    failures.append(str(upload_error))
                else:
                    self.store.set_subsession_upload_state(
                        identifier, "sent"
                    )
            self._refresh_info()
            if failures:
                return messagebox.showwarning(
                    "Envio de subsessões",
                    f"{len(result) - len(failures)} enviada(s); "
                    f"{len(failures)} falharam.\n\n"
                    + "\n".join(failures),
                )
            messagebox.showinfo(
                "Envio de subsessões",
                f"{len(result)} subsessão(ões) enviada(s).",
            )

        self._run(upload, done)

    def _set_subsession_page(self, page: int) -> None:
        self.subsession_page = max(1, page)
        self._refresh_subsessions()

    def _refresh_subsessions(self, snapshot: dict | None = None) -> None:
        if not hasattr(self, "subsession_table"):
            return
        snapshot = snapshot or self._info_snapshot or {}
        if snapshot.get("session_id") != self.current_session:
            self._refresh_info()
            return
        self.subsession_table.delete(*self.subsession_table.get_children())
        profile_names = {
            item["uid"]: item["name"]
            for item in getattr(self, "_current_profiles", [])
        }
        items = list(snapshot.get("subsessions") or [])
        summaries = snapshot.get("subsession_summaries") or {}
        self._selected_subsession_ids.intersection_update(
            item["id"] for item in items
        )
        active_client_key = f"client:{chr(97 + self._active_client_index)}"
        active = next(
            (
                item
                for item in items
                if item["ended_ns"] is None
                and (
                    item.get("client_key") == active_client_key
                    or (
                        not item.get("client_key")
                        and item["character_uid"] == self.active_character_uid
                    )
                )
            ),
            None,
        )
        displayed = active or next(
            (
                item
                for item in items
                if item.get("client_key") == active_client_key
                or (
                    not item.get("client_key")
                    and item["character_uid"] == self.active_character_uid
                )
            ),
            items[0] if items else None,
        )
        self.subsession_started.configure(
            text=(
                "Início\n"
                + datetime.fromtimestamp(
                    displayed["started_ns"] / 1_000_000_000
                ).strftime("%d/%m/%Y %H:%M:%S")
                if displayed
                else "Início\n—"
            )
        )
        self.subsession_ended.configure(
            text=(
                "Fim\n"
                + datetime.fromtimestamp(
                    displayed["ended_ns"] / 1_000_000_000
                ).strftime("%d/%m/%Y %H:%M:%S")
                if displayed and displayed["ended_ns"]
                else "Fim\n—"
            )
        )
        items = _filter_subsessions(items, self.subsession_filter.get())
        query = self.subsession_search.get().strip().casefold()
        if query:
            items = [
                item
                for item in items
                if query
                in " ".join(
                    (
                        str(item.get("name") or ""),
                        str(item.get("location") or ""),
                        " ".join(item.get("mobs") or []),
                        profile_names.get(item.get("character_uid"), ""),
                        str(item.get("client_key") or ""),
                    )
                ).casefold()
            ]
        page_size = int(self.subsession_page_size.get())
        page_count = max(1, (len(items) + page_size - 1) // page_size)
        self.subsession_page = min(self.subsession_page, page_count)
        start = (self.subsession_page - 1) * page_size
        visible = items[start : start + page_size]
        for item in visible:
            end = item["ended_ns"] or time.time_ns()
            duration = max(0, int((end - item["started_ns"]) / 1_000_000_000))
            client_index = 1 if item.get("client_key") == "client:b" else 0
            character_uid = (
                self._client_uid(client_index)
                if item.get("client_key")
                else item["character_uid"]
            )
            summary = summaries.get(item["id"]) or {
                "character": "",
                "exp_gained": 0,
                "exp_gained_percent": None,
                "credits": 0,
                "contribution": None,
                "kills": 0,
            }
            hours = duration / 3600 if duration else 0
            exp_hour = round(summary["exp_gained"] / hours) if hours else 0
            exp_total_percent = summary["exp_gained_percent"]
            exp_hour_percent = (
                exp_total_percent / hours
                if hours and isinstance(exp_total_percent, (int, float))
                else None
            )
            credits_hour = round(summary["credits"] / hours) if hours else 0
            contribution_hour = (
                round(summary["contribution"] / hours)
                if hours
                and isinstance(summary["contribution"], (int, float))
                else None
            )
            self.subsession_table.insert(
                "",
                END,
                iid=item["id"],
                values=(
                    "☑" if item["id"] in self._selected_subsession_ids else "☐",
                    (
                        "Cliente B"
                        if item.get("client_key") == "client:b"
                        else "Cliente A"
                    ),
                    profile_names.get(character_uid)
                    or summary["character"]
                    or "Aguardando UID",
                    item["location"] or "—",
                    f"{duration // 60:02d}:{duration % 60:02d}",
                    f"{int(summary.get('kills') or 0):,}".replace(",", "."),
                    f"{summary['exp_gained']:,.0f}".replace(",", "."),
                    (
                        f"{exp_total_percent:.2f}%".replace(".", ",")
                        if isinstance(exp_total_percent, (int, float))
                        else "—"
                    ),
                    f"{exp_hour:,.0f}".replace(",", "."),
                    (
                        f"{exp_hour_percent:.2f}%".replace(".", ",")
                        if isinstance(exp_hour_percent, (int, float))
                        else "—"
                    ),
                    f"{credits_hour:,.0f}".replace(",", "."),
                    (
                        f"{summary['contribution']:,.0f}".replace(",", ".")
                        if isinstance(summary["contribution"], (int, float))
                        else "—"
                    ),
                    (
                        f"{contribution_hour:,.0f}".replace(",", ".")
                        if isinstance(contribution_hour, (int, float))
                        else "—"
                    ),
                    "Sim" if item["upload_state"] == "sent" else "Não",
                    "Em andamento" if item["ended_ns"] is None else "Pronta",
                ),
            )
        selected_visible = [
            item["id"]
            for item in visible
            if item["id"] in self._selected_subsession_ids
        ]
        if selected_visible:
            self.subsession_table.selection_set(selected_visible)
        for column in self.subsession_table["columns"]:
            heading = self.subsession_table.heading(column).get("text", "")
            values = [
                str(self.subsession_table.set(row["id"], column))
                for row in visible
                if self.subsession_table.exists(row["id"])
            ]
            width = max([len(str(heading)), *(len(value) for value in values)])
            self.subsession_table.column(
                column,
                width=max(70, min(230, width * 8 + 20)),
                anchor="center",
            )
        shown_from = start + 1 if visible else 0
        shown_to = start + len(visible)
        self.subsession_page_status.configure(
            text=(
                f"Mostrando {shown_from} a {shown_to} de "
                f"{len(items)} registro(s)"
            )
        )
        first_page = max(1, min(self.subsession_page - 2, page_count - 4))
        for offset, button in enumerate(self.subsession_page_buttons):
            page = first_page + offset
            button.configure(
                text=str(page) if page <= page_count else "",
                state="normal" if page <= page_count else "disabled",
                style=(
                    "ClientActive.TButton"
                    if page == self.subsession_page
                    else "Quiet.TButton"
                ),
                command=lambda selected=page: self._set_subsession_page(
                    selected
                ),
            )

    def _rotate_auto_subsession(self, items: list[dict] | None = None) -> None:
        if not self.current_session:
            return
        now = time.time_ns()
        automatic = bool(self.auto_subsession.get())
        automatic_minutes = (
            max(5, int(self.auto_subsession_minutes.get()))
            if automatic
            else 0
        )
        items = (
            items
            if items is not None
            else self.store.subsessions(self.current_session)
        )
        def start_next(template: dict) -> None:
            self.store.start_subsession(
                f"{_safe_name(self.current_session, 'sessao')}-sub-"
                f"{now}-{template['character_uid'] or 'geral'}",
                self.current_session,
                template["name"],
                character_uid=template["character_uid"],
                client_key=template.get("client_key", ""),
                location=template["location"],
                map_name=template.get("map_name", ""),
                spot_name=template.get("spot_name", ""),
                mobs=template["mobs"],
                mob_levels=template["mob_levels"],
                duration_minutes=automatic_minutes,
                started_ns=now,
            )

        changed = False
        for active in items:
            if active["ended_ns"] is not None:
                continue
            duration_minutes = int(active.get("duration_minutes") or 0)
            if duration_minutes == 0:
                continue
            elapsed_ns = now - active["started_ns"]
            if elapsed_ns < min(
                duration_minutes,
                automatic_minutes if automatic else duration_minutes,
            ) * 60 * 1_000_000_000:
                continue
            self.store.end_subsession(active["id"], now)
            changed = True
            if automatic:
                start_next(active)
        if changed:
            self._refresh_info()

    def connect_site_profile(self) -> None:
        profile = self.site_profile_name.get().strip()
        token = self.site_profile_token.get().strip()
        if not profile or not token:
            return messagebox.showwarning(
                "Profile", "Informe o nome do Profile e o token gerado no site."
            )
        self.site_profile_status.configure(text="Validando token…")
        self._run(
            lambda: self.site_profile.connect(profile, token),
            self._site_profile_connected,
        )

    def _site_profile_connected(self, result, error) -> None:
        self.site_profile_token.delete(0, END)
        if error:
            return self.site_profile_status.configure(
                text=f"Não foi possível conectar: {error}"
            )
        self.site_profile_status.configure(
            text=f"Conectado ao Profile {result['profile']}",
            style="Data.TLabel",
        )
        self.profile.set(result["profile"])
        self._save_preferences()
        self._upload_pending_quick_captures()

    def disconnect_site_profile(self) -> None:
        self.site_profile.disconnect()
        self.site_profile_token.delete(0, END)
        self.site_profile_status.configure(
            text="Token removido deste computador",
            style="PanelMuted.TLabel",
        )

    def _pending_quick_upload_jobs(self) -> list[dict]:
        if not self.current_session or not self.site_profile.connected:
            return []
        session_id = self.current_session
        profiles = {
            str(item.get("uid")): str(item.get("name") or "").strip()
            for item in self.store.session_profiles(session_id)
            if item.get("uid")
        }
        jobs = []
        for window in self.store.pending_capture_uploads(session_id):
            mode = window["mode"]
            uid = window.get("character_uid")
            if not uid and len(profiles) == 1:
                uid = next(iter(profiles))
            character = profiles.get(str(uid), "") if uid else ""
            if mode != "market" and not character:
                continue
            envelope = self.store.interval_envelope(
                session_id,
                str(uid) if uid else None,
                window["started_ns"],
                window["ended_ns"],
            )
            key = hashlib.sha256(
                (
                    f"{session_id}\0{mode}\0{window['started_ns']}\0"
                    f"{window['ended_ns']}\0{uid or ''}"
                ).encode()
            ).hexdigest()
            metadata = {
                "profile": self.site_profile.profile,
                "character_name": character,
                "installation_id": self.license.installation_id,
                "license_lease": self.license.lease,
                "app_version": VERSION,
                "capture_mode": mode,
                "captured_at": datetime.fromtimestamp(
                    window["ended_ns"] / 1_000_000_000
                ).astimezone().isoformat(),
            }
            if mode == "market":
                try:
                    rows = _market_rows(
                        envelope, self._selected_item_names()
                    )
                except DecodeError:
                    rows = []
                payload = {"metadata": metadata, "rows": rows}
            else:
                summary, _marks = self._capture_summary_for_language(
                    envelope,
                    str(uid),
                    character,
                )
                profile_data = {
                    "profile": self.site_profile.profile,
                    "name": character,
                    "character_uid": uid,
                }
                if mode == "character":
                    profile_data["className"] = summary["character_class"]
                    profile_data["loadout"] = summary["loadout"]
                    rows = bool(
                        summary["character"]
                        or summary["character_class"]
                        or summary["loadout"]
                    )
                else:
                    requested_types = {1} if mode == "codex" else {2}
                    marks, seen_types = _collection_marks(
                        envelope, requested_types
                    )
                    profile_data["marks"] = marks
                    profile_data["collection_types"] = sorted(
                        requested_types.intersection(seen_types)
                    )
                    rows = marks
                payload = {
                    "metadata": {**metadata, "marks_mode": "merge"},
                    "profiles": [profile_data],
                    "capture": summary if mode == "character" else {},
                    "loadout": (
                        summary["loadout"] if mode == "character" else {}
                    ),
                    "subsession_reports": [],
                }
            if not rows:
                self.store.set_capture_upload_state(
                    session_id,
                    mode,
                    window["started_ns"],
                    "empty",
                )
                if mode in self.queue_mode_times:
                    self.queue_mode_times[mode].configure(text="Sem dados")
                continue
            jobs.append(
                {
                    "session_id": session_id,
                    "mode": mode,
                    "started_ns": window["started_ns"],
                    "key": key,
                    "payload": payload,
                }
            )
        return jobs

    def _upload_pending_quick_captures(self) -> None:
        if self._quick_uploading:
            return
        jobs = self._pending_quick_upload_jobs()
        if not jobs:
            return
        self._quick_uploading = True

        def upload():
            completed = []
            for job in jobs:
                try:
                    result = self.site_profile.upload_live(
                        job["mode"],
                        job["payload"],
                        job["key"],
                    )
                    completed.append((job, result, None))
                except Exception as error:
                    completed.append((job, None, error))
            return completed

        def done(result, error):
            self._quick_uploading = False
            if error:
                self.log.warning(
                    "quick_upload_failed reason=%s",
                    _safe_error_code(error),
                )
                return
            for job, _response, upload_error in result:
                mode = job["mode"]
                if upload_error:
                    self.log.warning(
                        "quick_upload_pending mode=%s reason=%s",
                        mode,
                        _safe_error_code(upload_error),
                    )
                    if mode in self.queue_mode_times:
                        self.queue_mode_times[mode].configure(
                            text="Envio pendente"
                        )
                    continue
                self.store.set_capture_upload_state(
                    job["session_id"],
                    mode,
                    job["started_ns"],
                    "sent",
                )
                if mode in self.queue_mode_times:
                    self.queue_mode_times[mode].configure(
                        text=f"Enviado {datetime.now():%H:%M:%S}"
                    )
                self.log.info("quick_upload_completed mode=%s", mode)

        self._run(upload, done)

    def export_and_upload(self) -> None:
        if not self._authorize_or_warn("exportar e enviar", "Envio bloqueado"):
            return
        if self._capture_is_active():
            return messagebox.showwarning(
                "Envio",
                "Encerre a captura antes de exportar e enviar.",
            )
        if not self.site_profile.connected:
            return messagebox.showwarning(
                "Envio", "Valide o token do Profile antes de enviar."
            )
        results = self._export_to(
            self.capture_dir / "Exportados", offer_cleanup=False
        )
        if not results:
            return
        self.site_profile_status.configure(text="Enviando dados…")

        def upload():
            return [
                self.site_profile.upload(result.json_path, result.sha256)
                for result in results
            ]

        self._run(upload, self._upload_completed)

    def _upload_completed(self, result, error) -> None:
        if error:
            return self.site_profile_status.configure(
                text=f"Envio não concluído: {error}"
            )
        self.site_profile_status.configure(
            text=f"{len(result)} arquivo(s) enviado(s) com sucesso",
            style="Data.TLabel",
        )

    def _run(self, job, done) -> None:
        def worker():
            try:
                result = job()
                self.after(0, lambda: done(result, None))
            except Exception as error:
                if hasattr(self, "log"):
                    self.log.exception(
                        "background_job_failed job=%s",
                        getattr(job, "__name__", type(job).__name__),
                    )
                self.after(0, lambda error=error: done(None, error))

        threading.Thread(target=worker, daemon=True).start()

    def refresh_game_choices(self, notify: bool = True) -> None:
        try:
            processes = connected_processes()
        except Exception as error:
            self.log.exception(
                "game_connection_discovery_failed reason=%s",
                _safe_error_code(error),
            )
            if notify:
                messagebox.showerror(
                    "Conexão do jogo",
                    "Não foi possível consultar as conexões abertas.",
                )
            return
        choices: dict[str, str] = {}
        for path, (pids, local_ports, _remote_ports) in sorted(
            processes.items(), key=lambda item: Path(item[0]).name.casefold()
        ):
            name = Path(path).name
            if any(label.casefold().startswith(f"{name.casefold()} ·") for label in choices):
                name = f"{name} ({Path(path).parent.name})"
            label = (
                f"{name} · {len(pids)} cliente(s) · "
                f"{len(local_ports)} conexão(ões)"
            )
            choices[label] = path
        if (
            self._selected_game_path
            and self._selected_game_path not in choices.values()
            and not choices
        ):
            choices[
                f"{Path(self._selected_game_path).name} · salvo · desconectado"
            ] = self._selected_game_path
        self._game_choices = choices
        if choices and self._selected_game_path not in choices.values():
            self._selected_game_path = next(iter(choices.values()))
        selected = next(
            (
                label
                for label, path in choices.items()
                if path == self._selected_game_path
            ),
            "",
        )
        if selected:
            local_ports, _remote_ports, clients = ports_for_executable(
                self._selected_game_path
            )
            if not self._capture_is_active():
                self.capture_state.configure(
                    text=(
                        f"{clients} cliente(s) detectado(s) · "
                        f"{len(local_ports)} conexão(ões)"
                        if local_ports
                        else "Aguardando conexão do jogo"
                    )
                )
        elif notify:
            self.capture_state.configure(text="Abra o RF NEXT para iniciar")

    def activate(self) -> None:
        key = self.key_entry.get().strip()
        if not key:
            return messagebox.showwarning("Licença", "Informe a chave recebida.")
        self.activation_status.configure(text="Validando…")
        self._run(
            lambda: self.license.activate(key, VERSION),
            lambda result, error: self._activation_done(result, error),
        )

    def _activation_done(self, claims, error) -> None:
        self.key_entry.delete(0, END)
        if error:
            self.activation_status.configure(
                text=f"Não foi possível ativar: {error}"
            )
            return
        self.activation_status.configure(
            text=f"Instalação ativa até {claims['valid_until']}."
        )
        self._refresh_license()

    def _apply_license_status(self, allowed: bool, message: str) -> None:
        self.capture_allowed = allowed
        self.top_license.configure(
            text=f"• {message}",
            style="TopbarOk.TLabel" if allowed else "Topbar.TLabel",
        )
        self.start_button.configure(
            state="normal"
            if allowed and not self._ingesting
            else "disabled"
        )

    def _license_checked(self, result, error) -> None:
        self._license_refresh_running = False
        allowed, message = (
            (False, f"Falha ao verificar: {type(error).__name__}")
            if error
            else result
        )
        self._apply_license_status(allowed, message)
        if not allowed and self._capture_is_active():
            self._halt_capture_for_license(message)

    def _refresh_license(self) -> tuple[bool, str]:
        allowed, message = self.license.refresh_if_due(VERSION)
        self._apply_license_status(allowed, message)
        return allowed, message

    def _authorize_or_warn(self, capability: str, title: str) -> bool:
        try:
            self.license.require(capability)
            return True
        except PermissionError as error:
            self._apply_license_status(False, str(error))
            messagebox.showwarning(title, str(error))
            return False

    def _halt_capture_for_license(self, message: str) -> None:
        self._close_live_preview()
        try:
            if self.capture.status().active:
                self.capture.stop()
        except Exception as error:
            self.log.exception(
                "license_capture_stop_failed reason=%s", _safe_error_code(error)
            )
        self.prefs["capture_pending"] = True
        self._save_preferences()
        self._apply_license_status(False, message)
        self.capture_state.configure(
            text=(
                "Captura encerrada por licença · arquivos brutos preservados · "
                "nenhuma leitura ou exportação executada"
            )
        )
        self.log.warning("capture_stopped_license_required")

    def _capture_is_active(self) -> bool:
        if not self.current_session:
            return False
        return self._live_capture is not None or self.capture.active

    def _discard_previous_capture(self) -> bool:
        session_id = self.current_session
        files = list(self.capture.segment_files())
        files.extend(self._live_files)
        if session_id:
            files.extend(self.store.session_sources(session_id))
            safe_session = _safe_name(session_id, "sessao")
            files.extend(
                self.capture_dir.glob(f"{safe_session}-cliente-*.pcap")
            )
            files.extend(PREVIEW_DIR.glob(f"{safe_session}-live-*.pcap"))
        files = list(dict.fromkeys(path for path in files if path.exists()))
        if not session_id and not files:
            self.discard_previous.set(False)
            return True
        total = sum(path.stat().st_size for path in files)
        if files:
            if not messagebox.askyesno(
                "Descartar sessão anterior",
                (
                    f"A sessão anterior e {_format_bytes(total)} em arquivos "
                    "serão removidos, mesmo sem decodificação.\n\n"
                    "Os arquivos serão enviados para a Lixeira. Continuar?"
                ),
            ):
                return False
            if self.capture.status().active:
                messagebox.showwarning(
                    "Captura ativa",
                    "Pare a captura antes de descartar a sessão.",
                )
                return False
            if not _recycle(files):
                messagebox.showerror(
                    "Limpeza incompleta",
                    "Não foi possível enviar todos os arquivos para a Lixeira.",
                )
                return False
        try:
            if session_id:
                self.store.clear_session(session_id)
        except Exception as error:
            self.log.exception("previous_session_clear_failed")
            messagebox.showerror(
                "Limpeza incompleta",
                f"Os arquivos foram removidos, mas o histórico não: {error}",
            )
            return False
        self.capture = PktmonCapture(self.capture_dir)
        self.current_session = None
        self.last_files = []
        self._live_files = []
        self._paused = False
        self._paused_at = None
        self.prefs["capture_pending"] = False
        for key in (
            "capture_prefix",
            "capture_ports",
            "capture_decode_ports",
            "last_session",
        ):
            self.prefs.pop(key, None)
        self.discard_previous.set(False)
        self._save_preferences()
        self._refresh_info()
        self.log.info(
            "previous_session_discarded files=%d bytes=%d",
            len(files),
            total,
        )
        return True

    def start_capture(self) -> None:
        allowed, message = self._refresh_license()
        if not allowed:
            return messagebox.showwarning("Captura bloqueada", message)
        if self._ingesting:
            return messagebox.showwarning(
                "Análise em andamento",
                "Aguarde a leitura da captura anterior antes de iniciar outra.",
            )
        if self.discard_previous.get() and not self._discard_previous_capture():
            return
        running = self.capture.status().active
        if self.prefs.get("capture_pending") and self.capture.segment_files():
            self._start_after_ingest = True
            self.capture_state.configure(
                text="Analisando a captura anterior antes de iniciar…"
            )
            self.stop_capture()
            return
        if running:
            try:
                self.capture.stop()
                self.log.info("external_pktmon_stopped_before_capture")
            except Exception as error:
                self.log.exception(
                    "external_pktmon_stop_failed reason=%s",
                    _safe_error_code(error),
                )
                return messagebox.showerror(
                    "Não foi possível preparar a captura", str(error)
                )
        profile = (
            self.profile.get().strip()
            or self.site_profile_name.get().strip()
            or "Profile"
        )
        if not self._selected_game_path:
            self.refresh_game_choices(False)
        if not self._selected_game_path:
            return messagebox.showwarning(
                "Conexão do jogo",
                "Abra um cliente ProjectRF e entre no jogo.",
            )
        local_ports, remote_ports, clients = ports_for_executable(
            self._selected_game_path, DEFAULT_PORTS
        )
        client_connections = clients_for_executable(
            self._selected_game_path, DEFAULT_PORTS
        )
        if not local_ports:
            self.refresh_game_choices(False)
            return messagebox.showwarning(
                "Conexão do jogo",
                "Nenhuma conexão ativa foi encontrada. Entre com o personagem "
                "no jogo e tente novamente.",
            )
        if clients > 2:
            return messagebox.showwarning(
                "Limite de clientes",
                "Foram encontrados mais de dois clientes. Feche os excedentes "
                "antes de iniciar.",
            )
        resuming = bool(self._paused is True and self.current_session)
        counter = int(self.prefs.get("session_counter", 0)) + (
            0 if resuming else 1
        )
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        session_id = (
            self.current_session
            if resuming
            else f"{_safe_name(profile, 'Profile')}-{stamp}-{counter:03d}"
        )
        capture_prefix = f"rfnext-{stamp}-{counter:03d}"
        filter_ports = tuple(
            dict.fromkeys((*local_ports, *remote_ports))
        )
        decode_ports = DEFAULT_PORTS
        try:
            self.capture.start_for_ports(capture_prefix, filter_ports)
        except Exception as error:
            self.log.exception(
                "capture_start_failed reason=%s", _safe_error_code(error)
            )
            return messagebox.showerror("Não foi possível iniciar", str(error))
        self.current_session = session_id
        if resuming and self._paused_at is not None:
            self._paused_total_seconds += max(
                0, int((datetime.now() - self._paused_at).total_seconds())
            )
        elif not resuming:
            self._paused_total_seconds = 0
        self._paused = False
        self._paused_at = None
        self._live_files = []
        self._live_ports = tuple(
            dict.fromkeys((*DEFAULT_PORTS, *filter_ports))
        )
        if resuming:
            self._client_pids, self._client_ports = _merge_client_routes(
                self._client_pids,
                self._client_ports,
                client_connections,
            )
        else:
            self._client_pids, self._client_ports = _merge_client_routes(
                [], [], client_connections
            )
        if not self._client_ports:
            self._client_ports = [tuple(local_ports)]
        self._live_index = 0
        try:
            self._open_live_preview()
        except Exception as error:
            self._live_capture = None
            self.log.warning(
                "live_preview_unavailable reason=%s", _safe_error_code(error)
            )
        self.prefs.update(
            session_counter=counter,
            capture_prefix=capture_prefix,
            capture_pending=True,
            capture_ports=list(filter_ports),
            capture_decode_ports=list(decode_ports),
            capture_client_ports=[list(group) for group in self._client_ports],
            capture_client_pids=self._client_pids,
        )
        self._last_packet_count = 0
        self._next_live_decode = (
            time.monotonic() + self._decode_interval_seconds()
        )
        self._last_live_decode = (
            "Aguardando primeira atualização"
            if self._live_capture
            else "Prévia ao vivo indisponível; exportação normal"
        )
        for obsolete in (
            "character1_pid",
            "character2_pid",
            "capture_pid_uids",
            "capture_port_uids",
            "capture_character_names",
        ):
            self.prefs.pop(obsolete, None)
        try:
            self._save_preferences()
        except OSError:
            self.log.exception("capture_state_save_failed")
        self.log.info(
            "capture_started clients=%d local_connections=%d "
            "remote_ports=%d filters=%d live_filters=%d client_routes=%s",
            clients,
            len(local_ports),
            len(remote_ports),
            len(filter_ports),
            len(self._live_ports),
            [list(group) for group in self._client_ports],
        )
        self.capture_state.configure(
            text=(
                f"Capturando {clients} cliente(s) · "
                f"{len(local_ports)} conexão(ões) · aguardando pacotes"
            )
        )

    def pause_capture(self) -> None:
        if self._paused is True:
            self.start_capture()
            return
        if not self._capture_is_active() or self._ingesting:
            return
        self._pause_requested = True
        self._paused_at = datetime.now()
        self.capture_state.configure(text="Pausando captura…")
        self.stop_capture()

    def stop_capture(self) -> None:
        try:
            self.license.require("ler captura encerrada")
        except PermissionError as error:
            self._halt_capture_for_license(str(error))
            return
        if self._ingesting:
            return
        if self._live_ingesting is True:
            self._stop_after_live_ingest = True
            self.capture_state.configure(
                text="Finalizando a leitura atual antes de parar…"
            )
            return
        if self._paused is True:
            self._paused = False
            self._paused_at = None
            self.capture_state.configure(text="Captura encerrada")
            self._refresh_info()
            return
        if not self.current_session:
            try:
                running = self.capture.status().active
            except Exception as error:
                return messagebox.showerror("Falha ao consultar PktMon", str(error))
            if not running:
                return messagebox.showwarning(
                    "Sessão", "Não existe sessão atual para encerrar."
                )
            if not messagebox.askyesno(
                "PktMon externo ativo",
                "O PktMon está ativo sem uma sessão reconhecida pelo programa. "
                "Deseja encerrá-lo? Nenhum arquivo será apagado.",
            ):
                return
            try:
                self.capture.stop()
                self.capture_state.configure(
                    text="PktMon externo encerrado · nenhum arquivo foi apagado"
                )
            except Exception as error:
                messagebox.showerror("Falha ao parar", str(error))
            return
        self._ingesting = True
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="disabled")
        try:
            now = time.time_ns()
            subsessions = self.store.subsessions(self.current_session)
            for subsession in subsessions if isinstance(subsessions, list) else ():
                if subsession["ended_ns"] is None:
                    self.store.end_subsession(subsession["id"], now)
            self._close_live_preview()
            if not self.capture.attached:
                prefix = str(
                    self.prefs.get("capture_prefix")
                    or _capture_prefix(self.current_session)
                    or ""
                )
                if prefix and tuple(
                    self.capture_dir.glob(f"{prefix}*.etl")
                ):
                    self.capture.attach(
                        prefix, tuple(self.prefs.get("capture_ports") or ())
                    )
            status = self.capture.stop()
            self.last_files = list(status.files)
            self.log.info("capture_stopped segments=%d", len(self.last_files))
            total_files = len(self.last_files)
            self.ingest_progress.configure(
                maximum=max(1, total_files), value=0
            )
            self.ingest_progress.grid()
            self.capture_state.configure(
                text=f"Lendo segmentos capturados… 0/{total_files}"
            )
        except Exception as error:
            self._ingesting = False
            self.stop_button.configure(state="normal")
            self.start_button.configure(
                state="normal" if self.capture_allowed else "disabled"
            )
            self.log.exception("capture_stop_failed")
            return messagebox.showerror("Falha ao parar", str(error))
        session_id = self.current_session
        files = tuple(self.last_files)
        preview_files = tuple(self._live_files)
        decode_ports = DEFAULT_PORTS

        def progress(done: int, total: int) -> None:
            def update() -> None:
                self.ingest_progress.configure(value=done)
                percent = round(done * 100 / total) if total else 100
                self.capture_state.configure(
                    text=(
                        f"Lendo segmentos capturados… {done}/{total} "
                        f"· {percent}%"
                    )
                )

            self.after(0, update)

        def ingest():
            return self._ingest_files(
                files,
                session_id,
                decode_ports,
                remove_sources=preview_files,
                progress=progress,
            )

        def ingest_done(result, error):
            self._ingesting = False
            self.ingest_progress.grid_remove()
            self.stop_button.configure(state="normal")
            self.start_button.configure(
                state="normal" if self.capture_allowed else "disabled"
            )
            if error:
                text = (
                    "Captura encerrada · leitura falhou: "
                    f"{_safe_error_code(error)}"
                )
            else:
                added, failures, empty_count = result
                self.log.info(
                    "capture_ingested events=%d failures=%d empty=%d",
                    added,
                    len(failures),
                    empty_count,
                )
                if added:
                    text = (
                        f"Captura encerrada · {added} eventos novos"
                    )
                elif failures:
                    text = (
                        "Captura encerrada · leitura falhou; arquivos "
                        "preservados para nova análise"
                    )
                elif empty_count:
                    text = "Captura encerrada sem pacotes utilizáveis"
                else:
                    text = (
                        "Captura encerrada sem eventos decodificados · "
                        "exportação disponível com alerta"
                    )
                if empty_count:
                    text += (
                        f" · {empty_count} segmento(s) vazio(s) ignorado(s)"
                    )
                if failures:
                    text += (
                        f" · {len(failures)} segmento(s) ignorado(s): "
                        + "; ".join(failures)
                    )
                else:
                    self.prefs["capture_pending"] = False
                    self._save_preferences()
                    for path in preview_files:
                        path.unlink(missing_ok=True)
            self.capture_state.configure(text=text)
            self.live_decode_state.configure(
                text=f"Última atualização: {self._last_live_decode}"
            )
            self._refresh_info()
            if self._pause_requested is True:
                self._pause_requested = False
                self._paused = True
                self.capture_state.configure(text="Captura pausada")
                return
            if self._start_after_ingest is True:
                self._start_after_ingest = False
                if not self.prefs.get("capture_pending"):
                    self.after(0, self.start_capture)
                return
            if (
                not error
                and result[0] > 0
                and not result[1]
                and self.auto_export.get()
            ):
                self._export_to(self.capture_dir / "Exportados")

        self._run(ingest, ingest_done)

    def _ingest_files(
        self,
        files: tuple[Path, ...],
        session_id: str,
        decode_ports: tuple[int, ...],
        *,
        remove_sources: tuple[Path, ...] = (),
        append_only: bool = False,
        progress=None,
    ) -> tuple[int, list[str], int]:
        self.license.require("ler captura")
        with self._ingest_lock:
            store = CaptureStore(DB_PATH)
            try:
                store.remove_sources(remove_sources)
                added = 0
                failures = []
                empty_count = 0
                for index, path in enumerate(files, 1):
                    try:
                        route_options = {}
                        raw_client_ports = getattr(self, "_client_ports", ())
                        client_ports = (
                            tuple(raw_client_ports)
                            if isinstance(raw_client_ports, (list, tuple))
                            else ()
                        )
                        if client_ports:
                            route_options["client_ports"] = client_ports
                            route_options["restrict_to_clients"] = True
                        added += store.ingest(
                            path,
                            session_id=session_id,
                            ports=decode_ports,
                            append_only=append_only,
                            **route_options,
                        )
                    except Exception as error:
                        reason = _safe_error_code(error)
                        self.log.exception(
                            "capture_segment_ingest_failed reason=%s "
                            "segment_bytes=%d",
                            reason,
                            path.stat().st_size if path.exists() else 0,
                        )
                        if reason == "empty_capture":
                            empty_count += 1
                        else:
                            failures.append(f"{path.name}: {reason}")
                    finally:
                        if progress:
                            progress(index, len(files))
                return added, failures, empty_count
            finally:
                store.close()

    def _recover_pending_character_uid(self, files: tuple[Path, ...]) -> None:
        """Read a retained capture once so its durable character UID is usable."""
        if (
            not self.current_session
            or not files
            or self.store.session_profiles(self.current_session)
        ):
            return
        decode_ports = DEFAULT_PORTS

        def recovered(result, error) -> None:
            if error:
                self.log.warning(
                    "pending_uid_recovery_failed reason=%s",
                    _safe_error_code(error),
                )
                return
            profiles = self.store.session_profiles(self.current_session)
            if not profiles:
                return
            self.log.info(
                "pending_uid_recovered characters=%d", len(profiles)
            )
            self.capture_state.configure(
                text=(
                    f"Captura pendente recuperada · UID de {len(profiles)} "
                    "personagem(ns) identificado(s)"
                )
            )
            self._refresh_info()

        self._run(
            lambda: self._ingest_files(
                files, self.current_session, decode_ports, append_only=True
            ),
            recovered,
        )

    def _next_live_target(self) -> Path:
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        self._live_index += 1
        return PREVIEW_DIR / (
            f"{_safe_name(self.current_session, 'sessao')}"
            f"-live-{self._live_index:04d}.pcap"
        )

    def _open_live_preview(self) -> None:
        self.license.require("monitorar captura")
        if not self.current_session or not self._live_ports:
            return
        target = self._next_live_target()
        capture = RealtimeCapture(target, self._live_ports)
        capture.start()
        self._live_capture = capture

    def _close_live_preview(self) -> tuple[Path, ...]:
        capture, self._live_capture = self._live_capture, None
        if capture is None:
            return ()
        try:
            capture.stop()
        except Exception as error:
            self.log.warning(
                "live_preview_stop_failed reason=%s", _safe_error_code(error)
            )
        self.log.info(
            "live_preview_closed packets=%d received=%d filtered=%d "
            "missed_write=%d missed_read=%d",
            capture.packets,
            capture.received_packets,
            capture.filtered_packets,
            capture.missed_write,
            capture.missed_read,
        )
        if not capture.target.exists():
            return ()
        if capture.target not in self._live_files:
            self._live_files.append(capture.target)
        return (capture.target,)

    def _maybe_decode_live(self) -> None:
        if (
            not self._live_capture
            or self._ingesting
            or self._live_ingesting
            or not self.current_session
            or time.monotonic() < self._next_live_decode
        ):
            return
        interval = self._decode_interval_seconds()
        self._next_live_decode = time.monotonic() + interval
        try:
            capture = self._live_capture
            target = capture.rotate(self._next_live_target())
        except Exception as error:
            self.log.warning(
                "live_preview_rotation_failed reason=%s",
                _safe_error_code(error),
            )
            self._last_live_decode = "Aguardando rotação da captura"
            return
        if not target.exists() or target.stat().st_size <= 24:
            target.unlink(missing_ok=True)
            self._last_live_decode = "Aguardando pacotes do RF"
            return
        self._live_files.append(target)
        self._live_ingesting = True
        self.live_decode_state.configure(text="Atualizando informações…")
        session_id = self.current_session
        started_at = time.monotonic()
        decode_ports = DEFAULT_PORTS

        def done(result, error):
            self._live_ingesting = False
            elapsed = time.monotonic() - started_at
            self._last_live_decode = datetime.now().strftime("%H:%M:%S")
            self._next_live_decode = (
                time.monotonic() + self._decode_interval_seconds()
            )
            self.log.info(
                "live_decode_finished seconds=%.3f bytes=%d",
                elapsed,
                target.stat().st_size if target.exists() else 0,
            )
            def finish_requested_action():
                if self._exit_after_live_ingest:
                    self._exit_after_live_ingest = False
                    self.after(0, self._exit)
                elif self._stop_after_live_ingest:
                    self._stop_after_live_ingest = False
                    self.after(0, self.stop_capture)

            if error:
                self.live_decode_state.configure(
                    text=(
                        "Atualização falhou · nova tentativa em "
                        f"{interval} s"
                    )
                )
                if self._pending_send_mode:
                    mode = self._pending_send_mode
                    self._pending_send_mode = None
                    self._pending_send_client_index = None
                    self._pending_send_notify = True
                    self.quick_mode_labels[mode].configure(
                        text="Falha na leitura"
                    )
                finish_requested_action()
                return
            added, failures, _empty_count = result
            self.log.info(
                "live_capture_ingested events=%d failures=%d segments=%d",
                added,
                len(failures),
                1,
            )
            suffix = (
                f" · {len(failures)} falha(s)"
                if failures
                else ""
            )
            self.live_decode_state.configure(
                text=(
                    f"Atualizado às {self._last_live_decode} · "
                    f"{added} evento(s) novo(s){suffix}"
                )
            )
            self._refresh_info()
            self._upload_pending_quick_captures()
            if self._pending_send_mode:
                mode = self._pending_send_mode
                client_index = self._pending_send_client_index
                notify = self._pending_send_notify
                self._pending_send_mode = None
                self._pending_send_client_index = None
                self._pending_send_notify = True
                self.after(
                    0,
                    lambda selected=mode, index=client_index, show=notify: (
                        self._send_mode_snapshot(selected, index, notify=show)
                    ),
                )
            finish_requested_action()

        def ingest_live():
            return self._ingest_files(
                (target,),
                session_id,
                decode_ports,
                append_only=True,
            )

        self._run(
            ingest_live,
            done,
        )

    def _session_parts(self) -> tuple[str, int]:
        match = re.search(r"-(\d{8}-\d{6})-(\d+)$", self.current_session or "")
        if match:
            return match.group(1), int(match.group(2))
        return datetime.now().strftime("%Y%m%d-%H%M%S"), int(
            self.prefs.get("session_counter", 0)
        )

    def _character_exports(
        self,
        *,
        prompt_exp: bool = False,
        store: CaptureStore | None = None,
        session_id: str | None = None,
        stats: dict[str, Any] | None = None,
        detected: list[dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        database = store or self.store
        session = session_id or self.current_session
        if not session:
            return []
        detected = detected if detected is not None else database.session_profiles(session)
        process_assigned = any(
            str(item["uid"]).startswith("client:") for item in detected
        )
        if (
            prompt_exp
            and len(detected) == 1
            and not process_assigned
        ):
            flows = database.unidentified_exp_flows(session)
            if flows:
                name = str(detected[0].get("name") or "personagem detectado")
                value = simpledialog.askfloat(
                    "Identificar eventos pela EXP",
                    f"Informe a EXP atual (%) de {name}:",
                    parent=self,
                    minvalue=0.0,
                    maxvalue=100.0,
                )
                if value is not None:
                    database.assign_unidentified_to_uid_by_exp(
                        session,
                        str(detected[0]["uid"]),
                        value,
                    )
        stats = stats or database.session_stats(session)
        if len(detected) > 7 or not detected:
            return [
                {
                    "uid": None,
                    "name": "Nao-identificado",
                    "include_unassigned": True,
                    "only_unassigned": False,
                    "identification_status": "unresolved",
                    "requested_characters": [],
                    "warning": (
                        "A captura não separou todos os personagens. Um arquivo "
                        "combinado será exportado e marcado para revisão pelo site."
                    ),
                }
            ]
        result = []
        for index, item in enumerate(detected):
            name = item["name"]
            result.append(
                {
                    "uid": item["uid"],
                    "client_key": item.get("client_key"),
                    "name": name or f"Personagem-{index + 1}",
                    "include_unassigned": len(detected) == 1,
                    "only_unassigned": False,
                    "identification_status": (
                        "exp_matched"
                        if item["uid"].startswith("exp:")
                        else "client_routed"
                        if item["uid"].startswith("client:")
                        else "confirmed_uid"
                    ),
                    "requested_characters": [],
                    "warning": (
                        "Alguns eventos não têm identificação individual; "
                        "o arquivo será marcado para revisão pelo site."
                        if len(detected) == 1 and int(stats["unassigned"] or 0)
                        else None
                    ),
                }
            )
        if len(detected) > 1 and int(stats["unassigned"] or 0):
            result.append(
                {
                    "uid": None,
                    "name": "Nao-atribuido",
                    "include_unassigned": False,
                    "only_unassigned": True,
                    "identification_status": "unresolved",
                    "requested_characters": [],
                    "warning": (
                        "Alguns eventos não puderam ser associados por UID ou "
                        "EXP. Eles serão exportados em um arquivo separado para "
                        "revisão pelo site."
                    ),
                }
            )
        return result

    def export(self) -> None:
        if not self._authorize_or_warn("exportar", "Exportação bloqueada"):
            return
        if self.capture.status().active:
            return messagebox.showwarning(
                "Captura ativa",
                "Pare a captura e aguarde a análise final antes de exportar.",
            )
        if not self.current_session:
            self.current_session = self.store.latest_session()
        if not self.current_session:
            return messagebox.showwarning(
                "Exportação", "Nenhuma sessão capturada está disponível."
            )
        pending_files = self.capture.segment_files()
        if pending_files and not self.store.session_sources(self.current_session):
            return messagebox.showwarning(
                "Captura pendente",
                "Os arquivos capturados ainda não foram analisados. Clique em "
                "Parar, aguarde a leitura e tente exportar novamente.",
            )
        if not self._session_has_data():
            messagebox.showwarning(
                "Sessão sem eventos reconhecidos",
                "O JSON e o CSV serão gerados mesmo assim e marcados para "
                "revisão. O site poderá recusar a importação.",
            )
        target = filedialog.askdirectory(
            title="Escolha a pasta de exportação",
            initialdir=str(self.capture_dir / "Exportados"),
        )
        if target:
            self._export_to(Path(target))

    def _session_has_data(self) -> bool:
        if not self.current_session:
            return False
        stats = self.store.session_stats(self.current_session)
        return bool(int(stats["recognized"] or 0) + int(stats["unknown"] or 0))

    def _diagnostic_file(
        self,
        target: Path,
        capture_id: str,
        session_id: str,
        *,
        include_logs: bool = False,
    ) -> Path | None:
        return self.store.export_diagnostics(
            target,
            capture_id,
            session_id,
            logs=recent_lines(LOG_PATH) if include_logs else None,
        )

    def open_log_folder(self) -> None:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        os.startfile(LOG_PATH.parent)

    def save_log_copy(self) -> None:
        lines = recent_lines(LOG_PATH)
        if not lines:
            return messagebox.showinfo(
                "Log técnico", "Ainda não há registros para salvar."
            )
        target = filedialog.asksaveasfilename(
            title="Salvar cópia sanitizada do log",
            defaultextension=".txt",
            initialfile=(
                f"RFQOL-log-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
            ),
            filetypes=(("Arquivo de texto", "*.txt"),),
        )
        if not target:
            return
        path = Path(target)
        temporary = path.with_name(f"{path.name}.tmp")
        try:
            temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
            os.replace(temporary, path)
            self.log.info("log_copy_saved")
            messagebox.showinfo("Log técnico", "Cópia sanitizada salva.")
        except OSError as error:
            temporary.unlink(missing_ok=True)
            messagebox.showerror("Log técnico", str(error))

    def send_diagnostic(self) -> None:
        if not self.license.lease:
            return messagebox.showwarning(
                "Diagnóstico", "Ative a licença antes de enviar."
            )
        if not messagebox.askyesno(
            "Enviar log técnico",
            "Autoriza enviar o log técnico sanitizado?\n\n"
            "Não são incluídos payload, IP, UID, personagem, licença, chave ou token.",
        ):
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        session_id = f"suporte-{stamp}"
        try:
            diagnostic = self._diagnostic_file(
                self.capture_dir / "Exportados",
                f"diagnostico-tecnico-{stamp}",
                session_id,
                include_logs=True,
            )
        except Exception as error:
            self.log.exception("diagnostic_export_failed")
            return messagebox.showerror("Diagnóstico", str(error))
        if not diagnostic:
            return messagebox.showinfo(
                "Diagnóstico", "Ainda não há informações técnicas para enviar."
            )
        self._run(
            lambda: self.license.upload_diagnostic(diagnostic, VERSION),
            self._diagnostic_done,
        )

    def _diagnostic_done(self, result, error) -> None:
        if error:
            self.log.error(
                "diagnostic_upload_failed error=%s", type(error).__name__
            )
            return messagebox.showinfo(
                "Diagnóstico",
                f"Não foi possível enviar. O arquivo foi preservado:\n{error}",
            )
        self.log.info("diagnostic_uploaded")
        messagebox.showinfo(
            "Diagnóstico", f"Enviado com protocolo {result.get('receipt')}."
        )

    def _export_to(
        self, target: Path, *, offer_cleanup: bool = True
    ) -> list:
        self.license.require("exportar")
        if not self.current_session:
            return []
        profile = self.profile.get().strip() or "Profile"
        stamp, counter = self._session_parts()
        try:
            characters = self._character_exports(prompt_exp=True)
            warnings = {
                str(character["warning"])
                for character in characters
                if character.get("warning")
            }
            if warnings:
                messagebox.showwarning(
                    "Exportação com identificação incompleta",
                    "\n\n".join(sorted(warnings))
                    + "\n\nA exportação continuará normalmente.",
                )
            results = []
            for character in characters:
                name = str(character["name"])
                capture_id = (
                    f"{_safe_name(profile, 'Profile')}-"
                    f"{_safe_name(name, 'Personagem')}-{stamp}-{counter:03d}"
                )
                preview = self.store.session_envelope(
                    self.current_session,
                    character["uid"],
                    bool(character["include_unassigned"]),
                    bool(character["only_unassigned"]),
                )
                detected_summary, marks = self._capture_summary_for_language(
                    preview,
                    str(character["uid"] or ""),
                    name,
                )
                _marks, collection_types = _collection_marks(preview)
                subsession_reports = []
                for subsession in self.store.subsessions(self.current_session):
                    if (
                        subsession["character_uid"] is not None
                        and subsession["character_uid"] != character["uid"]
                    ):
                        continue
                    subsession_reports.append(
                        self._subsession_report(
                            subsession, character["uid"]
                        )
                    )
                result = self.store.export(
                    target,
                    capture_id,
                    session_id=self.current_session,
                    character_uid=character["uid"],
                    include_unassigned=bool(character["include_unassigned"]),
                    only_unassigned=bool(character["only_unassigned"]),
                    context={
                        "profile": profile,
                        "character_name": name,
                        "installation_id": self.license.installation_id,
                        "license_lease": self.license.lease,
                        "app_version": VERSION,
                        "session_counter": counter,
                        "identification_status": character[
                            "identification_status"
                        ],
                        "requires_site_review": bool(character.get("warning")),
                        "requested_characters": character[
                            "requested_characters"
                        ],
                        "codex_marks": marks,
                        "subsession_reports": subsession_reports,
                    },
                )
                envelope = json.loads(
                    result.json_path.read_text(encoding="utf-8")
                )
                envelope["capture"] = detected_summary
                envelope["profiles"] = [
                    {
                        "profile": profile,
                        "name": name,
                        "character_uid": character["uid"],
                        "className": detected_summary["character_class"],
                        "loadout": detected_summary["loadout"],
                        "marks": marks,
                        "collection_types": collection_types,
                    }
                ]
                temporary = result.json_path.with_suffix(".json.tmp")
                temporary.write_text(
                    json.dumps(envelope, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                json.loads(temporary.read_text(encoding="utf-8"))
                os.replace(temporary, result.json_path)
                results.append(result)
            diagnostic = self._diagnostic_file(
                target,
                (
                    f"{_safe_name(profile, 'Profile')}-diagnostico-"
                    f"{stamp}-{counter:03d}"
                ),
                self.current_session,
            )
            total = sum(
                result.json_path.stat().st_size
                + result.csv_path.stat().st_size
                for result in results
            ) + (diagnostic.stat().st_size if diagnostic else 0)
            raw_files = list(
                dict.fromkeys(
                    [
                        *self.store.session_sources(self.current_session),
                        *self.capture_dir.glob(
                            f"{_safe_name(self.current_session, 'sessao')}-cliente-*.pcap"
                        ),
                    ]
                )
            )
            raw_bytes = int(
                self.store.session_stats(self.current_session)["raw_bytes"] or 0
            ) + sum(
                path.stat().st_size
                for path in raw_files
                if path.exists()
                and path not in self.store.session_sources(self.current_session)
            )
        except Exception as error:
            self.log.exception("export_failed")
            messagebox.showerror("Exportação falhou", str(error))
            return []

        if diagnostic and messagebox.askyesno(
            "Diagnóstico sanitizado",
            "Existem eventos ainda não decodificados. O arquivo separado não "
            "contém payload, IP, UID, personagem ou licença.\n\n"
            "Autoriza enviar ao desenvolvedor?",
        ):
            self._run(
                lambda: self.license.upload_diagnostic(diagnostic, VERSION),
                self._diagnostic_done,
            )
        self.log.info("export_completed characters=%d bytes=%d", len(results), total)
        if not offer_cleanup:
            return results

        erase = self.delete_after_export.get() or messagebox.askyesno(
            "Exportação concluída",
            f"{len(results)} personagem(ns), JSON + CSV validados: "
            f"{_format_bytes(total)}.\n\n"
            f"Enviar {_format_bytes(raw_bytes)} de segmentos desta sessão para "
            "a Lixeira e remover somente esta sessão do histórico local?",
        )
        if erase:
            if not _recycle(raw_files):
                return messagebox.showwarning(
                    "Lixeira",
                    "Alguns segmentos não puderam ser movidos. "
                    "O histórico local foi preservado.",
                )
            try:
                self.store.clear_exported(self.current_session)
                self.last_files = []
                self.capture_state.configure(
                    text="Exportação concluída · sessão enviada à Lixeira"
                )
                self.current_session = self.store.latest_session()
                self._save_preferences()
                self._refresh_info()
            except Exception as error:
                messagebox.showerror(
                    "Limpeza incompleta",
                    "Os arquivos exportados permanecem válidos, mas a sessão "
                    f"local não foi limpa: {error}",
                )
        return results

    def _sync_overview_layout(self, _event=None) -> None:
        if not hasattr(self, "overview_split"):
            return
        try:
            split = self.state() == "zoomed" or bool(
                self.attributes("-fullscreen")
            )
        except tk.TclError:
            return
        if split == self._overview_split_visible:
            return
        self._overview_split_visible = split
        if split:
            self.overview_single.pack_forget()
            self.overview_split.pack(fill=BOTH, expand=True)
        else:
            self.overview_split.pack_forget()
            self.overview_single.pack(fill=BOTH, expand=True)

    def _active_subsession_for_client(
        self, index: int, items: list[dict] | None = None
    ) -> dict | None:
        client_key = f"client:{chr(97 + index)}"
        uid = self._client_uid(index)
        return next(
            (
                item
                for item in (
                    items
                    if items is not None
                    else self.store.subsessions(self.current_session or "")
                )
                if item["ended_ns"] is None
                and (
                    item.get("client_key") == client_key
                    or (not item.get("client_key") and item["character_uid"] == uid)
                )
            ),
            None,
        )

    def _render_split_overview(
        self,
        index: int,
        name: str,
        summary: dict | None,
        duration: int,
        active_subsession: dict | None = None,
    ) -> None:
        if not hasattr(self, "split_overviews"):
            return
        widgets = self.split_overviews[index]
        summary = summary or {}
        hours = duration / 3600 if duration else 0
        gained = int(summary.get("exp_gained") or 0)
        credits = int(summary.get("credits") or 0)
        contribution = summary.get("contribution")
        class_name = str(summary.get("character_class") or "")
        class_icon = self.class_icons.get(
            (class_name, summary.get("biosuit_grade") or 0)
        ) or self.class_icons.get((class_name, 0))
        rover_icon = self.rover_icons.get(summary.get("rover_grade") or 0)
        widgets["class_icon"].configure(
            image=class_icon or "", text="" if class_icon else (class_name or "—")
        )
        widgets["rover_icon"].configure(image=rover_icon or "")
        widgets["name"].configure(
            text=f"Cliente {chr(65 + index)} · {name or 'aguardando personagem'}"
        )
        widgets["equipment"].configure(
            text=(
                f"{summary.get('character_class') or 'Classe —'} · "
                f"{summary.get('biosuit_name') or 'Biosuit —'} · "
                f"{summary.get('rover_name') or 'Rover —'}"
            )
        )
        widgets["progress"].configure(value=summary.get("exp_percent") or 0)
        rarity_totals = summary.get("loot_by_rarity") or {}
        values = {
            "exp": summary.get("exp"),
            "exp_missing": summary.get("exp_missing"),
            "credits": credits,
            "diamonds": summary.get("diamonds"),
            "contribution": contribution,
            "kills": int(summary.get("kills") or 0),
            "exp_hour": round(gained / hours) if hours else None,
            "credits_hour": round(credits / hours) if hours else None,
            "contribution_hour": (
                round(contribution / hours)
                if hours and isinstance(contribution, (int, float))
                else None
            ),
            "loot": " · ".join(
                f"{label} {int(rarity_totals.get(key, 0))}"
                for key, label in LOOT_RARITIES.values()
            ),
        }
        for key, label in widgets["metrics"].items():
            value = values[key]
            label.configure(
                text=(
                    f"{value:,.0f}".replace(",", ".")
                    if isinstance(value, (int, float))
                    else value or "—"
                )
            )
        widgets["subsession"].configure(
            text=(
                "Subsessão ativa: "
                f"{active_subsession['name'] if active_subsession else 'nenhuma'}"
            )
        )

    def _refresh_info(self) -> None:
        snapshot = self._info_snapshot
        if snapshot and snapshot.get("session_id") == self.current_session:
            self._apply_info_snapshot(snapshot)
        self._info_refresh_generation += 1
        self._info_refresh_pending = True
        if self._info_refresh_running:
            return
        self._start_info_refresh()

    def _start_info_refresh(self) -> None:
        if not self._info_refresh_pending or self._info_refresh_running:
            return
        generation = self._info_refresh_generation
        session_id = self.current_session
        language = self.item_name_language.get()
        database_path = self.store.path
        self._info_refresh_pending = False
        self._info_refresh_running = True

        def worker() -> None:
            database = None
            try:
                database = CaptureStore(database_path, readonly=True)
                result = self._load_info_snapshot(
                    database, session_id, language
                )
                self.after(
                    0,
                    lambda: self._info_refresh_finished(
                        generation, result, None
                    ),
                )
            except Exception as error:
                self.after(
                    0,
                    lambda error=error: self._info_refresh_finished(
                        generation, None, error
                    ),
                )
            finally:
                if database is not None:
                    database.close()

        threading.Thread(target=worker, daemon=True).start()

    def _load_info_snapshot(
        self,
        database: CaptureStore,
        session_id: str | None,
        language: str,
    ) -> dict[str, Any]:
        if not session_id:
            return {
                "session_id": None,
                "stats": dict(self._last_session_stats),
                "profiles": [],
                "characters": [],
                "subsessions": [],
                "subsession_summaries": {},
            }
        revision = database.event_revision()
        maximum_id = database.max_event_id(session_id)
        cache = self._info_worker_cache
        rebuild = (
            cache.get("session_id") != session_id
            or cache.get("revision") != revision
            or cache.get("language") != language
            or maximum_id < int(cache.get("last_global_id") or 0)
        )
        if rebuild:
            cache.clear()
            cache.update(
                {
                    "session_id": session_id,
                    "revision": revision,
                    "language": language,
                    "summaries": {},
                    "subsession_summaries": {},
                }
            )
        last_global_id = int(cache.get("last_global_id") or 0)
        if "stats" not in cache:
            cache["stats"] = database.session_stats(session_id)
        else:
            delta = database.session_stats_after(session_id, last_global_id)
            stats = cache["stats"]
            if maximum_id > last_global_id:
                for key in ("recognized", "unknown", "unassigned"):
                    stats[key] = int(stats.get(key) or 0) + int(delta.get(key) or 0)
                for key, chooser in (("started_ns", min), ("ended_ns", max)):
                    value = delta.get(key)
                    if isinstance(value, int):
                        current = stats.get(key)
                        stats[key] = chooser(current, value) if isinstance(current, int) else value
            stats["raw_bytes"] = int(delta.get("raw_bytes") or 0)
        if rebuild or maximum_id > last_global_id or "profiles" not in cache:
            cache["profiles"] = database.session_profiles(session_id)
        profiles = cache["profiles"]
        characters = self._character_exports(
            store=database,
            session_id=session_id,
            stats=cache["stats"],
            detected=profiles,
        )
        language = game_data_language(language)
        item_names = item_names_for_language(language)
        summaries = cache["summaries"]

        def update_summary_entry(
            entry: dict[str, Any],
            character_uid: str | None,
            character_name: str,
            **filters: Any,
        ) -> None:
            cursor = int(entry["last_id"])
            while True:
                events, next_cursor = database.ui_event_batch(
                    session_id,
                    character_uid,
                    after_id=cursor,
                    **filters,
                )
                if events or "summary" not in entry:
                    summary, _marks, state = _capture_summary(
                        {"events": events},
                        character_uid,
                        character_name,
                        item_names,
                        game_language=language,
                        _state=entry["state"],
                        _return_state=True,
                    )
                    entry.update(state=state, summary=summary)
                if len(events) < 5000:
                    break
                cursor = next_cursor
            entry["last_id"] = maximum_id

        character_results = []
        active_keys = set()
        for character in characters:
            key = (
                str(character.get("uid") or ""),
                bool(character.get("include_unassigned")),
                bool(character.get("only_unassigned")),
                str(character.get("name") or ""),
            )
            active_keys.add(key)
            entry = summaries.get(key)
            if entry is None:
                entry = {"last_id": 0, "state": {"loot_limit": 100}}
            update_summary_entry(
                entry,
                character.get("uid"),
                str(character.get("name") or ""),
                include_unassigned=bool(character.get("include_unassigned")),
                only_unassigned=bool(character.get("only_unassigned")),
            )
            summaries[key] = entry
            character_results.append({**character, "summary": entry["summary"]})
        for key in tuple(summaries):
            if key not in active_keys:
                summaries.pop(key, None)

        subsessions = database.subsessions(session_id)
        uid_by_client = {
            item.get("client_key"): item.get("uid")
            for item in profiles
            if item.get("client_key")
        }
        subsession_cache = cache["subsession_summaries"]
        subsession_results = {}
        active_subsession_ids = set()
        for item in subsessions:
            identifier = item["id"]
            active_subsession_ids.add(identifier)
            character_uid = (
                uid_by_client.get(item.get("client_key"))
                if item.get("client_key")
                else item.get("character_uid")
            )
            entry = subsession_cache.get(identifier)
            if (
                entry is None
                or entry.get("character_uid") != character_uid
                or entry.get("started_ns") != item["started_ns"]
            ):
                entry = {
                    "last_id": 0,
                    "state": {"loot_limit": 50},
                    "character_uid": character_uid,
                    "started_ns": item["started_ns"],
                }
            update_summary_entry(
                entry,
                character_uid,
                "",
                started_ns=item["started_ns"],
                ended_ns=item["ended_ns"],
            )
            entry["ended_ns"] = item["ended_ns"]
            subsession_cache[identifier] = entry
            subsession_results[identifier] = entry["summary"]
        for identifier in tuple(subsession_cache):
            if identifier not in active_subsession_ids:
                subsession_cache.pop(identifier, None)
        cache["last_global_id"] = maximum_id
        return {
            "session_id": session_id,
            "stats": dict(cache["stats"]),
            "profiles": profiles,
            "characters": character_results,
            "subsessions": subsessions,
            "subsession_summaries": subsession_results,
        }

    def _info_refresh_finished(
        self, generation: int, snapshot: dict | None, error: Exception | None
    ) -> None:
        self._info_refresh_running = False
        if error is not None:
            self.log.exception(
                "info_refresh_failed reason=%s", _safe_error_code(error),
                exc_info=(type(error), error, error.__traceback__),
            )
        elif generation == self._info_refresh_generation and snapshot is not None:
            self._info_snapshot = snapshot
            self._apply_info_snapshot(snapshot)
        if self._info_refresh_pending or generation != self._info_refresh_generation:
            self._info_refresh_pending = True
            self._start_info_refresh()

    def _apply_info_snapshot(self, snapshot: dict[str, Any]) -> None:
        if snapshot.get("session_id") != self.current_session:
            return
        profiles = snapshot.get("profiles") or []
        subsessions = snapshot.get("subsessions") or []
        stats = snapshot.get("stats") or dict(self._last_session_stats)
        self._last_session_stats = dict(stats)
        self._refresh_client_buttons(profiles)
        started, ended = stats.get("started_ns"), stats.get("ended_ns")
        duration = (
            max(0, int((ended - started) / 1_000_000_000))
            if isinstance(started, int) and isinstance(ended, int)
            else 0
        )
        if self._capture_is_active() and self.current_session:
            duration = max(
                duration,
                _session_elapsed(self.current_session, True, datetime.now())
                - self._paused_total_seconds,
            )
        lines = (
            ["Nenhuma sessão disponível."]
            if not self.current_session
            else [
                f"Sessão              {self.current_session}",
                f"Tempo               {duration // 60}m {duration % 60}s",
                f"Eventos reconhecidos {stats.get('recognized', 0)}",
                f"Sem personagem       {stats.get('unassigned', 0)}",
                f"Não decodificados   {stats.get('unknown', 0)}",
                f"Dados brutos         {_format_bytes(int(stats.get('raw_bytes') or 0))}",
                "",
            ]
        )
        overview = None
        overview_name = "Aguardando personagem"
        client_overviews: dict[int, tuple[str, dict]] = {}
        characters = snapshot.get("characters") or []
        routed = any(item.get("client_key") for item in characters)
        active_client_key = f"client:{chr(97 + self._active_client_index)}"
        session_kills = 0
        for character in characters:
            summary = character["summary"]
            session_kills += int(summary.get("kills") or 0)
            selected = (
                character.get("client_key") == active_client_key
                if routed
                else character.get("uid") == self.active_character_uid
            )
            if selected or (overview is None and not routed):
                overview = summary
                overview_name = character["name"]
            if character.get("client_key") in {"client:a", "client:b"}:
                index = 0 if character["client_key"] == "client:a" else 1
                client_overviews[index] = (character["name"], summary)
            exp_percent = summary.get("exp_percent")
            lines.extend(
                [
                    f"[{character['name']}]",
                    f"UID                 {character.get('uid') or 'aguardando identificação'}",
                    f"Level               {summary.get('level') if summary.get('level') is not None else '—'}",
                    f"EXP                 {summary.get('exp') if summary.get('exp') is not None else '—'}",
                    "EXP no level        " + (
                        f"{exp_percent:.2f}%" if isinstance(exp_percent, (int, float)) else "—"
                    ),
                    f"EXP obtida          {summary.get('exp_gained', 0)}",
                    f"Créditos            {summary.get('credits') or '—'}",
                    f"Contribuição        {summary.get('contribution') if summary.get('contribution') is not None else '—'}",
                    f"Mercado             {summary.get('market_events', 0)} evento(s)",
                    f"Kills estimadas     {summary.get('kills', 0)} (proxy por recompensa)",
                    "",
                ]
            )
        summary = overview or {
            "character_class": "",
            "biosuit_name": "",
            "biosuit_grade": None,
            "rover_name": "",
            "rover_grade": None,
            "level": None,
            "exp": None,
            "exp_missing": None,
            "exp_percent": None,
            "exp_gained": 0,
            "credits": 0,
            "diamonds": None,
            "contribution": None,
            "kills": 0,
            "finalizations": 0,
            "loot": [],
            "loot_by_rarity": {
                key: 0 for key, _label in LOOT_RARITIES.values()
            },
        }
        overview_name = (
            self._client_display_name(self._active_client_index, profiles)
            or overview_name
        )
        hours = duration / 3600 if duration else 0
        required = (
            LEVEL_CURVE.get(summary["level"] + 1)
            if isinstance(summary["level"], int)
            else None
        )
        values = {
            "exp": summary["exp"],
            "exp_missing": summary["exp_missing"],
            "diamonds": summary["diamonds"],
            "exp_gained": summary["exp_gained"],
            "exp_hour": round(summary["exp_gained"] / hours) if hours else None,
            "exp_hour_percent": (
                summary["exp_gained"] * 100 / required / hours
                if hours and required
                else None
            ),
            "credits": summary["credits"],
            "credits_hour": round(summary["credits"] / hours) if hours else None,
            "contribution": summary["contribution"],
            "contribution_hour": (
                round(summary["contribution"] / hours)
                if hours and isinstance(summary["contribution"], (int, float))
                else None
            ),
            "kills": summary["kills"],
            "finalizations": summary["finalizations"],
            "loot": "",
        }
        rarity_totals = summary.get("loot_by_rarity") or {}
        rarity_parts = [
            f"{label} {int(rarity_totals.get(key, 0))}"
            for key, label in LOOT_RARITIES.values()
        ]
        values["loot"] = "\n".join(
            " · ".join(rarity_parts[index : index + 2])
            for index in range(0, len(rarity_parts), 2)
        )
        self.overview_character.configure(text=str(overview_name))
        active_subsession = self._active_subsession_for_client(
            self._active_client_index, subsessions
        )
        self.overview_active_subsession.configure(
            text=(
                f"Subsessão ativa: {active_subsession['name']}"
                if active_subsession
                else "Subsessão ativa: nenhuma"
            )
        )
        for index in range(2):
            client_name, client_summary = client_overviews.get(
                index,
                (
                    self._client_display_name(index, profiles),
                    None,
                ),
            )
            self._render_split_overview(
                index,
                client_name,
                client_summary,
                duration,
                self._active_subsession_for_client(index, subsessions),
            )
        class_icon = self.class_icons.get(
            (summary["character_class"], summary["biosuit_grade"] or 0)
        ) or self.class_icons.get((summary["character_class"], 0))
        self.overview_class_symbol.configure(
            image=class_icon or "",
            text="" if class_icon else (summary["character_class"] or "—"),
        )
        rover_icon = self.rover_icons.get(summary["rover_grade"] or 0)
        self.overview_rover_symbol.configure(image=rover_icon or "")
        self.overview_rover_name.configure(
            text=summary["rover_name"] or "Rover —"
        )
        self.overview_level.configure(
            text=(
                " · ".join(
                    value
                    for value in (
                        f"Nível {summary['level']}",
                        summary["character_class"],
                        summary["biosuit_name"],
                    )
                    if value
                )
                if summary["level"] is not None
                else (
                    " · ".join(
                        value
                        for value in (
                            summary["character_class"],
                            summary["biosuit_name"],
                        )
                        if value
                    )
                    or "Nível —"
                )
            )
        )
        self.overview_exp.configure(
            text=(
                f"{summary['exp_percent']:.2f}%".replace(".", ",")
                if isinstance(summary["exp_percent"], (int, float))
                else "—"
            )
        )
        self.overview_exp_progress.configure(
            value=(
                max(0, min(100, float(summary["exp_percent"])))
                if isinstance(summary["exp_percent"], (int, float))
                else 0
            )
        )
        for key, label in self.overview_values.items():
            value = values[key]
            label.configure(
                text=(
                    f"{value:.2f}%".replace(".", ",")
                    if key == "exp_hour_percent"
                    and isinstance(value, (int, float))
                    else f"{value:,.0f}".replace(",", ".")
                    if isinstance(value, (int, float))
                    else value
                    if isinstance(value, str) and value
                    else "—"
                )
            )
        self._refresh_subsessions(snapshot=snapshot)
        self.info_text.configure(state="normal")
        self.info_text.delete("1.0", END)
        self.info_text.insert("1.0", "\n".join(lines))
        self.info_text.configure(state="disabled")
        self._last_kills = session_kills

    def check_update(self) -> None:
        if UPDATE_MODE == "manual":
            self.update_status.configure(
                text="Atualização automática desativada. Use o Discord oficial."
            )
            return
        self.update_button.configure(state="disabled")
        self.update_progress.configure(value=0)
        self.update_status.configure(text="Consultando atualizações…")
        self._run(lambda: latest(self.channel.get()), self._update_found)

    def _update_found(self, release, error) -> None:
        if UPDATE_MODE == "manual":
            self.update_status.configure(
                text="Atualização automática desativada. Use o Discord oficial."
            )
            return
        if error:
            self.update_button.configure(state="normal")
            return self.update_status.configure(
                text=f"Atualização indisponível: {error}"
            )
        tag = str(release.get("tag_name", ""))
        notes = str(release.get("body", "")).strip()[:800]
        if tag.lstrip("v") == VERSION:
            self.update_button.configure(state="normal")
            self.update_progress.configure(value=100)
            return self.update_status.configure(
                text="Você já usa a versão mais recente."
            )
        if not messagebox.askyesno(
            "Atualização encontrada",
            f"{tag}\n\n{notes}\n\nBaixar e verificar agora?",
        ):
            self.update_button.configure(state="normal")
            self.update_status.configure(text="Atualização cancelada.")
            return
        def progress(phase: str, downloaded: int, total: int | None) -> None:
            self.after(
                0,
                lambda: self._update_progress_changed(
                    phase, downloaded, total
                ),
            )

        self._run(
            lambda: download_release_with_rollback(
                release,
                progress,
                UPDATES_DIR,
                current_version=VERSION,
                current_sequence=self.license.highest_release_sequence,
            ),
            self._update_downloaded,
        )

    def _update_progress_changed(
        self, phase: str, downloaded: int, total: int | None
    ) -> None:
        if phase == "manifest":
            self.update_status.configure(text="Verificando manifesto assinado…")
            return
        if phase == "verify":
            self.update_progress.configure(value=99)
            self.update_status.configure(text="Verificando integridade do instalador…")
            return
        percent = min(100, downloaded * 100 / total) if total else 0
        self.update_progress.configure(value=percent)
        size = _format_bytes(downloaded)
        suffix = f" de {_format_bytes(total)}" if total else ""
        self.update_status.configure(
            text=f"Baixando atualização: {percent:.0f}% · {size}{suffix}"
        )

    def _update_downloaded(self, installer, error) -> None:
        if UPDATE_MODE == "manual":
            self.update_status.configure(text="Instalação automática desativada.")
            return
        self.update_button.configure(state="normal")
        if error:
            self.update_progress.configure(value=0)
            self.update_status.configure(text=f"Falha na atualização: {error}")
            return messagebox.showerror("Atualização rejeitada", str(error))
        self.update_progress.configure(value=100)
        self.update_status.configure(text="Download concluído e verificado.")
        if self.capture.attached and self.capture.status().active:
            return messagebox.showwarning(
                "Captura ativa",
                "Pare a captura e aguarde a leitura terminar antes de atualizar.",
            )
        if messagebox.askyesno(
            "Atualização verificada",
            "Manifesto Ed25519 e SHA-256 conferem.\n\n"
            "O instalador não usa assinatura de código do Windows e pode "
            "aparecer como Publicador desconhecido.\n\n"
            "O RF QOL será fechado e o instalador será aberto. Continuar?",
        ):
            self._save_preferences()
            try:
                manifest = verify_manifest(
                    json.loads(
                        (UPDATES_DIR / "update-manifest.json").read_text(
                            encoding="utf-8"
                        )
                    ),
                    current_sequence=self.license.highest_release_sequence,
                )
                verify_downloaded(installer, manifest)
                os.startfile(installer)
            except (OSError, ValueError, json.JSONDecodeError) as launch_error:
                self.log.exception("update_installer_launch_failed")
                return messagebox.showerror(
                    "Não foi possível abrir o instalador", str(launch_error)
                )
            if self.tray:
                self.tray.stop()
            self.store.close()
            self.log.info("app_closed_for_update")
            self.destroy()

    def rollback(self) -> None:
        if UPDATE_MODE == "manual":
            return messagebox.showinfo(
                "Instalação manual",
                "Para voltar de versão, use somente um instalador compatível "
                "fornecido oficialmente.",
            )
        try:
            installer = cached_rollback(
                UPDATES_DIR / "rollback",
                current_version=VERSION,
                current_sequence=self.license.highest_release_sequence,
            )
        except (OSError, ValueError, json.JSONDecodeError):
            return messagebox.showinfo(
                "Versão anterior",
                "Não existe uma versão anterior compatível e assinada no cache.",
            )
        if self.capture.attached and self.capture.status().active:
            return messagebox.showwarning(
                "Captura ativa",
                "Pare a captura e aguarde a leitura terminar antes do rollback.",
            )
        if not messagebox.askyesno(
            "Restaurar versão anterior",
            "A versão anterior possui manifesto Ed25519, compatibilidade, "
            "tamanho e SHA-256 válidos. Um backup verificado do banco será "
            "criado e o Windows pedirá confirmação administrativa. Continuar?",
        ):
            return
        try:
            installer = cached_rollback(
                UPDATES_DIR / "rollback",
                current_version=VERSION,
                current_sequence=self.license.highest_release_sequence,
            )
            backup_database(
                self.store.path,
                UPDATES_DIR / "database-backups",
                VERSION,
            )
            os.startfile(installer)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self.log.exception("rollback_installer_launch_failed")
            return messagebox.showerror("Rollback rejeitado", str(error))
        if self.tray:
            self.tray.stop()
        self.store.close()
        self.log.info("app_closed_for_rollback")
        self.destroy()

    def _request_runtime_refresh(self, active: bool) -> None:
        now = time.monotonic()
        if self._runtime_refresh_running or now < self._next_runtime_refresh:
            return
        self._runtime_refresh_running = True
        self._next_runtime_refresh = now + 5
        selected_game_path = self._selected_game_path
        capture_dir = self.capture_dir

        def worker() -> None:
            try:
                total = sum(
                    path.stat().st_size for path in capture_dir.glob("*.etl")
                )
                usage = shutil.disk_usage(capture_dir)
                packet_count = self.capture.packet_count() if active else None
                connections = None
                if active and selected_game_path:
                    local_ports, remote_ports, clients = ports_for_executable(
                        selected_game_path, DEFAULT_PORTS
                    )
                    client_connections = clients_for_executable(
                        selected_game_path, DEFAULT_PORTS
                    )
                    connections = (
                        local_ports,
                        remote_ports,
                        clients,
                        client_connections,
                    )
                result = {
                    "total_bytes": total,
                    "free_bytes": usage.free,
                    "disk_total": usage.total,
                    "packet_count": packet_count,
                    "connections": connections,
                }
                self.after(0, lambda: self._runtime_refresh_finished(result, None))
            except Exception as error:
                self.after(
                    0,
                    lambda error=error: self._runtime_refresh_finished(None, error),
                )

        threading.Thread(target=worker, daemon=True).start()

    def _runtime_refresh_finished(
        self, result: dict | None, error: Exception | None
    ) -> None:
        self._runtime_refresh_running = False
        if error is not None:
            self.log.error(
                "runtime_refresh_failed reason=%s", _safe_error_code(error)
            )
            return
        self._runtime_snapshot = result or self._runtime_snapshot
        packet_count = self._runtime_snapshot.get("packet_count")
        if packet_count is not None:
            self._last_packet_count = int(packet_count)
        connections = self._runtime_snapshot.get("connections")
        if connections is not None:
            self._apply_active_game_connections(connections)

    def _apply_active_game_connections(self, result: tuple) -> None:
        local_ports, remote_ports, clients, client_connections = result
        client_signature = tuple(
            (
                int(item["pid"]),
                tuple(item["local_ports"]),
                tuple(item["remote_ports"]),
            )
            for item in client_connections[:2]
        )
        signature = (clients, local_ports, remote_ports, client_signature)
        if signature == self._last_game_signature:
            return
        self._last_game_signature = signature
        if clients > 2:
            self.capture_state.configure(
                text="Mais de dois clientes conectados · feche os excedentes"
            )
            return
        if not clients:
            self.capture_state.configure(text="Aguardando reconexão do jogo")
            return
        filter_ports = tuple(
            dict.fromkeys((*local_ports, *remote_ports))
        )
        previous_client_ports = self._client_ports
        if client_connections:
            self._client_pids, self._client_ports = _merge_client_routes(
                self._client_pids,
                self._client_ports,
                client_connections,
            )
            self.prefs["capture_client_pids"] = self._client_pids
            self.prefs["capture_client_ports"] = [
                list(group) for group in self._client_ports
            ]
        try:
            added = self.capture.add_ports(filter_ports)
            live_added = (
                self._live_capture.add_ports(filter_ports)
                if self._live_capture
                else 0
            )
        except Exception as error:
            self.log.exception(
                "capture_connection_update_failed reason=%s",
                _safe_error_code(error),
            )
            self.capture_state.configure(
                text="Reconexão não monitorada · pare e inicie outra captura"
            )
            return
        if added or live_added:
            saved = set(self.prefs.get("capture_ports") or ())
            saved.update(filter_ports)
            self.prefs["capture_ports"] = sorted(saved)
            self._live_ports = tuple(
                sorted(set(self._live_ports) | set(filter_ports))
            )
            self.prefs["capture_decode_ports"] = list(DEFAULT_PORTS)
            self._save_preferences()
            self.log.info(
                "capture_connections_added filters=%d live_filters=%d "
                "remote_ports=%d",
                added,
                live_added,
                len(remote_ports),
            )
        elif self._client_ports != previous_client_ports:
            self._save_preferences()
        if self._client_ports != previous_client_ports:
            self.log.info(
                "client_routes_updated routes=%s",
                [list(group) for group in self._client_ports],
            )
        self.capture_state.configure(
            text=(
                f"{clients} cliente(s) conectado(s) · "
                f"{len(local_ports)} conexão(ões) monitorada(s)"
            )
        )

    def _poll(self) -> None:
        try:
            status = self.capture.cached_status
            active = self._capture_is_active()
            if active:
                try:
                    self.license.require("continuar captura")
                except PermissionError as error:
                    self._halt_capture_for_license(str(error))
                    active = False
            now = time.monotonic()
            if now >= self._next_license_refresh and not self._license_refresh_running:
                self._next_license_refresh = now + 60
                self._license_refresh_running = True
                self._run(
                    lambda: self.license.refresh_if_due(VERSION),
                    self._license_checked,
                )
            if active:
                self.capture.heartbeat()
            self._request_runtime_refresh(active)
            self._maybe_decode_live()
            total = int(self._runtime_snapshot.get("total_bytes") or 0)
            current_size = max(0, int(status.bytes_written or 0))
            free_bytes = int(self._runtime_snapshot.get("free_bytes") or 0)
            disk_total = int(self._runtime_snapshot.get("disk_total") or 0)
            percent_free = free_bytes / disk_total if disk_total else 0
            level = (
                "VERMELHO"
                if total >= 10 * GIB or percent_free < 0.10
                else "AMARELO"
                if total >= 5 * GIB
                else "OK"
            )
            self.settings_storage_state.configure(
                text=(
                    f"Arquivo da sessão: {_format_bytes(current_size)}\n"
                    f"Total armazenado: {_format_bytes(total)}\n"
                    f"Espaço livre: {_format_bytes(free_bytes)} · {level}"
                )
            )
            self.top_storage.configure(
                text=(
                    f"Sessão: {_format_bytes(current_size)} · "
                    f"Total: {_format_bytes(total)}"
                )
            )
            self.capture_size.configure(
                text=f"Arquivo atual\n{_format_bytes(current_size)}"
            )
            self.top_capture.configure(
                text=f"• Captura {'ativa' if active else 'parada'}",
                style=(
                    "TopbarData.TLabel"
                    if active
                    else "Topbar.TLabel"
                ),
            )
            self.bottom_capture.configure(
                text=f"• Captura {'ativa' if active else 'parada'}",
                style=(
                    "TopbarOk.TLabel" if active else "Topbar.TLabel"
                ),
            )
            self.top_decode.configure(
                text=f"Último decode: {self._last_live_decode}"
            )
            self.top_next_decode.configure(
                text=(
                    "Próx. atualização: "
                    f"{max(0, int(self._next_live_decode - time.monotonic()))} s"
                    if active
                    else "Próx. atualização: —"
                )
            )
            elapsed_now = (
                self._paused_at
                if self._paused and self._paused_at is not None
                else datetime.now()
            )
            elapsed = max(
                0,
                _session_elapsed(
                    self.current_session or "",
                    active or self._paused,
                    elapsed_now,
                )
                - self._paused_total_seconds,
            )
            self.capture_elapsed.configure(
                text=(
                    "Tempo decorrido\n"
                    f"{elapsed // 3600:02d}:{elapsed // 60 % 60:02d}:"
                    f"{elapsed % 60:02d}"
                )
            )
            self.queue_mode_times["continuous"].configure(
                text=(
                    f"{elapsed // 3600:02d}:{elapsed // 60 % 60:02d}:"
                    f"{elapsed % 60:02d}"
                    if active or self._paused
                    else "—"
                )
            )
            self.capture_badge.configure(
                text="ATIVO" if active else "PAUSADO" if self._paused else "PARADO",
                style=(
                    "ActiveBadge.TLabel"
                    if active
                    else "Data.TLabel"
                ),
            )
            self.session_since.configure(
                text=(
                    f"Desde {elapsed // 3600:02d}:"
                    f"{elapsed // 60 % 60:02d}:{elapsed % 60:02d}"
                )
            )
            if active:
                cached_subsessions = (
                    self._info_snapshot.get("subsessions", [])
                    if self._info_snapshot
                    and self._info_snapshot.get("session_id") == self.current_session
                    else []
                )
                self._rotate_auto_subsession(cached_subsessions)
            self.start_button.configure(
                state="disabled"
                if active
                or self._paused
                or self._ingesting
                or not self.capture_allowed
                else "normal"
            )
            pending = bool(
                self.prefs.get("capture_pending")
                and self.capture.segment_files()
            )
            self.stop_button.configure(
                state="normal"
                if active or self._paused or pending
                else "disabled"
            )
            if active:
                self.start_button.grid_remove()
                self.pause_button.configure(text="Pausar", state="normal")
                self.pause_button.grid()
            elif self._paused:
                self.start_button.grid_remove()
                self.pause_button.configure(
                    text="Continuar",
                    state=(
                        "normal"
                        if self.capture_allowed and not self._ingesting
                        else "disabled"
                    ),
                )
                self.pause_button.grid()
            else:
                self.pause_button.grid_remove()
                self.start_button.grid()
            for button in self.quick_buttons.values():
                button.configure(state="normal" if active else "disabled")
            stats = self._last_session_stats
            kills = self._last_kills
            lines = [
                f"Captura ativa        {'SIM' if active else 'NÃO'}",
                f"Sessão atual         {self.current_session or '—'}",
                f"Segmentos atuais     {len(status.files)}",
                f"Tamanho da sessão    {_format_bytes(status.bytes_written)}",
                "Pacotes observados   "
                + (
                    str(self._last_packet_count)
                    if self._last_packet_count is not None
                    else "indisponível"
                ),
                f"Eventos reconhecidos {stats['recognized']}",
                f"Sem personagem       {stats['unassigned']}",
                f"Não decodificados    {stats['unknown']}",
                f"Kills estimadas      {kills}  (proxy por recompensa)",
                f"Última atualização   {self._last_live_decode}",
                "",
                "Dados não confirmados permanecem ocultos.",
            ]
            self.metrics.configure(state="normal")
            self.metrics.delete("1.0", END)
            self.metrics.insert("1.0", "\n".join(lines))
            self.metrics.configure(state="disabled")
            self._last_poll_error = ""
        except Exception as error:
            if str(error) != self._last_poll_error:
                self._last_poll_error = str(error)
                self.log.exception("status_poll_failed")
        self.after(1000, self._poll)

    def report_callback_exception(self, exc, value, tb) -> None:
        self.log.error("tk_callback_failed", exc_info=(exc, value, tb))
        messagebox.showerror(
            "Falha inesperada",
            "O problema foi registrado. Use “Enviar log técnico” "
            "na aba Licença para ajudar na correção.",
        )

    def _close(self) -> None:
        self._save_preferences()
        if (
            self.capture.attached
            and self.capture.status().active
            and self.minimize_to_tray
        ):
            try:
                import pystray
                from PIL import Image

                if not self.tray:
                    image = Image.open(ASSETS / "karvalho-symbol-gold.png")
                    self.tray = pystray.Icon(
                        "RF QOL",
                        image,
                        "RF QOL · captura visível",
                        pystray.Menu(
                            pystray.MenuItem(
                                "Abrir", lambda: self.after(0, self.deiconify)
                            ),
                            pystray.MenuItem(
                                "Encerrar", lambda: self.after(0, self._exit)
                            ),
                        ),
                    )
                    threading.Thread(target=self.tray.run, daemon=True).start()
                self.withdraw()
                return
            except Exception:
                pass
        self._exit()

    def _exit(self) -> None:
        if self._live_ingesting is True:
            self._exit_after_live_ingest = True
            self.capture_state.configure(
                text="Finalizando a leitura atual antes de encerrar…"
            )
            return
        if self.capture.attached and self.capture.status().active:
            if not messagebox.askyesno(
                "Encerrar",
                "A captura está ativa. Parar com segurança e encerrar?",
            ):
                return
            self._close_live_preview()
            self.capture.stop()
        self._save_preferences()
        if self.tray:
            self.tray.stop()
        self.store.close()
        self.log.info("app_closed")
        self.destroy()


if __name__ == "__main__":
    _enable_dpi_awareness()
    if "--self-test" in sys.argv:
        App(ui_self_test=True)
        sample, marks = _capture_summary(
            {
                "events": [
                    {
                        "type": "collection_snapshot_chunk",
                        "data": {
                            "fields": {"character_name": "Carvalho"},
                            "records": [
                                {
                                    "collection_index": 1001,
                                    "completed_slots": [0, 2],
                                }
                            ],
                        },
                    }
                ]
            }
        )
        assert sample["character"] == "Carvalho"
        assert marks == {"1001": [1, 3]}
        assert _safe_name("Profile/Teste", "Profile") == "Profile-Teste"
        raise SystemExit(0)
    App().mainloop()
