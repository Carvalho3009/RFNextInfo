"""Resumo efêmero de combate usando somente campos confirmados do decoder."""

from __future__ import annotations

import time
from typing import Any, Iterable


NEARBY_PLAYER_STALE_SECONDS = 10
EXP_ACTIVITY_STALE_SECONDS = 10
PVE_ACTIVITY_STALE_SECONDS = 30
LOCAL_SKILL_CORRELATION_SECONDS = 3


def summarize_combat(
    events: Iterable[dict[str, Any]],
    character_uid: str,
    npc_names: dict[int, str] | None = None,
    *,
    boss_catalog: dict[int, dict[str, Any]] | None = None,
    now_ns: int | None = None,
    dps_window_seconds: int = 10,
    stale_seconds: int = 15,
    nearby_stale_seconds: int = NEARBY_PLAYER_STALE_SECONDS,
    pvp_stale_seconds: int = 3,
    modes: Iterable[str] | None = None,
) -> dict[str, Any]:
    active_modes = {"pve", "pvp", "boss"} if modes is None else set(modes)
    ordered = sorted(events, key=lambda event: (event.get("ts_ns") or 0))
    players: dict[int, dict[str, Any]] = {}
    monsters: dict[int, dict[str, Any]] = {}
    guild_relations: dict[str, tuple[str, str]] = {}
    local_uid: int | None = None
    npc_names = npc_names or {}
    boss_catalog = boss_catalog or {}
    damage: list[dict[str, int]] = []
    hp_history: dict[int, list[tuple[int, int]]] = {}
    target_damage: dict[int, dict[int, list[tuple[int, int]]]] = {}
    accumulated_target_damage: dict[int, dict[int, tuple[int, int]]] = {}
    accumulated_damage_players: dict[int, dict[str, Any]] = {}
    local_skill_requests: list[tuple[int, int | None, int | None, int | None]] = []
    last_pve: tuple[int, int] | None = None
    last_pve_activity: tuple[int, int, str] | None = None
    last_pve_kill: tuple[int, int, str] | None = None
    local_death: tuple[int, int, str] | None = None
    last_pvp: tuple[int, int, str] | None = None
    last_pvp_damage: tuple[int, int, str] | None = None
    last_exp_gain: tuple[int, int] | None = None
    selected_target: tuple[int, int] | None = None
    for event in ordered:
        data = event.get("data") or {}
        fields = data.get("fields") if isinstance(data.get("fields"), dict) else data
        timestamp = int(event.get("ts_ns") or 0)
        kind = event.get("type")
        if kind == "boss_damage_total":
            target_uid = _integer(data.get("target_uid"))
            caster_uid = _integer(data.get("caster_uid"))
            amount = _integer(data.get("damage"))
            first_seen_ns = _integer(data.get("first_seen_ns"))
            last_seen_ns = _integer(data.get("last_seen_ns"))
            if (
                target_uid is not None
                and caster_uid is not None
                and amount is not None
                and amount > 0
            ):
                accumulated_target_damage.setdefault(target_uid, {})[
                    caster_uid
                ] = (first_seen_ns or timestamp, amount)
                player = data.get("player")
                if isinstance(player, dict):
                    accumulated_damage_players[caster_uid] = dict(player)
                entity = monsters.get(target_uid)
                if entity and last_seen_ns is not None:
                    entity["last_seen_ns"] = max(
                        int(entity.get("last_seen_ns") or 0), last_seen_ns
                    )
            continue
        if kind == "update_exp":
            gain_exp = fields.get("gain_exp")
            if isinstance(gain_exp, (int, float)) and gain_exp > 0:
                last_exp_gain = (timestamp, int(gain_exp))
        elif kind == "drop_item_field":
            gained = sum(
                int(result.get("count") or 0)
                for result in data.get("results") or []
                if isinstance(result, dict)
                and result.get("item_index") == 900
                and isinstance(result.get("count"), (int, float))
                and result.get("count") > 0
            )
            if gained > 0:
                last_exp_gain = (timestamp, gained)
        elif kind in {"enemy_guild_list", "amity_guild_list"}:
            status = "enemy" if kind == "enemy_guild_list" else "ally"
            for guild in data.get("guilds") or []:
                guild_id = str(guild.get("guild_id") or "")
                if not guild_id:
                    continue
                guild_name = str(guild.get("guild_name") or "")
                guild_relations[guild_id] = (guild_name, status)
                for player in players.values():
                    if str(player.get("guild_id") or "") == guild_id:
                        player.update(guild_name=guild_name, pvp_status=status)
        elif kind == "appear_player_list":
            for unit in data.get("units") or []:
                uid = _integer(unit.get("uid"))
                if uid is None:
                    continue
                monsters.pop(uid, None)
                players[uid] = _entity("player", unit, timestamp)
                relation = guild_relations.get(str(unit.get("guild_id") or ""))
                if relation:
                    players[uid].update(
                        guild_name=relation[0], pvp_status=relation[1]
                    )
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
            known_monster = uid is not None and (
                uid in monsters or data.get("_known_entity_kind") == "monster"
            )
            if (
                known_monster
                and local_uid is not None
                and _integer(data.get("killer_uid")) == local_uid
            ):
                last_pve_activity = (timestamp, int(uid), "kill")
                last_pve_kill = last_pve_activity
            if uid is not None and local_uid is not None and uid == local_uid:
                local_death = (timestamp, uid, "death")
            if entity:
                entity["current_hp"] = 0
                entity["dead"] = True
                entity["last_seen_ns"] = timestamp
                _record_hp(hp_history, uid, timestamp, 0)
        elif kind in {"select_target_request", "use_skill_request"}:
            target_uid = _integer(data.get("target_uid"))
            if target_uid is not None:
                selected_target = (timestamp, target_uid)
                entity = players.get(target_uid) or monsters.get(target_uid)
                if entity:
                    entity["last_seen_ns"] = max(
                        int(entity.get("last_seen_ns") or 0), timestamp
                    )
            if kind == "use_skill_request":
                local_skill_requests.append((
                    timestamp,
                    _integer(data.get("skill_index")),
                    target_uid,
                    _integer(data.get("request_sequence_raw")),
                ))
                local_skill_requests = local_skill_requests[-64:]
        elif kind in {"use_skill_result", "use_normal_skill_result"}:
            if data.get("ret") not in (None, 0):
                continue
            caster = _integer(data.get("caster_uid"))
            response = _integer(data.get("response_number"))
            skill_index = _integer(data.get("skill_index"))
            main_target_uid = _integer(data.get("main_target_uid"))
            for request in reversed(local_skill_requests):
                requested_at, requested_skill, requested_target, sequence = request
                if timestamp - requested_at > LOCAL_SKILL_CORRELATION_SECONDS * 1_000_000_000:
                    break
                if requested_skill is not None and requested_skill != skill_index:
                    continue
                if requested_target is not None and requested_target != main_target_uid:
                    continue
                if sequence is not None and response is not None and sequence != response:
                    continue
                if caster is not None:
                    local_uid = caster
                break
            caster_entity = players.get(caster) or monsters.get(caster)
            if caster_entity and data.get("caster_final_hp") is not None:
                caster_entity["current_hp"] = int(data["caster_final_hp"])
                caster_entity["last_seen_ns"] = timestamp
                _record_hp(
                    hp_history, caster, timestamp, caster_entity.get("current_hp")
                )
            fallback_outgoing_target: int | None = None
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
                    by_caster.setdefault(caster, []).append((timestamp, hp_damage))
                if local_uid is None:
                    continue
                if caster == local_uid and target in monsters and hp_damage > 0:
                    final_hp = result.get("final_hp")
                    last_pve_activity = (
                        timestamp,
                        target,
                        "kill"
                        if isinstance(final_hp, (int, float)) and int(final_hp) == 0
                        else "damage",
                    )
                    if last_pve_activity[2] == "kill":
                        last_pve_kill = last_pve_activity
                if (
                    caster == local_uid
                    and fallback_outgoing_target is None
                    and (target in monsters or target in players)
                ):
                    fallback_outgoing_target = target
                if caster == local_uid and target in players:
                    damage.append(
                        {
                            "ts_ns": timestamp,
                            "target_uid": target,
                            "hp_damage": hp_damage,
                        }
                    )
                    if hp_damage > 0:
                        last_pvp_damage = (timestamp, target, "saída")
                elif target == local_uid and caster in players:
                    last_pvp = (timestamp, caster, "entrada")
                    if hp_damage > 0:
                        last_pvp_damage = (timestamp, caster, "entrada")
            if caster == local_uid:
                outgoing_target = (
                    main_target_uid
                    if main_target_uid in monsters or main_target_uid in players
                    else fallback_outgoing_target
                )
                if outgoing_target in monsters:
                    last_pve = (timestamp, outgoing_target)
                elif outgoing_target in players:
                    last_pvp = (timestamp, outgoing_target, "saída")

    reference_ns = int(now_ns if now_ns is not None else time.time_ns())
    for target_uid, by_caster in accumulated_target_damage.items():
        compact = target_damage.setdefault(target_uid, {})
        for caster_uid, (first_seen_ns, total) in by_caster.items():
            compact[caster_uid] = [(first_seen_ns, total)]
    damage_players = {**players, **accumulated_damage_players}
    for player in damage_players.values():
        relation = guild_relations.get(str(player.get("guild_id") or ""))
        if relation and not str(player.get("guild_name") or "").strip():
            player["guild_name"] = relation[0]

    bosses = []
    for entity in monsters.values() if "boss" in active_modes else ():
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
        if boss and not boss["stale"]:
            boss_damage = target_damage.get(int(entity["uid"]), {})
            _add_boss_rates(
                boss,
                hp_history.get(int(entity["uid"]), []),
                reference_ns,
                dps_window_seconds,
            )
            boss["top_damage_players"] = _top_damage_players(
                boss_damage,
                damage_players,
                reference_ns,
                dps_window_seconds,
            )
            boss["top_damage_guilds"] = _top_damage_groups(
                boss_damage,
                damage_players,
                "guild",
                reference_ns,
                dps_window_seconds,
            )
            boss["top_damage_groups"] = _top_damage_groups(
                boss_damage,
                damage_players,
                "group",
                reference_ns,
                dps_window_seconds,
            )
            boss.update(
                level=_integer(metadata.get("level")),
                npc_subtype=_integer(metadata.get("npc_subtype")),
                total_damage=sum(
                    _cumulative_damage_rate(events, reference_ns)[0]
                    for events in boss_damage.values()
                ),
            )
            bosses.append(boss)
    bosses.sort(key=lambda item: (-int(item.get("last_seen_ns") or 0), str(item.get("name") or "")))
    nearby_players_by_identity: dict[str, dict[str, Any]] = {}
    for uid, entity in players.items() if "pvp" in active_modes else ():
        character = str(entity.get("character_uid") or "").strip()
        name = str(entity.get("name") or "").strip()
        if uid == local_uid or not character or not name:
            continue
        target = _target_snapshot(
            {**entity, "last_seen_ns": entity["appeared_at_ns"]},
            reference_ns,
            nearby_stale_seconds,
        )
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
    for entity in monsters.values() if "pve" in active_modes else ():
        npc_index = _integer(entity.get("npc_index"))
        catalog_name = str(npc_names.get(npc_index) or "").strip()
        if npc_index is None or not catalog_name:
            continue
        target = _target_snapshot(
            entity,
            reference_ns,
            nearby_stale_seconds,
            fallback_name=catalog_name,
        )
        if (
            target
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
    if selected_target:
        selected_at, selected_uid = selected_target
        if selected_uid in monsters:
            last_pve = (selected_at, selected_uid)
            last_pvp = None
        elif selected_uid in players:
            last_pvp = (selected_at, selected_uid, "selecionado")
            last_pve = None
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
        "exp_gain": _recent_activity_snapshot(
            last_exp_gain,
            reference_ns,
            EXP_ACTIVITY_STALE_SECONDS,
            amount_index=1,
        ),
        "pve_activity": _combat_activity_snapshot(
            last_pve_activity,
            reference_ns,
            PVE_ACTIVITY_STALE_SECONDS,
        ) if "pve" in active_modes else None,
        "pve_kill": _combat_activity_snapshot(
            last_pve_kill,
            reference_ns,
            PVE_ACTIVITY_STALE_SECONDS,
        ) if "pve" in active_modes else None,
        "local_death": _combat_activity_snapshot(
            local_death,
            reference_ns,
            PVE_ACTIVITY_STALE_SECONDS,
        ),
        "pve": _named_pve_snapshot(
            monsters.get(last_pve[1]) if last_pve else None,
            npc_names,
            reference_ns,
            stale_seconds,
        ) if "pve" in active_modes else None,
        "pvp": _pvp_snapshot(
            players.get(last_pvp[1]) if last_pvp else None,
            last_pvp,
            damage,
            reference_ns,
            dps_window_seconds,
            pvp_stale_seconds,
        ) if "pvp" in active_modes else None,
        "pvp_activity": _pvp_snapshot(
            players.get(last_pvp_damage[1]) if last_pvp_damage else None,
            last_pvp_damage,
            damage,
            reference_ns,
            dps_window_seconds,
            pvp_stale_seconds,
        ) if "pvp" in active_modes else None,
    }


