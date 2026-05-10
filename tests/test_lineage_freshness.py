"""Tests for the Phase-40 lineage-freshness compute + admin CRUD.

Sprint 40.4 introduces ``expected_lineage_inbound`` registrations,
the ``compute_freshness`` helper that turns rows into per-pair
verdicts, and the ``/api/admin/expected-producers`` JSON CRUD
endpoints.
"""

from __future__ import annotations

import datetime as dt

import httpx
import pytest
from sqlalchemy import delete

from pointlessql.api.main import app
from pointlessql.models import ExpectedLineageInbound, LineageColumnMap
from pointlessql.services.lineage import freshness as fr


def _wipe() -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.execute(delete(ExpectedLineageInbound))
        session.execute(delete(LineageColumnMap).where(LineageColumnMap.producer.is_not(None)))
        session.commit()


@pytest.fixture(autouse=True)
def _wipe_around() -> None:
    _wipe()
    yield
    _wipe()


def _seed_expectation(
    *,
    target: str,
    producer: str,
    max_silence: int,
    is_active: bool = True,
    last_alerted_at: dt.datetime | None = None,
) -> int:
    factory = app.state.session_factory
    with factory() as session:
        row = ExpectedLineageInbound(
            workspace_id=1,
            target_table_full_name=target,
            producer=producer,
            max_silence_minutes=max_silence,
            is_active=is_active,
            last_alerted_at=last_alerted_at,
            created_at=dt.datetime(2026, 5, 1, tzinfo=dt.UTC),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def _seed_inbound_edge(
    *, target: str, producer: str, when: dt.datetime, source: str = "src.t"
) -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            LineageColumnMap(
                workspace_id=1,
                run_id=None,
                op_id=None,
                source_table=source,
                source_column="x",
                target_table=target,
                target_column="x",
                transform_kind="identity",
                producer=producer,
                external_event_id="evt",
                created_at=when,
            )
        )
        session.commit()


# ---------------------------------------------------------------------------
# compute_freshness
# ---------------------------------------------------------------------------


def test_freshness_never_seen_when_no_edge() -> None:
    _seed_expectation(target="main.silver.events", producer="kafka.x", max_silence=15)
    factory = app.state.session_factory
    with factory() as session:
        rows = fr.compute_freshness(
            session,
            workspace_id=1,
            now=dt.datetime(2026, 5, 6, 12, 0, tzinfo=dt.UTC),
        )
    assert len(rows) == 1
    assert rows[0]["status"] == fr.STATUS_NEVER_SEEN
    assert rows[0]["last_seen_at"] is None
    assert rows[0]["stale_minutes"] is None


def test_freshness_fresh_when_edge_recent() -> None:
    _seed_expectation(target="main.silver.events", producer="kafka.x", max_silence=15)
    _seed_inbound_edge(
        target="main.silver.events",
        producer="kafka.x",
        when=dt.datetime(2026, 5, 6, 11, 50, tzinfo=dt.UTC),  # 10 min ago
    )
    factory = app.state.session_factory
    with factory() as session:
        rows = fr.compute_freshness(
            session,
            workspace_id=1,
            now=dt.datetime(2026, 5, 6, 12, 0, tzinfo=dt.UTC),
        )
    assert rows[0]["status"] == fr.STATUS_FRESH
    assert rows[0]["stale_minutes"] is not None
    assert rows[0]["stale_minutes"] < 15


def test_freshness_stale_when_edge_too_old() -> None:
    _seed_expectation(target="main.silver.events", producer="kafka.x", max_silence=15)
    _seed_inbound_edge(
        target="main.silver.events",
        producer="kafka.x",
        when=dt.datetime(2026, 5, 6, 11, 30, tzinfo=dt.UTC),  # 30 min ago
    )
    factory = app.state.session_factory
    with factory() as session:
        rows = fr.compute_freshness(
            session,
            workspace_id=1,
            now=dt.datetime(2026, 5, 6, 12, 0, tzinfo=dt.UTC),
        )
    assert rows[0]["status"] == fr.STATUS_STALE
    assert rows[0]["stale_minutes"] is not None
    assert rows[0]["stale_minutes"] > 15


def test_freshness_inactive_skips_with_only_active() -> None:
    _seed_expectation(
        target="main.silver.events", producer="kafka.x", max_silence=15, is_active=False
    )
    factory = app.state.session_factory
    with factory() as session:
        rows = fr.compute_freshness(
            session,
            workspace_id=1,
            now=dt.datetime(2026, 5, 6, 12, 0, tzinfo=dt.UTC),
            only_active=True,
        )
    assert rows == []
    with factory() as session:
        rows = fr.compute_freshness(
            session,
            workspace_id=1,
            now=dt.datetime(2026, 5, 6, 12, 0, tzinfo=dt.UTC),
            only_active=False,
        )
    assert len(rows) == 1
    assert rows[0]["status"] == fr.STATUS_INACTIVE


def test_freshness_filters_by_target_table() -> None:
    _seed_expectation(target="main.silver.events", producer="kafka.x", max_silence=15)
    _seed_expectation(target="main.silver.other", producer="kafka.y", max_silence=15)
    factory = app.state.session_factory
    with factory() as session:
        rows = fr.compute_freshness(
            session,
            workspace_id=1,
            now=dt.datetime(2026, 5, 6, 12, 0, tzinfo=dt.UTC),
            target_table_full_name="main.silver.events",
        )
    assert len(rows) == 1
    assert rows[0]["target_table_full_name"] == "main.silver.events"


