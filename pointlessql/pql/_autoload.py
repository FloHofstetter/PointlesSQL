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
import glob
import hashlib
import logging
from pathlib import Path
from typing import Any, Literal, cast

import deltalake
import httpx
import pyarrow as pa
from soyuz_catalog_client import Client
from soyuz_catalog_client.api.tables import (
    create_table_api_2_1_unity_catalog_tables_post as _create_table,
)
from soyuz_catalog_client.api.tables import (
    get_table_api_2_1_unity_catalog_tables_full_name_get as _get_table,
)
from soyuz_catalog_client.errors import UnexpectedStatus
from soyuz_catalog_client.models.create_table import CreateTable
from soyuz_catalog_client.models.table_info import TableInfo
from soyuz_catalog_client.types import Unset
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.conventions import ConventionsConfig, load_conventions
from pointlessql.exceptions import (
    CatalogUnavailableError,
    ValidationError,
)
from pointlessql.models import AutoloadCheckpoint
from pointlessql.pql._columns import columns_from_tuples
from pointlessql.pql._hashing import concat_sha256
from pointlessql.pql._parsing import parse_full_name
from pointlessql.pql._write import derive_storage_location, safe_delta_version
from pointlessql.pql.engine import Engine
from pointlessql.services.agent_runs import operation_context
from pointlessql.types import OpName, RunId

logger = logging.getLogger(__name__)

AutoloadFormat = Literal["auto", "parquet", "csv", "json"]

_FORMAT_BY_EXTENSION: dict[str, AutoloadFormat] = {
    ".parquet": "parquet",
    ".csv": "csv",
    ".json": "json",
    ".jsonl": "json",
    ".ndjson": "json",
}

_DUCKDB_READER_BY_FORMAT: dict[AutoloadFormat, str] = {
    "parquet": "read_parquet",
    "csv": "read_csv_auto",
    "json": "read_json_auto",
}


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


def _build_autoload_column_edges(
    *,
    target_location: str,
    target: str,
    audit_columns: tuple[str, ...],
    source_volume_fqn: str | None,
) -> list:  # type: ignore[type-arg]
    """Construct ``ColumnEdgeSpec`` entries for an autoload op.

    Reads the target Delta schema (post-append) so the edges
    cover whatever columns actually landed.  Each non-audit column
    gets an ``unknown_origin`` edge with
    ``transform_detail="<file>"`` (or ``"file"`` when no Volume FQN
    was declared) — autoload sources are file URIs, not UC tables,
    so we deliberately avoid claiming a ``source_table_fqn``.

    Args:
        target_location: Delta storage location for the target.
        target: Fully-qualified UC name of the target.
        audit_columns: The audit-column names autoload injected.
        source_volume_fqn: Optional UC FQN of the upstream Volume.

    Returns:
        A list of :class:`ColumnEdgeSpec` ready for the recorder.
        Empty when the target schema can't be read.
    """
    from pointlessql.services.lineage_edges import ColumnEdgeSpec

    try:
        schema = deltalake.DeltaTable(target_location).schema()
        delta_columns = [field.name for field in schema.fields]
    except Exception:  # noqa: BLE001 — best-effort metadata read
        # bare-broad-ok: column-edge derivation skipped on Delta read failure
        return []

    audit_set = set(audit_columns)
    edges: list[ColumnEdgeSpec] = []
    detail = source_volume_fqn or "file"
    for col in delta_columns:
        if col in audit_set:
            edges.append(
                ColumnEdgeSpec(
                    source_table=None,
                    source_column=None,
                    target_table=target,
                    target_column=col,
                    transform_kind="unknown_origin",
                    transform_detail="audit",
                )
            )
        else:
            edges.append(
                ColumnEdgeSpec(
                    source_table=None,
                    source_column=None,
                    target_table=target,
                    target_column=col,
                    transform_kind="unknown_origin",
                    transform_detail=detail,
                )
            )
    return edges