def _combat_activity_snapshot(
    activity: tuple[int, int, str] | None,
    now_ns: int,
    stale_seconds: int,
) -> dict[str, Any] | None:
    if not activity:
        return None
    observed_at_ns, target_uid, kind = activity
    age = max(0.0, (now_ns - observed_at_ns) / 1_000_000_000)
    return {
        "kind": kind,
        "target_uid": target_uid,
        "observed_at_ns": observed_at_ns,
        "age_seconds": round(age, 1),
        "stale": age > stale_seconds,
    }


def _recent_activity_snapshot(
    activity: tuple[int, ...] | None,
    now_ns: int,
    stale_seconds: int,
    *,
    amount_index: int,
) -> dict[str, Any] | None:
    if not activity:
        return None
    observed_at_ns = int(activity[0])
    age = max(0.0, (now_ns - observed_at_ns) / 1_000_000_000)
    return {
        "amount": int(activity[amount_index]),
        "observed_at_ns": observed_at_ns,
        "age_seconds": round(age, 1),
        "stale": age > stale_seconds,
    }


def _named_pve_snapshot(
    entity: dict[str, Any] | None,
    npc_names: dict[int, str],
    now_ns: int,
    stale_seconds: int,
) -> dict[str, Any] | None:
    if not entity:
        return None
    npc_index = _integer(entity.get("npc_index"))
    name = str(npc_names.get(npc_index) or "").strip()
    if not name:
        return None
    return _target_snapshot(
        entity,
        now_ns,
        stale_seconds,
        fallback_name=name,
    )


