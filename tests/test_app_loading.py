from __future__ import annotations

from pathlib import Path

import app as app_module
from data_assistant.execution import ExecutionSnapshot, PublicPhase


def test_radial_loader_has_six_capsules_and_status_label() -> None:
    markup = app_module._loading_markup()
    assert markup.count('aria-hidden="true"></span>') == 6
    assert [f'--i:{index}' in markup for index in range(6)] == [True] * 6
    assert 'role="status"' in markup
    assert 'aria-live="polite"' in markup
    assert "Entendendo a pergunta" in markup


def test_loader_respects_reduced_motion_without_generic_spinner() -> None:
    styles = app_module.MATERIAL_STYLES
    assert "@media (prefers-reduced-motion: reduce)" in styles
    assert ".da-loading-mark span { animation: none;" in styles
    source = Path(app_module.__file__).read_text(encoding="utf-8")
    assert "st.spinner(" not in source


def test_public_progress_uses_closed_operational_messages() -> None:
    snapshot = ExecutionSnapshot(
        phase=PublicPhase.VALIDATING,
        cancellation_requested=False,
        may_have_consumed_quota=False,
        done=False,
    )
    markup = app_module._progress_markup(snapshot)
    assert "Validando a consulta" in markup
    assert 'aria-live="polite"' in markup
    assert "SQL privado" not in markup


def test_cancellation_progress_warns_about_provider_quota_without_results() -> None:
    snapshot = ExecutionSnapshot(
        phase=PublicPhase.CHECKING,
        cancellation_requested=True,
        may_have_consumed_quota=True,
        done=False,
    )
    markup = app_module._progress_markup(snapshot)
    assert "Solicitação de parada enviada" in markup
    assert "pode ter consumido cota" in markup
