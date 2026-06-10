"""Per-key catalog + IP grant CRUD."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.admin.api_keys._shared import api_key_by_name
from pointlessql.api.dependencies import get_user, require_admin
from pointlessql.exceptions import CatalogNotFoundError, ValidationError

router = APIRouter(tags=["admin-api-keys"])


@router.get("/api/admin/api-keys/{name}/grants")
async def api_admin_list_grants(request: Request, name: str) -> dict[str, Any]:
    """List a key's catalog + IP grants.

    Propagates :class:`CatalogNotFoundError` raised by
    :func:`api_key_by_name` when the key is missing or revoked.

    Args:
        request: Incoming FastAPI request.
        name: API-key name.

    Returns:
        ``{"catalog_grants": [...], "ip_grants": [...]}``.
    """
    from sqlalchemy import select

    from pointlessql.models import ApiKeyCatalogGrant, ApiKeyIpGrant

    require_admin(request)
    row = api_key_by_name(request, name)
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

    Propagates :class:`CatalogNotFoundError` raised by
    :func:`api_key_by_name` when the key is missing or revoked.

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
    """
    from datetime import UTC, datetime

    from pointlessql.models import ApiKeyCatalogGrant

    require_admin(request)
    row = api_key_by_name(request, name)
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
    row = api_key_by_name(request, name)
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

    Propagates :class:`CatalogNotFoundError` raised by
    :func:`api_key_by_name` when the key is missing or revoked.

    Args:
        request: Incoming FastAPI request.
        name: API-key name.
        body: JSON ``{cidr: str, label?: str}``.  ``cidr`` validated
            via ``ipaddress.ip_network`` and stored in canonical form.

    Returns:
        ``{"id": int, "cidr": ..., "label": ...}``.

    Raises:
        ValidationError: ``cidr`` missing / unparseable, or duplicate.
    """
    from datetime import UTC, datetime

    from pointlessql.models import ApiKeyIpGrant
    from pointlessql.services.api_keys._acl import validate_cidr

    require_admin(request)
    row = api_key_by_name(request, name)
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
    row = api_key_by_name(request, name)
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
