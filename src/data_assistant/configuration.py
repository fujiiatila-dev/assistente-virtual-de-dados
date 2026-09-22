"""Bounded, non-secret runtime limits for the public application."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _positive_limit(name: str, default: int, maximum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} deve ser um número inteiro positivo.") from exc
    if not 1 <= value <= maximum:
        raise ValueError(f"{name} deve estar entre 1 e {maximum}.")
    return value


@dataclass(frozen=True)
class PublicRuntimeSettings:
    """Limits shared across sessions; credentials stay in the LLM settings boundary."""

    free_daily_request_limit: int = 45
    quota_db_path: Path = Path("runtime/quota.sqlite3")
    max_question_chars: int = 2000
    max_concurrent_questions: int = 2
    app_requests_per_minute: int = 5

    @classmethod
    def from_environment(cls) -> PublicRuntimeSettings:
        quota_path = os.getenv("QUOTA_DB_PATH", "runtime/quota.sqlite3").strip()
        if not quota_path:
            raise ValueError("QUOTA_DB_PATH deve apontar para o ledger de runtime.")
        return cls(
            free_daily_request_limit=_positive_limit(
                "OPENROUTER_FREE_DAILY_REQUEST_LIMIT", 45, 10000
            ),
            quota_db_path=Path(quota_path).expanduser(),
            max_question_chars=_positive_limit("MAX_QUESTION_CHARS", 2000, 10000),
            max_concurrent_questions=_positive_limit("MAX_CONCURRENT_QUESTIONS", 2, 32),
            app_requests_per_minute=_positive_limit("APP_REQUESTS_PER_MINUTE", 5, 120),
        )
