from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

import pytest

import app as app_module
from data_assistant.assistant import DataAssistant
from data_assistant.errors import LLMOperationalError
from data_assistant.llm import LLMSettings


def _database(tmp_path: Path) -> Path:
    path = tmp_path / "reference.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, label TEXT)")
        connection.execute("INSERT INTO records(label) VALUES ('demo')")
    return path


def test_visitor_keys_remain_isolated_between_two_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "server-placeholder")
    database = _database(tmp_path)
    first: dict[str, Any] = {}
    second: dict[str, Any] = {}
    app_module._activate_session_key(first, "visitor-one", database)
    app_module._activate_session_key(second, "visitor-two", database)

    assert first["byok_api_key"] == "visitor-one"
    assert second["byok_api_key"] == "visitor-two"
    assert first["assistant"]._llm_settings.api_key == "visitor-one"
    assert second["assistant"]._llm_settings.api_key == "visitor-two"
    assert os.environ["OPENROUTER_API_KEY"] == "server-placeholder"

    app_module._clear_session_key(first, database)
    assert "byok_api_key" not in first
    assert second["byok_api_key"] == "visitor-two"


def test_rejected_personal_key_never_enters_answer_or_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _database(tmp_path)
    secret = "visitor-test-secret"

    class FakeProviderError(Exception):
        status_code = 401

    class RejectingChat:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def invoke(self, messages: Any) -> Any:
            del messages
            raise FakeProviderError(f"Rejected {secret}")

        def bind(self, **kwargs: Any) -> RejectingChat:
            return self

    monkeypatch.setattr("data_assistant.llm.ChatOpenAI", RejectingChat)
    caplog.set_level(logging.INFO)
    assistant = DataAssistant(database, llm_settings=LLMSettings.for_session_key(secret))
    answer = assistant.ask("Mostre registros")

    assert answer.operational_code == "invalid_key"
    assert isinstance(LLMOperationalError("invalid_key"), RuntimeError)
    assert secret not in answer.model_dump_json()
    assert secret not in caplog.text
    assert not (tmp_path / "quota.sqlite3").exists()
