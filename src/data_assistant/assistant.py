"""Public orchestration API for the data assistant."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from data_assistant.contract import AssistantAnswer, Visualization
from data_assistant.executor import SQLiteExecutor
from data_assistant.graph import GraphDependencies, LLMProtocol, build_graph, initial_state
from data_assistant.llm import MissingAPIKeyError, OpenRouterLLM
from data_assistant.schema import SchemaCache, SchemaDiscoveryError, discover_schema

DEFAULT_DATABASE_PATH = Path("../anexo_desafio_1.db")
MAX_ALLOWED_FIX_ATTEMPTS = 3
MAX_ALLOWED_QUERY_BUDGET = 6

logger = logging.getLogger(__name__)


def resolve_database_path(runtime_db: str | Path | None = None) -> Path:
    """Resolve runtime DB, then DB/DB_PATH environment variables, then the local default."""
    if runtime_db is not None and str(runtime_db).strip():
        return Path(runtime_db).expanduser()
    configured = os.getenv("DB", "").strip() or os.getenv("DB_PATH", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_DATABASE_PATH


def _bounded_environment_int(name: str, default: int, maximum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return min(max(value, 1), maximum)


def _error_answer(message: str, *, warning: str | None = None) -> AssistantAnswer:
    return AssistantAnswer(
        status="error",
        response=message,
        visualization=Visualization(
            type="table",
            title="Consulta não executada",
            available_types=["table"],
        ),
        warnings=[warning] if warning else [],
    )


class DataAssistant:
    """Session-scoped assistant backed by the configured OpenRouter model."""

    def __init__(
        self,
        database_path: str | Path | None = None,
        *,
        llm: LLMProtocol | None = None,
        schema_cache: SchemaCache | None = None,
    ) -> None:
        load_dotenv()
        self.database_path = resolve_database_path(database_path)
        self._llm = llm
        self.schema_cache = schema_cache or SchemaCache()
        self.max_sql_fix_attempts = _bounded_environment_int(
            "MAX_SQL_FIX_ATTEMPTS", 3, MAX_ALLOWED_FIX_ATTEMPTS
        )
        self.max_query_budget = _bounded_environment_int(
            "MAX_QUERY_BUDGET", 6, MAX_ALLOWED_QUERY_BUDGET
        )

    def _model(self) -> LLMProtocol:
        if self._llm is None:
            self._llm = OpenRouterLLM()
        return self._llm

    def ask(self, question: str, format_hint: str | None = None) -> AssistantAnswer:
        """Run one bounded graph execution and always return the public contract."""
        if not question.strip():
            return _error_answer("Informe uma pergunta sobre os dados para iniciar a análise.")
        if not self.database_path.is_file():
            return _error_answer(
                f"Banco SQLite não encontrado em: {self.database_path}",
                warning="Configure DB_PATH ou informe o parâmetro DB com um arquivo existente.",
            )

        try:
            # Validate and cache the source before spending a model call.
            discover_schema(self.database_path, self.schema_cache)
            dependencies = GraphDependencies(
                llm=self._model(),
                executor=SQLiteExecutor(self.database_path),
                schema_provider=lambda: discover_schema(self.database_path, self.schema_cache),
                max_sql_fix_attempts=self.max_sql_fix_attempts,
                max_query_budget=self.max_query_budget,
            )
            result = build_graph(dependencies).invoke(
                initial_state(
                    question.strip(),
                    format_hint,
                    query_budget=self.max_query_budget,
                )
            )
            answer = result.get("response")
            if not isinstance(answer, AssistantAnswer):
                return _error_answer("O fluxo terminou sem produzir uma resposta válida.")
            return answer
        except MissingAPIKeyError as exc:
            return _error_answer(str(exc))
        except SchemaDiscoveryError as exc:
            return _error_answer(
                str(exc),
                warning="Confirme se DB aponta para um arquivo SQLite legível.",
            )
        except Exception as exc:
            logger.error("Falha operacional no grafo: %s", type(exc).__name__)
            return _error_answer(
                "Não foi possível processar a pergunta. Confira o banco, a chave do modelo "
                "e tente novamente."
            )


def ask(
    question: str,
    format_hint: str | None = None,
    *,
    database_path: str | Path | None = None,
) -> AssistantAnswer:
    """Convenience API for callers that do not need an explicit session object."""
    return DataAssistant(database_path).ask(question, format_hint)
