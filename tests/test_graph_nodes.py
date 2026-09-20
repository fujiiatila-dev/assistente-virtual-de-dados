from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from data_assistant.executor import SQLiteExecutor
from data_assistant.graph import (
    GraphDependencies,
    correct_sql_node,
    discover_schema_node,
    evaluate_sufficiency_node,
    execute_sql_node,
    format_response_node,
    generate_sql_node,
    initial_state,
    interpret_node,
    refine_sql_node,
    validate_sql_node,
)
from data_assistant.schema import discover_schema


class FakeLLM:
    def __init__(
        self,
        *,
        texts: list[str] | None = None,
        payloads: list[dict[str, Any]] | None = None,
    ):
        self.texts = list(texts or [])
        self.payloads = list(payloads or [])

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        del system_prompt, user_prompt
        return self.texts.pop(0)

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        del system_prompt, user_prompt
        return self.payloads.pop(0)


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


def _dependencies(
    path: Path,
    llm: FakeLLM,
    executor_factory: Callable[[Path], SQLiteExecutor] = SQLiteExecutor,
) -> GraphDependencies:
    return GraphDependencies(
        llm=llm,
        executor=executor_factory(path),
        schema_provider=lambda: discover_schema(path),
    )


def test_nodes_interpret_discover_generate_validate_and_execute(tmp_path: Path) -> None:
    path = _database(tmp_path)
    llm = FakeLLM(
        payloads=[{"intent": "total"}],
        texts=["```sql\nSELECT COUNT(*) AS total FROM sales\n```"],
    )
    dependencies = _dependencies(path, llm)
    state = initial_state("Quantas vendas existem?")

    state = interpret_node(state, dependencies)
    state = discover_schema_node(state, dependencies)
    state = generate_sql_node(state, dependencies)
    state = validate_sql_node(state, dependencies)
    state = execute_sql_node(state, dependencies)

    assert state["interpretation"] == {"intent": "total"}
    assert 'TABLE "sales"' in state["schema"]
    assert state["last_sql"] == "SELECT COUNT(*) AS total FROM sales"
    assert state["last_result"] == [{"total": 2}]
    assert state["query_budget"] == 5
    assert [step["node"] for step in state["steps"]] == [
        "interpretar",
        "descobrir_schema",
        "gerar_sql",
        "validar_sql",
        "executar_sql",
    ]


def test_nodes_capture_validation_and_execution_errors_for_correction(tmp_path: Path) -> None:
    path = _database(tmp_path)
    llm = FakeLLM(texts=["SELECT absent FROM sales"])
    dependencies = _dependencies(path, llm)
    state = initial_state("Liste vendas")
    state["schema"] = discover_schema(path).to_dsl()
    state["last_sql"] = "DELETE FROM sales"

    rejected = validate_sql_node(state, dependencies)
    assert "Somente consultas" in (rejected["last_error"] or "")

    state["last_sql"] = "SELECT absent FROM sales"
    executed = execute_sql_node(state, dependencies)
    assert "no such column" in (executed["last_error"] or "")
    corrected = correct_sql_node(executed, dependencies)
    assert corrected["sql_fix_attempts"] == 1
    assert corrected["last_sql"] == "SELECT absent FROM sales"


def test_nodes_evaluate_refine_and_format(tmp_path: Path) -> None:
    path = _database(tmp_path)
    llm = FakeLLM(
        texts=["SELECT channel, SUM(amount) AS total FROM sales GROUP BY channel"],
        payloads=[
            {"sufficient": False, "reason": "Falta detalhar por canal."},
            {
                "response": "O App lidera com 10.",
                "visualization": {
                    "type": "bar",
                    "title": "Vendas por canal",
                    "x": "channel",
                    "y": ["total"],
                },
            },
        ],
    )
    dependencies = _dependencies(path, llm)
    state = initial_state("Qual canal lidera?", "barras")
    state["schema"] = discover_schema(path).to_dsl()
    state["last_sql"] = "SELECT * FROM sales"
    state["last_result"] = [{"id": 1, "channel": "App", "amount": 10.0}]
    state["result_history"] = [state["last_result"]]

    evaluated = evaluate_sufficiency_node(state, dependencies)
    assert evaluated["sufficient"] is False
    refined = refine_sql_node(evaluated, dependencies)
    assert refined["sql_fix_attempts"] == 0
    assert "GROUP BY channel" in refined["last_sql"]

    refined["last_result"] = [{"channel": "App", "total": 10.0}]
    refined["sufficient"] = True
    formatted = format_response_node(refined, dependencies)
    assert formatted["response"] is not None
    assert formatted["response"].status == "success"
    assert formatted["response"].visualization.type == "bar"
    assert formatted["response"].steps[-1]["node"] == "formatar_resposta"


def test_nodes_empty_quantitative_result_is_insufficient_without_llm(tmp_path: Path) -> None:
    path = _database(tmp_path)
    dependencies = _dependencies(path, FakeLLM())
    state = initial_state("Quantos clientes existem?")
    state["last_sql"] = "SELECT 1 WHERE 0"
    state["last_result"] = []

    evaluated = evaluate_sufficiency_node(state, dependencies)
    assert evaluated["sufficient"] is False
    assert evaluated["steps"][-1]["node"] == "avaliar_suficiencia"
