from __future__ import annotations

from pathlib import Path

import pytest

from data_assistant.configuration import PublicRuntimeSettings


def test_public_runtime_defaults_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "OPENROUTER_FREE_DAILY_REQUEST_LIMIT",
        "QUOTA_DB_PATH",
        "MAX_QUESTION_CHARS",
        "MAX_CONCURRENT_QUESTIONS",
        "APP_REQUESTS_PER_MINUTE",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = PublicRuntimeSettings.from_environment()
    assert settings.free_daily_request_limit == 45
    assert settings.quota_db_path == Path("runtime/quota.sqlite3")
    assert settings.max_question_chars == 2000
    assert settings.max_concurrent_questions == 2
    assert settings.app_requests_per_minute == 5


def test_public_runtime_reads_explicit_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_FREE_DAILY_REQUEST_LIMIT", "12")
    monkeypatch.setenv("QUOTA_DB_PATH", "private/ledger.sqlite3")
    monkeypatch.setenv("MAX_QUESTION_CHARS", "500")
    monkeypatch.setenv("MAX_CONCURRENT_QUESTIONS", "3")
    monkeypatch.setenv("APP_REQUESTS_PER_MINUTE", "4")
    settings = PublicRuntimeSettings.from_environment()
    assert settings.free_daily_request_limit == 12
    assert settings.quota_db_path == Path("private/ledger.sqlite3")
    assert settings.max_question_chars == 500
    assert settings.max_concurrent_questions == 3
    assert settings.app_requests_per_minute == 4


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("OPENROUTER_FREE_DAILY_REQUEST_LIMIT", "0"),
        ("MAX_QUESTION_CHARS", "nope"),
        ("MAX_CONCURRENT_QUESTIONS", "100"),
        ("APP_REQUESTS_PER_MINUTE", "-1"),
        ("QUOTA_DB_PATH", " "),
    ],
)
def test_invalid_limits_fail_closed(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        PublicRuntimeSettings.from_environment()
