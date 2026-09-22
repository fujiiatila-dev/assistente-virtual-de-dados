from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import Mock

import pytest

import app as app_module
from data_assistant.llm import DEFAULT_MODEL


def test_personal_key_activation_and_clear_are_session_scoped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "server-placeholder")
    before = os.environ["OPENROUTER_API_KEY"]
    session: dict[str, object] = {"pending_question": "Quantas compras?"}

    assert app_module._activate_session_key(session, " visitor-key ", tmp_path)
    assert session["byok_api_key"] == "visitor-key"
    assistant = session["assistant"]
    assert assistant._llm_settings.api_key == "visitor-key"  # type: ignore[attr-defined]
    assert assistant._llm_settings.model == DEFAULT_MODEL  # type: ignore[attr-defined]
    assert os.environ["OPENROUTER_API_KEY"] == before

    app_module._clear_session_key(session, tmp_path)
    assert "byok_api_key" not in session
    assert "pending_question" not in session
    assert session["assistant"] is not assistant
    assert os.environ["OPENROUTER_API_KEY"] == before


def test_empty_or_excessive_key_is_rejected(tmp_path: Path) -> None:
    session: dict[str, object] = {}
    assert not app_module._activate_session_key(session, "  ", tmp_path)
    assert not app_module._activate_session_key(session, "x" * 513, tmp_path)
    assert "byok_api_key" not in session


def test_quota_dialog_opens_only_after_explicit_click(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session: dict[str, object] = {"pending_question": "Mostre vendas"}
    dialog = Mock()
    button = Mock(return_value=False)
    monkeypatch.setattr(app_module.st, "session_state", session)
    monkeypatch.setattr(app_module.st, "button", button)
    monkeypatch.setattr(app_module.st, "caption", Mock())
    monkeypatch.setattr(app_module, "_byok_dialog", dialog)

    assert app_module._render_byok_controls(tmp_path) is None
    dialog.assert_not_called()
    button.return_value = True
    assert app_module._render_byok_controls(tmp_path) is None
    dialog.assert_called_once_with(tmp_path)
    assert session["pending_question"] == "Mostre vendas"


def test_pending_question_retries_only_on_click(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session: dict[str, object] = {"pending_question": "Mostre vendas"}
    app_module._activate_session_key(session, "visitor-key", tmp_path)
    button = Mock(return_value=False)
    monkeypatch.setattr(app_module.st, "session_state", session)
    monkeypatch.setattr(app_module.st, "button", button)
    monkeypatch.setattr(app_module.st, "info", Mock())

    assert app_module._render_byok_controls(tmp_path) is None
    assert session["pending_question"] == "Mostre vendas"
    button.return_value = True
    assert app_module._render_byok_controls(tmp_path) == "Mostre vendas"
    assert "pending_question" not in session


def test_dialog_uses_password_field_and_explicit_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session: dict[str, object] = {"pending_question": "Mostre vendas"}
    markdown = Mock()
    text_input = Mock(return_value="visitor-key")
    button = Mock(return_value=True)
    rerun = Mock()
    monkeypatch.setattr(app_module.st, "session_state", session)
    monkeypatch.setattr(app_module.st, "markdown", markdown)
    monkeypatch.setattr(app_module.st, "text_input", text_input)
    monkeypatch.setattr(app_module.st, "button", button)
    monkeypatch.setattr(app_module.st, "rerun", rerun)

    body = app_module._byok_dialog.__wrapped__
    body(tmp_path)

    assert "https://openrouter.ai/settings/keys" in markdown.call_args.args[0]
    assert "chave chega a este servidor" in markdown.call_args.args[0]
    assert text_input.call_args.kwargs["type"] == "password"
    assert button.call_args.args[0] == "Usar chave nesta sessão"
    assert session["byok_api_key"] == "visitor-key"
    assert session["pending_question"] == "Mostre vendas"
    rerun.assert_called_once()
