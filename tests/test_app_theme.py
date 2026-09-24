from __future__ import annotations

import tomllib
from types import SimpleNamespace

import pytest

import app as app_module


@pytest.mark.parametrize(("system_theme", "dark"), [("light", False), ("dark", True)])
def test_chart_palette_follows_effective_system_theme(
    system_theme: str, dark: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_module.st, "session_state", {})
    monkeypatch.setattr(
        app_module.st, "context", SimpleNamespace(theme=SimpleNamespace(type=system_theme))
    )
    assert app_module._is_dark_theme() is dark
    assert f"color-scheme:{system_theme}" in app_module._effective_palette_css()


def test_theme_override_is_session_local_and_can_return_to_system(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session: dict[str, str] = {"appearance_choice": "Escuro"}
    monkeypatch.setattr(app_module.st, "session_state", session)
    monkeypatch.setattr(
        app_module.st, "context", SimpleNamespace(theme=SimpleNamespace(type="light"))
    )

    app_module._theme_choice_changed()
    assert session["theme_override"] == "dark"
    assert app_module._is_dark_theme() is True

    session["appearance_choice"] = "Claro"
    app_module._theme_choice_changed()
    assert session["theme_override"] == "light"
    assert app_module._is_dark_theme() is False

    session["appearance_choice"] = "Sistema"
    app_module._theme_choice_changed()
    assert "theme_override" not in session
    assert app_module._is_dark_theme() is False


def test_theme_control_is_discreet_and_has_system_default() -> None:
    source = (app_module.Path(app_module.__file__).read_text(encoding="utf-8"))
    assert "def _render_theme_control" in source
    assert "st.popover(" in source
    assert 'options=("Sistema", "Claro", "Escuro")' in source
    assert 'st.session_state["theme_override"] = "dark"' in source
    assert "theme_mode" not in source
    assert "@media (prefers-color-scheme: dark)" in app_module.MATERIAL_STYLES
    configuration = tomllib.loads(
        (app_module.Path(app_module.__file__).parent / ".streamlit" / "config.toml").read_text(
            encoding="utf-8"
        )
    )
    assert configuration["client"]["toolbarMode"] == "minimal"
    assert configuration["client"]["showErrorDetails"] == "none"
    assert "theme" not in configuration
