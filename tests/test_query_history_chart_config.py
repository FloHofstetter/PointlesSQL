"""Tests for the Sprint-54 chart_config persistence surface."""

from __future__ import annotations

import datetime
import json

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.services import query_history as qh


def _seed_history(*, user_id: int) -> int:
    """Insert a single history row and return its id."""
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    return qh.record_query(
        factory,
        user_id=user_id,
        user_email="test@test.com" if user_id == 1 else "nonadmin@test.com",
        sql_text="SELECT 1",
        started_at=now,
        finished_at=now,
        status="succeeded",
        row_count=1,
        duration_ms=4,
        referenced_tables=[],
    )


# -- service layer ------------------------------------------------------------


def test_update_chart_config_writes_and_reads_back() -> None:
    factory = app.state.session_factory
    history_id = _seed_history(user_id=1)
    payload = json.dumps(
        {"type": "bar", "x": "name", "y": "count"},
        separators=(",", ":"),
        sort_keys=True,
    )
    row = qh.update_chart_config(
        factory,
        history_id,
        user_id=1,
        is_admin=True,
        chart_config=payload,
    )
    assert row is not None
    assert row["chart_config"] == payload
    # Lookup again via get_by_id to prove the write survived the commit.
    again = qh.get_by_id(factory, history_id, user_id=1, is_admin=True)
    assert again is not None and again["chart_config"] == payload


def test_update_chart_config_clears_with_none() -> None:
    factory = app.state.session_factory
    history_id = _seed_history(user_id=1)
    qh.update_chart_config(
        factory,
        history_id,
        user_id=1,
        is_admin=True,
        chart_config='{"type":"bar","x":"a","y":"b"}',
    )
    qh.update_chart_config(
        factory,
        history_id,
        user_id=1,
        is_admin=True,
        chart_config=None,
    )
    row = qh.get_by_id(factory, history_id, user_id=1, is_admin=True)
    assert row is not None and row["chart_config"] is None


def test_update_chart_config_non_owner_refused() -> None:
    factory = app.state.session_factory
    history_id = _seed_history(user_id=1)
    # Non-admin stranger cannot mutate admin's row.
    result = qh.update_chart_config(
        factory,
        history_id,
        user_id=2,
        is_admin=False,
        chart_config='{"type":"bar","x":"a","y":"b"}',
    )
    assert result is None
    # And cannot read it back.
    assert qh.get_by_id(factory, history_id, user_id=2, is_admin=False) is None


# -- API route ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_chart_config_round_trip_for_owner(admin_client: httpx.AsyncClient) -> None:
    history_id = _seed_history(user_id=1)
    patch = await admin_client.patch(
        f"/api/queries/{history_id}/chart-config",
        json={"chart_config": {"type": "line", "x": "day", "y": "count"}},
    )
    assert patch.status_code == 200
    body = patch.json()
    # Server canonicalises with sorted keys + compact separators.
    assert body["chart_config"] == '{"type":"line","x":"day","y":"count"}'
    # GET by id returns the same payload.
    got = await admin_client.get(f"/api/queries/{history_id}")
    assert got.status_code == 200
    assert got.json()["chart_config"] == '{"type":"line","x":"day","y":"count"}'


@pytest.mark.asyncio
async def test_patch_chart_config_null_clears(admin_client: httpx.AsyncClient) -> None:
    history_id = _seed_history(user_id=1)
    await admin_client.patch(
        f"/api/queries/{history_id}/chart-config",
        json={"chart_config": {"type": "bar", "x": "a", "y": "b"}},
    )
    cleared = await admin_client.patch(
        f"/api/queries/{history_id}/chart-config",
        json={"chart_config": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["chart_config"] is None


@pytest.mark.asyncio
async def test_patch_chart_config_invalid_payload_is_400(admin_client: httpx.AsyncClient) -> None:
    history_id = _seed_history(user_id=1)
    res = await admin_client.patch(
        f"/api/queries/{history_id}/chart-config",
        json={"chart_config": "bar"},
    )
    # ValidationError is mapped to 422 by the central error handler.
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_get_and_patch_by_stranger_returns_404(non_admin_client: httpx.AsyncClient) -> None:
    # Admin (user_id=1) creates the row; non-admin (user_id=2) probes it.
    history_id = _seed_history(user_id=1)
    missing = await non_admin_client.get(f"/api/queries/{history_id}")
    assert missing.status_code == 404
    patch = await non_admin_client.patch(
        f"/api/queries/{history_id}/chart-config",
        json={"chart_config": {"type": "pie", "x": "a", "y": "b"}},
    )
    assert patch.status_code == 404
