"""OpenRouter boundary for all language-model behavior."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from typing import Any, Final

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from data_assistant.errors import (
    LLMOperationalError,
    MissingAPIKeyError,
    QuotaExceededError,
    classify_provider_error,
)
from data_assistant.quota import QuotaStore

# OpenRouter's free router selects an available free model that supports the
# capabilities requested by this application, including structured output.
DEFAULT_MODEL: Final = "openrouter/free"
DEFAULT_BASE_URL: Final = "https://openrouter.ai/api/v1"


class LLMResponseError(RuntimeError):
    """Raised when an LLM response cannot satisfy the requested contract."""


def resolve_model_name() -> str:
    """Return the effective OpenRouter model name shown and used at runtime."""
    return os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


@dataclass(frozen=True)
class LLMSettings:
    """Runtime configuration for the OpenAI-compatible OpenRouter client."""

    api_key: str
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = 30.0
    max_retries: int = 0

    @classmethod
    def from_environment(cls) -> LLMSettings:
        return cls(
            api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
            model=resolve_model_name(),
            base_url=os.getenv("OPENROUTER_BASE_URL", DEFAULT_BASE_URL).strip()
            or DEFAULT_BASE_URL,
            timeout_seconds=float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "30")),
            max_retries=0,
        )

    @classmethod
    def for_server_key(cls) -> LLMSettings:
        """Use the configured shared credential only with the free router."""
        return replace(cls.from_environment(), model=DEFAULT_MODEL, max_retries=0)

    @classmethod
    def for_session_key(cls, api_key: str) -> LLMSettings:
        """Build an isolated free-router client without changing process environment."""
        base = cls.from_environment()
        return replace(base, api_key=api_key.strip(), model=DEFAULT_MODEL, max_retries=0)

    def require_api_key(self) -> None:
        if not self.api_key:
            raise MissingAPIKeyError()


def _content_as_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        fragments: list[str] = []
        for block in content:
            if isinstance(block, str):
                fragments.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                fragments.append(block["text"])
        return "\n".join(fragments).strip()
    return str(content).strip()


def _decode_json_object(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        candidate = "\n".join(lines[1:-1]).strip()
    start, end = candidate.find("{"), candidate.rfind("}")
    if start < 0 or end < start:
        raise LLMResponseError("O modelo não retornou um objeto JSON")
    try:
        payload = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMResponseError(f"JSON inválido retornado pelo modelo: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise LLMResponseError("O modelo retornou JSON, mas não um objeto")
    return payload


class OpenRouterLLM:
    """Small adapter around ChatOpenAI for text and JSON completions."""

    def __init__(
        self,
        settings: LLMSettings | None = None,
        *,
        quota_store: QuotaStore | None = None,
        daily_limit: int = 45,
    ) -> None:
        self.settings = settings or LLMSettings.from_environment()
        self.settings.require_api_key()
        self._quota_store = quota_store
        self._daily_limit = daily_limit
        self._client = ChatOpenAI(
            api_key=SecretStr(self.settings.api_key),
            base_url=self.settings.base_url,
            model=self.settings.model,
            temperature=0,
            timeout=self.settings.timeout_seconds,
            # SDK retries include 429; every attempt must be explicitly reserved.
            max_retries=0,
        )

    def _reserve(self) -> None:
        if self._quota_store is not None:
            self._quota_store.acquire(self._daily_limit)

    def _classified_failure(self, exc: Exception) -> LLMOperationalError:
        failure = classify_provider_error(exc)
        if isinstance(failure, QuotaExceededError) and self._quota_store is not None:
            self._quota_store.mark_provider_exhausted()
        return failure

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self._reserve()
        try:
            response = self._client.invoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
            )
        except Exception as exc:
            failure = self._classified_failure(exc)
        else:
            text = _content_as_text(response.content)
            if not text:
                raise LLMResponseError("O modelo retornou uma resposta vazia")
            return text
        # Raise outside the handler so the SDK exception (which can contain credentials)
        # is never chained into the public error.
        raise failure

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        self._reserve()
        try:
            client = self._client.bind(response_format={"type": "json_object"})
            response = client.invoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
            )
        except Exception as exc:
            failure = self._classified_failure(exc)
        else:
            return _decode_json_object(_content_as_text(response.content))
        raise failure
