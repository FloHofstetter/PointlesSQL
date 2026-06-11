"""BI snapshots: schedule CRUD + backing job, capture, executor, routes."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import deltalake
import httpx
import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from pointlessql.api import bi_snapshot_routes
from pointlessql.api.main import app
from pointlessql.exceptions import ValidationError
from pointlessql.models import Base, Job, JobLog, JobRun, User, UserNotification
from pointlessql.models.bi_dashboards import BiDashboard
from pointlessql.models.bi_schedules import BiDashboardSchedule, BiDashboardSnapshot
from pointlessql.services import bi_dashboards as bi_service
from pointlessql.services import bi_snapshots as snapshot_service
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo

_NOW = datetime.datetime(2026, 6, 1, tzinfo=datetime.UTC)


# ---------------------------------------------------------------------------
# Shared fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True, scope="module")
def _mount_snapshot_router():  # pyright: ignore[reportUnusedFunction]
    """Mount the (bootstrap-unregistered) router for this module only."""
    mounted = {getattr(route, "path", None) for route in app.router.routes}
    if "/api/bi/dashboards/{slug}/schedule" in mounted:
        yield
        return
    before = len(app.router.routes)
    app.include_router(bi_snapshot_routes.router)
    added = list(app.router.routes[before:])
    yield
    for route in added:
        app.router.routes.remove(route)


@pytest.fixture(autouse=True, scope="module")
def _create_bi_schedule_tables(_test_engine: tuple[Any, Any]):  # pyright: ignore[reportUnusedFunction]
    """Ensure the (not-yet-wired) schedule/snapshot tables exist app-side.

    The models module is not imported by ``pointlessql.models`` yet,
    so the session-scoped ``create_all`` may have run before these
    tables joined ``Base.metadata``; ``checkfirst`` makes the repair
    idempotent.
    """
    engine, _ = _test_engine
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def factory() -> Any:
    """In-memory session factory seeded with one dashboard owner."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        session.add(
            User(
                email="owner@test.com",
                display_name="Owner",
                password_hash="x",
                is_admin=False,
                created_at=_NOW,
            )
        )
        session.commit()
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def orders_delta(tmp_path: Path) -> str:
    """Create a tiny Delta table at ``tmp_path/orders`` and return its path."""
    loc = str(tmp_path / "orders")
    df = pd.DataFrame({"id": [1, 2, 3], "amount": [10.0, 20.0, 30.0]})
    deltalake.write_deltalake(loc, df)
    return loc


def _make_uc_mock(storage_location: str) -> MagicMock:
    client = MagicMock(spec=UnityCatalogClient)
    client.get_table = AsyncMock(
        return_value={
            "name": "orders",
            "catalog_name": "main",
            "schema_name": "sales",
            "storage_location": storage_location,
            "owner": "someone-else@test.com",
            "properties": {},
        }
    )
    client.get_effective_permissions = AsyncMock(return_value=[])
    return client


def _owner_id(factory: Any) -> int:
    with factory() as session:
        user = session.scalars(select(User)).first()
        assert user is not None
        return int(user.id)


def _make_dashboard(
    factory: Any, *, owner_id: int, params: list[dict[str, Any]] | None = None
) -> BiDashboard:
    row = bi_service.create_dashboard(
        factory, workspace_id=1, title="Sales KPIs", description=None, owner_id=owner_id
    )
    if params is not None:
        updated = bi_service.update_dashboard(factory, dashboard_id=row.id, params=params)
        assert updated is not None
        return updated
    return row


def _add_counter(factory: Any, dashboard_id: int, sql: str) -> None:
    bi_service.add_widget(
        factory,
        dashboard_id=dashboard_id,
        kind="counter",
        title="Count",
        sql_text=sql,
        saved_query_id=None,
        markdown=None,
        chart_spec=None,
        position=None,
    )


def _user_info(*, email: str = "owner@test.com", is_admin: bool = True) -> UserInfo:
    return cast(
        "UserInfo",
        {
            "id": 1,
            "email": email,
            "display_name": "Owner",
            "is_admin": is_admin,
            "is_supervisor": False,
            "is_auditor": False,
        },
    )


# ---------------------------------------------------------------------------
# Schedule CRUD + backing-job sync
# ---------------------------------------------------------------------------


