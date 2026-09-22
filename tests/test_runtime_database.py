from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from data_assistant.assistant import DataAssistant
from data_assistant.schema import discover_schema


def _renamed_database(tmp_path: Path) -> Path:
    path = tmp_path / "fonte-renomeada.sqlite"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE runtime_only (id INTEGER PRIMARY KEY, label TEXT)")
    connection.execute("INSERT INTO runtime_only (label) VALUES ('descoberto')")
    connection.commit()
    connection.close()
    return path


def test_runtime_database_is_read_only_and_schema_is_rediscovered(tmp_path: Path) -> None:
    path = _renamed_database(tmp_path)
    before = path.stat().st_mtime_ns

    snapshot = discover_schema(path)

    assert [table.name for table in snapshot.tables] == ["runtime_only"]
    assert path.stat().st_mtime_ns == before


def test_public_query_parameter_cannot_select_runtime_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _renamed_database(tmp_path)
    missing = tmp_path / "operator-only.sqlite"
    monkeypatch.setenv("DB_PATH", str(missing))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.query_params["DB"] = str(path)
    app.run(timeout=30)

    assert not app.exception
    assert not app.success
    assert any("Banco ausente" in error.value for error in app.error)
    assert not missing.exists()


def test_sidebar_shows_configured_openrouter_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _renamed_database(tmp_path)
    monkeypatch.setenv("DB_PATH", str(path))
    monkeypatch.setenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4")
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")

    app.run(timeout=30)

    assert not app.exception
    assert any(
        "Modelo · anthropic/claude-sonnet-4" in caption.value for caption in app.caption
    )


def test_invalid_runtime_path_does_not_create_file(tmp_path: Path) -> None:
    missing = tmp_path / "nao-criar.sqlite"
    answer = DataAssistant(missing).ask("Quantos registros existem?")

    assert answer.status == "error"
    assert "não encontrado" in answer.response
    assert not missing.exists()
