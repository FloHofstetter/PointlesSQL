"""Graph-shaped lineage query endpoints (D5).

Read-only any-user surface — answers ``which products are upstream of
X?``, ``which consumers depend on X?``, ``what is the path from X to
Y?``, ``how do products cluster by domain?`` without exposing the
mesh-graph payload directly.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from pointlessql.api.dependencies import current_workspace_id, require_user
from pointlessql.exceptions import BadRequestError
from pointlessql.services.lineage import _graph_query as graph_query

router = APIRouter(tags=["lineage"])


def _common(request: Request) -> tuple[Any, int]:
    require_user(request)
    return request.app.state.session_factory, current_workspace_id(request)


@router.get("/api/lineage/query/upstream")
async def lineage_upstream(
    request: Request,
    product: str,
    depth: int = 3,
    filter_kind: str | None = None,
    filter_domain: str | None = None,
) -> dict[str, Any]:
    """Return upstream producers of *product* up to *depth* hops."""
    factory, workspace_id = _common(request)
    if depth < 1 or depth > 10:
        raise BadRequestError("depth must be in [1, 10]")
    try:
        results = graph_query.find_upstream(
            factory,
            workspace_id=workspace_id,
            product_ref=product,
            depth=depth,
            filter_kind=filter_kind,
            filter_domain=filter_domain,
        )
    except LookupError as exc:
        # bare-http-ok: 404 for unknown product in lineage query; no domain exception.
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"product": product, "results": results}


@router.get("/api/lineage/query/downstream")
async def lineage_downstream(
    request: Request,
    product: str,
    depth: int = 3,
    filter_kind: str | None = None,
    filter_domain: str | None = None,
) -> dict[str, Any]:
    """Return downstream consumers of *product* up to *depth* hops."""
    factory, workspace_id = _common(request)
    if depth < 1 or depth > 10:
        raise BadRequestError("depth must be in [1, 10]")
    try:
        results = graph_query.find_downstream(
            factory,
            workspace_id=workspace_id,
            product_ref=product,
            depth=depth,
            filter_kind=filter_kind,
            filter_domain=filter_domain,
        )
    except LookupError as exc:
        # bare-http-ok: 404 for unknown product in lineage query; no domain exception.
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"product": product, "results": results}


@router.get("/api/lineage/query/path")
async def lineage_path(
    request: Request, source: str, target: str
) -> dict[str, Any]:
    """Return the shortest producer→consumer path between two products."""
    factory, workspace_id = _common(request)
    try:
        path = graph_query.find_shortest_path(
            factory,
            workspace_id=workspace_id,
            source_ref=source,
            target_ref=target,
        )
    except LookupError as exc:
        # bare-http-ok: 404 for unknown product in lineage query; no domain exception.
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"source": source, "target": target, "path": path}


@router.get("/api/lineage/query/clusters")
async def lineage_clusters(request: Request) -> dict[str, Any]:
    """Return every workspace product clustered by domain."""
    factory, workspace_id = _common(request)
    return {
        "clusters": graph_query.cluster_by_domain(
            factory, workspace_id=workspace_id
        )
    }
