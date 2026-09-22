from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from data_assistant.assistant import DataAssistant
from data_assistant.llm import DEFAULT_MODEL, LLMSettings


def test_session_settings_keep_keys_isolated_without_environment_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "server-placeholder")
    before = os.environ["OPENROUTER_API_KEY"]
    first = LLMSettings.for_session_key("visitor-one")
    second = LLMSettings.for_session_key("visitor-two")

    assert first.api_key == "visitor-one"
    assert second.api_key == "visitor-two"
    assert first.model == second.model == DEFAULT_MODEL
    assert first.max_retries == second.max_retries == 0
    assert os.environ["OPENROUTER_API_KEY"] == before


def test_assistant_uses_explicit_client_settings_per_instance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: list[LLMSettings] = []

    class FakeClient:
        def __init__(self, settings: LLMSettings) -> None:
            observed.append(settings)

        def complete(self, system_prompt: str, user_prompt: str) -> str:
            raise AssertionError("Não deve consultar o modelo neste teste")

        def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
            raise AssertionError("Não deve consultar o modelo neste teste")

    monkeypatch.setattr("data_assistant.assistant.OpenRouterLLM", FakeClient)
    first = DataAssistant(tmp_path, llm_settings=LLMSettings.for_session_key("visitor-one"))
    second = DataAssistant(tmp_path, llm_settings=LLMSettings.for_session_key("visitor-two"))
    first._model()
    second._model()

    assert [settings.api_key for settings in observed] == ["visitor-one", "visitor-two"]
    assert first._model() is not second._model()


def test_assistant_rejects_two_client_sources(tmp_path: Path) -> None:
    class DummyLLM:
        def complete(self, system_prompt: str, user_prompt: str) -> str:
            return "unused"

        def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
            return {}

    with pytest.raises(ValueError, match="nunca ambos"):
        DataAssistant(
            tmp_path,
            llm=DummyLLM(),
            llm_settings=LLMSettings.for_session_key("visitor-one"),
        )
