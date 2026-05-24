# pyright: reportUnusedClass=false
"""UPDATE + DELETE for the PQL façade."""

from __future__ import annotations

from typing import Any

from pointlessql.pql._pql_base import PQLBase as _PQLBase
from pointlessql.pql._update_delete import delete_table_rows, update_table


class _UpdateDeleteMixin(_PQLBase):
    """Mutate rows in place — UPDATE SET or DELETE FROM Delta tables."""

    def update(
        self,
        target: str,
        *,
        set_clause: dict[str, str],
        where: str | None = None,
        track_value_changes: bool = False,
    ) -> dict[str, Any]:
        """Run ``UPDATE target SET ... WHERE ...`` against a Delta table.

        Wraps :meth:`deltalake.DeltaTable.update` with the audit
        machinery: every call emits one ``agent_run_operations``
        row when ``agent_run_id`` is set, captures
        delta_version_before/_after, and records ``rows_affected``
        from the deltalake metrics.  Optional CDF-based per-cell
        capture mirrors :meth:`merge`'s ``track_value_changes``
        opt-in.

        Args:
            target: Three-part name ``"catalog.schema.table"``.
            set_clause: Mapping ``column_name -> SQL-expression-string``.
                Passed verbatim to deltalake.  Empty dict raises
                :class:`ValueError`.
            where: SQL WHERE clause (delta-rs / DataFusion dialect)
                or ``None`` to update every row.
            track_value_changes: When ``True``, populate
                ``lineage_value_changes`` from the Delta CDF for
                this update's commit range.  CDF must already be
                enabled on the target — first writes via
                :meth:`write_table` enable it automatically.

        Returns:
            The deltalake metrics dict
            (``num_added_files``, ``num_removed_files``,
            ``num_updated_rows``, ``num_copied_rows``,
            ``execution_time_ms``, ``scan_time_ms``).
        """
        return update_table(
            client=self._client,
            full_name=target,
            set_clause=set_clause,
            where=where,
            unreachable_msg=self._unreachable_msg(),
            agent_run_id=self._current_run_id,
            track_value_changes=track_value_changes,
        )

    def delete(
        self,
        target: str,
        *,
        where: str | None = None,
    ) -> dict[str, Any]:
        """Run ``DELETE FROM target WHERE ...`` against a Delta table.

        Wraps :meth:`deltalake.DeltaTable.delete`.  ``where=None``
        deletes every row — the SQL editor surface forces a
        confirmation modal in that case but the
        primitive itself does not refuse the call.

        Args:
            target: Three-part name ``"catalog.schema.table"``.
            where: SQL WHERE clause (delta-rs / DataFusion dialect)
                or ``None`` for a full-table delete.

        Returns:
            The deltalake metrics dict
            (``num_added_files``, ``num_removed_files``,
            ``num_deleted_rows``, ``num_copied_rows``,
            ``execution_time_ms``, ``scan_time_ms``).
        """
        return delete_table_rows(
            client=self._client,
            full_name=target,
            where=where,
            unreachable_msg=self._unreachable_msg(),
            agent_run_id=self._current_run_id,
        )
