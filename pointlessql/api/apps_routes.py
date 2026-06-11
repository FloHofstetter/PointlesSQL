"""Hosted-apps routes — app lifecycle JSON surface.

CRUD plus start / stop / log-tail under ``/api/apps``.  Reads are
open to any signed-in user; mutations (create / edit / delete /
start / stop) require a workspace admin because apps run arbitrary
operator-authored code on the host.  Browser traffic to a running
app goes through :mod:`pointlessql.api.apps_proxy`, never straight
to the worker port.
"""

from __future__ import annotations

import json
from typing import Any, cast

from fastapi import APIRouter, Body, HTTPException, Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_workspace_admin,
)
from pointlessql.exceptions import ResourceNotFoundError, ValidationError
from pointlessql.models.hosted_apps import HostedApp
from pointlessql.services import app_hosting
from pointlessql.services._executor import run_sync
from pointlessql.services.app_hosting import AppRuntimeMissingError, AppsManager
from pointlessql.services.secret_scopes import resolve_references_in_tree

router = APIRouter(tags=["apps"])

_UNSET: Any = object()


def serialize_app(row: HostedApp, *, manager: AppsManager | None = None) -> dict[str, Any]:
    """Project an app row to a JSON-safe dict.

    Shared with the HTML routes so the page's seed data and the
    refresh fetches stay interchangeable.

    Args:
        row: Detached app row.
        manager: Live worker manager, when wired — adds the worker's
            loopback port to the projection (``None`` when stopped).

    Returns:
        A JSON-safe dict of the app's fields.
    """
    return {
        "id": row.id,
        "slug": row.slug,
        "title": row.title,
        "description": row.description,
        "kind": row.kind,
        "source_code": row.source_code,
        "command_override": row.command_override,
        "env_json": row.env_json,
        "state": row.state,
        "last_error": row.last_error,
        "port": manager.port_for(row.id) if manager is not None else None,
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _optional_manager(request: Request) -> AppsManager | None:
    """Return the worker manager when wired, else ``None``.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The process-global :class:`AppsManager`, or ``None`` when
        hosted apps are not enabled.
    """
    manager: AppsManager | None = getattr(request.app.state, "apps_manager", None)
    return manager


def _ensure_app(request: Request, slug: str) -> HostedApp:
    """Return the active workspace's app or raise a 404.

    Args:
        request: Incoming FastAPI request.
        slug: App slug from the URL.

    Returns:
        The detached app row.

    Raises:
        ResourceNotFoundError: When no app with *slug* exists in the
            active workspace.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    row = app_hosting.get_app(factory, workspace_id=workspace_id, slug=slug)
    if row is None:
        raise ResourceNotFoundError(f"App '{slug}' not found.")
    return row


def _require_manager(request: Request) -> AppsManager:
    """Return the app's worker manager or answer 503.

    The lifespan constructs the manager; when it is absent (hosted
    apps disabled, or a partially-wired test app) lifecycle routes
    must fail loudly rather than half-start a worker.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The process-global :class:`AppsManager`.

    Raises:
        HTTPException: 503 when no manager is wired.
    """
    manager: AppsManager | None = getattr(request.app.state, "apps_manager", None)
    if manager is None:
        # bare-http-ok: 503 is the canonical subsystem-not-wired
        # status; no domain-named exception exists for it.
        raise HTTPException(status_code=503, detail="hosted apps are not enabled")
    return manager


def _env_from_body(body: dict[str, Any]) -> dict[str, str] | None | Any:
    """Extract the optional env mapping from a request body.

    Args:
        body: Parsed JSON request body.

    Returns:
        The env dict, ``None`` to clear, or the module sentinel when
        the field is absent.

    Raises:
        ValidationError: When ``env`` is present but not an object.
    """
    if "env" not in body:
        return _UNSET
    env = body.get("env")
    if env is None:
        return None
    if not isinstance(env, dict):
        raise ValidationError("env must be a JSON object of string values")
    return {str(k): str(v) for k, v in env.items()}  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]


@router.get("/api/apps")
async def api_list_apps(request: Request) -> dict[str, Any]:
    """List the active workspace's hosted apps."""
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    rows = await run_sync(app_hosting.list_apps, factory, workspace_id=workspace_id)
    manager = _optional_manager(request)
    return {"apps": [serialize_app(row, manager=manager) for row in rows]}


@router.post("/api/apps")
async def api_create_app(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Create an app in ``stopped`` state (workspace admins only).

    Args:
        request: Incoming FastAPI request.
        body: ``{"title", "kind", "source_code"}`` plus optional
            ``description``, ``command_override``, and ``env``.

    Returns:
        The serialized app row.

    Raises:
        ValidationError: On malformed input.
    """
    require_workspace_admin(request)
    user = get_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    env = _env_from_body(body)
    try:
        row = await run_sync(
            app_hosting.create_app,
            factory,
            workspace_id=workspace_id,
            title=str(body.get("title", "")),
            description=body.get("description"),
            kind=str(body.get("kind", "")),
            source_code=str(body.get("source_code", "")),
            command_override=body.get("command_override"),
            env=None if env is _UNSET else env,
            created_by_user_id=int(user["id"]),
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await audit(request, "hosted_app.created", f"hosted_app:{row.slug}", {"kind": row.kind})
    return serialize_app(row)


@router.get("/api/apps/{slug}")
async def api_get_app(request: Request, slug: str) -> dict[str, Any]:
    """Return one app by slug."""
    return serialize_app(_ensure_app(request, slug), manager=_optional_manager(request))


@router.patch("/api/apps/{slug}")
async def api_update_app(
    request: Request,
    slug: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Patch an app's editable fields (workspace admins only).

    Accepts any subset of ``title``, ``description``,
    ``source_code``, ``command_override``, and ``env``; source and
    env edits take effect on the next start.

    Args:
        request: Incoming FastAPI request.
        slug: App slug.
        body: Fields to update.

    Returns:
        The refreshed serialized app row.

    Raises:
        ValidationError: On malformed input.
        ResourceNotFoundError: When the app vanished mid-update.
    """
    require_workspace_admin(request)
    row = _ensure_app(request, slug)
    factory = request.app.state.session_factory
    kwargs: dict[str, Any] = {}
    if "title" in body:
        kwargs["title"] = str(body.get("title", ""))
    if "description" in body:
        kwargs["description"] = body.get("description")
    if "source_code" in body:
        kwargs["source_code"] = str(body.get("source_code", ""))
    if "command_override" in body:
        kwargs["command_override"] = body.get("command_override")
    env = _env_from_body(body)
    if env is not _UNSET:
        kwargs["env"] = env
    try:
        updated = await run_sync(app_hosting.update_app, factory, app_id=row.id, **kwargs)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    if updated is None:
        raise ResourceNotFoundError(f"App '{slug}' not found.")
    await audit(
        request,
        "hosted_app.updated",
        f"hosted_app:{slug}",
        {"fields": sorted(kwargs)},
    )
    return serialize_app(updated, manager=_optional_manager(request))


@router.delete("/api/apps/{slug}")
async def api_delete_app(request: Request, slug: str) -> dict[str, Any]:
    """Stop (if running) and delete an app (workspace admins only)."""
    require_workspace_admin(request)
    row = _ensure_app(request, slug)
    manager = _optional_manager(request)
    if manager is not None:
        await manager.stop(row.id)
    factory = request.app.state.session_factory
    deleted = await run_sync(app_hosting.delete_app, factory, app_id=row.id)
    if deleted:
        await audit(request, "hosted_app.deleted", f"hosted_app:{slug}", {"id": row.id})
    return {"deleted": deleted}


@router.post("/api/apps/{slug}/start")
async def api_start_app(request: Request, slug: str) -> dict[str, Any]:
    """Start the app's worker and wait for health (admins only).

    Secret references (``{{secrets/<scope>/<key>}}``) in the app's
    stored env resolve here, just-in-time, against the active
    workspace's scopes — the resolved values only ever live in the
    worker's process environment.

    Args:
        request: Incoming FastAPI request.
        slug: App slug.

    Returns:
        The serialized app row (``ready`` on success).

    Raises:
        ValidationError: When the stored env is corrupt, a secret
            reference does not resolve, or the worker fails to come
            up — the message carries the stderr tail.
        AppRuntimeMissingError: When the app's runtime package is
            not installed (renders as 503).
    """
    require_workspace_admin(request)
    row = _ensure_app(request, slug)
    manager = _require_manager(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    try:
        stored_env = json.loads(row.env_json or "{}")
    except json.JSONDecodeError as exc:
        raise ValidationError(f"stored env is not valid JSON: {exc}") from exc
    if not isinstance(stored_env, dict):
        raise ValidationError("stored env must be a JSON object")
    try:
        resolved = await run_sync(
            resolve_references_in_tree,
            factory,
            workspace_id=workspace_id,
            data=cast("dict[str, Any]", stored_env),
        )
    except ValueError as exc:
        raise ValidationError(f"env secret resolution failed: {exc}") from exc
    env = {str(k): str(v) for k, v in cast("dict[str, Any]", resolved).items()}
    await run_sync(app_hosting.set_state, factory, app_id=row.id, state="starting")
    try:
        await manager.start(row, env=env)
    except AppRuntimeMissingError as exc:
        await run_sync(
            app_hosting.set_state, factory, app_id=row.id, state="failed", error=str(exc)
        )
        raise
    except RuntimeError as exc:
        await run_sync(
            app_hosting.set_state, factory, app_id=row.id, state="failed", error=str(exc)
        )
        raise ValidationError(f"app failed to start: {exc}") from exc
    await run_sync(app_hosting.set_state, factory, app_id=row.id, state="ready")
    await audit(request, "hosted_app.started", f"hosted_app:{slug}", {"id": row.id})
    return serialize_app(_ensure_app(request, slug), manager=manager)


@router.post("/api/apps/{slug}/stop")
async def api_stop_app(request: Request, slug: str) -> dict[str, Any]:
    """Stop the app's worker (workspace admins only)."""
    require_workspace_admin(request)
    row = _ensure_app(request, slug)
    manager = _optional_manager(request)
    stopped = False
    if manager is not None:
        stopped = await manager.stop(row.id)
    factory = request.app.state.session_factory
    await run_sync(app_hosting.set_state, factory, app_id=row.id, state="stopped")
    if stopped:
        await audit(request, "hosted_app.stopped", f"hosted_app:{slug}", {"id": row.id})
    return serialize_app(_ensure_app(request, slug), manager=manager)


@router.get("/api/apps/{slug}/logs")
async def api_app_logs(request: Request, slug: str) -> dict[str, Any]:
    """Return the last 200 lines of the app worker's stderr log."""
    row = _ensure_app(request, slug)
    lines = await run_sync(app_hosting.read_log_tail, row.id, max_lines=200)
    return {"slug": slug, "lines": lines}
