from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from data_assistant.assistant import DataAssistant, ask, resolve_database_path


class StubLLM:
    def __init__(self) -> None:
        self.texts = ["SELECT COUNT(*) AS total FROM records"]
        self.payloads: list[dict[str, Any]] = [
            {"intent": "count"},
            {"sufficient": True, "reason": "Contagem disponível."},
            {
                "response": "Há 2 registros.",
                "visualization": {
                    "type": "metric",
                    "title": "Total",
                    "y": ["total"],
                },
            },
        ]

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        del system_prompt, user_prompt
        return self.texts.pop(0)

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        del system_prompt, user_prompt
        return self.payloads.pop(0)


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


def test_ask_runs_graph_and_validates_contract(assistant_db: Path) -> None:
    answer = ask("Quantos registros existem?", database_path=assistant_db, llm=StubLLM())

    assert answer.status == "success"
    assert answer.response == "Há 2 registros."
    assert answer.data == [{"total": 2}]
    assert answer.visualization.type == "metric"
    assert answer.queries == ["SELECT COUNT(*) AS total FROM records"]


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
    answer = DataAssistant(missing, llm=StubLLM()).ask("Quantos registros?")

    assert answer.status == "error"
    assert "não encontrado" in answer.response
    assert "Traceback" not in answer.response
    assert not missing.exists()


def test_invalid_sqlite_is_rejected_before_model_call(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.db"
    invalid.write_text("isto não é sqlite", encoding="utf-8")
    model = StubLLM()

    answer = DataAssistant(invalid, llm=model).ask("Quantos registros?")

    assert answer.status == "error"
    assert "schema" in answer.response or "SQLite" in answer.response
    assert model.texts == ["SELECT COUNT(*) AS total FROM records"]


def test_empty_question_returns_contract_without_model_call(assistant_db: Path) -> None:
    answer = DataAssistant(assistant_db, llm=StubLLM()).ask("   ")
    assert answer.status == "error"
    assert "Informe uma pergunta" in answer.response
