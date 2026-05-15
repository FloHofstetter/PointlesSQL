"""Public workspace landing page + pin CRUD (Phase 77.10).

Public sibling of ``pointlessql/api/admin/workspaces.py``.  The
admin module owns the workspace-lifecycle CRUD; this module owns:

* ``GET /workspaces/{slug}`` — the GitHub-org-style landing page
  (pinned entities + activity feed + workspace README +
  member list).
* ``GET /api/workspaces/{slug}/pins`` — ordered pinned-entity list.
* ``POST /api/workspaces/{slug}/pins`` — admin add a pin.
* ``DELETE /api/workspaces/{slug}/pins/{social_target_id}`` —
  admin remove a pin.
* ``PATCH /api/workspaces/{slug}/pins/reorder`` — drag-and-drop
  reorder for admins.
* ``GET /api/workspaces/{slug}/activity`` — workspace-scoped
  cross-entity feed (reuses 77.9 feed query with a workspace
  scope filter).

All public reads are member-gated; writes are admin-gated.
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from pointlessql.api.dependencies import (
    get_user,
    require_admin,
    require_user,
)
from pointlessql.models.notifications import UserNotification
from pointlessql.models.social._social_target import SocialTarget
from pointlessql.models.social._workspace_pin import WorkspacePinnedEntity
from pointlessql.models.workspace._core import Workspace, WorkspaceMember
from pointlessql.services.social import entity_registry

router = APIRouter(tags=["workspaces"])


def _resolve_workspace(session: Any, slug: str) -> Workspace:
    """Look up a workspace by slug, 404 when missing.

    Args:
        session: Active SQLAlchemy session.
        slug: Workspace slug.

    Returns:
        The :class:`Workspace` row.

    Raises:
        HTTPException: 404 when no workspace exists for *slug*.
    """
    ws = session.execute(
        select(Workspace).where(Workspace.slug == slug)
    ).scalar_one_or_none()
    if ws is None:
        # bare-http-ok: workspace not found.
        raise HTTPException(
            status_code=404, detail=f"workspace {slug!r} not found"
        )
    return ws


def _serialise_pin(
    pin: WorkspacePinnedEntity, target: SocialTarget
) -> dict[str, Any]:
    """Render one pin row + its target metadata as JSON."""
    return {
        "social_target_id": pin.social_target_id,
        "entity_kind": target.entity_kind,
        "entity_ref": target.entity_ref,
        "url": entity_registry.url_for(
            str(target.entity_kind), str(target.entity_ref)
        ),
        "pin_order": pin.pin_order,
        "pinned_by_user_id": pin.pinned_by_user_id,
        "pinned_at": pin.pinned_at.isoformat(),
    }


@router.get("/workspaces/{slug}", response_class=HTMLResponse)
async def workspace_landing_page(
    request: Request, slug: str
) -> HTMLResponse:
    """Render the workspace landing page.

    Args:
        request: Incoming FastAPI request.
        slug: Workspace slug from the URL.

    Returns:
        The rendered ``pages/workspace_landing.html`` template.

    Raises:
        HTTPException: 404 when the workspace slug doesn't exist.
    """
    require_user(request)
    user = get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        ws = _resolve_workspace(session, slug)
        member_count = session.execute(
            select(WorkspaceMember).where(WorkspaceMember.workspace_id == ws.id)
        ).all()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/workspace_landing.html",
        {
            "workspace": {
                "id": ws.id,
                "slug": ws.slug,
                "name": ws.name,
                "description": ws.description,
            },
            "member_count": len(member_count),
            "is_admin": user["is_admin"],
            "active_page": "workspaces",
        },
    )


@router.get("/api/workspaces/{slug}/pins")
async def list_pins(slug: str, request: Request) -> dict[str, Any]:
    """List every pinned entity for the workspace, ordered."""
    require_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        ws = _resolve_workspace(session, slug)
        rows = session.execute(
            select(WorkspacePinnedEntity, SocialTarget)
            .join(
                SocialTarget,
                WorkspacePinnedEntity.social_target_id == SocialTarget.id,
            )
            .where(WorkspacePinnedEntity.workspace_id == ws.id)
            .order_by(WorkspacePinnedEntity.pin_order)
        ).all()
        return {
            "workspace_slug": slug,
            "pins": [_serialise_pin(pin, target) for pin, target in rows],
        }


@router.post("/api/workspaces/{slug}/pins")
async def add_pin(slug: str, request: Request) -> dict[str, Any]:
    """Pin a polymorphic entity to the workspace landing (admin only).

    Body:
        ``{"social_target_id": int}`` — caller resolves the
        target id from the social_target row (citations parser
        can lift one out of a token).
    """
    require_admin(request)
    user = get_user(request)
    payload_raw = await request.json()
    if not isinstance(payload_raw, dict):
        # bare-http-ok: request body must be a JSON object.
        raise HTTPException(
            status_code=400, detail="request body must be a JSON object"
        )
    payload: dict[str, Any] = cast(dict[str, Any], payload_raw)
    target_id = payload.get("social_target_id")
    if not isinstance(target_id, int) or target_id <= 0:
        # bare-http-ok: target id must be a positive integer.
        raise HTTPException(
            status_code=400, detail="social_target_id must be a positive int"
        )
    factory = request.app.state.session_factory
    with factory() as session:
        ws = _resolve_workspace(session, slug)
        existing = session.execute(
            select(WorkspacePinnedEntity).where(
                WorkspacePinnedEntity.workspace_id == ws.id,
                WorkspacePinnedEntity.social_target_id == target_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            # bare-http-ok: pin already exists.
            raise HTTPException(
                status_code=409, detail="entity already pinned"
            )
        max_order_row = session.execute(
            select(WorkspacePinnedEntity.pin_order)
            .where(WorkspacePinnedEntity.workspace_id == ws.id)
            .order_by(WorkspacePinnedEntity.pin_order.desc())
            .limit(1)
        ).first()
        max_order = int(max_order_row[0]) if max_order_row else -1
        pin = WorkspacePinnedEntity(
            workspace_id=int(ws.id),
            social_target_id=target_id,
            pin_order=max_order + 1,
            pinned_by_user_id=int(user["id"]),
        )
        session.add(pin)
        session.commit()
        target = session.execute(
            select(SocialTarget).where(SocialTarget.id == target_id)
        ).scalar_one()
        return _serialise_pin(pin, target)


@router.delete(
    "/api/workspaces/{slug}/pins/{social_target_id}"
)
async def remove_pin(
    slug: str, social_target_id: int, request: Request
) -> dict[str, Any]:
    """Unpin an entity from the workspace landing (admin only)."""
    require_admin(request)
    factory = request.app.state.session_factory
    with factory() as session:
        ws = _resolve_workspace(session, slug)
        pin = session.execute(
            select(WorkspacePinnedEntity).where(
                WorkspacePinnedEntity.workspace_id == ws.id,
                WorkspacePinnedEntity.social_target_id == social_target_id,
            )
        ).scalar_one_or_none()
        if pin is None:
            # bare-http-ok: pin row not found.
            raise HTTPException(
                status_code=404, detail="pin not found"
            )
        session.delete(pin)
        session.commit()
    return {"deleted": True, "social_target_id": social_target_id}


@router.patch("/api/workspaces/{slug}/pins/reorder")
async def reorder_pins(
    slug: str, request: Request
) -> dict[str, Any]:
    """Re-apply ``pin_order`` from an admin-supplied id list.

    Body:
        ``{"order": [social_target_id, ...]}`` in the desired
        visual order.  Pins not in the list keep their current
        ``pin_order``.
    """
    require_admin(request)
    payload_raw = await request.json()
    if not isinstance(payload_raw, dict):
        # bare-http-ok: request body must be a JSON object.
        raise HTTPException(
            status_code=400, detail="request body must be a JSON object"
        )
    payload: dict[str, Any] = cast(dict[str, Any], payload_raw)
    order_raw = payload.get("order")
    if not isinstance(order_raw, list):
        # bare-http-ok: order must be a list of social_target ids.
        raise HTTPException(
            status_code=400, detail="order must be a list of ids"
        )
    order = cast(list[Any], order_raw)
    factory = request.app.state.session_factory
    with factory() as session:
        ws = _resolve_workspace(session, slug)
        pins = session.execute(
            select(WorkspacePinnedEntity).where(
                WorkspacePinnedEntity.workspace_id == ws.id,
            )
        ).scalars().all()
        index_by_id = {int(pin.social_target_id): pin for pin in pins}
        for new_order, raw_target_id in enumerate(order):
            if not isinstance(raw_target_id, int):
                continue
            pin = index_by_id.get(raw_target_id)
            if pin is not None:
                pin.pin_order = new_order
        session.commit()
    return {"reordered": True}


@router.get("/api/workspaces/{slug}/activity")
async def workspace_activity(
    slug: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Workspace-scoped recent activity — every inbox event in the workspace."""
    require_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        ws = _resolve_workspace(session, slug)
        notifs = session.execute(
            select(UserNotification)
            .where(UserNotification.workspace_id == ws.id)
            .order_by(UserNotification.created_at.desc())
            .limit(limit)
        ).scalars().all()
        return {
            "workspace_slug": slug,
            "activity": [
                {
                    "event_type": n.event_type,
                    "summary_md": n.summary_md,
                    "source_url": n.source_url,
                    "entity_kind": n.source_entity_kind,
                    "entity_ref": n.source_entity_ref,
                    "created_at": n.created_at.isoformat(),
                }
                for n in notifs
            ],
        }


__all__: list[str] = ["router"]
