from __future__ import annotations

from data_assistant.prompts import (
    correct_sql_prompt,
    format_answer_prompt,
    generate_sql_prompt,
    interpretation_prompt,
    sufficiency_prompt,
)


def test_generation_contains_schema_categories_and_semantic_rules() -> None:
    prompt = generate_sql_prompt(
        "Quantos clientes interagiram em maio?",
        'TABLE "campanhas"\n  - "canal" TEXT VALUES [\'WhatsApp\', \'App\']',
        "gráfico de barras",
    )
    combined = " ".join(f"{prompt.system}\n{prompt.user}".casefold().split())

    assert "schema descoberto em runtime" in combined
    assert "whatsapp" in combined
    assert "format hint: gráfico de barras" in combined
    assert "mês sem ano" in combined
    assert "todos os anos" in combined
    assert "clientes distintos" in combined
    assert "interação igual" in combined
    assert "primeiro agregue por categoria e cliente" in combined
    assert "nunca invente" in combined
    assert "somente select ou with" in combined
    assert "count(*)" in combined
    assert "agrupe exatamente pelas duas dimensões pedidas" in combined
    assert "não uma linha por evento" in combined


def test_interpretation_mentions_month_and_distinct_semantics() -> None:
    prompt = interpretation_prompt("Clientes em maio", None)
    assert "todos os anos" in prompt.system
    assert "clientes distintos" in prompt.system
    assert "não informado" in prompt.user


def test_correction_includes_real_error_previous_sql_and_schema() -> None:
    prompt = correct_sql_prompt(
        "Total por canal",
        'TABLE "compras"',
        "SELECT missing FROM compras",
        "sqlite3.OperationalError: no such column: missing",
    )
    assert "SELECT missing FROM compras" in prompt.user
    assert "no such column: missing" in prompt.user
    assert 'TABLE "compras"' in prompt.user
    assert "não repita" in prompt.system


def test_sufficiency_requires_refinement_for_empty_quantitative_result() -> None:
    prompt = sufficiency_prompt("Quantos clientes?", "SELECT 1", [])
    assert "resultado vazio nunca basta" in prompt.system.casefold()
    assert "consulta complementar" in prompt.system.casefold()
    assert " ".join(prompt.system.casefold().split()).find(
        "uma linha por par período/categoria"
    ) >= 0


def test_formatter_has_closed_visual_menu_and_honest_empty_rule() -> None:
    prompt = format_answer_prompt(
        "Mostre a tendência",
        [{"mes": "2025-01", "total": 2}],
        ["SELECT ..."],
        ["table", "line"],
        "linha",
    )
    combined = f"{prompt.system}\n{prompt.user}".casefold()
    assert "line|bar|table|metric" in combined
    assert "resultado vazio" in combined
    assert "zero inventado" in combined
    assert '"mes"' in combined
    assert "formato solicitado: linha" in combined
