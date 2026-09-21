from __future__ import annotations

import pytest

from data_assistant.llm import DEFAULT_MODEL, LLMSettings, resolve_model_name


@pytest.mark.parametrize("configured", [None, "", "   "])
def test_model_name_falls_back_to_default(
    configured: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    if configured is None:
        monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    else:
        monkeypatch.setenv("OPENROUTER_MODEL", configured)

    assert resolve_model_name() == DEFAULT_MODEL
    assert LLMSettings.from_environment().model == DEFAULT_MODEL


def test_model_name_uses_trimmed_environment_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_MODEL", "  anthropic/claude-sonnet-4  ")

    assert resolve_model_name() == "anthropic/claude-sonnet-4"
    assert LLMSettings.from_environment().model == "anthropic/claude-sonnet-4"
