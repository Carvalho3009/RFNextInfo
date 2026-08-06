#!/usr/bin/env python3
"""Servidor local do piloto FarmReport: PCAP -> decoder -> UI/JSON."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sqlite3
import sys
import threading
import webbrowser
from collections import Counter
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
RFNEXT_ROOT = ROOT.parents[2]
EVENTS_DB_DIR = ROOT.parent.parent / "events-db"
DEFAULT_CAPTURE_DIR = RFNEXT_ROOT / "tools" / "login-session-capture" / "captures"
DEFAULT_ITEMS_CSV = RFNEXT_ROOT / "analysis" / "1.28.5" / "exports" / "items.csv"
DEFAULT_GAME_DB = RFNEXT_ROOT / "tools" / "rftable" / "out" / "rfnext-game-data.sqlite"
ANNOTATIONS_PATH = ROOT / "annotations.json"
SCHEMA = "karvalho.farm-report/v1"
SUBSESSION_SCHEMA = "karvalho.farm-report.subsession/v1"
PORT = 12020

sys.path.insert(0, str(EVENTS_DB_DIR))
import capture_to_db as event_capture  # noqa: E402


def utc_iso(ts_ns: int | None) -> str | None:
    if ts_ns is None:
        return None
    return datetime.fromtimestamp(ts_ns / 1_000_000_000, timezone.utc).isoformat()


def fmt_hms(seconds: float) -> str:
    value = max(0, int(round(seconds)))
    hours, remainder = divmod(value, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def load_annotations() -> dict:
    try:
        return json.loads(ANNOTATIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def validate_client_port(client_port) -> str:
    if not isinstance(client_port, str) or not client_port.isdecimal():
        raise ValueError("Cliente inválido.")
    port_number = int(client_port)
    if not 1 <= port_number <= 65535:
        raise ValueError("Cliente inválido.")
    return client_port


def validate_character_assignment(client_port, name) -> tuple[str, str]:
    client_port = validate_client_port(client_port)
    if not isinstance(name, str):
        raise ValueError("Informe o nome do personagem.")
    name = name.strip()
    if not 1 <= len(name) <= 40 or any(ord(char) < 32 for char in name):
        raise ValueError("O nome deve ter entre 1 e 40 caracteres.")
    return client_port, name


def validate_subsession_details(location, mobs, level) -> tuple[str, str, int | None]:
    values = []
    for label, value in (("localização", location), ("mob", mobs)):
        if not isinstance(value, str):
            raise ValueError(f"Informe {label}.")
        value = value.strip()
        if len(value) > 80 or any(ord(char) < 32 for char in value):
            raise ValueError(f"{label.capitalize()} inválido.")
        values.append(value)
    if level in (None, ""):
        parsed_level = None
    else:
        try:
            parsed_level = int(level)
        except (TypeError, ValueError):
            raise ValueError("Nível inválido.") from None
        if not 1 <= parsed_level <= 999:
            raise ValueError("Nível inválido.")
    return values[0], values[1], parsed_level


def latest_pcap(target: Path) -> Path:
    if target.is_file():
        return target
    candidates = [
        path
        for pattern in ("*.pcap", "*.pcapng")
        for path in target.rglob(pattern)
        if path.is_file()
    ]
    if not candidates:
        raise FileNotFoundError(f"Nenhum PCAP encontrado em {target}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_exp_curve(path: Path = DEFAULT_GAME_DB) -> dict[int, int]:
    with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as connection:
        return dict(connection.execute("SELECT level, need_exp FROM level_curve"))


def load_item_grades(path: Path = DEFAULT_GAME_DB) -> dict[int, int]:
    with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as connection:
        return {int(item_id): int(grade) for item_id, grade in connection.execute("SELECT id, grade FROM item_details")}


def split_location(value) -> tuple[str | None, str | None]:
    value = str(value or "").strip()
    parts = [part.strip() for part in value.replace(" + ", " - ").split(" - ") if part.strip()]
    if len(parts) < 2:
        return value or None, None
    map_name, spot_name = parts[:2]
    if spot_name.casefold().startswith(map_name.casefold()):
        spot_name = spot_name[len(map_name):].strip(" -–—+")
    return map_name, spot_name


def new_character(client_port: str) -> dict:
    return {
        "client_port": client_port,
        "min_ts": None,
        "max_ts": None,
        "reward_min_ts": None,
        "reward_max_ts": None,
        "level": None,
        "name": None,
        "uid": None,
        "exp_current": None,
        "credit_current": None,
        "contribution_current": None,
        "kills": 0,
        "exp_total": 0,
        "credit_total": 0,
        "contribution_total": 0,
        "finalizations": 0,
        "finalization_timestamps": [],
        "loot": Counter(),
        "timeline": [],
    }


def update_bounds(character: dict, ts_ns: int | None, reward: bool = False) -> None:
    if ts_ns is None:
        return
    for low, high in (("min_ts", "max_ts"),):
        character[low] = ts_ns if character[low] is None else min(character[low], ts_ns)
        character[high] = ts_ns if character[high] is None else max(character[high], ts_ns)
    if reward:
        character["reward_min_ts"] = (
            ts_ns
            if character["reward_min_ts"] is None
            else min(character["reward_min_ts"], ts_ns)
        )
        character["reward_max_ts"] = (
            ts_ns
            if character["reward_max_ts"] is None
            else max(character["reward_max_ts"], ts_ns)
        )


def build_subsessions(
    character: dict,
    annotation: dict,
    item_names: dict[int, str],
    item_grades: dict[int, int],
    exp_level: int | None,
) -> list[dict]:
    def parse_timestamp(value):
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None

    markers = [
        (parsed, marker)
        for marker in annotation.get("subsessions", [])
        if (parsed := parse_timestamp(marker.get("started_at"))) is not None
    ]
    markers.sort(key=lambda item: item[0])
    rewards = [
        (parsed, reward)
        for reward in character["timeline"]
        if (parsed := parse_timestamp(reward.get("timestamp"))) is not None
    ]
    finalizations = [
        parsed
        for timestamp in character["finalization_timestamps"]
        if (parsed := parse_timestamp(timestamp)) is not None
    ]
    result = []
    for index, (started_at, marker) in enumerate(markers):
        next_start = markers[index + 1][0] if index + 1 < len(markers) else None
        explicit_end = parse_timestamp(marker.get("ended_at"))
        boundary = min(filter(None, (explicit_end, next_start)), default=None)
        entries = [
            reward
            for timestamp, reward in rewards
            if timestamp >= started_at and (boundary is None or timestamp < boundary)
        ]
        last_entry = max(
            (timestamp for timestamp, _reward in rewards if timestamp >= started_at and (boundary is None or timestamp < boundary)),
            default=None,
        )
        ended_at = boundary or last_entry
        duration = max(0.0, (ended_at - started_at).total_seconds()) if ended_at else 0.0
        hours = duration / 3600 if duration else None
        exp_total = sum(entry["exp"] for entry in entries)
        credit_total = sum(entry["credit"] for entry in entries)
        contribution_total = sum(entry["contribution"] for entry in entries)
        loot_counter = Counter()
        for entry in entries:
            loot_counter.update(entry.get("loot") or {})

        def per_hour(value):
            return value / hours if hours else None

        exp_per_hour = per_hour(exp_total)
        location_map, location_spot = split_location(marker.get("location"))
        raw_mobs = marker.get("mobs") or ""
        mob_list = [
            {"name": name.strip(), "level": marker.get("mob_level")}
            for name in str(raw_mobs).split(",") if name.strip()
        ]
        result.append(
            {
                "name": str(marker.get("name") or "Subsessão"),
                "location": marker.get("location") or None,
                "location_map": location_map,
                "location_spot": location_spot,
                "mobs": marker.get("mobs") or None,
                "mob_list": mob_list,
                "mob_level": marker.get("mob_level"),
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat() if ended_at else None,
                "active": explicit_end is None and next_start is None,
                "duration_seconds": duration,
                "duration_hms": fmt_hms(duration),
                "kills": len(entries),
                "exp_total": exp_total,
                "exp_per_hour": exp_per_hour,
                "exp_percent_total": exp_total * 100 / exp_level if exp_level else None,
                "exp_percent_per_hour": exp_per_hour * 100 / exp_level if exp_level and exp_per_hour is not None else None,
                "credit_total": credit_total,
                "credit_per_hour": per_hour(credit_total),
                "contribution_total": contribution_total,
                "contribution_per_hour": per_hour(contribution_total),
                "finalizations": sum(
                    timestamp >= started_at and (boundary is None or timestamp < boundary)
                    for timestamp in finalizations
                ),
                "loot": [
                    {
                        "item_index": item_index,
                        "name": item_names.get(int(item_index), f"Item {item_index}"),
                        "quantity": quantity,
                        "rarity": item_grades.get(int(item_index)),
                    }
                    for item_index, quantity in loot_counter.most_common()
                ],
            }
        )
    return result


def build_character(
    character: dict,
    annotation: dict,
    item_names: dict[int, str],
    item_grades: dict[int, int],
    exp_curve: dict[int, int],
) -> dict:
    start = character["reward_min_ts"] or character["min_ts"]
    end = character["reward_max_ts"] or character["max_ts"]
    duration = ((end - start) / 1_000_000_000) if start and end else 0.0
    hours = duration / 3600 if duration > 0 else None
    kills = character["kills"]
    level = character["level"]
    name = annotation.get("name") or character["name"]
    uid = character["uid"] or annotation.get("uid")
    identity_source = (
        annotation.get("identity_source", "manual_assignment")
        if annotation.get("name")
        else "decoded_world_info" if character["name"] else "client_port_only"
    )
    exp_current = character["exp_current"]
    exp_level = exp_curve.get(level + 1) if level is not None else None
    subsessions = build_subsessions(character, annotation, item_names, item_grades, exp_level)
    exp_missing = max(0, exp_level - exp_current) if exp_level is not None and exp_current is not None else None
    exp_percent = exp_current * 100 / exp_level if exp_level and exp_current is not None else None
    def per_mob(value: int) -> float | None:
        return value / kills if kills else None

    def per_hour(value: int) -> float | None:
        return value / hours if hours else None

    exp_per_hour = per_hour(character["exp_total"])

    loot = [
        {
            "item_index": item_index,
            "name": item_names.get(item_index, f"Item {item_index}"),
            "quantity": quantity,
            "rarity": item_grades.get(item_index),
        }
        for item_index, quantity in character["loot"].most_common()
    ]
    mob = annotation.get("mob")
    mobs = []
    if kills:
        mobs.append(
            {
                "id": mob.get("id") if mob else None,
                "name": mob.get("name") if mob else "Mob não identificado",
                "level": mob.get("level") if mob else None,
                "kills": kills,
                "exp_per_mob": per_mob(character["exp_total"]),
                "credit_per_mob": per_mob(character["credit_total"]),
                "contribution_per_mob": per_mob(character["contribution_total"]),
                "loot_quantity": sum(entry["quantity"] for entry in loot),
                "identification_source": "user_marked_capture" if mob else "pending_decode",
            }
        )

    return {
        "id": uid or f"client-port:{character['client_port']}",
        "client_port": character["client_port"],
        "order": annotation.get("order", 999),
        "character": {
            "name": name or f"Cliente {character['client_port']}",
            "uid": uid,
            "level": level,
            "exp_current": exp_current,
            "exp_level": exp_level,
            "exp_percent": exp_percent,
            "exp_missing": exp_missing,
            "credit": character["credit_current"],
            "diamond": None,
            "combat_power": None,
            "atk": None,
            "def": None,
            "acc": None,
            "inventory": None,
            "contribution_current": character["contribution_current"],
        },
        "session": {
            "started_at": utc_iso(start),
            "ended_at": utc_iso(end),
            "duration_seconds": duration,
            "duration_hms": fmt_hms(duration),
            "kills": kills,
            "exp_total": character["exp_total"],
            "exp_per_mob": per_mob(character["exp_total"]),
            "exp_per_hour": exp_per_hour,
            "exp_percent_per_hour": exp_per_hour * 100 / exp_level if exp_level and exp_per_hour is not None else None,
            "credit_total": character["credit_total"],
            "credit_per_mob": per_mob(character["credit_total"]),
            "credit_per_hour": per_hour(character["credit_total"]),
            "contribution_total": character["contribution_total"],
            "contribution_per_mob": per_mob(character["contribution_total"]),
            "contribution_per_hour": per_hour(character["contribution_total"]),
            "finalizations": character["finalizations"],
        },
        "mobs": mobs,
        "loot": loot,
        "subsessions": subsessions,
        "timeline": character["timeline"][-12:],
        "warnings": [annotation["pvp_warning"]] if annotation.get("pvp_warning") else [],
        "data_quality": {
            "character_identity": identity_source,
            "mob_identity": "user_marked_capture" if mob else "pending_decode",
            "reward_values": "decoded",
            "experience_curve": "database" if exp_level is not None else "pending",
            "unknown_fields_are_null": True,
        },
    }


def decode_report(pcap: Path, items_csv: Path = DEFAULT_ITEMS_CSV) -> dict:
    annotations = load_annotations()
    pcap_annotation = annotations.get(pcap.name, {})
    character_annotations = pcap_annotation.get("characters", {})
    known_connections = annotations.get("_known_connections", {})
    characters: dict[str, dict] = {}
    item_names = event_capture.load_item_names(items_csv if items_csv.is_file() else None)
    item_grades = load_item_grades()
    exp_curve = load_exp_curve()
    total_frames = 0

    for flow, _decoded, info, _bundle_seq in event_capture.iter_decoded_frames(
        pcap, PORT, items_csv if items_csv.is_file() else None
    ):
        total_frames += 1
        client_port, _direction = event_capture.client_port_and_direction(flow)
        if client_port is None:
            continue
        character = characters.setdefault(client_port, new_character(client_port))
        ts_ns = info.get("pcap_time_ns")
        update_bounds(character, ts_ns)
        observation = info.get("observation") or {}

        if observation.get("type") == "update_exp":
            character["level"] = observation.get("level", character["level"])
            character["exp_current"] = observation.get("exp", character["exp_current"])
            if observation.get("action_code") == 1006:
                character["finalizations"] += 1
                character["finalization_timestamps"].append(utc_iso(ts_ns))

        if observation.get("type") == "drop_item_field":
            reward = {"timestamp": utc_iso(ts_ns), "exp": 0, "credit": 0, "contribution": 0, "loot": {}}
            for result in observation.get("results", []):
                item_index = result.get("item_index")
                count = int(result.get("count") or 0)
                if item_index == 900:
                    reward["exp"] += count
                elif item_index == 1:
                    reward["credit"] += count
                    if result.get("gain_total") is not None:
                        character["credit_current"] = result["gain_total"]
                elif item_index == 1701:
                    reward["contribution"] += count
                elif item_index is not None and count:
                    character["loot"][item_index] += count
                    reward["loot"][item_index] = reward["loot"].get(item_index, 0) + count
            if reward["exp"] > 0:
                character["kills"] += 1
                character["exp_total"] += reward["exp"]
                character["credit_total"] += reward["credit"]
                character["contribution_total"] += reward["contribution"]
                character["timeline"].append(reward)
                update_bounds(character, ts_ns, reward=True)

        decoded = info.get("decoded") or {}
        if decoded.get("type") == "world_info_prefix":
            fields = decoded.get("fields") or {}
            character["name"] = fields.get("character_name") or character["name"]
            uid = fields.get("character_uid")
            character["uid"] = str(uid) if uid is not None else character["uid"]
            character["level"] = fields.get("level", character["level"])
        if decoded.get("type") == "realm_contribution_update":
            character["contribution_current"] = decoded.get("contribution_total")

    sha256 = file_sha256(pcap)
    effective_annotations = {
        port: {**known_connections.get(port, {}), **character_annotations.get(port, {})}
        for port in characters
    }
    annotation_hash = hashlib.sha256(
        json.dumps(effective_annotations, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    report_id = hashlib.sha256(f"{SCHEMA}:{sha256}:{annotation_hash}".encode()).hexdigest()[:24]
    stat = pcap.stat()
    output_characters = [
        build_character(
            character,
            effective_annotations[port],
            item_names,
            item_grades,
            exp_curve,
        )
        for port, character in characters.items()
        if character["kills"] or character["exp_current"] is not None
    ]
    output_characters.sort(key=lambda entry: (entry.pop("order"), entry["character"]["name"]))
    return {
        "schema": SCHEMA,
        "report_id": report_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "pcap_file": pcap.name,
            "pcap_sha256": sha256,
            "pcap_size": stat.st_size,
            "pcap_modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "decoder": "tools/events-db/rfnext_frame_decode.py",
            "decoder_port": PORT,
            "decoded_frames": total_frames,
            "annotation_source": pcap_annotation.get("source"),
            "experience_curve": "tools/rftable/out/rfnext-game-data.sqlite:level_curve",
        },
        "characters": output_characters,
        "site_import": {
            "contract": SCHEMA,
            "idempotency_key": report_id,
            "recommended_target": "rfnext.db",
            "write_status": "export_only",
        },
    }


def refresh_active_subsessions(report: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    for entry in report["characters"]:
        for subsession in entry["subsessions"]:
            if not subsession["active"]:
                continue
            duration = max(0.0, (now - datetime.fromisoformat(subsession["started_at"])).total_seconds())
            hours = duration / 3600 if duration else None
            subsession["duration_seconds"] = duration
            subsession["duration_hms"] = fmt_hms(duration)
            for total, rate in (
                ("exp_total", "exp_per_hour"),
                ("credit_total", "credit_per_hour"),
                ("contribution_total", "contribution_per_hour"),
            ):
                subsession[rate] = subsession[total] / hours if hours else None
            exp_level = entry["character"]["exp_level"]
            subsession["exp_percent_per_hour"] = (
                subsession["exp_per_hour"] * 100 / exp_level
                if exp_level and subsession["exp_per_hour"] is not None
                else None
            )
    return report


def build_subsession_export(report: dict, client_port, started_at) -> dict:
    client_port = validate_client_port(client_port)
    if not isinstance(started_at, str):
        raise ValueError("Subsessão inválida.")
    try:
        datetime.fromisoformat(started_at)
    except ValueError:
        raise ValueError("Subsessão inválida.") from None
    entry = next(
        (item for item in report["characters"] if item["client_port"] == client_port),
        None,
    )
    subsession = next(
        (item for item in entry["subsessions"] if item["started_at"] == started_at),
        None,
    ) if entry else None
    if subsession is None or subsession["active"] or not subsession["ended_at"]:
        raise ValueError("A subsessão precisa estar encerrada.")
    export_id = hashlib.sha256(
        f"{SUBSESSION_SCHEMA}:{entry['id']}:{client_port}:{started_at}:{subsession['ended_at']}".encode()
    ).hexdigest()
    return {
        "schema": SUBSESSION_SCHEMA,
        "subsession_id": export_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": report["source"],
        "character": {
            "id": entry["id"],
            "client_port": client_port,
            **entry["character"],
        },
        "subsession": subsession,
        "site_import": {
            "contract": SUBSESSION_SCHEMA,
            "idempotency_key": export_id,
            "recommended_target": "rfnext.db",
            "write_status": "export_only",
        },
    }


class ReportCache:
    def __init__(self, target: Path):
        self.target = target
        self.key = None
        self.value = None
        self.lock = threading.Lock()

    def get(self) -> dict:
        pcap = latest_pcap(self.target)
        stat = pcap.stat()
        key = (str(pcap.resolve()), stat.st_mtime_ns, stat.st_size)
        with self.lock:
            if key != self.key:
                self.value = decode_report(pcap)
                self.key = key
            result = copy.deepcopy(self.value)
        return refresh_active_subsessions(result)

    def set_character_name(self, client_port, name) -> dict:
        client_port, name = validate_character_assignment(client_port, name)
        pcap = latest_pcap(self.target)
        with self.lock:
            annotations = load_annotations()
            # ponytail: a porta identifica a conexão atual; migre para UID quando todo PCAP o expuser.
            for entry in (
                annotations.setdefault("_known_connections", {}).setdefault(client_port, {}),
                annotations.setdefault(pcap.name, {}).setdefault("characters", {}).setdefault(client_port, {}),
            ):
                entry.update({"name": name, "identity_source": "manual_assignment"})
            temporary = ANNOTATIONS_PATH.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(annotations, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(ANNOTATIONS_PATH)
            self.key = None
        return self.get()

    def start_subsession(self, client_port, name) -> dict:
        client_port, name = validate_character_assignment(client_port, name)
        pcap = latest_pcap(self.target)
        with self.lock:
            annotations = load_annotations()
            character = (
                annotations.setdefault(pcap.name, {})
                .setdefault("characters", {})
                .setdefault(client_port, {})
            )
            character.setdefault("subsessions", []).append(
                {
                    "name": name,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            temporary = ANNOTATIONS_PATH.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(annotations, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(ANNOTATIONS_PATH)
            self.key = None
        return self.get()

    def set_subsession_details(self, client_port, location, mobs, level) -> dict:
        client_port = validate_client_port(client_port)
        location, mobs, level = validate_subsession_details(location, mobs, level)
        pcap = latest_pcap(self.target)
        with self.lock:
            annotations = load_annotations()
            subsessions = (
                annotations.get(pcap.name, {})
                .get("characters", {})
                .get(client_port, {})
                .get("subsessions", [])
            )
            active = subsessions[-1] if subsessions and not subsessions[-1].get("ended_at") else None
            if active is None:
                raise ValueError("Nenhuma subsessão ativa.")
            active.update({"location": location, "mobs": mobs, "mob_level": level})
            temporary = ANNOTATIONS_PATH.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(annotations, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(ANNOTATIONS_PATH)
            self.key = None
        return self.get()

    def end_subsession(self, client_port) -> dict:
        client_port = validate_client_port(client_port)
        pcap = latest_pcap(self.target)
        with self.lock:
            annotations = load_annotations()
            subsessions = (
                annotations.get(pcap.name, {})
                .get("characters", {})
                .get(client_port, {})
                .get("subsessions", [])
            )
            active = subsessions[-1] if subsessions and not subsessions[-1].get("ended_at") else None
            if active is None:
                raise ValueError("Nenhuma subsessão ativa.")
            active["ended_at"] = datetime.now(timezone.utc).isoformat()
            temporary = ANNOTATIONS_PATH.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(annotations, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(ANNOTATIONS_PATH)
            self.key = None
        return self.get()

    def export_subsession(self, client_port, started_at) -> dict:
        return build_subsession_export(self.get(), client_port, started_at)


def make_handler(cache: ReportCache):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ROOT), **kwargs)

        def send_json(self, payload: dict, download: bool = False, filename: str | None = None) -> None:
            raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            if download:
                filename = filename or f"karvalho-farm-report-{payload['report_id']}.json"
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            request = urlparse(self.path)
            path = request.path.rstrip("/")
            if path == "/api/health":
                self.send_json({"ok": True, "schema": SCHEMA})
                return
            if path == "/api/subsession/export":
                try:
                    query = parse_qs(request.query)
                    payload = cache.export_subsession(
                        query.get("client_port", [None])[0],
                        query.get("started_at", [None])[0],
                    )
                    self.send_json(
                        payload,
                        download=True,
                        filename=f"karvalho-farm-subsession-{payload['subsession_id']}.json",
                    )
                except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
                    self.send_error(400, str(exc))
                return
            if path in ("/api/report", "/api/export"):
                try:
                    self.send_json(cache.get(), download=path == "/api/export")
                except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
                    self.send_error(500, str(exc))
                return
            super().do_GET()

        def do_POST(self):
            path = urlparse(self.path).path.rstrip("/")
            if path not in (
                "/api/character-name",
                "/api/subsession",
                "/api/subsession/details",
                "/api/subsession/end",
            ):
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    raise ValueError("Requisição inválida.")
                payload = json.loads(self.rfile.read(length))
                if path == "/api/character-name":
                    result = cache.set_character_name(payload.get("client_port"), payload.get("name"))
                elif path == "/api/subsession":
                    result = cache.start_subsession(
                        payload.get("client_port"),
                        payload.get("name"),
                    )
                elif path == "/api/subsession/details":
                    result = cache.set_subsession_details(
                        payload.get("client_port"),
                        payload.get("location", ""),
                        payload.get("mobs", ""),
                        payload.get("level"),
                    )
                else:
                    result = cache.end_subsession(payload.get("client_port"))
                self.send_json(result)
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                self.send_error(400, str(exc))
            except OSError as exc:
                self.send_error(500, str(exc))

        def log_message(self, message, *args):
            print(f"[pilot] {self.address_string()} - {message % args}")

    return Handler


def self_test() -> None:
    assert validate_character_assignment("19128", " FernanTorres ") == ("19128", "FernanTorres")
    assert validate_subsession_details("Deserto", "Sniper", "75") == ("Deserto", "Sniper", 75)
    try:
        validate_character_assignment("70000", "")
    except ValueError:
        pass
    else:
        raise AssertionError("atribuição inválida aceita")

    sample = new_character("19128")
    sample.update(
        {
            "level": 66,
            "reward_min_ts": 1_000_000_000,
            "reward_max_ts": 3_000_000_000,
            "kills": 2,
            "exp_total": 200,
            "credit_total": 20,
            "contribution_total": 10,
            "timeline": [
                {"timestamp": utc_iso(1_500_000_000), "exp": 100, "credit": 10, "contribution": 5, "loot": {}},
                {"timestamp": utc_iso(2_500_000_000), "exp": 100, "credit": 10, "contribution": 5, "loot": {42: 2}},
            ],
            "finalization_timestamps": [utc_iso(2_400_000_000)],
        }
    )
    built = build_character(
        sample,
        {"name": "Teste", "uid": "1", "mob": {"name": "Mob", "level": 75}},
        {},
        {},
        {67: 400},
    )
    assert built["session"]["exp_per_mob"] == 100
    assert built["session"]["credit_per_mob"] == 10
    assert built["session"]["duration_seconds"] == 2
    built = build_character(
        sample,
        {"name": "Teste", "subsessions": [{
            "name": "Agora",
            "location": "Deserto",
            "mobs": "Sniper",
            "mob_level": 75,
            "started_at": utc_iso(2_000_000_000),
        }]},
        {42: "Loot teste"},
        {42: 4},
        {67: 400},
    )
    assert built["subsessions"][0]["kills"] == 1
    assert built["subsessions"][0]["exp_total"] == 100
    assert built["subsessions"][0]["finalizations"] == 1
    assert built["subsessions"][0]["loot"][0]["quantity"] == 2
    assert built["subsessions"][0]["loot"][0]["rarity"] == 4
    assert built["subsessions"][0]["exp_percent_total"] == 25
    assert built["subsessions"][0]["mob_list"] == [{"name": "Sniper", "level": 75}]
    assert built["subsessions"][0]["location"] == "Deserto"
    assert built["subsessions"][0]["mobs"] == "Sniper"
    assert built["subsessions"][0]["mob_level"] == 75
    refresh_active_subsessions(
        {"characters": [built]},
        datetime.fromtimestamp(12, timezone.utc),
    )
    assert built["subsessions"][0]["duration_seconds"] == 10
    assert built["subsessions"][0]["exp_per_hour"] == 36000
    built = build_character(
        sample,
        {"subsessions": [{
            "name": "Encerrada",
            "started_at": utc_iso(2_000_000_000),
            "ended_at": utc_iso(3_000_000_000),
        }]},
        {},
        {},
        {67: 400},
    )
    assert built["subsessions"][0]["active"] is False
    assert built["subsessions"][0]["duration_seconds"] == 1
    exported = build_subsession_export(
        {
            "report_id": "report-test",
            "source": {"pcap_file": "test.pcap"},
            "characters": [{
                "id": "1",
                "client_port": "19128",
                "character": {"name": "Teste"},
                "subsessions": built["subsessions"],
            }],
        },
        "19128",
        utc_iso(2_000_000_000),
    )
    assert exported["schema"] == SUBSESSION_SCHEMA
    assert exported["subsession"]["name"] == "Encerrada"
    assert exported["site_import"]["idempotency_key"] == exported["subsession_id"]
    second_export = build_subsession_export(
        {
            "report_id": "report-changed",
            "source": {"pcap_file": "test.pcap"},
            "characters": [{
                "id": "1",
                "client_port": "19128",
                "character": {"name": "Teste"},
                "subsessions": built["subsessions"],
            }],
        },
        "19128",
        utc_iso(2_000_000_000),
    )
    assert second_export["subsession_id"] == exported["subsession_id"]
    sample["level"] = 66
    sample["exp_current"] = 300
    sample["name"] = "Nome Decodificado"
    sample["uid"] = "42"
    built = build_character(sample, {"name": "Nome Manual"}, {}, {}, {67: 400})
    assert built["character"]["name"] == "Nome Manual"
    assert built["character"]["uid"] == "42"
    assert built["data_quality"]["character_identity"] == "manual_assignment"
    assert built["character"]["exp_percent"] == 75
    assert built["character"]["exp_missing"] == 100
    assert built["session"]["exp_percent_per_hour"] == 90000
    print("self-test: ok")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_CAPTURE_DIR)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0

    cache = ReportCache(args.input)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(cache))
    url = f"http://{args.host}:{args.port}/"
    print(f"FarmReport piloto: {url}")
    print(f"PCAP: {args.input}")
    if args.open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