def _resolve_audit_columns(conventions: ConventionsConfig) -> tuple[str, ...]:
    """Return the bronze layer's required audit columns or the documented default.

    Args:
        conventions: The loaded :class:`ConventionsConfig`.

    Returns:
        A tuple of audit-column names to inject on every appended
        row.  Empty when an operator has stripped them via
        ``pointlessql.yaml``.
    """
    bronze = conventions.get_layer("bronze")
    if bronze is None:
        return ()
    return bronze.required_audit_columns


def _list_source_files(source_path: str | Path, file_format: AutoloadFormat) -> list[str]:
    """List files under *source_path* matching the requested format.

    A path containing glob characters is treated as a glob; otherwise
    we walk the directory tree and keep files whose extension maps to
    a supported format (or to *file_format* when it is not ``"auto"``).
    Ordering is deterministic (sorted) so the autoload-then-checkpoint
    sequence is reproducible across runs.

    Args:
        source_path: Local filesystem path or glob.
        file_format: ``"auto"`` or an explicit format.

    Returns:
        List of absolute file paths in sorted order.
    """
    raw = str(source_path)
    if any(ch in raw for ch in ("*", "?", "[")):
        candidates = sorted(p for p in glob.glob(raw, recursive=True) if Path(p).is_file())
    else:
        root = Path(raw)
        if root.is_file():
            candidates = [str(root)]
        elif root.is_dir():
            candidates = sorted(str(p) for p in root.rglob("*") if p.is_file())
        else:
            candidates = []

    if file_format == "auto":
        return [p for p in candidates if Path(p).suffix.lower() in _FORMAT_BY_EXTENSION]

    target_ext = {ext for ext, fmt in _FORMAT_BY_EXTENSION.items() if fmt == file_format}
    return [p for p in candidates if Path(p).suffix.lower() in target_ext]


def _resolve_file_format(file_path: str, file_format: AutoloadFormat) -> AutoloadFormat:
    """Decide which DuckDB reader to use for *file_path*.

    Args:
        file_path: Absolute path of the source file.
        file_format: ``"auto"`` to derive from the extension, or an
            explicit override.

    Returns:
        One of ``"parquet"`` / ``"csv"`` / ``"json"``.

    Raises:
        ValidationError: When ``file_format`` is ``"auto"`` and the
            extension isn't in :data:`_FORMAT_BY_EXTENSION`.
    """
    if file_format != "auto":
        return file_format
    ext = Path(file_path).suffix.lower()
    inferred = _FORMAT_BY_EXTENSION.get(ext)
    if inferred is None:
        raise ValidationError(
            f"autoload could not infer file_format for {file_path!r} — "
            f"pass file_format='parquet'/'csv'/'json' explicitly"
        )
    return inferred


def _read_file_via_duckdb(file_path: str, file_format: AutoloadFormat) -> pa.Table:
    """Read *file_path* through DuckDB and return a PyArrow Table.

    Args:
        file_path: Absolute path of the source file.
        file_format: One of the explicit formats.

    Returns:
        A PyArrow Table with DuckDB-inferred types.
    """
    import duckdb

    reader = _DUCKDB_READER_BY_FORMAT[file_format]
    conn = duckdb.connect()
    try:
        # The DuckDB readers accept positional path arguments and
        # tolerate arbitrary file system paths; the SQL injection
        # surface is bounded because file_path comes from a directory
        # walk we just did, not from user input.
        cursor = conn.execute(f"SELECT * FROM {reader}(?)", [file_path])
        return cursor.fetch_arrow_table()
    finally:
        conn.close()


