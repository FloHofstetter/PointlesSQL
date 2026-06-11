"""Model-serving routes — endpoint lifecycle + the invocation proxy.

JSON surface under ``/api/serving-endpoints``.  Lifecycle mutations
(create / start / stop / delete) require an authenticated user;
invocations proxy to the endpoint's local scoring worker so
PointlesSQL's auth + audit front every request.  Without the
optional ``mlflow`` extra the lifecycle routes answer 503 and the
list stays readable.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import current_workspace_id, get_user
from pointlessql.exceptions import (
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationError,
)
from pointlessql.models.serving import ServingEndpoint
from pointlessql.services import model_serving as serving_service
from pointlessql.services._executor import run_sync
from pointlessql.services.mlflow_subprocess import MLflowStartupError, mlflow_available
from pointlessql.services.model_serving import get_serving_manager

router = APIRouter(tags=["serving"])


def _serialize(row: ServingEndpoint) -> dict[str, Any]:
    """Project an endpoint row to a JSON-safe dict."""
    return {
        "id": row.id,
        "name": row.name,
        "model_name": row.model_name,
        "model_version": row.model_version,
        "state": row.state,
        "last_error": row.last_error,
        "created_by": row.created_by,
        "invocation_count": row.invocation_count,
        "last_invoked_at": row.last_invoked_at.isoformat() if row.last_invoked_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _ensure_endpoint(request: Request, name: str) -> ServingEndpoint:
    """Return the active workspace's endpoint or raise a 404.

    Args:
        request: Incoming FastAPI request.
        name: Endpoint name from the URL.

    Returns:
        The detached endpoint row.

    Raises:
        ResourceNotFoundError: When no endpoint with *name* exists in
            the active workspace.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    row = serving_service.get_endpoint(factory, workspace_id=workspace_id, name=name)
    if row is None:
        raise ResourceNotFoundError(f"Serving endpoint '{name}' not found.")
    return row


def _require_mlflow() -> None:
    """Gate lifecycle mutations on the optional ``mlflow`` extra.

    Raises:
        MLflowStartupError: When the ``mlflow`` package is not
            installed (renders as 503, mirroring the proxy).
    """
    if not mlflow_available():
        raise MLflowStartupError(
            "model serving needs the optional mlflow extra (pip install pointlessql[ml])"
        )


@router.get("/api/serving-endpoints")
async def api_list_endpoints(request: Request) -> dict[str, Any]:
    """List the active workspace's serving endpoints."""
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    rows = await run_sync(serving_service.list_endpoints, factory, workspace_id=workspace_id)
    return {"endpoints": [_serialize(row) for row in rows]}


