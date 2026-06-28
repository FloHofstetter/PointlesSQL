# pyright: reportUnusedFunction=false
# These are package-internal helpers for the autoload orchestrator in
# this package's __init__; they are 'unused' only within this sub-module.
"""Audit-column injection + autoload lineage column edges.

Internal helpers for :func:`pointlessql.pql.autoload`.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from pointlessql.services.lineage_edges import ColumnEdgeSpec

import deltalake
import pyarrow as pa

from pointlessql.conventions import ConventionsConfig
from pointlessql.pql._storage_options import storage_options_for
from pointlessql.pql._types import (
    ArrowArray,
    ArrowTable,
    DeltaSchema,
)

logger = logging.getLogger(__name__)


def _build_autoload_column_edges(
    *,
    target_location: str,
    target: str,
    audit_columns: tuple[str, ...],
    source_volume_fqn: str | None,
) -> list[ColumnEdgeSpec]:
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
        schema = cast(
            DeltaSchema,
            deltalake.DeltaTable(
                target_location, storage_options=storage_options_for(target_location)
            ).schema(),
        )
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


def _inject_audit_columns(
    arrow_table: ArrowTable,
    audit_columns: tuple[str, ...],
    *,
    file_path: str,
    file_sha: str,
    source_system: str,
    ingested_at: datetime.datetime,
) -> ArrowTable:
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
    column_values: dict[str, ArrowArray] = {
        "_ingested_at": cast(
            ArrowArray,
            pa.array([ingested_at] * n, type=pa.timestamp("us", tz="UTC")),
        ),
        "_source_file": cast(ArrowArray, pa.array([base_name] * n, type=pa.string())),
        "_source_system": cast(ArrowArray, pa.array([source_system] * n, type=pa.string())),
        "_lineage_row_id": cast(
            ArrowArray,
            pa.array(
                [_row_lineage_id(file_sha, idx) for idx in range(n)],
                type=pa.string(),
            ),
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
