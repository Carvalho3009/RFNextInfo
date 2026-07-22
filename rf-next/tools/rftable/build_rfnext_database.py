#!/usr/bin/env python3
"""Monta um SQLite pesquisavel com os dados extraidos do RF ONLINE NEXT."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from rftable import RFTable, load


DEFAULT_ROOT = Path(r"K:\MCP\projects\rf-next\analysis\1.28.5\extracted-all")
DEFAULT_OUTPUT = Path(r"K:\MCP\projects\rf-next\analysis\1.28.5\rfnext-data.sqlite")
INTEGER_TYPES = set(range(0x03, 0x0D))
REAL_TYPES = {0x0D, 0x0E}


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def sqlite_type(type_code: int, is_array: bool) -> str:
    if is_array:
        return "TEXT"
    if type_code in INTEGER_TYPES:
        return "INTEGER"
    if type_code in REAL_TYPES:
        return "REAL"
    return "TEXT"


def value_for_sqlite(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def chunks(values: Iterable[Any], size: int = 5000) -> Iterable[list[Any]]:
    batch: list[Any] = []
    for value in values:
        batch.append(value)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def create_metadata(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE _meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE _files(
            relative_path TEXT PRIMARY KEY,
            extension TEXT NOT NULL,
            byte_size INTEGER NOT NULL,
            stem TEXT NOT NULL,
            family_path TEXT NOT NULL
        );
        CREATE TABLE _sources(
            table_name TEXT PRIMARY KEY,
            source_kind TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            internal_name TEXT,
            declared_rows INTEGER,
            imported_rows INTEGER,
            column_count INTEGER,
            byte_size INTEGER NOT NULL,
            status TEXT NOT NULL,
            error TEXT
        );
        CREATE TABLE _columns(
            table_name TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            column_name TEXT NOT NULL,
            type_code TEXT,
            sqlite_type TEXT NOT NULL,
            primary_key INTEGER NOT NULL DEFAULT 0,
            grouped INTEGER NOT NULL DEFAULT 0,
            is_array INTEGER NOT NULL DEFAULT 0,
            referenced_type TEXT,
            default_value TEXT,
            description TEXT,
            PRIMARY KEY(table_name, ordinal)
        );
        CREATE TABLE _quality_checks(
            table_name TEXT NOT NULL,
            check_name TEXT NOT NULL,
            status TEXT NOT NULL,
            metric_value REAL,
            details TEXT,
            PRIMARY KEY(table_name, check_name)
        );
        CREATE TABLE _relationships(
            child_table TEXT NOT NULL,
            child_column TEXT NOT NULL,
            parent_table TEXT NOT NULL,
            parent_column TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            confidence REAL NOT NULL,
            notes TEXT,
            PRIMARY KEY(child_table, child_column, parent_table, parent_column)
        );
        CREATE TABLE _string_references(
            source_table TEXT NOT NULL,
            source_column TEXT NOT NULL,
            source_key TEXT NOT NULL,
            string_id TEXT NOT NULL
        );
        CREATE TABLE _asset_references(
            source_table TEXT NOT NULL,
            source_column TEXT NOT NULL,
            source_key TEXT NOT NULL,
            object_path TEXT NOT NULL,
            expected_file TEXT,
            resolved_file TEXT,
            match_kind TEXT NOT NULL
        );
        """
    )


def catalog_files(connection: sqlite3.Connection, root: Path) -> tuple[set[str], dict[str, list[str]]]:
    relative_paths: set[str] = set()
    assets_by_stem: dict[str, list[str]] = {}
    rows = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        relative_paths.add(relative.casefold())
        if path.suffix.casefold() == ".uasset":
            assets_by_stem.setdefault(path.stem.casefold(), []).append(relative)
        rows.append(
            (
                relative,
                path.suffix.lower(),
                path.stat().st_size,
                path.stem,
                Path(relative).with_suffix("").as_posix(),
            )
        )
        if len(rows) == 10000:
            connection.executemany("INSERT INTO _files VALUES(?,?,?,?,?)", rows)
            rows.clear()
    if rows:
        connection.executemany("INSERT INTO _files VALUES(?,?,?,?,?)", rows)
    connection.execute("CREATE INDEX ix_files_extension ON _files(extension)")
    connection.execute("CREATE INDEX ix_files_family ON _files(family_path)")
    return relative_paths, assets_by_stem


