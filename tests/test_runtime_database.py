from __future__ import annotations

import sqlite3
from pathlib import Path

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


def test_query_parameter_selects_runtime_database_in_streamlit(tmp_path: Path) -> None:
    path = _renamed_database(tmp_path)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.query_params["DB"] = str(path)
    app.run(timeout=30)

    assert not app.exception
    assert app.success
    assert path.name in app.success[0].value


def test_invalid_runtime_path_does_not_create_file(tmp_path: Path) -> None:
    missing = tmp_path / "nao-criar.sqlite"
    answer = DataAssistant(missing).ask("Quantos registros existem?")

    assert answer.status == "error"
    assert "não encontrado" in answer.response
    assert not missing.exists()
