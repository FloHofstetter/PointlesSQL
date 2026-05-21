"""Phase 105.2 — real-time co-edit WebSocket hub.

Wires :mod:`pointlessql.services.notebook.coedit` (the storage
primitive shipped in Sprint 105.1) to multiple browser tabs editing
the same notebook.  A per-``notebook_id`` :class:`_NotebookHub`
holds the authoritative :class:`pycrdt.Doc` in memory while any
client is connected; clients exchange binary frames that the hub
applies + rebroadcasts.

Wire format — every frame starts with a single tag byte:

* ``0x00`` — ``sync_step1``: client → server, payload is the
  client's state vector (``Doc.get_state()``).
* ``0x01`` — ``sync_step2``: server → client, payload is an update
  relative to the receiver's state.  Sent unsolicited on connect
  with the full state.
* ``0x02`` — ``sync_update``: bidirectional incremental update.
  Server applies + rebroadcasts to other subscribers.
* ``0x03`` — ``awareness_update``: opaque (cursor / presence /
  agent attribution).  Relayed verbatim, never persisted.

Persistence cadence: the hub flushes the live Doc to
``notebook_crdt_state`` once per second when dirty + once
synchronously when the last subscriber leaves.  The teardown path
also opportunistically triggers compaction when
:func:`coedit_service.needs_compaction` says the blob has crossed
size or TTL bounds.

Sprint 105.3 layers ``y-monaco`` on the client side; 105.4 puts
semantics on the awareness channel.  This module stays oblivious to
both — it is a binary fanout pipe with auth + backpressure.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import uuid
from typing import TYPE_CHECKING, Any, Final
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pycrdt import Doc
from sqlalchemy import select

from pointlessql.api.ws_auth import resolve_websocket_user
from pointlessql.models import Notebook
from pointlessql.models.notebook import NotebookCellIdentity, NotebookCrdtState
from pointlessql.services.notebook import coedit as coedit_service
from pointlessql.services.notebook import permissions as perms_service
from pointlessql.services.notebook._doc import (
    load_document,
    resolve_py_notebook_path,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker

    from pointlessql.config import Settings

_LOG = logging.getLogger(__name__)
router = APIRouter()

# Wire-protocol tag bytes (kept in sync with the future
# ``frontend/js/notebook/coedit.js`` Sprint-105.3 mixin).
TAG_SYNC_STEP1: Final[int] = 0x00
TAG_SYNC_STEP2: Final[int] = 0x01
TAG_SYNC_UPDATE: Final[int] = 0x02
TAG_AWARENESS_UPDATE: Final[int] = 0x03

# Per-subscriber outbound queue cap.  At 256 frames a slow client
# disconnects long before they can OOM the host; faster clients
# never come close.
_QUEUE_MAXSIZE: Final[int] = 256

# Hub-level periodic flush cadence.  One second strikes the balance
# between losing-at-most-one-second-of-edits on crash and avoiding
# per-keystroke DB roundtrips.
_FLUSH_INTERVAL_S: Final[float] = 1.0


@dataclasses.dataclass(slots=True)
class _ClientSubscription:
    """One connected client's per-hub bookkeeping.

    Attributes:
        client_id: Short uuid4-derived tag for log correlation.
        websocket: The accepted Starlette :class:`WebSocket`.
        outbound: Bounded queue the broadcast path pushes into; the
            pump task drains it.  ``maxsize=256``.
        pump_task: Background task forwarding queued frames to the
            socket.  ``None`` only during the brief window between
            subscription creation and task spawn.
        user_id: Authenticated user id; ``0`` indicates a synthetic
            api-key principal (rejected at handshake).
    """

    client_id: str
    websocket: WebSocket
    outbound: asyncio.Queue[bytes]
    pump_task: asyncio.Task[None] | None
    user_id: int


@dataclasses.dataclass(slots=True)
class _NotebookHub:
    """In-memory state for one ``notebook_id`` with ≥1 live client.

    Attributes:
        notebook_id: 36-char :class:`Notebook` UUID this hub serves.
        doc: The live :class:`pycrdt.Doc` mutated under :attr:`lock`.
        subscribers: All currently-connected clients.  Mutated under
            :attr:`lock`.
        lock: Serialises ``apply_update`` + broadcast so other peers
            never observe an inconsistent ordering of updates.
        dirty: Set by every successful ``apply_update``; cleared by
            the flush task once the persistence write completes.
        flush_task: Periodic 1-s task that snapshots the doc to the
            ``notebook_crdt_state`` row when ``dirty``.  ``None``
            during the brief construction window.
    """

    notebook_id: str
    doc: Doc  # pyright: ignore[reportMissingTypeArgument]
    subscribers: list[_ClientSubscription]
    lock: asyncio.Lock
    dirty: bool
    flush_task: asyncio.Task[None] | None


# Module-level singleton — the asyncio loop is single-threaded per
# uvicorn worker so a plain dict + lock pair is enough.  Multi-worker
# deployments need a Redis pub/sub broker; out of scope for 105.2.
_HUBS: dict[str, _NotebookHub] = {}
_HUBS_LOCK = asyncio.Lock()


def _extract_seed_cells(
    document: Any,
    cell_uuid_map: dict[str, str],
) -> list[dict[str, Any]]:
    """Build the ``seed_cells`` payload for :func:`get_or_init_ydoc`.

    The Y.Doc's :class:`pycrdt.Map` keys live for the duration of
    the live session; the canonical mapping is to the stable
    :class:`NotebookCellIdentity` row.  Cells with no live identity
    row (brand-new notebook never saved since Phase 95 landed) get a
    transient uuid4 so the doc is still navigable; the next save
    materialises a stable id and Sprint 105.5's save-barrier will
    broadcast a remap.

    Args:
        document: The :class:`NotebookDocument` returned by
            :func:`load_document`.
        cell_uuid_map: ``content_hash -> cell_uuid`` mapping resolved
            from ``notebook_cells`` (live rows only).

    Returns:
        Ordered list of ``{cell_uuid, source}`` dicts ready for
        :func:`_seed_cells_into_doc`.
    """
    seed: list[dict[str, Any]] = []
    for cell in document.cells:
        resolved = cell_uuid_map.get(cell.content_hash) or uuid4().hex
        seed.append({"cell_uuid": resolved, "source": cell.source})
    return seed


def _build_seed(
    factory: sessionmaker[Any],
    settings: Settings,
    *,
    notebook_id: str,
) -> list[dict[str, Any]]:
    """Load a notebook's on-disk cells + resolve their stable UUIDs.

    Returns an empty list when the underlying ``.py`` file is missing
    (notebook row exists but file was renamed / deleted) — cold-init
    then produces an empty Doc, which is still a valid starting point
    for new collaborators.

    Args:
        factory: SQLAlchemy session factory from app state.
        settings: Application settings carrying ``jupyter.notebooks_dir``.
        notebook_id: 36-char :class:`Notebook` UUID.

    Returns:
        ``seed_cells`` payload for :func:`coedit_service.get_or_init_ydoc`.
    """
    with factory() as session:
        notebook = session.get(Notebook, notebook_id)
        if notebook is None:
            return []
        file_path = notebook.file_path
        rows = session.execute(
            select(
                NotebookCellIdentity.id,
                NotebookCellIdentity.current_content_hash,
            ).where(
                NotebookCellIdentity.notebook_id == notebook_id,
                NotebookCellIdentity.removed_at.is_(None),
            )
        ).all()
        cell_uuid_map: dict[str, str] = {row[1]: row[0] for row in rows}
    try:
        notebooks_dir = settings.jupyter.notebooks_dir.resolve()
        absolute = resolve_py_notebook_path(notebooks_dir, file_path, must_exist=True)
        document = load_document(absolute, file_path)
    except Exception as exc:  # noqa: BLE001 — best-effort cold seed
        _LOG.warning(
            "coedit: cold-seed load failed for %s (%s); starting with empty doc",
            notebook_id,
            exc,
        )
        return []
    return _extract_seed_cells(document, cell_uuid_map)


async def _get_or_create_hub(
    notebook_id: str,
    factory: sessionmaker[Any],
    settings: Settings,
) -> _NotebookHub:
    """Return the live hub for *notebook_id*, creating it on cold path.

    Cold path loads the persisted blob (or seeds from disk) into a
    fresh in-memory Doc and spawns the periodic flush task.  Warm
    path returns the existing hub unchanged.
    """
    async with _HUBS_LOCK:
        hub = _HUBS.get(notebook_id)
        if hub is not None:
            return hub
        seed = _build_seed(factory, settings, notebook_id=notebook_id)
        with factory() as session:
            doc = coedit_service.get_or_init_ydoc(
                session, notebook_id=notebook_id, seed_cells=seed
            )
            session.commit()
        hub = _NotebookHub(
            notebook_id=notebook_id,
            doc=doc,
            subscribers=[],
            lock=asyncio.Lock(),
            dirty=False,
            flush_task=None,
        )
        hub.flush_task = asyncio.create_task(
            _flush_loop(hub, factory),
            name=f"coedit-flush-{notebook_id[:8]}",
        )
        _HUBS[notebook_id] = hub
        return hub


async def _release_hub_if_empty(
    notebook_id: str,
    factory: sessionmaker[Any],
) -> None:
    """Tear down the hub when the last subscriber leaves.

    Cancels the periodic flush task, writes a synchronous final
    flush so no edit is lost, and opportunistically compacts the
    blob if it has crossed the size or TTL gate.  Best-effort — any
    DB error is logged but does not propagate.
    """
    async with _HUBS_LOCK:
        hub = _HUBS.get(notebook_id)
        if hub is None or hub.subscribers:
            return
        flush_task = hub.flush_task
        if flush_task is not None:
            flush_task.cancel()
            try:
                await flush_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        try:
            with factory() as session:
                coedit_service.flush_doc(
                    session, notebook_id=notebook_id, doc=hub.doc
                )
                row = session.execute(
                    select(NotebookCrdtState).where(
                        NotebookCrdtState.notebook_id == notebook_id
                    )
                ).scalar_one_or_none()
                if row is not None and coedit_service.needs_compaction(row):
                    coedit_service.compact(session, notebook_id=notebook_id)
                session.commit()
        except Exception:  # noqa: BLE001 — teardown must not raise
            _LOG.exception("coedit: final flush failed for %s", notebook_id)
        del _HUBS[notebook_id]


async def _flush_loop(
    hub: _NotebookHub,
    factory: sessionmaker[Any],
) -> None:
    """Periodically snapshot the hub's Doc to the sidecar row.

    Cancelled at hub teardown; the synchronous final flush in
    :func:`_release_hub_if_empty` handles the last write.
    """
    try:
        while True:
            await asyncio.sleep(_FLUSH_INTERVAL_S)
            if not hub.dirty:
                continue
            async with hub.lock:
                snapshot = hub.doc.get_update()
                hub.dirty = False
            try:
                with factory() as session:
                    coedit_service._upsert_state(  # pyright: ignore[reportPrivateUsage]
                        session,
                        notebook_id=hub.notebook_id,
                        blob=snapshot,
                    )
                    session.commit()
            except Exception:  # noqa: BLE001 — keep looping on transient DB errors
                _LOG.exception(
                    "coedit: periodic flush failed for %s", hub.notebook_id
                )
                # Re-mark dirty so the next tick retries.
                hub.dirty = True
    except asyncio.CancelledError:
        raise


async def _broadcast(
    hub: _NotebookHub,
    frame: bytes,
    *,
    exclude: _ClientSubscription,
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
                _close_overflowed(sub),
                name=f"coedit-overflow-{sub.client_id}",
            )


async def _close_overflowed(sub: _ClientSubscription) -> None:
    """Force-close a subscriber whose outbound queue overflowed."""
    if sub.pump_task is not None:
        sub.pump_task.cancel()
    try:
        await sub.websocket.close(code=1011)
    except Exception:  # noqa: BLE001 — already-closed sockets raise
        pass


async def _pump(sub: _ClientSubscription) -> None:
    """Drain ``sub.outbound`` to the WebSocket forever.

    Silent exit on disconnect / closure — the receive loop's
    ``finally`` handles subscriber removal.
    """
    try:
        while True:
            frame = await sub.outbound.get()
            await sub.websocket.send_bytes(frame)
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:  # noqa: BLE001 — log + bail; cleanup handles state
        _LOG.exception("coedit: pump task crashed for %s", sub.client_id)


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

    user = resolve_websocket_user(websocket)
    if user is None:
        await websocket.close(code=4401)
        return
    user_id = int(user.get("id") or 0)
    is_admin = bool(user.get("is_admin"))
    if user_id == 0:
        # Synthetic api-key principals are intentionally locked out
        # of the browser-only co-edit surface.
        await websocket.close(code=4403)
        return

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

    hub = await _get_or_create_hub(notebook_id, factory, settings)
    sub = _ClientSubscription(
        client_id=uuid.uuid4().hex[:8],
        websocket=websocket,
        outbound=asyncio.Queue(maxsize=_QUEUE_MAXSIZE),
        pump_task=None,
        user_id=user_id,
    )
    sub.pump_task = asyncio.create_task(
        _pump(sub), name=f"coedit-pump-{sub.client_id}"
    )
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
                        _LOG.warning(
                            "coedit: malformed sync_step1 from %s", sub.client_id
                        )
                        continue
                await sub.outbound.put(bytes([TAG_SYNC_STEP2]) + diff)
            elif tag in (TAG_SYNC_UPDATE, TAG_SYNC_STEP2):
                async with hub.lock:
                    try:
                        hub.doc.apply_update(payload)
                    except Exception:  # noqa: BLE001 — malformed update
                        _LOG.warning(
                            "coedit: malformed update from %s", sub.client_id
                        )
                        continue
                    hub.dirty = True
                    await _broadcast(
                        hub,
                        bytes([TAG_SYNC_UPDATE]) + payload,
                        exclude=sub,
                    )
            elif tag == TAG_AWARENESS_UPDATE:
                async with hub.lock:
                    await _broadcast(hub, frame, exclude=sub)
            else:
                _LOG.debug(
                    "coedit: unknown tag 0x%02x from %s", tag, sub.client_id
                )
    except WebSocketDisconnect:
        pass
    finally:
        sub.pump_task.cancel()
        try:
            await sub.pump_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        async with hub.lock:
            if sub in hub.subscribers:
                hub.subscribers.remove(sub)
        await _release_hub_if_empty(notebook_id, factory)


__all__ = ["router"]
