"""Phase 105.2 / 105.5 — real-time co-edit WebSocket hub.

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
* ``0x04`` — ``cell_uuid_remap``: server → all clients.  JSON
  payload ``{old_uuid: new_uuid, ...}`` emitted by Phase 105.5's
  save-barrier when the three-pass reconciler mints a fresh UUID
  for a cell the clients already track.  The hub atomically
  rewrites ``cells_text`` / ``cells_order`` under its lock so the
  next ``sync_update`` round-trip carries the new keys.

Persistence cadence: the hub flushes the live Doc to
``notebook_crdt_state`` once per second when dirty + once
synchronously when the last subscriber leaves.  The teardown path
also opportunistically triggers compaction when
:func:`coedit_service.needs_compaction` says the blob has crossed
size or TTL bounds.

Sprint 105.3 layers the client scaffold; 105.4 layers awareness
semantics on top.  This module stays oblivious to both — it is a
binary fanout pipe with auth + backpressure.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import uuid
from typing import TYPE_CHECKING, Any, Final
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pycrdt import Array, Doc, Map, Text
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
    from pointlessql.services.notebook.coedit_bus import CoeditBus

_LOG = logging.getLogger(__name__)
router = APIRouter()

# Wire-protocol tag bytes (kept in sync with the future
# ``frontend/js/notebook/coedit.js`` Sprint-105.3 mixin).
TAG_SYNC_STEP1: Final[int] = 0x00
TAG_SYNC_STEP2: Final[int] = 0x01
TAG_SYNC_UPDATE: Final[int] = 0x02
TAG_AWARENESS_UPDATE: Final[int] = 0x03
TAG_CELL_UUID_REMAP: Final[int] = 0x04
# Phase 105.6 — agent-presence ride-along; defined alongside its
# REST emitter in ``notebook_coedit_agent_routes.py`` but Phase 109
# needs the constant for the cross-worker dispatch switch.
TAG_AGENT_PRESENCE: Final[int] = 0x05

# Tags that ride the Phase-109 cross-worker bus.  Handshake bytes
# (sync_step1/2) stay strictly local — they are per-client and
# the answering hub has the authoritative state.
_BUS_RELAYED_TAGS: Final[frozenset[int]] = frozenset(
    {TAG_SYNC_UPDATE, TAG_AWARENESS_UPDATE, TAG_CELL_UUID_REMAP, TAG_AGENT_PRESENCE}
)

# Importing ``coedit_service`` to keep the type aliases for
# ``CELLS_ORDER_KEY`` / ``CELLS_TEXT_KEY`` co-located.
_CELLS_ORDER_KEY: Final[str] = coedit_service.CELLS_ORDER_KEY
_CELLS_TEXT_KEY: Final[str] = coedit_service.CELLS_TEXT_KEY

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
# uvicorn worker so a plain dict + lock pair is enough.  Phase 109's
# cross-worker fanout rides PG LISTEN/NOTIFY through
# :class:`pointlessql.services.notebook.coedit_bus.CoeditBus`; the
# bus stays optional (default-off feature flag) so single-worker
# installs are unaffected.
_HUBS: dict[str, _NotebookHub] = {}
_HUBS_LOCK = asyncio.Lock()

# Phase 109 — module-level handle on the bus.  Wrapped in a single-
# slot list so the assignment site does not trip pyright's
# ``reportConstantRedefinition`` (uppercase names are read-only).
# Set by the FastAPI lifespan via :func:`bind_coedit_bus` after the
# bus has started so publish sites can reach it without threading
# the WebSocket / Request through every helper.  Stays empty on
# single-worker or SQLite installs.
_bus_ref: list[CoeditBus | None] = [None]


def bind_coedit_bus(bus: CoeditBus | None) -> None:
    """Attach (or detach) the cross-worker bus to this hub module.

    Called from the FastAPI lifespan once at startup with the live
    :class:`CoeditBus`, and again at teardown with ``None``.  When
    set, the WS dispatch path publishes outbound frames over the
    bus after the local fanout completes.

    Args:
        bus: Live :class:`CoeditBus` or ``None`` to detach.
    """
    _bus_ref[0] = bus


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


async def _broadcast_to_all(hub: _NotebookHub, frame: bytes) -> None:
    """Push a server-originated frame to every subscriber.

    Unlike :func:`_broadcast`, this helper carries no ``exclude``
    parameter — the originating party is the hub itself, not a
    connected client.  Used by Phase 105.5's save-barrier to fan a
    ``cell_uuid_remap`` advisory out to every tab editing the
    affected notebook.

    Backpressure handling mirrors :func:`_broadcast`: a full queue
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
                _close_overflowed(sub),
                name=f"coedit-overflow-{sub.client_id}",
            )


