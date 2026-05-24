# pyright: reportUnusedClass=false
"""Table read operations for the PQL façade — current + historical."""

from __future__ import annotations

from typing import Any

from pointlessql.pql._pql_base import PQLBase as _PQLBase
from pointlessql.pql._read import read_table


class _ReadMixin(_PQLBase):
    """Read Delta tables — current version, by version, or by wall-clock time."""

    def table(self, full_name: str) -> Any:
        """Read a Delta table registered in Unity Catalog.

        Args:
            full_name: Three-part name ``"catalog.schema.table"``.
                When the kernel's :mod:`pointlessql.pql.context` carries
                an active branch binding (Phase 102 Wave-D), the
                schema segment is rewritten on the fly so the read
                follows the binding without the caller spelling it
                out.  Reads falling through to a table the branch
                does not carry surface ``BranchNotFoundError`` and
                callers can fall back to the canonical FQN with
                ``with_branch=False``-style overrides in a future
                follow-up.

        Returns:
            The table contents in the engine's native frame type
            (e.g. pandas DataFrame, DuckDB relation).
        """
        return read_table(
            client=self._client,
            engine=self._engine,
            full_name=self._branch_remap(full_name),
            unreachable_msg=self._unreachable_msg(),
        )

    def table_at_version(self, full_name: str, version: int) -> Any:
        """Read a Delta table as of a specific historical version.

        Always materialises through pandas — the engine abstraction
        targets current-version reads only, and per-engine
        ``load_as_version`` would surface near-identical code.
        Records a ``query_history`` row with
        ``read_kind="pql_table_at_version"`` so the time-travel read
        shows up in ``/queries``.

        Args:
            full_name: Three-part name ``"catalog.schema.table"``.
            version: Target Delta version.  ``0`` is the initial
                commit; subsequent commits monotonically increment.

        Returns:
            A pandas DataFrame as the table looked at *version*.
        """
        from pointlessql.pql._time_travel import read_table_at_version

        return read_table_at_version(
            client=self._client,
            full_name=full_name,
            version=version,
            unreachable_msg=self._unreachable_msg(),
        )

    def table_at_timestamp(self, full_name: str, when: Any) -> Any:
        """Read a Delta table as it looked at wall-clock instant *when*.

        Resolves to a Delta version via
        :meth:`deltalake.DeltaTable.load_as_version` (the public API
        accepts a datetime).

        Args:
            full_name: Three-part name ``"catalog.schema.table"``.
            when: Timezone-aware ``datetime``.

        Returns:
            A pandas DataFrame as the table looked at *when*.
        """
        from pointlessql.pql._time_travel import read_table_at_timestamp

        return read_table_at_timestamp(
            client=self._client,
            full_name=full_name,
            when=when,
            unreachable_msg=self._unreachable_msg(),
        )
