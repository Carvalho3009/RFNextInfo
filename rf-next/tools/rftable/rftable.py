#!/usr/bin/env python3
"""Leitor do formato autodescritivo RFTable usado por RF ONLINE NEXT 1.28.5."""

from __future__ import annotations

import argparse
import csv
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


MAGIC = b"RFT\x1a"
ENUM_SIZES = {2: 4, 4: 4, 8: 1, 9: 2, 11: 4}
SCALAR_FORMATS = {
    0x05: "b",
    0x06: "B",
    0x07: "h",
    0x08: "H",
    0x09: "i",
    0x0A: "I",
    0x0B: "q",
    0x0C: "Q",
    0x0D: "f",
    0x0E: "d",
}
STRING_TYPES = {0x0F, 0x10, 0x15, 0x16}


@dataclass(frozen=True)
class Column:
    type_code: int
    primary_key: bool
    grouped: bool
    is_array: bool
    enum_storage: int
    name: str
    referenced_type: str
    default_value: str
    description: str
    raw_header: bytes


@dataclass(frozen=True)
class RFTable:
    path: Path
    name: str
    row_count: int
    columns: tuple[Column, ...]
    data: bytes
    data_offset: int

    def rows(self) -> Iterator[dict[str, Any]]:
        pos = self.data_offset
        for row_number in range(self.row_count):
            row: dict[str, Any] = {}
            for column in self.columns:
                if column.is_array:
                    count = struct.unpack_from("<H", self.data, pos)[0]
                    pos += 2
                    if count > 10000:
                        raise ValueError(
                            f"Contagem de array invalida ({count}) em "
                            f"{self.path.name}, linha {row_number}, coluna {column.name}"
                        )
                    values = []
                    for _ in range(count):
                        value, pos = _read_scalar(self.data, pos, column)
                        values.append(value)
                    row[column.name] = values
                else:
                    row[column.name], pos = _read_scalar(self.data, pos, column)
            yield row

        if pos != len(self.data):
            raise ValueError(
                f"Leitura incompleta de {self.path.name}: posicao={pos}, tamanho={len(self.data)}"
            )


def _cstring(data: bytes, pos: int) -> tuple[str, int]:
    end = data.index(0, pos)
    return data[pos:end].decode("utf-8", errors="replace"), end + 1


def _find_header(data: bytes) -> tuple[int, int, int]:
    for pos in range(0x18, min(0x100, len(data) - 13)):
        column_count = struct.unpack_from("<H", data, pos)[0]
        row_count = struct.unpack_from("<I", data, pos + 2)[0]
        payload_size = struct.unpack_from("<Q", data, pos + 6)[0]
        if (
            0 < column_count < 1000
            and row_count < 10_000_000
            and payload_size == len(data) - pos - 14
        ):
            return pos, column_count, row_count
    raise ValueError("Cabecalho RFTable nao encontrado")


def _read_scalar(data: bytes, pos: int, column: Column) -> tuple[Any, int]:
    type_code = column.type_code
    if type_code == 0x03:
        size = ENUM_SIZES.get(column.enum_storage)
        if size is None:
            raise ValueError(
                f"Enum com armazenamento desconhecido: {column.enum_storage} ({column.name})"
            )
        fmt = {1: "B", 2: "H", 4: "I", 8: "Q"}[size]
        return struct.unpack_from("<" + fmt, data, pos)[0], pos + size
    if type_code == 0x04:
        return bool(data[pos]), pos + 1
    if type_code in SCALAR_FORMATS:
        fmt = "<" + SCALAR_FORMATS[type_code]
        return struct.unpack_from(fmt, data, pos)[0], pos + struct.calcsize(fmt)
    if type_code in STRING_TYPES:
        return _cstring(data, pos)
    if type_code == 0x12:
        return tuple(data[pos : pos + 4]), pos + 4
    if type_code == 0x13:
        return struct.unpack_from("<dd", data, pos), pos + 16
    if type_code == 0x14:
        return struct.unpack_from("<ddd", data, pos), pos + 24
    raise ValueError(f"Tipo RFTable desconhecido: 0x{type_code:02X} ({column.name})")


def load(path: str | Path) -> RFTable:
    source = Path(path)
    data = source.read_bytes()
    if not data.startswith(MAGIC):
        raise ValueError(f"{source} nao e um RFTable valido")

    table_name, _ = _cstring(data, 0x17)
    header_pos, column_count, row_count = _find_header(data)
    pos = header_pos + 14
    columns = []
    for _ in range(column_count):
        raw_header = data[pos : pos + 12]
        pos += 12
        strings = []
        for _ in range(4):
            value, pos = _cstring(data, pos)
            strings.append(value)
        columns.append(
            Column(
                type_code=raw_header[0],
                primary_key=bool(raw_header[1]),
                grouped=bool(raw_header[2]),
                is_array=bool(raw_header[5]),
                enum_storage=raw_header[10],
                name=strings[0],
                referenced_type=strings[1],
                default_value=strings[2],
                description=strings[3],
                raw_header=raw_header,
            )
        )
    return RFTable(source, table_name, row_count, tuple(columns), data, pos)


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def export_csv(table: RFTable, output: str | Path) -> int:
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fields = [column.name for column in table.columns]
    count = 0
    with destination.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in table.rows():
            writer.writerow({key: _csv_value(value) for key, value in row.items()})
            count += 1
    return count


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Arquivo .RFTable")
    parser.add_argument("-o", "--output", type=Path, help="CSV de saida")
    parser.add_argument("--schema", action="store_true", help="Mostra somente o esquema")
    args = parser.parse_args()

    table = load(args.input)
    if args.schema:
        print(json.dumps({
            "table": table.name,
            "rows": table.row_count,
            "columns": [
                {
                    "name": column.name,
                    "type_code": f"0x{column.type_code:02X}",
                    "referenced_type": column.referenced_type,
                    "array": column.is_array,
                    "description": column.description,
                }
                for column in table.columns
            ],
        }, ensure_ascii=False, indent=2))
        return 0

    output = args.output or args.input.with_suffix(".csv")
    count = export_csv(table, output)
    print(f"{table.name}: {count} linhas -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
