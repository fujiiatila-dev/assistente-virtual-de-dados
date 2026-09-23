from __future__ import annotations

from unittest.mock import Mock

import pytest

import app as app_module
from data_assistant.contract import AssistantAnswer, Visualization


def _answer(data: list[dict[str, object]], kind: str) -> AssistantAnswer:
    return AssistantAnswer(
        status="success",
        response="Resultado",
        data=data,
        visualization=Visualization(
            type=kind,  # type: ignore[arg-type]
            title="Verificação",
            x="mes" if kind == "line" else "canal",
            y=["total"],
            group="canal" if kind == "line" else None,
            available_types=["table", "bar", "line"],
        ),
    )


def test_png_failure_preserves_interactive_chart(monkeypatch: pytest.MonkeyPatch) -> None:
    chart = Mock()
    info = Mock()
    download = Mock()
    monkeypatch.setattr(app_module.st, "selectbox", lambda *args, **kwargs: "bar")
    monkeypatch.setattr(app_module.st, "plotly_chart", chart)
    monkeypatch.setattr(app_module.st, "columns", lambda count: [download])
    monkeypatch.setattr(app_module.st, "info", info)
    monkeypatch.setattr(app_module, "_is_dark_theme", lambda: False)
    monkeypatch.setattr(
        app_module, "_cached_png", lambda *args: (None, "Chrome/Chromium não encontrado")
    )

    app_module._render_visualization(
        _answer([{"canal": "App", "total": 2}], "bar"),
        key_prefix="teste",
    )

    chart.assert_called_once()
    info.assert_called_once_with("Chrome/Chromium não encontrado")
    download.download_button.assert_not_called()


def test_ambiguous_line_falls_back_to_table_and_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    chart = Mock()
    dataframe = Mock()
    warning = Mock()
    csv_slot = Mock()
    png_slot = Mock()
    monkeypatch.setattr(app_module.st, "selectbox", lambda *args, **kwargs: "line")
    monkeypatch.setattr(app_module.st, "plotly_chart", chart)
    monkeypatch.setattr(app_module.st, "dataframe", dataframe)
    monkeypatch.setattr(app_module.st, "warning", warning)
    monkeypatch.setattr(app_module.st, "columns", lambda count: [csv_slot, png_slot])
    monkeypatch.setattr(app_module.st, "info", Mock())
    monkeypatch.setattr(app_module, "_is_dark_theme", lambda: False)
    monkeypatch.setattr(app_module, "_cached_png", lambda *args: (None, "PNG indisponível"))

    app_module._render_visualization(
        _answer(
            [
                {"mes": "2025-01", "canal": "App", "total": 1},
                {"mes": "2025-01", "canal": "App", "total": 2},
            ],
            "line",
        ),
        key_prefix="teste",
    )

    chart.assert_not_called()
    dataframe.assert_called_once()
    assert "uma linha por período/série" in warning.call_args.args[0]
    csv_slot.download_button.assert_called_once()
    assert csv_slot.download_button.call_args.args[0] == "Baixar CSV"
