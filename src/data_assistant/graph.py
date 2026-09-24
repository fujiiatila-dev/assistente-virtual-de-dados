"""Pure agent nodes and typed state for the LangGraph workflow."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlglot import exp, parse_one
from sqlglot.errors import ParseError

from data_assistant.contract import AssistantAnswer
from data_assistant.errors import LLMOperationalError, OperationalCode
from data_assistant.execution import (
    ExecutionCancelledError,
    ExecutionControl,
    PublicPhase,
)
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
    has_temporal_and_categorical_columns,
    normalize_visualization,
    temporal_and_categorical_columns,
)


class LLMProtocol(Protocol):
    """The model operations consumed by nodes and replaced by fakes in tests."""

    def complete(self, system_prompt: str, user_prompt: str) -> str: ...

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]: ...


class QueryExecutorProtocol(Protocol):
    """The single query execution operation consumed by the graph."""

    def execute(
        self,
        sql: str,
        *,
        cancel_event: threading.Event | None = None,
    ) -> list[dict[str, object]]: ...


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
    operational_error: OperationalCode | None
    aggregation_refinement_attempts: int
    response: AssistantAnswer | None


@dataclass(frozen=True)
class GraphDependencies:
    """Side-effect boundaries injected into otherwise deterministic nodes."""

    llm: LLMProtocol
    executor: QueryExecutorProtocol
    schema_provider: Callable[[], SchemaSnapshot]
    max_sql_fix_attempts: int = 3
    max_query_budget: int = 6
    execution_control: ExecutionControl | None = None


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
        operational_error=None,
        aggregation_refinement_attempts=0,
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


def _checkpoint(
    dependencies: GraphDependencies, phase: PublicPhase | None = None
) -> None:
    control = dependencies.execution_control
    if control is None:
        return
    control.checkpoint()
    if phase is not None:
        control.publish_progress(phase)


def _complete_text(
    dependencies: GraphDependencies, system_prompt: str, user_prompt: str
) -> str:
    def operation() -> str:
        return dependencies.llm.complete(system_prompt, user_prompt)

    if dependencies.execution_control is None:
        return operation()
    return dependencies.execution_control.call_provider(operation)


def _complete_json(
    dependencies: GraphDependencies, system_prompt: str, user_prompt: str
) -> dict[str, Any]:
    def operation() -> dict[str, Any]:
        return dependencies.llm.complete_json(system_prompt, user_prompt)

    if dependencies.execution_control is None:
        return operation()
    return dependencies.execution_control.call_provider(operation)


_COUNT_INTENT = re.compile(
    r"\b(?:quantos?|quantas?|quantidade|contagem|contar|total|n[uú]mero|qtd)\b",
    flags=re.IGNORECASE,
)


def _expression_key(expression: exp.Expression) -> str:
    """Normalize simple column references and compound SQL expressions."""
    if isinstance(expression, exp.Column):
        return f"column:{expression.name.casefold()}"
    return expression.sql(dialect="sqlite").casefold()


def _dimension_is_grouped(
    expression: exp.Select, group_expressions: list[exp.Expression], output_column: str
) -> bool:
    """Check that a visible time/category result maps to an actual GROUP BY term."""
    for selected in expression.expressions:
        if str(selected.alias_or_name).casefold() != output_column.casefold():
            continue
        selected_value = selected.this if isinstance(selected, exp.Alias) else selected
        selected_key = _expression_key(selected_value)
        for grouped in group_expressions:
            if (
                isinstance(grouped, exp.Column)
                and grouped.name.casefold() == output_column.casefold()
            ) or _expression_key(grouped) == selected_key:
                return True
    return False


def _needs_temporal_category_aggregation(
    question: str, sql: str, rows: list[dict[str, Any]] | None
) -> bool:
    """Reject detail rows when a quantitative question asks for time/category groups."""
    if not rows or not _COUNT_INTENT.search(question):
        return False
    if not has_temporal_and_categorical_columns(rows):
        return False
    try:
        expression = parse_one(sql, read="sqlite")
    except ParseError:
        return True
    if not isinstance(expression, exp.Select):
        return True
    group = expression.args.get("group")
    group_expressions = group.expressions if isinstance(group, exp.Group) else []
    selects_count = any(
        selected.find(exp.Count) is not None for selected in expression.expressions
    )
    categorical_columns, temporal_columns = temporal_and_categorical_columns(rows)
    grouped_dimensions_are_visible = bool(categorical_columns and temporal_columns)
    grouped_dimensions_are_valid = (
        grouped_dimensions_are_visible
        and _dimension_is_grouped(expression, group_expressions, categorical_columns[0])
        and _dimension_is_grouped(expression, group_expressions, temporal_columns[0])
    )
    return not (
        selects_count
        and len(group_expressions) == 2
        and grouped_dimensions_are_valid
    )


def interpret_node(state: AgentState, dependencies: GraphDependencies) -> AgentState:
    """Interpret intent without exposing internal reasoning."""
    _checkpoint(dependencies, PublicPhase.UNDERSTANDING)
    updated = _copied(state)
    prompt = interpretation_prompt(state["question"], state["format_hint"])
    updated["interpretation"] = _complete_json(dependencies, prompt.system, prompt.user)
    _record(updated, "interpretar", "Pergunta e formato interpretados.")
    return updated


def discover_schema_node(state: AgentState, dependencies: GraphDependencies) -> AgentState:
    """Discover and serialize the runtime database schema."""
    _checkpoint(dependencies, PublicPhase.SCHEMA)
    updated = _copied(state)
    snapshot = dependencies.schema_provider()
    _checkpoint(dependencies)
    updated["schema"] = snapshot.to_dsl()
    _record(
        updated,
        "descobrir_schema",
        f"Schema descoberto em runtime: {len(snapshot.tables)} objeto(s).",
    )
    return updated


def generate_sql_node(state: AgentState, dependencies: GraphDependencies) -> AgentState:
    """Generate an initial SQL statement grounded in the discovered schema."""
    _checkpoint(dependencies, PublicPhase.VALIDATING)
    updated = _copied(state)
    prompt = generate_sql_prompt(
        state["question"],
        state["schema"],
        state["format_hint"],
        state["interpretation"],
    )
    updated["last_sql"] = _strip_sql_fence(
        _complete_text(dependencies, prompt.system, prompt.user)
    )
    updated["last_error"] = None
    _record(updated, "gerar_sql", "Consulta inicial gerada.", sql=updated["last_sql"])
    return updated


def validate_sql_node(state: AgentState, dependencies: GraphDependencies) -> AgentState:
    """Apply deterministic guardrails before any executor call."""
    _checkpoint(dependencies, PublicPhase.VALIDATING)
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
    _checkpoint(dependencies, PublicPhase.QUERYING)
    updated = _copied(state)
    if state["query_budget"] <= 0:
        budget_error = "Orçamento máximo de consultas esgotado."
        updated["last_error"] = budget_error
        _record(updated, "executar_sql", budget_error)
        return updated

    updated["query_budget"] = state["query_budget"] - 1
    updated["queries"].append(state["last_sql"])
    try:
        if dependencies.execution_control is None:
            raw_rows = dependencies.executor.execute(state["last_sql"])
        else:
            raw_rows = dependencies.executor.execute(
                state["last_sql"],
                cancel_event=dependencies.execution_control.cancel_event,
            )
        rows = [dict(row) for row in raw_rows]
    except ExecutionCancelledError:
        if dependencies.execution_control is not None:
            dependencies.execution_control.checkpoint()
        raise
    except Exception as exc:
        if dependencies.execution_control is not None:
            dependencies.execution_control.checkpoint()
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
        _checkpoint(dependencies)
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
    _checkpoint(dependencies, PublicPhase.VALIDATING)
    updated = _copied(state)
    prompt = correct_sql_prompt(
        state["question"],
        state["schema"],
        state["last_sql"],
        state["last_error"] or "Erro não especificado",
        state["last_result"],
    )
    updated["last_sql"] = _strip_sql_fence(
        _complete_text(dependencies, prompt.system, prompt.user)
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
    _checkpoint(dependencies, PublicPhase.CHECKING)
    updated = _copied(state)
    result = state["last_result"] or []
    if _needs_temporal_category_aggregation(
        state["question"], state["last_sql"], state["last_result"]
    ):
        updated["sufficient"] = False
        _record(
            updated,
            "avaliar_suficiencia",
            "A contagem por período e categoria requer uma consulta agregada.",
            sufficient=False,
        )
        return updated
    quantitative = any(
        token in state["question"].casefold()
        for token in ("quant", "média", "media", "total", "número", "numero")
    )
    if not result and quantitative:
        sufficient, reason = False, "Resultado vazio para uma pergunta quantitativa."
    else:
        prompt = sufficiency_prompt(state["question"], state["last_sql"], result)
        try:
            assessment = _complete_json(dependencies, prompt.system, prompt.user)
        except LLMOperationalError as exc:
            updated["operational_error"] = exc.code
            updated["warnings"].append(str(exc))
            _record(updated, "avaliar_suficiencia", "Avaliação interrompida pelo provedor.")
            return updated
        sufficient = bool(assessment.get("sufficient"))
        reason = str(assessment.get("reason") or "Avaliação concluída.")
    updated["sufficient"] = sufficient
    _record(updated, "avaliar_suficiencia", reason, sufficient=sufficient)
    return updated


def refine_sql_node(state: AgentState, dependencies: GraphDependencies) -> AgentState:
    """Generate a complementary query without consuming correction attempts."""
    _checkpoint(dependencies, PublicPhase.CHECKING)
    updated = _copied(state)
    prior_rows = [row for result in state["result_history"] for row in result[:20]]
    prompt = generate_sql_prompt(
        state["question"],
        state["schema"],
        state["format_hint"],
        state["interpretation"],
        prior_rows,
    )
    try:
        updated["last_sql"] = _strip_sql_fence(
            _complete_text(dependencies, prompt.system, prompt.user)
        )
    except LLMOperationalError as exc:
        updated["operational_error"] = exc.code
        updated["warnings"].append(str(exc))
        _record(updated, "refinar_consulta", "Refinamento interrompido pelo provedor.")
        return updated
    if _needs_temporal_category_aggregation(
        state["question"], state["last_sql"], state["last_result"]
    ):
        updated["aggregation_refinement_attempts"] += 1
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
    _checkpoint(dependencies, PublicPhase.FORMATTING)
    updated = _copied(state)
    aggregation_missing = _needs_temporal_category_aggregation(
        state["question"], state["last_sql"], state["last_result"]
    )
    result = [] if aggregation_missing else (state["last_result"] or [])
    if aggregation_missing:
        warning = (
            "A consulta trouxe registros individuais e não foi possível validar uma "
            "contagem agrupada por período e categoria. As linhas individuais foram "
            "ocultadas; ajuste a pergunta ou tente novamente."
        )
        if warning not in updated["warnings"]:
            updated["warnings"].append(warning)
        updated["steps"] = [
            {key: value for key, value in step.items() if key != "rows"}
            for step in updated["steps"]
        ]
    exhausted_with_error = bool(state["last_error"])
    if aggregation_missing:
        status = "partial"
    elif state["operational_error"] or exhausted_with_error:
        status = "partial" if result else "error"
    elif not state["sufficient"] and state["query_budget"] <= 0:
        status = "partial"
    elif not result:
        status = "empty"
    else:
        status = "success"

    proposal: Mapping[str, Any] | None = None
    response_text = (
        "Não foi possível preparar a quantidade solicitada por período e categoria. "
        "A consulta trouxe registros individuais e a agregação precisa ser refeita."
        if aggregation_missing
        else _fallback_response(state, status)
    )
    if not aggregation_missing and not exhausted_with_error and not state["operational_error"]:
        available_types = compatible_visualization_types(result)
        prompt = format_answer_prompt(
            state["question"],
            result,
            state["queries"],
            available_types,
            state["format_hint"],
        )
        try:
            payload = _complete_json(dependencies, prompt.system, prompt.user)
            response_text = str(payload.get("response") or response_text)
            raw_proposal = payload.get("visualization")
            proposal = raw_proposal if isinstance(raw_proposal, Mapping) else None
        except LLMOperationalError as exc:
            updated["operational_error"] = exc.code
            updated["warnings"].append(str(exc))
            status = "partial" if result else "error"
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
    _checkpoint(dependencies)
    updated["response"] = AssistantAnswer(
        status=status,  # type: ignore[arg-type]
        response=response_text,
        visualization=visualization,
        data=result,
        queries=updated["queries"],
        steps=updated["steps"],
        warnings=updated["warnings"],
        operational_code=updated["operational_error"],
    )
    _checkpoint(dependencies)
    return updated


ValidationRoute = Literal["executar_sql", "corrigir_sql", "formatar_resposta"]
ExecutionRoute = Literal["corrigir_sql", "avaliar_suficiencia", "formatar_resposta"]
SufficiencyRoute = Literal["refinar_consulta", "formatar_resposta"]


def route_after_validation(state: AgentState, *, max_fix_attempts: int = 3) -> ValidationRoute:
    """Route safe SQL to execution and rejected SQL through the bounded correction loop."""
    if state["query_budget"] <= 0:
        return "formatar_resposta"
    if state["last_error"]:
        if state["sql_fix_attempts"] < max_fix_attempts:
            return "corrigir_sql"
        return "formatar_resposta"
    return "executar_sql"


def route_after_execution(state: AgentState, *, max_fix_attempts: int = 3) -> ExecutionRoute:
    """Separate execution failures from successful results."""
    if state["last_error"]:
        if state["sql_fix_attempts"] < max_fix_attempts and state["query_budget"] > 0:
            return "corrigir_sql"
        return "formatar_resposta"
    return "avaliar_suficiencia"


def route_after_sufficiency(state: AgentState) -> SufficiencyRoute:
    """Refine successful but insufficient results while budget remains."""
    if state["operational_error"] or state["sufficient"] or state["query_budget"] <= 0:
        return "formatar_resposta"
    if (
        state["aggregation_refinement_attempts"] >= 1
        and _needs_temporal_category_aggregation(
            state["question"], state["last_sql"], state["last_result"]
        )
    ):
        return "formatar_resposta"
    return "refinar_consulta"


def route_after_refinement(state: AgentState) -> Literal["validar_sql", "formatar_resposta"]:
    return "formatar_resposta" if state["operational_error"] else "validar_sql"


def build_graph(
    dependencies: GraphDependencies,
) -> CompiledStateGraph[AgentState, None, AgentState, AgentState]:
    """Compile the complete correction/refinement workflow."""
    workflow = StateGraph(AgentState)
    workflow.add_node("interpretar", lambda state: interpret_node(state, dependencies))
    workflow.add_node(
        "descobrir_schema", lambda state: discover_schema_node(state, dependencies)
    )
    workflow.add_node("gerar_sql", lambda state: generate_sql_node(state, dependencies))
    workflow.add_node("validar_sql", lambda state: validate_sql_node(state, dependencies))
    workflow.add_node("executar_sql", lambda state: execute_sql_node(state, dependencies))
    workflow.add_node("corrigir_sql", lambda state: correct_sql_node(state, dependencies))
    workflow.add_node(
        "avaliar_suficiencia", lambda state: evaluate_sufficiency_node(state, dependencies)
    )
    workflow.add_node("refinar_consulta", lambda state: refine_sql_node(state, dependencies))
    workflow.add_node(
        "formatar_resposta", lambda state: format_response_node(state, dependencies)
    )

    workflow.add_edge(START, "interpretar")
    workflow.add_edge("interpretar", "descobrir_schema")
    workflow.add_edge("descobrir_schema", "gerar_sql")
    workflow.add_edge("gerar_sql", "validar_sql")
    workflow.add_conditional_edges(
        "validar_sql",
        lambda state: route_after_validation(
            state, max_fix_attempts=dependencies.max_sql_fix_attempts
        ),
    )
    workflow.add_conditional_edges(
        "executar_sql",
        lambda state: route_after_execution(
            state, max_fix_attempts=dependencies.max_sql_fix_attempts
        ),
    )
    workflow.add_edge("corrigir_sql", "validar_sql")
    workflow.add_conditional_edges("avaliar_suficiencia", route_after_sufficiency)
    workflow.add_conditional_edges("refinar_consulta", route_after_refinement)
    workflow.add_edge("formatar_resposta", END)
    return workflow.compile(name="data-assistant")
