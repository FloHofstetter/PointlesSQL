"""In-memory broadcast hub for the event-stream output port.

One hub per ``(product_full_name, table)`` key holds the live WebSocket
subscribers.  The pump broadcasts each new CDF row as a JSON-tagged
frame; the WS endpoint owns subscriber lifecycle (register on connect,
deregister on close).

Mirrors the per-notebook coedit hub pattern at
:mod:`pointlessql.api.notebook_coedit_ws._hub` — a lock-guarded lazy
init keyed dict + a release-if-empty helper.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
from typing import Any, Protocol

_LOG = logging.getLogger(__name__)


class _SendableWebSocket(Protocol):
    """Structural protocol matching :class:`starlette.websockets.WebSocket`."""

    async def send_text(self, data: str) -> None:
        """Send one text frame to the client."""
        ...


@dataclasses.dataclass
class EventHub:
    """One in-memory broadcast hub for a (product, table) pair.

    Attributes:
        key: The canonical ``(catalog.schema, table)`` key.
        subscribers: Live WebSocket subscribers.  Mutated under
            :attr:`lock`.
        lock: Asyncio lock guarding :attr:`subscribers` against
            concurrent register/deregister.
    """

    key: tuple[str, str]
    subscribers: list[_SendableWebSocket]
    lock: asyncio.Lock


_HUBS: dict[tuple[str, str], EventHub] = {}
_HUBS_LOCK = asyncio.Lock()


async def get_or_create_hub(product_full_name: str, table: str) -> EventHub:
    """Return the live hub for ``(product_full_name, table)``.

    Cold path creates the hub with an empty subscriber list.  Warm
    path returns the existing one.

    Args:
        product_full_name: ``catalog.schema`` of the source product.
        table: Table the event stream is sourced from.

    Returns:
        The :class:`EventHub`.
    """
    key = (product_full_name, table)
    async with _HUBS_LOCK:
        hub = _HUBS.get(key)
        if hub is not None:
            return hub
        hub = EventHub(key=key, subscribers=[], lock=asyncio.Lock())
        _HUBS[key] = hub
        return hub


async def register(hub: EventHub, websocket: _SendableWebSocket) -> None:
    """Add *websocket* to the hub's subscriber list."""
    async with hub.lock:
        hub.subscribers.append(websocket)


async def deregister(hub: EventHub, websocket: _SendableWebSocket) -> None:
    """Remove *websocket* if present.  No-op when absent."""
    async with hub.lock:
        try:
            hub.subscribers.remove(websocket)
        except ValueError:
            return


async def release_hub_if_empty(product_full_name: str, table: str) -> None:
    """Drop the hub when no subscribers remain."""
    key = (product_full_name, table)
    async with _HUBS_LOCK:
        hub = _HUBS.get(key)
        if hub is None or hub.subscribers:
            return
        del _HUBS[key]


async def broadcast(hub: EventHub, frame: dict[str, Any]) -> int:
    """Send *frame* (JSON-encoded) to every live subscriber.

    Best-effort: any send failure deregisters the failing subscriber
    without raising.

    Returns:
        The number of subscribers the frame was delivered to.
    """
    payload = json.dumps(frame, default=str)
    delivered = 0
    async with hub.lock:
        targets = list(hub.subscribers)
    failed: list[_SendableWebSocket] = []
    for ws in targets:
        try:
            await ws.send_text(payload)
            delivered += 1
        # bare-broad-ok: any send failure means the subscriber is gone; drop it
        except Exception:  # noqa: BLE001
            failed.append(ws)
            _LOG.debug("event_port: broadcast failed for one subscriber")
    if failed:
        async with hub.lock:
            for ws in failed:
                try:
                    hub.subscribers.remove(ws)
                except ValueError:
                    pass
    return delivered


def subscriber_count(product_full_name: str, table: str) -> int:
    """Return the live subscriber count, 0 when the hub does not exist."""
    hub = _HUBS.get((product_full_name, table))
    if hub is None:
        return 0
    return len(hub.subscribers)


def hub_keys() -> list[tuple[str, str]]:
    """Return a snapshot of the active hub keys (test helper)."""
    return list(_HUBS.keys())
