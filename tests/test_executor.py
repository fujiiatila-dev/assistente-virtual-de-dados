from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

import pytest

from data_assistant.execution import ExecutionCancelledError
from data_assistant.executor import DatabaseNotFoundError, SQLiteExecutor, enforce_row_limit


@pytest.fixture
def executor_db(tmp_path: Path) -> Path:
    path = tmp_path / "dados com espaço.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE numbers (value INTEGER)")
    connection.executemany("INSERT INTO numbers VALUES (?)", [(index,) for index in range(300)])
    connection.commit()
    connection.close()
    return path


def test_executes_relative_and_absolute_windows_safe_paths(
    executor_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    absolute_rows = SQLiteExecutor(executor_db).execute("SELECT value FROM numbers ORDER BY value")
    assert len(absolute_rows) == 200
    assert absolute_rows[0] == {"value": 0}

    monkeypatch.chdir(executor_db.parent)
    relative_rows = SQLiteExecutor(Path(executor_db.name)).execute(
        "SELECT value FROM numbers ORDER BY value LIMIT 2"
    )
    assert relative_rows == [{"value": 0}, {"value": 1}]


def test_caps_an_excessive_limit(executor_db: Path) -> None:
    rows = SQLiteExecutor(executor_db, row_limit=10).execute("SELECT value FROM numbers LIMIT 999")
    assert len(rows) == 10


@pytest.mark.parametrize(
    ("sql", "expected_limit"),
    [
        ("SELECT value FROM numbers", 10),
        ("SELECT value FROM numbers LIMIT 0", 0),
        ("SELECT value FROM numbers LIMIT 5", 5),
        ("SELECT value FROM numbers LIMIT 10", 10),
        ("SELECT value FROM numbers LIMIT 999", 10),
        ("SELECT value FROM numbers LIMIT -1", 10),
        ("SELECT value FROM numbers LIMIT -20", 10),
    ],
)
def test_enforces_only_non_negative_limits_within_maximum(
    sql: str, expected_limit: int
) -> None:
    assert enforce_row_limit(sql, 10).endswith(f"LIMIT {expected_limit}")


def test_negative_limit_is_capped_before_execution(executor_db: Path) -> None:
    rows = SQLiteExecutor(executor_db, row_limit=10).execute(
        "SELECT value FROM numbers ORDER BY value LIMIT -1"
    )

    assert rows == [{"value": value} for value in range(10)]


def test_read_only_connection_rejects_writes(executor_db: Path) -> None:
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        SQLiteExecutor(executor_db).execute("DELETE FROM numbers")

    assert SQLiteExecutor(executor_db).execute("SELECT COUNT(*) AS total FROM numbers") == [
        {"total": 300}
    ]


def test_timeout_interrupts_expensive_query(executor_db: Path) -> None:
    sql = """
    WITH RECURSIVE counter(value) AS (
        SELECT 1
        UNION ALL
        SELECT value + 1 FROM counter WHERE value < 100000000
    )
    SELECT SUM(value) AS total FROM counter
    """
    with pytest.raises(sqlite3.OperationalError, match="interrupted"):
        SQLiteExecutor(executor_db, timeout_seconds=0.001).execute(sql)


def test_cancel_interrupts_sqlite_work_in_progress(
    executor_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = SQLiteExecutor(executor_db)
    cancel_event = threading.Event()
    query_started = threading.Event()
    release_query = threading.Event()
    errors: list[ExecutionCancelledError] = []
    original_connect = executor._connect

    def connect_with_blocking_function() -> sqlite3.Connection:
        connection = original_connect()

        def wait_inside_query() -> int:
            query_started.set()
            release_query.wait(2)
            return 1

        connection.create_function("wait_inside_query", 0, wait_inside_query)
        return connection

    monkeypatch.setattr(executor, "_connect", connect_with_blocking_function)

    def run_query() -> None:
        try:
            executor.execute("SELECT wait_inside_query()", cancel_event=cancel_event)
        except ExecutionCancelledError as exc:
            errors.append(exc)

    worker = threading.Thread(target=run_query)
    worker.start()
    assert query_started.wait(1)
    cancel_event.set()
    release_query.set()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert len(errors) == 1


def test_cancel_event_is_checked_by_sqlite_progress_handler(executor_db: Path) -> None:
    executor = SQLiteExecutor(executor_db, timeout_seconds=5)
    cancel_event = threading.Event()
    query_started = threading.Event()
    errors: list[ExecutionCancelledError] = []
    sql = """
    WITH RECURSIVE counter(value) AS (
        SELECT 1
        UNION ALL
        SELECT value + 1 FROM counter WHERE value < 100000000
    )
    SELECT SUM(value) AS total FROM counter
    """

    def run_query() -> None:
        query_started.set()
        try:
            executor.execute(sql, cancel_event=cancel_event)
        except ExecutionCancelledError as exc:
            errors.append(exc)

    worker = threading.Thread(target=run_query)
    started_at = time.monotonic()
    worker.start()
    assert query_started.wait(1)
    time.sleep(0.05)
    cancel_event.set()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert len(errors) == 1
    assert time.monotonic() - started_at < 2


def test_invalid_sql_preserves_sqlite_error(executor_db: Path) -> None:
    with pytest.raises(sqlite3.OperationalError, match="no such column"):
        SQLiteExecutor(executor_db).execute("SELECT absent FROM numbers")


def test_missing_path_is_not_created(tmp_path: Path) -> None:
    missing = tmp_path / "never-create.db"
    with pytest.raises(DatabaseNotFoundError, match="não encontrado"):
        SQLiteExecutor(missing).execute("SELECT 1")
    assert not missing.exists()
