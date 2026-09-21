from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from data_assistant.assistant import DataAssistant
from data_assistant.contract import AssistantAnswer, VisualizationType
from data_assistant.schema import discover_schema
from data_assistant.validator import validate_sql

pytestmark = pytest.mark.integration


class ReferenceLLM:
    """Deterministic model double that drives the complete production graph."""

    def __init__(self, sql: str, visualization: dict[str, Any]) -> None:
        self.sql = sql
        self.visualization = visualization
        self.text_calls = 0
        self.json_calls = 0

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        assert "schema" in (system_prompt + user_prompt).casefold()
        self.text_calls += 1
        return self.sql

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        del system_prompt, user_prompt
        self.json_calls += 1
        if self.json_calls == 1:
            return {"intent": "reference acceptance"}
        if self.json_calls == 2:
            return {"sufficient": True, "reason": "Resultado determinístico disponível."}
        return {
            "response": "Resultado calculado no anexo de referência.",
            "visualization": self.visualization,
        }


@pytest.fixture(scope="module")
def reference_db() -> Path:
    configured = os.getenv("DB_PATH", "").strip()
    candidates = [Path(configured)] if configured else []
    candidates.append(Path(__file__).resolve().parents[2] / "anexo_desafio_1.db")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    pytest.skip(
        "Anexo oficial indisponível. Defina DB_PATH ou coloque "
        "anexo_desafio_1.db um nível acima."
    )


def _run(
    reference_db: Path,
    question: str,
    sql: str,
    visualization: dict[str, Any],
) -> tuple[AssistantAnswer, ReferenceLLM]:
    llm = ReferenceLLM(sql, visualization)
    answer = DataAssistant(reference_db, llm=llm).ask(question)
    return answer, llm


def _assert_complete_graph_answer(
    answer: AssistantAnswer,
    llm: ReferenceLLM,
    expected_visualization: VisualizationType,
) -> None:
    assert isinstance(answer, AssistantAnswer)
    assert answer.status == "success"
    assert answer.response
    assert answer.data
    assert len(answer.queries) == 1
    assert validate_sql(answer.queries[0])
    assert answer.visualization.type == expected_visualization
    assert expected_visualization in answer.visualization.available_types
    assert answer.warnings == []
    assert "Traceback" not in answer.response
    assert [step["node"] for step in answer.steps] == [
        "interpretar",
        "descobrir_schema",
        "gerar_sql",
        "validar_sql",
        "executar_sql",
        "avaliar_suficiencia",
        "formatar_resposta",
    ]
    assert llm.text_calls == 1
    assert llm.json_calls == 3


def test_reference_schema_reflects_extra_customer_columns(reference_db: Path) -> None:
    snapshot = discover_schema(reference_db)
    customers = next(table for table in snapshot.tables if table.name == "clientes")
    columns = {column.name for column in customers.columns}

    assert {"valor_total_gasto", "data_ultima_compra"}.issubset(columns)


def test_reference_top_states_for_app_purchases_in_may(reference_db: Path) -> None:
    answer, llm = _run(
        reference_db,
        "Quais os 5 estados com mais clientes que compraram pelo App em maio?",
        """
        SELECT c.estado, COUNT(DISTINCT c.id) AS clientes
        FROM clientes AS c
        JOIN compras AS p ON p.cliente_id = c.id
        WHERE p.canal = 'App' AND strftime('%m', p.data_compra) = '05'
        GROUP BY c.estado
        ORDER BY clientes DESC, c.estado ASC
        LIMIT 5
        """,
        {"type": "bar", "title": "Clientes por estado", "x": "estado", "y": ["clientes"]},
    )

    _assert_complete_graph_answer(answer, llm, "bar")
    assert answer.data == [
        {"estado": "São Paulo", "clientes": 6},
        {"estado": "Minas Gerais", "clientes": 3},
        {"estado": "Santa Catarina", "clientes": 3},
        {"estado": "Alagoas", "clientes": 2},
        {"estado": "Espírito Santo", "clientes": 2},
    ]
    assert "valor_total_gasto" not in answer.queries[0]
    assert "data_ultima_compra" not in answer.queries[0]