def _inject_audit_columns(
    arrow_table: pa.Table,
    audit_columns: tuple[str, ...],
    *,
    file_path: str,
    file_sha: str,
    source_system: str,
    ingested_at: datetime.datetime,
) -> pa.Table:
    """Append the configured audit columns to *arrow_table*.

    Skips any audit column already present on the source so a
    pre-augmented file (e.g. re-ingest of a prior bronze export)
    doesn't double-write the column.  The relative path stored in
    ``_source_file`` is just :func:`os.path.basename`-style — the
    full path is excessive in audit context and can change when an
    operator renames a Volume mount.

    The  ``_lineage_row_id`` column is computed
    deterministically from ``file_sha`` and the row's offset within
    the file, so re-ingesting the same bytes gives the same IDs and
    every silver-layer trace can walk back to the originating cell.

    Args:
        arrow_table: The data DuckDB read.
        audit_columns: The configured audit-column names.
        file_path: Source file path; the basename goes into
            ``_source_file``.
        file_sha: SHA-256 hex digest of the source file's bytes;
            seeds the deterministic ``_lineage_row_id`` per row.
        source_system: Value for ``_source_system`` (free-form).
        ingested_at: UTC instant for ``_ingested_at``.

    Returns:
        A new Arrow Table with the audit columns appended on the
        right.  Existing columns are left untouched.
    """
    if not audit_columns:
        return arrow_table

    n = arrow_table.num_rows
    base_name = Path(file_path).name
    column_values: dict[str, pa.Array] = {
        "_ingested_at": pa.array([ingested_at] * n, type=pa.timestamp("us", tz="UTC")),
        "_source_file": pa.array([base_name] * n, type=pa.string()),
        "_source_system": pa.array([source_system] * n, type=pa.string()),
        "_lineage_row_id": pa.array(
            [_row_lineage_id(file_sha, idx) for idx in range(n)],
            type=pa.string(),
        ),
    }
    augmented = arrow_table
    for name in audit_columns:
        if name in augmented.schema.names:
            continue
        if name not in column_values:
            continue
        augmented = augmented.append_column(name, column_values[name])
    return augmented


def _row_lineage_id(file_sha: str, offset: int) -> str:
    """Synthesise a deterministic per-row lineage identity.

    The result hashes ``"<file_sha>:<offset>"`` so the same row in
    the same source file always lands on the same ID — re-ingest is
    safe and downstream silver/gold rows can be traced back to the
    exact bronze row that fed them.

    Args:
        file_sha: SHA-256 hex digest of the source file's bytes.
        offset: Zero-based row offset within the file.

    Returns:
        64-character lowercase hex digest.
    """
    return hashlib.sha256(f"{file_sha}:{offset}".encode()).hexdigest()


