from __future__ import annotations

import plotly.graph_objects as go
import pytest

from data_assistant.contract import Visualization
from data_assistant.visualization import (
    ImageExportError,
    build_plotly_figure,
    figure_to_png,
    result_to_csv,
    visualization_for_type,
)


def test_switches_visual_type_locally_from_existing_rows() -> None:
    data = [{"canal": "App", "total": 10}, {"canal": "Loja", "total": 5}]
    visual = visualization_for_type(data, "bar", title="Vendas")

    assert visual.type == "bar"
    assert visual.x == "canal"
    assert visual.y == ["total"]
    assert visual.available_types == ["table", "bar"]


@pytest.mark.parametrize(
    ("visualization", "expected_trace"),
    [
        (
            Visualization(type="table", title="Tabela", available_types=["table"]),
            go.Table,
        ),
        (
            Visualization(
                type="bar",
                title="Barras",
                x="label",
                y=["total"],
                available_types=["table", "bar"],
            ),
            go.Bar,
        ),
        (
            Visualization(
                type="line",
                title="Linha",
                x="label",
                y=["total"],
                available_types=["table", "line"],
            ),
            go.Scatter,
        ),
        (
            Visualization(
                type="metric",
                title="Métrica",
                y=["total"],
                available_types=["table", "metric"],
            ),
            go.Indicator,
        ),
    ],
)
def test_builds_plotly_figure_for_every_contract_type(
    visualization: Visualization, expected_trace: type[object]
) -> None:
    figure = build_plotly_figure([{"label": "2025-01", "total": 10}], visualization)
    assert isinstance(figure.data[0], expected_trace)


def test_csv_export_is_utf8_and_preserves_columns() -> None:
    payload = result_to_csv([{"estado": "São Paulo", "total": 6}])
    decoded = payload.decode("utf-8-sig")
    assert decoded.splitlines() == ["estado,total", "São Paulo,6"]


def test_png_export_returns_renderer_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(go.Figure, "to_image", lambda self, **kwargs: b"png")
    assert figure_to_png(go.Figure()) == b"png"


def test_png_export_failure_is_operational(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_renderer(self: go.Figure, **kwargs: object) -> bytes:
        raise RuntimeError("renderer stack trace should stay internal")

    monkeypatch.setattr(go.Figure, "to_image", fail_renderer)
    with pytest.raises(ImageExportError, match="renderer de PNG está indisponível") as error:
        figure_to_png(go.Figure())
    assert "stack trace" not in str(error.value)