def test_freshness_orders_stale_before_fresh() -> None:
    _seed_expectation(target="main.silver.fresh", producer="p1", max_silence=15)
    _seed_expectation(target="main.silver.stale", producer="p2", max_silence=15)
    _seed_inbound_edge(
        target="main.silver.fresh",
        producer="p1",
        when=dt.datetime(2026, 5, 6, 11, 55, tzinfo=dt.UTC),
    )
    _seed_inbound_edge(
        target="main.silver.stale",
        producer="p2",
        when=dt.datetime(2026, 5, 6, 11, 0, tzinfo=dt.UTC),
    )
    factory = app.state.session_factory
    with factory() as session:
        rows = fr.compute_freshness(
            session,
            workspace_id=1,
            now=dt.datetime(2026, 5, 6, 12, 0, tzinfo=dt.UTC),
        )
    statuses = [r["status"] for r in rows]
    assert statuses == [fr.STATUS_STALE, fr.STATUS_FRESH]


# ---------------------------------------------------------------------------
# select_alert_candidates + stamp_alerted
# ---------------------------------------------------------------------------


def test_select_alert_candidates_skips_recently_alerted() -> None:
    now = dt.datetime(2026, 5, 6, 12, 0, tzinfo=dt.UTC)
    rows = [
        {
            "id": 1,
            "status": fr.STATUS_STALE,
            "max_silence_minutes": 15,
            "last_alerted_at": now - dt.timedelta(minutes=10),  # within cooldown
        },
        {
            "id": 2,
            "status": fr.STATUS_STALE,
            "max_silence_minutes": 15,
            "last_alerted_at": now - dt.timedelta(minutes=20),  # past cooldown
        },
        {
            "id": 3,
            "status": fr.STATUS_FRESH,
            "max_silence_minutes": 15,
            "last_alerted_at": None,
        },
    ]
    selected = fr.select_alert_candidates(rows, now=now)
    assert {r["id"] for r in selected} == {2}


def test_stamp_alerted_updates_last_alerted_at() -> None:
    expectation_id = _seed_expectation(
        target="main.silver.events", producer="kafka.x", max_silence=15
    )
    fired_at = dt.datetime(2026, 5, 6, 12, 0, tzinfo=dt.UTC)
    updated = fr.stamp_alerted(
        app.state.session_factory, expectation_ids=[expectation_id], fired_at=fired_at
    )
    assert updated == 1
    factory = app.state.session_factory
    with factory() as session:
        row = session.get(ExpectedLineageInbound, expectation_id)
        assert row is not None
        assert row.last_alerted_at is not None


# ---------------------------------------------------------------------------
# Admin CRUD routes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_register_then_list_expected_producer(admin_client: httpx.AsyncClient) -> None:
    create = await admin_client.post(
        "/api/admin/expected-producers",
        json={
            "target_table_full_name": "main.silver.events",
            "producer": "kafka.events.us-east",
            "max_silence_minutes": 15,
        },
    )
    assert create.status_code == 200, create.text
    row = create.json()
    assert row["target_table_full_name"] == "main.silver.events"
    assert row["producer"] == "kafka.events.us-east"
    assert row["max_silence_minutes"] == 15
    assert row["is_active"] is True

    listing = await admin_client.get("/api/admin/expected-producers")
    assert listing.status_code == 200
    rows = listing.json()["expectations"]
    assert len(rows) == 1
    assert rows[0]["producer"] == "kafka.events.us-east"


@pytest.mark.asyncio
async def test_admin_duplicate_expectation_rejected(admin_client: httpx.AsyncClient) -> None:
    first = await admin_client.post(
        "/api/admin/expected-producers",
        json={
            "target_table_full_name": "main.silver.events",
            "producer": "kafka.x",
            "max_silence_minutes": 15,
        },
    )
    assert first.status_code == 200
    dup = await admin_client.post(
        "/api/admin/expected-producers",
        json={
            "target_table_full_name": "main.silver.events",
            "producer": "kafka.x",
            "max_silence_minutes": 5,
        },
    )
    assert dup.status_code == 422


@pytest.mark.asyncio
async def test_admin_toggle_then_delete_expected_producer(admin_client: httpx.AsyncClient) -> None:
    create = await admin_client.post(
        "/api/admin/expected-producers",
        json={
            "target_table_full_name": "main.silver.events",
            "producer": "kafka.x",
            "max_silence_minutes": 15,
        },
    )
    expectation_id = create.json()["id"]
    toggle = await admin_client.post(f"/api/admin/expected-producers/{expectation_id}/toggle")
    assert toggle.status_code == 200
    assert toggle.json()["is_active"] is False
    delete_resp = await admin_client.delete(f"/api/admin/expected-producers/{expectation_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted"] is True


@pytest.mark.asyncio
async def test_admin_freshness_endpoint_returns_status_rows(
    admin_client: httpx.AsyncClient,
) -> None:
    _seed_expectation(target="main.silver.events", producer="kafka.x", max_silence=15)
    _seed_inbound_edge(
        target="main.silver.events",
        producer="kafka.x",
        when=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=5),
    )
    response = await admin_client.get("/api/admin/expected-producers/freshness")
    assert response.status_code == 200, response.text
    body = response.json()
    assert "now" in body
    assert len(body["rows"]) == 1
    assert body["rows"][0]["status"] == fr.STATUS_FRESH


@pytest.mark.asyncio
async def test_admin_create_validation_errors(admin_client: httpx.AsyncClient) -> None:
    missing = await admin_client.post(
        "/api/admin/expected-producers",
        json={"producer": "x", "max_silence_minutes": 1},
    )
    assert missing.status_code == 422
    zero_silence = await admin_client.post(
        "/api/admin/expected-producers",
        json={
            "target_table_full_name": "t",
            "producer": "p",
            "max_silence_minutes": 0,
        },
    )
    assert zero_silence.status_code == 422
