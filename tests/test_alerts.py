"""Tests for the Sprint-55 alerting surface."""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
from typing import Any
from unittest.mock import AsyncMock
from xml.etree import ElementTree as ET

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.exceptions import ValidationError
from pointlessql.services import alert_dispatcher, alert_feeds
from pointlessql.services import alerts as alerts_service


def _make_saved_query(*, owner_id: int, title: str = "Fixture Q") -> int:
    """Insert a saved query for alert FKs; return the new id."""
    from pointlessql.services import saved_queries as sq_service

    factory = app.state.session_factory
    row = sq_service.create_saved_query(
        factory,
        owner_id=owner_id,
        title=title,
        description=None,
        sql_text="SELECT 1 AS n",
        is_shared=False,
    )
    return int(row["id"])


# -- condition evaluator ------------------------------------------------------


def test_evaluate_condition_each_operator() -> None:
    assert alerts_service.evaluate_condition(10, "gt", 5) is True
    assert alerts_service.evaluate_condition(5, "gt", 5) is False
    assert alerts_service.evaluate_condition(1, "lt", 5) is True
    assert alerts_service.evaluate_condition(5, "eq", 5) is True
    assert alerts_service.evaluate_condition(5, "ne", 4) is True


def test_evaluate_condition_unknown_op_raises() -> None:
    with pytest.raises(ValidationError):
        alerts_service.evaluate_condition(1, "ge", 0)


# -- CloudEvents envelope -----------------------------------------------------


def test_build_cloudevent_has_mandatory_fields() -> None:
    now = datetime.datetime.now(datetime.UTC)
    env = alerts_service.build_cloudevent(
        event_id="deadbeef" * 4,
        alert_slug="daily-orders",
        saved_query_slug="daily-q-abc123",
        condition_op="gt",
        threshold=100,
        row_count=142,
        duration_ms=37,
        referenced_tables=["main.sales.orders"],
        fired_at=now,
    )
    # CloudEvents 1.0 mandates these top-level fields on every envelope.
    for key in ("specversion", "id", "source", "type", "time"):
        assert key in env, f"missing {key}"
    assert env["specversion"] == "1.0"
    assert env["type"] == "sql.pointlessql.alert.fired.v1"
    assert env["source"].endswith("/daily-orders")
    # Phase-13 cost-gate payload fields must be present so that contract
    # stays forward-compatible without a payload-shape break.
    assert env["data"]["duration_ms"] == 37
    assert env["data"]["referenced_tables"] == ["main.sales.orders"]
    assert env["data"]["row_count"] == 142


# -- dispatcher --------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_webhook_signs_body_and_returns_true_on_2xx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = {
        "specversion": "1.0",
        "id": "abc",
        "source": "/a",
        "type": "t",
        "time": "2026-04-18T12:00:00+00:00",
        "data": {},
    }
    secret = "shhhh-secret"
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = bytes(request.content)
        captured["sig"] = request.headers.get("X-PointlesSQL-Signature")
        captured["ctype"] = request.headers.get("Content-Type")
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        ok = await alert_dispatcher.dispatch_webhook(
            "https://example.test/hook",
            envelope,
            hmac_secret=secret,
            client=client,
        )
    assert ok is True
    # Exactly reproduces our canonical serialisation.
    expected_body = alert_dispatcher.canonicalise_envelope(envelope)
    assert captured["body"] == expected_body
    assert captured["ctype"] == "application/cloudevents+json"
    expected_sig = "sha256=" + hmac.new(secret.encode(), expected_body, hashlib.sha256).hexdigest()
    assert captured["sig"] == expected_sig


@pytest.mark.asyncio
async def test_dispatch_webhook_retries_on_5xx_then_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(502)

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(alert_dispatcher, "_sleep", no_sleep)
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        ok = await alert_dispatcher.dispatch_webhook(
            "https://example.test/hook",
            {
                "specversion": "1.0",
                "id": "a",
                "source": "/a",
                "type": "t",
                "time": "2026-04-18T12:00:00+00:00",
                "data": {},
            },
            client=client,
        )
    assert ok is False
    assert call_count["n"] == 3  # initial + 2 retries