@router.post("/api/serving-endpoints")
async def api_create_endpoint(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Create an endpoint in ``stopped`` state.

    Args:
        request: Incoming FastAPI request.
        body: ``{"name", "model_name", "model_version"}`` —
            ``model_version`` is a version number or ``@alias``.

    Returns:
        The serialized endpoint row.

    Raises:
        ValidationError: On malformed input or a duplicate name.
        PermissionDeniedError: When the caller is unauthenticated.
    """
    user = get_user(request)
    if user["id"] <= 0:
        raise PermissionDeniedError("authentication required to create serving endpoints")
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    try:
        row = await run_sync(
            serving_service.create_endpoint,
            factory,
            workspace_id=workspace_id,
            name=str(body.get("name", "")),
            model_name=str(body.get("model_name", "")),
            model_version=str(body.get("model_version", "")),
            principal=user["email"],
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await audit(
        request,
        "serving_endpoint.created",
        f"serving_endpoint:{row.name}",
        {"model": f"{row.model_name}/{row.model_version}"},
    )
    return _serialize(row)


@router.delete("/api/serving-endpoints/{name}")
async def api_delete_endpoint(request: Request, name: str) -> dict[str, Any]:
    """Stop (if running) and delete an endpoint."""
    row = _ensure_endpoint(request, name)
    manager = get_serving_manager(request.app)
    await manager.stop(row.id)
    factory = request.app.state.session_factory
    deleted = await run_sync(serving_service.delete_endpoint, factory, endpoint_id=row.id)
    if deleted:
        await audit(
            request,
            "serving_endpoint.deleted",
            f"serving_endpoint:{row.name}",
            {"id": row.id},
        )
    return {"deleted": deleted}


@router.post("/api/serving-endpoints/{name}/start")
async def api_start_endpoint(request: Request, name: str) -> dict[str, Any]:
    """Start the endpoint's scoring worker and wait for health.

    Args:
        request: Incoming FastAPI request.
        name: Endpoint name.

    Returns:
        The serialized endpoint row (``ready`` on success).

    Raises:
        ValidationError: When the worker fails to come up — the
            message carries the stderr tail for the detail page.
    """
    _require_mlflow()
    row = _ensure_endpoint(request, name)
    factory = request.app.state.session_factory
    manager = get_serving_manager(request.app)
    await run_sync(serving_service.set_state, factory, endpoint_id=row.id, state="starting")
    try:
        await manager.start(row)
    except RuntimeError as exc:
        await run_sync(
            serving_service.set_state,
            factory,
            endpoint_id=row.id,
            state="failed",
            error=str(exc),
        )
        raise ValidationError(f"endpoint failed to start: {exc}") from exc
    await run_sync(serving_service.set_state, factory, endpoint_id=row.id, state="ready")
    await audit(
        request,
        "serving_endpoint.started",
        f"serving_endpoint:{row.name}",
        {"id": row.id},
    )
    return _serialize(_ensure_endpoint(request, name))


@router.post("/api/serving-endpoints/{name}/stop")
async def api_stop_endpoint(request: Request, name: str) -> dict[str, Any]:
    """Stop the endpoint's scoring worker."""
    row = _ensure_endpoint(request, name)
    manager = get_serving_manager(request.app)
    stopped = await manager.stop(row.id)
    factory = request.app.state.session_factory
    await run_sync(serving_service.set_state, factory, endpoint_id=row.id, state="stopped")
    if stopped:
        await audit(
            request,
            "serving_endpoint.stopped",
            f"serving_endpoint:{row.name}",
            {"id": row.id},
        )
    return _serialize(_ensure_endpoint(request, name))


@router.post("/api/serving-endpoints/{name}/invocations")
async def api_invoke_endpoint(
    request: Request,
    name: str,
    body: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Proxy one scoring request to the endpoint's worker.

    The body passes through verbatim in the MLflow scoring protocol
    (``dataframe_split`` / ``dataframe_records`` / ``instances`` /
    ``inputs``); the worker's JSON answer returns with its status.

    Args:
        request: Incoming FastAPI request.
        name: Endpoint name.
        body: Scoring payload (protocol-shaped, passed through).

    Returns:
        The worker's JSON response.

    Raises:
        ValidationError: When the endpoint is not running or the
            worker cannot be reached.
    """
    row = _ensure_endpoint(request, name)
    manager = get_serving_manager(request.app)
    port = manager.port_for(row.id)
    if port is None:
        raise ValidationError(f"endpoint '{name}' is not running — start it first")
    settings = request.app.state.settings
    try:
        async with httpx.AsyncClient() as client:
            upstream = await client.post(
                f"http://127.0.0.1:{port}/invocations",
                json=body,
                timeout=settings.serving.invocation_timeout_seconds,
            )
    except httpx.HTTPError as exc:
        raise ValidationError(f"scoring worker unreachable: {exc}") from exc
    factory = request.app.state.session_factory
    await run_sync(serving_service.record_invocation, factory, endpoint_id=row.id)
    media_type = upstream.headers.get("content-type", "application/json")
    return JSONResponse(
        content=upstream.json() if "json" in media_type else {"raw": upstream.text},
        status_code=upstream.status_code,
    )
