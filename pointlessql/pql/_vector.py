"""``pql.vector_index()`` / ``pql.vector_search()`` — semantic retrieval.

Third PointlesSQL compute primitive next to :mod:`pointlessql.pql._merge`
and :mod:`pointlessql.pql._autoload`.  Builds and queries HNSW indices
over a text column of a Delta table using the DuckDB ``vss`` extension.

Index files live at
``<table.storage_location>/_vss/<column>.duckdb`` — colocated with the
Delta table so a table-drop sweeps the index, and a workspace export
captures it.  Delta remains the source-of-truth; the index is a
secondary structure rebuilt incrementally on every
:meth:`pointlessql.pql.PQL.merge` write via the post-commit hook in
:mod:`pointlessql.services.agent_runs.operations._vector_rebuild`.

The embedder is selected at index-creation time and persisted in the
``vector_indices`` metadata row + the index file's ``meta`` table so
later rebuilds / searches re-resolve the same provider.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import deltalake
import httpx
from soyuz_catalog_client import Client
from soyuz_catalog_client.api.tables import (
    get_table_api_2_1_unity_catalog_tables_full_name_get as _get_table,
)
from soyuz_catalog_client.models.table_info import TableInfo
from soyuz_catalog_client.types import Unset

from pointlessql.db import get_session_factory
from pointlessql.exceptions import (
    CatalogNotFoundError,
    CatalogUnavailableError,
    ValidationError,
)
from pointlessql.models.vector import VectorIndex
from pointlessql.pql._parsing import parse_full_name
from pointlessql.pql._vss_engine import open_index, read_meta, write_meta
from pointlessql.pql.embedders import Embedder, EmbedderUnavailableError, resolve_embedder
from pointlessql.types import OpName, RunId

__all__ = [
    "VectorMetric",
    "create_or_rebuild_index",
    "delete_index",
    "list_indices",
    "search",
]

logger = logging.getLogger(__name__)


VectorMetric = Literal["cosine", "l2", "ip"]

_METRIC_TO_DUCKDB_FN: dict[VectorMetric, str] = {
    "cosine": "array_cosine_similarity",
    "l2": "array_distance",
    "ip": "array_inner_product",
}
# array_distance is "lower is better"; the other two are "higher is
# better".  ``search`` flips the ORDER BY direction accordingly.
_METRIC_HIGHER_IS_BETTER: dict[VectorMetric, bool] = {
    "cosine": True,
    "l2": False,
    "ip": True,
}


def create_or_rebuild_index(
    *,
    client: Client,
    table: str,
    column: str,
    dim: int | None,
    model: str,
    embedder: str | Embedder,
    metric: VectorMetric,
    hnsw_m: int,
    hnsw_ef_construction: int,
    rebuild: bool,
    unreachable_msg: str,
    agent_run_id: RunId | None,
    workspace_id: int | None,
) -> dict[str, Any]:
    """Create (or fully rebuild) a vector index over *table.column*.

    Args:
        client: Configured catalog client.
        table: Three-part UC FQN.
        column: Source text column on *table*.
        dim: Output vector dimensionality.  ``None`` lets the
            embedder pick (recommended unless the caller wants to
            assert a specific dim).
        model: Provider-specific model identifier.
        embedder: Either an embedder registry key or a live instance.
        metric: Similarity metric — ``"cosine"`` is the default in
            the public API and the only one indexed for fast top-K
            on most workloads.
        hnsw_m: HNSW ``m`` (max-neighbours) build parameter.
            duckdb-vss default 16 is sane for ≤1M rows.
        hnsw_ef_construction: HNSW build-time candidate list size.
            duckdb-vss default 128 is sane for ≤1M rows.
        rebuild: When ``True``, drop and rebuild the index file
            even if the row count is unchanged.
        unreachable_msg: Pre-rendered "cannot reach catalog" message.
        agent_run_id: Run UUID for audit-trail attribution.
        workspace_id: PointlesSQL workspace owning this index — set on
            the ``vector_indices`` row.  ``None`` is allowed only when
            the metadata-DB session factory is not bound (interactive
            REPL outside the FastAPI lifespan).

    Returns:
        Dict with the resolved ``index_id``, ``path``, ``dim``,
        ``rows_indexed``, ``delta_version_indexed``, etc.

    Raises:
        CatalogNotFoundError: Target table not in soyuz-catalog or
            has no ``storage_location``.
        CatalogUnavailableError: soyuz-catalog is unreachable.
        ValidationError: ``column`` not present on *table* or the
            column is not a string type.
        EmbedderUnavailableError: Backing embedder library not
            installed / API not reachable.
    """  # noqa: DOC502,DOC503 — bubble up from helpers
    from pointlessql.services.agent_runs import operation_context

    catalog, schema, table_name = parse_full_name(table)
    storage_location = _resolve_storage_location(client, table, unreachable_msg)
    embedder_instance = resolve_embedder(embedder, model=model)
    resolved_dim = embedder_instance.dim
    if dim is not None and dim != resolved_dim:
        raise ValidationError(
            f"requested dim {dim} does not match embedder {embedder_instance.name!r} "
            f"({embedder_instance.model!r}) dim {resolved_dim}"
        )
    index_path = _index_file_path(storage_location, column)

    params = {
        "table": table,
        "column": column,
        "embedder": embedder_instance.name,
        "model": embedder_instance.model,
        "metric": metric,
        "rebuild": rebuild,
    }
    with operation_context(
        _session_factory_or_none(),
        agent_run_id=agent_run_id,
        op_name=OpName.VECTOR_INDEX,
        params=params,
        target_table=table,
    ) as recorder:
        if rebuild and index_path.exists():
            index_path.unlink()

        delta_table = deltalake.DeltaTable(storage_location)
        delta_version = delta_table.version()
        column_data, pk_payloads = _read_column_with_pks(delta_table, column)
        rows_indexed = len(column_data)

        recorder.delta_version_before = delta_version

        vectors = embedder_instance.embed(column_data) if rows_indexed else []
        conn = open_index(index_path, dim=resolved_dim)
        try:
            conn.execute("DELETE FROM embeddings")
            if rows_indexed:
                rows_to_insert = [
                    (i, json.dumps(pk_payloads[i]), column_data[i], vectors[i])
                    for i in range(rows_indexed)
                ]
                conn.executemany(
                    "INSERT INTO embeddings (rowid, pk_json, source_text, vector) "
                    "VALUES (?, ?, ?, ?)",
                    rows_to_insert,
                )
            # Drop + recreate the HNSW index so dim / param changes
            # take effect on rebuild.  duckdb-vss does not currently
            # support ALTER on an HNSW index.
            conn.execute("DROP INDEX IF EXISTS hnsw_idx")
            if rows_indexed:
                conn.execute(
                    f"CREATE INDEX hnsw_idx ON embeddings "
                    f"USING HNSW (vector) "
                    f"WITH (metric = '{metric}', m = {hnsw_m}, "
                    f"ef_construction = {hnsw_ef_construction})"
                )
            built_at = datetime.now(UTC)
            write_meta(
                conn,
                column=column,
                dim=resolved_dim,
                model=embedder_instance.model,
                embedder=embedder_instance.name,
                metric=metric,
                hnsw_m=hnsw_m,
                hnsw_ef_construction=hnsw_ef_construction,
                delta_version_indexed=delta_version,
                built_at=built_at.isoformat(),
                rows_indexed=rows_indexed,
            )
        finally:
            conn.close()

        # ``vector_indices`` is the workspace-scoped metadata table the
        # merge hook + REST list endpoint read from.  When the session
        # factory is not bound (interactive REPL outside FastAPI), we
        # skip the row — the index file on disk is still usable, but
        # the UI tab + auto-rebuild only kick in once the server can
        # discover the index.
        index_id: int | None = None
        session_factory = _session_factory_or_none()
        if session_factory is not None:
            with session_factory() as session:
                index_id = _upsert_vector_index(
                    session,
                    workspace_id=workspace_id,
                    catalog=catalog,
                    schema=schema,
                    table=table_name,
                    column=column,
                    dim=resolved_dim,
                    model=embedder_instance.model,
                    embedder=embedder_instance.name,
                    metric=metric,
                    hnsw_m=hnsw_m,
                    hnsw_ef_construction=hnsw_ef_construction,
                    index_path=str(index_path),
                    delta_version_indexed=delta_version,
                    last_built_at=built_at,
                    last_built_rows=rows_indexed,
                )
                session.commit()

        recorder.rows_affected = rows_indexed
        recorder.delta_version_after = delta_version
        recorder.extra_params["rows_indexed"] = rows_indexed
        recorder.extra_params["embedder"] = embedder_instance.name
        recorder.extra_params["dim"] = resolved_dim

    return {
        "index_id": index_id,
        "table_fqn": table,
        "column": column,
        "rows_indexed": rows_indexed,
        "dim": resolved_dim,
        "model": embedder_instance.model,
        "embedder": embedder_instance.name,
        "metric": metric,
        "path": str(index_path),
        "built_at": built_at.isoformat(),
        "delta_version_indexed": delta_version,
    }


def search(
    *,
    client: Client,
    table: str,
    column: str,
    query: str,
    top_k: int,
    unreachable_msg: str,
    embedder_override: Embedder | None = None,
) -> dict[str, Any]:
    """Run a top-K vector search against an existing index.

    Args:
        client: Configured catalog client.
        table: Three-part UC FQN.
        column: Source column on *table* — must already have an
            index.
        query: Free-text query.  Embedded with the same provider
            that built the index unless *embedder_override* is set.
        top_k: Number of hits to return (1–200).
        unreachable_msg: Pre-rendered "cannot reach catalog" message.
        embedder_override: For test injection — pass a fake embedder
            to make search deterministic.  Production callers leave
            this ``None``.

    Returns:
        Dict with ``table``, ``column``, ``model``, ``embedder``,
        ``delta_version_indexed``, and ``hits`` (list of dicts with
        ``score``, ``pk``, ``snippet``).

    Raises:
        CatalogNotFoundError: Target table not in catalog.
        FileNotFoundError: No index file exists for the column.
        EmbedderUnavailableError: Embedder cannot be resolved.
    """  # noqa: DOC502,DOC503 — bubble up from helpers
    storage_location = _resolve_storage_location(client, table, unreachable_msg)
    index_path = _index_file_path(storage_location, column)
    if not index_path.exists():
        raise FileNotFoundError(
            f"no vector index for {table}.{column} — call pql.vector_index() first"
        )
    conn = open_index(index_path, dim=0, read_only=True)
    try:
        meta = read_meta(conn)
        embedder_name = str(meta.get("embedder") or "sentence_transformers")
        model = str(meta.get("model") or "")
        metric = cast(VectorMetric, str(meta.get("metric") or "cosine"))
        dim = int(meta.get("dim") or 0)

        if embedder_override is not None:
            embedder_instance: Embedder = embedder_override
        else:
            embedder_instance = resolve_embedder(embedder_name, model=model or None)
        if embedder_instance.dim != dim:
            raise EmbedderUnavailableError(
                f"embedder {embedder_instance.name!r} dim {embedder_instance.dim} "
                f"does not match index dim {dim} (model drift?)"
            )

        query_vector = embedder_instance.embed([query])[0]
        fn = _METRIC_TO_DUCKDB_FN[metric]
        direction = "DESC" if _METRIC_HIGHER_IS_BETTER[metric] else "ASC"
        rows = conn.execute(
            f"SELECT rowid, pk_json, source_text, "
            f"{fn}(vector, CAST(? AS FLOAT[{dim}])) AS score "
            f"FROM embeddings ORDER BY score {direction} LIMIT ?",
            [query_vector, top_k],
        ).fetchall()
    finally:
        conn.close()

    hits = [
        {
            "score": float(row[3]),
            "pk": json.loads(row[1]) if row[1] else {"_row_index": row[0]},
            "snippet": _truncate(row[2], 240),
        }
        for row in rows
    ]
    return {
        "table": table,
        "column": column,
        "model": model,
        "embedder": embedder_name,
        "metric": metric,
        "delta_version_indexed": int(meta.get("delta_version_indexed") or 0),
        "hits": hits,
    }


def list_indices(*, workspace_id: int, table: str | None = None) -> list[VectorIndex]:
    """Return ``vector_indices`` rows for a workspace, optionally filtered.

    Args:
        workspace_id: PointlesSQL workspace id.
        table: Optional three-part FQN filter.  ``None`` returns all
            indices for the workspace.

    Returns:
        List of :class:`VectorIndex` ORM rows (may be empty).
    """
    session_factory = get_session_factory()
    with session_factory() as session:
        stmt = _select_indices(session, workspace_id, table)
        return list(stmt)


def delete_index(*, workspace_id: int, index_id: str) -> Path | None:
    """Delete an index by id; remove the on-disk file.

    Args:
        workspace_id: Workspace owning the index.
        index_id: Row UUID (matches ``meta.index_id`` inside the file
            and ``vector_indices.id`` in the metadata DB).

    Returns:
        The :class:`Path` of the removed file, or ``None`` when the
        row did not exist.
    """
    session_factory = get_session_factory()
    with session_factory() as session:
        row = (
            session.query(VectorIndex)
            .filter_by(workspace_id=workspace_id, id=index_id)
            .one_or_none()
        )
        if row is None:
            return None
        path = Path(row.index_path)
        session.delete(row)
        session.commit()
    if path.exists():
        path.unlink()
    return path


def _index_file_path(storage_location: str, column: str) -> Path:
    # Soyuz returns ``storage_location`` as a ``file://`` URI for managed
    # tables; ``deltalake`` handles that natively but DuckDB's
    # ``connect()`` expects a plain filesystem path.  Strip the scheme
    # so the same call site works for both Delta reads and DuckDB index
    # opens.  Non-``file://`` schemes (s3://, abfss://) intentionally
    # fall through — vector-search currently only supports local Delta.
    if storage_location.startswith("file://"):
        storage_location = storage_location[len("file://") :]
    base = Path(storage_location.rstrip("/"))
    return base / "_vss" / f"{column}.duckdb"


def _resolve_storage_location(client: Client, full_name: str, unreachable_msg: str) -> str:
    """Mirror of ``_merge._resolve_target_location`` for the vector path.

    Kept local rather than imported because the merge helper is
    private.  Both modules want the same behaviour: fetch
    ``TableInfo.storage_location``, raise on missing.
    """
    try:
        response = _get_table.sync(client=client, full_name=full_name)
    except httpx.ConnectError as exc:
        raise CatalogUnavailableError(unreachable_msg) from exc
    if not isinstance(response, TableInfo):
        raise CatalogNotFoundError(f"vector-index target {full_name!r} not found in soyuz-catalog")
    location = response.storage_location
    if isinstance(location, Unset) or not location:
        raise CatalogNotFoundError(f"vector-index target {full_name!r} has no storage_location")
    return location


def _read_column_with_pks(
    delta_table: deltalake.DeltaTable, column: str
) -> tuple[list[str], list[dict[str, Any]]]:
    """Read *column* and primary-key payloads from *delta_table*.

    Args:
        delta_table: Open :class:`deltalake.DeltaTable`.
        column: Name of the text column to materialise.

    Returns:
        Tuple of (text values, per-row pk payloads).  Rows whose
        column value is null are dropped; the pk payload preserves
        the post-drop ordering so search results can be joined back
        to the original Delta row.

    Raises:
        ValidationError: When *column* is not present on the table.
    """
    arrow_table = delta_table.to_pyarrow_table(columns=None)
    if column not in arrow_table.column_names:
        raise ValidationError(
            f"column {column!r} not present on Delta table (columns: {arrow_table.column_names!r})"
        )
    pk_columns = _resolve_pk_columns(delta_table, arrow_table.column_names)
    text_values: list[str] = []
    pk_payloads: list[dict[str, Any]] = []
    column_idx = arrow_table.column_names.index(column)
    column_data = arrow_table.column(column_idx).to_pylist()
    for row_idx, value in enumerate(column_data):
        if value is None:
            continue
        text_values.append(str(value))
        pk_payloads.append(_extract_pk(arrow_table, pk_columns, row_idx))
    return text_values, pk_payloads


def _resolve_pk_columns(
    delta_table: deltalake.DeltaTable, available_columns: list[str]
) -> list[str]:
    """Return the primary-key column names for *delta_table*.

    Delta does not enforce primary keys, but tables created via
    ``pql.write_table`` carry a ``_lineage_row_id`` column we prefer.
    Falling back to ``_row_index`` keeps the search result joinable
    via positional rowid.
    """
    if "_lineage_row_id" in available_columns:
        return ["_lineage_row_id"]
    metadata = delta_table.metadata()
    user_metadata = metadata.configuration or {}
    declared = user_metadata.get("delta.constraints.primaryKey")
    if declared:
        parts = [c.strip() for c in declared.split(",") if c.strip()]
        if all(p in available_columns for p in parts):
            return parts
    return []


def _extract_pk(arrow_table: Any, pk_columns: list[str], row_idx: int) -> dict[str, Any]:
    if not pk_columns:
        return {"_row_index": row_idx}
    out: dict[str, Any] = {}
    for col in pk_columns:
        idx = arrow_table.column_names.index(col)
        out[col] = arrow_table.column(idx)[row_idx].as_py()
    return out


def _truncate(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _session_factory_or_none() -> Any:
    """Return the bound session factory, or ``None`` when unbound."""
    try:
        return get_session_factory()
    except RuntimeError:
        return None


def _upsert_vector_index(
    session: Any,
    *,
    workspace_id: int | None,
    catalog: str,
    schema: str,
    table: str,
    column: str,
    dim: int,
    model: str,
    embedder: str,
    metric: str,
    hnsw_m: int,
    hnsw_ef_construction: int,
    index_path: str,
    delta_version_indexed: int,
    last_built_at: datetime,
    last_built_rows: int,
) -> int | None:
    if workspace_id is None:
        return None
    existing = (
        session.query(VectorIndex)
        .filter_by(
            workspace_id=workspace_id,
            catalog=catalog,
            schema=schema,
            table=table,
            column=column,
        )
        .one_or_none()
    )
    if existing is None:
        row = VectorIndex(
            workspace_id=workspace_id,
            catalog=catalog,
            schema=schema,
            table=table,
            column=column,
            dim=dim,
            model=model,
            embedder=embedder,
            metric=metric,
            hnsw_m=hnsw_m,
            hnsw_ef_construction=hnsw_ef_construction,
            index_path=index_path,
            delta_version_indexed=delta_version_indexed,
            last_built_at=last_built_at,
            last_built_rows=last_built_rows,
            last_error=None,
        )
        session.add(row)
        session.flush()
        return int(row.id)
    existing.dim = dim
    existing.model = model
    existing.embedder = embedder
    existing.metric = metric
    existing.hnsw_m = hnsw_m
    existing.hnsw_ef_construction = hnsw_ef_construction
    existing.index_path = index_path
    existing.delta_version_indexed = delta_version_indexed
    existing.last_built_at = last_built_at
    existing.last_built_rows = last_built_rows
    existing.last_error = None
    return int(existing.id)


def _select_indices(session: Any, workspace_id: int, table: str | None) -> Any:
    q = session.query(VectorIndex).filter_by(workspace_id=workspace_id)
    if table:
        catalog, schema, table_name = parse_full_name(table)
        q = q.filter_by(catalog=catalog, schema=schema, table=table_name)
    return q.order_by(
        VectorIndex.catalog,
        VectorIndex.schema,
        VectorIndex.table,
        VectorIndex.column,
    )
