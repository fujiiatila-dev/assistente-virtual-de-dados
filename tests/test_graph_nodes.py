from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, NoReturn

from data_assistant.executor import SQLiteExecutor
from data_assistant.graph import (
    GraphDependencies,
    _needs_temporal_category_aggregation,
    discover_schema_node,
    evaluate_sufficiency_node,
    execute_sql_node,
    format_response_node,
    initial_state,
    refine_sql_node,
    route_after_execution,
    route_after_sufficiency,
    route_after_validation,
    validate_sql_node,
)
from data_assistant.schema import discover_schema


class UnexpectedLLM:
    """Fail if a node expected to be deterministic attempts to call an agent."""

    def complete(self, system_prompt: str, user_prompt: str) -> NoReturn:
        del system_prompt, user_prompt
        raise AssertionError("Este nó não deve chamar o agente")

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        del system_prompt, user_prompt
        raise AssertionError("Este nó não deve chamar o agente")


def _database(tmp_path: Path) -> Path:
    path = tmp_path / "agent.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE sales (id INTEGER PRIMARY KEY, channel TEXT, amount REAL);
        INSERT INTO sales (channel, amount) VALUES ('App', 10), ('Loja', 5);
        """
    )
    connection.close()
    return path


def _dependencies(path: Path) -> GraphDependencies:
    return GraphDependencies(
        llm=UnexpectedLLM(),
        executor=SQLiteExecutor(path),
        schema_provider=lambda: discover_schema(path),
    )


def test_deterministic_nodes_discover_validate_and_execute(tmp_path: Path) -> None:
    path = _database(tmp_path)
    dependencies = _dependencies(path)
    state = initial_state("Liste os canais")

    state = discover_schema_node(state, dependencies)
    assert 'TABLE "sales"' in state["schema"]

    # Direct input isolates the validator and executor; acceptance SQL comes from OpenRouter.
    state["last_sql"] = "SELECT channel, amount FROM sales ORDER BY id"
    state = validate_sql_node(state, dependencies)
    state = execute_sql_node(state, dependencies)

    assert state["last_error"] is None
    assert state["last_result"] == [
        {"channel": "App", "amount": 10.0},
        {"channel": "Loja", "amount": 5.0},
    ]
    assert state["query_budget"] == 5


def test_validation_failure_routes_to_bounded_correction_without_execution(tmp_path: Path) -> None:
    path = _database(tmp_path)
    dependencies = _dependencies(path)
    state = initial_state("Apague os dados")
    state["last_sql"] = "DELETE FROM sales"

    rejected = validate_sql_node(state, dependencies)

    assert "Somente consultas" in (rejected["last_error"] or "")
    assert rejected["queries"] == []
    assert route_after_validation(rejected) == "corrigir_sql"
    rejected["sql_fix_attempts"] = 3
    assert route_after_validation(rejected) == "formatar_resposta"


def test_execution_error_preserves_sqlite_feedback_for_agent_correction(tmp_path: Path) -> None:
    path = _database(tmp_path)
    dependencies = _dependencies(path)
    state = initial_state("Liste os dados")
    state["last_sql"] = "SELECT absent FROM sales"

    executed = execute_sql_node(state, dependencies)

    assert "no such column" in (executed["last_error"] or "")
    assert route_after_execution(executed) == "corrigir_sql"
    assert executed["queries"] == ["SELECT absent FROM sales"]


def test_empty_quantitative_result_is_insufficient_without_agent_call(tmp_path: Path) -> None:
    path = _database(tmp_path)
    dependencies = _dependencies(path)
    state = initial_state("Quantos clientes existem?")
    state["last_sql"] = "SELECT 1 WHERE 0"
    state["last_result"] = []

    evaluated = evaluate_sufficiency_node(state, dependencies)

    assert evaluated["sufficient"] is False
    assert route_after_sufficiency(evaluated) == "refinar_consulta"
    evaluated["query_budget"] = 0
    assert route_after_sufficiency(evaluated) == "formatar_resposta"


def test_exhausted_error_formats_operational_contract_without_agent_call(tmp_path: Path) -> None:
    path = _database(tmp_path)
    dependencies = _dependencies(path)
    state = initial_state("Pergunta impossível")
    state["last_error"] = "OperationalError: no such column"
    state["sql_fix_attempts"] = 3

    formatted = format_response_node(state, dependencies)

    assert formatted["response"] is not None
    assert formatted["response"].status == "error"
    assert "Traceback" not in formatted["response"].response


def test_response_and_figure_use_only_final_result_not_prior_query(tmp_path: Path) -> None:
    from data_assistant.visualization import build_plotly_figure

    state = initial_state("Mostre a tendência")
    state["last_result"] = [{"mes": "2025-02", "total": 2}, {"mes": "2025-01", "total": 1}]
    state["result_history"] = [[{"mes": "2024-01", "total": 999}]]
    state["last_error"] = "Limite de consultas atingido"
    answer = format_response_node(state, _dependencies(_database(tmp_path)))["response"]

    assert answer is not None
    assert answer.data == state["last_result"]
    assert answer.visualization.type == "line"
    figure = build_plotly_figure(answer.data, answer.visualization)
    assert figure.data[0].x == ("2025-01", "2025-02")
    assert "2024-01" not in str(figure.to_plotly_json())


def test_temporal_category_count_refines_detail_rows_into_grouped_sql(
    tmp_path: Path,
) -> None:
    path = tmp_path / "temporal-events.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE event_records (event_type TEXT, occurred_on TEXT);
        INSERT INTO event_records VALUES
            ('Compra', '2024-08-07'),
            ('Compra', '2024-08-07'),
            ('Compra', '2024-08-07'),
            ('Suporte', '2024-08-08');
        """
    )
    connection.close()

    class AggregationLLM:
        def complete(self, system_prompt: str, user_prompt: str) -> str:
            combined = f"{system_prompt}\n{user_prompt}"
            assert "COUNT(*)" in combined
            return (
                "SELECT event_type AS tipo, occurred_on AS data_registro, "
                "COUNT(*) AS quantidade FROM event_records "
                "GROUP BY event_type, occurred_on "
                "ORDER BY occurred_on, event_type"
            )

        def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
            del user_prompt
            if "sufficient" in system_prompt:
                return {"sufficient": True, "reason": "A quantidade está agregada."}
            return {
                "response": "A Compra teve três registros em 7 de agosto de 2024.",
                "visualization": {"type": "table", "title": "Registros por tipo e data"},
            }

    dependencies = GraphDependencies(
        llm=AggregationLLM(),
        executor=SQLiteExecutor(path),
        schema_provider=lambda: discover_schema(path),
    )
    state = initial_state("Quantos registros por tipo e data existem?")
    state["last_sql"] = "SELECT event_type, occurred_on FROM event_records"
    state = validate_sql_node(state, dependencies)
    state = execute_sql_node(state, dependencies)

    evaluated = evaluate_sufficiency_node(state, dependencies)
    assert evaluated["sufficient"] is False
    assert route_after_sufficiency(evaluated) == "refinar_consulta"

    refined = refine_sql_node(evaluated, dependencies)
    assert refined["aggregation_refinement_attempts"] == 1
    refined = validate_sql_node(refined, dependencies)
    aggregated = execute_sql_node(refined, dependencies)
    assert aggregated["last_result"] == [
        {"tipo": "Compra", "data_registro": "2024-08-07", "quantidade": 3},
        {"tipo": "Suporte", "data_registro": "2024-08-08", "quantidade": 1},
    ]

    final_check = evaluate_sufficiency_node(aggregated, dependencies)
    assert final_check["sufficient"] is True
    answer_state = format_response_node(final_check, dependencies)
    answer = answer_state["response"]
    assert answer is not None
    assert answer.data[0]["quantidade"] == 3


