"""Exercise mounted SQLite and the public graph without contacting a model provider."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from data_assistant.assistant import DataAssistant
from data_assistant.schema import discover_schema, quote_identifier


class DeterministicLLM:
    """Supply one runtime-schema-grounded query for container diagnostics only."""

    def __init__(self, sql: str) -> None:
        self.sql = sql
        self.json_calls = 0

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        del system_prompt, user_prompt
        return self.sql

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        del system_prompt, user_prompt
        self.json_calls += 1
        if self.json_calls == 1:
            return {
                "intent": "count",
                "metric": "rows",
                "dimensions": [],
                "time_scope": None,
                "format_hint": "table",
                "ambiguities": [],
            }
        if self.json_calls == 2:
            return {"sufficient": True, "reason": "Contagem encontrada."}
        return {
            "response": "Contagem verificada no banco montado.",
            "visualization": {"type": "table", "title": "Contagem"},
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    database: Path = args.db
    before = database.stat().st_mtime_ns
    tables = [table for table in discover_schema(database).tables if table.kind == "table"]
    if not tables:
        print("Falha: o banco não contém tabelas transacionais.")
        return 1
    sql = f"SELECT COUNT(*) AS total FROM {quote_identifier(tables[0].name)}"
    answer = DataAssistant(database, llm=DeterministicLLM(sql)).ask(
        "Quantos registros existem na primeira tabela?"
    )
    if (
        answer.status != "success"
        or answer.queries != [sql]
        or not answer.data
        or not isinstance(answer.data[0].get("total"), int)
        or database.stat().st_mtime_ns != before
    ):
        print(f"Falha: contrato inesperado ({answer.status}, {answer.operational_code}).")
        return 1
    print("OK: pergunta determinística, SQL read-only e resposta validada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
