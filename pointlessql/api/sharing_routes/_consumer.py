"""Consumer-side Delta Sharing — provider profiles + protocol reads.

Any authenticated user can register a provider profile (the bearer
token is the credential the remote side issued — possession is the
grant) and browse/preview what it offers.  Protocol traffic runs in
the worker pool via :func:`run_sync` because the consumer client is
deliberately synchronous (it feeds the sync PQL world).
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Body, Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import current_workspace_id, get_user
from pointlessql.exceptions import (
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationError,
)
from pointlessql.models.sharing_providers import SharingProvider
from pointlessql.services import delta_sharing_consumer as consumer
from pointlessql.services._executor import run_sync

router = APIRouter()

_PREVIEW_ROWS = 200


def _serialize_provider(row: SharingProvider) -> dict[str, Any]:
    """Project a provider row to a JSON-safe dict — token never ships."""
    return {
        "id": row.id,
        "name": row.name,
        "endpoint_url": row.endpoint_url,
        "comment": row.comment,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _ensure_provider(request: Request, name: str) -> SharingProvider:
    """Return the active workspace's provider or raise a 404.

    Args:
        request: Incoming FastAPI request.
        name: Provider alias from the URL.

    Returns:
        The detached provider row.

    Raises:
        ResourceNotFoundError: When no provider with *name* exists in
            the active workspace.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    row = consumer.get_provider(factory, workspace_id=workspace_id, name=name)
    if row is None:
        raise ResourceNotFoundError(f"Sharing provider '{name}' not found.")
    return row


@router.get("/api/sharing/providers")
async def api_list_providers(request: Request) -> dict[str, Any]:
    """List the workspace's registered remote providers."""
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    rows = await run_sync(consumer.list_providers, factory, workspace_id=workspace_id)
    return {"providers": [_serialize_provider(row) for row in rows]}


@router.post("/api/sharing/providers")
async def api_create_provider(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Register a remote provider profile.

    Args:
        request: Incoming FastAPI request.
        body: ``{"name", "endpoint_url", "token", "comment"?}`` —
            the shape of a ``config.share`` profile file.

    Returns:
        The serialized provider (without any token material).

    Raises:
        ValidationError: On malformed input or a duplicate alias.
        PermissionDeniedError: When the caller is unauthenticated.
    """
    user = get_user(request)
    if user["id"] <= 0:
        raise PermissionDeniedError("authentication required to register providers")
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    try:
        row = await run_sync(
            consumer.create_provider,
            factory,
            workspace_id=workspace_id,
            name=str(body.get("name", "")),
            endpoint_url=str(body.get("endpoint_url", "")),
            token=str(body.get("token", "")),
            comment=body.get("comment") if isinstance(body.get("comment"), str) else None,
            principal=user["email"],
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await audit(
        request,
        "sharing_provider.created",
        f"sharing_provider:{row.name}",
        {"endpoint": row.endpoint_url},
    )
    return _serialize_provider(row)


@router.delete("/api/sharing/providers/{name}")
async def api_delete_provider(request: Request, name: str) -> dict[str, Any]:
    """Delete a provider profile."""
    row = _ensure_provider(request, name)
    factory = request.app.state.session_factory
    deleted = await run_sync(consumer.delete_provider, factory, provider_id=row.id)
    if deleted:
        await audit(
            request,
            "sharing_provider.deleted",
            f"sharing_provider:{row.name}",
            {"id": row.id},
        )
    return {"deleted": deleted}


@router.get("/api/sharing/providers/{name}/shares")
async def api_provider_shares(request: Request, name: str) -> dict[str, Any]:
    """List the shares the remote side offers this profile.

    Args:
        request: Incoming FastAPI request.
        name: Provider alias.

    Returns:
        ``{"shares": [names]}``.

    Raises:
        ValidationError: When the remote answers outside the
            protocol.
    """
    row = _ensure_provider(request, name)
    factory = request.app.state.session_factory
    try:
        shares = await run_sync(consumer.list_remote_shares, factory, row)
    except consumer.SharingProtocolError as exc:
        raise ValidationError(str(exc)) from exc
    return {"shares": shares}


@router.get("/api/sharing/providers/{name}/shares/{share}/tables")
async def api_provider_tables(request: Request, name: str, share: str) -> dict[str, Any]:
    """List every table of one remote share.

    Args:
        request: Incoming FastAPI request.
        name: Provider alias.
        share: Remote share name.

    Returns:
        ``{"tables": [{"share", "schema", "name"}]}``.

    Raises:
        ValidationError: When the remote answers outside the
            protocol.
    """
    row = _ensure_provider(request, name)
    factory = request.app.state.session_factory
    try:
        tables = await run_sync(consumer.list_remote_tables, factory, row, share)
    except consumer.SharingProtocolError as exc:
        raise ValidationError(str(exc)) from exc
    return {"tables": tables}


@router.post("/api/sharing/providers/{name}/read")
async def api_provider_read(
    request: Request, name: str, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Preview one shared table as JSON rows.

    Args:
        request: Incoming FastAPI request.
        name: Provider alias.
        body: ``{"share", "schema", "table", "limit"?}`` (preview
            rows capped server-side).

    Returns:
        ``{"columns", "rows", "row_count", "truncated"}``.

    Raises:
        ValidationError: On missing coordinates or protocol errors.
    """
    row = _ensure_provider(request, name)
    share = str(body.get("share", "")).strip()
    schema = str(body.get("schema", "")).strip()
    table = str(body.get("table", "")).strip()
    if not share or not schema or not table:
        raise ValidationError("share, schema, and table are required")
    limit = int(body.get("limit") or _PREVIEW_ROWS)
    limit = max(1, min(limit, _PREVIEW_ROWS))
    factory = request.app.state.session_factory
    try:
        frame = await run_sync(
            consumer.query_table_as_pandas,
            factory,
            row,
            share=share,
            schema=schema,
            table=table,
            limit_hint=limit,
        )
    except consumer.SharingProtocolError as exc:
        raise ValidationError(str(exc)) from exc
    truncated = len(frame) > limit
    sliced = frame.head(limit)
    await audit(
        request,
        "sharing_provider.read",
        f"sharing_provider:{row.name}",
        {"table": f"{share}.{schema}.{table}", "rows": int(len(sliced))},
    )
    json_rows = cast(
        "list[list[Any]]",
        sliced.astype(object).where(sliced.notna(), None).values.tolist(),  # pyright: ignore[reportUnknownMemberType]
    )
    return {
        "columns": [str(c) for c in cast("list[Any]", list(sliced.columns))],
        "rows": json_rows,
        "row_count": int(len(sliced)),
        "truncated": truncated,
    }