def test_upsert_schedule_creates_backing_job(factory: Any) -> None:
    """First upsert materialises the hidden bi_snapshot job."""
    owner = _owner_id(factory)
    dash = _make_dashboard(factory, owner_id=owner)
    row = snapshot_service.upsert_schedule(
        factory,
        dashboard_id=dash.id,
        workspace_id=1,
        created_by_user_id=owner,
        cron_expr="0 8 * * *",
    )
    assert row.backing_job_id is not None
    with factory() as session:
        job = session.get(Job, row.backing_job_id)
        assert job is not None
        assert job.kind == "bi_snapshot"
        assert json.loads(job.config) == {"schedule_id": row.id}
        assert job.cron_expr == "0 8 * * *"
        assert job.run_as_user_id == owner
        assert job.is_paused is False
        assert job.name == f"bi_snapshot:{dash.slug}"


def test_upsert_schedule_syncs_cron_and_pause(factory: Any) -> None:
    """Re-upsert keeps one row and maps is_active onto Job.is_paused."""
    owner = _owner_id(factory)
    dash = _make_dashboard(factory, owner_id=owner)
    first = snapshot_service.upsert_schedule(
        factory,
        dashboard_id=dash.id,
        workspace_id=1,
        created_by_user_id=owner,
        cron_expr="0 8 * * *",
    )
    second = snapshot_service.upsert_schedule(
        factory,
        dashboard_id=dash.id,
        workspace_id=1,
        created_by_user_id=owner,
        cron_expr="*/5 * * * *",
        is_active=False,
    )
    assert second.id == first.id
    assert second.backing_job_id == first.backing_job_id
    with factory() as session:
        assert len(list(session.scalars(select(BiDashboardSchedule)))) == 1
        job = session.get(Job, second.backing_job_id)
        assert job is not None
        assert job.cron_expr == "*/5 * * * *"
        assert job.is_paused is True
    third = snapshot_service.upsert_schedule(
        factory,
        dashboard_id=dash.id,
        workspace_id=1,
        created_by_user_id=owner,
        cron_expr="*/5 * * * *",
        is_active=True,
    )
    with factory() as session:
        job = session.get(Job, third.backing_job_id)
        assert job is not None
        assert job.is_paused is False


def test_upsert_schedule_rejects_bad_cron(factory: Any) -> None:
    """An unparseable cron expression is a ValidationError."""
    owner = _owner_id(factory)
    dash = _make_dashboard(factory, owner_id=owner)
    with pytest.raises(ValidationError):
        snapshot_service.upsert_schedule(
            factory,
            dashboard_id=dash.id,
            workspace_id=1,
            created_by_user_id=owner,
            cron_expr="not a cron",
        )


def test_upsert_schedule_keeps_hmac_when_unset(factory: Any) -> None:
    """Omitting the secret keeps it; passing None clears it."""
    owner = _owner_id(factory)
    dash = _make_dashboard(factory, owner_id=owner)
    snapshot_service.upsert_schedule(
        factory,
        dashboard_id=dash.id,
        workspace_id=1,
        created_by_user_id=owner,
        cron_expr="0 8 * * *",
        webhook_url="https://example.com/hook",
        webhook_hmac_secret="s3cret",
    )
    kept = snapshot_service.upsert_schedule(
        factory,
        dashboard_id=dash.id,
        workspace_id=1,
        created_by_user_id=owner,
        cron_expr="0 9 * * *",
        webhook_url="https://example.com/hook",
    )
    assert kept.webhook_hmac_secret == "s3cret"
    cleared = snapshot_service.upsert_schedule(
        factory,
        dashboard_id=dash.id,
        workspace_id=1,
        created_by_user_id=owner,
        cron_expr="0 9 * * *",
        webhook_url="https://example.com/hook",
        webhook_hmac_secret=None,
    )
    assert cleared.webhook_hmac_secret is None


def test_delete_schedule_removes_job_and_children(factory: Any) -> None:
    """Delete drops the schedule, its Job, and the job's runs + logs."""
    owner = _owner_id(factory)
    dash = _make_dashboard(factory, owner_id=owner)
    row = snapshot_service.upsert_schedule(
        factory,
        dashboard_id=dash.id,
        workspace_id=1,
        created_by_user_id=owner,
        cron_expr="0 8 * * *",
    )
    backing_id = row.backing_job_id
    assert backing_id is not None
    with factory() as session:
        run = JobRun(
            workspace_id=1,
            job_id=backing_id,
            started_at=_NOW,
            finished_at=_NOW,
            status="succeeded",
            trigger="scheduled",
        )
        session.add(run)
        session.flush()
        session.add(JobLog(workspace_id=1, job_run_id=run.id, ts=_NOW, level="INFO", message="ran"))
        session.commit()
    assert snapshot_service.delete_schedule(factory, dashboard_id=dash.id) is True
    with factory() as session:
        assert session.scalars(select(BiDashboardSchedule)).first() is None
        assert session.get(Job, backing_id) is None
        assert session.scalars(select(JobRun)).first() is None
        assert session.scalars(select(JobLog)).first() is None
    assert snapshot_service.delete_schedule(factory, dashboard_id=dash.id) is False


