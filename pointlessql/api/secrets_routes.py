"""Secret-scopes REST surface — ACL-gated, values write-only.

JSON endpoints under ``/api/secrets`` for every authenticated user;
what a caller can see and do is decided per scope by the ACL ladder
(``READ < WRITE < MANAGE``, admins implicitly ``MANAGE``):

* ``GET    /api/secrets/scopes`` — scopes visible to the caller.
* ``POST   /api/secrets/scopes`` — create (creator gets ``MANAGE``).
* ``DELETE /api/secrets/scopes/{scope}`` — ``MANAGE``.
* ``GET    /api/secrets/scopes/{scope}/secrets`` — keys + metadata,
  never values (``READ``).
* ``PUT    /api/secrets/scopes/{scope}/secrets/{key}`` — ``WRITE``.
* ``DELETE /api/secrets/scopes/{scope}/secrets/{key}`` — ``WRITE``.
* ``GET    /api/secrets/scopes/{scope}/secrets/{key}/value`` — the
  audited runtime getter (``READ``); the only path that decrypts.
* ``GET/PUT/DELETE …/acls[/{principal}]`` — ``MANAGE``.

A scope the caller holds no grant on answers 404 — existence is
itself a secret.  Every mutation and every value read logs to
:class:`AuditLog` under the ``secret*`` action prefix.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import current_workspace_id, get_user
from pointlessql.exceptions import (
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationError,
)
from pointlessql.models.secret_scopes import SecretScope, SecretScopeAcl, SecretScopeSecret
from pointlessql.services import secret_scopes as scopes_service

router = APIRouter(tags=["secrets"])


def _caller(request: Request) -> tuple[str | None, bool]:
    """Return the caller's ``(principal e-mail, is_admin)`` pair."""
    user = get_user(request)
    principal = user["email"] if user["id"] > 0 else None
    return principal, bool(user["is_admin"])


def _serialize_scope(row: SecretScope, permission: str) -> dict[str, Any]:
    """Project a scope row plus the caller's effective permission."""
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "permission": permission,
    }


