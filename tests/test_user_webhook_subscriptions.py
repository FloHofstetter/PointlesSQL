"""Tests for the per-user webhook subscriptions.

Covers:

* POST creates a row + returns the HMAC secret exactly once.
* GET list does NOT echo the secret.
* PUT toggles ``is_active``.
* DELETE removes the row.
* ``deliver_to_user_subscriptions`` fires for matching events.
* Filter mismatch (event type) → no fire.
* DP-ref filter exact match works.
* Wildcard ``*`` event type matches every DP event.
* Cross-user iso: one user can't see another user's row.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models.notifications import UserWebhookSubscription
from pointlessql.services.notifications import deliver_to_user_subscriptions


def _mock_transport(captured: dict[str, Any], status: int = 200) -> httpx.MockTransport:
    """Build a transport that captures the first matching POST."""

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = bytes(request.content)
        captured["sig"] = request.headers.get("X-PointlesSQL-Signature")
        captured["ctype"] = request.headers.get("Content-Type")
        captured["called"] = captured.get("called", 0) + 1
        return httpx.Response(status)

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_returns_secret_once(
    admin_client: httpx.AsyncClient,
) -> None:
    """POST /api/me/subscriptions returns ``hmac_secret`` in the response."""
    res = await admin_client.post(
        "/api/me/subscriptions",
        json={
            "webhook_url": "https://example.com/hook",
            "event_type_filter": "pointlessql.data_product.commented",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["webhook_url"] == "https://example.com/hook"
    assert body["hmac_secret"]  # not empty
    assert len(body["hmac_secret"]) >= 16


@pytest.mark.asyncio
async def test_list_does_not_echo_secret(
    admin_client: httpx.AsyncClient,
) -> None:
    """GET list omits the HMAC secret."""
    await admin_client.post(
        "/api/me/subscriptions",
        json={
            "webhook_url": "https://example.com/x",
            "event_type_filter": "*",
        },
    )
    res = await admin_client.get("/api/me/subscriptions")
    assert res.status_code == 200
    rows = res.json()["subscriptions"]
    assert len(rows) == 1
    assert "hmac_secret" not in rows[0]


@pytest.mark.asyncio
async def test_put_toggles_active(
    admin_client: httpx.AsyncClient,
) -> None:
    """PUT can toggle ``is_active`` off and back on."""
    created = (
        await admin_client.post(
            "/api/me/subscriptions",
            json={
                "webhook_url": "https://example.com/x",
                "event_type_filter": "*",
            },
        )
    ).json()
    sub_id = created["id"]
    res = await admin_client.put(
        f"/api/me/subscriptions/{sub_id}",
        json={"is_active": False},
    )
    assert res.json()["is_active"] is False
    res2 = await admin_client.put(
        f"/api/me/subscriptions/{sub_id}",
        json={"is_active": True},
    )
    assert res2.json()["is_active"] is True


@pytest.mark.asyncio
async def test_delete_removes_row(
    admin_client: httpx.AsyncClient,
) -> None:
    """DELETE drops the row; GET reflects the removal."""
    created = (
        await admin_client.post(
            "/api/me/subscriptions",
            json={
                "webhook_url": "https://example.com/x",
                "event_type_filter": "*",
            },
        )
    ).json()
    res = await admin_client.delete(f"/api/me/subscriptions/{created['id']}")
    assert res.json() == {"deleted": True}
    rows = (await admin_client.get("/api/me/subscriptions")).json()["subscriptions"]
    assert rows == []


@pytest.mark.asyncio
async def test_cross_user_isolation(
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """One user's subscription is invisible to another."""
    admin_sub = (
        await admin_client.post(
            "/api/me/subscriptions",
            json={
                "webhook_url": "https://example.com/x",
                "event_type_filter": "*",
            },
        )
    ).json()
    res = await non_admin_client.put(
        f"/api/me/subscriptions/{admin_sub['id']}",
        json={"is_active": False},
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


def _make_envelope(event_type: str, dp_ref: str = "main.sales_gold") -> dict[str, object]:
    """Build a CloudEvents envelope shaped like governance.py emits."""
    return {
        "specversion": "1.0",
        "id": "test-1",
        "source": "/test",
        "type": event_type,
        "time": datetime.datetime.now(datetime.UTC).isoformat(),
        "datacontenttype": "application/json",
        "data": {"data_product_ref": dp_ref},
    }


def _seed_sub(
    *,
    event_type_filter: str,
    dp_ref_filter: str | None = None,
    webhook_url: str = "https://hooks.test/incoming",
) -> int:
    """Seed one subscription for the admin user; return its id."""
    factory = app.state.session_factory
    from pointlessql.models.auth import User

    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        admin_id = (
            session.execute(select(User).where(User.email == "test@test.com")).scalar_one().id
        )
        sub = UserWebhookSubscription(
            workspace_id=1,
            user_id=admin_id,
            webhook_url=webhook_url,
            hmac_secret="secret-xyz",
            event_type_filter=event_type_filter,
            dp_ref_filter=dp_ref_filter,
            is_active=1,
            created_at=now,
        )
        session.add(sub)
        session.commit()
        return sub.id


@pytest.mark.asyncio
async def test_delivery_fires_for_matching_event() -> None:
    """An active subscription matching the envelope type fires one POST."""
    _seed_sub(event_type_filter="pointlessql.data_product.commented")
    envelope = _make_envelope("pointlessql.data_product.commented")
    captured: dict[str, Any] = {}
    async with httpx.AsyncClient(transport=_mock_transport(captured)) as client:
        log = await deliver_to_user_subscriptions(
            app.state.session_factory,
            envelope,
            workspace_id=1,
            client=client,
        )
    assert captured.get("called") == 1
    assert len(log) == 1
    assert log[0]["ok"] is True


@pytest.mark.asyncio
async def test_delivery_wildcard_event_type() -> None:
    """``event_type_filter='*'`` matches any DP event."""
    _seed_sub(event_type_filter="*")
    envelope = _make_envelope("pointlessql.data_product.reviewed")
    captured: dict[str, Any] = {}
    async with httpx.AsyncClient(transport=_mock_transport(captured)) as client:
        log = await deliver_to_user_subscriptions(
            app.state.session_factory,
            envelope,
            workspace_id=1,
            client=client,
        )
    assert captured.get("called") == 1
    assert len(log) == 1


@pytest.mark.asyncio
async def test_delivery_filter_mismatch_skips() -> None:
    """Event type mismatch yields zero fires."""
    _seed_sub(event_type_filter="pointlessql.data_product.commented")
    envelope = _make_envelope("pointlessql.data_product.reviewed")
    captured: dict[str, Any] = {}
    async with httpx.AsyncClient(transport=_mock_transport(captured)) as client:
        log = await deliver_to_user_subscriptions(
            app.state.session_factory,
            envelope,
            workspace_id=1,
            client=client,
        )
    assert captured.get("called", 0) == 0
    assert log == []


@pytest.mark.asyncio
async def test_delivery_dp_ref_filter_exact_match() -> None:
    """``dp_ref_filter='main.other_schema'`` skips other DPs."""
    _seed_sub(
        event_type_filter="*",
        dp_ref_filter="main.other_schema",
    )
    envelope = _make_envelope(
        "pointlessql.data_product.commented",
        dp_ref="main.sales_gold",
    )
    captured: dict[str, Any] = {}
    async with httpx.AsyncClient(transport=_mock_transport(captured)) as client:
        log = await deliver_to_user_subscriptions(
            app.state.session_factory,
            envelope,
            workspace_id=1,
            client=client,
        )
    assert captured.get("called", 0) == 0
    assert log == []


@pytest.mark.asyncio
async def test_delivery_signs_with_hmac() -> None:
    """The webhook POST carries an ``X-PointlesSQL-Signature`` header."""
    _seed_sub(event_type_filter="*")
    envelope = _make_envelope("pointlessql.data_product.commented")
    captured: dict[str, Any] = {}
    async with httpx.AsyncClient(transport=_mock_transport(captured)) as client:
        await deliver_to_user_subscriptions(
            app.state.session_factory,
            envelope,
            workspace_id=1,
            client=client,
        )
    assert captured["sig"].startswith("sha256=")
    assert json.loads(captured["body"].decode("utf-8"))["id"] == "test-1"
