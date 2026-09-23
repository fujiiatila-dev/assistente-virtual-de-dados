"""Deterministic visualization compatibility and fallback rules."""

from __future__ import annotations

import csv
import io
import math
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any, cast

import plotly.graph_objects as go

from data_assistant.contract import Visualization, VisualizationType

TYPE_ORDER: tuple[VisualizationType, ...] = ("table", "bar", "line", "metric")


def _columns(data: Sequence[Mapping[str, Any]]) -> list[str]:
    return list(dict.fromkeys(key for row in data for key in row))


def _non_null_values(data: Sequence[Mapping[str, Any]], column: str) -> list[Any]:
    return [row[column] for row in data if row.get(column) is not None]


def _is_numeric_column(data: Sequence[Mapping[str, Any]], column: str) -> bool:
    values = _non_null_values(data, column)
    return bool(values) and all(
        isinstance(value, int | float) and not isinstance(value, bool) for value in values
    )


def _looks_temporal(value: Any) -> bool:
    if isinstance(value, date | datetime):
        return True
    if not isinstance(value, str):
        return False
    candidate = value.strip().replace("Z", "+00:00")
    try:
        datetime.fromisoformat(candidate)
    except ValueError:
        return bool(
            len(candidate) == 7
            and candidate[4] == "-"
            and candidate[:4].isdigit()
            and candidate[5:].isdigit()
        )
    return True


def _is_temporal_column(data: Sequence[Mapping[str, Any]], column: str) -> bool:
    normalized = column.casefold()
    date_tokens = ("data", "date", "mês", "mes", "month", "período", "periodo")
    hinted = any(token in normalized for token in date_tokens)
    values = _non_null_values(data, column)
    return bool(values) and (hinted or all(_looks_temporal(value) for value in values))


def _column_roles(data: Sequence[Mapping[str, Any]]) -> tuple[list[str], list[str], list[str]]:
    columns = _columns(data)
    numeric = [column for column in columns if _is_numeric_column(data, column)]
    temporal = [column for column in columns if _is_temporal_column(data, column)]
    categorical = [column for column in columns if column not in numeric and column not in temporal]
    return categorical, temporal, numeric


def compatible_visualization_types(
    data: Sequence[Mapping[str, Any]],
) -> list[VisualizationType]:
    """Calculate renderable types from result shape and values."""
    available: list[VisualizationType] = ["table"]
    if not data:
        return available
    categorical, temporal, numeric = _column_roles(data)
    if categorical and numeric:
        available.append("bar")
    if temporal and numeric:
        available.append("line")
    if len(data) == 1 and numeric:
        available.append("metric")
    return [kind for kind in TYPE_ORDER if kind in available]


def _hinted_type(format_hint: str | None) -> VisualizationType | None:
    hint = (format_hint or "").casefold()
    aliases: tuple[tuple[VisualizationType, tuple[str, ...]], ...] = (
        ("bar", ("barra", "bar")),
        ("line", ("linha", "line", "tendência", "tendencia")),
        ("metric", ("métrica", "metrica", "metric", "kpi")),
        ("table", ("tabela", "table")),
    )
    return next((kind for kind, words in aliases if any(word in hint for word in words)), None)


def _proposal_type(proposal: Mapping[str, Any] | None) -> VisualizationType | None:
    raw_type = proposal.get("type") if proposal else None
    if raw_type in TYPE_ORDER:
        return cast(VisualizationType, raw_type)
    return None


def _proposal_columns_valid(
    proposal: Mapping[str, Any], columns: set[str], visual_type: VisualizationType
) -> bool:
    if visual_type == "table":
        return True
    x = proposal.get("x")
    y = proposal.get("y")
    group = proposal.get("group")
    references = {value for value in (x, group) if isinstance(value, str)}
    if isinstance(y, list):
        references.update(value for value in y if isinstance(value, str))
    return bool(references) and references.issubset(columns)


def _default_type(available: Sequence[VisualizationType]) -> VisualizationType:
    preference: tuple[VisualizationType, ...] = ("metric", "line", "bar", "table")
    for kind in preference:
        if kind in available:
            return kind
    return "table"