def _integer(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None


def _entity(kind: str, unit: dict[str, Any], timestamp: int) -> dict[str, Any]:
    position = None
    try:
        values = tuple(float(unit.get(f"position_{axis}")) for axis in ("x", "y", "z"))
    except (TypeError, ValueError):
        values = ()
    if len(values) == 3:
        position = dict(zip(("x", "y", "z"), values))
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
        "pvp_status": str(unit.get("pvp_status") or "neutral"),
        "group_id": unit.get("group_id") or unit.get("party_id"),
        "max_hp": _integer(unit.get("max_hp")),
        "current_hp": _integer(unit.get("current_hp")),
        "dead": False,
        "appeared_at_ns": timestamp,
        "last_seen_ns": timestamp,
        "position": position,
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
    damage: dict[int, list[tuple[int, int]]],
    players: dict[int, dict[str, Any]],
    now_ns: int,
    window_seconds: int,
) -> list[dict[str, Any]]:
    rows = []
    for uid, events in damage.items():
        total, average_dps, elapsed = _cumulative_damage_rate(events, now_ns)
        if not total:
            continue
        player = players.get(uid) or {}
        rows.append({
            "uid": uid,
            "character_uid": player.get("character_uid"),
            "name": str(player.get("name") or ""),
            "guild_id": player.get("guild_id"),
            "guild_name": str(player.get("guild_name") or ""),
            "damage": total,
            "dps_hp": average_dps,
            "elapsed_seconds": elapsed,
            "calculation": "encounter_total",
        })
    return sorted(
        rows,
        key=lambda row: (
            -int(row["damage"]), -float(row["dps_hp"]), row["name"]
        ),
    )[:10]


