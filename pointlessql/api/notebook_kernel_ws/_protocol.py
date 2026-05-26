"""JSON-RPC envelope helpers shared between handler + pump.

Pure protocol layer:

* ``RESERVED_BOOTSTRAP_HASH`` — sentinel content hash that
  flags echo frames from the in-kernel bootstrap so the pump can
  skip them without leaking ``__pql_sql_bootstrap__`` rows into
  ``notebook_outputs``.
* :func:`user_can_use_editor` — auth gate.
* :func:`send_error` — JSON-RPC error envelope serializer.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from pointlessql.types import UserInfo

RESERVED_BOOTSTRAP_HASH = "__pql_sql_bootstrap__"


def user_can_use_editor(user: UserInfo) -> bool:
    """Return whether the resolved user is permitted to drive the editor.

    The gate accepts any authenticated user — matching the
    workspace + edit HTTP routes, which use ``require_user``
    rather than ``require_admin``.
    """
    return bool(user.get("id"))


async def send_error(
    websocket: WebSocket,
    *,
    request_id: int | None,
    code: str,
    message: str,
) -> None:
    """Send a JSON-RPC error frame for a specific inbound request id.

    Args:
        websocket: The active WebSocket.
        request_id: Original ``id`` from the request frame, or
            ``None`` when the failing input never produced one.
        code: Short identifier — caller-actionable, mirrors the
            upstream Jupyter convention.
        message: One-sentence human-readable detail.
    """
    payload: dict[str, Any] = {
        "id": request_id,
        "error": {"code": code, "message": message},
    }
    try:
        await websocket.send_text(json.dumps(payload))
    except WebSocketDisconnect:
        return
