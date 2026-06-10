"""Load / save / list / fetch-version routes for the canvas document."""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import select

from pointlessql.api.data_products_routes.canvas._helpers import (
    load_dp,
    require_dp_write,
    resolve_dp_refs,
)
from pointlessql.api.data_products_routes.canvas._schemas import (
    CanvasLoadResponse,
    CanvasLoadVersionResponse,
    CanvasSaveRequest,
    CanvasSaveResponse,
    CanvasVersionEntry,
    CanvasVersionsResponse,
)
from pointlessql.api.dependencies import get_user, require_user
from pointlessql.exceptions import ResourceNotFoundError, ValidationError
from pointlessql.models import DataProductCanvasGraph
from pointlessql.services.dp_canvas import CanvasDoc, load_latest_graph, save_graph

router = APIRouter(prefix="/api/dp", tags=["data-products-canvas"])


@router.get("/{dp_id}/canvas", response_model=CanvasLoadResponse)
def get_canvas(dp_id: int, request: Request) -> CanvasLoadResponse:
    """Return the most recent saved canvas document for *dp_id*."""
    require_user(request)
    load_dp(request, dp_id)
    factory = request.app.state.session_factory
    result = load_latest_graph(factory, data_product_id=dp_id)
    if result is None:
        return CanvasLoadResponse(document=None, version=None, created_at=None)
    doc, version = result
    with factory() as session:
        row = session.execute(
            select(DataProductCanvasGraph).where(
                DataProductCanvasGraph.data_product_id == dp_id,
                DataProductCanvasGraph.version == version,
            )
        ).scalar_one()
        created_at = row.created_at
    return CanvasLoadResponse(document=doc, version=version, created_at=created_at)


@router.post("/{dp_id}/canvas", response_model=CanvasSaveResponse)
def save_canvas(dp_id: int, body: CanvasSaveRequest, request: Request) -> CanvasSaveResponse:
    """Persist *body.document* as the next version for *dp_id*."""
    require_user(request)
    user = get_user(request)
    row = load_dp(request, dp_id)
    require_dp_write(user, row)
    factory = request.app.state.session_factory

    if body.expected_base_version is not None:
        existing = load_latest_graph(factory, data_product_id=dp_id)
        existing_version = existing[1] if existing else 0
        if existing_version != body.expected_base_version:
            raise ValidationError(
                f"canvas save conflict: caller expected v{body.expected_base_version} "
                f"but latest is v{existing_version}"
            )

    actor_id = int(user["id"]) if user["id"] > 0 else None
    resolved_doc = resolve_dp_refs(request, body.document)
    new_version = save_graph(
        factory,
        data_product_id=dp_id,
        doc=resolved_doc,
        author_user_id=actor_id,
    )
    with factory() as session:
        saved = session.execute(
            select(DataProductCanvasGraph).where(
                DataProductCanvasGraph.data_product_id == dp_id,
                DataProductCanvasGraph.version == new_version,
            )
        ).scalar_one()
        created_at = saved.created_at
    return CanvasSaveResponse(version=new_version, created_at=created_at)


@router.get("/{dp_id}/canvas/versions", response_model=CanvasVersionsResponse)
def list_canvas_versions(dp_id: int, request: Request) -> CanvasVersionsResponse:
    """List saved canvas versions for *dp_id* newest-first."""
    require_user(request)
    load_dp(request, dp_id)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = (
            session.execute(
                select(DataProductCanvasGraph)
                .where(DataProductCanvasGraph.data_product_id == dp_id)
                .order_by(DataProductCanvasGraph.version.desc())
            )
            .scalars()
            .all()
        )
    entries = [
        CanvasVersionEntry(
            version=r.version,
            created_at=r.created_at,
            author_user_id=r.author_user_id,
            is_production=bool(r.is_production),
        )
        for r in rows
    ]
    pinned = next((e.version for e in entries if e.is_production), None)
    return CanvasVersionsResponse(versions=entries, pinned_version=pinned)


@router.get("/{dp_id}/canvas/versions/{version}", response_model=CanvasLoadVersionResponse)
def load_canvas_version(dp_id: int, version: int, request: Request) -> CanvasLoadVersionResponse:
    """Return the canvas document for a specific stored version."""
    require_user(request)
    load_dp(request, dp_id)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(DataProductCanvasGraph).where(
                DataProductCanvasGraph.data_product_id == dp_id,
                DataProductCanvasGraph.version == version,
            )
        ).scalar_one_or_none()
    if row is None:
        raise ResourceNotFoundError(f"canvas version v{version} not found on dp {dp_id}")
    return CanvasLoadVersionResponse(
        document=CanvasDoc.model_validate_json(row.document),
        version=row.version,
        created_at=row.created_at,
    )
