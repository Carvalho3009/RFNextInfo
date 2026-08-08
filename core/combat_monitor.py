"""Resumo efêmero de combate usando somente campos confirmados do decoder."""

from __future__ import annotations

import time
from typing import Any, Iterable


def summarize_combat(
    events: Iterable[dict[str, Any]],
    character_uid: str,
    npc_names: dict[int, str] | None = None,
    *,
    boss_catalog: dict[int, dict[str, Any]] | None = None,
    now_ns: int | None = None,
    dps_window_seconds: int = 10,
    stale_seconds: int = 15,
) -> dict[str, Any]:
    ordered = sorted(events, key=lambda event: (event.get("ts_ns") or 0))
    players: dict[int, dict[str, Any]] = {}
    monsters: dict[int, dict[str, Any]] = {}
    local_uid: int | None = None
    npc_names = npc_names or {}
    boss_catalog = boss_catalog or {}
    damage: list[dict[str, int]] = []
    hp_history: dict[int, list[tuple[int, int]]] = {}
    target_damage: dict[int, dict[int, int]] = {}
    last_pve: tuple[int, int] | None = None
    last_pvp: tuple[int, int, str] | None = None
    for event in ordered:
        data = event.get("data") or {}
        timestamp = int(event.get("ts_ns") or 0)
        kind = event.get("type")
        if kind == "appear_player_list":
            for unit in data.get("units") or []:
                uid = _integer(unit.get("uid"))
                if uid is None:
                    continue
                monsters.pop(uid, None)
                players[uid] = _entity("player", unit, timestamp)
                _record_hp(hp_history, uid, timestamp, players[uid].get("current_hp"))
                if str(unit.get("character_uid")) == str(character_uid):
                    local_uid = uid
        elif kind == "appear_monster_list":
            for unit in data.get("units") or []:
                uid = _integer(unit.get("uid"))
                if uid is None:
                    continue
                players.pop(uid, None)
                monsters[uid] = _entity("monster", unit, timestamp)
                _record_hp(hp_history, uid, timestamp, monsters[uid].get("current_hp"))
        elif kind == "restore_hp_fp":
            uid = _integer(data.get("uid"))
            entity = players.get(uid) or monsters.get(uid)
            if entity:
                _update_hp(entity, data, timestamp)
                _record_hp(hp_history, uid, timestamp, entity.get("current_hp"))
        elif kind == "dying_unit":
            uid = _integer(data.get("uid"))
            entity = players.get(uid) or monsters.get(uid)
            if entity:
                entity["current_hp"] = 0
                entity["dead"] = True
                entity["last_seen_ns"] = timestamp
                _record_hp(hp_history, uid, timestamp, 0)
        elif kind in {"use_skill_result", "use_normal_skill_result"}:
            if data.get("ret") not in (None, 0):
                continue
            caster = _integer(data.get("caster_uid"))
            caster_entity = players.get(caster) or monsters.get(caster)
            if caster_entity and data.get("caster_final_hp") is not None:
                caster_entity["current_hp"] = int(data["caster_final_hp"])
                caster_entity["last_seen_ns"] = timestamp
                _record_hp(
                    hp_history, caster, timestamp, caster_entity.get("current_hp")
                )
            for result in data.get("effect_results") or []:
                target = _integer(result.get("uid"))
                if target is None:
                    continue
                target_entity = players.get(target) or monsters.get(target)
                if target_entity and result.get("final_hp") is not None:
                    target_entity["current_hp"] = int(result["final_hp"])
                    target_entity["dead"] = int(result["final_hp"]) == 0
                    target_entity["last_seen_ns"] = timestamp
                    _record_hp(
                        hp_history, target, timestamp, target_entity.get("current_hp")
                    )
                hp_damage = max(0, int(result.get("hp_damage") or 0))
                if caster is not None and hp_damage:
                    by_caster = target_damage.setdefault(target, {})
                    by_caster[caster] = by_caster.get(caster, 0) + hp_damage
                if local_uid is None:
                    continue
                if caster == local_uid and target in monsters:
                    last_pve = (timestamp, target)
                if caster == local_uid and target in players:
                    last_pvp = (timestamp, target, "saída")
                    damage.append(
                        {
                            "ts_ns": timestamp,
                            "target_uid": target,
                            "hp_damage": hp_damage,
                        }
                    )
                elif target == local_uid and caster in players:
                    last_pvp = (timestamp, caster, "entrada")

    reference_ns = int(now_ns if now_ns is not None else time.time_ns())
    bosses = []
    for entity in monsters.values():
        npc_index = _integer(entity.get("npc_index"))
        metadata = boss_catalog.get(npc_index) if npc_index is not None else None
        if not metadata or entity.get("dead") or entity.get("current_hp") == 0:
            continue
        boss = _target_snapshot(
            entity,
            reference_ns,
            stale_seconds,
            fallback_name=str(metadata.get("name") or "") or None,
        )
        if boss:
            _add_boss_rates(
                boss,
                hp_history.get(int(entity["uid"]), []),
                reference_ns,
                dps_window_seconds,
            )
            boss["top_damage_players"] = _top_damage_players(
                target_damage.get(int(entity["uid"]), {}), players
            )
            boss["top_damage_guilds"] = _top_damage_groups(
                target_damage.get(int(entity["uid"]), {}), players, "guild"
            )
            boss["top_damage_groups"] = _top_damage_groups(
                target_damage.get(int(entity["uid"]), {}), players, "group"
            )
            boss.update(
                level=_integer(metadata.get("level")),
                npc_subtype=_integer(metadata.get("npc_subtype")),
            )
            bosses.append(boss)
    bosses.sort(key=lambda item: (-int(item.get("last_seen_ns") or 0), str(item.get("name") or "")))
    nearby_players_by_identity: dict[str, dict[str, Any]] = {}
    for uid, entity in players.items():
        character = str(entity.get("character_uid") or "").strip()
        name = str(entity.get("name") or "").strip()
        if uid == local_uid or not character or not name:
            continue
        target = _target_snapshot(entity, reference_ns, stale_seconds)
        if not target or target["stale"] or target.get("dead"):
            continue
        previous = nearby_players_by_identity.get(character)
        if not previous or int(target.get("last_seen_ns") or 0) > int(
            previous.get("last_seen_ns") or 0
        ):
            nearby_players_by_identity[character] = target
    nearby_players = list(nearby_players_by_identity.values())
    nearby_players.sort(key=lambda item: str(item.get("name") or "").casefold())
    nearby_monsters_by_type: dict[int, dict[str, Any]] = {}
    for entity in monsters.values():
        target = _target_snapshot(
            entity,
            reference_ns,
            stale_seconds,
            fallback_name=npc_names.get(int(entity.get("npc_index") or 0)),
        )
        npc_index = _integer(entity.get("npc_index"))
        if (
            npc_index is not None
            and target
            and not target["stale"]
            and not target.get("dead")
        ):
            nearby_monsters_by_type[npc_index] = target
    local = _target_snapshot(players.get(local_uid), reference_ns, stale_seconds)
    local_realm = (players.get(local_uid) or {}).get("realm")
    allies = sum(
        1
        for player in nearby_players
        if local_realm is not None and player.get("realm") == local_realm
    )
    enemies = sum(
        1
        for player in nearby_players
        if local_realm is not None and player.get("realm") != local_realm
    )
    by_guild: dict[str, int] = {}
    for player in nearby_players:
        guild = str(player.get("guild_name") or player.get("guild_id") or "").strip()
        if guild:
            by_guild[guild] = by_guild.get(guild, 0) + 1
    return {
        "local_combat_uid": local_uid,
        "local": local,
        "nearby_players": nearby_players,
        "nearby_monsters": list(nearby_monsters_by_type.values()),
        "player_counts": {
            "allies": allies,
            "enemies": enemies,
            "unknown": len(nearby_players) - allies - enemies,
            "by_guild": dict(sorted(by_guild.items(), key=lambda item: (-item[1], item[0]))),
        },
        "bosses": bosses,
        "pve": _target_snapshot(
            monsters.get(last_pve[1]) if last_pve else None,
            reference_ns,
            stale_seconds,
            fallback_name=(
                npc_names.get(int(monsters[last_pve[1]].get("npc_index") or 0))
                if last_pve and last_pve[1] in monsters else None
            ),
        ),
        "pvp": _pvp_snapshot(
            players.get(last_pvp[1]) if last_pvp else None,
            last_pvp,
            damage,
            reference_ns,
            dps_window_seconds,
            stale_seconds,
        ),
    }