async def _publish_to_bus(notebook_id: str, frame: bytes) -> None:
    """Best-effort cross-worker fanout for *frame*.

    No-op when the bus is unbound (default single-worker config) or
    when the frame's tag is not in :data:`_BUS_RELAYED_TAGS`.  Errors
    are logged + swallowed inside :meth:`CoeditBus.publish`; the
    local broadcast has already happened so a transient PG outage
    costs only cross-worker consistency, not the editor UX.
    """
    bus = _bus_ref[0]
    if bus is None or not frame:
        return
    if frame[0] not in _BUS_RELAYED_TAGS:
        return
    await bus.publish(notebook_id, frame)


async def apply_remote_bus_frame(
    notebook_uuid: str, payload: bytes, source_pid: int
) -> None:
    """Bus dispatch callback — apply a frame received from another worker.

    Invoked by :class:`CoeditBus` after a NOTIFY/SELECT round-trip
    when ``source_pid`` is not our own PID.  Mirrors the WS receive
    path: applies CRDT updates to the local hub's Doc and broadcasts
    to every locally-connected subscriber.  Does **not** re-publish
    to the bus — Phase 109's frame-once invariant relies on the
    publisher being the only worker that puts a given frame on the
    bus.

    No-op when the local worker is not currently hosting
    ``notebook_uuid`` (no entry in :data:`_HUBS`).  This is the
    common case for any worker that doesn't have a live editor on
    that notebook.

    Args:
        notebook_uuid: Target notebook id.
        payload: Tag-prefixed wire bytes — same frame the originating
            worker received from a WS client (or generated server-side
            in :func:`apply_save_remap` / :func:`broadcast_agent_presence`).
        source_pid: ``os.getpid()`` of the publisher.  Used for
            log correlation; self-loop suppression already happened
            inside :class:`CoeditBus`.
    """
    if not payload:
        return
    tag = payload[0]
    inner = payload[1:]
    async with _HUBS_LOCK:
        hub = _HUBS.get(notebook_uuid)
    if hub is None:
        return
    async with hub.lock:
        if tag == TAG_SYNC_UPDATE:
            try:
                hub.doc.apply_update(inner)
            except Exception:  # noqa: BLE001 — malformed remote update
                _LOG.exception(
                    "coedit-bus: malformed sync_update from pid=%d nb=%s",
                    source_pid,
                    notebook_uuid,
                )
                return
            hub.dirty = True
            await _broadcast_to_all(hub, payload)
        elif tag == TAG_AWARENESS_UPDATE:
            await _broadcast_to_all(hub, payload)
        elif tag == TAG_CELL_UUID_REMAP:
            try:
                remap = json.loads(inner.decode("utf-8"))
            except Exception:  # noqa: BLE001 — malformed remap json
                _LOG.exception(
                    "coedit-bus: malformed cell_uuid_remap from pid=%d nb=%s",
                    source_pid,
                    notebook_uuid,
                )
                return
            if not isinstance(remap, dict):
                return
            _apply_remap_locked(hub, remap)
            await _broadcast_to_all(hub, payload)
        elif tag == TAG_AGENT_PRESENCE:
            await _broadcast_to_all(hub, payload)
        else:
            _LOG.debug(
                "coedit-bus: ignoring unknown remote tag 0x%02x", tag
            )


def _apply_remap_locked(hub: _NotebookHub, remap: dict[str, str]) -> None:
    """Apply a cell-uuid remap to *hub.doc* under an open ``hub.lock``.

    Shared body between :func:`apply_save_remap` (called by the save
    handler) and :func:`apply_remote_bus_frame` (called by the bus
    listener on remote workers).
    """
    order = hub.doc.get(_CELLS_ORDER_KEY, type=Array)
    texts = hub.doc.get(_CELLS_TEXT_KEY, type=Map)
    with hub.doc.transaction(origin="pql-server-remap"):
        for old_uuid, new_uuid in remap.items():
            if old_uuid == new_uuid:
                continue
            if old_uuid in texts:
                try:
                    prior = texts[old_uuid]
                    prior_value = (
                        prior.to_py() if hasattr(prior, "to_py") else str(prior)
                    )
                except Exception:  # noqa: BLE001
                    prior_value = ""
                del texts[old_uuid]
                texts[new_uuid] = Text(prior_value)
            for i, value in enumerate(list(order)):
                if value == old_uuid:
                    del order[i]
                    order.insert(i, new_uuid)