def normalize_visualization(
    data: Sequence[Mapping[str, Any]],
    proposal: Mapping[str, Any] | None = None,
    *,
    format_hint: str | None = None,
    default_title: str = "Resultado",
) -> Visualization:
    """Validate an LLM proposal and apply a deterministic table fallback."""
    rows = [dict(row) for row in data]
    available = compatible_visualization_types(rows)
    columns = set(_columns(rows))
    hinted = _hinted_type(format_hint)
    proposed = _proposal_type(proposal)
    invalid_proposal = bool(proposal) and (
        proposed is None
        or proposed not in available
        or not _proposal_columns_valid(proposal or {}, columns, proposed)
    )

    if hinted and hinted in available:
        selected = hinted
    elif invalid_proposal:
        selected = "table"
    elif proposed == "table" and len(available) > 1:
        # A generic model table is not an explicit user preference. Prefer the
        # shape-derived visual; callers can still select the table without a query.
        selected = _default_type(available)
    else:
        selected = proposed or _default_type(available)

    title = str((proposal or {}).get("title") or default_title)
    if selected == "table":
        return Visualization(type="table", title=title, available_types=available)

    categorical, temporal, numeric = _column_roles(rows)
    inferred_x = temporal[0] if selected == "line" else (categorical[0] if categorical else None)
    if selected == "metric":
        inferred_x = None
    x = (proposal or {}).get("x") if proposed == selected else inferred_x
    proposed_y = (proposal or {}).get("y") if proposed == selected else None
    y = proposed_y if isinstance(proposed_y, list) else [numeric[0]]
    group = (proposal or {}).get("group") if proposed == selected else None
    return Visualization(
        type=selected,
        title=title,
        x=x if isinstance(x, str) else inferred_x,
        y=[str(column) for column in y],
        group=group if isinstance(group, str) else None,
        available_types=available,
    )


class VisualizationRenderError(ValueError):
    """Raised when valid contract data still cannot be rendered."""


class ImageExportError(RuntimeError):
    """Raised when Kaleido cannot render a figure without hiding the answer."""


def visualization_for_type(
    data: Sequence[Mapping[str, Any]],
    selected_type: VisualizationType,
    *,
    title: str,
) -> Visualization:
    """Recompute axes locally when the user changes the available visual type."""
    visual = normalize_visualization(
        data,
        None,
        format_hint=selected_type,
        default_title=title,
    )
    if visual.type == "line":
        categorical, _, _ = _column_roles(data)
        if len(categorical) == 1:
            visual.group = categorical[0]
    return visual


def _series_for_group(
    data: Sequence[Mapping[str, Any]], group: str
) -> dict[str, list[Mapping[str, Any]]]:
    series: dict[str, list[Mapping[str, Any]]] = {}
    for row in data:
        series.setdefault(str(row.get(group) or "Sem grupo"), []).append(row)
    return series


