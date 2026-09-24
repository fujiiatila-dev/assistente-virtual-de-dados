from __future__ import annotations

import math

import plotly.graph_objects as go
import pytest
from dotenv import load_dotenv

from data_assistant.contract import Visualization
from data_assistant.visualization import (
    ImageExportError,
    VisualizationRenderError,
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


def test_switch_to_line_infers_single_categorical_series() -> None:
    data = [
        {"mes": "2025-01", "canal": "App", "total": 1},
        {"mes": "2025-01", "canal": "Loja", "total": 2},
    ]
    visual = visualization_for_type(data, "line", title="Tendência")
    assert visual.group == "canal"
    figure = build_plotly_figure(data, visual)
    assert [trace.name for trace in figure.data] == ["App · total", "Loja · total"]


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
    payload = b"\x89PNG\r\n\x1a\nmock"
    monkeypatch.setattr(go.Figure, "to_image", lambda self, **kwargs: payload)
    assert figure_to_png(go.Figure()) == payload


def test_png_export_failure_is_operational(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_renderer(self: go.Figure, **kwargs: object) -> bytes:
        raise RuntimeError("renderer stack trace should stay internal")

    monkeypatch.setattr(go.Figure, "to_image", fail_renderer)
    with pytest.raises(ImageExportError, match="Falha inesperada ao exportar PNG") as error:
        figure_to_png(go.Figure())
    assert "stack trace" not in str(error.value)


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (ImportError("No module named kaleido"), "Kaleido não está instalado"),
        (type("ChromeNotFoundError", (RuntimeError,), {})("missing"), "não encontrado"),
        (type("BrowserFailedError", (RuntimeError,), {})("crashed"), "não iniciou"),
    ],
)
def test_png_export_reports_actionable_failure(
    monkeypatch: pytest.MonkeyPatch, error: Exception, message: str
) -> None:
    def fail_renderer(self: go.Figure, **kwargs: object) -> bytes:
        raise error

    monkeypatch.setattr(go.Figure, "to_image", fail_renderer)
    with pytest.raises(ImageExportError, match=message) as caught:
        figure_to_png(go.Figure())
    assert "Traceback" not in str(caught.value)


def test_png_export_rejects_non_png_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(go.Figure, "to_image", lambda self, **kwargs: b"not png")
    with pytest.raises(ImageExportError, match="arquivo inválido"):
        figure_to_png(go.Figure())


def test_bars_have_external_numeric_labels_in_both_themes() -> None:
    data = [{"canal": "App", "total": 1234.5}, {"canal": "Loja", "total": None}]
    visual = Visualization(
        type="bar", title="Vendas", x="canal", y=["total"], available_types=["table", "bar"]
    )
    for dark in (False, True):
        trace = build_plotly_figure(data, visual, dark=dark).data[0]
        assert isinstance(trace, go.Bar)
        assert trace.text == ("1.234,5", "")
        assert trace.texttemplate == "%{text}"
        assert trace.textposition == "outside"
        assert trace.hovertemplate is not None


def test_line_labels_sort_chronologically_and_preserve_group_legend() -> None:
    data = [
        {"mes": "2025-03", "canal": "App", "total": 3},
        {"mes": "2025-01", "canal": "Loja", "total": 4},
        {"mes": "2025-01", "canal": "App", "total": 1},
        {"mes": "2025-02", "canal": "App", "total": 2},
        {"mes": "2025-02", "canal": "Loja", "total": 5},
    ]
    visual = Visualization(
        type="line", title="Tendência", x="mes", y=["total"], group="canal",
        available_types=["table", "line"],
    )
    figure = build_plotly_figure(data, visual)
    app, store = figure.data
    assert isinstance(app, go.Scatter)
    assert isinstance(store, go.Scatter)
    assert app.name == "App · total"
    assert app.x == ("2025-01", "2025-02", "2025-03")
    assert app.y == (1, 2, 3)
    assert app.text == ("1", "2", "3")
    assert store.name == "Loja · total"
    assert store.x == ("2025-01", "2025-02")
    assert store.y == (4, 5)
    assert app.mode == "lines+markers+text"
    assert app.textposition == "top center"
    assert figure.layout.xaxis.type == "date"
    assert figure.layout.xaxis.tickformat == "%Y-%m"


