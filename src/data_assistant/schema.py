"""Runtime SQLite schema discovery with optional session-scoped caching."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

MAX_CATEGORY_VALUES: Final = 20


class SchemaDiscoveryError(RuntimeError):
    """Raised when a database cannot be introspected safely."""


@dataclass(frozen=True)
class ColumnInfo:
    """Metadata for one SQLite column."""

    name: str
    data_type: str
    not_null: bool
    primary_key: bool
    sample_values: tuple[str, ...] = ()


@dataclass(frozen=True)
class ForeignKeyInfo:
    """A foreign key relationship discovered through SQLite metadata."""

    column: str
    target_table: str
    target_column: str


@dataclass(frozen=True)
class TableInfo:
    """Discovered metadata for a table or view."""

    name: str
    kind: str
    columns: tuple[ColumnInfo, ...]
    foreign_keys: tuple[ForeignKeyInfo, ...]


@dataclass(frozen=True)
class SchemaSnapshot:
    """A serializable view of the database schema."""

    tables: tuple[TableInfo, ...]

    def to_dsl(self) -> str:
        """Serialize metadata into a compact text format suitable for an LLM prompt."""
        lines: list[str] = []
        for table in self.tables:
            lines.append(f'{table.kind.upper()} "{table.name}"')
            for column in table.columns:
                flags: list[str] = []
                if column.primary_key:
                    flags.append("PK")
                if column.not_null:
                    flags.append("NOT NULL")
                suffix = f" [{' '.join(flags)}]" if flags else ""
                samples = ""
                if column.sample_values:
                    rendered = ", ".join(repr(value) for value in column.sample_values)
                    samples = f" VALUES [{rendered}]"
                lines.append(f'  - "{column.name}" {column.data_type or "ANY"}{suffix}{samples}')
            for foreign_key in table.foreign_keys:
                lines.append(
                    f'  FK "{foreign_key.column}" -> '
                    f'"{foreign_key.target_table}"."{foreign_key.target_column}"'
                )
        return "\n".join(lines)


@dataclass
class SchemaCache:
    """In-memory cache whose lifetime is controlled by the caller's session."""

    _snapshots: dict[Path, SchemaSnapshot] = field(default_factory=dict)

    def get(self, path: Path) -> SchemaSnapshot | None:
        return self._snapshots.get(path.resolve())

    def put(self, path: Path, snapshot: SchemaSnapshot) -> None:
        self._snapshots[path.resolve()] = snapshot

    def clear(self) -> None:
        self._snapshots.clear()


def quote_identifier(identifier: str) -> str:
    """Quote an identifier for SQLite metadata-generated queries."""
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'


def _connect_read_only(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise SchemaDiscoveryError(f"Arquivo SQLite não encontrado: {path}")
    try:
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5.0)
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA foreign_keys=ON")
    except sqlite3.Error as exc:
        raise SchemaDiscoveryError(f"Não foi possível ler o schema do SQLite: {exc}") from exc
    return connection


def _is_text_type(data_type: str) -> bool:
    normalized = data_type.upper()
    return any(marker in normalized for marker in ("CHAR", "CLOB", "TEXT"))


def _sample_low_cardinality_values(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    *,
    maximum: int,
) -> tuple[str, ...]:
    table_sql = quote_identifier(table)
    column_sql = quote_identifier(column)
    rows = connection.execute(
        f"SELECT DISTINCT {column_sql} FROM {table_sql} "
        f"WHERE {column_sql} IS NOT NULL LIMIT ?",
        (maximum + 1,),
    ).fetchall()
    if len(rows) > maximum:
        return ()
    return tuple(str(row[0]) for row in rows)


def _discover(connection: sqlite3.Connection) -> SchemaSnapshot:
    objects = connection.execute(
        """
        SELECT name, type
        FROM sqlite_master
        WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    tables: list[TableInfo] = []
    for raw_name, raw_kind in objects:
        name, kind = str(raw_name), str(raw_kind)
        table_sql = quote_identifier(name)
        column_rows = connection.execute(f"PRAGMA table_info({table_sql})").fetchall()
        columns: list[ColumnInfo] = []
        for row in column_rows:
            column_name, data_type = str(row[1]), str(row[2] or "")
            sample_values: tuple[str, ...] = ()
            if kind == "table" and _is_text_type(data_type):
                sample_values = _sample_low_cardinality_values(
                    connection,
                    name,
                    column_name,
                    maximum=MAX_CATEGORY_VALUES,
                )
            columns.append(
                ColumnInfo(
                    name=column_name,
                    data_type=data_type,
                    not_null=bool(row[3]),
                    primary_key=bool(row[5]),
                    sample_values=sample_values,
                )
            )

        foreign_key_rows = connection.execute(f"PRAGMA foreign_key_list({table_sql})").fetchall()
        foreign_keys = tuple(
            ForeignKeyInfo(column=str(row[3]), target_table=str(row[2]), target_column=str(row[4]))
            for row in foreign_key_rows
        )
        tables.append(
            TableInfo(
                name=name,
                kind=kind,
                columns=tuple(columns),
                foreign_keys=foreign_keys,
            )
        )
    return SchemaSnapshot(tables=tuple(tables))


def discover_schema(path: str | Path, cache: SchemaCache | None = None) -> SchemaSnapshot:
    """Discover tables, columns, relations and low-cardinality text values at runtime."""
    database_path = Path(path).expanduser()
    cached = cache.get(database_path) if cache else None
    if cached is not None:
        return cached

    connection = _connect_read_only(database_path)
    try:
        snapshot = _discover(connection)
    except sqlite3.Error as exc:
        raise SchemaDiscoveryError(f"Falha durante a descoberta do schema: {exc}") from exc
    finally:
        connection.close()

    if cache:
        cache.put(database_path, snapshot)
    return snapshot
