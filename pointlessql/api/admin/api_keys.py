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
        "lineage_inbound": bool(getattr(row, "lineage_inbound", False)),
        "analyst": bool(getattr(row, "analyst", False)),
        "sql_execute": bool(getattr(row, "sql_execute", False)),
        "token_format": getattr(row, "token_format", "legacy") or "legacy",
        "token_env": getattr(row, "token_env", "legacy") or "legacy",
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
        body: JSON ``{name: str, supervisor?: bool, auditor?: bool,
            lineage_inbound?: bool, analyst?: bool, sql_execute?: bool,
            workspace_id?: int, env?: 'live' | 'test'}``.  ``workspace_id``
            defaults to ``1`` (the install-default workspace) so
            single-tenant clients never have to name one.  ``env``
            defaults to ``'live'``; ``'test'`` mints visually distinct
            keys for staging / CI integration.

    Returns:
        ``{name, secret, secret_prefix, supervisor, auditor,
        lineage_inbound, analyst, sql_execute, token_format,
        token_env, created_at}`` — ``secret`` is the full plaintext
        token, persist it now or lose it.

    Raises:
        ValidationError: ``name`` missing or empty, ``workspace_id``
            not a positive int, or ``env`` not ``'live'`` / ``'test'``.
    """
    require_admin(request)
    name_raw = body.get("name")
    if not isinstance(name_raw, str) or not name_raw.strip():
        raise ValidationError("name must be a non-empty string")
    supervisor = bool(body.get("supervisor", False))
    auditor = bool(body.get("auditor", False))
    lineage_inbound = bool(body.get("lineage_inbound", False))
    analyst = bool(body.get("analyst", False))
    sql_execute = bool(body.get("sql_execute", False))
    workspace_id_raw = body.get("workspace_id", 1)
    if not isinstance(workspace_id_raw, int) or workspace_id_raw < 1:
        raise ValidationError("workspace_id must be a positive integer")
    env_raw = body.get("env", "live")
    if env_raw not in ("live", "test"):
        raise ValidationError("env must be 'live' or 'test'")
    user = get_user(request)
    try:
        row, plaintext = api_keys_service.create_api_key(
            request.app.state.session_factory,
            name=name_raw,
            supervisor=supervisor,
            auditor=auditor,
            lineage_inbound=lineage_inbound,
            analyst=analyst,
            sql_execute=sql_execute,
            created_by_user_id=user.get("id") or None,
            workspace_id=workspace_id_raw,
            env=env_raw,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await audit(
        request,
        "api_key.created",
        f"api_key:{row.name}",
        {
            "supervisor": supervisor,
            "auditor": auditor,
            "lineage_inbound": lineage_inbound,
            "analyst": analyst,
            "sql_execute": sql_execute,
            "workspace_id": workspace_id_raw,
            "env": env_raw,
        },
    )
    return {
        "name": row.name,
        "secret": plaintext,
        "secret_prefix": row.secret_prefix,
        "supervisor": bool(row.supervisor),
        "auditor": bool(getattr(row, "auditor", False)),
        "lineage_inbound": bool(getattr(row, "lineage_inbound", False)),
        "analyst": bool(getattr(row, "analyst", False)),
        "sql_execute": bool(getattr(row, "sql_execute", False)),
        "token_format": getattr(row, "token_format", "v1") or "v1",
        "token_env": getattr(row, "token_env", env_raw) or env_raw,
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
