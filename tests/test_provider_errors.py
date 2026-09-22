from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

import pytest

from data_assistant.assistant import DataAssistant
from data_assistant.errors import LLMOperationalError, QuotaExceededError
from data_assistant.llm import DEFAULT_MODEL, LLMSettings, OpenRouterLLM


@pytest.fixture
def source_db(tmp_path: Path) -> Path:
    path = tmp_path / "source.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO records (value) VALUES ('ok')")
    return path


@pytest.mark.parametrize(
    ("status_code", "detail", "code"),
    [
        (401, "bad credential", "invalid_key"),
        (402, "payment required", "quota_exhausted"),
        (429, "daily quota", "quota_exhausted"),
        (429, "burst limit", "rate_limited"),
        (503, "upstream down", "provider_unavailable"),
    ],
)
def test_provider_statuses_have_safe_public_messages(
    status_code: int, detail: str, code: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ProviderFailure(Exception):
        def __init__(self) -> None:
            self.status_code = status_code
            super().__init__(f"visitor-secret: {detail}")

    class RejectingClient:
        def __init__(self, **kwargs: Any) -> None:
            assert kwargs["model"] == DEFAULT_MODEL
            assert kwargs["max_retries"] == 0

        def invoke(self, messages: Any) -> None:
            del messages
            raise ProviderFailure()

    monkeypatch.setattr("data_assistant.llm.ChatOpenAI", RejectingClient)
    client = OpenRouterLLM(LLMSettings.for_session_key("visitor-secret"))
    with pytest.raises(LLMOperationalError) as captured:
        client.complete("system", "user")
    assert captured.value.code == code
    assert "visitor-secret" not in str(captured.value)
    assert captured.value.__context__ is None


def test_question_length_is_bounded_for_personal_key(
    source_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAX_QUESTION_CHARS", "10")
    assistant = DataAssistant(source_db, llm_settings=LLMSettings.for_session_key("visitor"))
    answer = assistant.ask("a" * 11)
    assert answer.operational_code == "local_error"
    assert "10 caracteres" in answer.response
    assert answer.queries == []


def test_session_rate_limit_is_applied_before_model_call(
    source_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_REQUESTS_PER_MINUTE", "1")

    class ExhaustedLLM:
        calls = 0

        def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
            del system_prompt, user_prompt
            self.calls += 1
            raise QuotaExceededError()

        def complete(self, system_prompt: str, user_prompt: str) -> str:
            raise AssertionError("Não deve chegar à geração SQL")

    fake = ExhaustedLLM()
    assistant = DataAssistant(source_db, llm=fake)
    assert assistant.ask("Primeira pergunta").operational_code == "quota_exhausted"
    second = assistant.ask("Segunda pergunta")
    assert second.operational_code == "rate_limited"
    assert fake.calls == 1


def test_global_concurrency_gate_is_shared_across_sessions(
    source_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAX_CONCURRENT_QUESTIONS", "1")
    entered = threading.Event()
    release = threading.Event()

    class BlockingLLM:
        def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
            del system_prompt, user_prompt
            entered.set()
            release.wait(timeout=3)
            raise QuotaExceededError()

        def complete(self, system_prompt: str, user_prompt: str) -> str:
            raise AssertionError("Não deve chegar à geração SQL")

    first = DataAssistant(source_db, llm=BlockingLLM())
    second = DataAssistant(source_db, llm=BlockingLLM())
    worker = threading.Thread(target=lambda: first.ask("Primeira pergunta"))
    worker.start()
    try:
        assert entered.wait(timeout=3)
        answer = second.ask("Segunda pergunta")
        assert answer.operational_code == "rate_limited"
        assert "atendendo outras perguntas" in answer.response
    finally:
        release.set()
        worker.join(timeout=3)


def test_personal_key_quota_has_correct_copy(source_db: Path) -> None:
    assistant = DataAssistant(source_db, llm_settings=LLMSettings.for_session_key("visitor"))

    class ExhaustedLLM:
        def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
            raise QuotaExceededError()

        def complete(self, system_prompt: str, user_prompt: str) -> str:
            raise QuotaExceededError()

    assistant._llm = ExhaustedLLM()
    answer = assistant.ask("Mostre os registros")
    assert answer.operational_code == "quota_exhausted"
    assert "chave desta sessão" in answer.response
    assert "compartilhada" not in answer.response
