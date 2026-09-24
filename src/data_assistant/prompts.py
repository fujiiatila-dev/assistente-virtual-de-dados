"""Prompt construction for the isolated LLM boundary."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PromptPair:
    """System and user messages for one model operation."""

    system: str
    user: str


SHARED_SQL_RULES = """
Use exclusivamente tabelas, colunas, relações e valores presentes no schema fornecido.
Nunca invente identificadores. Gere exatamente um statement SQLite, somente SELECT ou WITH,
sem markdown. Não use PRAGMA, ATTACH, load_extension nem operações de escrita.
Para métricas operacionais de compras, use a tabela transacional de compras como fonte de
verdade; campos agregados do cadastro podem estar desatualizados.
Regras semânticas obrigatórias:
- mês sem ano: considere todos os anos disponíveis e permita que a resposta declare o
  período efetivamente consultado;
- "clientes que interagiram": conte clientes distintos com indicador de interação igual
  a 1, sem confundir clientes, envios e total de interações;
- "média de compras por cliente": primeiro agregue por categoria e cliente, depois calcule
  a média entre clientes.
- perguntas por quantidade, total ou frequência ao longo do tempo e por categoria: selecione
  COUNT(*) AS quantidade, mantenha período e categoria no resultado e agrupe exatamente
  pelas duas dimensões pedidas; retorne uma linha por par, não uma linha por evento. Aplique
  limites apenas depois da agregação.
""".strip()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def interpretation_prompt(question: str, format_hint: str | None) -> PromptPair:
    """Ask for a concise structured interpretation of user intent."""
    return PromptPair(
        system="""
Você interpreta perguntas de negócio em pt-BR sem inventar fatos. Retorne somente um objeto
JSON com: intent, metric, dimensions, time_scope, format_hint e ambiguities. Quando houver
um mês sem ano, registre que todos os anos disponíveis devem ser considerados. Diferencie
clientes distintos, envios e interações. Não produza SQL nesta etapa.
""".strip(),
        user=f"Pergunta: {question}\nFormato solicitado: {format_hint or 'não informado'}",
    )


def generate_sql_prompt(
    question: str,
    schema_dsl: str,
    format_hint: str | None,
    interpretation: Mapping[str, Any] | None = None,
    prior_results: Sequence[Mapping[str, Any]] | None = None,
) -> PromptPair:
    """Build the initial or refinement text-to-SQL prompt."""
    system = (
        "Você é especialista em SQLite e gera SQL analítico auditável.\n"
        f"{SHARED_SQL_RULES}\n"
        "Os valores categóricos válidos aparecem como VALUES no schema. Respeite grafia, "
        "acentos e capitalização."
    )
    user = "\n".join(
        (
            f"Pergunta: {question}",
            f"Format hint: {format_hint or 'não informado'}",
            f"Interpretação: {_json(dict(interpretation or {}))}",
            f"Resultados anteriores para refinamento: {_json(list(prior_results or [])[:20])}",
            "Schema descoberto em runtime, incluindo valores categóricos:",
            schema_dsl,
            "Retorne somente o SQL.",
        )
    )
    return PromptPair(system=system, user=user)


def correct_sql_prompt(
    question: str,
    schema_dsl: str,
    previous_sql: str,
    error: str,
    result: Sequence[Mapping[str, Any]] | None = None,
) -> PromptPair:
    """Return the real validator/SQLite error to the model for one correction."""
    system = (
        "Você corrige uma consulta SQLite usando o erro real recebido.\n"
        f"{SHARED_SQL_RULES}\n"
        "Altere apenas o necessário e não repita uma query que já falhou. Retorne somente SQL."
    )
    user = "\n".join(
        (
            f"Pergunta original: {question}",
            "Schema descoberto em runtime:",
            schema_dsl,
            f"SQL anterior: {previous_sql}",
            f"Erro real: {error}",
            f"Resultado anterior, se existir: {_json(list(result or [])[:20])}",
        )
    )
    return PromptPair(system=system, user=user)


def sufficiency_prompt(
    question: str,
    sql: str,
    result: Sequence[Mapping[str, Any]],
) -> PromptPair:
    """Ask whether successful rows are enough or a complementary query is needed."""
    return PromptPair(
        system="""
Avalie se o resultado permite responder à pergunta sem inventar dados. Retorne somente JSON:
{"sufficient": boolean, "reason": string}. Resultado vazio nunca basta para uma pergunta
quantitativa; peça refinamento. Uma consulta complementar deve agregar informação nova, não
repetir a consulta anterior.
Para uma contagem solicitada por período e categoria, exija COUNT selecionado, ambos os
campos dimensionais visíveis e uma linha por par período/categoria; uma amostra de eventos
individuais não é suficiente.
""".strip(),
        user=f"Pergunta: {question}\nSQL: {sql}\nResultado (amostra): {_json(list(result)[:20])}",
    )


def format_answer_prompt(
    question: str,
    result: Sequence[Mapping[str, Any]],
    queries: Sequence[str],
    available_types: Sequence[str],
    format_hint: str | None,
) -> PromptPair:
    """Ask for a grounded pt-BR answer and a closed-menu visualization proposal."""
    return PromptPair(
        system="""
Formate uma resposta executiva em pt-BR usando somente os dados recebidos. Resultado vazio
deve gerar uma resposta honesta, nunca um zero inventado. Explique o período quando a pergunta
citar mês sem ano. Retorne somente JSON com:
{"response": string, "visualization": {"type": "line|bar|table|metric", "title": string,
"x": string|null, "y": [string]|null, "group": string|null}}.
Escolha apenas um tipo do cardápio disponível e colunas existentes. Tendência temporal usa
line; comparação usa bar; lista usa table; escalar usa metric. Um formato explicitamente
pedido tem prioridade quando for compatível.
""".strip(),
        user="\n".join(
            (
                f"Pergunta: {question}",
                f"Formato solicitado: {format_hint or 'não informado'}",
                f"Cardápio disponível: {_json(list(available_types))}",
                f"Queries executadas: {_json(list(queries))}",
                f"Dados: {_json(list(result)[:200])}",
            )
        ),
    )
