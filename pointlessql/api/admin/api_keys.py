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
        "expires_at": (row.expires_at.isoformat() if getattr(row, "expires_at", None) else None),
        "rotated_at": (row.rotated_at.isoformat() if getattr(row, "rotated_at", None) else None),
        "grace_until": (row.grace_until.isoformat() if getattr(row, "grace_until", None) else None),
        "quarantined_at": (
            row.quarantined_at.isoformat() if getattr(row, "quarantined_at", None) else None
        ),
        "quarantine_reason": getattr(row, "quarantine_reason", None),
        "rotated_from_id": getattr(row, "rotated_from_id", None),
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


# ---------------------------------------------------------------------------
# lifecycle endpoints
# ---------------------------------------------------------------------------


@router.post("/api/admin/api-keys/{name}/rotate")
async def api_admin_rotate_api_key(
    request: Request, name: str, body: dict[str, Any] | None = Body(default=None)
) -> dict[str, Any]:
    """Mint a successor key; predecessor stays valid through grace window.

    Args:
        request: Incoming FastAPI request.
        name: Predecessor key name.
        body: Optional JSON ``{successor_name?: str, grace_seconds?: int}``.

    Returns:
        ``{predecessor, successor: {name, secret, secret_prefix, ...},
        grace_seconds}``.  ``secret`` is the plaintext, persist it now
        or lose it.

    Raises:
        CatalogNotFoundError: No active, un-rotated key with that name.
        ValidationError: ``grace_seconds`` not a non-negative int or
            ``successor_name`` not a non-empty string.
    """
    require_admin(request)
    payload = body or {}
    successor_name_raw = payload.get("successor_name")
    if successor_name_raw is not None and (
        not isinstance(successor_name_raw, str) or not successor_name_raw.strip()
    ):
        raise ValidationError("successor_name must be a non-empty string when provided")
    grace_seconds = payload.get("grace_seconds", 86_400)
    if not isinstance(grace_seconds, int) or grace_seconds < 0:
        raise ValidationError("grace_seconds must be a non-negative integer")
    user = get_user(request)
    rotated = api_keys_service.rotate_api_key(
        request.app.state.session_factory,
        name=name,
        successor_name=successor_name_raw.strip() if isinstance(successor_name_raw, str) else None,
        grace_seconds=grace_seconds,
        created_by_user_id=user.get("id") or None,
    )
    if rotated is None:
        raise CatalogNotFoundError(
            f"api_key {name!r} not found, already revoked, or already rotated"
        )
    successor_row, plaintext = rotated
    await audit(
        request,
        "api_key.rotated",
        f"api_key:{name}",
        {
            "successor": successor_row.name,
            "grace_seconds": grace_seconds,
        },
    )
    return {
        "predecessor": name,
        "grace_seconds": grace_seconds,
        "successor": {
            "name": successor_row.name,
            "secret": plaintext,
            "secret_prefix": successor_row.secret_prefix,
            "token_format": getattr(successor_row, "token_format", "v1") or "v1",
            "token_env": getattr(successor_row, "token_env", "live") or "live",
            "supervisor": bool(successor_row.supervisor),
            "auditor": bool(getattr(successor_row, "auditor", False)),
            "lineage_inbound": bool(getattr(successor_row, "lineage_inbound", False)),
            "analyst": bool(getattr(successor_row, "analyst", False)),
            "sql_execute": bool(getattr(successor_row, "sql_execute", False)),
        },
    }


