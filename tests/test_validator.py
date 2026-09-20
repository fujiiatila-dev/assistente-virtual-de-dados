from __future__ import annotations

import pytest

from data_assistant.validator import SQLValidationError, validate_sql


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM clientes",
        "DROP TABLE clientes",
        "UPDATE clientes SET nome = 'X'",
        "INSERT INTO clientes VALUES (1)",
        "CREATE TABLE invasao (id INTEGER)",
        "ATTACH DATABASE 'other.db' AS other",
        "PRAGMA table_info(clientes)",
        "SELECT load_extension('malicious')",
        "SELECT * FROM pragma_table_info('clientes')",
    ],
)
def test_rejects_writes_and_blocked_constructs(sql: str) -> None:
    with pytest.raises(SQLValidationError):
        validate_sql(sql)


def test_rejects_multiple_statements() -> None:
    with pytest.raises(SQLValidationError, match="um statement"):
        validate_sql("SELECT 1; DROP TABLE clientes")


def test_accepts_semicolon_and_blocked_words_inside_literal() -> None:
    sql = validate_sql("SELECT '; DROP TABLE x; PRAGMA; ATTACH; load_extension' AS texto")
    assert "DROP TABLE" in sql


def test_accepts_select_and_cte() -> None:
    assert validate_sql("SELECT 1 AS value") == "SELECT 1 AS value"
    validated = validate_sql("WITH totals AS (SELECT 1 AS value) SELECT value FROM totals")
    assert validated.startswith("WITH totals AS")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM a CROSS JOIN b",
        "SELECT * FROM a JOIN b",
        "SELECT * FROM a, b",
    ],
)
def test_rejects_joins_without_conditions(sql: str) -> None:
    with pytest.raises(SQLValidationError, match="JOIN sem condição"):
        validate_sql(sql)


def test_accepts_join_with_condition_and_natural_join() -> None:
    assert " ON " in validate_sql("SELECT a.id FROM a JOIN b ON b.a_id = a.id")
    assert "NATURAL JOIN" in validate_sql("SELECT * FROM a NATURAL JOIN b")


def test_rejects_empty_or_invalid_sql() -> None:
    with pytest.raises(SQLValidationError, match="vazia"):
        validate_sql(" ")
    with pytest.raises(SQLValidationError, match="SQL inválido"):
        validate_sql("SELECT FROM")
