from __future__ import annotations

import ast
import json
import re
import shutil
import sqlite3
import struct
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path(r"K:\MCP\Karvalho\rf-next")
SOURCE_DB = (
    SOURCE_ROOT
    / "analysis"
    / "1.29.7"
    / "db-staging-2026-08-05"
    / "rfnext-data.sqlite"
)
SOURCE_MAPS = SOURCE_ROOT / "map-interativo" / "public" / "map"
SOURCE_TILES = Path(
    r"E:\Assets\Imagens_PNG\ProjectRF\Content\Streaming\Maps"
    r"\WorldMapTexture\WorldMapTileTex"
)
SOURCE_TILE_INFO = Path(
    r"E:\Assets\Extraidos\ProjectRF\Content\Streaming\Maps"
    r"\WorldMapTexture\WorldMapTileTex"
)
TARGET_MAPS = ROOT / "assets" / "maps"
TARGET_CATALOG = ROOT / "core" / "map_previews.json"
TILE_RE = re.compile(r"_(?P<map>\d+)_(-?\d+)_(-?\d+)\.png$", re.I)
WORLD_PER_TILE_CANDIDATES = (3_200, 6_400, 12_800, 25_600, 51_200, 102_400)

TARGET_GROUPS = {
    "novus": (101, 103),
    "albern_crater": (751, 752, 754, 755),
    "android_junkyard": (635, 636, 637, 638, 639, 640, 4211, 4212, 4213, 4214),
    "secret_nemesis_base": (601, 602, 605, 606, 607),
    "public_mining_field": (
        611, 612, 613, 614, 615, 616, 617, 618, 619,
        620, 621, 622, 623, 624, 625, 626,
        4625, 4645, 4665, 4685,
    ),
    "exclusive_mining_field": (610, 630, 4603),
    "orbital": (642, 643, 644, 4504, 4554),
}

# O MapIndex continua identificando a planta/andar internamente. Na interface,
# mapas segmentados por andar mantêm um único nome de mapa e expõem o andar
# como região fixa.
DISPLAY_MAP_NAMES = {
    "novus": {"pt": "Mundo Novus", "en": "Novus World"},
    "android_junkyard": {
        "pt": "Ferro-Velho de Androides",
        "en": "Android Junkyard",
    },
    "secret_nemesis_base": {
        "pt": "Base Secreta Nemesis",
        "en": "Secret Nemesis Base",
    },
    "public_mining_field": {
        "pt": "Campo de Mineração Público",
        "en": "Public Mining Field",
    },
    "exclusive_mining_field": {
        "pt": "Campo de Mineração Exclusivo",
        "en": "Exclusive Mining Field",
    },
}

FLOOR_BY_MAP_INDEX = {
    601: "1F", 602: "2F", 605: "3F", 606: "4F", 607: "5F",
    610: "1F", 630: "2F", 4603: "3F",
    611: "1F", 612: "2F", 613: "3F", 614: "1F", 615: "2F",
    616: "3F", 617: "1F", 618: "2F", 619: "3F", 620: "4F",
    621: "4F", 622: "4F", 623: "1F", 624: "2F", 625: "3F",
    626: "4F", 4625: "5F", 4645: "5F", 4665: "5F", 4685: "5F",
    635: "5F", 636: "6F", 637: "7F", 638: "8F", 639: "9F",
    640: "10F", 4211: "11F", 4212: "12F", 4213: "13F",
    4214: "14F",
}

# Esses índices não possuem textura própria no extrato, mas compartilham o
# mesmo LevelPath e a mesma topologia de coordenadas da planta indicada.
ASSET_ALIASES = {
    **{map_index: 631 for map_index in TARGET_GROUPS["android_junkyard"]},
    4645: 4625,
    4665: 4625,
    4685: 4625,
}

