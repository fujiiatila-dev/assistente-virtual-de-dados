from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from data_assistant.assistant import DataAssistant, resolve_database_path
from data_assistant.errors import QuotaExceededError


@pytest.fixture
def assistant_db(tmp_path: Path) -> Path:
    path = tmp_path / "assistant.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE records (id INTEGER PRIMARY KEY, label TEXT);
        INSERT INTO records (label) VALUES ('A'), ('B');
        """
    )
    connection.close()
    return path


def test_runtime_database_has_priority_over_environment(
    assistant_db: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environment_db = tmp_path / "environment.db"
    monkeypatch.setenv("DB", str(environment_db))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "db-path.db"))

    assert resolve_database_path(assistant_db) == assistant_db
    assert resolve_database_path() == environment_db
    monkeypatch.delenv("DB")
    assert resolve_database_path() == tmp_path / "db-path.db"


def test_missing_database_is_operational_and_never_created(tmp_path: Path) -> None:
    missing = tmp_path / "missing.db"
    answer = DataAssistant(missing).ask("Quantos registros?")

    assert answer.status == "error"
    assert "não encontrado" in answer.response
    assert "Traceback" not in answer.response
    assert not missing.exists()


def test_invalid_sqlite_is_rejected_before_agent_call(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.db"
    invalid.write_text("isto não é sqlite", encoding="utf-8")

    answer = DataAssistant(invalid).ask("Quantos registros?")

    assert answer.status == "error"
    assert "schema" in answer.response or "SQLite" in answer.response
    assert "Traceback" not in answer.response


def test_empty_question_returns_contract_without_agent_call(assistant_db: Path) -> None:
    answer = DataAssistant(assistant_db).ask("   ")
    assert answer.status == "error"
    assert "Informe uma pergunta" in answer.response


def test_valid_question_requires_real_openrouter_configuration(
    assistant_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "")

    answer = DataAssistant(assistant_db).ask("Quantos registros existem?")

    assert answer.status == "error"
    assert "OPENROUTER_API_KEY" in answer.response
    assert answer.queries == []


def test_quota_error_returns_typed_operational_answer(assistant_db: Path) -> None:
    class ExhaustedLLM:
        def complete(self, system_prompt: str, user_prompt: str) -> str:
            raise QuotaExceededError()

        def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
            raise QuotaExceededError()

    answer = DataAssistant(assistant_db, llm=ExhaustedLLM()).ask("Quais são os registros?")
    assert answer.status == "error"
    assert answer.operational_code == "quota_exhausted"
    assert "chave própria" in answer.response
    assert "Traceback" not in answer.response
