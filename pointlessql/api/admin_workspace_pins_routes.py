"""Admin CRUD for ``workspace_catalog_pins`` (Phase 28.3).

Pins are *cosmetic* — they shape the sidebar tree's initial
expansion (``GET /api/tree?primary_only=true``) but never restrict
which catalogs a workspace can query.  The admin-only routes below
let an admin pin / unpin / list catalogs per workspace.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Body, Request
from sqlalchemy import select

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import require_admin
from pointlessql.exceptions import CatalogNotFoundError, ValidationError
from pointlessql.models import WORKSPACE_PIN_MODES, Workspace, WorkspaceCatalogPin

router = APIRouter(tags=["admin"])


def _serialize(row: WorkspaceCatalogPin) -> dict[str, Any]:
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "catalog_name": row.catalog_name,
        "mode": row.mode,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _ensure_workspace(factory: Any, workspace_id: int) -> Workspace:
    with factory() as session:
        ws = session.get(Workspace, workspace_id)
        if ws is None:
            raise CatalogNotFoundError(f"workspace id={workspace_id} not found")
        session.expunge(ws)
    return ws


@router.get("/api/admin/workspaces/{workspace_id}/pins")
async def api_admin_list_pins(request: Request, workspace_id: int) -> dict[str, Any]:
    """Return every catalog-pin row for *workspace_id*.

    Args:
        request: Incoming FastAPI request.
        workspace_id: ``Workspace.id`` whose pins to list.

    Returns:
        ``{"workspace_id": int, "pins": [...]}`` newest-first.

    The ``require_admin`` dependency raises ``AuthorizationError`` if
    the caller is not a tenant admin; ``_ensure_workspace`` raises
    ``CatalogNotFoundError`` when no workspace has that id.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    _ensure_workspace(factory, workspace_id)
    with factory() as session:
        rows = list(
            session.scalars(
                select(WorkspaceCatalogPin)
                .where(WorkspaceCatalogPin.workspace_id == workspace_id)
                .order_by(WorkspaceCatalogPin.created_at.desc())
            ).all()
        )
    return {"workspace_id": workspace_id, "pins": [_serialize(r) for r in rows]}


@router.post("/api/admin/workspaces/{workspace_id}/pins")
async def api_admin_create_pin(
    request: Request,
    workspace_id: int,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Pin a catalog to a workspace.

    Args:
        request: Incoming FastAPI request.
        workspace_id: ``Workspace.id`` to pin to.
        body: ``{"catalog_name": str, "mode": "primary"|"pinned"}``.

    Returns:
        The serialised pin row.

    The ``require_admin`` dependency raises ``AuthorizationError`` if
    the caller is not a tenant admin; ``_ensure_workspace`` raises
    ``CatalogNotFoundError`` when the workspace does not exist.

    Raises:
        ValidationError: When the body is malformed or the
            (workspace_id, catalog_name) tuple is already pinned.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    _ensure_workspace(factory, workspace_id)

    catalog_raw = body.get("catalog_name")
    if not isinstance(catalog_raw, str) or not catalog_raw.strip():
        raise ValidationError("catalog_name must be a non-empty string")
    catalog_name = catalog_raw.strip()
    mode = str(body.get("mode") or "pinned").strip().lower()
    if mode not in WORKSPACE_PIN_MODES:
        raise ValidationError(f"mode must be one of {sorted(WORKSPACE_PIN_MODES)}")

    with factory() as session:
        existing = session.scalar(
            select(WorkspaceCatalogPin).where(
                WorkspaceCatalogPin.workspace_id == workspace_id,
                WorkspaceCatalogPin.catalog_name == catalog_name,
            )
        )
        if existing is not None:
            raise ValidationError(
                f"catalog {catalog_name!r} is already pinned to workspace {workspace_id}"
            )
        # If marking primary, demote any previous primary in the workspace.
        if mode == "primary":
            for prior in session.scalars(
                select(WorkspaceCatalogPin).where(
                    WorkspaceCatalogPin.workspace_id == workspace_id,
                    WorkspaceCatalogPin.mode == "primary",
                )
            ).all():
                prior.mode = "pinned"
        row = WorkspaceCatalogPin(
            workspace_id=workspace_id,
            catalog_name=catalog_name,
            mode=mode,
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)

    await audit(
        request,
        "workspace.pin_added",
        f"workspace:{workspace_id}",
        {"catalog_name": catalog_name, "mode": mode},
    )
    return _serialize(row)


@router.delete("/api/admin/workspaces/{workspace_id}/pins/{catalog_name}")
async def api_admin_delete_pin(
    request: Request, workspace_id: int, catalog_name: str
) -> dict[str, Any]:
    """Unpin a catalog from a workspace.

    Args:
        request: Incoming FastAPI request.
        workspace_id: ``Workspace.id`` to unpin from.
        catalog_name: Catalog to unpin.

    Returns:
        ``{"deleted": True}`` on success, ``{"deleted": False}`` when
        no matching pin existed.

    The ``require_admin`` dependency raises ``AuthorizationError`` if
    the caller is not a tenant admin; ``_ensure_workspace`` raises
    ``CatalogNotFoundError`` when the workspace does not exist.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    _ensure_workspace(factory, workspace_id)

    with factory() as session:
        row = session.scalar(
            select(WorkspaceCatalogPin).where(
                WorkspaceCatalogPin.workspace_id == workspace_id,
                WorkspaceCatalogPin.catalog_name == catalog_name,
            )
        )
        if row is None:
            return {"deleted": False}
        session.delete(row)
        session.commit()

    await audit(
        request,
        "workspace.pin_removed",
        f"workspace:{workspace_id}",
        {"catalog_name": catalog_name},
    )
    return {"deleted": True}
