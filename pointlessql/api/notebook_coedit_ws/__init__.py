"""real-time co-edit WebSocket hub — split per concern.

The pre-Phase-111.6 layout collapsed every helper into one ~779 LOC
``notebook_coedit_ws.py`` module.  Phase 111.6 split it along the
natural axes:

* :mod:`._constants`  — wire-protocol tag bytes
  (``TAG_SYNC_STEP1`` / … / ``TAG_AGENT_PRESENCE``), the
  bus-relayed tag set, and the queue/flush tuning knobs.
* :mod:`._state`      — :class:`ClientSubscription` and
  :class:`NotebookHub` dataclasses, the :data:`HUBS` singleton,
  and :func:`bind_coedit_bus` / :func:`get_bus`.
* :mod:`._seed`       — cold-init helpers
  (:func:`build_seed`, :func:`extract_seed_cells`).
* :mod:`._hub`        — hub lifecycle
  (:func:`get_or_create_hub`, :func:`release_hub_if_empty`,
  :func:`flush_loop`).
* :mod:`._broadcast`  — :func:`broadcast`, :func:`broadcast_to_all`,
  :func:`publish_to_bus`, :func:`close_overflowed`, :func:`pump`.
* :mod:`._remap`      — cell-uuid remap apply + bus-frame dispatch +
  server-originated broadcasts (:func:`apply_save_remap`,
  :func:`broadcast_agent_presence`, :func:`apply_remote_bus_frame`).
* :mod:`._endpoint`   — the ``/ws/notebook/coedit/{notebook_id}``
  router + handler.

Wires :mod:`pointlessql.services.notebook.coedit` (the storage
primitive shipped in Sprint 105.1) to multiple browser tabs editing
the same notebook.  A per-``notebook_id`` :class:`NotebookHub`
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
* ``0x05`` — ``agent_presence``: server → all clients.  JSON
  payload describing which agents are currently editing.

Persistence cadence: the hub flushes the live Doc to
``notebook_crdt_state`` once per second when dirty + once
synchronously when the last subscriber leaves.  The teardown path
also opportunistically triggers compaction when
:func:`coedit_service.needs_compaction` says the blob has crossed
size or TTL bounds.
"""

from __future__ import annotations

from pointlessql.api.notebook_coedit_ws._constants import (
    TAG_AGENT_PRESENCE,
    TAG_AWARENESS_UPDATE,
    TAG_CELL_UUID_REMAP,
    TAG_SYNC_STEP1,
    TAG_SYNC_STEP2,
    TAG_SYNC_UPDATE,
)
from pointlessql.api.notebook_coedit_ws._endpoint import router
from pointlessql.api.notebook_coedit_ws._remap import (
    apply_remote_bus_frame,
    apply_save_remap,
    broadcast_agent_presence,
)
from pointlessql.api.notebook_coedit_ws._state import HUBS as _HUBS
from pointlessql.api.notebook_coedit_ws._state import bind_coedit_bus

__all__ = [
    "TAG_AGENT_PRESENCE",
    "TAG_AWARENESS_UPDATE",
    "TAG_CELL_UUID_REMAP",
    "TAG_SYNC_STEP1",
    "TAG_SYNC_STEP2",
    "TAG_SYNC_UPDATE",
    "_HUBS",
    "apply_remote_bus_frame",
    "apply_save_remap",
    "bind_coedit_bus",
    "broadcast_agent_presence",
    "router",
]
