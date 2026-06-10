"""Per-run unified row + column lineage DAG endpoint.

Backbone for the Lineage / Graph sub-tab on ``/runs/{id}``.  Joins
:class:`pointlessql.models.LineageRowEdge` and
:class:`pointlessql.models.LineageColumnMap` per ``run_id`` (and
optional ``op_id``) into a single cytoscape-shaped payload.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from pointlessql.api.dependencies import require_supervisor
from pointlessql.exceptions import CatalogNotFoundError
from pointlessql.models.agent._runs import AgentRun

router = APIRouter()


@router.get("/api/runs/{run_id}/graph")
async def api_run_graph(
    request: Request,
    run_id: str,
    op_id: int | None = Query(default=None, description="Restrict to a single op"),
) -> dict[str, Any]:
    """Return the unified row + column lineage DAG for one run.

    The route follows the auditor / supervisor scope ladder used by
    the per-run audit-axis JSON endpoints — same data already
    visible on the run-detail Lineage tab, just rearranged.  A caller
    without the supervisor or auditor scope propagates the
    :class:`pointlessql.exceptions.AuthorizationError` raised by
    :func:`require_supervisor`.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID of the run.
        op_id: Optional op filter.  When set, only edges + nodes
            touched by this op are emitted.

    Returns:
        ``{"run_id", "op_id", "nodes": [...], "edges": [...]}``.
        See :func:`pointlessql.services.lineage.graph_builder.build_lineage_graph`
        for the full per-element shape.

    Raises:
        CatalogNotFoundError: No run with that id.
    """
    require_supervisor(request)
    factory = request.app.state.session_factory
    with factory() as session:
        if session.scalar(select(AgentRun).where(AgentRun.id == run_id)) is None:
            raise CatalogNotFoundError(f"agent run {run_id!r} not found")
    from pointlessql.services.lineage.graph_builder import build_lineage_graph

    return build_lineage_graph(request, run_id, op_id=op_id)
