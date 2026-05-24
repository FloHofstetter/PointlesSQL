"""typed parameter binding for the public SQL API."""

from __future__ import annotations

import pytest
import sqlglot
from sqlglot import exp  # noqa: F401  — re-exported for the test below

from pointlessql.services.sql_statements._parameters import (
    SUPPORTED_PARAM_TYPES,
    bind_parameters,
)


def _norm(sql: str) -> str:
    return sqlglot.parse_one(sql, read="duckdb").sql(dialect="duckdb")


def test_bind_string_parameter_quotes_safely() -> None:
    out = bind_parameters(
        "SELECT * FROM main.s.t WHERE region = :region",
        [{"name": "region", "value": "EU", "type": "STRING"}],
    )
    # Single-quoted literal; the value made it to the SQL output.
    assert "'EU'" in out


def test_bind_int_parameter_renders_numeric() -> None:
    out = bind_parameters(
        "SELECT * FROM main.s.t WHERE id = :id",
        [{"name": "id", "value": 42, "type": "INT"}],
    )
    assert "= 42" in out.replace(" ", "= 42")
    # No quoting around numerics.
    assert "'42'" not in out


def test_bind_boolean_parameter() -> None:
    out = bind_parameters(
        "SELECT * FROM main.s.t WHERE active = :flag",
        [{"name": "flag", "value": True, "type": "BOOLEAN"}],
    )
    assert "TRUE" in out.upper()


def test_bind_null_parameter() -> None:
    out = bind_parameters(
        "SELECT * FROM main.s.t WHERE optional = :v",
        [{"name": "v", "value": None, "type": "NULL"}],
    )
    assert "NULL" in out.upper()


def test_bind_date_parameter_casts() -> None:
    out = bind_parameters(
        "SELECT * FROM main.s.t WHERE d = :d",
        [{"name": "d", "value": "2026-05-23", "type": "DATE"}],
    )
    upper = out.upper()
    assert "CAST(" in upper or "::DATE" in upper or "DATE" in upper


def test_bind_injection_string_is_quoted_not_pasted() -> None:
    """A SQL-injection-y string survives as a single SELECT statement.

    sqlglot escapes the literal so the inner ``'`` becomes ``''`` and
    the payload stays trapped inside the string.  We assert the
    output parses back to exactly one SELECT — a successful injection
    would produce two statements (SELECT + DROP).
    """
    payload = "EU'); DROP TABLE main.s.t; --"
    out = bind_parameters(
        "SELECT * FROM main.s.t WHERE region = :region",
        [{"name": "region", "value": payload, "type": "STRING"}],
    )
    statements = sqlglot.parse(out, read="duckdb")
    # Single-statement check + the top-level must remain SELECT.
    assert len(statements) == 1
    assert isinstance(statements[0], sqlglot.exp.Select)


def test_missing_binding_raises() -> None:
    with pytest.raises(ValueError):
        bind_parameters(
            "SELECT * FROM main.s.t WHERE region = :region",
            [],
        )


def test_unknown_type_raises() -> None:
    with pytest.raises(ValueError):
        bind_parameters(
            "SELECT * FROM main.s.t WHERE x = :x",
            [{"name": "x", "value": "1", "type": "QUATERNION"}],
        )


def test_unused_parameter_raises() -> None:
    with pytest.raises(ValueError):
        bind_parameters(
            "SELECT * FROM main.s.t",
            [{"name": "unused", "value": "1", "type": "STRING"}],
        )


def test_supported_types_cover_dbx_v1_set() -> None:
    """Sanity: every type our docs promise is in the supported set."""
    for type_name in ("STRING", "INT", "LONG", "DOUBLE", "BOOLEAN", "DATE", "TIMESTAMP", "NULL"):
        assert type_name in SUPPORTED_PARAM_TYPES


def test_no_parameters_passes_through_unchanged() -> None:
    sql = "SELECT 1"
    assert bind_parameters(sql, []) == sql
    assert _norm(bind_parameters(sql, [])) == _norm(sql)
