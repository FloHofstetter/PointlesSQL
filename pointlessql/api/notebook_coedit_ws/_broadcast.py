"""Broadcast primitives — local fanout, bus relay, backpressure handling."""

from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocketDisconnect

from pointlessql.api.notebook_coedit_ws._constants import BUS_RELAYED_TAGS
from pointlessql.api.notebook_coedit_ws._state import (
    ClientSubscription,
    NotebookHub,
    get_bus,
)

_LOG = logging.getLogger(__name__)


async def broadcast(
    hub: NotebookHub,
    frame: bytes,
    *,
    exclude: ClientSubscription,
) -> None:
    """Fan a frame out to every subscriber except the originator.

    On per-subscriber backpressure (queue full) the offending
    client is closed with ``1011 try again later``; other
    subscribers stay unaffected.  Must be called with the hub's
    :attr:`lock` already held by the caller so the subscriber set
    cannot mutate mid-iteration.
    """
    for sub in hub.subscribers:
        if sub is exclude:
            continue
        try:
            sub.outbound.put_nowait(frame)
        except asyncio.QueueFull:
            _LOG.warning(
                "coedit: outbound overflow for client %s on notebook %s",
                sub.client_id,
                hub.notebook_id,
            )
            asyncio.create_task(
                close_overflowed(sub),
                name=f"coedit-overflow-{sub.client_id}",
            )


async def broadcast_to_all(hub: NotebookHub, frame: bytes) -> None:
    """Push a server-originated frame to every subscriber.

    Unlike :func:`broadcast`, this helper carries no ``exclude``
    parameter — the originating party is the hub itself, not a
    connected client.  Used by save-barrier to fan a
    ``cell_uuid_remap`` advisory out to every tab editing the
    affected notebook.

    Backpressure handling mirrors :func:`broadcast`: a full queue
    closes the offending subscriber with ``1011`` while leaving the
    rest of the fanout intact.  Must be called with ``hub.lock`` held.
    """
    for sub in hub.subscribers:
        try:
            sub.outbound.put_nowait(frame)
        except asyncio.QueueFull:
            _LOG.warning(
                "coedit: outbound overflow during server broadcast for %s on %s",
                sub.client_id,
                hub.notebook_id,
            )
            asyncio.create_task(
                close_overflowed(sub),
                name=f"coedit-overflow-{sub.client_id}",
            )


async def publish_to_bus(notebook_id: str, frame: bytes) -> None:
    """Best-effort cross-worker fanout for *frame*.

    No-op when the bus is unbound (default single-worker config) or
    when the frame's tag is not in :data:`BUS_RELAYED_TAGS`.  Errors
    are logged + swallowed inside :meth:`CoeditBus.publish`; the
    local broadcast has already happened so a transient PG outage
    costs only cross-worker consistency, not the editor UX.
    """
    bus = get_bus()
    if bus is None or not frame:
        return
    if frame[0] not in BUS_RELAYED_TAGS:
        return
    await bus.publish(notebook_id, frame)


async def close_overflowed(sub: ClientSubscription) -> None:
    """Force-close a subscriber whose outbound queue overflowed."""
    if sub.pump_task is not None:
        sub.pump_task.cancel()
    try:
        await sub.websocket.close(code=1011)
    except Exception:  # noqa: BLE001 — already-closed sockets raise; nothing to do
        pass  # bare-broad-ok: closing an already-closed WebSocket is benign


async def pump(sub: ClientSubscription) -> None:
    """Drain ``sub.outbound`` to the WebSocket forever.

    Silent exit on disconnect / closure — the receive loop's
    ``finally`` handles subscriber removal.
    """
    try:
        while True:
            frame = await sub.outbound.get()
            await sub.websocket.send_bytes(frame)
    except WebSocketDisconnect, asyncio.CancelledError:
        pass
    except Exception:  # noqa: BLE001 — log + bail; cleanup handles state
        _LOG.exception("coedit: pump task crashed for %s", sub.client_id)
