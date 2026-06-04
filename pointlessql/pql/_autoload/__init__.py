# pyright: reportPrivateUsage=false
# The orchestrator reaches across the per-concern sub-modules and calls
# their package-private helpers; that cross-module access is intentional.
"""``pql.autoload()`` — file → bronze ingestion.

One of the Medallion building blocks: lifts files from a Volume
directory (or any local filesystem path) into a Delta target table
with audit columns, file-level exactly-once via SHA-256 checkpoints.
DuckDB does the type inference; ``deltalake`` does the write.

Design choices (deliberately small for the MVP):

* **Local filesystem paths** are the source — Volumes-as-managed-
  directories.  HTTP-fetched-Volume support stays a follow-up;
  the demo runs against locally-mounted Volume roots.
* **File-level exactly-once** via the ``autoload_checkpoints``
  table, keyed on ``(target_table, file_sha)``.  A re-run over
  the same directory skips already-ingested files; a content
  edit produces a new SHA and re-ingests.  Per-row dedup +
  schema-drift handling are explicitly deferred (out of MVP
  scope).
* **Audit columns** (``_ingested_at`` / ``_source_file`` /
  ``_source_system``) are pulled from
  :func:`pointlessql.conventions.load_conventions` so the column
  names track the configured contract.
* **Target bootstrap** — the first autoload into a non-existent
  target uses ``deltalake.write_deltalake`` (which is happy to
  create) and registers the resulting Delta path in soyuz-catalog
  via the same call sequence as :func:`pointlessql.pql._write.write_table`.
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Any, cast

from soyuz_catalog_client import Client
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.conventions import ConventionsConfig, load_conventions
from pointlessql.pql._autoload._audit_columns import (
    _build_autoload_column_edges,
    _inject_audit_columns,
    _resolve_audit_columns,
)
from pointlessql.pql._autoload._checkpoint import (
    _checkpoint_exists,
    _record_checkpoint,
    _sha256_file,
)
from pointlessql.pql._autoload._files import (
    AutoloadFormat,
    _list_source_files,
    _read_file_via_duckdb,
    _resolve_file_format,
)
from pointlessql.pql._autoload._sink import (
    _append_to_delta,
    _register_target_in_uc,
    _resolve_target_or_derive,
)
from pointlessql.pql._hashing import concat_sha256
from pointlessql.pql._parsing import parse_full_name
from pointlessql.pql._write import safe_delta_version
from pointlessql.pql.engine import Engine
from pointlessql.services.agent_runs import operation_context
from pointlessql.types import OpName, RunId

logger = logging.getLogger(__name__)


def autoload_files(
    *,
    client: Client,
    engine: Engine,
    session_factory: sessionmaker[Session],
    source_path: str | Path,
    target: str,
    source_system: str,
    file_format: AutoloadFormat,
    conventions: ConventionsConfig | None,
    unreachable_msg: str,
    agent_run_id: str | None = None,
    source_volume_fqn: str | None = None,
) -> dict[str, Any]:
    """Ingest matching files under *source_path* into the target Delta table.

    Args:
        client: Configured ``soyuz_catalog_client.Client``.
        engine: PQL engine — used only for column-info on the
            first-time table registration in soyuz-catalog.
        session_factory: SQLAlchemy session factory backing the
            ``autoload_checkpoints`` table.  Caller is responsible
            for ``init_db`` having been called.  The same factory
            also backs the ``agent_run_operations`` row.
        source_path: Local filesystem directory (recursive walk) or
            a glob pattern (``*`` / ``?`` / ``[``-class).
        target: UC ``"catalog.schema.table"`` string.
        source_system: Free-form name of the upstream system —
            written into the ``_source_system`` audit column verbatim.
            Empty string is allowed but discouraged for production.
        file_format: ``"auto"`` (per-file extension), or one of
            ``"parquet"`` / ``"csv"`` / ``"json"`` to force.
        conventions: Optional pre-loaded conventions; falls back to
            :func:`load_conventions` when ``None``.  The bronze
            layer's ``required_audit_columns`` drive the injection.
        unreachable_msg: Pre-rendered "cannot reach catalog" message.
        agent_run_id: When set, emits one ``agent_run_operations``
            row capturing pre/post Delta versions, file SHA digest,
            and ingest counts.
        source_volume_fqn: When set, recorded on the audit row so
            future Volume-tracking work can declare the upstream UC
            Volume on the OpenLineage event.  Today the value is
            stashed but the lineage emission still uses no inputs
            (autoload sources are filesystem paths, not UC
            securables); see  for context.

    Returns:
        ``{"target", "files_scanned", "files_ingested", "files_skipped",
        "rows_ingested"}``.

    Raises:
        ValidationError: When *target* is malformed or *file_format*
            cannot be inferred for a file.
        CatalogNotFoundError: When *target*'s parent schema has no
            storage root and the table doesn't exist yet.
        CatalogUnavailableError: When soyuz-catalog is unreachable.
        AuditUnavailableError: If *agent_run_id* is set and the
            ``agent_run_operations`` row cannot be persisted.
    """  # noqa: DOC502,DOC503 — every Raises entry propagates from helpers
    catalog, schema, table = parse_full_name(target)
    resolved_conventions = conventions or load_conventions()
    audit_columns = _resolve_audit_columns(resolved_conventions)

    files = _list_source_files(source_path, file_format)

    target_location, target_exists = _resolve_target_or_derive(
        client, catalog, schema, table, target, unreachable_msg
    )

    audit_factory = session_factory if agent_run_id else None

    with operation_context(
        audit_factory,
        agent_run_id=cast(RunId | None, agent_run_id),
        op_name=OpName.AUTOLOAD,
        params={
            "source_path": str(source_path),
            "target": target,
            "source_system": source_system,
            "file_format": file_format,
        },
        target_table=target,
    ) as recorder:
        if agent_run_id is not None and target_exists:
            recorder.delta_version_before = safe_delta_version(target_location)

        files_ingested = 0
        files_skipped = 0
        rows_total = 0
        bootstrap_done = target_exists
        ingested_shas: list[str] = []

        for file_path in files:
            sha = _sha256_file(file_path)
            if _checkpoint_exists(session_factory, target, sha):
                files_skipped += 1
                continue

            per_file_format = _resolve_file_format(file_path, file_format)
            arrow_table = _read_file_via_duckdb(file_path, per_file_format)
            ingested_at = datetime.datetime.now(datetime.UTC)
            augmented = _inject_audit_columns(
                arrow_table,
                audit_columns,
                file_path=file_path,
                file_sha=sha,
                source_system=source_system,
                ingested_at=ingested_at,
            )

            _append_to_delta(target_location, augmented)

            if not bootstrap_done:
                _register_target_in_uc(
                    client=client,
                    engine=engine,
                    catalog=catalog,
                    schema=schema,
                    table=table,
                    location=target_location,
                    arrow_for_columns=augmented,
                    unreachable_msg=unreachable_msg,
                )
                bootstrap_done = True

            rows_total += augmented.num_rows
            _record_checkpoint(
                session_factory,
                source_path=file_path,
                file_sha=sha,
                target_table=target,
                ingested_at=ingested_at,
                rows_ingested=augmented.num_rows,
            )
            files_ingested += 1
            ingested_shas.append(sha)

        if not target_exists and files_ingested > 0:
            from pointlessql.pql._cdf import ensure_cdf_enabled

            ensure_cdf_enabled(target_location)

        if agent_run_id is not None:
            recorder.delta_version_after = safe_delta_version(target_location)
            recorder.rows_affected = rows_total
            recorder.input_sha = concat_sha256(ingested_shas) if ingested_shas else None
            extras: dict[str, Any] = {
                "files_scanned": len(files),
                "files_ingested": files_ingested,
                "files_skipped": files_skipped,
            }
            if source_volume_fqn:
                extras["source_volume_fqn"] = source_volume_fqn
            recorder.extra_params = extras

            if files_ingested > 0:
                recorder.pending_column_edges = _build_autoload_column_edges(
                    target_location=target_location,
                    target=target,
                    audit_columns=audit_columns,
                    source_volume_fqn=source_volume_fqn,
                )

    return {
        "target": target,
        "files_scanned": len(files),
        "files_ingested": files_ingested,
        "files_skipped": files_skipped,
        "rows_ingested": rows_total,
    }


__all__ = ["AutoloadFormat", "autoload_files"]