def ptbr_strings(root: Path) -> dict[str, str]:
    path = next(root.rglob("RF_StringTable_PT_BR.RFTable"))
    return {str(row["StringID"]): str(row["KO_KR"]) for row in load(path).rows()}


def source_key(table: RFTable, row: dict[str, Any], row_number: int) -> str:
    keys = {column.name: row[column.name] for column in table.columns if column.primary_key}
    if not keys:
        keys = {"row": row_number}
    return json.dumps(keys, ensure_ascii=False, separators=(",", ":"), default=str)


def expected_asset_path(object_path: str) -> str | None:
    package = object_path.split(".", 1)[0]
    if package.startswith("/Game/"):
        return "ProjectRF/Content/" + package.removeprefix("/Game/") + ".uasset"
    if package.startswith("/Engine/"):
        return "Engine/Content/" + package.removeprefix("/Engine/") + ".uasset"
    return None


def resolve_asset(
    object_path: str,
    referenced_type: str,
    file_paths: set[str],
    assets_by_stem: dict[str, list[str]],
) -> tuple[str | None, str | None, str]:
    expected = expected_asset_path(object_path)
    if expected and expected.casefold() in file_paths:
        return expected, expected, "exact"
    package = object_path.split(".", 1)[0]
    stem = package.rsplit("/", 1)[-1].casefold()
    candidates = list(assets_by_stem.get(stem, []))
    if "UPaperSprite" in referenced_type:
        candidates.extend(assets_by_stem.get(stem + "_sprite", []))
    candidates = sorted(set(candidates))
    if len(candidates) == 1:
        return expected, candidates[0], "unique_basename"
    return expected, None, "ambiguous" if candidates else "missing"


