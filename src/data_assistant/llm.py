"""OpenRouter boundary for all language-model behavior."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Final

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

DEFAULT_MODEL: Final = "google/gemini-2.5-flash"
DEFAULT_BASE_URL: Final = "https://openrouter.ai/api/v1"


class MissingAPIKeyError(RuntimeError):
    """Raised when OpenRouter cannot be called without its credential."""


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
    max_retries: int = 2

    @classmethod
    def from_environment(cls) -> LLMSettings:
        return cls(
            api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
            model=resolve_model_name(),
            base_url=os.getenv("OPENROUTER_BASE_URL", DEFAULT_BASE_URL).strip()
            or DEFAULT_BASE_URL,
            timeout_seconds=float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "30")),
            max_retries=int(os.getenv("OPENROUTER_MAX_RETRIES", "2")),
        )

    def require_api_key(self) -> None:
        if not self.api_key:
            raise MissingAPIKeyError(
                "OPENROUTER_API_KEY não configurada. Copie .env.example para .env "
                "e informe a chave."
            )


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

    def __init__(self, settings: LLMSettings | None = None) -> None:
        self.settings = settings or LLMSettings.from_environment()
        self.settings.require_api_key()
        self._client = ChatOpenAI(
            api_key=SecretStr(self.settings.api_key),
            base_url=self.settings.base_url,
            model=self.settings.model,
            temperature=0,
            timeout=self.settings.timeout_seconds,
            max_retries=self.settings.max_retries,
        )

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.invoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        )
        text = _content_as_text(response.content)
        if not text:
            raise LLMResponseError("O modelo retornou uma resposta vazia")
        return text

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        client = self._client.bind(response_format={"type": "json_object"})
        response = client.invoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        )
        return _decode_json_object(_content_as_text(response.content))
