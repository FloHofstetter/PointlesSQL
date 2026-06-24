"""A middleware caps request body size so an upload cannot OOM the process.

No body-size limit meant a large upload was read fully into memory and
could DoS the process.  These tests pin the Content-Length middleware's
413 and that a normally-sized request is unaffected.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest


@pytest.mark.asyncio
async def test_oversized_body_rejected_with_413(
    admin_client: httpx.AsyncClient,
    settings_override: Callable[[str, object], None],
) -> None:
    """A body larger than the cap is rejected before the handler runs."""
    settings_override("server.max_request_bytes", 16)
    res = await admin_client.post(
        "/api/me/subscriptions",
        content=b"x" * 64,
        headers={"content-type": "application/json"},
    )
    assert res.status_code == 413


@pytest.mark.asyncio
async def test_normal_body_not_capped(
    admin_client: httpx.AsyncClient,
    settings_override: Callable[[str, object], None],
) -> None:
    """A request within the cap is not turned into a 413."""
    settings_override("server.max_request_bytes", 25 * 1024 * 1024)
    res = await admin_client.post(
        "/api/me/subscriptions",
        json={"webhook_url": "https://hook.test/x", "event_type_filter": "x"},
    )
    assert res.status_code != 413