def import_rftable(
    connection: sqlite3.Connection,
    root: Path,
    path: Path,
    strings: dict[str, str],
    file_paths: set[str],
    assets_by_stem: dict[str, list[str]],
    index_number: int,
) -> bool:
    table_name = path.stem
    relative = path.relative_to(root).as_posix()
    try:
        table = load(path)
    except Exception as error:
        connection.execute(
            "INSERT INTO _sources VALUES(?,?,?,?,?,?,?,?,?,?)",
            (table_name, "rftable", relative, None, None, None, None, path.stat().st_size, "marker", str(error)),
        )
        return False

    column_sql = ",".join(
        f"{quote(column.name)} {sqlite_type(column.type_code, column.is_array)}"
        for column in table.columns
    )
    connection.execute(f"CREATE TABLE {quote(table_name)}({column_sql})")
    connection.execute(
        "INSERT INTO _sources VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            table_name,
            "rftable",
            relative,
            table.name,
            table.row_count,
            0,
            len(table.columns),
            path.stat().st_size,
            "importing",
            None,
        ),
    )
    connection.executemany(
        "INSERT INTO _columns VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                table_name,
                ordinal,
                column.name,
                f"0x{column.type_code:02X}",
                sqlite_type(column.type_code, column.is_array),
                int(column.primary_key),
                int(column.grouped),
                int(column.is_array),
                column.referenced_type,
                column.default_value,
                column.description,
            )
            for ordinal, column in enumerate(table.columns)
        ],
    )

    placeholders = ",".join("?" for _ in table.columns)
    insert_sql = f"INSERT INTO {quote(table_name)} VALUES({placeholders})"
    string_columns = [column for column in table.columns if sqlite_type(column.type_code, column.is_array) == "TEXT"]
    asset_columns = [
        column for column in table.columns
        if column.referenced_type.startswith("TSoftObjectPtr")
    ]
    row_batch = []
    string_batch = []
    asset_batch = []
    imported = 0
    try:
        for row_number, row in enumerate(table.rows(), start=1):
            key = source_key(table, row, row_number)
            row_batch.append(tuple(value_for_sqlite(row[column.name]) for column in table.columns))
            if not table_name.startswith("RF_StringTable"):
                for column in string_columns:
                    value = row[column.name]
                    if isinstance(value, str) and value in strings:
                        string_batch.append((table_name, column.name, key, value))
            for column in asset_columns:
                value = row[column.name]
                values = value if isinstance(value, list) else [value]
                for object_path in values:
                    if not isinstance(object_path, str) or not object_path:
                        continue
                    expected, resolved, match_kind = resolve_asset(
                        object_path, column.referenced_type, file_paths, assets_by_stem
                    )
                    asset_batch.append(
                        (table_name, column.name, key, object_path, expected, resolved, match_kind)
                    )
            if len(row_batch) >= 2000:
                connection.executemany(insert_sql, row_batch)
                connection.executemany("INSERT INTO _string_references VALUES(?,?,?,?)", string_batch)
                connection.executemany("INSERT INTO _asset_references VALUES(?,?,?,?,?,?,?)", asset_batch)
                imported += len(row_batch)
                row_batch.clear()
                string_batch.clear()
                asset_batch.clear()
        if row_batch:
            connection.executemany(insert_sql, row_batch)
            connection.executemany("INSERT INTO _string_references VALUES(?,?,?,?)", string_batch)
            connection.executemany("INSERT INTO _asset_references VALUES(?,?,?,?,?,?,?)", asset_batch)
            imported += len(row_batch)
    except Exception as error:
        connection.execute(f"DROP TABLE {quote(table_name)}")
        connection.execute("DELETE FROM _columns WHERE table_name=?", (table_name,))
        connection.execute("DELETE FROM _string_references WHERE source_table=?", (table_name,))
        connection.execute("DELETE FROM _asset_references WHERE source_table=?", (table_name,))
        connection.execute(
            "UPDATE _sources SET imported_rows=?, status='failed', error=? WHERE table_name=?",
            (imported, str(error), table_name),
        )
        return False

    status = "passed" if imported == table.row_count else "failed"
    connection.execute(
        "UPDATE _sources SET imported_rows=?, status=? WHERE table_name=?",
        (imported, "parsed" if status == "passed" else "failed", table_name),
    )
    connection.execute(
        "INSERT INTO _quality_checks VALUES(?,?,?,?,?)",
        (table_name, "row_count", status, imported, f"declared={table.row_count}"),
    )

    primary_columns = [column.name for column in table.columns if column.primary_key]
    if primary_columns:
        columns = ",".join(quote(name) for name in primary_columns)
        try:
            connection.execute(
                f"CREATE UNIQUE INDEX {quote(f'ux_rf_{index_number:04d}')} "
                f"ON {quote(table_name)}({columns})"
            )
            pk_status = "passed"
        except sqlite3.IntegrityError:
            connection.execute(
                f"CREATE INDEX {quote(f'ix_rf_{index_number:04d}')} "
                f"ON {quote(table_name)}({columns})"
            )
            pk_status = "failed"
        connection.execute(
            "INSERT INTO _quality_checks VALUES(?,?,?,?,?)",
            (table_name, "primary_key_unique", pk_status, None, ",".join(primary_columns)),
        )
    return True


def import_embedded_sqlite(connection: sqlite3.Connection, root: Path, path: Path) -> None:
    relative = path.relative_to(root).as_posix()
    with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as source:
        source.row_factory = sqlite3.Row
        names = [
            row[0] for row in source.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for name in names:
            columns = list(source.execute(f"PRAGMA table_info({quote(name)})"))
            definition = ",".join(f"{quote(row['name'])} {row['type'] or 'TEXT'}" for row in columns)
            connection.execute(f"CREATE TABLE {quote(name)}({definition})")
            connection.executemany(
                "INSERT INTO _columns VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (name, ordinal, row["name"], None, row["type"] or "TEXT", int(row["pk"]), 0, 0, None, None, None)
                    for ordinal, row in enumerate(columns)
                ],
            )
            rows = source.execute(f"SELECT * FROM {quote(name)}")
            insert_sql = f"INSERT INTO {quote(name)} VALUES({','.join('?' for _ in columns)})"
            count = 0
            while batch := rows.fetchmany(5000):
                connection.executemany(insert_sql, (tuple(row) for row in batch))
                count += len(batch)
            connection.execute(
                "INSERT INTO _sources VALUES(?,?,?,?,?,?,?,?,?,?)",
                (name, "sqlite", relative, name, count, count, len(columns), path.stat().st_size, "parsed", None),
            )
            connection.execute(
                "INSERT INTO _quality_checks VALUES(?,?,?,?,?)",
                (name, "row_count", "passed", count, "embedded sqlite"),
            )