# A posição transmitida pelo servidor usa a unidade espacial própria do mapa,
# enquanto a planta extraída usa coordenadas de mundo. A origem abaixo foi
# calibrada comparando 52 aparições vivas dos NPCs 359101/2/3/190 com os
# respectivos spawns estáticos do MapIndex 643. O 644 compartilha o LevelPath.
LIVE_POSITION_TRANSFORMS = {
    643: {
        "scale_x": 25.0,
        "scale_y": 25.0,
        "offset_x": 11397.281,
        "offset_y": -21539.558,
        "evidence": "live-npc-to-static-spawn-2026-08-18-52-samples",
    },
    644: {
        "scale_x": 25.0,
        "scale_y": 25.0,
        "offset_x": 11397.281,
        "offset_y": -21539.558,
        "evidence": "shared-level-layout-map-643-live-calibration",
    },
}


def _position(value: object) -> tuple[float, float, float] | None:
    try:
        parsed = ast.literal_eval(str(value))
        if not isinstance(parsed, (list, tuple)) or len(parsed) != 3:
            return None
        return tuple(float(item) for item in parsed)
    except (SyntaxError, TypeError, ValueError):
        return None


def _tile_set(map_index: int, group_index: int) -> list[tuple[int, int, Path]]:
    folder = SOURCE_TILES / str(group_index)
    candidates: dict[int, list[tuple[int, int, Path]]] = defaultdict(list)
    if not folder.is_dir():
        return []
    for path in folder.rglob("*.png"):
        match = TILE_RE.search(path.name)
        if match:
            candidates[int(match.group("map"))].append(
                (int(match.group(2)), int(match.group(3)), path)
            )
    for key in (map_index, group_index, group_index // 10):
        if key in candidates:
            return candidates[key]
    return max(candidates.values(), key=len, default=[])


def _world_per_tile(
    positions: list[tuple[float, float, float]],
    tile_bounds: tuple[int, int, int, int],
) -> int:
    min_tx, max_tx, min_ty, max_ty = tile_bounds

    def coverage(size: int) -> int:
        return sum(
            min_tx * size <= x <= (max_tx + 1) * size
            and min_ty * size <= y <= (max_ty + 1) * size
            for x, y, _z in positions
        )

    return max(WORLD_PER_TILE_CANDIDATES, key=lambda size: (coverage(size), -size))


def _map_row(db: sqlite3.Connection, map_index: int) -> sqlite3.Row:
    row = db.execute(
        """
        SELECT m.MapIndex,m.RegionGroupIndex,m.LevelPath,
               COALESCE(NULLIF(pt.KO_KR,''),m.MapNameString) name_pt,
               COALESCE(NULLIF(en.KO_KR,''),NULLIF(pt.KO_KR,''),m.MapNameString) name_en
          FROM RF_MapTable m
          LEFT JOIN RF_StringTable_PT_BR pt ON pt.StringID=m.MapNameString
          LEFT JOIN RF_StringTable_EN_US en ON en.StringID=m.MapNameString
         WHERE m.MapIndex=?
        """,
        (map_index,),
    ).fetchone()
    if row is None:
        raise ValueError(f"MapIndex ausente: {map_index}")
    return row


def _spawn_positions(
    db: sqlite3.Connection, map_index: int
) -> list[tuple[float, float, float]]:
    return [
        parsed
        for row in db.execute(
            """SELECT TargetPosition1 FROM RF_MapInfoTable_Spawn
                 WHERE MapIndex=? AND NPCType=2""",
            (map_index,),
        )
        if (parsed := _position(row[0])) is not None
    ]


def _bounds_for_asset(
    db: sqlite3.Connection, asset_map_index: int
) -> dict[str, float]:
    row = _map_row(db, asset_map_index)
    group_index = int(row["RegionGroupIndex"])
    tiles = _tile_set(asset_map_index, group_index)
    if not tiles:
        raise ValueError(f"Textura sem tiles confirmados: {asset_map_index}")
    tile_bounds = (
        min(item[0] for item in tiles),
        max(item[0] for item in tiles),
        min(item[1] for item in tiles),
        max(item[1] for item in tiles),
    )
    info_path = SOURCE_TILE_INFO / str(group_index) / "TileTexInfoAsset.uexp"
    if info_path.is_file():
        data = info_path.read_bytes()
        if len(data) >= 64:
            name_length = struct.unpack_from("<i", data, 8)[0]
            offset = 12 + name_length
            if 0 < name_length <= 256 and offset + 52 <= len(data):
                coordinate_scale = float(struct.unpack_from("<f", data, offset)[0])
                tile_pixels = int(struct.unpack_from("<I", data, offset + 4)[0])
                world_per_tile = float(struct.unpack_from("<f", data, offset + 8)[0])
                min_x, min_y, max_x, max_y = struct.unpack_from(
                    "<dddd", data, offset + 20
                )
                if (
                    0 < coordinate_scale <= 10_000
                    and 1 <= tile_pixels <= 4096
                    and abs(coordinate_scale * tile_pixels - world_per_tile) <= 1
                    and min_x < max_x
                    and min_y < max_y
                ):
                    return {
                        "min_x": min_x,
                        "max_x": max_x,
                        "min_y": min_y,
                        "max_y": max_y,
                        "span_x": max_x - min_x,
                        "span_y": max_y - min_y,
                        "world_per_tile": world_per_tile,
                        "coordinate_scale": coordinate_scale,
                    }
    world_per_tile = _world_per_tile(
        _spawn_positions(db, asset_map_index), tile_bounds
    )
    min_tx, max_tx, min_ty, max_ty = tile_bounds
    min_x = float(min_tx * world_per_tile)
    max_x = float((max_tx + 1) * world_per_tile)
    min_y = float(min_ty * world_per_tile)
    max_y = float((max_ty + 1) * world_per_tile)
    return {
        "min_x": min_x,
        "max_x": max_x,
        "min_y": min_y,
        "max_y": max_y,
        "span_x": max_x - min_x,
        "span_y": max_y - min_y,
        "world_per_tile": world_per_tile,
        "coordinate_scale": world_per_tile / 256,
    }


def _crop_bounds(
    points: list[tuple[float, float, float]],
    center: tuple[float, float, float],
    world: dict[str, float],
) -> dict[str, float]:
    xs = [point[0] for point in points] or [center[0]]
    ys = [point[1] for point in points] or [center[1]]
    padding = 12_800.0
    min_size = 51_200.0
    min_x, max_x = min(xs) - padding, max(xs) + padding
    min_y, max_y = min(ys) - padding, max(ys) + padding
    if max_x - min_x < min_size:
        middle = (min_x + max_x) / 2
        min_x, max_x = middle - min_size / 2, middle + min_size / 2
    if max_y - min_y < min_size:
        middle = (min_y + max_y) / 2
        min_y, max_y = middle - min_size / 2, middle + min_size / 2
    min_x, max_x = max(world["min_x"], min_x), min(world["max_x"], max_x)
    min_y, max_y = max(world["min_y"], min_y), min(world["max_y"], max_y)
    return {
        "min_x": round(min_x, 3),
        "max_x": round(max_x, 3),
        "min_y": round(min_y, 3),
        "max_y": round(max_y, 3),
        "span_x": round(max_x - min_x, 3),
        "span_y": round(max_y - min_y, 3),
    }


def _regions(
    db: sqlite3.Connection,
    map_index: int,
    world: dict[str, float],
) -> list[dict[str, object]]:
    if map_index not in {101, 103, 643, 644}:
        return []
    rows = db.execute(
        """
        SELECT s.RegionIndex,
               COALESCE(NULLIF(rpt.KO_KR,''),r.RegionNameStringIndex) name_pt,
               COALESCE(NULLIF(ren.KO_KR,''),NULLIF(rpt.KO_KR,''),r.RegionNameStringIndex) name_en,
               r.Location,s.TargetPosition1
          FROM RF_MapInfoTable_Spawn s
          JOIN RF_RegionTable r ON r.RegionIndex=s.RegionIndex
          LEFT JOIN RF_StringTable_PT_BR rpt ON rpt.StringID=r.RegionNameStringIndex
          LEFT JOIN RF_StringTable_EN_US ren ON ren.StringID=r.RegionNameStringIndex
         WHERE s.MapIndex=? AND s.NPCType=2
         ORDER BY s.RegionIndex,s.Key
        """,
        (map_index,),
    ).fetchall()
    grouped: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        grouped[int(row["RegionIndex"])].append(row)
    result = []
    for region_index, region_rows in grouped.items():
        center = _position(region_rows[0]["Location"])
        points = [
            parsed
            for row in region_rows
            if (parsed := _position(row["TargetPosition1"])) is not None
        ]
        if center is None:
            continue
        spawn_bounds = {
            "min_x": round(min(point[0] for point in points), 3),
            "max_x": round(max(point[0] for point in points), 3),
            "min_y": round(min(point[1] for point in points), 3),
            "max_y": round(max(point[1] for point in points), 3),
        }
        result.append({
            "region_index": region_index,
            "pt": str(region_rows[0]["name_pt"]),
            "en": str(region_rows[0]["name_en"]),
            "center": {
                "x": round(center[0], 3),
                "y": round(center[1], 3),
                "z": round(center[2], 3),
            },
            "spawn_count": len(points),
            "spawn_bounds": spawn_bounds,
            "crop_bounds": _crop_bounds(points, center, world),
            "evidence": "official-region-center-and-static-spawns",
        })
    return result


def main() -> None:
    if not SOURCE_DB.is_file() or not SOURCE_MAPS.is_dir() or not SOURCE_TILES.is_dir():
        raise SystemExit("Fontes canônicas de mapas não estão acessíveis")
    TARGET_MAPS.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(SOURCE_DB)
    db.row_factory = sqlite3.Row
    maps: dict[str, dict[str, object]] = {}
    try:
        categories = {
            map_index: category
            for category, map_indexes in TARGET_GROUPS.items()
            for map_index in map_indexes
        }
        for map_index in sorted(categories):
            row = _map_row(db, map_index)
            category = categories[map_index]
            display_names = DISPLAY_MAP_NAMES.get(category) or {
                "pt": str(row["name_pt"]),
                "en": str(row["name_en"]),
            }
            floor = FLOOR_BY_MAP_INDEX.get(map_index)
            asset_map_index = ASSET_ALIASES.get(map_index, map_index)
            source_image = SOURCE_MAPS / f"{asset_map_index}.webp"
            if not source_image.is_file():
                raise ValueError(
                    f"Imagem fonte ausente: {source_image} para mapa {map_index}"
                )
            target_image = TARGET_MAPS / f"{map_index}.webp"
            shutil.copy2(source_image, target_image)
            world = _bounds_for_asset(db, asset_map_index)
            positions = _spawn_positions(db, map_index)
            if not all(
                world["min_x"] <= x <= world["max_x"]
                and world["min_y"] <= y <= world["max_y"]
                for x, y, _z in positions
            ):
                raise ValueError(
                    f"Coordenadas do mapa {map_index} não cabem no asset {asset_map_index}"
                )
            maps[str(map_index)] = {
                "map_index": map_index,
                "category": category,
                "pt": str(row["name_pt"]),
                "en": str(row["name_en"]),
                "display_pt": display_names["pt"],
                "display_en": display_names["en"],
                "fixed_region": (
                    {
                        "pt": floor,
                        "en": floor,
                        "confidence": "map-index-floor",
                    }
                    if floor else None
                ),
                "asset": f"{map_index}.webp",
                "asset_source_map_index": asset_map_index,
                "level_path": str(row["LevelPath"]),
                "world_bounds": world,
                "live_position_transform": LIVE_POSITION_TRANSFORMS.get(map_index),
                "regions": _regions(db, map_index, world),
                "evidence": (
                    "shared-level-layout-static-coordinate-match"
                    if asset_map_index != map_index
                    else "official-world-map-tiles"
                ),
            }
    finally:
        db.close()
    payload = {
        "schema_version": 1,
        "source_version": "1.29.7",
        "region_resolution": "nearest-official-center",
        "groups": {key: list(value) for key, value in TARGET_GROUPS.items()},
        "maps": maps,
    }
    TARGET_CATALOG.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"OK: {len(maps)} mapas, "
        f"{sum(len(item['regions']) for item in maps.values())} regiões"
    )


if __name__ == "__main__":
    main()
