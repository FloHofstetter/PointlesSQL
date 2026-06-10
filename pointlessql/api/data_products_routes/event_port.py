"""Event-stream output-port endpoints — subscription CRUD + HTTP + WS.

Backed by the :mod:`pointlessql.services.event_port` runtime:

* ``GET /api/data-products/{c}/{s}/events?table=…&since=…&format=ndjson``
  — one-shot HTTP/1.1 chunked pull from a starting Delta CDF version.
* ``WS  /ws/data-products/{c}/{s}/events?table=…``
  — live push, registers as a subscriber on the in-memory hub and
  receives broadcast JSON frames until the client disconnects.
* ``GET / POST / DELETE /api/data-products/{c}/{s}/event-subscriptions``
  — durable subscription CRUD (steward/admin POST/DELETE; any user
  GET sees only own; admin sees all).
* ``POST .../event-subscriptions/{id}/pause`` + ``/resume`` +
  ``/rewind?to_version=N`` — state-machine control.

Auth ladder mirrors the rest of the data-product surface: any
authenticated user may read + create-for-self; steward/admin may
manage any subscription on a product they steward.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Body, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.exceptions import BadRequestError, ResourceNotFoundError
from pointlessql.models import (
    DataProductEventSubscription,
    DataProductOutputPort,
)
from pointlessql.services import event_port as event_port_service
from pointlessql.services._executor import run_sync
from pointlessql.services.event_port import _ws_hub
from pointlessql.services.event_port._cdf_reader import read_changes

router = APIRouter(tags=["data-products"])


def _resolve_product_id(request: Request, catalog: str, schema: str) -> int:
    """Return the :class:`DataProduct` PK or raise ``404``."""
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    dp_row, _, _, _ = load_one(factory, workspace_id, catalog, schema)
    return int(dp_row.id)


def _resolve_event_port_id(
    request: Request, data_product_id: int, port_name: str | None = None
) -> int:
    """Return the single ``kind='event'`` output-port PK for this product.

    When *port_name* is given the lookup is restricted to that name;
    otherwise the first event port is returned.  Raises 400 when the
    product has no event port (declared = nothing to consume).
    """
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = select(DataProductOutputPort).where(
            DataProductOutputPort.data_product_id == data_product_id,
            DataProductOutputPort.kind == "event",
        )
        if port_name is not None:
            stmt = stmt.where(DataProductOutputPort.name == port_name)
        row = session.scalars(stmt.limit(1)).first()
        if row is None:
            raise BadRequestError(
                "data product has no event-kind output port"
                + (f" {port_name!r}" if port_name else "")
            )
        return int(row.id)


def _is_steward_or_admin(request: Request, catalog: str, schema: str) -> bool:
    """Return True when the caller may manage subscriptions on this product."""
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    dp_row, _, _, _ = load_one(factory, workspace_id, catalog, schema)
    user = get_user(request)
    if user.get("is_admin"):
        return True
    if dp_row.steward_user_id is not None and dp_row.steward_user_id == user["id"]:
        return True
    return False


# ---------------------------------------------------------------------------
# Subscription CRUD
# ---------------------------------------------------------------------------


@router.get("/api/data-products/{catalog}/{schema}/event-subscriptions")
async def list_event_subscriptions(
    request: Request,
    catalog: str,
    schema: str,
) -> dict[str, Any]:
    """Return subscriptions on this product.

    Admin / steward sees all rows on the product.  A regular user sees
    only their own rows (rows where ``owner_user_id`` matches the
    caller).
    """
    require_user(request)
    data_product_id = _resolve_product_id(request, catalog, schema)
    factory = request.app.state.session_factory
    rows = event_port_service.list_subscriptions(factory, data_product_id=data_product_id)
    if not _is_steward_or_admin(request, catalog, schema):
        user_id = int(get_user(request).get("id", 0))
        rows = [r for r in rows if r["owner_user_id"] == user_id]
    return {"items": rows}


@router.post("/api/data-products/{catalog}/{schema}/event-subscriptions")
async def create_event_subscription(
    request: Request,
    catalog: str,
    schema: str,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Create a durable subscription on the product's event port.

    Body fields:

    * ``table`` (required) — source table name.
    * ``consumer_label`` (required) — caller-chosen unique label.
    * ``port_name`` (optional) — pick a specific event port if
      multiple exist.
    * ``start_version`` (optional, default 0) — cursor start.
    """
    require_user(request)
    user = get_user(request)
    data_product_id = _resolve_product_id(request, catalog, schema)
    table = str(body.get("table", "")).strip()
    label = str(body.get("consumer_label", "")).strip()
    if not table or not label:
        raise BadRequestError("table and consumer_label are required")
    port_name = body.get("port_name")
    output_port_id = _resolve_event_port_id(
        request, data_product_id, port_name=port_name if isinstance(port_name, str) else None
    )
    factory = request.app.state.session_factory
    try:
        row = event_port_service.create_subscription(
            factory,
            data_product_id=data_product_id,
            output_port_id=output_port_id,
            table_name=table,
            consumer_label=label,
            owner_user_id=int(user["id"]) if user.get("id") else None,
            start_version=int(body.get("start_version", 0)),
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
    return row


@router.delete("/api/data-products/{catalog}/{schema}/event-subscriptions/{subscription_id}")
async def delete_event_subscription(
    request: Request,
    catalog: str,
    schema: str,
    subscription_id: int,
) -> dict[str, Any]:
    """Hard-delete one subscription (steward/admin or own row)."""
    require_user(request)
    _resolve_product_id(request, catalog, schema)
    if not _is_steward_or_admin(request, catalog, schema):
        user_id = int(get_user(request).get("id", 0))
        factory = request.app.state.session_factory
        with factory() as session:
            row = session.get(DataProductEventSubscription, subscription_id)
            if row is None:
                raise ResourceNotFoundError(f"subscription {subscription_id} not found")
            if row.owner_user_id != user_id:
                raise BadRequestError("only the owner / steward may delete")
    factory = request.app.state.session_factory
    removed = event_port_service.delete_subscription(factory, subscription_id=subscription_id)
    if not removed:
        raise ResourceNotFoundError(f"subscription {subscription_id} not found")
    return {"deleted": True}


def _control(
    request: Request,
    catalog: str,
    schema: str,
    subscription_id: int,
    action: str,
    *,
    to_version: int | None = None,
) -> dict[str, Any]:
    """Shared steward-gated handler for pause / resume / rewind."""
    require_user(request)
    _resolve_product_id(request, catalog, schema)
    if not _is_steward_or_admin(request, catalog, schema):
        raise BadRequestError("only steward / admin may control subscriptions")
    factory = request.app.state.session_factory
    if action == "pause":
        row = event_port_service.pause_subscription(factory, subscription_id=subscription_id)
    elif action == "resume":
        row = event_port_service.resume_subscription(factory, subscription_id=subscription_id)
    elif action == "rewind":
        if to_version is None:
            raise BadRequestError("to_version query param required for rewind")
        try:
            row = event_port_service.rewind_subscription(
                factory,
                subscription_id=subscription_id,
                to_version=int(to_version),
            )
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc
    else:  # pragma: no cover — internal misuse
        raise BadRequestError(f"unknown action {action!r}")
    if row is None:
        raise ResourceNotFoundError(f"subscription {subscription_id} not found")
    return row


@router.post("/api/data-products/{catalog}/{schema}/event-subscriptions/{subscription_id}/pause")
async def pause_event_subscription(
    request: Request, catalog: str, schema: str, subscription_id: int
) -> dict[str, Any]:
    """Pause a subscription (steward/admin)."""
    return _control(request, catalog, schema, subscription_id, "pause")


@router.post("/api/data-products/{catalog}/{schema}/event-subscriptions/{subscription_id}/resume")
async def resume_event_subscription(
    request: Request, catalog: str, schema: str, subscription_id: int
) -> dict[str, Any]:
    """Resume a paused subscription (steward/admin)."""
    return _control(request, catalog, schema, subscription_id, "resume")


@router.post("/api/data-products/{catalog}/{schema}/event-subscriptions/{subscription_id}/rewind")
async def rewind_event_subscription(
    request: Request,
    catalog: str,
    schema: str,
    subscription_id: int,
    to_version: int = Query(..., ge=0),
) -> dict[str, Any]:
    """Rewind a subscription cursor to ``to_version`` (steward/admin)."""
    return _control(
        request,
        catalog,
        schema,
        subscription_id,
        "rewind",
        to_version=to_version,
    )


# ---------------------------------------------------------------------------
# HTTP one-shot streaming pull
# ---------------------------------------------------------------------------


def _resolve_table_location(request: Request, catalog: str, schema: str, table: str) -> str | None:
    """Return the Delta storage URI for the source table, or ``None``."""
    # NDJSON pull bypasses the per-request UC facade because it needs a
    # location URI, not row data — the facade is row-oriented.
    from soyuz_catalog_client.api.tables import (  # noqa: TID251 — location lookup, no row data
        get_table_api_2_1_unity_catalog_tables_full_name_get as _get_table,
    )

    from pointlessql.config import get_settings
    from pointlessql.services.soyuz_client import make_soyuz_client

    settings = get_settings()
    client = make_soyuz_client(settings)
    try:
        info = _get_table.sync(client=client, full_name=f"{catalog}.{schema}.{table}")
    # bare-broad-ok: missing UC entry == no stream available; HTTP layer raises 400 upstream
    except Exception:  # noqa: BLE001
        return None
    if info is None:
        return None
    storage = getattr(info, "storage_location", None)
    return str(storage) if storage else None


@router.get("/api/data-products/{catalog}/{schema}/events")
async def http_event_stream(
    request: Request,
    catalog: str,
    schema: str,
    table: str = Query(..., min_length=1),
    since: int = Query(0, ge=0),
    format: str = Query("ndjson", pattern="^(ndjson|jsonl)$"),
) -> StreamingResponse:
    """Stream CDF rows starting at ``since`` as newline-delimited JSON.

    One-shot — the stream ends when the current head version is
    reached.  For continuous follow-along, use the WebSocket endpoint.
    """
    require_user(request)
    _resolve_product_id(request, catalog, schema)
    location = _resolve_table_location(request, catalog, schema, table)
    if location is None:
        raise BadRequestError(f"table {table!r} not found in {catalog}.{schema}")

    del format  # ndjson / jsonl are wire-equivalent for the per-line form.

    async def iter_chunks() -> AsyncIterator[bytes]:
        from pointlessql.config import get_settings

        settings = get_settings()
        max_versions = int(
            getattr(getattr(settings, "event_port", None), "cdf_max_versions_per_pump", 100)
        )
        cursor = int(since)
        while True:
            rows = await run_sync(
                read_changes, location, since_version=cursor, max_versions=max_versions
            )
            if not rows:
                break
            for change in rows:
                frame = {
                    "version": change.version,
                    "commit_timestamp": change.commit_timestamp,
                    "change_type": change.change_type,
                    "data": change.data,
                }
                yield (json.dumps(frame, default=str) + "\n").encode("utf-8")
            cursor = max(row.version for row in rows) + 1

    return StreamingResponse(
        iter_chunks(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store"},
    )


# ---------------------------------------------------------------------------
# WebSocket live push
# ---------------------------------------------------------------------------


@router.websocket("/ws/data-products/{catalog}/{schema}/events")
async def ws_event_stream(
    websocket: WebSocket,
    catalog: str,
    schema: str,
    table: str = Query(..., min_length=1),
) -> None:
    """Live push: register as subscriber, receive broadcast frames."""
    await websocket.accept()
    product_full = f"{catalog}.{schema}"
    hub = await _ws_hub.get_or_create_hub(product_full, table)
    await _ws_hub.register(hub, websocket)
    try:
        await websocket.send_text(
            json.dumps(
                {
                    "hello": True,
                    "product": product_full,
                    "table": table,
                }
            )
        )
        while True:
            # Keep the connection alive; we don't act on inbound text
            # but reads let us detect disconnects promptly.
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break
    finally:
        await _ws_hub.deregister(hub, websocket)
        await _ws_hub.release_hub_if_empty(product_full, table)
