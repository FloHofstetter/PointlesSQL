"""WebSocket endpoint — accept handshake + dispatch binary frames."""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from pointlessql.api._ws_scaffold import authenticate_or_close
from pointlessql.api.notebook_coedit_ws._broadcast import (
    broadcast,
    publish_to_bus,
    pump,
)
from pointlessql.api.notebook_coedit_ws._constants import (
    QUEUE_MAXSIZE,
    TAG_AWARENESS_UPDATE,
    TAG_SYNC_STEP1,
    TAG_SYNC_STEP2,
    TAG_SYNC_UPDATE,
)
from pointlessql.api.notebook_coedit_ws._hub import (
    get_or_create_hub,
    release_hub_if_empty,
)
from pointlessql.api.notebook_coedit_ws._state import ClientSubscription
from pointlessql.models import Notebook
from pointlessql.services.notebook import permissions as perms_service

_LOG = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/notebook/coedit/{notebook_id}")
async def notebook_coedit_ws(  # noqa: C901 — handshake + dispatch are inherently long
    websocket: WebSocket,
    notebook_id: str,
) -> None:
    """Accept a co-edit WebSocket and pump binary frames.

    Args:
        websocket: Incoming WebSocket from Starlette.
        notebook_id: Path parameter; the :class:`Notebook` UUID to
            join.

    Close codes:

    * ``4401`` — no resolvable user (no cookie + no Bearer).
    * ``4403`` — api-key principal or missing ``edit`` role.
    * ``4404`` — notebook id unknown to the workspace.
    * ``1011`` — outbound queue overflow on this subscriber.
    """
    factory = websocket.app.state.session_factory
    settings = websocket.app.state.settings
    await websocket.accept()

    # Synthetic api-key principals are intentionally locked out
    # of the browser-only co-edit surface.
    user = await authenticate_or_close(
        websocket,
        close_reason=None,
        reject_api_key_principals=True,
    )
    if user is None:
        return
    user_id = int(user.get("id") or 0)
    is_admin = bool(user.get("is_admin"))

    with factory() as session:
        notebook = session.get(Notebook, notebook_id)
        if notebook is None:
            await websocket.close(code=4404)
            return
        if not perms_service.actor_has_role(
            session,
            notebook_id=notebook_id,
            user_id=user_id,
            is_admin=is_admin,
            required="edit",
        ):
            await websocket.close(code=4403)
            return

    hub = await get_or_create_hub(notebook_id, factory, settings)
    sub = ClientSubscription(
        client_id=uuid.uuid4().hex[:8],
        websocket=websocket,
        outbound=asyncio.Queue(maxsize=QUEUE_MAXSIZE),
        pump_task=None,
        user_id=user_id,
    )
    sub.pump_task = asyncio.create_task(pump(sub), name=f"coedit-pump-{sub.client_id}")
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
                    except Exception:  # noqa: BLE001 — malformed state vector
                        # bare-broad-ok: client sent garbage; log + skip is the protocol
                        _LOG.warning("coedit: malformed sync_step1 from %s", sub.client_id)
                        continue
                await sub.outbound.put(bytes([TAG_SYNC_STEP2]) + diff)
            elif tag in (TAG_SYNC_UPDATE, TAG_SYNC_STEP2):
                relay_frame = bytes([TAG_SYNC_UPDATE]) + payload
                async with hub.lock:
                    try:
                        hub.doc.apply_update(payload)
                    except Exception:  # noqa: BLE001 — malformed update
                        # bare-broad-ok: client sent garbage; log + skip is the protocol
                        _LOG.warning("coedit: malformed update from %s", sub.client_id)
                        continue
                    hub.dirty = True
                    await broadcast(hub, relay_frame, exclude=sub)
                await publish_to_bus(notebook_id, relay_frame)
            elif tag == TAG_AWARENESS_UPDATE:
                async with hub.lock:
                    await broadcast(hub, frame, exclude=sub)
                await publish_to_bus(notebook_id, frame)
            else:
                _LOG.debug("coedit: unknown tag 0x%02x from %s", tag, sub.client_id)
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
        await release_hub_if_empty(notebook_id, factory)
