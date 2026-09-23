from __future__ import annotations

import tomllib
from types import SimpleNamespace

import pytest

import app as app_module


@pytest.mark.parametrize(("system_theme", "dark"), [("light", False), ("dark", True)])
def test_chart_palette_follows_effective_system_theme(
    system_theme: str, dark: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        app_module.st, "context", SimpleNamespace(theme=SimpleNamespace(type=system_theme))
    )
    assert app_module._is_dark_theme() is dark
    assert f"color-scheme:{system_theme}" in app_module._effective_palette_css()


def test_no_app_theme_selector_or_override() -> None:
    source = (app_module.Path(app_module.__file__).read_text(encoding="utf-8"))
    assert "_theme_override" not in source
    assert "theme_mode" not in source
    assert 'options=("System", "Light", "Dark")' not in source
    assert "@media (prefers-color-scheme: dark)" in app_module.MATERIAL_STYLES
    configuration = tomllib.loads(
        (app_module.Path(app_module.__file__).parent / ".streamlit" / "config.toml").read_text(
            encoding="utf-8"
        )
    )
    assert configuration["client"]["toolbarMode"] == "minimal"
    assert configuration["client"]["showErrorDetails"] == "none"
    assert "theme" not in configuration
