"""In-process pub/sub fan-out for the chat WebSocket.

The chat surface has two writers and one reader:

* the propose route writes a :class:`ChatProposal` row and needs
  to notify the WS connection for that ``editor_session_id``;
* the turn-runner writes incremental tokens / tool-progress frames
  during a turn;
* the WS coroutine reads from a per-session ``asyncio.Queue`` and
  forwards frames to the client.

Because the chat backend lives in the same FastAPI process as the
SQL editor backend, a process-local dict of queues is enough — no
Redis dependency.  The broker is intentionally tiny: subscribers
are responsible for their own queue lifecycle (a stale queue is
just one extra dict slot until ``unsubscribe`` is called or the
process exits).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ChatEvent:
    """Single fan-out frame.

    Attributes:
        kind: Event family — one of ``"proposal_created"``,
            ``"token"``, ``"tool_call_start"``,
            ``"tool_call_result"``, ``"final"``, ``"error"``.  WS
            envelope uses this as the ``notify`` discriminator.
        payload: JSON-serialisable dict; the WS coroutine emits it
            verbatim as ``{"notify": kind, "params": payload}``.
    """

    kind: str
    payload: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())


_subscribers: dict[str, list[asyncio.Queue[ChatEvent]]] = {}
_lock: Lock = Lock()


def subscribe(editor_session_id: str) -> asyncio.Queue[ChatEvent]:
    """Register a new queue for *editor_session_id* and return it.

    Args:
        editor_session_id: UUID7 string of the editor tab's chat
            session.  The same session id can have multiple
            subscribers (a second WS connection from a reconnect)
            — both queues get every event.

    Returns:
        An unbounded :class:`asyncio.Queue` carrying every
        :class:`ChatEvent` published for this session.  Caller is
        responsible for calling :func:`unsubscribe` on close.
    """
    queue: asyncio.Queue[ChatEvent] = asyncio.Queue()
    with _lock:
        _subscribers.setdefault(editor_session_id, []).append(queue)
    return queue


def unsubscribe(editor_session_id: str, queue: asyncio.Queue[ChatEvent]) -> None:
    """Remove *queue* from the *editor_session_id* fan-out group."""
    with _lock:
        listeners = _subscribers.get(editor_session_id)
        if not listeners:
            return
        try:
            listeners.remove(queue)
        except ValueError:
            return
        if not listeners:
            _subscribers.pop(editor_session_id, None)


def publish(editor_session_id: str, event: ChatEvent) -> int:
    """Fan *event* out to every subscriber of *editor_session_id*.

    Args:
        editor_session_id: Target session.
        event: The :class:`ChatEvent` to fan out.

    Returns:
        Number of queues that received the event.  ``0`` when no
        WS is listening (e.g. the propose route fires before the
        client opens a chat connection — the row stays in the DB
        and the editor will reload it via REST on next open).
    """
    with _lock:
        listeners = list(_subscribers.get(editor_session_id, []))
    for queue in listeners:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(
                "chat queue full for editor_session_id=%s, dropping %s",
                editor_session_id,
                event.kind,
            )
    return len(listeners)


def publish_proposal_created(
    editor_session_id: str,
    proposal_id: str,
    sql_text: str,
    kind: str,
    rationale: str | None,
) -> int:
    """Convenience wrapper for the propose-route's fan-out frame."""
    return publish(
        editor_session_id,
        ChatEvent(
            kind="proposal_created",
            payload={
                "proposal_id": proposal_id,
                "sql": sql_text,
                "kind": kind,
                "rationale": rationale,
            },
        ),
    )
