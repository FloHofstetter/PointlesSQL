"""Provider-side Delta Sharing administration (admin-gated).

Thin JSON proxies over the UC facade's :class:`SharingMixin` —
soyuz-catalog owns the share/recipient rows and the protocol
endpoints; PointlesSQL adds the operator gate, audit entries, and
the one-time-token handling on recipient create/rotate.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query, Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import get_uc_client, require_admin

router = APIRouter()


@router.get("/api/sharing/shares")
async def api_list_shares(request: Request) -> dict[str, Any]:
    """List every share this install offers."""
    require_admin(request)
    uc = get_uc_client(request)
    return {"shares": await uc.list_shares()}


@router.post("/api/sharing/shares")
async def api_create_share(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Create a share (``{"name", "comment"?}``)."""
    require_admin(request)
    uc = get_uc_client(request)
    created = await uc.create_share(body)
    await audit(request, "share.created", f"share:{created.get('name')}", None)
    return created


@router.get("/api/sharing/shares/{name}")
async def api_get_share(request: Request, name: str) -> dict[str, Any]:
    """Return one share with its objects and grants."""
    require_admin(request)
    uc = get_uc_client(request)
    return await uc.get_share(name)


@router.patch("/api/sharing/shares/{name}")
async def api_update_share(
    request: Request, name: str, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Patch a share's comment."""
    require_admin(request)
    uc = get_uc_client(request)
    updated = await uc.update_share(name, body)
    await audit(request, "share.updated", f"share:{name}", {"fields": sorted(body)})
    return updated


@router.delete("/api/sharing/shares/{name}")
async def api_delete_share(request: Request, name: str) -> dict[str, Any]:
    """Delete a share (objects + grants cascade on soyuz)."""
    require_admin(request)
    uc = get_uc_client(request)
    await uc.delete_share(name)
    await audit(request, "share.deleted", f"share:{name}", None)
    return {"deleted": True}


@router.post("/api/sharing/shares/{name}/objects")
async def api_add_share_object(
    request: Request, name: str, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Add a table (``{"table_full_name", "shared_as"?}``) to a share."""
    require_admin(request)
    uc = get_uc_client(request)
    updated = await uc.add_share_object(name, body)
    await audit(
        request,
        "share.object_added",
        f"share:{name}",
        {"table": body.get("table_full_name")},
    )
    return updated


@router.delete("/api/sharing/shares/{name}/objects")
async def api_remove_share_object(
    request: Request, name: str, table_full_name: str = Query(...)
) -> dict[str, Any]:
    """Remove a table from a share."""
    require_admin(request)
    uc = get_uc_client(request)
    await uc.remove_share_object(name, table_full_name)
    await audit(request, "share.object_removed", f"share:{name}", {"table": table_full_name})
    return {"removed": True}


@router.put("/api/sharing/shares/{name}/recipients/{recipient_name}")
async def api_grant_share(request: Request, name: str, recipient_name: str) -> dict[str, Any]:
    """Grant a recipient access to a share (idempotent)."""
    require_admin(request)
    uc = get_uc_client(request)
    await uc.grant_share(name, recipient_name)
    await audit(request, "share.granted", f"share:{name}", {"recipient": recipient_name})
    return {"granted": True}


@router.delete("/api/sharing/shares/{name}/recipients/{recipient_name}")
async def api_revoke_share(request: Request, name: str, recipient_name: str) -> dict[str, Any]:
    """Revoke a recipient's access to a share."""
    require_admin(request)
    uc = get_uc_client(request)
    await uc.revoke_share(name, recipient_name)
    await audit(request, "share.revoked", f"share:{name}", {"recipient": recipient_name})
    return {"revoked": True}


@router.get("/api/sharing/recipients")
async def api_list_recipients(request: Request) -> dict[str, Any]:
    """List every recipient (no token material)."""
    require_admin(request)
    uc = get_uc_client(request)
    return {"recipients": await uc.list_recipients()}


@router.post("/api/sharing/recipients")
async def api_create_recipient(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Create a recipient — the response carries the ONE-TIME token.

    The plaintext token appears exactly once here and never again
    (soyuz stores only its hash); the UI must surface it immediately
    with a copy affordance.

    Args:
        request: Incoming FastAPI request.
        body: ``{"name", "comment"?}``.

    Returns:
        The recipient info dict including ``token``.
    """
    require_admin(request)
    uc = get_uc_client(request)
    created = await uc.create_recipient(body)
    await audit(request, "recipient.created", f"recipient:{created.get('name')}", None)
    return created


@router.delete("/api/sharing/recipients/{name}")
async def api_delete_recipient(request: Request, name: str) -> dict[str, Any]:
    """Delete a recipient (grants cascade on soyuz)."""
    require_admin(request)
    uc = get_uc_client(request)
    await uc.delete_recipient(name)
    await audit(request, "recipient.deleted", f"recipient:{name}", None)
    return {"deleted": True}


@router.post("/api/sharing/recipients/{name}/rotate-token")
async def api_rotate_recipient_token(request: Request, name: str) -> dict[str, Any]:
    """Rotate a recipient's bearer token; returns the new one-time token."""
    require_admin(request)
    uc = get_uc_client(request)
    rotated = await uc.rotate_recipient_token(name)
    await audit(request, "recipient.token_rotated", f"recipient:{name}", None)
    return rotated
