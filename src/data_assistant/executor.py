"""Bounded, read-only SQLite query execution."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Final

from sqlglot import exp, parse_one
from sqlglot.errors import ParseError

from data_assistant.execution import ExecutionCancelledError

DEFAULT_ROW_LIMIT: Final = 200
DEFAULT_TIMEOUT_SECONDS: Final = 10.0


class DatabaseNotFoundError(FileNotFoundError):
    """Raised before connecting so SQLite never creates a missing file."""


def _read_only_uri(path: Path) -> str:
    return f"{path.resolve().as_uri()}?mode=ro"


def _literal_limit(expression: exp.Query) -> int | None:
    limit = expression.args.get("limit")
    if not isinstance(limit, exp.Limit):
        return None
    value = limit.expression
    if isinstance(value, exp.Literal) and value.is_int:
        return int(value.this)
    return None


def enforce_row_limit(sql: str, maximum_rows: int = DEFAULT_ROW_LIMIT) -> str:
    """Add or cap a top-level SELECT limit using the SQLite SQL parser."""
    if maximum_rows <= 0:
        raise ValueError("maximum_rows deve ser maior que zero")
    try:
        expression = parse_one(sql, read="sqlite")
    except ParseError:
        # Let SQLite return its native syntax error to the correction loop.
        return sql

    if not isinstance(expression, exp.Query):
        return sql
    existing = _literal_limit(expression)
    if existing is not None and 0 <= existing <= maximum_rows:
        return expression.sql(dialect="sqlite")
    return expression.limit(maximum_rows, copy=True).sql(dialect="sqlite")


class SQLiteExecutor:
    """Execute one query against an immutable SQLite file."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        row_limit: int = DEFAULT_ROW_LIMIT,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.database_path = Path(database_path).expanduser()
        self.row_limit = row_limit
        self.timeout_seconds = timeout_seconds
        if row_limit <= 0:
            raise ValueError("row_limit deve ser maior que zero")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds deve ser maior que zero")

    def _connect(self) -> sqlite3.Connection:
        if not self.database_path.is_file():
            raise DatabaseNotFoundError(f"Arquivo SQLite não encontrado: {self.database_path}")
        connection = sqlite3.connect(
            _read_only_uri(self.database_path),
            uri=True,
            timeout=self.timeout_seconds,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def execute(
        self,
        sql: str,
        *,
        cancel_event: threading.Event | None = None,
    ) -> list[dict[str, object]]:
        """Execute SQL with a row cap and wall-clock timeout.

        SQLite exceptions intentionally retain their original message so the graph can
        provide precise feedback to the SQL correction prompt.
        """
        if cancel_event is not None and cancel_event.is_set():
            raise ExecutionCancelledError()
        bounded_sql = enforce_row_limit(sql, self.row_limit)
        connection = self._connect()
        deadline = time.monotonic() + self.timeout_seconds

        def interrupt_after_deadline() -> int:
            cancelled = cancel_event is not None and cancel_event.is_set()
            return int(cancelled or time.monotonic() >= deadline)

        connection.set_progress_handler(interrupt_after_deadline, 1_000)
        try:
            if cancel_event is not None and cancel_event.is_set():
                raise ExecutionCancelledError()
            cursor = connection.execute(bounded_sql)
            rows = cursor.fetchmany(self.row_limit + 1)
            if cancel_event is not None and cancel_event.is_set():
                raise ExecutionCancelledError()
            return [dict(row) for row in rows[: self.row_limit]]
        except sqlite3.OperationalError as exc:
            if cancel_event is not None and cancel_event.is_set():
                raise ExecutionCancelledError() from exc
            raise
        finally:
            connection.set_progress_handler(None, 0)
            connection.close()
