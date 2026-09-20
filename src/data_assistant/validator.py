"""Deterministic SQL validation independent from the language model."""

from __future__ import annotations

from sqlglot import exp, parse
from sqlglot.errors import ParseError


class SQLValidationError(ValueError):
    """Raised when generated SQL violates the read-only policy."""


def _function_name(node: object) -> str:
    if isinstance(node, exp.Anonymous):
        return node.name.lower()
    sql_name = getattr(node, "sql_name", None)
    if callable(sql_name):
        return str(sql_name()).lower()
    return ""


def _reject_blocked_constructs(expression: exp.Query) -> None:
    for node in expression.walk():
        function_name = _function_name(node)
        if function_name == "load_extension":
            raise SQLValidationError("A função load_extension não é permitida")
        if function_name.startswith("pragma_"):
            raise SQLValidationError("Funções de tabela PRAGMA não são permitidas")

        if isinstance(node, exp.Table):
            table_name = node.name.lower()
            if table_name.startswith("pragma_"):
                raise SQLValidationError("Funções de tabela PRAGMA não são permitidas")

        if isinstance(node, exp.Join):
            method = str(node.args.get("method") or "").upper()
            kind = str(node.args.get("kind") or "").upper()
            on_clause = node.args.get("on")
            implicit_true = isinstance(on_clause, exp.Boolean) and on_clause.this is True
            has_condition = bool((on_clause and not implicit_true) or node.args.get("using"))
            if kind == "CROSS" or (not has_condition and method != "NATURAL"):
                raise SQLValidationError("JOIN sem condição explícita não é permitido")


def validate_sql(sql: str) -> str:
    """Return normalized SQLite SELECT SQL or raise a policy error.

    Parsing the complete input avoids treating semicolons inside string literals as
    statement separators.
    """
    if not sql.strip():
        raise SQLValidationError("A query SQL está vazia")
    try:
        statements = [statement for statement in parse(sql, read="sqlite") if statement]
    except ParseError as exc:
        raise SQLValidationError(f"SQL inválido: {exc}") from exc

    if len(statements) != 1:
        raise SQLValidationError("Apenas um statement SQL é permitido")
    statement = statements[0]
    if not isinstance(statement, exp.Query):
        raise SQLValidationError("Somente consultas SELECT ou WITH são permitidas")

    _reject_blocked_constructs(statement)
    return statement.sql(dialect="sqlite")
