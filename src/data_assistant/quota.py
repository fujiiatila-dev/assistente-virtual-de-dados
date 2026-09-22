"""Atomic, aggregate-only daily budget for the shared OpenRouter credential."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from data_assistant.errors import QuotaExceededError


def _utc_day() -> date:
    return datetime.now(UTC).date()


@dataclass(frozen=True)
class QuotaSnapshot:
    day_utc: date
    used: int
    limit: int
    provider_exhausted: bool

    @property
    def remaining(self) -> int:
        return 0 if self.provider_exhausted else max(self.limit - self.used, 0)


class QuotaStore:
    """One SQLite counter shared safely by concurrent sessions and app processes."""

    def __init__(
        self,
        path: str | Path,
        *,
        source_database: str | Path | None = None,
        day_provider: Callable[[], date] = _utc_day,
    ) -> None:
        self.path = Path(path).expanduser().resolve()
        if source_database is not None and self.path == (
            Path(source_database).expanduser().resolve()
        ):
            raise ValueError("O ledger de quota deve ser separado do banco de dados de entrada.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._day_provider = day_provider
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS daily_usage ("
                "day_utc TEXT PRIMARY KEY, used INTEGER NOT NULL DEFAULT 0, "
                "provider_exhausted INTEGER NOT NULL DEFAULT 0)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def acquire(self, limit: int) -> QuotaSnapshot:
        """Reserve one attempt before transport; failure still consumes the unit."""
        if limit < 1:
            raise ValueError("O limite diário deve ser positivo.")
        today = self._day_provider()
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM daily_usage WHERE day_utc < ?",
                ((today - timedelta(days=7)).isoformat(),),
            )
            connection.execute(
                "INSERT OR IGNORE INTO daily_usage(day_utc, used, provider_exhausted) "
                "VALUES (?, 0, 0)",
                (today.isoformat(),),
            )
            row = connection.execute(
                "SELECT used, provider_exhausted FROM daily_usage WHERE day_utc = ?",
                (today.isoformat(),),
            ).fetchone()
            assert row is not None
            used, blocked = int(row[0]), bool(row[1])
            if blocked or used >= limit:
                raise QuotaExceededError()
            connection.execute(
                "UPDATE daily_usage SET used = used + 1 WHERE day_utc = ?",
                (today.isoformat(),),
            )
        return QuotaSnapshot(today, used + 1, limit, False)

    def mark_provider_exhausted(self) -> None:
        """Stop shared-key calls until the next UTC day after remote quota exhaustion."""
        today = self._day_provider().isoformat()
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO daily_usage(day_utc, used, provider_exhausted) VALUES (?, 0, 1) "
                "ON CONFLICT(day_utc) DO UPDATE SET provider_exhausted = 1",
                (today,),
            )

    def snapshot(self, limit: int) -> QuotaSnapshot:
        """Read only the aggregate state for the current UTC day."""
        today = self._day_provider()
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT used, provider_exhausted FROM daily_usage WHERE day_utc = ?",
                (today.isoformat(),),
            ).fetchone()
        return QuotaSnapshot(
            today, int(row[0]) if row else 0, limit, bool(row[1]) if row else False
        )
