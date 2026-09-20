"""Deterministic visualization compatibility and fallback rules."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any, cast

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
