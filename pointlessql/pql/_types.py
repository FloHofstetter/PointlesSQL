"""Result dataclasses returned by :mod:`pointlessql.pql.pql`.

Lives in its own module so the public :class:`SQLResult` shape can
be re-imported by helpers (the SQL execution path) without dragging
the full :class:`PQL` class import graph along.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SQLResult:
    """The outcome of a :meth:`PQL.sql` execution.

    All fields are JSON-encodable so the route handler can serialise
    the result straight into a ``JSONResponse`` body.

    Attributes:
        columns: One dict per output column with ``name`` and
            stringified DuckDB ``type``.
        rows: The result rows as a list of lists (column order matches
            :attr:`columns`).
        row_count: Length of :attr:`rows` after any row-cap slicing.
        truncated: ``True`` iff the underlying query produced more
            rows than ``max_rows`` and the excess was dropped.
        duration_ms: Wall-clock execution time on the DuckDB engine.
        executed_sql: The SQL string the caller supplied (unchanged).
        rewritten_sql: What was actually sent to DuckDB after the
            3-part → single-quoted-identifier rewrite.
        referenced_tables: The list of UC ``catalog.schema.table``
            references extracted from the parsed SQL.
    """

    columns: list[dict[str, str]]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    duration_ms: int
    executed_sql: str
    rewritten_sql: str
    referenced_tables: list[str]