def _sha256_file(file_path: str) -> str:
    """Return the SHA-256 hex digest of the file's bytes.

    Reads in 1-MB chunks so very large source files don't push the
    process into swap.

    Args:
        file_path: Absolute path of the file to hash.

    Returns:
        64-character lowercase hex digest.
    """
    hasher = hashlib.sha256()
    with open(file_path, "rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _checkpoint_exists(session_factory: sessionmaker[Session], target: str, sha: str) -> bool:
    """Return whether ``(target, sha)`` is already recorded.

    Args:
        session_factory: SQLAlchemy session factory.
        target: UC ``"catalog.schema.table"`` string.
        sha: SHA-256 hex digest.

    Returns:
        ``True`` when the row exists.
    """
    with session_factory() as session:
        stmt = select(AutoloadCheckpoint.id).where(
            AutoloadCheckpoint.target_table == target,
            AutoloadCheckpoint.file_sha == sha,
        )
        return session.scalar(stmt) is not None


def _record_checkpoint(
    session_factory: sessionmaker[Session],
    *,
    source_path: str,
    file_sha: str,
    target_table: str,
    ingested_at: datetime.datetime,
    rows_ingested: int,
) -> None:
    """Insert one ``autoload_checkpoints`` row.

    Args:
        session_factory: SQLAlchemy session factory.
        source_path: Source file path.
        file_sha: SHA-256 hex digest of the file's bytes.
        target_table: UC ``"catalog.schema.table"`` string.
        ingested_at: UTC timestamp the autoload appended.
        rows_ingested: Row count delivered into the target.
    """
    with session_factory() as session:
        row = AutoloadCheckpoint(
            source_path=source_path,
            file_sha=file_sha,
            target_table=target_table,
            ingested_at=ingested_at,
            rows_ingested=rows_ingested,
        )
        session.add(row)
        session.commit()


def _resolve_target_or_derive(
    client: Client,
    catalog: str,
    schema: str,
    table: str,
    full_name: str,
    unreachable_msg: str,
) -> tuple[str, bool]:
    """Resolve the target's storage location, deriving one when missing.

    Args:
        client: Configured catalog client.
        catalog: Catalog name.
        schema: Schema name.
        table: Table name.
        full_name: Three-part name (used for error messages).
        unreachable_msg: Pre-rendered "cannot reach catalog" message.

    Returns:
        ``(storage_location, target_exists)`` tuple.

    Raises:
        CatalogNotFoundError: When the table doesn't exist and no
            schema storage_root is set to derive one from
            (propagates from :func:`derive_storage_location`).
        CatalogUnavailableError: When soyuz-catalog is unreachable.
        UnexpectedStatus: For any non-404 soyuz-catalog error.
    """  # noqa: DOC502,DOC503 — CatalogNotFoundError propagates from derive_storage_location
    try:
        response = _get_table.sync(client=client, full_name=full_name)
    except httpx.ConnectError as exc:
        raise CatalogUnavailableError(unreachable_msg) from exc
    except UnexpectedStatus as exc:
        if exc.status_code != 404:
            raise
        response = None

    if isinstance(response, TableInfo):
        location = response.storage_location
        if not isinstance(location, Unset) and location:
            return (location, True)

    derived = derive_storage_location(client, catalog, schema, table)
    return (derived, False)


def _append_to_delta(target_location: str, arrow_table: pa.Table) -> None:
    """Append *arrow_table* to the Delta table at *target_location*.

    Uses ``deltalake.write_deltalake(mode="append")`` which creates
    the table on the first call.  No schema-evolution flags — the
    MVP requires the second-and-subsequent files to match the
    bootstrap schema.  Schema-drift handling is deferred.

    Args:
        target_location: Delta table storage URI.
        arrow_table: Augmented data to append.
    """
    deltalake.write_deltalake(target_location, arrow_table, mode="append")


def _register_target_in_uc(
    *,
    client: Client,
    engine: Engine,
    catalog: str,
    schema: str,
    table: str,
    location: str,
    arrow_for_columns: pa.Table,
    unreachable_msg: str,
) -> None:
    """Register a freshly-created Delta table in soyuz-catalog.

    Mirrors the catalog-side bookkeeping
    :func:`pointlessql.pql._write.write_table` does after a
    create-mode write so an autoload-bootstrapped table is
    indistinguishable from one written through the editor.

    The columns metadata is derived by handing the augmented
    Arrow table to :class:`pointlessql.pql.engine.Engine` —
    converting Arrow → engine frame is unnecessary because the
    engine's :meth:`columns_info` accepts any frame whose schema
    can be read by inspection (pandas via ``pa.Table.to_pandas``
    on the column metadata).

    Args:
        client: Configured catalog client.
        engine: PQL engine (used for column metadata).
        catalog: Catalog name.
        schema: Schema name.
        table: Table name.
        location: Storage URI of the new Delta table.
        arrow_for_columns: Arrow table whose schema describes the
            columns to register.
        unreachable_msg: Pre-rendered "cannot reach catalog" message.

    Raises:
        CatalogUnavailableError: When soyuz-catalog is unreachable.
    """
    pandas_for_meta = arrow_for_columns.to_pandas()
    columns = columns_from_tuples(engine.columns_info(pandas_for_meta))
    body = CreateTable(
        catalog_name=catalog,
        schema_name=schema,
        name=table,
        table_type="MANAGED",
        data_source_format="DELTA",
        columns=columns,
        storage_location=location,
    )
    try:
        _create_table.sync(client=client, body=body)
    except httpx.ConnectError as exc:
        raise CatalogUnavailableError(unreachable_msg) from exc
