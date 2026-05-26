"""Parse SQL and prepare it for the right execution path — split per concern.

The parser is split along the natural axes:

* :mod:`._types`           — ``StmtType`` enum + ``SQLParseError`` +
  ``PreparedSQL`` dataclass.
* :mod:`._parse`           — single-statement parser, batch parser,
  classifier (``_parse_root`` / ``parse_batch`` / ``parse_and_classify``
  / ``classify``).
* :mod:`._prepare`         — ``prepare_sql`` SELECT-side rewriter +
  ``extract_table_refs`` convenience shim.
* :mod:`._refs`            — ``extract_write_target`` /
  ``extract_source_refs`` / ``_extract_schema_target``.
* :mod:`._column_lineage`  — sqlglot-driven ``extract_column_lineage``
  + tree helpers.
* :mod:`._limit`           — ``inject_limit`` for read-only Lens SQL.

The public surface — 11 symbols — matches the pre-split import path so
``pql/__init__.py``, the four cross-module callers (``api.sql_chat
_routes._propose``, ``services.lens.cost_gate``, ``pql._sql``,
``pql.sql_merge_translator``), and the test suites need no edits.

The SQL editor classifies each statement and dispatches to one of
three families:

* **SELECT (and ``WITH ... SELECT``)** runs through DuckDB.  The
  route extracts the 3-part UC table references, enforces ``SELECT``
  per table, and rewrites each reference to a quoted identifier
  matching a pre-registered Delta view.  DuckDB reserves ``main``
  as a catalog name and refuses to bind 3-part UC references
  natively, hence the rewrite.
* **DML (``INSERT INTO ... SELECT``, ``UPDATE``, ``DELETE``,
  ``MERGE``, ``CREATE TABLE ... AS SELECT``)** routes through the
  PQL primitives (``write_table`` / ``update`` / ``delete`` /
  ``merge``).  Source SELECT subqueries still go through the
  DuckDB rewriter for materialisation; the target table stays as
  a plain FQN because Delta writes bypass DuckDB.
* **DDL (``CREATE/DROP SCHEMA``, ``DROP TABLE``, ``ALTER TABLE``)**
  routes through the soyuz client.

Multi-statement input is rejected by ``_parse_root`` ("exactly one
statement").  Use :func:`parse_batch` for the batch path.
"""

from __future__ import annotations

from pointlessql.pql.sql_parser._column_lineage import extract_column_lineage
from pointlessql.pql.sql_parser._limit import inject_limit
from pointlessql.pql.sql_parser._parse import (
    classify,
    parse_and_classify,
    parse_batch,
)
from pointlessql.pql.sql_parser._prepare import extract_table_refs, prepare_sql
from pointlessql.pql.sql_parser._refs import (
    extract_source_refs,
    extract_write_target,
)
from pointlessql.pql.sql_parser._types import PreparedSQL, SQLParseError, StmtType

__all__ = [
    "PreparedSQL",
    "SQLParseError",
    "StmtType",
    "classify",
    "extract_column_lineage",
    "extract_source_refs",
    "extract_table_refs",
    "extract_write_target",
    "inject_limit",
    "parse_and_classify",
    "parse_batch",
    "prepare_sql",
]
