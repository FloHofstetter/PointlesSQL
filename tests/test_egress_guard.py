"""SSRF egress guard for user-supplied destination URLs.

The guard is disabled suite-wide (it does real DNS); these tests
re-enable it via ``settings_override`` and pin both the address-class
blocks and the send-time enforcement in the webhook dispatcher.  Public
targets use IP literals so no test makes a real DNS query.
"""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from pointlessql.services.egress_guard import EgressError, assert_public_http_url

_ENV = {"specversion": "1.0", "id": "e1", "type": "test", "source": "/t"}


@pytest.fixture
def egress_on(settings_override: Callable[[str, object], None]) -> None:
    """Enable the egress guard for this test."""
    settings_override("egress.enabled", True)


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://127.0.0.1/",  # loopback
        "http://localhost/hook",  # loopback by name
        "http://[::1]/",  # IPv6 loopback
        "http://10.0.0.5/",  # private
        "http://192.168.1.1/",  # private
        "http://169.254.10.10/",  # link-local
        "http://[::ffff:127.0.0.1]/",  # IPv4-mapped loopback
    ],
)
def test_blocks_non_public_targets(egress_on: None, url: str) -> None:
    """Loopback / private / link-local / metadata targets are rejected."""
    with pytest.raises(EgressError):
        assert_public_http_url(url)


@pytest.mark.parametrize("url", ["ftp://8.8.8.8/x", "file:///etc/passwd", "gopher://8.8.8.8/"])
def test_blocks_non_http_schemes(egress_on: None, url: str) -> None:
    """Only http and https are permitted."""
    with pytest.raises(EgressError):
        assert_public_http_url(url)


def test_allows_public_target(egress_on: None) -> None:
    """A public IP literal passes (no DNS query needed)."""
    assert_public_http_url("https://8.8.8.8/hook") is None


def test_disabled_guard_is_noop() -> None:
    """With the guard off (suite default), even metadata URLs pass."""
    assert_public_http_url("http://169.254.169.254/") is None


def test_allowlist_narrows_to_named_hosts(
    settings_override: Callable[[str, object], None],
) -> None:
    """A non-empty allowlist rejects hosts outside it."""
    settings_override("egress.enabled", True)
    settings_override("egress.allowed_hosts", "8.8.8.8, hooks.example")
    assert_public_http_url("https://8.8.8.8/x") is None
    with pytest.raises(EgressError):
        assert_public_http_url("https://1.1.1.1/x")


def test_allow_private_escape_hatch(
    settings_override: Callable[[str, object], None],
) -> None:
    """allow_private lets an install reach an internal relay on purpose."""
    settings_override("egress.enabled", True)
    settings_override("egress.allow_private", True)
    assert_public_http_url("http://127.0.0.1/internal") is None


@pytest.mark.asyncio
async def test_dispatch_webhook_blocks_at_send_time(egress_on: None) -> None:
    """A rebind to a metadata IP is caught before the POST fires."""
    from pointlessql.services.alert_dispatcher import dispatch_webhook

    client = MagicMock()
    client.post = AsyncMock(return_value=MagicMock(status_code=200))
    ok = await dispatch_webhook("http://169.254.169.254/", _ENV, client=client)
    assert ok is False
    client.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_webhook_allows_public_target(egress_on: None) -> None:
    """A public target still delivers through the guard."""
    from pointlessql.services.alert_dispatcher import dispatch_webhook

    client = MagicMock()
    client.post = AsyncMock(return_value=MagicMock(status_code=200))
    ok = await dispatch_webhook("https://8.8.8.8/hook", _ENV, client=client)
    assert ok is True
    client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_subscription_create_rejects_internal_url(
    non_admin_client: httpx.AsyncClient,
    settings_override: Callable[[str, object], None],
) -> None:
    """POST /api/me/subscriptions refuses a metadata URL with 400."""
    settings_override("egress.enabled", True)
    res = await non_admin_client.post(
        "/api/me/subscriptions",
        json={
            "webhook_url": "http://169.254.169.254/",
            "event_type_filter": "pointlessql.data_product.published",
        },
    )
    assert res.status_code == 400, res.text
