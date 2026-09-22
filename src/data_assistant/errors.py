"""Safe public error taxonomy for LLM and local execution failures."""

from __future__ import annotations

from typing import Literal

OperationalCode = Literal[
    "missing_key",
    "invalid_key",
    "quota_exhausted",
    "rate_limited",
    "provider_unavailable",
    "timeout",
    "local_error",
]

PUBLIC_MESSAGES: dict[OperationalCode, str] = {
    "missing_key": (
        "OPENROUTER_API_KEY não configurada. O servidor precisa de uma chave para iniciar."
    ),
    "invalid_key": "A chave OpenRouter foi rejeitada. Confira a chave informada nesta sessão.",
    "quota_exhausted": (
        "A cota gratuita compartilhada foi esgotada. Você pode continuar com uma chave própria."
    ),
    "rate_limited": "O provedor limitou as chamadas por enquanto. Aguarde e tente novamente.",
    "provider_unavailable": "O provedor de IA está indisponível. Tente novamente mais tarde.",
    "timeout": "O provedor demorou além do limite. Tente novamente mais tarde.",
    "local_error": "Não foi possível concluir a análise. Confira a fonte e tente novamente.",
}


class LLMOperationalError(RuntimeError):
    """A classified failure whose public string never includes provider payloads."""

    def __init__(self, code: OperationalCode) -> None:
        self.code = code
        super().__init__(PUBLIC_MESSAGES[code])


class MissingAPIKeyError(LLMOperationalError):
    """The configured server/session OpenRouter credential is absent."""

    def __init__(self) -> None:
        super().__init__("missing_key")


class QuotaExceededError(LLMOperationalError):
    """A local reservation or remote free quota rejected a new model attempt."""

    def __init__(self) -> None:
        super().__init__("quota_exhausted")


def classify_provider_error(exc: Exception) -> LLMOperationalError:
    """Map SDK failures without copying exception text or request details to the UI."""
    if isinstance(exc, LLMOperationalError):
        return exc
    status_code = getattr(exc, "status_code", None)
    if status_code == 401 or status_code == 403:
        return LLMOperationalError("invalid_key")
    if status_code == 402:
        return QuotaExceededError()
    if status_code == 429:
        detail = str(exc).casefold()
        if any(token in detail for token in ("daily", "quota", "credit", "free limit")):
            return QuotaExceededError()
        return LLMOperationalError("rate_limited")
    if isinstance(status_code, int) and status_code >= 500:
        return LLMOperationalError("provider_unavailable")
    if "timeout" in type(exc).__name__.casefold():
        return LLMOperationalError("timeout")
    if "connection" in type(exc).__name__.casefold():
        return LLMOperationalError("provider_unavailable")
    return LLMOperationalError("local_error")
