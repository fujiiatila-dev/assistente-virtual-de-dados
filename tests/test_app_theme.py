from __future__ import annotations

import tomllib
from types import SimpleNamespace

import pytest

import app as app_module


@pytest.mark.parametrize(("system_theme", "dark"), [("light", False), ("dark", True)])
def test_export_theme_follows_native_streamlit_theme(
    system_theme: str, dark: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        app_module.st, "context", SimpleNamespace(theme=SimpleNamespace(type=system_theme))
    )
    assert app_module._is_dark_theme() is dark


def test_legacy_session_override_does_not_override_streamlit_theme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_module.st, "session_state", {"theme_override": "dark"})
    monkeypatch.setattr(
        app_module.st, "context", SimpleNamespace(theme=SimpleNamespace(type="light"))
    )

    assert app_module._is_dark_theme() is False


def test_native_settings_menu_controls_app_theme_without_custom_override() -> None:
    source = (app_module.Path(app_module.__file__).read_text(encoding="utf-8"))
    assert "_render_theme_control" not in source
    assert "_theme_choice_changed" not in source
    assert "appearance_choice" not in source
    assert "theme_override" not in source
    assert "@media (prefers-color-scheme: dark)" not in app_module.MATERIAL_STYLES
    assert "--background-color:" not in source
    assert "color-scheme:" not in source
    assert 'theme="streamlit"' in source
    assert "color: inherit" in app_module.MATERIAL_STYLES
    assert "background: currentColor" in app_module.MATERIAL_STYLES
    configuration = tomllib.loads(
        (app_module.Path(app_module.__file__).parent / ".streamlit" / "config.toml").read_text(
            encoding="utf-8"
        )
    )
    assert configuration["client"]["toolbarMode"] == "viewer"
    assert configuration["client"]["showErrorDetails"] == "none"
    assert "theme" not in configuration
