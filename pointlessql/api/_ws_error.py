"""Shared WebSocket error-frame emitter for chat WS routes.

Wire shape is locked by the frontend chat panels — ``chat.js``
(``frontend/js/sql_editor/chat.js``) and ``notebook/chat.js`` both
parse ``frame.error.message`` directly to render error toasts.
This module consolidates two byte-identical ``_send_error``
helpers in ``sql_chat_ws.py`` and ``notebook_chat_ws.py`` into one
shared function so future error-vocabulary changes (new codes,
extra fields) land in a single place.  The wire bytes are
unchanged on purpose: this is a code-dedup, not a protocol change.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import WebSocket


async def send_error(
    websocket: WebSocket,
    *,
    request_id: int | None,
    code: str,
    message: str,
) -> None:
    """Send a ``{"id": ..., "error": {"code": ..., "message": ...}}`` frame.

    The optional ``id`` echoes the client's request id so the panel
    can correlate the error with the originating request; unsolicited
    error frames omit it.

    Args:
        websocket: Already-accepted WebSocket connection.
        request_id: Echoed back as ``id``; ``None`` for unsolicited
            error frames.
        code: Stable machine-readable identifier consumed by the
            frontend toast layer (``permission_denied``,
            ``rate_limited``, …).
        message: Human-readable explanation surfaced verbatim in
            the chat panel toast.
    """
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if request_id is not None:
        body["id"] = request_id
    await websocket.send_text(json.dumps(body))
