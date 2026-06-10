"""Real-time co-edit WebSocket hub for the visual data-product canvas.

Mirrors the Phase-105 ``notebook_coedit_ws`` pattern at a smaller
scale: one in-memory ``pycrdt.Doc`` per data-product id, binary
frames with a one-byte protocol tag, periodic flush to the
``data_product_canvas_graph`` table.

Wire format — every frame starts with a single tag byte:

* ``0x00`` — ``sync_step1`` (client → server, payload is the
  client's state vector).
* ``0x01`` — ``sync_step2`` (server → client, payload is an update
  relative to the receiver's state).  Sent unsolicited on connect
  with the full state.
* ``0x02`` — ``sync_update`` — bidirectional incremental update.
* ``0x03`` — ``awareness_update`` — opaque cursor/presence; relayed
  verbatim, never persisted.

Scope is deliberately narrower than the notebook hub: no
cross-process bus, no agent-presence tag, no cell-uuid remap.
Single-worker browser-to-browser co-edit only — multi-worker fan-out
can be added later by mirroring the notebook hub's PG LISTEN/NOTIFY bus.

Conditional client mount: the editor only joins the hub when the
URL carries ``?coedit=1``, so the single-user path stays unchanged.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from pointlessql.api.ws_auth import resolve_websocket_user
from pointlessql.models import DataProduct
from pointlessql.services.dp_canvas._coedit import (
    get_or_init_canvas_ydoc,
    persist_canvas_ydoc,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker

_LOG = logging.getLogger(__name__)

router = APIRouter()

TAG_SYNC_STEP1 = 0x00
TAG_SYNC_STEP2 = 0x01
TAG_SYNC_UPDATE = 0x02
TAG_AWARENESS_UPDATE = 0x03

QUEUE_MAXSIZE = 256
FLUSH_INTERVAL_S = 1.5


@dataclass
class _Subscriber:
    client_id: str
    websocket: WebSocket
    outbound: asyncio.Queue[bytes]
    pump_task: asyncio.Task[None] | None
    user_id: int


@dataclass
class _CanvasHub:
    dp_id: int
    doc: Any
    subscribers: list[_Subscriber] = field(default_factory=lambda: [])
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    dirty: bool = False
    flush_task: asyncio.Task[None] | None = None
    last_author_user_id: int | None = None


_HUBS: dict[int, _CanvasHub] = {}
_HUBS_LOCK = asyncio.Lock()


async def _pump(sub: _Subscriber) -> None:
    """Drain ``sub.outbound`` to the socket; close on overflow / disconnect."""
    try:
        while True:
            frame = await sub.outbound.get()
            await sub.websocket.send_bytes(frame)
    except WebSocketDisconnect, asyncio.CancelledError:
        pass
    except Exception:  # noqa: BLE001  # bare-broad-ok: last-ditch shutdown of the socket
        _LOG.exception("dp-canvas-coedit: pump for %s crashed", sub.client_id)
        try:
            await sub.websocket.close(code=1011)
        except Exception:  # noqa: BLE001  # bare-broad-ok: socket already torn down
            pass


async def _broadcast(hub: _CanvasHub, frame: bytes, *, exclude: _Subscriber | None) -> None:
    for sub in list(hub.subscribers):
        if sub is exclude:
            continue
        try:
            sub.outbound.put_nowait(frame)
        except asyncio.QueueFull:
            _LOG.warning("dp_canvas-coedit: outbound queue overflow for %s", sub.client_id)


async def _flush_loop(hub: _CanvasHub, factory: sessionmaker[Any]) -> None:
    """Persist the live Y.Doc to ``data_product_canvas_graph`` periodically."""
    try:
        while True:
            await asyncio.sleep(FLUSH_INTERVAL_S)
            async with hub.lock:
                if not hub.dirty:
                    continue
                hub.dirty = False
                snapshot_doc = hub.doc
                author = hub.last_author_user_id
            await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: persist_canvas_ydoc(
                    factory,
                    data_product_id=hub.dp_id,
                    doc=snapshot_doc,
                    author_user_id=author,
                ),
            )
    except asyncio.CancelledError:
        pass


async def _get_or_create_hub(dp_id: int, factory: sessionmaker[Any]) -> _CanvasHub:
    async with _HUBS_LOCK:
        existing = _HUBS.get(dp_id)
        if existing is not None:
            return existing
        doc = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: get_or_init_canvas_ydoc(factory, data_product_id=dp_id),
        )
        hub = _CanvasHub(dp_id=dp_id, doc=doc)
        hub.flush_task = asyncio.create_task(
            _flush_loop(hub, factory), name=f"dp-canvas-coedit-flush-{dp_id}"
        )
        _HUBS[dp_id] = hub
        return hub


async def _release_hub_if_empty(dp_id: int, factory: sessionmaker[Any]) -> None:
    async with _HUBS_LOCK:
        hub = _HUBS.get(dp_id)
        if hub is None:
            return
        if hub.subscribers:
            return
        if hub.flush_task is not None:
            hub.flush_task.cancel()
            try:
                await hub.flush_task
            except asyncio.CancelledError:
                pass
        # Final flush so the last edits land on disk before tear-down.
        async with hub.lock:
            if hub.dirty:
                snapshot = hub.doc
                author = hub.last_author_user_id
                hub.dirty = False
            else:
                snapshot = None
                author = None
        if snapshot is not None:
            await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: persist_canvas_ydoc(
                    factory,
                    data_product_id=dp_id,
                    doc=snapshot,
                    author_user_id=author,
                ),
            )
        _HUBS.pop(dp_id, None)


@router.websocket("/ws/dp-canvas/{dp_id}")
async def dp_canvas_coedit_ws(websocket: WebSocket, dp_id: int) -> None:
    """Accept a co-edit WebSocket on the canvas for *dp_id*.

    Close codes:

    * ``4401`` — no resolvable user.
    * ``4403`` — api-key principal (browser-only surface).
    * ``4404`` — dp_id missing in the workspace.
    """
    factory = websocket.app.state.session_factory
    await websocket.accept()
    user = resolve_websocket_user(websocket)
    if user is None:
        await websocket.close(code=4401)
        return
    user_id = int(user.get("id") or 0)
    if user_id == 0:
        await websocket.close(code=4403)
        return
    with factory() as session:
        dp = session.get(DataProduct, dp_id)
        if dp is None:
            await websocket.close(code=4404)
            return
    hub = await _get_or_create_hub(dp_id, factory)
    sub = _Subscriber(
        client_id=uuid.uuid4().hex[:8],
        websocket=websocket,
        outbound=asyncio.Queue(maxsize=QUEUE_MAXSIZE),
        pump_task=None,
        user_id=user_id,
    )
    sub.pump_task = asyncio.create_task(_pump(sub), name=f"dp-canvas-coedit-pump-{sub.client_id}")
    async with hub.lock:
        hub.subscribers.append(sub)
        initial = hub.doc.get_update()
    await sub.outbound.put(bytes([TAG_SYNC_STEP2]) + initial)
    try:
        while True:
            frame = await websocket.receive_bytes()
            if not frame:
                continue
            tag = frame[0]
            payload = frame[1:]
            if tag == TAG_SYNC_STEP1:
                async with hub.lock:
                    try:
                        diff = hub.doc.get_update(payload)
                    except Exception:  # noqa: BLE001  # bare-broad-ok: malformed state-vector from client
                        _LOG.warning(
                            "dp-canvas-coedit: malformed sync_step1 from %s",
                            sub.client_id,
                            exc_info=True,
                        )
                        continue
                await sub.outbound.put(bytes([TAG_SYNC_STEP2]) + diff)
            elif tag in (TAG_SYNC_UPDATE, TAG_SYNC_STEP2):
                relay = bytes([TAG_SYNC_UPDATE]) + payload
                async with hub.lock:
                    try:
                        hub.doc.apply_update(payload)
                    except Exception:  # noqa: BLE001  # bare-broad-ok: malformed update payload
                        _LOG.warning(
                            "dp-canvas-coedit: malformed update from %s",
                            sub.client_id,
                            exc_info=True,
                        )
                        continue
                    hub.dirty = True
                    hub.last_author_user_id = user_id
                    await _broadcast(hub, relay, exclude=sub)
            elif tag == TAG_AWARENESS_UPDATE:
                async with hub.lock:
                    await _broadcast(hub, frame, exclude=sub)
            else:
                _LOG.debug("dp-canvas-coedit: unknown tag 0x%02x", tag)
    except WebSocketDisconnect:
        pass
    finally:
        sub.pump_task.cancel()
        try:
            await sub.pump_task
        except asyncio.CancelledError, Exception:  # noqa: BLE001
            pass
        async with hub.lock:
            if sub in hub.subscribers:
                hub.subscribers.remove(sub)
        await _release_hub_if_empty(dp_id, factory)


__all__ = [
    "TAG_AWARENESS_UPDATE",
    "TAG_SYNC_STEP1",
    "TAG_SYNC_STEP2",
    "TAG_SYNC_UPDATE",
    "router",
]