def test_duplicate_period_and_group_falls_back_without_aggregation() -> None:
    data = [
        {"mes": "2025-01", "canal": "App", "total": 1},
        {"mes": "2025-01", "canal": "App", "total": 2},
    ]
    visual = Visualization(
        type="line", title="Tendência", x="mes", y=["total"], group="canal",
        available_types=["table", "line"],
    )
    with pytest.raises(VisualizationRenderError, match="uma linha por período/série"):
        build_plotly_figure(data, visual)


def test_temporal_bar_is_grouped_by_category_and_sorted_chronologically() -> None:
    from data_assistant.visualization import normalize_visualization

    data = [
        {"data_registro": "2024-08-08", "tipo": "Loja", "quantidade": 1},
        {"data_registro": "2024-08-07", "tipo": "Compra", "quantidade": 3},
        {"data_registro": "2024-08-07", "tipo": "Suporte", "quantidade": 2},
        {"data_registro": "2024-08-08", "tipo": "Compra", "quantidade": 4},
    ]
    visual = normalize_visualization(
        data,
        {"type": "bar", "title": "Registros por data", "x": "tipo", "y": ["quantidade"]},
    )

    assert visual.type == "bar"
    assert visual.x == "data_registro"
    assert visual.group == "tipo"
    figure = build_plotly_figure(data, visual)

    assert figure.layout.barmode == "group"
    assert [trace.name for trace in figure.data] == ["Compra", "Loja", "Suporte"]
    assert figure.data[0].x == ("2024-08-07", "2024-08-08")
    assert figure.data[0].y == (3, 4)
    assert figure.data[0].text == ("3", "4")
    assert figure.data[1].y == (None, 1)


def test_temporal_grouped_bar_rejects_duplicate_period_category_measure() -> None:
    data = [
        {"mes": "2025-01", "tipo": "Compra", "quantidade": 2},
        {"mes": "2025-01", "tipo": "Compra", "quantidade": 3},
    ]
    visual = visualization_for_type(data, "bar", title="Quantidade por mês e tipo")

    assert visual.x == "mes"
    assert visual.group == "tipo"
    with pytest.raises(VisualizationRenderError, match="uma linha por período/dimensão/medida"):
        build_plotly_figure(data, visual)
    table = visualization_for_type(data, "table", title="Tendência")
    assert len(build_plotly_figure(data, table).data[0].cells.values[0]) == 2


def test_line_labels_omit_non_finite_values() -> None:
    visual = Visualization(
        type="line", title="Tendência", x="mes", y=["total"], available_types=["table", "line"]
    )
    figure = build_plotly_figure(
        [{"mes": "2025-01", "total": math.nan}, {"mes": "2025-02", "total": 2.0}],
        visual,
    )
    assert figure.data[0].text == ("", "2")


@pytest.mark.png
@pytest.mark.parametrize("visual_type", ["table", "bar", "line", "metric"])
def test_real_png_export_for_all_visual_types(visual_type: str) -> None:
    load_dotenv()
    data = [{"mes": "2025-01", "canal": "App", "total": 1}]
    visual = visualization_for_type(data, visual_type, title="Verificação")  # type: ignore[arg-type]
    figure = build_plotly_figure(data, visual)
    try:
        payload = figure_to_png(figure)
    except ImageExportError as exc:
        if "Chrome/Chromium não encontrado" in str(exc):
            pytest.skip("Chrome/Chromium não provisionado para o teste real de PNG")
        raise
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(payload) > 100