def test_temporal_category_count_never_exposes_raw_rows_when_budget_is_exhausted(
    tmp_path: Path,
) -> None:
    state = initial_state("Quantos registros por tipo e data existem?", query_budget=0)
    state["last_sql"] = "SELECT event_type, occurred_on FROM event_records"
    state["last_result"] = [
        {"tipo": "Compra", "data_registro": "2024-08-07"},
        {"tipo": "Compra", "data_registro": "2024-08-07"},
    ]

    formatted = format_response_node(state, _dependencies(_database(tmp_path)))
    answer = formatted["response"]

    assert answer is not None
    assert answer.status == "partial"
    assert answer.data == []
    assert any("não foi possível validar" in item for item in answer.warnings)
    assert all("rows" not in step for step in answer.steps)


def test_temporal_category_count_requires_count_and_both_dimensions_in_sql(
    tmp_path: Path,
) -> None:
    question = "Quantos registros por tipo e data existem?"
    grouped_rows = [
        {"tipo": "Compra", "data_registro": "2024-08-07", "quantidade": 3}
    ]

    assert _needs_temporal_category_aggregation(
        question,
        "SELECT tipo, data_registro, SUM(1) AS quantidade "
        "FROM registros GROUP BY tipo, data_registro",
        grouped_rows,
    )

    assert _needs_temporal_category_aggregation(
        question,
        "SELECT tipo, data_registro, COUNT(*) AS quantidade "
        "FROM registros GROUP BY tipo, data_registro, cliente_id",
        grouped_rows,
    )
    assert _needs_temporal_category_aggregation(
        question,
        "SELECT tipo, data_registro, COUNT(*) AS quantidade "
        "FROM registros GROUP BY cliente_id, data_registro",
        grouped_rows,
    )

    state = initial_state(question)
    state["last_sql"] = (
        "SELECT tipo, data_registro, SUM(1) AS quantidade "
        "FROM registros GROUP BY tipo, data_registro"
    )
    state["last_result"] = grouped_rows
    formatted = format_response_node(state, _dependencies(_database(tmp_path)))

    assert formatted["response"] is not None
    assert formatted["response"].data == []
    assert any("não foi possível validar" in warning for warning in formatted["warnings"])