def test_reference_whatsapp_customers_and_interactions_in_2024(reference_db: Path) -> None:
    answer, llm = _run(
        reference_db,
        "Quantos clientes interagiram com campanhas de WhatsApp em 2024?",
        """
        SELECT
            COUNT(DISTINCT cliente_id) AS clientes_distintos,
            SUM(CASE WHEN interagiu = 1 THEN 1 ELSE 0 END) AS interacoes,
            COUNT(*) AS envios
        FROM campanhas_marketing
        WHERE canal = 'WhatsApp' AND strftime('%Y', data_envio) = '2024'
        """,
        {"type": "metric", "title": "Clientes WhatsApp", "y": ["clientes_distintos"]},
    )

    _assert_complete_graph_answer(answer, llm, "metric")
    assert answer.data == [{"clientes_distintos": 33, "interacoes": 17, "envios": 35}]


def test_reference_average_purchases_per_customer_by_category(reference_db: Path) -> None:
    answer, llm = _run(
        reference_db,
        "Quais categorias tiveram o maior número de compras em média por cliente?",
        """
        WITH compras_cliente AS (
            SELECT categoria, cliente_id, COUNT(*) AS quantidade
            FROM compras
            GROUP BY categoria, cliente_id
        )
        SELECT categoria, ROUND(AVG(quantidade), 2) AS media_por_cliente
        FROM compras_cliente
        GROUP BY categoria
        ORDER BY media_por_cliente DESC, categoria ASC
        """,
        {
            "type": "bar",
            "title": "Média por cliente",
            "x": "categoria",
            "y": ["media_por_cliente"],
        },
    )

    _assert_complete_graph_answer(answer, llm, "bar")
    assert answer.data == [
        {"categoria": "Roupas", "media_por_cliente": 2.21},
        {"categoria": "Viagens", "media_por_cliente": 2.16},
        {"categoria": "Livros", "media_por_cliente": 1.98},
        {"categoria": "Serviços", "media_por_cliente": 1.96},
        {"categoria": "Eletrônicos", "media_por_cliente": 1.92},
        {"categoria": "Alimentos", "media_por_cliente": 1.88},
    ]
    assert "valor_total_gasto" not in answer.queries[0]
    assert "data_ultima_compra" not in answer.queries[0]


def test_reference_unresolved_complaints_by_channel(reference_db: Path) -> None:
    answer, llm = _run(
        reference_db,
        "Quantas reclamações não resolvidas existem por canal?",
        """
        SELECT canal, COUNT(*) AS reclamacoes_nao_resolvidas
        FROM suporte
        WHERE tipo_contato = 'Reclamação' AND resolvido = 0
        GROUP BY canal
        ORDER BY reclamacoes_nao_resolvidas DESC, canal ASC
        """,
        {
            "type": "bar",
            "title": "Reclamações não resolvidas",
            "x": "canal",
            "y": ["reclamacoes_nao_resolvidas"],
        },
    )

    _assert_complete_graph_answer(answer, llm, "bar")
    assert answer.data == [
        {"canal": "Telefone", "reclamacoes_nao_resolvidas": 19},
        {"canal": "Chat", "reclamacoes_nao_resolvidas": 18},
        {"canal": "E-mail", "reclamacoes_nao_resolvidas": 14},
    ]
    assert "tipo_contato = 'Reclamação'" in answer.queries[0]


def test_reference_monthly_complaint_trend_by_channel(reference_db: Path) -> None:
    answer, llm = _run(
        reference_db,
        "Qual a tendência mensal de reclamações por canal?",
        """
        SELECT
            strftime('%Y-%m', data_contato) AS mes,
            canal,
            COUNT(*) AS reclamacoes
        FROM suporte
        WHERE tipo_contato = 'Reclamação'
        GROUP BY mes, canal
        ORDER BY mes, canal
        """,
        {
            "type": "line",
            "title": "Tendência de reclamações",
            "x": "mes",
            "y": ["reclamacoes"],
            "group": "canal",
        },
    )

    _assert_complete_graph_answer(answer, llm, "line")
    assert min(row["mes"] for row in answer.data) == "2024-07"
    assert max(row["mes"] for row in answer.data) == "2025-07"
    assert {row["canal"] for row in answer.data} == {"Telefone", "Chat", "E-mail"}
    assert "tipo_contato = 'Reclamação'" in answer.queries[0]