def _temporal_key(value: Any) -> datetime:
    """Normalize recognized dates and months solely for ordering and duplicate checks."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    elif isinstance(value, str):
        candidate = value.strip()
        if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", candidate):
            candidate += "-01"
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError as exc:
            raise VisualizationRenderError(
                "O período não contém datas ou meses reconhecíveis."
            ) from exc
    else:
        raise VisualizationRenderError("O período não contém datas ou meses reconhecíveis.")
    return parsed.astimezone(UTC).replace(tzinfo=None) if parsed.tzinfo else parsed


def _line_series(
    rows: Sequence[Mapping[str, Any]], x_column: str, y_columns: Sequence[str], group: str | None
) -> dict[str, list[Mapping[str, Any]]]:
    """Sort final rows per series; ambiguous period/metric pairs cannot be drawn safely."""
    grouped = _series_for_group(rows, group) if group else {"": list(rows)}
    prepared: dict[str, list[Mapping[str, Any]]] = {}
    for group_name, group_rows in grouped.items():
        dated = sorted(group_rows, key=lambda row: _temporal_key(row.get(x_column)))
        seen: set[tuple[datetime, str]] = set()
        for row in dated:
            period = _temporal_key(row.get(x_column))
            for metric in y_columns:
                if row.get(metric) is None:
                    continue
                pair = (period, metric)
                if pair in seen:
                    raise VisualizationRenderError(
                        "Há mais de um valor para o mesmo período e série. "
                        "A consulta precisa retornar uma linha por período/série."
                    )
                seen.add(pair)
        prepared[group_name] = dated
    return prepared


def _value_label(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return ""
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    number = f"{value:,}" if isinstance(value, int) else f"{value:,.2f}".rstrip("0").rstrip(".")
    return number.replace(",", "_").replace(".", ",").replace("_", ".")


def build_plotly_figure(
    data: Sequence[Mapping[str, Any]],
    visualization: Visualization,
    *,
    dark: bool = False,
) -> go.Figure:
    """Build the single Plotly representation used on screen and for PNG export."""
    rows = [dict(row) for row in data]
    template = "plotly_dark" if dark else "plotly_white"
    figure = go.Figure()

    if visualization.type == "table":
        columns = _columns(rows)
        figure.add_trace(
            go.Table(
                header={"values": columns, "align": "left"},
                cells={
                    "values": [[row.get(column) for row in rows] for column in columns],
                    "align": "left",
                },
            )
        )
    elif visualization.type == "metric":
        metric_column = visualization.y[0] if visualization.y else None
        value = rows[0].get(metric_column) if rows and metric_column else None
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise VisualizationRenderError("A métrica não possui um valor numérico compatível.")
        figure.add_trace(
            go.Indicator(
                mode="number",
                value=value,
                title={"text": visualization.title},
            )
        )
    elif visualization.type in ("bar", "line"):
        x_column = visualization.x
        y_columns = visualization.y or []
        if not x_column or not y_columns:
            raise VisualizationRenderError("A visualização requer eixos x e y.")
        grouped = (
            _line_series(rows, x_column, y_columns, visualization.group)
            if visualization.type == "line"
            else _series_for_group(rows, visualization.group) if visualization.group else {"": rows}
        )
        for group_name, group_rows in grouped.items():
            for y_column in y_columns:
                series_rows = (
                    [row for row in group_rows if row.get(y_column) is not None]
                    if visualization.type == "line"
                    else group_rows
                )
                label_parts = [part for part in (group_name, y_column) if part]
                trace_args = {
                    "x": [row.get(x_column) for row in series_rows],
                    "y": [row.get(y_column) for row in series_rows],
                    "name": " · ".join(label_parts),
                    "text": [_value_label(row.get(y_column)) for row in series_rows],
                    "hovertemplate": (
                        f"{x_column}: %{{x}}<br>{y_column}: %{{y}}<extra>%{{fullData.name}}</extra>"
                    ),
                    "cliponaxis": False,
                }
                if visualization.type == "bar":
                    figure.add_trace(
                        go.Bar(**trace_args, texttemplate="%{text}", textposition="outside")
                    )
                else:
                    # Keep labels even in dense series; hover remains the precise view.
                    figure.add_trace(
                        go.Scatter(
                            **trace_args,
                            mode="lines+markers+text",
                            textposition="top center",
                        )
                    )
    else:
        raise VisualizationRenderError("Tipo de visualização não suportado.")

    figure.update_layout(
        template=template,
        title=None if visualization.type == "metric" else visualization.title,
        margin={"l": 48, "r": 32, "t": 80, "b": 56},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        hovermode="x unified" if visualization.type == "line" else "closest",
    )
    if visualization.type == "line":
        temporal_column = visualization.x
        if temporal_column is None:
            raise VisualizationRenderError("A visualização requer um eixo temporal.")
        figure.update_xaxes(type="date", automargin=True)
        if all(
            isinstance(row.get(temporal_column), str)
            and re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", row[temporal_column].strip())
            for row in rows
        ):
            figure.update_xaxes(tickformat="%Y-%m")
        figure.update_yaxes(automargin=True)
    elif visualization.type == "bar":
        figure.update_xaxes(automargin=True)
        figure.update_yaxes(automargin=True)
    return figure


def result_to_csv(data: Sequence[Mapping[str, Any]]) -> bytes:
    """Serialize result rows as UTF-8 CSV with stable column order."""
    rows = [dict(row) for row in data]
    columns = _columns(rows)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def figure_to_png(figure: go.Figure) -> bytes:
    """Render a high-density PNG with actionable, non-traceback diagnostics."""
    try:
        payload = figure.to_image(format="png", scale=2)
    except Exception as exc:
        chain: list[BaseException] = []
        current: BaseException | None = exc
        while current is not None and current not in chain:
            chain.append(current)
            current = current.__cause__ or current.__context__
        names = {type(error).__name__ for error in chain}
        messages = " ".join(str(error).casefold() for error in chain)
        if "ChromeNotFoundError" in names or "chrome not found" in messages:
            message = (
                "Chrome/Chromium não encontrado para exportar PNG. Instale-o com "
                "plotly_get_chrome ou kaleido_get_chrome; se necessário, configure BROWSER_PATH."
            )
        elif "BrowserFailedError" in names or "browser failed" in messages:
            message = (
                "Chrome/Chromium foi encontrado, mas não iniciou para exportar PNG. "
                "Verifique a instalação e as dependências do navegador; "
                "se necessário, configure BROWSER_PATH."
            )
        elif any(isinstance(error, ImportError) for error in chain) or "kaleido" in messages:
            message = "Kaleido não está instalado. Execute uv sync para habilitar a exportação PNG."
        else:
            message = (
                "Falha inesperada ao exportar PNG. O gráfico interativo continua disponível; "
                "verifique o ambiente do renderer."
            )
        raise ImageExportError(message) from exc
    if not isinstance(payload, bytes) or not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ImageExportError("O renderer de PNG retornou um arquivo inválido.")
    return payload
