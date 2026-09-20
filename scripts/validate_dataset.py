"""Validate the local Challenge 1 dataset without modifying it."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Final

REQUIRED_SCHEMA: Final[dict[str, set[str]]] = {
    "clientes": {"id", "nome", "email", "idade", "cidade", "estado", "profissao", "genero"},
    "compras": {"id", "cliente_id", "data_compra", "valor", "categoria", "canal"},
    "suporte": {"id", "cliente_id", "data_contato", "tipo_contato", "resolvido", "canal"},
    "campanhas_marketing": {
        "id",
        "cliente_id",
        "nome_campanha",
        "data_envio",
        "interagiu",
        "canal",
    },
}

DATE_COLUMNS: Final[dict[str, str]] = {
    "compras": "data_compra",
    "suporte": "data_contato",
    "campanhas_marketing": "data_envio",
}


def _read_only_uri(path: Path) -> str:
    """Return a SQLite URI that fails instead of creating a missing database."""
    return f"{path.resolve().as_uri()}?mode=ro"


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    escaped = table.replace('"', '""')
    return {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{escaped}")')}


def validate_dataset(path: Path) -> tuple[list[str], list[str]]:
    """Validate schema and integrity, returning warnings and errors."""
    warnings: list[str] = []
    errors: list[str] = []

    if not path.is_file():
        return warnings, [f"Arquivo não encontrado: {path}"]

    try:
        connection = sqlite3.connect(_read_only_uri(path), uri=True, timeout=5.0)
    except sqlite3.Error as exc:
        return warnings, [f"Não foi possível abrir o SQLite em modo somente leitura: {exc}"]

    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA foreign_keys=ON")

        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            errors.append(f"Falha no integrity_check: {integrity}")

        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        missing_tables = sorted(REQUIRED_SCHEMA.keys() - tables)
        if missing_tables:
            errors.append(f"Tabelas obrigatórias ausentes: {', '.join(missing_tables)}")

        for table, required_columns in REQUIRED_SCHEMA.items():
            if table not in tables:
                continue
            actual_columns = _columns(connection, table)
            missing_columns = sorted(required_columns - actual_columns)
            if missing_columns:
                errors.append(
                    f"Colunas obrigatórias ausentes em {table}: {', '.join(missing_columns)}"
                )
            extra_columns = sorted(actual_columns - required_columns)
            if extra_columns:
                print(f"INFO: {table} contém colunas extras toleradas: {', '.join(extra_columns)}")

        foreign_key_issues = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_issues:
            errors.append(f"Chaves estrangeiras com órfãos: {len(foreign_key_issues)} ocorrência(s)")

        for table in sorted(REQUIRED_SCHEMA):
            if table in tables:
                count = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                print(f"CONTAGEM: {table}={count}")

        for table, column in DATE_COLUMNS.items():
            if table in tables and column in _columns(connection, table):
                date_range = connection.execute(
                    f'SELECT MIN("{column}"), MAX("{column}") FROM "{table}"'
                ).fetchone()
                print(f"PERÍODO: {table}.{column}={date_range[0]} a {date_range[1]}")

        customer_columns = _columns(connection, "clientes") if "clientes" in tables else set()
        purchase_columns = _columns(connection, "compras") if "compras" in tables else set()
        if {
            "id",
            "valor_total_gasto",
            "data_ultima_compra",
        }.issubset(customer_columns) and {
            "cliente_id",
            "valor",
            "data_compra",
        }.issubset(purchase_columns):
            divergence = connection.execute(
                """
                WITH fatos AS (
                    SELECT cliente_id, SUM(valor) AS total, MAX(data_compra) AS ultima
                    FROM compras
                    GROUP BY cliente_id
                )
                SELECT
                    SUM(CASE WHEN ABS(COALESCE(c.valor_total_gasto, 0) - COALESCE(f.total, 0)) > 0.01
                        THEN 1 ELSE 0 END),
                    SUM(CASE WHEN COALESCE(c.data_ultima_compra, '') <> COALESCE(f.ultima, '')
                        THEN 1 ELSE 0 END)
                FROM clientes AS c
                LEFT JOIN fatos AS f ON f.cliente_id = c.id
                """
            ).fetchone()
            total_mismatches, date_mismatches = int(divergence[0] or 0), int(divergence[1] or 0)
            if total_mismatches or date_mismatches:
                warnings.append(
                    "Campos denormalizados de clientes divergem de compras: "
                    f"valor_total_gasto={total_mismatches}, data_ultima_compra={date_mismatches}. "
                    "Use compras como fonte de verdade para métricas operacionais."
                )
    except sqlite3.DatabaseError as exc:
        errors.append(f"SQLite inválido ou ilegível: {exc}")
    finally:
        connection.close()

    return warnings, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path, help="Caminho do arquivo SQLite")
    args = parser.parse_args()

    warnings, errors = validate_dataset(args.db)
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        return 1
    print("OK: dataset legível e contrato mínimo validado em modo somente leitura.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
