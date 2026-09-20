"""Pure agent nodes and typed state for the LangGraph workflow."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, TypedDict

from data_assistant.contract import AssistantAnswer
from data_assistant.prompts import (
    correct_sql_prompt,
    format_answer_prompt,
    generate_sql_prompt,
    interpretation_prompt,
    sufficiency_prompt,
)
from data_assistant.schema import SchemaSnapshot
from data_assistant.validator import SQLValidationError, validate_sql
from data_assistant.visualization import (
    compatible_visualization_types,
    normalize_visualization,
)


class LLMProtocol(Protocol):
    """The model operations consumed by nodes and replaced by fakes in tests."""

    def complete(self, system_prompt: str, user_prompt: str) -> str: ...

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]: ...


class QueryExecutorProtocol(Protocol):
    """The single query execution operation consumed by the graph."""

    def execute(self, sql: str) -> list[dict[str, object]]: ...


class AgentState(TypedDict):
    """Complete state shared by the LangGraph nodes."""

    question: str
    format_hint: str | None
    schema: str
    steps: list[dict[str, Any]]
    queries: list[str]
    last_sql: str
    last_result: list[dict[str, Any]] | None
    result_history: list[list[dict[str, Any]]]
    last_error: str | None
    sql_fix_attempts: int
    query_budget: int
    sufficient: bool
    interpretation: dict[str, Any]
    warnings: list[str]
    response: AssistantAnswer | None


@dataclass(frozen=True)
class GraphDependencies:
    """Side-effect boundaries injected into otherwise deterministic nodes."""

    llm: LLMProtocol
    executor: QueryExecutorProtocol
    schema_provider: Callable[[], SchemaSnapshot]
    max_sql_fix_attempts: int = 3
    max_query_budget: int = 6


def initial_state(
    question: str,
    format_hint: str | None = None,
    *,
    query_budget: int = 6,
) -> AgentState:
    """Create a complete initial state with bounded counters."""
    return AgentState(
        question=question,
        format_hint=format_hint,
        schema="",
        steps=[],
        queries=[],
        last_sql="",
        last_result=None,
        result_history=[],
        last_error=None,
        sql_fix_attempts=0,
        query_budget=query_budget,
        sufficient=False,
        interpretation={},
        warnings=[],
        response=None,
    )


def _copied(state: AgentState) -> AgentState:
    copy = AgentState(**state)
    copy["steps"] = list(state["steps"])
    copy["queries"] = list(state["queries"])
    copy["result_history"] = [list(result) for result in state["result_history"]]
    copy["warnings"] = list(state["warnings"])
    copy["interpretation"] = dict(state["interpretation"])
    return copy


def _record(state: AgentState, node: str, detail: str, **evidence: Any) -> None:
    state["steps"].append({"node": node, "detail": detail, **evidence})


def _strip_sql_fence(text: str) -> str:
    candidate = text.strip()
    match = re.fullmatch(r"```(?:sql)?\s*(.*?)\s*```", candidate, flags=re.I | re.S)
    return match.group(1).strip() if match else candidate


def interpret_node(state: AgentState, dependencies: GraphDependencies) -> AgentState:
    """Interpret intent without exposing internal reasoning."""
    updated = _copied(state)
    prompt = interpretation_prompt(state["question"], state["format_hint"])
    updated["interpretation"] = dependencies.llm.complete_json(prompt.system, prompt.user)
    _record(updated, "interpretar", "Pergunta e formato interpretados.")
    return updated


def discover_schema_node(state: AgentState, dependencies: GraphDependencies) -> AgentState:
    """Discover and serialize the runtime database schema."""
    updated = _copied(state)
    snapshot = dependencies.schema_provider()
    updated["schema"] = snapshot.to_dsl()
    _record(
        updated,
        "descobrir_schema",
        f"Schema descoberto em runtime: {len(snapshot.tables)} objeto(s).",
    )
    return updated


def generate_sql_node(state: AgentState, dependencies: GraphDependencies) -> AgentState:
    """Generate an initial SQL statement grounded in the discovered schema."""
    updated = _copied(state)
    prompt = generate_sql_prompt(
        state["question"],
        state["schema"],
        state["format_hint"],
        state["interpretation"],
    )
    updated["last_sql"] = _strip_sql_fence(
        dependencies.llm.complete(prompt.system, prompt.user)
    )
    updated["last_error"] = None
    _record(updated, "gerar_sql", "Consulta inicial gerada.", sql=updated["last_sql"])
    return updated


def validate_sql_node(state: AgentState, dependencies: GraphDependencies) -> AgentState:
    """Apply deterministic guardrails before any executor call."""
    del dependencies
    updated = _copied(state)
    try:
        updated["last_sql"] = validate_sql(state["last_sql"])
    except SQLValidationError as exc:
        updated["last_error"] = str(exc)
        _record(
            updated,
            "validar_sql",
            "Consulta rejeitada pelos guardrails.",
            sql=state["last_sql"],
            error=str(exc),
        )
    else:
        updated["last_error"] = None
        _record(updated, "validar_sql", "Consulta aprovada pelos guardrails.")
    return updated


def execute_sql_node(state: AgentState, dependencies: GraphDependencies) -> AgentState:
    """Execute one validated query and preserve SQLite's useful error message."""
    updated = _copied(state)
    if state["query_budget"] <= 0:
        budget_error = "Orçamento máximo de consultas esgotado."
        updated["last_error"] = budget_error
        _record(updated, "executar_sql", budget_error)
        return updated

    updated["query_budget"] = state["query_budget"] - 1
    updated["queries"].append(state["last_sql"])
    try:
        raw_rows = dependencies.executor.execute(state["last_sql"])
        rows = [dict(row) for row in raw_rows]
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        updated["last_result"] = None
        updated["last_error"] = error
        _record(
            updated,
            "executar_sql",
            "A consulta falhou e pode ser corrigida.",
            sql=state["last_sql"],
            error=error,
        )
    else:
        updated["last_result"] = rows
        updated["result_history"].append(rows)
        updated["last_error"] = None
        _record(
            updated,
            "executar_sql",
            f"Consulta executada: {len(rows)} linha(s).",
            sql=state["last_sql"],
            rows=rows[:20],
        )
    return updated