def add_indexes_and_relationships(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE INDEX ix_string_refs_id ON _string_references(string_id);
        CREATE INDEX ix_string_refs_source ON _string_references(source_table, source_column);
        CREATE INDEX ix_asset_refs_path ON _asset_references(resolved_file);
        CREATE INDEX ix_asset_refs_source ON _asset_references(source_table, source_column);
        CREATE INDEX ix_reward_index ON RF_RewardTableRow(RewardIndex);
        CREATE INDEX ix_reward_subgroup ON RF_RewardTableRow(SubGroupIndex);
        CREATE INDEX ix_subgroup_index ON RF_SubGroupInfoRow(SubGroupIndex);
        CREATE INDEX ix_subgroup_item ON RF_SubGroupInfoRow(RewardItemIndex);
        CREATE INDEX ix_item_group ON RF_ItemTable(ItemGroup);
        CREATE INDEX ix_npc_reward ON RF_NPCTable(RewardIndex);
        CREATE INDEX ix_spawn_npc ON RF_MapInfoTable_Spawn(NPCIndex);
        CREATE INDEX ix_spawn_map_region ON RF_MapInfoTable_Spawn(MapIndex, RegionIndex);
        """
    )
    relationships = [
        ("RF_ItemTable", "NameStringIndex", "RF_StringTable_PT_BR", "StringID", "localization", 1.0, "Exact string key"),
        ("RF_ItemTable", "DescStringIndex", "RF_StringTable_PT_BR", "StringID", "localization", 1.0, "Exact string key"),
        ("RF_NPCTable", "NameStringIndex", "RF_StringTable_PT_BR", "StringID", "localization", 1.0, "Exact string key"),
        ("RF_NPCTable", "TitleStringIndex", "RF_StringTable_PT_BR", "StringID", "localization", 1.0, "Exact string key"),
        ("RF_SkillTable", "NameStringIndex", "RF_StringTable_PT_BR", "StringID", "localization", 1.0, "Exact string key"),
        ("RF_SkillTable", "DescStringIndex", "RF_StringTable_PT_BR", "StringID", "localization", 1.0, "Exact string key"),
        ("RF_ItemCollection", "NameStringIndex", "RF_StringTable_PT_BR", "StringID", "localization", 1.0, "Exact string key"),
        ("RF_NPCTable", "RewardIndex", "RF_RewardTableRow", "RewardIndex", "reward", 1.0, "Static reward mapping; not a confirmed probability"),
        ("RF_RewardTableRow", "SubGroupIndex", "RF_SubGroupInfoRow", "SubGroupIndex", "reward", 1.0, "Static subgroup mapping"),
        ("RF_SubGroupInfoRow", "RewardItemIndex", "RF_ItemTable", "ItemIndex", "item", 0.95, "Internal item 900 represents EXP and is not a normal item row"),
        ("RF_SubGroupInfoRow", "RewardItemIndex", "RF_WeaponCostumeTable", "ItemIndex", "polymorphic_item", 1.0, "Weapon costume reward entity"),
        ("RF_SubGroupInfoRow", "RewardItemIndex", "RF_TitleTable", "ItemIndex", "polymorphic_item", 1.0, "Title reward entity"),
        ("RF_SubGroupInfoRow", "RewardItemIndex", "RF_Costume", "ItemIndex", "polymorphic_item", 1.0, "Costume reward entity"),
        ("RF_SubGroupInfoRow", "RewardItemIndex", "RF_BiosuitTable", "ItemIndex", "polymorphic_item", 1.0, "Biosuit reward entity"),
        ("RF_MapInfoTable_Spawn", "NPCIndex", "RF_NPCTable", "NPCIndex", "spawn", 1.0, "Exact NPC identifier"),
        ("RF_ItemCollection", "CollectionN_ItemGroup", "RF_ItemTable", "ItemGroup", "collection", 1.0, "N expands from 1 through 10"),
    ]
    connection.executemany("INSERT INTO _relationships VALUES(?,?,?,?,?,?,?)", relationships)


def create_views(connection: sqlite3.Connection) -> None:
    collection_slots = " UNION ALL ".join(
        f"SELECT CollectionIndex,{slot} AS Slot,Collection{slot}_ItemGroup AS ItemGroup,"
        f"Collection{slot}_Value AS RequiredQuantity,Collection{slot}_EnchantLevel AS RequiredEnchantLevel "
        f"FROM RF_ItemCollection WHERE Collection{slot}_ItemGroup<>0 AND Collection{slot}_Value<>0"
        for slot in range(1, 11)
    )
    connection.executescript(
        f"""
        CREATE VIEW v_strings_ptbr AS
        SELECT StringID, KO_KR AS TextPTBR FROM RF_StringTable_PT_BR;

        CREATE VIEW v_items_ptbr AS
        SELECT i.*, n.TextPTBR AS NamePTBR, d.TextPTBR AS DescriptionPTBR
        FROM RF_ItemTable i
        LEFT JOIN v_strings_ptbr n ON n.StringID=i.NameStringIndex
        LEFT JOIN v_strings_ptbr d ON d.StringID=i.DescStringIndex;

        CREATE VIEW v_npcs_ptbr AS
        SELECT n.*, s.TextPTBR AS NamePTBR, t.TextPTBR AS TitlePTBR
        FROM RF_NPCTable n
        LEFT JOIN v_strings_ptbr s ON s.StringID=n.NameStringIndex
        LEFT JOIN v_strings_ptbr t ON t.StringID=n.TitleStringIndex;

        CREATE VIEW v_skills_ptbr AS
        SELECT s.*, n.TextPTBR AS NamePTBR, d.TextPTBR AS DescriptionPTBR
        FROM RF_SkillTable s
        LEFT JOIN v_strings_ptbr n ON n.StringID=s.NameStringIndex
        LEFT JOIN v_strings_ptbr d ON d.StringID=s.DescStringIndex;

        CREATE VIEW v_maps_ptbr AS
        SELECT m.*, s.TextPTBR AS NamePTBR
        FROM RF_MapInfoTable m
        LEFT JOIN v_strings_ptbr s ON s.StringID=m.MapInfoNameString;

        CREATE VIEW v_missions_ptbr AS
        SELECT m.*, t.TextPTBR AS MissionTitlePTBR,
               g.TextPTBR AS MissionGoalPTBR, g2.TextPTBR AS MissionGoal2PTBR
        FROM RF_MissionTable m
        LEFT JOIN v_strings_ptbr t ON t.StringID=m.MissionTitle
        LEFT JOIN v_strings_ptbr g ON g.StringID=m.MissionGoal
        LEFT JOIN v_strings_ptbr g2 ON g2.StringID=m.MissionGoal2;

        CREATE VIEW v_map_spawns AS
        SELECT s.*, n.Level AS NPCLevel, n.Grade AS NPCGrade,
               n.NameStringIndex, n.NamePTBR, n.RewardIndex
        FROM RF_MapInfoTable_Spawn s
        LEFT JOIN v_npcs_ptbr n ON n.NPCIndex=s.NPCIndex;

        CREATE VIEW v_reward_entities_ptbr AS
        SELECT ItemIndex AS EntityIndex, 'item' AS EntityType,
               NamePTBR, DescriptionPTBR, 'RF_ItemTable' AS SourceTable
        FROM v_items_ptbr
        UNION ALL
        SELECT w.ItemIndex, 'weapon_costume', n.TextPTBR, '', 'RF_WeaponCostumeTable'
        FROM RF_WeaponCostumeTable w
        LEFT JOIN v_strings_ptbr n ON n.StringID=w.NameString
        UNION ALL
        SELECT t.ItemIndex, 'title', n.TextPTBR, d.TextPTBR, 'RF_TitleTable'
        FROM RF_TitleTable t
        LEFT JOIN v_strings_ptbr n ON n.StringID=t.TitleStringIndex
        LEFT JOIN v_strings_ptbr d ON d.StringID=t.GainDescStringIndex
        UNION ALL
        SELECT c.ItemIndex, 'costume', n.TextPTBR, d.TextPTBR, 'RF_Costume'
        FROM RF_Costume c
        LEFT JOIN v_strings_ptbr n ON n.StringID=c.NameStringMale
        LEFT JOIN v_strings_ptbr d ON d.StringID=c.NameStringDescription
        UNION ALL
        SELECT b.ItemIndex, 'biosuit', n.TextPTBR, d.TextPTBR, 'RF_BiosuitTable'
        FROM RF_BiosuitTable b
        LEFT JOIN v_strings_ptbr n ON n.StringID=b.NameStringIndex
        LEFT JOIN v_strings_ptbr d ON d.StringID=b.DescStringIndex;

        CREATE VIEW v_loot_candidates AS
        SELECT n.NPCIndex, n.NamePTBR AS NPCNamePTBR, n.Level AS NPCLevel,
               n.RewardIndex, r.BoxType, r.SubGroupIndex,
               g.RewardItemIndex,
               CASE WHEN g.RewardItemIndex=900 THEN 'exp' ELSE e.EntityType END AS RewardEntityType,
               CASE WHEN g.RewardItemIndex=900 THEN 'EXP' ELSE e.NamePTBR END AS RewardItemNamePTBR,
               e.SourceTable AS RewardEntitySource,
               g.MinValue, g.EnchantLevel, g.BiosuitType,
               0 AS ChanceConfirmed
        FROM v_npcs_ptbr n
        JOIN RF_RewardTableRow r ON r.RewardIndex=n.RewardIndex
        JOIN RF_SubGroupInfoRow g ON g.SubGroupIndex=r.SubGroupIndex
        LEFT JOIN v_reward_entities_ptbr e ON e.EntityIndex=g.RewardItemIndex;

        CREATE VIEW v_collections_ptbr AS
        SELECT c.*, s.TextPTBR AS NamePTBR
        FROM RF_ItemCollection c
        LEFT JOIN v_strings_ptbr s ON s.StringID=c.NameStringIndex;

        CREATE VIEW v_collection_requirements AS
        WITH requirements AS ({collection_slots})
        SELECT r.*, c.NamePTBR AS CollectionNamePTBR,
               i.ItemIndex AS AcceptedItemIndex, i.NamePTBR AS AcceptedItemNamePTBR,
               i.Grade AS AcceptedItemGrade, i.Tier AS AcceptedItemTier
        FROM requirements r
        JOIN v_collections_ptbr c ON c.CollectionIndex=r.CollectionIndex
        LEFT JOIN v_items_ptbr i ON i.ItemGroup=r.ItemGroup;

        CREATE VIEW v_database_summary AS
        SELECT 'files' AS metric, COUNT(*) AS value FROM _files
        UNION ALL SELECT 'rftables_parsed', COUNT(*) FROM _sources WHERE source_kind='rftable' AND status='parsed'
        UNION ALL SELECT 'rftables_markers', COUNT(*) FROM _sources WHERE source_kind='rftable' AND status='marker'
        UNION ALL SELECT 'raw_rows', COALESCE(SUM(imported_rows),0) FROM _sources WHERE source_kind='rftable'
        UNION ALL SELECT 'string_references', COUNT(*) FROM _string_references
        UNION ALL SELECT 'asset_references', COUNT(*) FROM _asset_references
        UNION ALL SELECT 'asset_references_resolved', COUNT(*) FROM _asset_references WHERE resolved_file IS NOT NULL;
        """
    )


def build_search(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE VIRTUAL TABLE search_ptbr USING fts5("
        "entity_type, entity_id UNINDEXED, name, description, source_table UNINDEXED, "
        "tokenize='unicode61 remove_diacritics 2')"
    )
    statements = [
        "INSERT INTO search_ptbr SELECT 'item',ItemIndex,NamePTBR,DescriptionPTBR,'RF_ItemTable' FROM v_items_ptbr WHERE NamePTBR<>''",
        "INSERT INTO search_ptbr SELECT 'npc',NPCIndex,NamePTBR,TitlePTBR,'RF_NPCTable' FROM v_npcs_ptbr WHERE NamePTBR<>''",
        "INSERT INTO search_ptbr SELECT 'skill',SkillIndex,NamePTBR,DescriptionPTBR,'RF_SkillTable' FROM v_skills_ptbr WHERE NamePTBR<>''",
        "INSERT INTO search_ptbr SELECT 'map',MapInfoIndex,NamePTBR,'','RF_MapInfoTable' FROM v_maps_ptbr WHERE NamePTBR<>''",
        "INSERT INTO search_ptbr SELECT 'mission',MissionIndex,MissionTitlePTBR,MissionGoalPTBR,'RF_MissionTable' FROM v_missions_ptbr WHERE MissionTitlePTBR<>''",
        "INSERT INTO search_ptbr SELECT 'collection',CollectionIndex,NamePTBR,'','RF_ItemCollection' FROM v_collections_ptbr WHERE NamePTBR<>''",
        "INSERT INTO search_ptbr SELECT EntityType,EntityIndex,NamePTBR,DescriptionPTBR,SourceTable FROM v_reward_entities_ptbr WHERE EntityType<>'item' AND NamePTBR<>''",
    ]
    for statement in statements:
        connection.execute(statement)


def add_quality_checks(connection: sqlite3.Connection) -> None:
    connection.execute(
        "DELETE FROM _quality_checks WHERE check_name IN "
        "('name_ptbr_coverage_when_key_present','name_key_resolves_ptbr',"
        "'name_text_nonempty_ptbr','file_coverage','reward_orphans',"
        "'subgroup_orphans','reward_entity_orphans_excluding_exp_900')"
    )
    checks = [
        ("RF_ItemTable", "name_key_resolves_ptbr", "SELECT AVG(EXISTS(SELECT 1 FROM RF_StringTable_PT_BR s WHERE s.StringID=i.NameStringIndex)) FROM RF_ItemTable i WHERE NameStringIndex<>''", 0.95),
        ("RF_NPCTable", "name_key_resolves_ptbr", "SELECT AVG(EXISTS(SELECT 1 FROM RF_StringTable_PT_BR s WHERE s.StringID=n.NameStringIndex)) FROM RF_NPCTable n WHERE NameStringIndex<>''", 0.95),
        ("RF_SkillTable", "name_key_resolves_ptbr", "SELECT AVG(EXISTS(SELECT 1 FROM RF_StringTable_PT_BR s WHERE s.StringID=k.NameStringIndex)) FROM RF_SkillTable k WHERE NameStringIndex<>''", 0.95),
        ("RF_ItemTable", "name_text_nonempty_ptbr", "SELECT AVG(NamePTBR IS NOT NULL AND NamePTBR<>'') FROM v_items_ptbr WHERE NameStringIndex<>''", 0.95),
        ("RF_NPCTable", "name_text_nonempty_ptbr", "SELECT AVG(NamePTBR IS NOT NULL AND NamePTBR<>'') FROM v_npcs_ptbr WHERE NameStringIndex<>''", 0.95),
        ("RF_SkillTable", "name_text_nonempty_ptbr", "SELECT AVG(NamePTBR IS NOT NULL AND NamePTBR<>'') FROM v_skills_ptbr WHERE NameStringIndex<>''", 0.95),
        ("_asset_references", "file_coverage", "SELECT AVG(resolved_file IS NOT NULL) FROM _asset_references", 0.90),
    ]
    for table_name, check_name, sql, threshold in checks:
        value = connection.execute(sql).fetchone()[0]
        connection.execute(
            "INSERT OR REPLACE INTO _quality_checks VALUES(?,?,?,?,?)",
            (
                table_name,
                check_name,
                "passed" if value is not None and value >= threshold else "warning",
                value,
                f"threshold={threshold}",
            ),
        )

    orphan_checks = [
        (
            "RF_NPCTable", "reward_orphans",
            "SELECT COUNT(*) FROM RF_NPCTable n WHERE n.RewardIndex<>0 AND NOT EXISTS "
            "(SELECT 1 FROM RF_RewardTableRow r WHERE r.RewardIndex=n.RewardIndex)",
        ),
        (
            "RF_RewardTableRow", "subgroup_orphans",
            "SELECT COUNT(*) FROM RF_RewardTableRow r WHERE NOT EXISTS "
            "(SELECT 1 FROM RF_SubGroupInfoRow s WHERE s.SubGroupIndex=r.SubGroupIndex)",
        ),
        (
            "RF_SubGroupInfoRow", "reward_entity_orphans_excluding_exp_900",
            "SELECT COUNT(*) FROM RF_SubGroupInfoRow s WHERE s.RewardItemIndex<>900 AND NOT EXISTS "
            "(SELECT 1 FROM v_reward_entities_ptbr e WHERE e.EntityIndex=s.RewardItemIndex)",
        ),
    ]
    for table_name, check_name, sql in orphan_checks:
        value = connection.execute(sql).fetchone()[0]
        connection.execute(
            "INSERT OR REPLACE INTO _quality_checks VALUES(?,?,?,?,?)",
            (table_name, check_name, "passed" if value == 0 else "warning", value, "Non-zero values need domain review"),
        )


def validate(connection: sqlite3.Connection) -> None:
    assert connection.execute("SELECT COUNT(*) FROM _sources WHERE source_kind='rftable' AND status='parsed'").fetchone()[0] == 509
    assert connection.execute("SELECT COUNT(*) FROM RF_ItemTable").fetchone()[0] == 8231
    assert connection.execute("SELECT COUNT(*) FROM RF_StringTable_PT_BR").fetchone()[0] == 79044
    assert connection.execute("SELECT COUNT(*) FROM RF_RewardTableRow").fetchone()[0] > 0
    assert connection.execute("SELECT COUNT(*) FROM v_loot_candidates").fetchone()[0] > 0
    assert connection.execute("SELECT COUNT(*) FROM search_ptbr").fetchone()[0] > 0


def build(root: Path, output: Path) -> None:
    if not root.is_dir():
        raise FileNotFoundError(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.unlink(missing_ok=True)

    connection = sqlite3.connect(temporary)
    try:
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute("PRAGMA temp_store=MEMORY")
        create_metadata(connection)
        connection.executemany(
            "INSERT INTO _meta VALUES(?,?)",
            [
                ("game", "RF ONLINE NEXT"),
                ("version", "1.28.5"),
                ("locale", "pt-BR"),
                ("source_root", str(root)),
                ("loot_probability_confirmed", "false"),
                ("notes", "Merged client data: base, patch0, then patch1. Static reward links are not drop probabilities."),
            ],
        )
        file_paths, assets_by_stem = catalog_files(connection, root)
        strings = ptbr_strings(root)
        parsed = 0
        for index_number, path in enumerate(sorted(root.rglob("*.RFTable")), start=1):
            parsed += int(
                import_rftable(
                    connection, root, path, strings, file_paths, assets_by_stem, index_number
                )
            )
            if index_number % 25 == 0:
                print(f"RFTable {index_number}/511")
        for path in sorted(root.rglob("*.sqlite")):
            import_embedded_sqlite(connection, root, path)
        add_indexes_and_relationships(connection)
        create_views(connection)
        build_search(connection)
        add_quality_checks(connection)
        connection.execute("INSERT INTO _meta VALUES('rftables_parsed',?)", (str(parsed),))
        validate(connection)
        connection.execute("PRAGMA optimize")
        connection.commit()
    finally:
        connection.close()
    os.replace(temporary, output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    build(args.root, args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
