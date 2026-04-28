"""Admin CRUD for the ``api_keys`` table.

Three JSON endpoints, all gated by :func:`require_admin`.  Plaintext
secrets are returned exactly once — at create time — and never
re-readable.  Revocation is soft (``revoked_at`` set; row stays so
historical audit attribution still resolves).

The admin UI surface is intentionally minimal: a list + create-with-
plaintext-display + revoke flow.  HTML pages can be added later if
real users ask for them.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import get_user, require_admin
from pointlessql.exceptions import CatalogNotFoundError, ValidationError
from pointlessql.services import api_keys as api_keys_service

router = APIRouter(tags=["admin-api-keys"])


def _serialize(row: Any) -> dict[str, Any]:
    """Project an :class:`ApiKey` ORM row to a JSON-safe dict.

    Args:
        row: Detached ORM row from
            :func:`pointlessql.services.api_keys.list_api_keys` /
            :func:`create_api_key`.

    Returns:
        ``{name, secret_prefix, supervisor, auditor, created_at,
        revoked_at, last_used_at}``.  Plaintext secret is never
        included.
    """
    return {
        "name": row.name,
        "secret_prefix": row.secret_prefix,
        "supervisor": bool(row.supervisor),
        "auditor": bool(getattr(row, "auditor", False)),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "last_used_at": (row.last_used_at.isoformat() if row.last_used_at else None),
    }


@router.get("/api/admin/api-keys")
async def api_admin_list_api_keys(
    request: Request, include_revoked: bool = False
) -> dict[str, Any]:
    """List active (and optionally revoked) API keys.

    Args:
        request: Incoming FastAPI request.
        include_revoked: When ``True`` revoked keys are included.

    Returns:
        ``{"keys": [{...}, ...]}`` newest-first.
    """
    require_admin(request)
    rows = api_keys_service.list_api_keys(
        request.app.state.session_factory, include_revoked=include_revoked
    )
    return {"keys": [_serialize(row) for row in rows]}


@router.post("/api/admin/api-keys")
async def api_admin_create_api_key(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Create a new API key and return the plaintext secret once.

    Args:
        request: Incoming FastAPI request.
        body: JSON ``{name: str, supervisor?: bool, auditor?: bool}``.

    Returns:
        ``{name, secret, secret_prefix, supervisor, auditor,
        created_at}`` — ``secret`` is the plaintext, persist it
        now or lose it.

    Raises:
        ValidationError: ``name`` missing or empty.
    """
    require_admin(request)
    name_raw = body.get("name")
    if not isinstance(name_raw, str) or not name_raw.strip():
        raise ValidationError("name must be a non-empty string")
    supervisor = bool(body.get("supervisor", False))
    auditor = bool(body.get("auditor", False))
    user = get_user(request)
    try:
        row, plaintext = api_keys_service.create_api_key(
            request.app.state.session_factory,
            name=name_raw,
            supervisor=supervisor,
            auditor=auditor,
            created_by_user_id=user.get("id") or None,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await audit(
        request,
        "api_key.created",
        f"api_key:{row.name}",
        {"supervisor": supervisor, "auditor": auditor},
    )
    return {
        "name": row.name,
        "secret": plaintext,
        "secret_prefix": row.secret_prefix,
        "supervisor": bool(row.supervisor),
        "auditor": bool(getattr(row, "auditor", False)),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.post("/api/admin/api-keys/{name}/revoke")
async def api_admin_revoke_api_key(request: Request, name: str) -> dict[str, Any]:
    """Mark *name* as revoked.

    Args:
        request: Incoming FastAPI request.
        name: API-key name to revoke.

    Returns:
        ``{"name": ..., "revoked": True}``.

    Raises:
        CatalogNotFoundError: No active key with that name.
    """
    require_admin(request)
    revoked = api_keys_service.revoke_api_key(request.app.state.session_factory, name=name)
    if not revoked:
        raise CatalogNotFoundError(f"api_key {name!r} not found or already revoked")
    await audit(request, "api_key.revoked", f"api_key:{name}")
    return {"name": name, "revoked": True}


__all__ = ["router"]