def correct_sql_node(state: AgentState, dependencies: GraphDependencies) -> AgentState:
    """Generate one corrected SQL statement using structured error feedback."""
    updated = _copied(state)
    prompt = correct_sql_prompt(
        state["question"],
        state["schema"],
        state["last_sql"],
        state["last_error"] or "Erro não especificado",
        state["last_result"],
    )
    updated["last_sql"] = _strip_sql_fence(
        dependencies.llm.complete(prompt.system, prompt.user)
    )
    updated["sql_fix_attempts"] = state["sql_fix_attempts"] + 1
    updated["last_error"] = None
    _record(
        updated,
        "corrigir_sql",
        f"Correção {updated['sql_fix_attempts']} gerada.",
        sql=updated["last_sql"],
    )
    return updated


def evaluate_sufficiency_node(state: AgentState, dependencies: GraphDependencies) -> AgentState:
    """Decide whether successful rows answer the question."""
    updated = _copied(state)
    result = state["last_result"] or []
    quantitative = any(
        token in state["question"].casefold()
        for token in ("quant", "média", "media", "total", "número", "numero")
    )
    if not result and quantitative:
        sufficient, reason = False, "Resultado vazio para uma pergunta quantitativa."
    else:
        prompt = sufficiency_prompt(state["question"], state["last_sql"], result)
        assessment = dependencies.llm.complete_json(prompt.system, prompt.user)
        sufficient = bool(assessment.get("sufficient"))
        reason = str(assessment.get("reason") or "Avaliação concluída.")
    updated["sufficient"] = sufficient
    _record(updated, "avaliar_suficiencia", reason, sufficient=sufficient)
    return updated


def refine_sql_node(state: AgentState, dependencies: GraphDependencies) -> AgentState:
    """Generate a complementary query without consuming correction attempts."""
    updated = _copied(state)
    prior_rows = [row for result in state["result_history"] for row in result[:20]]
    prompt = generate_sql_prompt(
        state["question"],
        state["schema"],
        state["format_hint"],
        state["interpretation"],
        prior_rows,
    )
    updated["last_sql"] = _strip_sql_fence(
        dependencies.llm.complete(prompt.system, prompt.user)
    )
    updated["last_error"] = None
    _record(updated, "refinar_consulta", "Consulta complementar gerada.", sql=updated["last_sql"])
    return updated


def _fallback_response(state: AgentState, status: str) -> str:
    if status == "error":
        return (
            "Não foi possível concluir a consulta dentro dos limites configurados. "
            "Revise a pergunta ou confira a conexão com o banco."
        )
    result = state["last_result"] or []
    if not result:
        return "Não foram encontrados registros que permitam responder à pergunta."
    return f"Consulta concluída com {len(result)} registro(s)."


def format_response_node(state: AgentState, dependencies: GraphDependencies) -> AgentState:
    """Build a validated answer, with deterministic output if formatting fails."""
    updated = _copied(state)
    result = state["last_result"] or []
    exhausted_with_error = bool(state["last_error"])
    if exhausted_with_error:
        status = "partial" if result else "error"
    elif not result:
        status = "empty"
    elif not state["sufficient"] and state["query_budget"] <= 0:
        status = "partial"
    else:
        status = "success"

    proposal: Mapping[str, Any] | None = None
    response_text = _fallback_response(state, status)
    if not exhausted_with_error:
        available_types = compatible_visualization_types(result)
        prompt = format_answer_prompt(
            state["question"],
            result,
            state["queries"],
            available_types,
            state["format_hint"],
        )
        try:
            payload = dependencies.llm.complete_json(prompt.system, prompt.user)
            response_text = str(payload.get("response") or response_text)
            raw_proposal = payload.get("visualization")
            proposal = raw_proposal if isinstance(raw_proposal, Mapping) else None
        except Exception:
            updated["warnings"].append(
                "A formatação automática falhou; foi aplicada uma apresentação determinística."
            )

    visualization = normalize_visualization(
        result,
        proposal,
        format_hint=state["format_hint"],
        default_title="Resultado da consulta",
    )
    _record(updated, "formatar_resposta", f"Resposta final preparada com status {status}.")
    updated["response"] = AssistantAnswer(
        status=status,  # type: ignore[arg-type]
        response=response_text,
        visualization=visualization,
        data=result,
        queries=updated["queries"],
        steps=updated["steps"],
        warnings=updated["warnings"],
    )
    return updated