# ---------------------------------------------------------------------------
# render_snapshot
# ---------------------------------------------------------------------------


async def test_render_snapshot_captures_widgets(factory: Any, orders_delta: str) -> None:
    """Counter / table / markdown all land in one frozen payload."""
    owner = _owner_id(factory)
    dash = _make_dashboard(factory, owner_id=owner)
    _add_counter(factory, dash.id, "SELECT COUNT(*) AS n FROM main.sales.orders")
    bi_service.add_widget(
        factory,
        dashboard_id=dash.id,
        kind="table",
        title="Orders",
        sql_text="SELECT id, amount FROM main.sales.orders ORDER BY id",
        saved_query_id=None,
        markdown=None,
        chart_spec=None,
        position=None,
    )
    bi_service.add_widget(
        factory,
        dashboard_id=dash.id,
        kind="markdown",
        title=None,
        sql_text=None,
        saved_query_id=None,
        markdown="## Notes",
        chart_spec=None,
        position=None,
    )
    snapshot_id = await snapshot_service.render_snapshot(
        factory,
        uc_client=_make_uc_mock(orders_delta),
        dashboard_id=dash.id,
        workspace_id=1,
        actor_email="owner@test.com",
        is_admin=True,
        triggered_by="manual",
    )
    snap = snapshot_service.get_snapshot(factory, dashboard_id=dash.id, snapshot_id=snapshot_id)
    assert snap is not None
    assert snap.triggered_by == "manual"
    payload = json.loads(snap.payload)
    assert payload["title"] == "Sales KPIs"
    entries = payload["widgets"]
    assert len(entries) == 3
    counter, table, markdown = entries
    assert counter["error"] is None
    assert counter["rows"] == [[3]]
    assert counter["row_count"] == 1
    assert table["rows"] == [[1, 10.0], [2, 20.0], [3, 30.0]]
    assert table["truncated"] is False
    assert markdown["kind"] == "markdown"
    assert markdown["markdown"] == "## Notes"
    assert markdown["rows"] is None


async def test_render_snapshot_substitutes_param_defaults(factory: Any, orders_delta: str) -> None:
    """``{{param}}`` placeholders resolve from the dashboard defaults."""
    owner = _owner_id(factory)
    dash = _make_dashboard(
        factory,
        owner_id=owner,
        params=[{"name": "min_id", "type": "number", "default": 2}],
    )
    _add_counter(
        factory, dash.id, "SELECT COUNT(*) AS n FROM main.sales.orders WHERE id >= {{min_id}}"
    )
    snapshot_id = await snapshot_service.render_snapshot(
        factory,
        uc_client=_make_uc_mock(orders_delta),
        dashboard_id=dash.id,
        workspace_id=1,
        actor_email="owner@test.com",
        is_admin=True,
        triggered_by="manual",
    )
    snap = snapshot_service.get_snapshot(factory, dashboard_id=dash.id, snapshot_id=snapshot_id)
    assert snap is not None
    entry = json.loads(snap.payload)["widgets"][0]
    assert entry["error"] is None
    assert entry["rows"] == [[2]]


async def test_render_snapshot_isolates_widget_errors(factory: Any, orders_delta: str) -> None:
    """One broken widget records an error; the others still capture."""
    owner = _owner_id(factory)
    dash = _make_dashboard(factory, owner_id=owner)
    _add_counter(factory, dash.id, "THIS IS NOT SQL AT ALL")
    _add_counter(factory, dash.id, "SELECT COUNT(*) AS n FROM main.sales.orders")
    snapshot_id = await snapshot_service.render_snapshot(
        factory,
        uc_client=_make_uc_mock(orders_delta),
        dashboard_id=dash.id,
        workspace_id=1,
        actor_email="owner@test.com",
        is_admin=True,
        triggered_by="manual",
    )
    snap = snapshot_service.get_snapshot(factory, dashboard_id=dash.id, snapshot_id=snapshot_id)
    assert snap is not None
    broken, good = json.loads(snap.payload)["widgets"]
    assert broken["error"]
    assert broken["rows"] is None
    assert good["error"] is None
    assert good["rows"] == [[3]]


