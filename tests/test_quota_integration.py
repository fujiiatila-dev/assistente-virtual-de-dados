from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest

from data_assistant.errors import LLMOperationalError, QuotaExceededError
from data_assistant.graph import (
    GraphDependencies,
    evaluate_sufficiency_node,
    format_response_node,
    initial_state,
    refine_sql_node,
    route_after_refinement,
    route_after_sufficiency,
)
from data_assistant.llm import LLMSettings, OpenRouterLLM
from data_assistant.quota import QuotaStore


class FakeResponse:
    content = '{"sufficient": true, "reason": "ok"}'


class FakeChatClient:
    calls = 0
    retries: ClassVar[list[int]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.retries.append(kwargs["max_retries"])

    def bind(self, **kwargs: Any) -> FakeChatClient:
        return self

    def invoke(self, messages: Any) -> FakeResponse:
        del messages
        type(self).calls += 1
        return FakeResponse()


def test_shared_budget_counts_each_completion_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    FakeChatClient.calls = 0
    FakeChatClient.retries = []
    monkeypatch.setattr("data_assistant.llm.ChatOpenAI", FakeChatClient)
    store = QuotaStore(tmp_path / "quota.sqlite3")
    llm = OpenRouterLLM(
        LLMSettings(api_key="test-placeholder"), quota_store=store, daily_limit=2
    )

    llm.complete("sistema", "pergunta")
    llm.complete_json("sistema", "pergunta")
    with pytest.raises(QuotaExceededError):
        llm.complete("sistema", "pergunta")

    assert FakeChatClient.calls == 2
    assert FakeChatClient.retries == [0]
    assert store.snapshot(2).used == 2


def test_graph_preserves_last_valid_rows_when_quota_hits_sufficiency() -> None:
    class ExhaustedLLM:
        def complete(self, system_prompt: str, user_prompt: str) -> str:
            raise AssertionError("Nova geração não deve ocorrer")

        def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
            raise QuotaExceededError()

    dependencies = GraphDependencies(
        llm=ExhaustedLLM(),
        executor=None,  # type: ignore[arg-type]
        schema_provider=lambda: None,  # type: ignore[arg-type,return-value]
    )
    state = initial_state("Mostre as vendas")
    state["last_sql"] = "SELECT 1"
    state["last_result"] = [{"mes": "2025-01", "total": 1}]
    state["queries"] = ["SELECT 1"]

    evaluated = evaluate_sufficiency_node(state, dependencies)
    assert route_after_sufficiency(evaluated) == "formatar_resposta"
    answer = format_response_node(evaluated, dependencies)["response"]

    assert answer is not None
    assert answer.status == "partial"
    assert answer.operational_code == "quota_exhausted"
    assert answer.data == state["last_result"]
    assert "Traceback" not in answer.response


def test_provider_secret_is_not_chained_into_public_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Unauthorized(Exception):
        status_code = 401

    class RejectingClient(FakeChatClient):
        def invoke(self, messages: Any) -> FakeResponse:
            del messages
            raise Unauthorized("visitor-secret")

    monkeypatch.setattr("data_assistant.llm.ChatOpenAI", RejectingClient)
    llm = OpenRouterLLM(LLMSettings(api_key="visitor-secret"))
    with pytest.raises(LLMOperationalError, match="chave OpenRouter foi rejeitada") as captured:
        llm.complete("sistema", "pergunta")
    assert "visitor-secret" not in str(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


def test_remote_quota_blocks_shared_key_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class PaymentRequired(Exception):
        status_code = 402

    class RejectingClient(FakeChatClient):
        calls = 0

        def invoke(self, messages: Any) -> FakeResponse:
            del messages
            type(self).calls += 1
            raise PaymentRequired("provider-secret")

    monkeypatch.setattr("data_assistant.llm.ChatOpenAI", RejectingClient)
    store = QuotaStore(tmp_path / "quota.sqlite3")
    llm = OpenRouterLLM(LLMSettings(api_key="server-placeholder"), quota_store=store)
    with pytest.raises(QuotaExceededError):
        llm.complete("sistema", "pergunta")
    with pytest.raises(QuotaExceededError):
        llm.complete("sistema", "pergunta")
    assert RejectingClient.calls == 1
    assert store.snapshot(45).provider_exhausted is True


def test_refinement_quota_uses_previous_final_result() -> None:
    class ExhaustedLLM:
        def complete(self, system_prompt: str, user_prompt: str) -> str:
            raise QuotaExceededError()

        def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
            raise AssertionError("Formatação não deve gastar outra chamada")

    dependencies = GraphDependencies(
        llm=ExhaustedLLM(),
        executor=None,  # type: ignore[arg-type]
        schema_provider=lambda: None,  # type: ignore[arg-type,return-value]
    )
    state = initial_state("Mostre vendas por mês")
    state["last_result"] = [{"mes": "2025-01", "total": 1}]
    state["queries"] = ["SELECT 1"]

    refined = refine_sql_node(state, dependencies)
    assert route_after_refinement(refined) == "formatar_resposta"
    answer = format_response_node(refined, dependencies)["response"]
    assert answer is not None
    assert answer.operational_code == "quota_exhausted"
    assert answer.data == state["last_result"]


def test_formatting_quota_keeps_query_result() -> None:
    class ExhaustedLLM:
        def complete(self, system_prompt: str, user_prompt: str) -> str:
            raise AssertionError("Não deve chamar texto")

        def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
            raise QuotaExceededError()

    dependencies = GraphDependencies(
        llm=ExhaustedLLM(),
        executor=None,  # type: ignore[arg-type]
        schema_provider=lambda: None,  # type: ignore[arg-type,return-value]
    )
    state = initial_state("Mostre vendas")
    state["last_result"] = [{"total": 4}]
    state["sufficient"] = True

    answer = format_response_node(state, dependencies)["response"]
    assert answer is not None
    assert answer.status == "partial"
    assert answer.operational_code == "quota_exhausted"
    assert answer.data == state["last_result"]