@router.post("/api/admin/api-keys/{name}/quarantine")
async def api_admin_quarantine_api_key(
    request: Request, name: str, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Soft-disable a key (auth returns 401 until ``unquarantine``).

    Args:
        request: Incoming FastAPI request.
        name: Key name.
        body: JSON ``{reason: str}`` — short admin note.

    Returns:
        ``{"name": ..., "quarantined": True, "reason": ...}``.

    Raises:
        ValidationError: ``reason`` missing or empty.
        CatalogNotFoundError: Key missing, revoked, or already
            quarantined.
    """
    require_admin(request)
    reason_raw = body.get("reason")
    if not isinstance(reason_raw, str) or not reason_raw.strip():
        raise ValidationError("reason must be a non-empty string")
    applied = api_keys_service.quarantine_api_key(
        request.app.state.session_factory, name=name, reason=reason_raw
    )
    if not applied:
        raise CatalogNotFoundError(f"api_key {name!r} not found, revoked, or already quarantined")
    await audit(
        request,
        "api_key.quarantined",
        f"api_key:{name}",
        {"reason": reason_raw.strip()[:200]},
    )
    return {"name": name, "quarantined": True, "reason": reason_raw.strip()[:200]}


@router.post("/api/admin/api-keys/{name}/unquarantine")
async def api_admin_unquarantine_api_key(request: Request, name: str) -> dict[str, Any]:
    """Lift a quarantine.

    Args:
        request: Incoming FastAPI request.
        name: Key name.

    Returns:
        ``{"name": ..., "quarantined": False}``.

    Raises:
        CatalogNotFoundError: Key missing or not currently quarantined.
    """
    require_admin(request)
    applied = api_keys_service.unquarantine_api_key(request.app.state.session_factory, name=name)
    if not applied:
        raise CatalogNotFoundError(f"api_key {name!r} not found or not currently quarantined")
    await audit(request, "api_key.unquarantined", f"api_key:{name}")
    return {"name": name, "quarantined": False}


@router.patch("/api/admin/api-keys/{name}")
async def api_admin_update_api_key(
    request: Request, name: str, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Update mutable lifecycle fields on a key.

    v1 only exposes ``expires_at`` (set or clear) — scope edits would
    require an audit-trail design and ship in a later phase.

    Args:
        request: Incoming FastAPI request.
        name: Key name.
        body: JSON ``{expires_at: ISO-8601 str | null}``.  ``null``
            clears the TTL.

    Returns:
        ``{"name": ..., "expires_at": ISO-8601 str | None}``.

    Raises:
        ValidationError: ``expires_at`` not parseable.
        CatalogNotFoundError: Key missing or revoked.
    """
    from datetime import datetime as _datetime

    require_admin(request)
    if "expires_at" not in body:
        raise ValidationError("body must contain 'expires_at' (ISO-8601 or null)")
    raw = body["expires_at"]
    expires_at: _datetime | None
    if raw is None:
        expires_at = None
    elif isinstance(raw, str):
        try:
            expires_at = _datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ValidationError(f"expires_at not parseable: {exc}") from exc
    else:
        raise ValidationError("expires_at must be an ISO-8601 string or null")
    applied = api_keys_service.update_api_key_ttl(
        request.app.state.session_factory, name=name, expires_at=expires_at
    )
    if not applied:
        raise CatalogNotFoundError(f"api_key {name!r} not found or revoked")
    await audit(
        request,
        "api_key.ttl_updated",
        f"api_key:{name}",
        {"expires_at": expires_at.isoformat() if expires_at else None},
    )
    return {
        "name": name,
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


# ---------------------------------------------------------------------------
# per-key grants CRUD
# ---------------------------------------------------------------------------


def _api_key_by_name(request: Request, name: str) -> Any:
    """Resolve an :class:`ApiKey` row by name; raises 404 when missing."""
    from sqlalchemy import select

    from pointlessql.models import ApiKey

    factory = request.app.state.session_factory
    with factory() as session:
        row = session.scalar(select(ApiKey).where(ApiKey.name == name))
        if row is None or row.revoked_at is not None:
            raise CatalogNotFoundError(f"api_key {name!r} not found or revoked")
        session.expunge(row)
        return row


@router.get("/api/admin/api-keys/{name}/grants")
async def api_admin_list_grants(request: Request, name: str) -> dict[str, Any]:
    """List a key's catalog + IP grants.

    Args:
        request: Incoming FastAPI request.
        name: API-key name.

    Returns:
        ``{"catalog_grants": [...], "ip_grants": [...]}``.

    Raises:
        CatalogNotFoundError: Key missing or revoked.
    """  # noqa: DOC502 — raised by _api_key_by_name helper
    from sqlalchemy import select

    from pointlessql.models import ApiKeyCatalogGrant, ApiKeyIpGrant

    require_admin(request)
    row = _api_key_by_name(request, name)
    factory = request.app.state.session_factory
    with factory() as session:
        cg = session.scalars(
            select(ApiKeyCatalogGrant).where(ApiKeyCatalogGrant.api_key_id == row.id)
        ).all()
        ig = session.scalars(select(ApiKeyIpGrant).where(ApiKeyIpGrant.api_key_id == row.id)).all()
        return {
            "catalog_grants": [
                {
                    "id": g.id,
                    "catalog_name": g.catalog_name,
                    "schema_name": g.schema_name,
                    "granted_at": g.granted_at.isoformat() if g.granted_at else None,
                }
                for g in cg
            ],
            "ip_grants": [
                {
                    "id": g.id,
                    "cidr": g.cidr,
                    "label": g.label,
                    "granted_at": g.granted_at.isoformat() if g.granted_at else None,
                }
                for g in ig
            ],
        }


@router.post("/api/admin/api-keys/{name}/grants/catalog")
async def api_admin_add_catalog_grant(
    request: Request, name: str, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Add a catalog/schema grant to a key.

    Args:
        request: Incoming FastAPI request.
        name: API-key name.
        body: JSON ``{catalog_name: str, schema_name?: str | null}``.
            ``schema_name`` omitted or ``null`` grants the whole catalog.

    Returns:
        ``{"id": int, "catalog_name": ..., "schema_name": ...}``.

    Raises:
        ValidationError: ``catalog_name`` missing or empty, or grant
            already exists.
        CatalogNotFoundError: Key missing or revoked.
    """  # noqa: DOC502 DOC503 — CatalogNotFoundError raised by helper
    from datetime import UTC, datetime

    from pointlessql.models import ApiKeyCatalogGrant

    require_admin(request)
    row = _api_key_by_name(request, name)
    catalog_raw = body.get("catalog_name")
    if not isinstance(catalog_raw, str) or not catalog_raw.strip():
        raise ValidationError("catalog_name must be a non-empty string")
    schema_raw = body.get("schema_name")
    if schema_raw is not None and (not isinstance(schema_raw, str) or not schema_raw.strip()):
        raise ValidationError("schema_name must be a non-empty string or null")
    user = get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        grant = ApiKeyCatalogGrant(
            api_key_id=row.id,
            catalog_name=catalog_raw.strip(),
            schema_name=schema_raw.strip() if isinstance(schema_raw, str) else None,
            granted_at=datetime.now(UTC),
            granted_by_user_id=user.get("id") or None,
        )
        session.add(grant)
        try:
            session.commit()
        except Exception as exc:  # noqa: BLE001 — translate unique-violation
            session.rollback()
            raise ValidationError(
                f"grant already exists for ({catalog_raw}, {schema_raw or '*'})"
            ) from exc
        session.refresh(grant)
        grant_id = grant.id
    await audit(
        request,
        "api_key.grant.added",
        f"api_key:{name}",
        {
            "kind": "catalog",
            "catalog_name": catalog_raw.strip(),
            "schema_name": schema_raw.strip() if isinstance(schema_raw, str) else None,
        },
    )
    return {
        "id": grant_id,
        "catalog_name": catalog_raw.strip(),
        "schema_name": schema_raw.strip() if isinstance(schema_raw, str) else None,
    }


@router.delete("/api/admin/api-keys/{name}/grants/catalog/{grant_id}")
async def api_admin_delete_catalog_grant(
    request: Request, name: str, grant_id: int
) -> dict[str, Any]:
    """Delete a catalog grant.

    Args:
        request: Incoming FastAPI request.
        name: API-key name.
        grant_id: Grant row ID.

    Returns:
        ``{"deleted": True, "id": grant_id}``.

    Raises:
        CatalogNotFoundError: Key or grant missing.
    """
    from sqlalchemy import delete as _delete

    from pointlessql.models import ApiKeyCatalogGrant

    require_admin(request)
    row = _api_key_by_name(request, name)
    factory = request.app.state.session_factory
    with factory() as session:
        result = session.execute(
            _delete(ApiKeyCatalogGrant).where(
                ApiKeyCatalogGrant.id == grant_id,
                ApiKeyCatalogGrant.api_key_id == row.id,
            )
        )
        if not result.rowcount:
            raise CatalogNotFoundError(f"grant {grant_id} not found for {name!r}")
        session.commit()
    await audit(
        request,
        "api_key.grant.removed",
        f"api_key:{name}",
        {"kind": "catalog", "grant_id": grant_id},
    )
    return {"deleted": True, "id": grant_id}


@router.post("/api/admin/api-keys/{name}/grants/ip")
async def api_admin_add_ip_grant(
    request: Request, name: str, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Add an IP/CIDR grant to a key.

    Args:
        request: Incoming FastAPI request.
        name: API-key name.
        body: JSON ``{cidr: str, label?: str}``.  ``cidr`` validated
            via ``ipaddress.ip_network`` and stored in canonical form.

    Returns:
        ``{"id": int, "cidr": ..., "label": ...}``.

    Raises:
        ValidationError: ``cidr`` missing / unparseable, or duplicate.
        CatalogNotFoundError: Key missing or revoked.
    """  # noqa: DOC502 DOC503 — CatalogNotFoundError raised by helper
    from datetime import UTC, datetime

    from pointlessql.models import ApiKeyIpGrant
    from pointlessql.services.api_keys._acl import validate_cidr

    require_admin(request)
    row = _api_key_by_name(request, name)
    cidr_raw = body.get("cidr")
    if not isinstance(cidr_raw, str) or not cidr_raw.strip():
        raise ValidationError("cidr must be a non-empty string")
    try:
        cidr_clean = validate_cidr(cidr_raw)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    label_raw = body.get("label")
    if label_raw is not None and not isinstance(label_raw, str):
        raise ValidationError("label must be a string or null")
    label_clean = label_raw.strip()[:200] if isinstance(label_raw, str) else None
    user = get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        grant = ApiKeyIpGrant(
            api_key_id=row.id,
            cidr=cidr_clean,
            label=label_clean,
            granted_at=datetime.now(UTC),
            granted_by_user_id=user.get("id") or None,
        )
        session.add(grant)
        try:
            session.commit()
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            raise ValidationError(f"grant already exists for cidr {cidr_clean}") from exc
        session.refresh(grant)
        grant_id = grant.id
    await audit(
        request,
        "api_key.ip_grant.added",
        f"api_key:{name}",
        {"cidr": cidr_clean, "label": label_clean},
    )
    return {"id": grant_id, "cidr": cidr_clean, "label": label_clean}


@router.delete("/api/admin/api-keys/{name}/grants/ip/{grant_id}")
async def api_admin_delete_ip_grant(request: Request, name: str, grant_id: int) -> dict[str, Any]:
    """Delete an IP grant.

    Args:
        request: Incoming FastAPI request.
        name: API-key name.
        grant_id: Grant row ID.

    Returns:
        ``{"deleted": True, "id": grant_id}``.

    Raises:
        CatalogNotFoundError: Key or grant missing.
    """
    from sqlalchemy import delete as _delete

    from pointlessql.models import ApiKeyIpGrant

    require_admin(request)
    row = _api_key_by_name(request, name)
    factory = request.app.state.session_factory
    with factory() as session:
        result = session.execute(
            _delete(ApiKeyIpGrant).where(
                ApiKeyIpGrant.id == grant_id,
                ApiKeyIpGrant.api_key_id == row.id,
            )
        )
        if not result.rowcount:
            raise CatalogNotFoundError(f"grant {grant_id} not found for {name!r}")
        session.commit()
    await audit(
        request,
        "api_key.ip_grant.removed",
        f"api_key:{name}",
        {"grant_id": grant_id},
    )
    return {"deleted": True, "id": grant_id}


@router.get("/api/admin/api-keys/{name}/usage")
async def api_admin_get_usage(request: Request, name: str, days: int = 30) -> dict[str, Any]:
    """Return the last *days* days of usage for *name*.

    Args:
        request: Incoming FastAPI request.
        name: API-key name.
        days: Window size in days.  Defaults to 30; clamped to
            ``[1, 365]``.

    Returns:
        ``{"name": ..., "days": [{"date": "YYYY-MM-DD", "count":
        int}, ...], "top_ips": [{"ip": str, "count": int}, ...]}``.

    Raises:
        CatalogNotFoundError: Key missing or revoked.
    """  # noqa: DOC502 — raised by _api_key_by_name helper
    from pointlessql.services.api_keys._usage import get_usage_summary

    require_admin(request)
    row = _api_key_by_name(request, name)
    clamped_days = max(1, min(days, 365))
    summary = get_usage_summary(
        request.app.state.session_factory, api_key_id=row.id, days=clamped_days
    )
    return {"name": name, **summary}


__all__ = ["router"]
