"""Dataclasses + module-singleton state shared by the co-edit hub."""

from __future__ import annotations

import asyncio
import dataclasses
from typing import TYPE_CHECKING

from fastapi import WebSocket
from pycrdt import Doc

if TYPE_CHECKING:
    from pointlessql.services.notebook.coedit_bus import CoeditBus


@dataclasses.dataclass(slots=True)
class ClientSubscription:
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
class NotebookHub:
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
    subscribers: list[ClientSubscription]
    lock: asyncio.Lock
    dirty: bool
    flush_task: asyncio.Task[None] | None


# Module-level singleton — the asyncio loop is single-threaded per
# uvicorn worker so a plain dict + lock pair is enough.  Phase 109's
# cross-worker fanout rides PG LISTEN/NOTIFY through
# :class:`pointlessql.services.notebook.coedit_bus.CoeditBus`; the
# bus stays optional (default-off feature flag) so single-worker
# installs are unaffected.
HUBS: dict[str, NotebookHub] = {}
HUBS_LOCK = asyncio.Lock()

# module-level handle on the bus.  Wrapped in a single-
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


def get_bus() -> CoeditBus | None:
    """Return the currently-bound :class:`CoeditBus`, or ``None``."""
    return _bus_ref[0]
