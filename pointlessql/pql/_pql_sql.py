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
        preserve_lineage_row_id: bool = True,
    ) -> SQLResult:
        """Run a single SELECT against DuckDB with UC-backed views.

        Thin façade over :func:`pointlessql.pql._sql.run_sql` — the
        helper handles parsing, the approved-tables guard, view
        registration, execution, row-cap slicing, and result framing.

        Lineage propagation: in an agent context, a row-preserving
        SELECT that reads a single lineage-bearing source but omits
        ``_lineage_row_id`` has the column carried forward automatically,
        so the downstream :meth:`write_table` / :meth:`merge` keeps its
        row-edges.  Collapsing SELECTs (GROUP BY / DISTINCT / aggregate /
        CTE / multi-source) are intentional row boundaries — they are
        left untouched and flagged ``lineage_row_id_dropped_at_select``
        on the op's ``params_json`` for run-detail review.  Pass
        ``preserve_lineage_row_id=False`` to return exactly the projected
        columns.

        Args:
            query: The user-entered SQL.  Must be a single SELECT.
            approved_tables: Mapping of fully-qualified table name to
                its Delta storage location.
            max_rows: Post-execution row cap.
            conn: Optional pre-created DuckDB connection.
            explain: When ``True``, return the EXPLAIN ANALYZE output.
            preserve_lineage_row_id: When ``True`` (the default),
                auto-project ``_lineage_row_id`` onto safe row-preserving
                SELECTs so lineage survives into the downstream write.

        Returns:
            A :class:`SQLResult` with columns, rows, and metrics.
        """
        return run_sql(
            query,
            approved_tables=approved_tables,
            max_rows=max_rows,
            conn=conn,
            explain=explain,
            preserve_lineage_row_id=preserve_lineage_row_id,
        )
