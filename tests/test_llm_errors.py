from __future__ import annotations

import pytest

from data_assistant.errors import (
    LLMOperationalError,
    MissingAPIKeyError,
    QuotaExceededError,
    classify_provider_error,
)


class FakeStatusError(Exception):
    def __init__(self, status_code: int, detail: str = "secret-token") -> None:
        self.status_code = status_code
        super().__init__(detail)


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (FakeStatusError(401), "invalid_key"),
        (FakeStatusError(402), "quota_exhausted"),
        (FakeStatusError(429, "daily quota secret-token"), "quota_exhausted"),
        (FakeStatusError(429), "rate_limited"),
        (FakeStatusError(503), "provider_unavailable"),
        (TimeoutError("secret-token"), "timeout"),
        (ConnectionError("secret-token"), "provider_unavailable"),
        (ValueError("secret-token"), "local_error"),
    ],
)
def test_provider_failures_are_typed_and_redacted(error: Exception, code: str) -> None:
    classified = classify_provider_error(error)
    assert classified.code == code
    assert "secret-token" not in str(classified)
    assert "Traceback" not in str(classified)


def test_local_missing_and_quota_errors_are_explicit() -> None:
    assert MissingAPIKeyError().code == "missing_key"
    assert QuotaExceededError().code == "quota_exhausted"
    assert isinstance(QuotaExceededError(), LLMOperationalError)