async def apply_save_remap(notebook_id: str, remap: dict[str, str]) -> None:
    """Apply a save-driven ``cell_uuid`` remap to the live hub.

    Called by the ``/api/notebooks/save`` handler after the
    three-pass reconciler has minted fresh UUIDs for any cell that
    drifted past the Jaccard gate.  When a hub exists for
    ``notebook_id``, we:

    1. Rewrite ``cells_text`` so the new key carries the same
       :class:`pycrdt.Text` value the old key held.
    2. Replace every occurrence of the old uuid in ``cells_order``.
    3. Broadcast a ``TAG_CELL_UUID_REMAP`` frame to all subscribers
       so their local Y.Doc + frontend state pick up the new key
       within the same Y origin marker (``server-remap``) the doc
       transaction carries.

    Idempotent + no-op when no hub is open (``remap`` is empty or
    no one is currently subscribed); the canonical mapping lives in
    ``notebook_cells`` regardless.

    Args:
        notebook_id: The :class:`Notebook` UUID whose hub should be
            mutated.
        remap: ``{client_provided_uuid: reconciled_uuid}`` mapping
            covering only cells whose UUID actually changed.
    """
    if not remap:
        return
    async with _HUBS_LOCK:
        hub = _HUBS.get(notebook_id)
    frame = bytes([TAG_CELL_UUID_REMAP]) + json.dumps(remap).encode("utf-8")
    if hub is not None:
        async with hub.lock:
            _apply_remap_locked(hub, remap)
            hub.dirty = True
            await _broadcast_to_all(hub, frame)
    # Bus publish happens regardless of local-hub presence — another
    # worker may be hosting the notebook even if this one isn't.  No-op
    # in single-worker installs (bus is None).
    await _publish_to_bus(notebook_id, frame)


async def broadcast_agent_presence(notebook_id: str, frame: bytes) -> bool:
    """Fan an agent-presence frame out to every subscriber.

    Phase 105.6 — counterpart to :func:`apply_save_remap`, dedicated
    to the ``TAG_AGENT_PRESENCE`` byte the REST endpoint at
    ``/api/notebooks/{notebook_id}/coedit/agent-presence`` emits.
    No Y.Doc mutation: agent presence is purely informational, the
    canonical state lives in the agent_run record.

    Args:
        notebook_id: Target notebook UUID.
        frame: Fully-formed wire bytes (``tag + payload``).  The
            caller has already JSON-encoded the body.

    Returns:
        ``True`` when at least one subscriber was reachable;
        ``False`` when no hub is open (the caller surfaces this
        as ``status="no-hub"`` to the agent).
    """
    async with _HUBS_LOCK:
        hub = _HUBS.get(notebook_id)
    local_delivered = hub is not None
    if hub is not None:
        async with hub.lock:
            await _broadcast_to_all(hub, frame)
    # Always relay agent-presence over the bus — other workers may
    # host the same notebook even if we don't.  Caller's "delivered"
    # semantics describe local-hub state only; cross-worker fanout is
    # informational.
    await _publish_to_bus(notebook_id, frame)
    return local_delivered


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
                relay_frame = bytes([TAG_SYNC_UPDATE]) + payload
                async with hub.lock:
                    try:
                        hub.doc.apply_update(payload)
                    except Exception:  # noqa: BLE001 — malformed update
                        _LOG.warning(
                            "coedit: malformed update from %s", sub.client_id
                        )
                        continue
                    hub.dirty = True
                    await _broadcast(hub, relay_frame, exclude=sub)
                await _publish_to_bus(notebook_id, relay_frame)
            elif tag == TAG_AWARENESS_UPDATE:
                async with hub.lock:
                    await _broadcast(hub, frame, exclude=sub)
                await _publish_to_bus(notebook_id, frame)
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


__all__ = ["apply_save_remap", "broadcast_agent_presence", "router"]
