"""``/api/sql/vector_search/indices`` — index admin endpoints.

* ``POST /api/sql/vector_search/indices`` — create / rebuild.
  Workspace-admin only.  Long-running; runs the embed pass on a
  thread.
* ``GET  /api/sql/vector_search/indices?table=…`` — list indices
  filtered by table (or all for the workspace).  Any authenticated
  user.
* ``DELETE /api/sql/vector_search/indices/{id}`` — drop the row
  and remove the on-disk file.  Workspace-admin only.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, Request

from pointlessql.api._audit_helpers import audit, effective_agent_run_id
from pointlessql.api.dependencies import (
    current_workspace_id,
    effective_principal,
    get_user,
    require_workspace_admin,
)
from pointlessql.api.sql.vector_search._models import (
    VectorIndexCreateRequest,
    VectorIndexSummary,
)
from pointlessql.db import get_session_factory
from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.models.vector import VectorIndex
from pointlessql.pql._parsing import parse_full_name
from pointlessql.pql._vector import create_or_rebuild_index
from pointlessql.services._executor import run_sync
from pointlessql.services.soyuz_client import make_principal_client, make_soyuz_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sql", "vector-search"])


@router.post(
    "/api/sql/vector_search/indices",
    response_model=VectorIndexSummary,
    status_code=201,
)
async def api_vector_index_create(
    request: Request, body: VectorIndexCreateRequest
) -> VectorIndexSummary:
    """Create or rebuild a vector index over ``table.column``.

    Propagates :class:`AuthorizationError` from
    :func:`require_workspace_admin` when the caller is not a
    workspace admin, :class:`ValidationError` from
    :func:`parse_full_name` when the table FQN is not three-part,
    and :class:`CatalogNotFoundError` /
    :class:`EmbedderUnavailableError` from
    :func:`create_or_rebuild_index` when the target table is
    unknown or the requested embedder cannot be resolved (e.g.
    ``[vector]`` extra not installed).

    Args:
        request: Incoming FastAPI request.
        body: Validated request body.

    Returns:
        The newly-persisted :class:`VectorIndexSummary` row.
    """
    require_workspace_admin(request)
    parse_full_name(body.table)
    settings = request.app.state.settings
    workspace_id = current_workspace_id(request)

    principal = effective_principal(request)
    if principal:
        client = make_principal_client(settings, principal)
    else:
        client = make_soyuz_client(settings)
    unreachable_msg = f"soyuz-catalog at {settings.soyuz.catalog_url} is unreachable."

    agent_run_id = effective_agent_run_id(request)
    stats = await run_sync(
        create_or_rebuild_index,
        client=client,
        table=body.table,
        column=body.column,
        dim=None,
        model=body.model,
        embedder=body.embedder,
        metric=body.metric,
        hnsw_m=body.hnsw_m,
        hnsw_ef_construction=body.hnsw_ef_construction,
        rebuild=body.rebuild,
        unreachable_msg=unreachable_msg,
        agent_run_id=agent_run_id,  # type: ignore[arg-type]
        workspace_id=workspace_id,
    )
    audit_metadata: dict[str, Any] = {
        "table": body.table,
        "column": body.column,
        "model": stats.get("model"),
        "embedder": stats.get("embedder"),
        "dim": stats.get("dim"),
        "rows_indexed": stats.get("rows_indexed"),
        "rebuild": body.rebuild,
    }
    await audit(request, "sql.vector_index.create", body.table, audit_metadata)

    return _to_summary_dict(stats, table_fqn=body.table)


@router.get(
    "/api/sql/vector_search/indices",
    response_model=list[VectorIndexSummary],
)
async def api_vector_index_list(
    request: Request,
    table: str | None = Query(None, description="Optional 3-part table FQN filter."),
) -> list[VectorIndexSummary]:
    """List vector indices for the current workspace, optionally filtered.

    Args:
        request: Incoming FastAPI request.
        table: Optional 3-part FQN filter.  ``None`` returns every
            index in the workspace.

    Returns:
        A list of :class:`VectorIndexSummary` rows; empty when none
        match.
    """
    get_user(request)
    workspace_id = current_workspace_id(request)
    session_factory = get_session_factory()
    with session_factory() as session:
        q = session.query(VectorIndex).filter_by(workspace_id=workspace_id)
        if table:
            catalog, schema, table_name = parse_full_name(table)
            q = q.filter_by(catalog=catalog, schema=schema, table=table_name)
        q = q.order_by(
            VectorIndex.catalog,
            VectorIndex.schema,
            VectorIndex.table,
            VectorIndex.column,
        )
        rows = list(q)
    return [_row_to_summary(r) for r in rows]


@router.delete(
    "/api/sql/vector_search/indices/{index_id}",
    status_code=204,
)
async def api_vector_index_delete(request: Request, index_id: int) -> None:
    """Delete a vector index by id and remove its on-disk file.

    Propagates :class:`AuthorizationError` from
    :func:`require_workspace_admin` when the caller is not a
    workspace admin.

    Args:
        request: Incoming FastAPI request.
        index_id: Auto-increment id of the ``vector_indices`` row.

    Raises:
        ResourceNotFoundError: When the index row does not exist in
            the caller's workspace (rendered as a 404).
    """
    require_workspace_admin(request)
    workspace_id = current_workspace_id(request)
    session_factory = get_session_factory()
    with session_factory() as session:
        row = (
            session.query(VectorIndex)
            .filter_by(workspace_id=workspace_id, id=index_id)
            .one_or_none()
        )
        if row is None:
            raise ResourceNotFoundError("vector index not found")
        target_fqn = f"{row.catalog}.{row.schema}.{row.table}"
        index_path = Path(row.index_path)
        column = row.column
        session.delete(row)
        session.commit()
    if index_path.exists():
        try:
            index_path.unlink()
        except OSError:
            logger.warning("vector_index_delete: failed to unlink %s", index_path, exc_info=True)
    # ``_vss/`` is a per-table directory we own end-to-end.  If the
    # just-removed index was the last one for the table, the dir
    # is now empty and serves no purpose — clean it up so a stale
    # empty dir does not linger on disk forever.  Non-empty (other
    # column indices) → ``rmdir`` raises ``OSError`` which we swallow.
    parent = index_path.parent
    if parent.exists() and parent.name == "_vss":
        try:
            parent.rmdir()
        except OSError:
            pass
    await audit(
        request,
        "sql.vector_index.delete",
        target_fqn,
        {"column": column, "id": index_id},
    )


def _row_to_summary(row: VectorIndex) -> VectorIndexSummary:
    return VectorIndexSummary(
        id=row.id,
        table=f"{row.catalog}.{row.schema}.{row.table}",
        column=row.column,
        dim=row.dim,
        model=row.model,
        embedder=row.embedder,
        metric=row.metric,
        delta_version_indexed=row.delta_version_indexed,
        last_built_at=row.last_built_at.isoformat() if row.last_built_at else None,
        last_built_rows=row.last_built_rows,
        last_error=row.last_error,
    )


def _to_summary_dict(stats: dict[str, Any], *, table_fqn: str) -> VectorIndexSummary:
    return VectorIndexSummary(
        id=int(stats.get("index_id") or 0),
        table=table_fqn,
        column=str(stats["column"]),
        dim=int(stats["dim"]),
        model=str(stats["model"]),
        embedder=str(stats["embedder"]),
        metric=str(stats.get("metric") or "cosine"),
        delta_version_indexed=int(stats.get("delta_version_indexed") or 0),
        last_built_at=str(stats.get("built_at")) if stats.get("built_at") else None,
        last_built_rows=int(stats.get("rows_indexed") or 0),
        last_error=None,
    )
