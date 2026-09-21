from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, NoReturn

from data_assistant.executor import SQLiteExecutor
from data_assistant.graph import (
    GraphDependencies,
    discover_schema_node,
    evaluate_sufficiency_node,
    execute_sql_node,
    format_response_node,
    initial_state,
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
