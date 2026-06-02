"""Version-management routes: pin / unpin a production version, diff two."""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import select

from pointlessql.api.data_products_routes.canvas._helpers import load_dp, require_dp_write
from pointlessql.api.data_products_routes.canvas._schemas import CanvasDiffResponse
from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.models import DataProductCanvasGraph
from pointlessql.services.dp_canvas import CanvasDoc
from pointlessql.services.dp_canvas._diff import diff_docs
from pointlessql.services.dp_canvas._pinning import (
    pin_version as _pin_canvas_version,
)
from pointlessql.services.dp_canvas._pinning import (
    unpin_version as _unpin_canvas_version,
)

router = APIRouter(prefix="/api/dp", tags=["data-products-canvas"])


@router.post("/{dp_id}/canvas/versions/{version}/pin", status_code=204)
def pin_canvas_version(dp_id: int, version: int, request: Request) -> None:
    """Mark *version* of canvas *dp_id* as the production revision."""
    require_user(request)
    user = get_user(request)
    dp = load_dp(request, dp_id)
    require_dp_write(user, dp)
    factory = request.app.state.session_factory
    client_ip = request.client.host if request.client else None
    _pin_canvas_version(
        factory,
        dp_id=dp_id,
        version=version,
        actor_user_id=int(user["id"]),
        actor_user_email=str(user.get("email") or ""),
        workspace_id=current_workspace_id(request),
        client_ip=client_ip,
    )


@router.post("/{dp_id}/canvas/versions/{version}/unpin", status_code=204)
def unpin_canvas_version(dp_id: int, version: int, request: Request) -> None:
    """Clear the production-pin from *version* of canvas *dp_id*."""
    require_user(request)
    user = get_user(request)
    dp = load_dp(request, dp_id)
    require_dp_write(user, dp)
    factory = request.app.state.session_factory
    client_ip = request.client.host if request.client else None
    _unpin_canvas_version(
        factory,
        dp_id=dp_id,
        version=version,
        actor_user_id=int(user["id"]),
        actor_user_email=str(user.get("email") or ""),
        workspace_id=current_workspace_id(request),
        client_ip=client_ip,
    )


@router.get("/{dp_id}/canvas/diff", response_model=CanvasDiffResponse)
def diff_canvas_versions(
    dp_id: int,
    request: Request,
    from_version: int,
    to_version: int,
) -> CanvasDiffResponse:
    """Compare two saved canvas versions and return the structural diff."""
    require_user(request)
    load_dp(request, dp_id)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = (
            session.execute(
                select(DataProductCanvasGraph).where(
                    DataProductCanvasGraph.data_product_id == dp_id,
                    DataProductCanvasGraph.version.in_([from_version, to_version]),
                )
            )
            .scalars()
            .all()
        )
    by_version = {r.version: r for r in rows}
    if from_version not in by_version or to_version not in by_version:
        raise ResourceNotFoundError(
            f"canvas version(s) missing on dp {dp_id}: requested "
            f"v{from_version}/v{to_version}, have {sorted(by_version)}"
        )
    before = CanvasDoc.model_validate_json(by_version[from_version].document)
    after = CanvasDoc.model_validate_json(by_version[to_version].document)
    return CanvasDiffResponse(
        from_version=from_version,
        to_version=to_version,
        diff=diff_docs(before, after),
    )
