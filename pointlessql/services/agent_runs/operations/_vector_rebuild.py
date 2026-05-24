"""post-commit hook that auto-rebuilds vector indices.

Wired into :func:`pointlessql.services.agent_runs.operations._lifecycle.operation_context`
as the sixth post-commit hook, fired after the contract-event hook
on the success path.  Looks up any ``vector_indices`` rows that
target the just-mutated table and rebuilds each one against the
current Delta snapshot.

Failure semantics are deliberately **non-fatal**: the source
operation has already committed.  A rebuild failure logs, stamps
``vector_indices.last_error``, and emits an
``AgentRunEvent`` so the UI can surface staleness — it never
re-raises into the primitive's caller.
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import deltalake

from pointlessql.models import VectorIndex
from pointlessql.pql._parsing import parse_full_name
from pointlessql.pql._vss_engine import open_index, write_meta
from pointlessql.pql.embedders import EmbedderUnavailableError, resolve_embedder

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

    from pointlessql.types import OpId, RunId

logger = logging.getLogger(__name__)


# Op names that mutate Delta tables — only these trigger a rebuild.
# ``vector_index`` itself does not (the primitive owns its file
# already); ``vector_search`` is pure read.
_REBUILD_TRIGGER_OPS: frozenset[str] = frozenset({
    "merge",
    "write_table",
    "autoload",
    "update",
    "delete",
    "sql",
    "aggregate",
    "rollback",
    "branch_promote",
    "dbt_model",
})


def rebuild_vss_indices_after_commit(
    session_factory: sessionmaker[Session] | None,
    *,
    op_id: OpId | None,
    agent_run_id: RunId | None,
    op_name: str,
    target_table: str | None,
    error_message: str | None,
) -> None:
    """Rebuild any vector indices targeting *target_table*.

    Args:
        session_factory: Bound SQLAlchemy session factory.  ``None``
            disables the hook (interactive REPL outside the FastAPI
            lifespan).
        op_id: The just-written ``agent_run_operations`` row id.
            Used for log correlation only.
        agent_run_id: Owning run, for ``AgentRunEvent`` attribution.
        op_name: The wrapped operation's op name.  Only the entries
            in :data:`_REBUILD_TRIGGER_OPS` trigger a rebuild —
            others (``branch_create``, ``vector_search``, etc.)
            short-circuit immediately.
        target_table: Three-part UC FQN the operation targeted.
            ``None`` for read-only or untargeted ops; short-circuits
            the hook.
        error_message: ``None`` on the success path; set when the
            wrapped block raised.  Set short-circuits the hook so
            we never rebuild against an uncommitted Delta version.
    """
    if session_factory is None:
        return
    if error_message is not None or target_table is None:
        return
    if op_name not in _REBUILD_TRIGGER_OPS:
        return

    try:
        catalog, schema, table_name = parse_full_name(target_table)
    except Exception:  # noqa: BLE001 — non-3-part FQN is silently skipped
        # bare-broad-ok: parse_full_name catches malformed FQNs by design
        logger.debug("vss_rebuild: target_table %r is not a 3-part name", target_table)
        return

    with session_factory() as session:
        rows = list(
            session.query(VectorIndex)
            .filter_by(catalog=catalog, schema=schema, table=table_name)
            .all()
        )
        for row in rows:
            try:
                stats = _rebuild_one(row)
            except Exception as exc:  # noqa: BLE001 — non-fatal log
                logger.exception(
                    "vss_rebuild: failed for index %s table=%s.%s.%s column=%s op_id=%s",
                    row.id,
                    catalog,
                    schema,
                    table_name,
                    row.column,
                    op_id,
                )
                row.last_error = repr(exc)
                row.updated_at = datetime.datetime.now(datetime.UTC)
                continue
            row.last_error = None
            row.delta_version_indexed = int(stats["delta_version"])  # type: ignore[arg-type]
            row.last_built_at = stats["built_at"]  # type: ignore[assignment]
            row.last_built_rows = int(stats["rows_indexed"])  # type: ignore[arg-type]
            row.updated_at = datetime.datetime.now(datetime.UTC)
        session.commit()


def _rebuild_one(row: VectorIndex) -> dict[str, object]:
    """Rebuild *row*'s on-disk index against the current Delta snapshot.

    Args:
        row: The :class:`VectorIndex` row whose on-disk file is to
            be rebuilt.

    Returns:
        Dict with ``delta_version``, ``rows_indexed``, ``built_at``.

    Raises:
        EmbedderUnavailableError: Embedder dim no longer matches the
            persisted dim (model drift since the index was built).
        RuntimeError: The indexed column has been dropped from the
            source Delta table.
    """  # noqa: DOC502,DOC503 — caller (hook) catches and stamps last_error
    index_path = Path(row.index_path)
    storage_location = str(index_path.parent.parent)
    delta_table = deltalake.DeltaTable(storage_location)
    delta_version = delta_table.version()

    arrow_table = delta_table.to_pyarrow_table(columns=None)
    if row.column not in arrow_table.column_names:
        raise RuntimeError(
            f"column {row.column!r} no longer present on table "
            f"{row.catalog}.{row.schema}.{row.table}"
        )

    embedder = resolve_embedder(row.embedder, model=row.model)
    if embedder.dim != row.dim:
        raise EmbedderUnavailableError(
            f"embedder {embedder.name!r} dim {embedder.dim} does not match "
            f"persisted dim {row.dim} (model drift?)"
        )

    column_idx = arrow_table.column_names.index(row.column)
    column_data = arrow_table.column(column_idx).to_pylist()
    pk_columns = ["_lineage_row_id"] if "_lineage_row_id" in arrow_table.column_names else []
    text_values: list[str] = []
    pk_payloads: list[dict[str, object]] = []
    for row_idx, value in enumerate(column_data):
        if value is None:
            continue
        text_values.append(str(value))
        if pk_columns:
            pk_idx = arrow_table.column_names.index(pk_columns[0])
            pk_payloads.append({pk_columns[0]: arrow_table.column(pk_idx)[row_idx].as_py()})
        else:
            pk_payloads.append({"_row_index": row_idx})

    rows_indexed = len(text_values)
    vectors = embedder.embed(text_values) if rows_indexed else []
    built_at = datetime.datetime.now(datetime.UTC)
    conn = open_index(index_path, dim=row.dim)
    try:
        conn.execute("DELETE FROM embeddings")
        if rows_indexed:
            import json as _json

            payload = [
                (i, _json.dumps(pk_payloads[i]), text_values[i], vectors[i])
                for i in range(rows_indexed)
            ]
            conn.executemany(
                "INSERT INTO embeddings (rowid, pk_json, source_text, vector) "
                "VALUES (?, ?, ?, ?)",
                payload,
            )
        conn.execute("DROP INDEX IF EXISTS hnsw_idx")
        if rows_indexed:
            conn.execute(
                f"CREATE INDEX hnsw_idx ON embeddings "
                f"USING HNSW (vector) "
                f"WITH (metric = '{row.metric}', m = {row.hnsw_m}, "
                f"ef_construction = {row.hnsw_ef_construction})"
            )
        write_meta(
            conn,
            delta_version_indexed=delta_version,
            built_at=built_at.isoformat(),
            rows_indexed=rows_indexed,
        )
    finally:
        conn.close()
    return {
        "delta_version": delta_version,
        "rows_indexed": rows_indexed,
        "built_at": built_at,
    }
