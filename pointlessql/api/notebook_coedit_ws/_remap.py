"""Cell-uuid remap apply + bus-frame dispatch + server-originated broadcasts."""

from __future__ import annotations

import json
import logging

from pycrdt import Array, Map, Text

from pointlessql.api.notebook_coedit_ws._broadcast import (
    broadcast_to_all,
    publish_to_bus,
)
from pointlessql.api.notebook_coedit_ws._constants import (
    CELLS_ORDER_KEY,
    CELLS_TEXT_KEY,
    TAG_AGENT_PRESENCE,
    TAG_AWARENESS_UPDATE,
    TAG_CELL_UUID_REMAP,
    TAG_SYNC_UPDATE,
)
from pointlessql.api.notebook_coedit_ws._state import (
    HUBS,
    HUBS_LOCK,
    NotebookHub,
)

_LOG = logging.getLogger(__name__)


def apply_remap_locked(hub: NotebookHub, remap: dict[str, str]) -> None:
    """Apply a cell-uuid remap to *hub.doc* under an open ``hub.lock``.

    Shared body between :func:`apply_save_remap` (called by the save
    handler) and :func:`apply_remote_bus_frame` (called by the bus
    listener on remote workers).
    """
    order = hub.doc.get(CELLS_ORDER_KEY, type=Array)
    texts = hub.doc.get(CELLS_TEXT_KEY, type=Map)
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
    ``notebook_uuid`` (no entry in :data:`HUBS`).  This is the
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
    async with HUBS_LOCK:
        hub = HUBS.get(notebook_uuid)
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
            await broadcast_to_all(hub, payload)
        elif tag == TAG_AWARENESS_UPDATE:
            await broadcast_to_all(hub, payload)
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
            apply_remap_locked(hub, remap)
            await broadcast_to_all(hub, payload)
        elif tag == TAG_AGENT_PRESENCE:
            await broadcast_to_all(hub, payload)
        else:
            _LOG.debug(
                "coedit-bus: ignoring unknown remote tag 0x%02x", tag
            )


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
    async with HUBS_LOCK:
        hub = HUBS.get(notebook_id)
    frame = bytes([TAG_CELL_UUID_REMAP]) + json.dumps(remap).encode("utf-8")
    if hub is not None:
        async with hub.lock:
            apply_remap_locked(hub, remap)
            hub.dirty = True
            await broadcast_to_all(hub, frame)
    # Bus publish happens regardless of local-hub presence — another
    # worker may be hosting the notebook even if this one isn't.  No-op
    # in single-worker installs (bus is None).
    await publish_to_bus(notebook_id, frame)


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
    async with HUBS_LOCK:
        hub = HUBS.get(notebook_id)
    local_delivered = hub is not None
    if hub is not None:
        async with hub.lock:
            await broadcast_to_all(hub, frame)
    # Always relay agent-presence over the bus — other workers may
    # host the same notebook even if we don't.  Caller's "delivered"
    # semantics describe local-hub state only; cross-worker fanout is
    # informational.
    await publish_to_bus(notebook_id, frame)
    return local_delivered
