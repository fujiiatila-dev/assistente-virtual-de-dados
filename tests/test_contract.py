from __future__ import annotations

from data_assistant.contract import AssistantAnswer, Visualization
from data_assistant.visualization import compatible_visualization_types, normalize_visualization


def test_calculates_compatible_types_from_data_shape() -> None:
    scalar = [{"total": 33}]
    comparison = [{"canal": "App", "total": 10}, {"canal": "Loja", "total": 5}]
    trend = [{"mes": "2025-01", "total": 2}, {"mes": "2025-02", "total": 4}]

    assert compatible_visualization_types(scalar) == ["table", "metric"]
    assert compatible_visualization_types(comparison) == ["table", "bar"]
    assert compatible_visualization_types(trend) == ["table", "line"]
    assert compatible_visualization_types([]) == ["table"]


def test_invalid_type_or_columns_fall_back_to_table() -> None:
    data = [{"categoria": "Livros", "total": 8}]
    invalid_type = normalize_visualization(data, {"type": "pie", "title": "Pizza"})
    invalid_columns = normalize_visualization(
        data,
        {"type": "bar", "title": "Barras", "x": "inventada", "y": ["total"]},
    )

    assert invalid_type.type == "table"
    assert invalid_columns.type == "table"
    assert invalid_columns.available_types == ["table", "bar", "metric"]


def test_generic_model_table_uses_shape_derived_default_without_explicit_hint() -> None:
    scalar = [{"clientes": 33, "interacoes": 17, "envios": 35}]
    comparison = [{"categoria": "Roupas", "media": 2.21}, {"categoria": "Livros", "media": 1.98}]

    assert normalize_visualization(scalar, {"type": "table"}).type == "metric"
    assert normalize_visualization(comparison, {"type": "table"}).type == "bar"
    assert normalize_visualization(
        comparison, {"type": "table"}, format_hint="mostre como tabela"
    ).type == "table"


def test_explicit_valid_format_has_priority_without_new_data() -> None:
    data = [{"categoria": "Livros", "total": 8}, {"categoria": "Roupas", "total": 4}]
    visual = normalize_visualization(
        data,
        {"type": "table", "title": "Categorias"},
        format_hint="mostre como gráfico de barras",
    )
    assert visual.type == "bar"
    assert visual.x == "categoria"
    assert visual.y == ["total"]


def test_answer_contract_falls_back_when_referenced_column_is_missing() -> None:
    answer = AssistantAnswer(
        status="success",
        response="Há 8 compras.",
        visualization=Visualization(
            type="bar",
            title="Compras",
            x="categoria",
            y=["inexistente"],
            available_types=["table", "bar"],
        ),
        data=[{"categoria": "Livros", "total": 8}],
    )

    assert answer.visualization.type == "table"
    assert answer.warnings == [
        "Visualização solicitada incompatível com as colunas; exibindo tabela."
    ]


def test_operational_code_preserves_existing_public_contract() -> None:
    answer = AssistantAnswer(
        status="partial",
        response="Consulta parcial.",
        visualization=Visualization(type="table", title="Dados"),
        data=[{"total": 2}],
        warnings=["Cota encerrada."],
        operational_code="quota_exhausted",
    )

    payload = answer.model_dump()
    assert payload["status"] == "partial"
    assert payload["warnings"] == ["Cota encerrada."]
    assert payload["visualization"]["available_types"] == ["table"]
    assert payload["operational_code"] == "quota_exhausted"
