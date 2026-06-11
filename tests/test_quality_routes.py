"""Quality routes: page rendering, monitor CRUD JSON surface, manual scans.

The quality router ships unregistered (the navigation integration
wires it into the bootstrap block later), so this module mounts it
onto the app for its own duration and removes the routes on teardown
— the session-global app stays pristine for other test modules, and
the fixture no-ops once the router is registered for real.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import deltalake
import httpx
import pandas as pd
import pytest
from sqlalchemy import select

from pointlessql.api import quality_routes
from pointlessql.api.main import app
from pointlessql.models import Base, Job
from pointlessql.models.quality_monitoring import QualityAnomaly, TableProfileSnapshot

_NOW = datetime.datetime(2026, 6, 1, tzinfo=datetime.UTC)


@pytest.fixture(autouse=True, scope="module")
def _mount_quality_router():
    mounted = {getattr(route, "path", None) for route in app.router.routes}
    if "/quality" in mounted:
        yield
        return
    before = len(app.router.routes)
    app.include_router(quality_routes.router)
    added = list(app.router.routes[before:])
    yield
    for route in added:
        app.router.routes.remove(route)


@pytest.fixture(autouse=True, scope="module")
def _quality_schema(_test_engine: tuple[Any, Any]):
    """Make sure the quality tables exist on the session-scope engine.

    ``create_all`` is idempotent, so this no-ops once the quality
    models are imported before the session-scope schema build.
    """
    engine, _ = _test_engine
    Base.metadata.create_all(engine)
    yield


async def _create_monitor(
    client: httpx.AsyncClient, target: str = "main.sales.orders"
) -> dict[str, Any]:
    res = await client.post(
        "/api/quality/monitors",
        json={"target": target, "cron_expr": "0 6 * * *"},
    )
    assert res.status_code == 200, res.text
    return res.json()


# ---------------------------------------------------------------------------
# HTML page
# ---------------------------------------------------------------------------


async def test_quality_page_renders_for_non_admin(non_admin_client: httpx.AsyncClient) -> None:
    """Any signed-in user reaches the cockpit; no admin gate on reads."""
    res = await non_admin_client.get("/quality")
    assert res.status_code == 200
    body = res.text
    assert 'data-pql-entry="quality.js' in body
    assert "Data Quality" in body
    # the monitors JSON carries double quotes, so the x-data attribute
    # MUST be single-quoted or Alpine sees a torn expression.
    assert "x-data='qualityMonitors(" in body
    assert "qualityMonitors([], false)" in body


async def test_quality_page_admin_flag(admin_client: httpx.AsyncClient) -> None:
    """Admins get the create form switched on through the seeded flag."""
    res = await admin_client.get("/quality")
    assert res.status_code == 200
    assert "qualityMonitors([], true)" in res.text


async def test_quality_page_redirects_anonymous(anonymous_client: httpx.AsyncClient) -> None:
    """Anonymous HTML traffic bounces to the login page."""
    res = await anonymous_client.get("/quality", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/auth/login"


# ---------------------------------------------------------------------------
# JSON CRUD
# ---------------------------------------------------------------------------


async def test_create_requires_admin(non_admin_client: httpx.AsyncClient) -> None:
    """Monitor creation is an operator concern."""
    res = await non_admin_client.post(
        "/api/quality/monitors",
        json={"target": "main.sales.orders", "cron_expr": "0 6 * * *"},
    )
    assert res.status_code == 403


async def test_create_and_list_monitor(
    admin_client: httpx.AsyncClient, non_admin_client: httpx.AsyncClient
) -> None:
    """Admins create; any signed-in user lists."""
    monitor = await _create_monitor(admin_client)
    assert monitor["target"] == "main.sales.orders"
    assert monitor["is_active"] is True
    assert monitor["backing_job_id"] is not None

    res = await non_admin_client.get("/api/quality/monitors")
    assert res.status_code == 200
    monitors = res.json()["monitors"]
    assert [m["id"] for m in monitors] == [monitor["id"]]
    assert monitors[0]["open_anomalies"] == 0


async def test_create_rejects_malformed_target(admin_client: httpx.AsyncClient) -> None:
    """Targets must be 2- or 3-part dotted names."""
    res = await admin_client.post(
        "/api/quality/monitors",
        json={"target": "not a name", "cron_expr": "0 6 * * *"},
    )
    assert res.status_code == 422


async def test_create_rejects_duplicate_target(admin_client: httpx.AsyncClient) -> None:
    """One monitor per target per workspace."""
    await _create_monitor(admin_client)
    res = await admin_client.post(
        "/api/quality/monitors",
        json={"target": "main.sales.orders", "cron_expr": "0 6 * * *"},
    )
    assert res.status_code == 422


async def test_patch_toggles_backing_job(admin_client: httpx.AsyncClient) -> None:
    """Pausing a monitor pauses its hidden scheduler job."""
    monitor = await _create_monitor(admin_client)
    res = await admin_client.patch(
        f"/api/quality/monitors/{monitor['id']}", json={"is_active": False}
    )
    assert res.status_code == 200
    assert res.json()["is_active"] is False

    factory = app.state.session_factory
    with factory() as session:
        job = session.get(Job, monitor["backing_job_id"])
        assert job is not None and job.is_paused is True


async def test_patch_requires_admin(
    admin_client: httpx.AsyncClient, non_admin_client: httpx.AsyncClient
) -> None:
    """Non-admins cannot mutate monitors."""
    monitor = await _create_monitor(admin_client)
    res = await non_admin_client.patch(
        f"/api/quality/monitors/{monitor['id']}", json={"is_active": False}
    )
    assert res.status_code == 403


async def test_get_monitor_detail_carries_snapshots_and_anomalies(
    admin_client: httpx.AsyncClient,
) -> None:
    """The detail payload inlines recent snapshots + the anomaly timeline."""
    monitor = await _create_monitor(admin_client)
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            TableProfileSnapshot(
                monitor_id=monitor["id"],
                table_fqn="main.sales.orders",
                delta_version=3,
                row_count=42,
                column_metrics='{"id": {"null_count": 0}}',
                captured_at=_NOW,
            )
        )
        session.add(
            QualityAnomaly(
                monitor_id=monitor["id"],
                table_fqn="main.sales.orders",
                column_name="id",
                kind="null_spike",
                severity="critical",
                observed="null fraction 0.80",
                expected="at most 0.20",
                detected_at=_NOW,
            )
        )
        session.commit()

    res = await admin_client.get(f"/api/quality/monitors/{monitor['id']}")
    assert res.status_code == 200
    body = res.json()
    assert body["open_anomalies"] == 1
    assert len(body["snapshots"]) == 1
    assert body["snapshots"][0]["row_count"] == 42
    assert body["snapshots"][0]["column_metrics"] == {"id": {"null_count": 0}}
    assert len(body["anomalies"]) == 1
    assert body["anomalies"][0]["kind"] == "null_spike"
    assert body["anomalies"][0]["resolved_at"] is None


async def test_get_missing_monitor_is_404(admin_client: httpx.AsyncClient) -> None:
    """Unknown ids answer a clean 404."""
    res = await admin_client.get("/api/quality/monitors/99999")
    assert res.status_code == 404


async def test_delete_monitor_removes_job(admin_client: httpx.AsyncClient) -> None:
    """Delete sweeps the monitor and its hidden scheduler job."""
    monitor = await _create_monitor(admin_client)
    res = await admin_client.delete(f"/api/quality/monitors/{monitor['id']}")
    assert res.status_code == 200
    assert res.json() == {"deleted": True}

    res = await admin_client.get(f"/api/quality/monitors/{monitor['id']}")
    assert res.status_code == 404
    factory = app.state.session_factory
    with factory() as session:
        assert session.get(Job, monitor["backing_job_id"]) is None


async def test_delete_requires_admin(
    admin_client: httpx.AsyncClient, non_admin_client: httpx.AsyncClient
) -> None:
    """Non-admins cannot delete monitors."""
    monitor = await _create_monitor(admin_client)
    res = await non_admin_client.delete(f"/api/quality/monitors/{monitor['id']}")
    assert res.status_code == 403


async def test_anomalies_status_filter(admin_client: httpx.AsyncClient) -> None:
    """The workspace anomaly feed filters on open / resolved."""
    monitor = await _create_monitor(admin_client)
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            QualityAnomaly(
                monitor_id=monitor["id"],
                table_fqn="main.sales.orders",
                kind="freshness",
                severity="warn",
                observed="o",
                expected="e",
                detected_at=_NOW,
            )
        )
        session.add(
            QualityAnomaly(
                monitor_id=monitor["id"],
                table_fqn="main.sales.orders",
                kind="schema_change",
                severity="warn",
                observed="o",
                expected="e",
                detected_at=_NOW,
                resolved_at=_NOW,
            )
        )
        session.commit()

    res = await admin_client.get("/api/quality/anomalies", params={"status": "open"})
    assert res.status_code == 200
    assert [a["kind"] for a in res.json()["anomalies"]] == ["freshness"]

    res = await admin_client.get("/api/quality/anomalies", params={"status": "resolved"})
    assert [a["kind"] for a in res.json()["anomalies"]] == ["schema_change"]

    res = await admin_client.get("/api/quality/anomalies")
    assert len(res.json()["anomalies"]) == 2


# ---------------------------------------------------------------------------
# manual run
# ---------------------------------------------------------------------------


async def test_run_now_requires_admin(
    admin_client: httpx.AsyncClient, non_admin_client: httpx.AsyncClient
) -> None:
    """The manual scan dispatches scheduler work — admin only."""
    monitor = await _create_monitor(admin_client)
    res = await non_admin_client.post(f"/api/quality/monitors/{monitor['id']}/run")
    assert res.status_code == 403


async def test_run_now_scans_target_table(
    admin_client: httpx.AsyncClient,
    uc_client_stub: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The manual run resolves the target through UC and stores a snapshot."""
    loc = str(tmp_path / "orders")
    deltalake.write_deltalake(loc, pd.DataFrame({"id": [1, 2, 3], "amount": [1.0, 2.0, 3.0]}))
    uc_client_stub.get_table = AsyncMock(
        return_value={
            "name": "orders",
            "catalog_name": "main",
            "schema_name": "sales",
            "storage_location": loc,
        }
    )

    # The scheduler executor calls ``get_session_factory`` — point it
    # at the test's app.state factory without going through init_db.
    from pointlessql import db as pql_db

    monkeypatch.setattr(pql_db, "get_session_factory", lambda: app.state.session_factory)

    monitor = await _create_monitor(admin_client)
    res = await admin_client.post(f"/api/quality/monitors/{monitor['id']}/run")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "succeeded", body
    assert body["error"] is None

    factory = app.state.session_factory
    with factory() as session:
        snapshot = session.scalars(
            select(TableProfileSnapshot).where(TableProfileSnapshot.monitor_id == monitor["id"])
        ).one()
        assert snapshot.row_count == 3
        assert snapshot.table_fqn == "main.sales.orders"
