"""Dataclasses threaded through the dispatcher branches.

Stand-alone module so every branch can ``from ._types import
DispatchContext`` without dragging in the entrypoint (which imports
the branches — circular if the dataclasses lived there).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import Request
from sqlglot.expressions.core import Expression

from pointlessql.config import Settings
from pointlessql.pql import StmtType


@dataclass
class ExecutionResult:
    """Uniform return shape for every dispatcher branch.

    ``kind`` discriminates the JSON response shape the route
    returns; SELECT keeps the legacy ``columns/rows/row_count``
    fields, write paths add ``target``, ``rows_affected``,
    ``agent_run_id``, and ``operation_id``.
    """

    kind: Literal["select", "dml", "ddl"]
    columns: list[str] | None = None
    rows: list[list[Any]] | None = None
    row_count: int | None = None
    truncated: bool = False
    duration_ms: int | None = None
    executed_sql: str | None = None
    referenced_tables: list[str] = field(default_factory=list[str])
    target: str | None = None
    rows_affected: int | None = None
    agent_run_id: str | None = None
    operation_id: str | None = None
    op_name: str | None = None
    stats: dict[str, Any] | None = None


@dataclass
class DispatchContext:
    """Inputs assembled once at the route boundary.

    Avoids threading 8+ kwargs through every branch.
    """

    request: Request
    settings: Settings
    sql: str
    ast: Expression
    stype: StmtType
    actor_email: str
    is_admin: bool
    # duckdb.DuckDBPyConnection — Any so non-DuckDB branches may pass None
    conn: Any
    max_rows: int
