# pyright: reportUnusedClass=false
"""DuckDB SQL execution for the PQL façade."""

from __future__ import annotations

from typing import Any

from pointlessql.pql._pql_base import PQLBase as _PQLBase
from pointlessql.pql._sql import run_sql
from pointlessql.pql._types import SQLResult


class _SqlMixin(_PQLBase):
    """Run a single SELECT against DuckDB with UC-backed views."""

    @staticmethod
    def sql(
        query: str,
        *,
        approved_tables: dict[str, str],
        max_rows: int = 10_000,
        conn: Any = None,
        explain: bool = False,
    ) -> SQLResult:
        """Run a single SELECT against DuckDB with UC-backed views.

        Thin façade over :func:`pointlessql.pql._sql.run_sql` — the
        helper handles parsing, the approved-tables guard, view
        registration, execution, row-cap slicing, and result framing.

        Lineage propagation: when a referenced source
        table carries ``_lineage_row_id`` and the agent will feed the
        result frame into :meth:`write_table` or :meth:`merge` with
        row-edges expected, the SELECT must explicitly project the
        column (``SELECT t._lineage_row_id AS _lineage_row_id, …``).
        Without it, the downstream audit hook short-circuits — no
        source IDs to correlate on, so ``lineage_row_edges`` records
        nothing and every further table inherits the gap.  An INFO
        log + ``lineage_row_id_dropped_at_select`` flag on the op's
        ``params_json`` surfaces the omission for run-detail review.

        Args:
            query: The user-entered SQL.  Must be a single SELECT.
            approved_tables: Mapping of fully-qualified table name to
                its Delta storage location.
            max_rows: Post-execution row cap.
            conn: Optional pre-created DuckDB connection.
            explain: When ``True``, return the EXPLAIN ANALYZE output.

        Returns:
            A :class:`SQLResult` with columns, rows, and metrics.
        """
        return run_sql(
            query,
            approved_tables=approved_tables,
            max_rows=max_rows,
            conn=conn,
            explain=explain,
        )