# ---------------------------------------------------------------------------
# bi_snapshot_executor
# ---------------------------------------------------------------------------


async def test_executor_captures_and_notifies(
    factory: Any, orders_delta: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A scheduled run snapshots, stamps last_run_at, and fans out in-app."""
    owner = _owner_id(factory)
    dash = _make_dashboard(factory, owner_id=owner)
    _add_counter(factory, dash.id, "SELECT COUNT(*) AS n FROM main.sales.orders")
    schedule = snapshot_service.upsert_schedule(
        factory,
        dashboard_id=dash.id,
        workspace_id=1,
        created_by_user_id=owner,
        cron_expr="0 8 * * *",
    )
    monkeypatch.setattr("pointlessql.db.get_session_factory", lambda: factory)
    await snapshot_service.bi_snapshot_executor(
        1, _user_info(), {"schedule_id": schedule.id}, _make_uc_mock(orders_delta)
    )
    with factory() as session:
        snap = session.scalars(select(BiDashboardSnapshot)).first()
        assert snap is not None
        assert snap.triggered_by == "schedule"
        refreshed = session.get(BiDashboardSchedule, schedule.id)
        assert refreshed is not None
        assert refreshed.last_run_at is not None
        note = session.scalars(select(UserNotification)).first()
        assert note is not None
        assert note.recipient_user_id == owner
        assert note.event_type == "pointlessql.bi.snapshot_created"
        assert note.source_entity_ref == dash.slug
        assert f"/bi/{dash.slug}/snapshots/{snap.id}" == note.source_url


async def test_executor_dispatches_signed_webhook(
    factory: Any, orders_delta: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A configured webhook receives the CloudEvents envelope."""
    owner = _owner_id(factory)
    dash = _make_dashboard(factory, owner_id=owner)
    _add_counter(factory, dash.id, "SELECT COUNT(*) AS n FROM main.sales.orders")
    schedule = snapshot_service.upsert_schedule(
        factory,
        dashboard_id=dash.id,
        workspace_id=1,
        created_by_user_id=owner,
        cron_expr="0 8 * * *",
        deliver_inapp=False,
        webhook_url="https://example.com/hook",
        webhook_hmac_secret="s3cret",
    )
    calls: dict[str, Any] = {}

    async def fake_dispatch(
        url: str, envelope: dict[str, Any], *, hmac_secret: str | None = None
    ) -> bool:
        calls["url"] = url
        calls["envelope"] = envelope
        calls["secret"] = hmac_secret
        return True

    monkeypatch.setattr(snapshot_service, "dispatch_webhook", fake_dispatch)
    monkeypatch.setattr("pointlessql.db.get_session_factory", lambda: factory)
    await snapshot_service.bi_snapshot_executor(
        1, _user_info(), {"schedule_id": schedule.id}, _make_uc_mock(orders_delta)
    )
    assert calls["url"] == "https://example.com/hook"
    assert calls["secret"] == "s3cret"
    envelope = calls["envelope"]
    assert envelope["type"] == "sql.pointlessql.bi.snapshot.v1"
    assert envelope["subject"] == dash.slug
    assert envelope["data"]["widget_count"] == 1
    with factory() as session:
        assert session.scalars(select(UserNotification)).first() is None


async def test_executor_skips_inactive_schedule(
    factory: Any, orders_delta: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A paused schedule produces neither snapshot nor notification."""
    owner = _owner_id(factory)
    dash = _make_dashboard(factory, owner_id=owner)
    schedule = snapshot_service.upsert_schedule(
        factory,
        dashboard_id=dash.id,
        workspace_id=1,
        created_by_user_id=owner,
        cron_expr="0 8 * * *",
        is_active=False,
    )
    monkeypatch.setattr("pointlessql.db.get_session_factory", lambda: factory)
    await snapshot_service.bi_snapshot_executor(
        1, _user_info(), {"schedule_id": schedule.id}, _make_uc_mock(orders_delta)
    )
    with factory() as session:
        assert session.scalars(select(BiDashboardSnapshot)).first() is None


async def test_executor_requires_schedule_id() -> None:
    """A config without an integer schedule_id is a ValidationError."""
    with pytest.raises(ValidationError):
        await snapshot_service.bi_snapshot_executor(1, _user_info(), {}, MagicMock())


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _app_admin_id() -> int:
    factory = app.state.session_factory
    with factory() as session:
        row = session.scalar(select(User).where(User.email == "test@test.com"))
        assert row is not None
        return int(row.id)


def _app_dashboard(*, counter_sql: str | None = None) -> BiDashboard:
    factory = app.state.session_factory
    dash = bi_service.create_dashboard(
        factory, workspace_id=1, title="Route Dash", description=None, owner_id=_app_admin_id()
    )
    if counter_sql:
        _add_counter(factory, dash.id, counter_sql)
    return dash


async def test_schedule_route_roundtrip(admin_client: httpx.AsyncClient) -> None:
    """GET (empty) → PUT → GET → DELETE → 404 on the second DELETE."""
    dash = _app_dashboard()
    res = await admin_client.get(f"/api/bi/dashboards/{dash.slug}/schedule")
    assert res.status_code == 200
    assert res.json()["schedule"] is None

    res = await admin_client.put(
        f"/api/bi/dashboards/{dash.slug}/schedule",
        json={"cron_expr": "0 8 * * *", "webhook_url": "https://example.com/h"},
    )
    assert res.status_code == 200, res.text
    body = res.json()["schedule"]
    assert body["cron_expr"] == "0 8 * * *"
    assert body["webhook_url"] == "https://example.com/h"
    assert body["is_active"] is True
    assert body["backing_job_id"] is not None

    res = await admin_client.get(f"/api/bi/dashboards/{dash.slug}/schedule")
    assert res.json()["schedule"]["id"] == body["id"]

    res = await admin_client.delete(f"/api/bi/dashboards/{dash.slug}/schedule")
    assert res.status_code == 200
    assert res.json() == {"deleted": True}

    res = await admin_client.delete(f"/api/bi/dashboards/{dash.slug}/schedule")
    assert res.status_code == 404


async def test_schedule_route_rejects_bad_cron(admin_client: httpx.AsyncClient) -> None:
    """An invalid cron expression answers 422 (ValidationError)."""
    dash = _app_dashboard()
    res = await admin_client.put(
        f"/api/bi/dashboards/{dash.slug}/schedule", json={"cron_expr": "nope"}
    )
    assert res.status_code == 422


async def test_schedule_route_forbidden_for_non_owner(
    non_admin_client: httpx.AsyncClient,
) -> None:
    """A non-owner, non-admin viewer cannot touch the schedule."""
    dash = _app_dashboard()
    res = await non_admin_client.put(
        f"/api/bi/dashboards/{dash.slug}/schedule", json={"cron_expr": "0 8 * * *"}
    )
    assert res.status_code == 403
    res = await non_admin_client.get(f"/api/bi/dashboards/{dash.slug}/snapshots")
    assert res.status_code == 403


async def test_manual_snapshot_route_and_page(
    admin_client: httpx.AsyncClient, orders_delta: str
) -> None:
    """POST captures; list/detail/HTML replay the frozen payload."""
    app.state.uc_client = _make_uc_mock(orders_delta)
    dash = _app_dashboard(counter_sql="SELECT COUNT(*) AS n FROM main.sales.orders")

    res = await admin_client.post(f"/api/bi/dashboards/{dash.slug}/snapshots")
    assert res.status_code == 200, res.text
    snapshot_id = res.json()["id"]
    assert res.json()["url"] == f"/bi/{dash.slug}/snapshots/{snapshot_id}"

    res = await admin_client.get(f"/api/bi/dashboards/{dash.slug}/snapshots")
    assert res.status_code == 200
    items = res.json()["snapshots"]
    assert len(items) == 1
    assert items[0]["id"] == snapshot_id
    assert items[0]["triggered_by"] == "manual"
    assert items[0]["widget_count"] == 1

    res = await admin_client.get(f"/api/bi/dashboards/{dash.slug}/snapshots/{snapshot_id}")
    assert res.status_code == 200
    payload = res.json()["payload"]
    assert payload["widgets"][0]["rows"] == [[3]]

    res = await admin_client.get(f"/bi/{dash.slug}/snapshots/{snapshot_id}")
    assert res.status_code == 200
    body = res.text
    assert 'data-pql-entry="bi_snapshot.js' in body
    # tojson output carries double quotes, so the x-data attribute
    # MUST stay single-quoted or Alpine sees a torn expression.
    assert "x-data='biSnapshotView(" in body

    res = await admin_client.get(f"/api/bi/dashboards/{dash.slug}/snapshots/999999")
    assert res.status_code == 404
