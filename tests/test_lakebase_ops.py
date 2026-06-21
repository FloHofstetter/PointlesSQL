"""Tests for the Lakebase autonomous-ops health + recommendation engine."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

import httpx
import pytest

from pointlessql.api.main import app as fastapi_app
from pointlessql.models import Workspace
from pointlessql.models.synced_tables import SyncedTable
from pointlessql.services import lakebase_ops

_NOW = datetime.datetime(2026, 6, 1, 12, 0, tzinfo=datetime.UTC)


def _mk(**kw: Any) -> SyncedTable:
    defaults: dict[str, Any] = {
        "name": "t",
        "source_fqn": "c.s.t",
        "target_url": "sqlite://",
        "target_table": "t",
        "mode": "full",
        "status": "ok",
        "primary_keys": None,
        "last_synced_at": _NOW,
        "last_error": None,
    }
    defaults.update(kw)
    return SyncedTable(**defaults)


def test_failed_is_critical() -> None:
    a = lakebase_ops.assess_synced_table(_mk(status="failed", last_error="boom"), now=_NOW)
    assert a["health"] == "critical"
    assert any(r["action"] == "investigate_failure" for r in a["recommendations"])


def test_ok_recent_is_healthy() -> None:
    a = lakebase_ops.assess_synced_table(_mk(status="ok", last_synced_at=_NOW), now=_NOW)
    assert a["health"] == "healthy"


def test_stale_ok_is_degraded() -> None:
    old = _NOW - datetime.timedelta(hours=2)
    a = lakebase_ops.assess_synced_table(
        _mk(status="ok", last_synced_at=old), now=_NOW, stale_after_minutes=60
    )
    assert a["health"] == "degraded"
    assert any(r["action"] == "resync" for r in a["recommendations"])


def test_never_synced_idle_is_degraded() -> None:
    a = lakebase_ops.assess_synced_table(_mk(status="idle", last_synced_at=None), now=_NOW)
    assert a["health"] == "degraded"
    assert any(r["action"] == "initial_sync" for r in a["recommendations"])


def test_cdf_without_primary_keys_recommends_keys() -> None:
    a = lakebase_ops.assess_synced_table(
        _mk(status="ok", mode="cdf", primary_keys=None, last_synced_at=_NOW), now=_NOW
    )
    assert a["health"] == "degraded"
    assert any(r["action"] == "set_primary_keys" for r in a["recommendations"])


def test_serving_index_advisory_is_info_only() -> None:
    a = lakebase_ops.assess_synced_table(
        _mk(status="ok", primary_keys="id, region", last_synced_at=_NOW), now=_NOW
    )
    index_recs = [r for r in a["recommendations"] if r["action"] == "add_serving_index"]
    assert index_recs and index_recs[0]["severity"] == "info"
    # An info-only recommendation must not degrade the health verdict.
    assert a["health"] == "healthy"


def test_syncing_state() -> None:
    a = lakebase_ops.assess_synced_table(_mk(status="syncing"), now=_NOW)
    assert a["health"] == "syncing"


# --- overview + route -------------------------------------------------


def _factory():
    return fastapi_app.state.session_factory


def _fresh_workspace() -> int:
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        ws = Workspace(slug=f"lb-{uuid.uuid4().hex[:10]}", name="Lakebase ops test", created_at=now)
        session.add(ws)
        session.commit()
        session.refresh(ws)
        return int(ws.id)


def _seed(ws: int, **kw: Any) -> None:
    now = datetime.datetime.now(datetime.UTC)
    defaults: dict[str, Any] = {
        "workspace_id": ws,
        "name": f"st-{uuid.uuid4().hex[:8]}",
        "source_fqn": "main.s.t",
        "target_url": "sqlite://",
        "target_table": "t",
        "mode": "full",
        "status": "ok",
        "last_synced_at": now,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(kw)
    with _factory()() as session:
        session.add(SyncedTable(**defaults))
        session.commit()


def test_ops_overview_summarizes_and_sorts() -> None:
    ws = _fresh_workspace()
    now = datetime.datetime.now(datetime.UTC)
    _seed(ws, name="healthy-one", status="ok", last_synced_at=now)
    _seed(ws, name="broken-one", status="failed", last_error="boom")

    ov = lakebase_ops.ops_overview(_factory(), workspace_id=ws, now=now)

    assert ov["total"] == 2
    assert ov["summary"]["critical"] == 1
    assert ov["summary"]["healthy"] == 1
    assert ov["open_recommendations"] >= 1
    # Worst health sorts first.
    assert ov["tables"][0]["health"] == "critical"


@pytest.mark.asyncio
async def test_route_ops(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.get("/api/online-tables/ops")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert {"tables", "summary", "total", "open_recommendations"} <= set(data)