def _top_damage_groups(
    damage: dict[int, list[tuple[int, int]]],
    players: dict[int, dict[str, Any]],
    group_type: str,
    now_ns: int,
    window_seconds: int,
) -> list[dict[str, Any]]:
    grouped_events: dict[str, dict[str, Any]] = {}
    for uid, events in damage.items():
        player = players.get(uid) or {}
        if group_type == "guild":
            guild_id = str(player.get("guild_id") or "").strip()
            name = str(player.get("guild_name") or guild_id).strip()
            key = guild_id or name
        else:
            name = str(player.get("group_id") or "").strip()
            guild_id = ""
            key = name
        if name:
            group = grouped_events.setdefault(
                key, {"name": name, "guild_id": guild_id, "events": []}
            )
            if group["name"] == key and name != key:
                group["name"] = name
            group["events"].extend(events)
    rows = []
    for group in grouped_events.values():
        total, average_dps, elapsed = _cumulative_damage_rate(
            group["events"], now_ns
        )
        if total:
            row = {
                "name": group["name"],
                "damage": total,
                "dps_hp": average_dps,
                "elapsed_seconds": elapsed,
                "calculation": "encounter_total",
            }
            if group_type == "guild" and group["guild_id"]:
                row["guild_id"] = group["guild_id"]
            rows.append(row)
    return sorted(
        rows,
        key=lambda row: (
            -int(row["damage"]), -float(row["dps_hp"]), row["name"]
        ),
    )[:10]


