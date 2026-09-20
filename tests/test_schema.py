from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from data_assistant.schema import SchemaCache, SchemaDiscoveryError, discover_schema


@pytest.fixture
def schema_db(tmp_path: Path) -> Path:
    path = tmp_path / "schema.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE owners (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            extra_runtime_column TEXT
        );
        CREATE TABLE pets (
            id INTEGER PRIMARY KEY,
            owner_id INTEGER NOT NULL REFERENCES owners(id),
            species TEXT,
            notes TEXT
        );
        INSERT INTO owners (name, extra_runtime_column) VALUES ('Ana', 'premium');
        INSERT INTO pets (owner_id, species, notes) VALUES (1, 'gato', 'calmo');
        INSERT INTO pets (owner_id, species, notes) VALUES (1, 'cão', 'brinca');
        """
    )
    connection.commit()
    connection.close()
    return path


def test_discovers_runtime_columns_foreign_keys_and_categories(schema_db: Path) -> None:
    snapshot = discover_schema(schema_db)
    tables = {table.name: table for table in snapshot.tables}

    assert set(tables) == {"owners", "pets"}
    assert "extra_runtime_column" in {column.name for column in tables["owners"].columns}
    assert tables["pets"].foreign_keys[0].target_table == "owners"
    species = next(column for column in tables["pets"].columns if column.name == "species")
    assert species.sample_values == ("gato", "cão")

    dsl = snapshot.to_dsl()
    assert 'TABLE "pets"' in dsl
    assert 'FK "owner_id" -> "owners"."id"' in dsl
    assert "VALUES ['gato', 'cão']" in dsl


def test_does_not_sample_high_cardinality_text(schema_db: Path) -> None:
    connection = sqlite3.connect(schema_db)
    connection.executemany(
        "INSERT INTO owners (name, extra_runtime_column) VALUES (?, ?)",
        [(f"Pessoa {index}", f"grupo-{index}") for index in range(25)],
    )
    connection.commit()
    connection.close()

    snapshot = discover_schema(schema_db)
    owners = next(table for table in snapshot.tables if table.name == "owners")
    name = next(column for column in owners.columns if column.name == "name")
    assert name.sample_values == ()


def test_cache_lifetime_is_controlled_by_session(schema_db: Path) -> None:
    cache = SchemaCache()
    first = discover_schema(schema_db, cache)
    second = discover_schema(schema_db, cache)

    assert first is second
    cache.clear()
    assert discover_schema(schema_db, cache) is not first


def test_missing_database_is_not_created(tmp_path: Path) -> None:
    missing = tmp_path / "missing.db"
    with pytest.raises(SchemaDiscoveryError, match="não encontrado"):
        discover_schema(missing)
    assert not missing.exists()
