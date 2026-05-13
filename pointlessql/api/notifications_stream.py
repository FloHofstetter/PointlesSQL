"""``GET /api/notifications/stream`` — SSE inbox stream (Phase 76.6).

Long-lived Server-Sent Events endpoint that pushes new
``user_notifications`` rows to the caller in near-real-time —
the upgrade path for the existing 60-second poll on the topbar
bell.  The poll fallback stays in place (belt + braces).

Implementation: per-connection ``asyncio.Queue`` registered in
``app.state.notification_streams: dict[int, list[asyncio.Queue]]``
keyed by ``recipient_user_id``.  The fan-out helper in
``services.notifications.fanout`` publishes to every queue
registered for the recipient after each successful inbox INSERT.

A 25-second keep-alive comment is emitted to keep reverse-
proxies (nginx, ALB) from closing the connection.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from pointlessql.api.dependencies import get_user, require_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["notifications"])

_KEEPALIVE_SECONDS = 25.0

# Module-level listener registry — keyed by ``recipient_user_id``.
# Module-level (not app-state) so the fan-out helper in
# ``services.notifications.fanout`` can publish without threading
# the FastAPI ``app`` through every call site.
_LISTENERS: dict[int, list[asyncio.Queue[dict[str, Any]]]] = {}


def _register_listener(user_id: int) -> asyncio.Queue[dict[str, Any]]:
    """Register a fresh per-connection queue under ``user_id``."""
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
    _LISTENERS.setdefault(user_id, []).append(queue)
    return queue


def _unregister_listener(
    user_id: int, queue: asyncio.Queue[dict[str, Any]]
) -> None:
    """Drop the queue from the listener map on disconnect."""
    listeners = _LISTENERS.get(user_id, [])
    try:
        listeners.remove(queue)
    except ValueError:
        pass
    if not listeners:
        _LISTENERS.pop(user_id, None)


def publish_notification(recipient_user_id: int, payload: dict[str, Any]) -> int:
    """Fan a payload out to every live SSE connection for *recipient*.

    Called by ``services.notifications.fanout`` after a successful
    inbox INSERT.  Best-effort — full queues drop the event rather
    than block.

    Args:
        recipient_user_id: Target user.
        payload: JSON-serialisable event payload.

    Returns:
        Count of queues that accepted the payload.
    """
    listeners = _LISTENERS.get(recipient_user_id, [])
    delivered = 0
    for queue in list(listeners):
        try:
            queue.put_nowait(payload)
            delivered += 1
        except asyncio.QueueFull:
            # Slow consumer — skip the event rather than block.
            logger.warning(
                "notification SSE queue full for user_id=%s; dropping event",
                recipient_user_id,
            )
    return delivered


def active_listener_count(user_id: int) -> int:
    """Return the number of live SSE connections for *user_id*."""
    return len(_LISTENERS.get(user_id, []))


async def _stream_events(
    request: Request,
    user_id: int,
    queue: asyncio.Queue[dict[str, Any]],
) -> AsyncIterator[bytes]:
    """Yield SSE-formatted bytes for a single connection."""
    try:
        yield b": connected\n\n"
        while True:
            if await request.is_disconnected():
                return
            try:
                payload = await asyncio.wait_for(
                    queue.get(), timeout=_KEEPALIVE_SECONDS
                )
            except TimeoutError:
                yield b": keep-alive\n\n"
                continue
            data = json.dumps(payload).encode("utf-8")
            yield b"event: notification\n"
            yield b"data: " + data + b"\n\n"
    except asyncio.CancelledError:
        return
    finally:
        _unregister_listener(user_id, queue)


@router.get("/api/notifications/stream")
async def notifications_stream(request: Request) -> StreamingResponse:
    """Return an SSE stream of newly-arriving notifications.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``text/event-stream`` response that yields one
        ``event: notification`` block per fan-out hit + a
        25-second ``: keep-alive`` comment to prevent proxy
        idle-timeouts.
    """
    require_user(request)
    user = get_user(request)
    queue = _register_listener(user["id"])
    return StreamingResponse(
        _stream_events(request, user["id"], queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
