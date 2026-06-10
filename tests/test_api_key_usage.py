"""Tests for the usage record + flush + retention path."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    ApiKey,
    ApiKeyCatalogGrant,
    ApiKeyIpGrant,
    ApiKeyUsageBucket,
)
from pointlessql.services import api_keys as api_keys_service
from pointlessql.services.api_keys._usage import (
    cleanup_stale_usage,
    flush_buffer,
    get_usage_summary,
    record_use,
)


def _wipe() -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.query(ApiKeyUsageBucket).delete()
        session.query(ApiKeyIpGrant).delete()
        session.query(ApiKeyCatalogGrant).delete()
        session.query(ApiKey).delete()
        session.commit()
    api_keys_service.invalidate_cache()
    # Reset the in-process buffer between tests.
    if hasattr(app.state, "api_key_usage_buffer"):
        delattr(app.state, "api_key_usage_buffer")


def test_record_use_buffers_under_app_state() -> None:
    _wipe()
    row, _ = api_keys_service.create_api_key(app.state.session_factory, name="rec")
    record_use(app.state, api_key_id=row.id, source_ip="127.0.0.1")
    record_use(app.state, api_key_id=row.id, source_ip="127.0.0.1")
    buffer: Counter[object] | None = getattr(app.state, "api_key_usage_buffer", None)
    assert buffer is not None
    assert len(buffer) == 1
    assert next(iter(buffer.values())) == 2
    _wipe()


def test_record_use_normalises_none_ip_to_empty_string() -> None:
    _wipe()
    row, _ = api_keys_service.create_api_key(app.state.session_factory, name="ipnone")
    record_use(app.state, api_key_id=row.id, source_ip=None)
    buffer: Counter[object] = app.state.api_key_usage_buffer
    key = next(iter(buffer.keys()))
    assert key[2] == ""  # source_ip slot
    _wipe()


def test_record_use_ignores_invalid_api_key_id() -> None:
    _wipe()
    record_use(app.state, api_key_id=0, source_ip="127.0.0.1")
    record_use(app.state, api_key_id=-3, source_ip="127.0.0.1")
    buffer = getattr(app.state, "api_key_usage_buffer", None)
    # Either the buffer wasn't created or it stayed empty.
    assert buffer is None or len(buffer) == 0
    _wipe()


def test_flush_buffer_writes_rows_and_clears_counter() -> None:
    _wipe()
    row, _ = api_keys_service.create_api_key(app.state.session_factory, name="flush1")
    for _ in range(7):
        record_use(app.state, api_key_id=row.id, source_ip="10.0.0.1")
    touched = flush_buffer(app.state.session_factory, app.state)
    assert touched == 1
    assert len(app.state.api_key_usage_buffer) == 0
    # Round-trip: the row count is 7.
    with app.state.session_factory() as session:
        bucket = session.query(ApiKeyUsageBucket).first()
        assert bucket is not None and bucket.count == 7
    _wipe()


def test_flush_buffer_increments_existing_bucket() -> None:
    """Two flushes against the same minute aggregate into one row."""
    _wipe()
    row, _ = api_keys_service.create_api_key(app.state.session_factory, name="flush2")
    for _ in range(3):
        record_use(app.state, api_key_id=row.id, source_ip="10.0.0.2")
    flush_buffer(app.state.session_factory, app.state)
    for _ in range(5):
        record_use(app.state, api_key_id=row.id, source_ip="10.0.0.2")
    flush_buffer(app.state.session_factory, app.state)
    with app.state.session_factory() as session:
        bucket = session.query(ApiKeyUsageBucket).first()
        assert bucket is not None and bucket.count == 8
    _wipe()


def test_flush_buffer_is_a_noop_when_empty() -> None:
    _wipe()
    assert flush_buffer(app.state.session_factory, app.state) == 0
    _wipe()


def test_cleanup_stale_usage_prunes_old_rows() -> None:
    _wipe()
    row, _ = api_keys_service.create_api_key(app.state.session_factory, name="prune")
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    with app.state.session_factory() as session:
        # 35 days ago: should be pruned at 30-day retention.
        session.add(
            ApiKeyUsageBucket(
                api_key_id=row.id,
                bucket_minute=now - timedelta(days=35),
                source_ip="1.1.1.1",
                count=5,
                last_seen_at=now - timedelta(days=35),
            )
        )
        # 5 days ago: keep.
        session.add(
            ApiKeyUsageBucket(
                api_key_id=row.id,
                bucket_minute=now - timedelta(days=5),
                source_ip="1.1.1.1",
                count=3,
                last_seen_at=now - timedelta(days=5),
            )
        )
        session.commit()
    deleted = cleanup_stale_usage(app.state.session_factory, retention_days=30)
    assert deleted == 1
    with app.state.session_factory() as session:
        assert session.query(ApiKeyUsageBucket).count() == 1
    _wipe()


def test_cleanup_stale_usage_noop_when_disabled() -> None:
    _wipe()
    row, _ = api_keys_service.create_api_key(app.state.session_factory, name="noprune")
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    with app.state.session_factory() as session:
        session.add(
            ApiKeyUsageBucket(
                api_key_id=row.id,
                bucket_minute=now - timedelta(days=10),
                source_ip="1.1.1.1",
                count=5,
                last_seen_at=now - timedelta(days=10),
            )
        )
        session.commit()
    assert cleanup_stale_usage(app.state.session_factory, retention_days=0) == 0
    _wipe()


def test_get_usage_summary_returns_zero_filled_days() -> None:
    _wipe()
    row, _ = api_keys_service.create_api_key(app.state.session_factory, name="sum")
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    with app.state.session_factory() as session:
        session.add(
            ApiKeyUsageBucket(
                api_key_id=row.id,
                bucket_minute=now,
                source_ip="10.0.0.1",
                count=42,
                last_seen_at=now,
            )
        )
        session.commit()
    summary = get_usage_summary(app.state.session_factory, api_key_id=row.id, days=7)
    assert len(summary["days"]) == 7
    today_iso = now.date().isoformat()
    today_entry = next(d for d in summary["days"] if d["date"] == today_iso)
    assert today_entry["count"] == 42
    # Earlier days are zero-filled.
    assert all(d["count"] == 0 for d in summary["days"] if d["date"] != today_iso)
    # Top IP is the only one.
    assert summary["top_ips"] == [{"ip": "10.0.0.1", "count": 42}]
    _wipe()


@pytest.mark.asyncio
async def test_usage_endpoint_returns_summary_via_admin_route(
    admin_client: httpx.AsyncClient,
) -> None:
    _wipe()
    create = await admin_client.post("/api/admin/api-keys", json={"name": "endpt"})
    key_name = create.json()["name"]
    factory = app.state.session_factory
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    with factory() as session:
        row = session.query(ApiKey).filter(ApiKey.name == key_name).first()
        assert row is not None
        session.add(
            ApiKeyUsageBucket(
                api_key_id=row.id,
                bucket_minute=now,
                source_ip="127.0.0.1",
                count=3,
                last_seen_at=now,
            )
        )
        session.commit()
    resp = await admin_client.get(f"/api/admin/api-keys/{key_name}/usage")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == key_name
    assert len(body["days"]) == 30
    assert body["top_ips"] == [{"ip": "127.0.0.1", "count": 3}]
    _wipe()


# ---------------------------------------------------------------------------
# Phase 164 — sparklines + WoW + anomaly heuristic
# ---------------------------------------------------------------------------


def test_usage_summary_response_carries_stats_and_wow() -> None:
    """get_usage_summary returns the new wow + stats envelopes."""
    _wipe()
    row, _ = api_keys_service.create_api_key(app.state.session_factory, name="phase164-shape")
    factory = app.state.session_factory
    summary = get_usage_summary(factory, api_key_id=row.id, days=30)
    assert "wow" in summary
    assert set(summary["wow"]) == {"last_7d", "prev_7d", "change_pct"}
    assert "stats" in summary
    assert set(summary["stats"]) == {"mean_7d", "std_7d"}
    assert all("is_anomaly" in day for day in summary["days"])
    _wipe()


def test_usage_summary_wow_calculates_change_pct() -> None:
    _wipe()
    row, _ = api_keys_service.create_api_key(app.state.session_factory, name="phase164-wow")
    factory = app.state.session_factory
    now = datetime.now(UTC).replace(microsecond=0, second=0)
    today = now.date()
    with factory() as session:
        # 100 hits/day for the last 7 days; 50 hits/day for the prior 7.
        for offset in range(7):
            day = today - timedelta(days=offset)
            session.add(
                ApiKeyUsageBucket(
                    api_key_id=row.id,
                    bucket_minute=datetime.combine(day, datetime.min.time(), tzinfo=UTC),
                    source_ip="1.1.1.1",
                    count=100,
                    last_seen_at=now,
                )
            )
        for offset in range(7, 14):
            day = today - timedelta(days=offset)
            session.add(
                ApiKeyUsageBucket(
                    api_key_id=row.id,
                    bucket_minute=datetime.combine(day, datetime.min.time(), tzinfo=UTC),
                    source_ip="1.1.1.1",
                    count=50,
                    last_seen_at=now,
                )
            )
        session.commit()
    summary = get_usage_summary(factory, api_key_id=row.id, days=30)
    assert summary["wow"]["last_7d"] == 7 * 100
    assert summary["wow"]["prev_7d"] == 7 * 50
    assert summary["wow"]["change_pct"] == 100.0
    _wipe()


def test_usage_summary_wow_change_pct_none_when_prev_zero() -> None:
    _wipe()
    row, _ = api_keys_service.create_api_key(app.state.session_factory, name="phase164-no-prev")
    factory = app.state.session_factory
    now = datetime.now(UTC).replace(microsecond=0, second=0)
    today = now.date()
    with factory() as session:
        session.add(
            ApiKeyUsageBucket(
                api_key_id=row.id,
                bucket_minute=datetime.combine(today, datetime.min.time(), tzinfo=UTC),
                source_ip="2.2.2.2",
                count=42,
                last_seen_at=now,
            )
        )
        session.commit()
    summary = get_usage_summary(factory, api_key_id=row.id, days=30)
    assert summary["wow"]["last_7d"] >= 42
    assert summary["wow"]["prev_7d"] == 0
    assert summary["wow"]["change_pct"] is None
    _wipe()


def test_usage_summary_anomaly_flag_for_3sigma_spike() -> None:
    """A day count > 3σ from the prior 7-day mean is flagged is_anomaly."""
    _wipe()
    row, _ = api_keys_service.create_api_key(app.state.session_factory, name="phase164-spike")
    factory = app.state.session_factory
    now = datetime.now(UTC).replace(microsecond=0, second=0)
    today = now.date()
    with factory() as session:
        # Quiet baseline: 10 / day for 7 days before today.
        for offset in range(1, 8):
            day = today - timedelta(days=offset)
            session.add(
                ApiKeyUsageBucket(
                    api_key_id=row.id,
                    bucket_minute=datetime.combine(day, datetime.min.time(), tzinfo=UTC),
                    source_ip="3.3.3.3",
                    count=10,
                    last_seen_at=now,
                )
            )
        # Today: 10000 hits — way beyond 3σ.
        session.add(
            ApiKeyUsageBucket(
                api_key_id=row.id,
                bucket_minute=datetime.combine(today, datetime.min.time(), tzinfo=UTC),
                source_ip="3.3.3.3",
                count=10000,
                last_seen_at=now,
            )
        )
        session.commit()
    summary = get_usage_summary(factory, api_key_id=row.id, days=30)
    today_iso = today.isoformat()
    today_entry = next(d for d in summary["days"] if d["date"] == today_iso)
    assert today_entry["is_anomaly"] is True
    _wipe()


def test_usage_summary_zero_std_no_anomaly() -> None:
    """Constant traffic should never flag as anomaly (std = 0)."""
    _wipe()
    row, _ = api_keys_service.create_api_key(app.state.session_factory, name="phase164-const")
    factory = app.state.session_factory
    now = datetime.now(UTC).replace(microsecond=0, second=0)
    today = now.date()
    with factory() as session:
        # 50 hits/day across the whole 30-day window.
        for offset in range(30):
            day = today - timedelta(days=offset)
            session.add(
                ApiKeyUsageBucket(
                    api_key_id=row.id,
                    bucket_minute=datetime.combine(day, datetime.min.time(), tzinfo=UTC),
                    source_ip="4.4.4.4",
                    count=50,
                    last_seen_at=now,
                )
            )
        session.commit()
    summary = get_usage_summary(factory, api_key_id=row.id, days=30)
    assert not any(d["is_anomaly"] for d in summary["days"])
    _wipe()
