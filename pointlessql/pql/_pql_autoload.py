# pyright: reportUnusedClass=false
"""Volume file ingestion (autoload) for the PQL façade."""

from __future__ import annotations

from typing import Any

from pointlessql.pql._autoload import AutoloadFormat, autoload_files
from pointlessql.pql._pql_base import PQLBase as _PQLBase


class _AutoloadMixin(_PQLBase):
    """Lift files from Volume directories into bronze Delta tables."""

    def autoload(
        self,
        source_path: str,
        target: str,
        *,
        source_system: str = "",
        file_format: AutoloadFormat = "auto",
        source_volume_fqn: str | None = None,
    ) -> dict[str, Any]:
        """Lift files from a Volume directory into a bronze Delta table.

        DuckDB type-infers each file
        (``read_parquet`` / ``read_csv_auto`` / ``read_json_auto``),
        the audit columns from
        :func:`pointlessql.conventions.load_conventions` are
        injected on every row, and the result appends to the target
        Delta table.  File-level exactly-once: a SHA-256 of the file
        bytes is recorded in ``autoload_checkpoints`` after a
        successful append, so re-running the autoload over the same
        directory is a no-op for previously-ingested files.

        Args:
            source_path: Local filesystem directory (recursive walk)
                or glob pattern.  Volumes-as-managed-directories;
                HTTP-fetched-Volume support is a follow-up.
            target: UC ``"catalog.schema.table"`` string.  When the
                target doesn't exist it is created on the first
                successful append, using the parent schema's
                ``storage_root``.
            source_system: Free-form upstream-system identifier
                written into the ``_source_system`` audit column.
                Empty default for dev / smoke; production callers
                should pass a real value.
            file_format: ``"auto"`` (per-file extension), or one of
                ``"parquet"`` / ``"csv"`` / ``"json"`` to force.
            source_volume_fqn: Optional UC FQN of the upstream
                Volume backing *source_path*.  Stashed on the audit
                row today; future Volume-tracking work will surface
                it as an OpenLineage input.

        Returns:
            ``{"target", "files_scanned", "files_ingested",
            "files_skipped", "rows_ingested"}``.
        """
        from pointlessql.db import get_session_factory

        return autoload_files(
            client=self._client,
            engine=self._engine,
            session_factory=get_session_factory(),
            source_path=source_path,
            target=target,
            source_system=source_system,
            file_format=file_format,
            conventions=None,
            unreachable_msg=self._unreachable_msg(),
            agent_run_id=self._current_run_id,
            source_volume_fqn=source_volume_fqn,
        )
