"""Versioned contract between the agent engine and the Streamlit frontend."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from data_assistant.errors import OperationalCode

VisualizationType = Literal["line", "bar", "table", "metric"]
AnswerStatus = Literal["success", "empty", "partial", "error", "cancelled"]


def _table_only() -> list[VisualizationType]:
    return ["table"]


class Visualization(BaseModel):
    """A validated visualization selected from the product's closed menu."""

    type: VisualizationType
    title: str
    x: str | None = None
    y: list[str] | None = None
    group: str | None = None
    available_types: list[VisualizationType] = Field(default_factory=_table_only)

    @model_validator(mode="after")
    def keep_available_types_consistent(self) -> Visualization:
        self.available_types = list(dict.fromkeys(self.available_types))
        if "table" not in self.available_types:
            self.available_types.insert(0, "table")
        if self.type not in self.available_types:
            self.type = "table"
            self.x = None
            self.y = None
            self.group = None
        return self


class AssistantAnswer(BaseModel):
    """Complete, renderable and auditable answer returned by the assistant."""

    status: AnswerStatus
    response: str
    visualization: Visualization
    data: list[dict[str, Any]] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    operational_code: OperationalCode | None = None

    @model_validator(mode="after")
    def fallback_when_columns_are_missing(self) -> AssistantAnswer:
        columns = {column for row in self.data for column in row}
        visual = self.visualization
        referenced = set(visual.y or [])
        if visual.x:
            referenced.add(visual.x)
        if visual.group:
            referenced.add(visual.group)
        if visual.type != "table" and (not referenced or not referenced.issubset(columns)):
            self.visualization = Visualization(
                type="table",
                title=visual.title,
                available_types=visual.available_types,
            )
            warning = "Visualização solicitada incompatível com as colunas; exibindo tabela."
            if warning not in self.warnings:
                self.warnings.append(warning)
        return self