def _integer(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None


def _entity(kind: str, unit: dict[str, Any], timestamp: int) -> dict[str, Any]:
    return {
        "kind": kind,
        "uid": int(unit["uid"]),
        "character_uid": unit.get("character_uid"),
        "name": str(unit.get("name") or ""),
        "npc_index": unit.get("npc_index"),
        "biosuit_item_index": unit.get("biosuit_item_index"),
        "rover_item_index": unit.get("rover_item_index"),
        "level": _integer(unit.get("level")),
        "realm": _integer(unit.get("realm_raw", unit.get("realm"))),
        "guild_id": unit.get("guild_id"),
        "guild_name": str(unit.get("guild_name") or ""),
        "group_id": unit.get("group_id") or unit.get("party_id"),
        "max_hp": _integer(unit.get("max_hp")),
        "current_hp": _integer(unit.get("current_hp")),
        "dead": False,
        "last_seen_ns": timestamp,
    }


def _update_hp(entity: dict[str, Any], data: dict[str, Any], timestamp: int) -> None:
    entity["current_hp"] = _integer(data.get("current_hp"))
    entity["max_hp"] = _integer(data.get("max_hp")) or entity.get("max_hp")
    entity["dead"] = entity["current_hp"] == 0
    entity["last_seen_ns"] = timestamp


def _record_hp(
    history: dict[int, list[tuple[int, int]]],
    uid: int | None,
    timestamp: int,
    current_hp: Any,
) -> None:
    if uid is None or not isinstance(current_hp, int):
        return
    values = history.setdefault(uid, [])
    if not values or values[-1][1] != current_hp:
        values.append((timestamp, current_hp))


def _add_boss_rates(
    boss: dict[str, Any],
    history: list[tuple[int, int]],
    now_ns: int,
    window_seconds: int,
) -> None:
    cutoff = now_ns - window_seconds * 1_000_000_000
    recent = [point for point in history if point[0] >= cutoff]
    if len(recent) < 2:
        boss.update(dps_hp=None, eta_seconds=None, dps_window_seconds=window_seconds)
        return
    elapsed = (recent[-1][0] - recent[0][0]) / 1_000_000_000
    dps = (
        max(0.0, (recent[0][1] - recent[-1][1]) / elapsed)
        if elapsed > 0
        else 0.0
    )
    current = boss.get("current_hp")
    boss.update(
        dps_hp=round(dps, 1),
        eta_seconds=(
            round(current / dps, 1)
            if isinstance(current, int) and dps > 0
            else None
        ),
        dps_window_seconds=window_seconds,
    )


def _top_damage_players(
    damage: dict[int, int], players: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    rows = [
        {
            "uid": uid,
            "name": str((players.get(uid) or {}).get("name") or f"UID {uid}"),
            "damage": amount,
        }
        for uid, amount in damage.items()
        if amount > 0
    ]
    return sorted(
        rows, key=lambda row: (-int(row["damage"]), row["name"])
    )[:10]


def _top_damage_groups(
    damage: dict[int, int],
    players: dict[int, dict[str, Any]],
    group_type: str,
) -> list[dict[str, Any]]:
    totals: dict[str, int] = {}
    for uid, amount in damage.items():
        player = players.get(uid) or {}
        if group_type == "guild":
            name = str(player.get("guild_name") or player.get("guild_id") or "").strip()
        else:
            name = str(player.get("group_id") or "").strip()
        if name and amount > 0:
            totals[name] = totals.get(name, 0) + amount
    return [
        {"name": name, "damage": amount}
        for name, amount in sorted(totals.items(), key=lambda item: (-item[1], item[0]))[:10]
    ]


def _target_snapshot(
    entity: dict[str, Any] | None,
    now_ns: int,
    stale_seconds: int,
    *,
    fallback_name: str | None = None,
) -> dict[str, Any] | None:
    if not entity:
        return None
    age = max(0.0, (now_ns - int(entity.get("last_seen_ns") or 0)) / 1_000_000_000)
    current = entity.get("current_hp")
    maximum = entity.get("max_hp")
    return {
        **entity,
        "name": entity.get("name") or fallback_name or (
            f"NPC {entity.get('npc_index')}" if entity.get("npc_index") else "Alvo confirmado"
        ),
        "hp_percent": round(current * 100 / maximum, 2)
        if isinstance(current, int) and isinstance(maximum, int) and maximum > 0
        else None,
        "age_seconds": round(age, 1),
        "stale": age > stale_seconds,
    }


def _pvp_snapshot(
    entity: dict[str, Any] | None,
    last_pvp: tuple[int, int, str] | None,
    damage: list[dict[str, int]],
    now_ns: int,
    window_seconds: int,
    stale_seconds: int,
) -> dict[str, Any] | None:
    target = _target_snapshot(entity, now_ns, stale_seconds)
    if not target or not last_pvp:
        return None
    cutoff = now_ns - window_seconds * 1_000_000_000
    total = sum(
        item["hp_damage"]
        for item in damage
        if item["target_uid"] == last_pvp[1] and item["ts_ns"] >= cutoff
    )
    target.update(
        {
            "direction": last_pvp[2],
            "dps_hp": round(total / window_seconds, 1),
            "dps_window_seconds": window_seconds,
        }
    )
    return target
