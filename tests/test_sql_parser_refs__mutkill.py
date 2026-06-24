"""Mutation-kill tests for ``pointlessql.pql.sql_parser._refs``.

Pins ``_extract_schema_target``: a two-part ``catalog.schema`` reference is
returned, and a one-part reference is rejected as not fully qualified.
"""

from __future__ import annotations

import pytest
import sqlglot

from pointlessql.pql.sql_parser._refs import _extract_schema_target
from pointlessql.pql.sql_parser._types import SQLParseError


@pytest.mark.parametrize("sql", ["CREATE SCHEMA main.bronze", "DROP SCHEMA main.bronze"])
def test_extract_schema_target_returns_two_part_qualified(sql: str) -> None:
    """A two-part ``catalog.schema`` reference is unwrapped and returned."""
    # kills `node = node.this` -> `node = None` (the exp.Schema unwrap)
    ast = sqlglot.parse_one(sql, dialect="duckdb")
    assert _extract_schema_target(ast) == "main.bronze"


def test_extract_schema_target_rejects_one_part_reference() -> None:
    """A one-part schema reference raises SQLParseError (needs catalog.schema)."""
    # kills `catalog is not None and schema is not None` -> `or`, and message -> None
    ast = sqlglot.parse_one("CREATE SCHEMA bronze", dialect="duckdb")
    with pytest.raises(SQLParseError, match="fully qualified"):
        _extract_schema_target(ast)
