from __future__ import annotations

from pathlib import Path

import app as app_module


def test_radial_loader_has_six_capsules_and_status_label() -> None:
    markup = app_module._loading_markup()
    assert markup.count('aria-hidden="true"></span>') == 6
    assert [f'--i:{index}' in markup for index in range(6)] == [True] * 6
    assert 'role="status"' in markup
    assert 'aria-live="polite"' in markup
    assert "Interpretando a pergunta" in markup


def test_loader_respects_reduced_motion_without_generic_spinner() -> None:
    styles = app_module.MATERIAL_STYLES
    assert "@media (prefers-reduced-motion: reduce)" in styles
    assert ".da-loading-mark span { animation: none;" in styles
    source = Path(app_module.__file__).read_text(encoding="utf-8")
    assert "st.spinner(" not in source
