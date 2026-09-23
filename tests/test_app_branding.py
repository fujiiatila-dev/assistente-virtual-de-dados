from __future__ import annotations

from base64 import b64decode
from pathlib import Path

import app as app_module


def test_robot_asset_is_transparent_and_shared_with_header() -> None:
    asset = app_module.ROBOT_ASSET
    assert asset == Path(app_module.__file__).resolve().parent / "assets" / "robot.svg"
    svg = asset.read_text(encoding="utf-8")
    assert "<svg" in svg
    assert "<title" in svg
    assert "<rect" in svg
    assert "background" not in svg
    markup = app_module._brand_markup()
    assert 'alt="Robô do Assistente Virtual de Dados"' in markup
    encoded = markup.split("data:image/svg+xml;base64,", 1)[1].split('"', 1)[0]
    assert b64decode(encoded) == asset.read_bytes()


def test_source_status_has_no_success_card_or_emoji() -> None:
    source = Path(app_module.__file__).read_text(encoding="utf-8")
    assert "st.success(" not in source
    assert "✅" not in source
    assert "⚠️" not in source
    assert 'page_icon="📊"' not in source
    assert "Fonte de dados ·" in source