@pytest.mark.asyncio
async def test_dispatch_webhook_4xx_is_permanent_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(400)

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(alert_dispatcher, "_sleep", no_sleep)
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        ok = await alert_dispatcher.dispatch_webhook(
            "https://example.test/hook",
            {
                "specversion": "1.0",
                "id": "a",
                "source": "/a",
                "type": "t",
                "time": "2026-04-18T12:00:00+00:00",
                "data": {},
            },
            client=client,
        )
    assert ok is False
    assert call_count["n"] == 1


# -- feed renderers ----------------------------------------------------------


def test_render_atom_has_required_structure() -> None:
    events = [
        {
            "id": 1,
            "alert_id": 10,
            "alert_slug": "daily-orders",
            "alert_title": "Daily orders",
            "event_id": "abc123",
            "fired_at": "2026-04-18T12:00:00+00:00",
            "row_count": 42,
            "outcome": "fired",
            "payload_json": '{"specversion":"1.0","id":"abc123"}',
        },
    ]
    xml = alert_feeds.render_atom(
        events,
        user_email="flo@test.com",
        base_url="http://test",
    )
    # Starts with an XML prolog and parses.
    assert xml.startswith("<?xml ")
    root = ET.fromstring(xml)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    assert root.tag.endswith("feed")
    entries = root.findall("a:entry", ns)
    assert len(entries) == 1
    entry_id = entries[0].find("a:id", ns)
    assert entry_id is not None and entry_id.text == "urn:pointlessql:alert:abc123"


def test_render_json_feed_has_version_and_items() -> None:
    events = [
        {
            "id": 1,
            "alert_id": 10,
            "alert_slug": "daily-orders",
            "alert_title": "Daily orders",
            "event_id": "abc123",
            "fired_at": "2026-04-18T12:00:00+00:00",
            "row_count": 42,
            "outcome": "fired",
            "payload_json": '{"specversion":"1.0","id":"abc123"}',
        },
    ]
    feed = alert_feeds.render_json_feed(
        events,
        user_email="flo@test.com",
        base_url="http://test",
    )
    assert feed["version"].startswith("https://jsonfeed.org/version/1.")
    assert feed["items"][0]["id"] == "abc123"
    assert feed["items"][0]["title"].startswith("Daily orders")


# -- service CRUD ------------------------------------------------------------


def test_create_alert_requires_title_and_valid_op() -> None:
    factory = app.state.session_factory
    saved_query_id = _make_saved_query(owner_id=1)
    with pytest.raises(ValidationError):
        alerts_service.create_alert(
            factory,
            owner_id=1,
            title="",
            saved_query_id=saved_query_id,
            cron_expr="*/5 * * * *",
            condition_op="gt",
            threshold=0,
        )
    with pytest.raises(ValidationError):
        alerts_service.create_alert(
            factory,
            owner_id=1,
            title="Ok",
            saved_query_id=saved_query_id,
            cron_expr="*/5 * * * *",
            condition_op="between",
            threshold=0,
        )


def test_create_and_fetch_alert_round_trip() -> None:
    factory = app.state.session_factory
    saved_query_id = _make_saved_query(owner_id=1)
    row = alerts_service.create_alert(
        factory,
        owner_id=1,
        title="Daily orders",
        saved_query_id=saved_query_id,
        cron_expr="*/10 * * * *",
        condition_op="gt",
        threshold=100,
    )
    got = alerts_service.get_by_slug(
        factory,
        row["slug"],
        user_id=1,
        is_admin=True,
    )
    assert got is not None
    assert got["title"] == "Daily orders"
    assert got["destinations"] == []
    assert got["backing_job_id"] is not None, "backing Job should be materialised"