def _serialize_secret(row: SecretScopeSecret) -> dict[str, Any]:
    """Project a secret row's metadata — the value never ships."""
    return {
        "key": row.key,
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _serialize_acl(row: SecretScopeAcl) -> dict[str, Any]:
    """Project an ACL row to a JSON-safe dict."""
    return {
        "principal": row.principal,
        "permission": row.permission,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _ensure_scope(request: Request, scope_name: str, *, need: str) -> SecretScope:
    """Return the scope when the caller holds *need*, or raise.

    Args:
        request: Incoming FastAPI request.
        scope_name: Scope identifier inside the active workspace.
        need: Required permission level.

    Returns:
        The detached scope row.

    Raises:
        ResourceNotFoundError: When the scope is absent — or when the
            caller holds no grant at all, so unauthorized probing
            cannot distinguish "missing" from "forbidden".
        PermissionDeniedError: When the caller holds a grant below
            *need*.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    principal, is_admin = _caller(request)
    scope = scopes_service.get_scope(factory, workspace_id=workspace_id, name=scope_name)
    permission = (
        None
        if scope is None
        else scopes_service.resolve_permission(
            factory, scope_id=scope.id, principal=principal, is_admin=is_admin
        )
    )
    if scope is None or permission is None:
        raise ResourceNotFoundError(f"Secret scope '{scope_name}' not found.")
    if not scopes_service.permission_satisfies(permission, need):
        raise PermissionDeniedError(f"secret scope '{scope_name}' requires {need}")
    return scope


@router.get("/api/secrets/scopes")
async def api_list_scopes(request: Request) -> dict[str, Any]:
    """List the scopes visible to the caller with effective permissions."""
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    principal, is_admin = _caller(request)
    pairs = scopes_service.list_scopes(
        factory, workspace_id=workspace_id, principal=principal, is_admin=is_admin
    )
    return {"scopes": [_serialize_scope(scope, permission) for scope, permission in pairs]}


@router.post("/api/secrets/scopes")
async def api_create_scope(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Create a scope; the creator receives ``MANAGE``.

    Args:
        request: Incoming FastAPI request.
        body: ``{"name": str, "description"?: str}``.

    Returns:
        The serialized scope row.

    Raises:
        ValidationError: On a malformed or already-taken name.
        PermissionDeniedError: When the caller is unauthenticated.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    principal, is_admin = _caller(request)
    if principal is None and not is_admin:
        raise PermissionDeniedError("authentication required to create secret scopes")
    name_raw = body.get("name")
    if not isinstance(name_raw, str) or not name_raw.strip():
        raise ValidationError("name must be a non-empty string")
    description = body.get("description")
    try:
        row = scopes_service.create_scope(
            factory,
            workspace_id=workspace_id,
            name=name_raw,
            description=description if isinstance(description, str) else None,
            principal=principal,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await audit(
        request,
        "secret_scope.created",
        f"secret_scope:{row.name}",
        {"id": row.id, "name": row.name},
    )
    return _serialize_scope(row, "MANAGE")


@router.delete("/api/secrets/scopes/{scope_name}")
async def api_delete_scope(request: Request, scope_name: str) -> dict[str, Any]:
    """Delete a scope and, via CASCADE, its secrets and ACLs (``MANAGE``)."""
    scope = _ensure_scope(request, scope_name, need="MANAGE")
    factory = request.app.state.session_factory
    deleted = scopes_service.delete_scope(factory, scope_id=scope.id)
    if deleted:
        await audit(
            request,
            "secret_scope.deleted",
            f"secret_scope:{scope.name}",
            {"id": scope.id, "name": scope.name},
        )
    return {"deleted": deleted}


@router.get("/api/secrets/scopes/{scope_name}/secrets")
async def api_list_secrets(request: Request, scope_name: str) -> dict[str, Any]:
    """List a scope's secret keys + write metadata (``READ``); never values."""
    scope = _ensure_scope(request, scope_name, need="READ")
    factory = request.app.state.session_factory
    rows = scopes_service.list_secret_keys(factory, scope_id=scope.id)
    return {"scope": scope.name, "secrets": [_serialize_secret(row) for row in rows]}


@router.put("/api/secrets/scopes/{scope_name}/secrets/{key}")
async def api_put_secret(
    request: Request,
    scope_name: str,
    key: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Create or overwrite a secret value (``WRITE``).

    Args:
        request: Incoming FastAPI request.
        scope_name: Scope identifier.
        key: Secret name.
        body: ``{"value": str}`` — the plaintext to encrypt at rest.

    Returns:
        The serialized secret metadata (without any value).

    Raises:
        ValidationError: On a malformed key, a non-string value, or a
            value beyond the size cap.
    """
    scope = _ensure_scope(request, scope_name, need="WRITE")
    factory = request.app.state.session_factory
    principal, _ = _caller(request)
    value = body.get("value")
    if not isinstance(value, str) or not value:
        raise ValidationError("value must be a non-empty string")
    try:
        row = scopes_service.put_secret(
            factory, scope_id=scope.id, key=key, value=value, principal=principal
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await audit(
        request,
        "secret.put",
        f"secret_scope:{scope.name}",
        {"key": row.key},
    )
    return _serialize_secret(row)


@router.delete("/api/secrets/scopes/{scope_name}/secrets/{key}")
async def api_delete_secret(request: Request, scope_name: str, key: str) -> dict[str, Any]:
    """Delete a secret (``WRITE``)."""
    scope = _ensure_scope(request, scope_name, need="WRITE")
    factory = request.app.state.session_factory
    deleted = scopes_service.delete_secret(factory, scope_id=scope.id, key=key)
    if deleted:
        await audit(
            request,
            "secret.deleted",
            f"secret_scope:{scope.name}",
            {"key": key},
        )
    return {"deleted": deleted}


@router.get("/api/secrets/scopes/{scope_name}/secrets/{key}/value")
async def api_get_secret_value(request: Request, scope_name: str, key: str) -> dict[str, Any]:
    """Decrypt one value for runtime use (``READ``) — always audited.

    The UI never calls this; it exists for kernel helpers and
    connector runtimes.  Every hit lands in the audit log as
    ``secret.accessed`` *before* the response leaves.

    Args:
        request: Incoming FastAPI request.
        scope_name: Scope identifier.
        key: Secret name.

    Returns:
        ``{"scope", "key", "value"}`` with the plaintext value.

    Raises:
        ResourceNotFoundError: When the key does not exist in the
            scope.
    """
    scope = _ensure_scope(request, scope_name, need="READ")
    factory = request.app.state.session_factory
    value = scopes_service.get_secret_value(factory, scope_id=scope.id, key=key)
    if value is None:
        raise ResourceNotFoundError(f"Secret key '{key}' not found in scope '{scope_name}'.")
    await audit(
        request,
        "secret.accessed",
        f"secret_scope:{scope.name}",
        {"key": key},
    )
    return {"scope": scope.name, "key": key, "value": value}


@router.get("/api/secrets/scopes/{scope_name}/acls")
async def api_list_acls(request: Request, scope_name: str) -> dict[str, Any]:
    """List a scope's ACL rows (``MANAGE``)."""
    scope = _ensure_scope(request, scope_name, need="MANAGE")
    factory = request.app.state.session_factory
    rows = scopes_service.list_acls(factory, scope_id=scope.id)
    return {"scope": scope.name, "acls": [_serialize_acl(row) for row in rows]}


@router.put("/api/secrets/scopes/{scope_name}/acls/{principal}")
async def api_put_acl(
    request: Request,
    scope_name: str,
    principal: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Grant or update a principal's permission (``MANAGE``).

    Args:
        request: Incoming FastAPI request.
        scope_name: Scope identifier.
        principal: User e-mail or ``*``.
        body: ``{"permission": "READ"|"WRITE"|"MANAGE"}``.

    Returns:
        The serialized ACL row.

    Raises:
        ValidationError: On an unknown permission level or empty
            principal.
    """
    scope = _ensure_scope(request, scope_name, need="MANAGE")
    factory = request.app.state.session_factory
    permission = body.get("permission")
    if not isinstance(permission, str):
        raise ValidationError("permission must be a string")
    try:
        row = scopes_service.put_acl(
            factory, scope_id=scope.id, principal=principal, permission=permission
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await audit(
        request,
        "secret_acl.put",
        f"secret_scope:{scope.name}",
        {"principal": row.principal, "permission": row.permission},
    )
    return _serialize_acl(row)


@router.delete("/api/secrets/scopes/{scope_name}/acls/{principal}")
async def api_delete_acl(request: Request, scope_name: str, principal: str) -> dict[str, Any]:
    """Revoke a principal's grant (``MANAGE``)."""
    scope = _ensure_scope(request, scope_name, need="MANAGE")
    factory = request.app.state.session_factory
    deleted = scopes_service.delete_acl(factory, scope_id=scope.id, principal=principal)
    if deleted:
        await audit(
            request,
            "secret_acl.deleted",
            f"secret_scope:{scope.name}",
            {"principal": principal},
        )
    return {"deleted": deleted}
