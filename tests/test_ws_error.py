"""Phase 121.1.d — pin the WebSocket error-frame wire shape.

The frontend chat panels (``frontend/js/sql_editor/chat.js`` and
``frontend/js/notebook/chat.js``) parse ``frame.error.message``
directly to render error toasts.  This test pins the byte-shape so
the consolidated helper can't drift away from what the JS panels
read — any future change here forces a deliberate frontend update.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from pointlessql.api._ws_error import send_error


class _FakeWebSocket:
    """Minimal stand-in capturing ``send_text`` calls verbatim."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_text(self, payload: str) -> None:
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_send_error_with_request_id() -> None:
    ws = _FakeWebSocket()
    await send_error(
        ws,  # type: ignore[arg-type]
        request_id=42,
        code="permission_denied",
        message="No SELECT on main.bronze.orders",
    )
    assert len(ws.sent) == 1
    body: dict[str, Any] = json.loads(ws.sent[0])
    assert body == {
        "id": 42,
        "error": {"code": "permission_denied", "message": "No SELECT on main.bronze.orders"},
    }


@pytest.mark.asyncio
async def test_send_error_without_request_id_omits_id_key() -> None:
    ws = _FakeWebSocket()
    await send_error(
        ws,  # type: ignore[arg-type]
        request_id=None,
        code="rate_limited",
        message="Slow down",
    )
    body: dict[str, Any] = json.loads(ws.sent[0])
    # Unsolicited error frames must NOT carry the ``id`` key — the
    # frontend uses presence-or-absence to decide whether to
    # correlate with a pending request.
    assert "id" not in body
    assert body == {"error": {"code": "rate_limited", "message": "Slow down"}}


@pytest.mark.asyncio
async def test_send_error_request_id_zero_is_kept() -> None:
    """0 is a valid request id — must not be coerced to omission."""
    ws = _FakeWebSocket()
    await send_error(
        ws,  # type: ignore[arg-type]
        request_id=0,
        code="oops",
        message="zero id",
    )
    body: dict[str, Any] = json.loads(ws.sent[0])
    assert body["id"] == 0