def test_non_owner_cannot_see_or_mutate_alert() -> None:
    factory = app.state.session_factory
    saved_query_id = _make_saved_query(owner_id=1)
    row = alerts_service.create_alert(
        factory,
        owner_id=1,
        title="Admin alert",
        saved_query_id=saved_query_id,
        cron_expr="*/5 * * * *",
        condition_op="gt",
        threshold=0,
    )
    # Non-admin user_id=2 should not see admin's row.
    assert (
        alerts_service.get_by_slug(
            factory,
            row["slug"],
            user_id=2,
            is_admin=False,
        )
        is None
    )
    # … and cannot mutate it either.
    assert (
        alerts_service.update_by_slug(
            factory,
            row["slug"],
            user_id=2,
            is_admin=False,
            is_active=False,
        )
        is None
    )
    assert (
        alerts_service.delete_by_slug(
            factory,
            row["slug"],
            user_id=2,
            is_admin=False,
        )
        is False
    )


def test_add_and_remove_webhook_destination() -> None:
    factory = app.state.session_factory
    saved_query_id = _make_saved_query(owner_id=1)
    row = alerts_service.create_alert(
        factory,
        owner_id=1,
        title="With dest",
        saved_query_id=saved_query_id,
        cron_expr="*/5 * * * *",
        condition_op="gt",
        threshold=0,
    )
    dest = alerts_service.add_destination(
        factory,
        row["slug"],
        user_id=1,
        is_admin=True,
        kind="webhook",
        webhook_url="https://example.test/h",
        hmac_secret="shhh",
    )
    assert dest is not None
    assert dest["kind"] == "webhook"
    assert dest["has_hmac"] is True
    # Deletion round-trip.
    assert (
        alerts_service.delete_destination(
            factory,
            row["slug"],
            dest["id"],
            user_id=1,
            is_admin=True,
        )
        is True
    )


def test_webhook_destination_requires_url() -> None:
    factory = app.state.session_factory
    saved_query_id = _make_saved_query(owner_id=1)
    row = alerts_service.create_alert(
        factory,
        owner_id=1,
        title="Needs url",
        saved_query_id=saved_query_id,
        cron_expr="*/5 * * * *",
        condition_op="gt",
        threshold=0,
    )
    with pytest.raises(ValidationError):
        alerts_service.add_destination(
            factory,
            row["slug"],
            user_id=1,
            is_admin=True,
            kind="webhook",
            webhook_url="",
        )


# -- HTTP surface ------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_create_list_delete_alert_round_trip(admin_client: httpx.AsyncClient) -> None:
    saved_query_id = _make_saved_query(owner_id=1, title="via HTTP")
    create = await admin_client.post(
        "/api/alerts",
        json={
            "title": "API alert",
            "saved_query_id": saved_query_id,
            "cron_expr": "*/5 * * * *",
            "condition_op": "gt",
            "threshold": 0,
        },
    )
    assert create.status_code == 200
    slug = create.json()["slug"]
    listing = await admin_client.get("/api/alerts")
    assert listing.status_code == 200
    slugs = [a["slug"] for a in listing.json()]
    assert slug in slugs
    deletion = await admin_client.delete(f"/api/alerts/{slug}")
    assert deletion.status_code == 204


