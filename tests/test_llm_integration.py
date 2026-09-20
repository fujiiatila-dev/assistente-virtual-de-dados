from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest
from dotenv import load_dotenv

from data_assistant.assistant import DataAssistant
from data_assistant.contract import AssistantAnswer, VisualizationType
from data_assistant.validator import validate_sql

pytestmark = [pytest.mark.llm, pytest.mark.integration]


def _reference_database() -> Path:
    configured = os.getenv("DB_PATH", "").strip()
    candidates = [Path(configured)] if configured else []
    candidates.append(Path(__file__).resolve().parents[2] / "anexo_desafio_1.db")
    database = next((candidate for candidate in candidates if candidate.is_file()), None)
    if database is None:
        pytest.skip("Anexo oficial indisponível para o teste LLM.")
    return database


@pytest.fixture(scope="module", autouse=True)
def require_llm_configuration() -> None:
    load_dotenv()
    if not os.getenv("OPENROUTER_API_KEY", "").strip():
        pytest.skip("OPENROUTER_API_KEY ausente; testes LLM reais não foram executados.")


def _flattened_values(answer: AssistantAnswer) -> list[object]:
    return [value for row in answer.data for value in row.values()]


def _assert_top_states(answer: AssistantAnswer) -> None:
    values = _flattened_values(answer)
    for state in ("São Paulo", "Minas Gerais", "Santa Catarina", "Alagoas", "Espírito Santo"):
        assert state in values
    counts = sorted(value for value in values if isinstance(value, int))
    assert counts[-5:] == [2, 2, 3, 3, 6]


def _assert_whatsapp(answer: AssistantAnswer) -> None:
    values = _flattened_values(answer)
    assert 33 in values
    assert 17 in values
    assert 35 in values


def _assert_category_averages(answer: AssistantAnswer) -> None:
    expected = {
        "Roupas": 2.21,
        "Viagens": 2.16,
        "Livros": 1.98,
        "Serviços": 1.96,
        "Eletrônicos": 1.92,
        "Alimentos": 1.88,
    }
    values = _flattened_values(answer)
    for category, average in expected.items():
        assert category in values
        assert any(
            isinstance(value, int | float) and abs(value - average) < 0.011
            for value in values
        )


def _assert_unresolved_complaints(answer: AssistantAnswer) -> None:
    values = _flattened_values(answer)
    for channel in ("Telefone", "Chat", "E-mail"):
        assert channel in values
    for count in (19, 18, 14):
        assert count in values


def _assert_monthly_trend(answer: AssistantAnswer) -> None:
    values = [str(value) for value in _flattened_values(answer)]
    assert any(value.startswith("2024-07") for value in values)
    assert any(value.startswith("2025-07") for value in values)


LLM_CASES: tuple[
    tuple[str, VisualizationType, Callable[[AssistantAnswer], None]], ...
] = (
    (
        "Quais são os 5 estados com mais clientes que compraram pelo App em maio?",
        "bar",
        _assert_top_states,
    ),
    (
        "Quantos clientes interagiram com campanhas de WhatsApp em 2024? "
        "Informe clientes distintos alcançados, interações e envios.",
        "metric",
        _assert_whatsapp,
    ),
    (
        "Quais categorias tiveram o maior número de compras em média por cliente?",
        "bar",
        _assert_category_averages,
    ),
    (
        "Quantas reclamações não resolvidas existem por canal?",
        "bar",
        _assert_unresolved_complaints,
    ),
    (
        "Qual foi a tendência mensal de reclamações por canal no último ano?",
        "line",
        _assert_monthly_trend,
    ),
)


@pytest.mark.parametrize(("question", "expected_visual", "assert_values"), LLM_CASES)
def test_five_reference_questions_with_real_llm(
    question: str,
    expected_visual: VisualizationType,
    assert_values: Callable[[AssistantAnswer], None],
) -> None:
    answer = DataAssistant(_reference_database()).ask(question)

    assert answer.status == "success"
    assert answer.response
    assert answer.data
    assert answer.queries
    assert expected_visual in answer.visualization.available_types
    assert answer.visualization.type == expected_visual
    assert "Traceback" not in answer.response
    for query in answer.queries:
        assert validate_sql(query)
    assert_values(answer)