def _cumulative_damage_rate(
    events: list[tuple[int, int]], now_ns: int
) -> tuple[int, float, float]:
    """Soma o encontro inteiro e calcula a média desde o primeiro golpe.

    A retenção dos eventos é limitada pelo stream/configuração de memória; esta
    função não cria histórico adicional e não volta a usar uma janela móvel.
    """
    valid = [
        (int(timestamp), max(0, int(amount)))
        for timestamp, amount in events
        if int(timestamp) >= 0 and int(amount) > 0
    ]
    if not valid:
        return 0, 0.0, 0.0
    total = sum(amount for _timestamp, amount in valid)
    first_at = min(timestamp for timestamp, _amount in valid)
    elapsed = max(1.0, (int(now_ns) - first_at) / 1_000_000_000)
    return total, round(total / elapsed, 1), round(elapsed, 1)


def _damage_rate(
    events: list[tuple[int, int]], now_ns: int, window_seconds: int
) -> tuple[int, float]:
    cutoff = now_ns - window_seconds * 1_000_000_000
    recent = [(timestamp, amount) for timestamp, amount in events if timestamp >= cutoff]
    if not recent:
        return 0, 0.0
    elapsed = max(1.0, min(float(window_seconds), (now_ns - recent[0][0]) / 1_000_000_000))
    total = sum(amount for _timestamp, amount in recent)
    return total, round(total / elapsed, 1)


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
    if not target or target["stale"] or not last_pvp:
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