@pytest.mark.asyncio
async def test_feed_atom_rejects_bad_token(admin_client: httpx.AsyncClient) -> None:
    res = await admin_client.get("/alerts/feed.atom", params={"token": "nope"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_feed_atom_roundtrip_with_valid_token(admin_client: httpx.AsyncClient) -> None:
    # Admin requests their feed token, then fetches the feed.
    token_res = await admin_client.get("/api/me/feed-token")
    assert token_res.status_code == 200
    token = token_res.json()["token"]
    assert token
    feed = await admin_client.get("/alerts/feed.atom", params={"token": token})
    assert feed.status_code == 200
    assert "application/atom+xml" in feed.headers.get("content-type", "")
    root = ET.fromstring(feed.text)
    assert root.tag.endswith("feed")


@pytest.mark.asyncio
async def test_feed_json_roundtrip_with_valid_token(admin_client: httpx.AsyncClient) -> None:
    token_res = await admin_client.get("/api/me/feed-token")
    token = token_res.json()["token"]
    feed = await admin_client.get("/alerts/feed.json", params={"token": token})
    assert feed.status_code == 200
    data = feed.json()
    assert data["version"].startswith("https://jsonfeed.org/")
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_stranger_cannot_fetch_alert_by_slug(admin_client: httpx.AsyncClient, non_admin_client: httpx.AsyncClient) -> None:
    saved_query_id = _make_saved_query(owner_id=1, title="Stranger test")
    create = await admin_client.post(
        "/api/alerts",
        json={
            "title": "Admin only",
            "saved_query_id": saved_query_id,
            "cron_expr": "*/5 * * * *",
            "condition_op": "gt",
            "threshold": 0,
        },
    )
    slug = create.json()["slug"]
    res = await non_admin_client.get(f"/api/alerts/{slug}")
    assert res.status_code == 404


# -- scheduler executor ------------------------------------------------------


@pytest.mark.asyncio
async def test_alert_check_executor_fires_and_records_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The executor evaluates the condition and records one event row."""
    from pointlessql.pql.pql import SQLResult
    from pointlessql.services import scheduler as scheduler_module
    from pointlessql.types import UserInfo

    saved_query_id = _make_saved_query(owner_id=1, title="Exec test")
    factory = app.state.session_factory
    alert_row = alerts_service.create_alert(
        factory,
        owner_id=1,
        title="Exec alert",
        saved_query_id=saved_query_id,
        cron_expr="*/5 * * * *",
        condition_op="gt",
        threshold=0,
    )
    alert_id = int(alert_row["id"])

    # Stub SQL execution — no UC round-trip, no DuckDB.
    class _FakePrepared:
        refs: list[str] = []

    def fake_prepare(_sql: str) -> Any:
        return _FakePrepared()

    def fake_sql(
        _sql: str,
        *,
        approved_tables: dict[str, str],
        max_rows: int,
        conn: Any = None,
        explain: bool = False,
    ) -> SQLResult:
        del approved_tables, max_rows, conn, explain
        return SQLResult(
            columns=[{"name": "n", "type": "BIGINT"}],
            rows=[[1], [2]],
            row_count=2,
            truncated=False,
            duration_ms=3,
            executed_sql="SELECT 1",
            rewritten_sql="SELECT 1",
            referenced_tables=[],
        )

    monkeypatch.setattr(
        scheduler_module,  # but imports are inside the executor
        "_sleep",
        lambda _s: None,  # unused but silences lint
        raising=False,
    )
    from pointlessql.pql import pql as pql_module
    from pointlessql.pql import sql_parser as sql_parser_module

    monkeypatch.setattr(sql_parser_module, "prepare_sql", fake_prepare)
    monkeypatch.setattr(pql_module.PQL, "sql", staticmethod(fake_sql))

    # The scheduler executor calls ``get_session_factory`` — point it at
    # the test's app.state factory without going through init_db.
    from pointlessql import db as pql_db

    monkeypatch.setattr(pql_db, "get_session_factory", lambda: app.state.session_factory)

    # Force dispatcher to a no-op so no outbound HTTP traffic.
    async def fake_dispatch(*_a: Any, **_kw: Any) -> bool:
        return True

    from pointlessql.services import alert_dispatcher as dispatcher_mod

    monkeypatch.setattr(dispatcher_mod, "dispatch_webhook", fake_dispatch)

    # UC client isn't actually hit because prepared.refs is empty.
    uc_client = AsyncMock()
    await scheduler_module._alert_check_executor(
        job_run_id=0,
        user_info=UserInfo(
            id=0,
            email="test@test.com",
            display_name="test",
            is_admin=True,
            is_supervisor=False,
            is_auditor=False,
        ),
        config={"alert_id": alert_id},
        uc_client=uc_client,
    )
    events = alerts_service.list_events_for_alert(factory, alert_id, limit=10)
    assert len(events) == 1
    assert events[0]["outcome"] == "fired"
    payload = json.loads(events[0]["payload_json"])
    assert payload["specversion"] == "1.0"
    assert payload["type"] == "sql.pointlessql.alert.fired.v1"
    assert payload["data"]["row_count"] == 2
