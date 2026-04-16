"""Tests for the Sprint 19 scheduler and job routes."""

from __future__ import annotations

import datetime
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from pointlessql.api.main import app
from pointlessql.exceptions import ValidationError
from pointlessql.models import Base, Job, JobRun, User
from pointlessql.services import scheduler as scheduler_service
from pointlessql.services.scheduler import (
    KindRegistry,
    Scheduler,
    build_default_registry,
    execute_run,
    tick_once,
)
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.settings import Settings
from pointlessql.types import UserInfo


@pytest.fixture
def scheduler_factory() -> Any:
    """Return an in-memory session factory with a single seed user."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        session.add(
            User(
                email="runner@test.com",
                display_name="Runner",
                password_hash="x",
                is_admin=False,
                created_at=datetime.datetime(2026, 4, 1, tzinfo=datetime.UTC),
            )
        )
        session.commit()
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def _seed_job(
    factory: Any,
    *,
    name: str = "job-1",
    cron_expr: str = "* * * * *",
    kind: str = "fake",
    config: dict[str, Any] | None = None,
    is_paused: bool = False,
    run_as_user_id: int | None = None,
) -> int:
    with factory() as session:
        if run_as_user_id is None:
            user = session.scalars(select(User)).first()
            assert user is not None
            run_as_user_id = user.id
        now = datetime.datetime(2026, 4, 1, tzinfo=datetime.UTC)
        job = Job(
            name=name,
            cron_expr=cron_expr,
            run_as_user_id=run_as_user_id,
            kind=kind,
            config=json.dumps(config or {}),
            is_paused=is_paused,
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        return job.id


def _settings() -> Settings:
    return Settings(
        jupyter_enabled=False,
        scheduler_enabled=False,
        soyuz_catalog_url="http://127.0.0.1:8080",
    )


class _RecordingRegistry(KindRegistry):
    """Registry that records every invocation for assertions."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[int, UserInfo, dict[str, Any]]] = []
        self.should_raise: Exception | None = None

        async def _fake(
            job_run_id: int,
            user_info: UserInfo,
            config: dict[str, Any],
            uc_client: UnityCatalogClient,
        ) -> None:
            self.calls.append((job_run_id, user_info, config))
            if self.should_raise is not None:
                raise self.should_raise

        self.register("fake", _fake)


class TestIsDue:
    def test_never_run_is_due_for_every_minute(self) -> None:
        now = datetime.datetime(2026, 4, 1, 12, 0, tzinfo=datetime.UTC)
        assert scheduler_service._is_due("* * * * *", now, None) is True

    def test_not_due_when_last_run_matches_cron(self) -> None:
        # Last run at 12:00, cron every minute — at 12:00 the next fire
        # is 12:01, which is > now, so not due.
        now = datetime.datetime(2026, 4, 1, 12, 0, 30, tzinfo=datetime.UTC)
        last = datetime.datetime(2026, 4, 1, 12, 0, tzinfo=datetime.UTC)
        assert scheduler_service._is_due("* * * * *", now, last) is False

    def test_due_when_cron_elapsed_since_last_run(self) -> None:
        now = datetime.datetime(2026, 4, 1, 12, 5, tzinfo=datetime.UTC)
        last = datetime.datetime(2026, 4, 1, 12, 0, tzinfo=datetime.UTC)
        assert scheduler_service._is_due("*/5 * * * *", now, last) is True

    def test_invalid_cron_raises(self) -> None:
        with pytest.raises(ValidationError):
            scheduler_service._is_due("not a cron", datetime.datetime.now(datetime.UTC), None)


class TestTickOnce:
    async def test_runs_due_job(
        self, scheduler_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        registry = _RecordingRegistry()
        monkeypatch.setattr(
            UnityCatalogClient,
            "for_principal",
            classmethod(lambda cls, s, p: MagicMock(spec=UnityCatalogClient)),
        )
        _seed_job(scheduler_factory, cron_expr="* * * * *")
        now = datetime.datetime(2026, 4, 1, 12, 5, tzinfo=datetime.UTC)
        runs = await tick_once(scheduler_factory, _settings(), registry, now=now)
        assert len(runs) == 1
        assert runs[0].status == "succeeded"
        assert runs[0].trigger == "scheduled"
        assert len(registry.calls) == 1
        assert registry.calls[0][0] == runs[0].id
        # Job id resolves to our seed user
        assert registry.calls[0][1]["email"] == "runner@test.com"
        assert registry.calls[0][2] == {}
        # Second tick without advancing the clock should not re-fire.
        registry.calls.clear()
        runs2 = await tick_once(scheduler_factory, _settings(), registry, now=now)
        assert runs2 == []

    async def test_skips_paused_job(
        self, scheduler_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        registry = _RecordingRegistry()
        monkeypatch.setattr(
            UnityCatalogClient,
            "for_principal",
            classmethod(lambda cls, s, p: MagicMock(spec=UnityCatalogClient)),
        )
        _seed_job(scheduler_factory, is_paused=True)
        now = datetime.datetime(2026, 4, 1, 12, 5, tzinfo=datetime.UTC)
        runs = await tick_once(scheduler_factory, _settings(), registry, now=now)
        assert runs == []
        assert registry.calls == []

    async def test_skipped_run_when_previous_still_running(
        self, scheduler_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        registry = _RecordingRegistry()
        monkeypatch.setattr(
            UnityCatalogClient,
            "for_principal",
            classmethod(lambda cls, s, p: MagicMock(spec=UnityCatalogClient)),
        )
        job_id = _seed_job(scheduler_factory, cron_expr="* * * * *")
        # Seed a stuck "running" row so the overlap guard trips.
        with scheduler_factory() as session:
            session.add(
                JobRun(
                    job_id=job_id,
                    started_at=datetime.datetime(
                        2026, 4, 1, 11, 0, tzinfo=datetime.UTC
                    ),
                    status="running",
                    trigger="scheduled",
                )
            )
            session.commit()

        now = datetime.datetime(2026, 4, 1, 12, 5, tzinfo=datetime.UTC)
        runs = await tick_once(scheduler_factory, _settings(), registry, now=now)
        assert len(runs) == 1
        assert runs[0].status == "skipped"
        assert registry.calls == []

    async def test_executor_failure_marks_run_failed(
        self, scheduler_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        registry = _RecordingRegistry()
        registry.should_raise = RuntimeError("boom")
        monkeypatch.setattr(
            UnityCatalogClient,
            "for_principal",
            classmethod(lambda cls, s, p: MagicMock(spec=UnityCatalogClient)),
        )
        _seed_job(scheduler_factory, cron_expr="* * * * *")
        now = datetime.datetime(2026, 4, 1, 12, 5, tzinfo=datetime.UTC)
        runs = await tick_once(scheduler_factory, _settings(), registry, now=now)
        assert len(runs) == 1
        assert runs[0].status == "failed"
        assert runs[0].error is not None
        assert "boom" in runs[0].error

    async def test_missing_user_marks_run_failed(
        self, scheduler_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        registry = _RecordingRegistry()
        monkeypatch.setattr(
            UnityCatalogClient,
            "for_principal",
            classmethod(lambda cls, s, p: MagicMock(spec=UnityCatalogClient)),
        )
        # Seed a job pointing at a non-existent user.
        _seed_job(scheduler_factory, cron_expr="* * * * *", run_as_user_id=999)
        now = datetime.datetime(2026, 4, 1, 12, 5, tzinfo=datetime.UTC)
        runs = await tick_once(scheduler_factory, _settings(), registry, now=now)
        assert len(runs) == 1
        assert runs[0].status == "failed"
        assert runs[0].error is not None
        assert "999" in runs[0].error


class TestExecuteRun:
    async def test_for_principal_called_with_user_email(
        self, scheduler_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        registry = _RecordingRegistry()
        captured_principals: list[str] = []

        def _fake_for_principal(cls: Any, s: Any, p: str) -> MagicMock:
            captured_principals.append(p)
            return MagicMock(spec=UnityCatalogClient)

        monkeypatch.setattr(
            UnityCatalogClient,
            "for_principal",
            classmethod(_fake_for_principal),
        )
        job_id = _seed_job(scheduler_factory)
        run = await execute_run(
            scheduler_factory, _settings(), registry, job_id, "manual"
        )
        assert run.status == "succeeded"
        assert captured_principals == ["runner@test.com"]

    async def test_invalid_config_json_recorded_as_failed(
        self, scheduler_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        registry = _RecordingRegistry()
        monkeypatch.setattr(
            UnityCatalogClient,
            "for_principal",
            classmethod(lambda cls, s, p: MagicMock(spec=UnityCatalogClient)),
        )
        job_id = _seed_job(scheduler_factory)
        with scheduler_factory() as session:
            job = session.get(Job, job_id)
            assert job is not None
            job.config = "{not valid json"
            session.commit()
        run = await execute_run(
            scheduler_factory, _settings(), registry, job_id, "manual"
        )
        assert run.status == "failed"
        assert run.error is not None
        assert "invalid job config" in run.error


class TestPgSyncKind:
    async def test_pg_sync_executor_end_to_end(
        self,
        scheduler_factory: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from pointlessql.services import pg_sync as pg_sync_service

        uc = MagicMock(spec=UnityCatalogClient)
        uc.get_catalog = AsyncMock(
            return_value={"name": "pg_cat", "connection_name": "pg1"}
        )
        uc.get_connection = AsyncMock(
            return_value={"name": "pg1", "options": {"host": "h", "database": "d"}}
        )
        uc.list_schemas = AsyncMock(return_value=[])
        uc.list_tables = AsyncMock(return_value=[])
        uc.create_schema = AsyncMock(return_value={})
        uc.create_table = AsyncMock(return_value={})

        monkeypatch.setattr(
            UnityCatalogClient,
            "for_principal",
            classmethod(lambda cls, s, p: uc),
        )

        monkeypatch.setattr(
            "pointlessql.db.get_session_factory",
            lambda: scheduler_factory,
        )

        # Stub the introspector so the executor never touches psycopg.
        from pointlessql.services.pg_sync import PostgresSnapshot

        class _StubIntrospector:
            def snapshot(self, dsn: str, schema_filter: Any = None) -> PostgresSnapshot:
                from pointlessql.services.pg_sync import PgColumn, PgTable

                return PostgresSnapshot(
                    tables=(
                        PgTable(
                            schema="public",
                            name="users",
                            columns=(
                                PgColumn(name="id", data_type="integer", nullable=False),
                            ),
                        ),
                    )
                )

        monkeypatch.setattr(
            pg_sync_service, "PsycopgIntrospector", _StubIntrospector
        )

        registry = build_default_registry()
        job_id = _seed_job(
            scheduler_factory,
            kind="pg_sync",
            config={"catalog_name": "pg_cat"},
        )
        run = await execute_run(
            scheduler_factory, _settings(), registry, job_id, "manual"
        )
        assert run.status == "succeeded"

        # A SyncRun row landed in our metadata DB.
        from pointlessql.models import SyncRun

        with scheduler_factory() as session:
            syncs = list(session.scalars(select(SyncRun)).all())
        assert len(syncs) == 1
        assert syncs[0].catalog_name == "pg_cat"
        assert syncs[0].status == "succeeded"

    async def test_pg_sync_requires_catalog_name(
        self,
        scheduler_factory: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        uc = MagicMock(spec=UnityCatalogClient)
        monkeypatch.setattr(
            UnityCatalogClient,
            "for_principal",
            classmethod(lambda cls, s, p: uc),
        )
        registry = build_default_registry()
        job_id = _seed_job(
            scheduler_factory, kind="pg_sync", config={}
        )
        run = await execute_run(
            scheduler_factory, _settings(), registry, job_id, "manual"
        )
        assert run.status == "failed"
        assert run.error is not None
        assert "catalog_name" in run.error


class TestSchedulerLifecycle:
    async def test_start_stop_is_idempotent(
        self, scheduler_factory: Any
    ) -> None:
        settings = _settings()
        # Very fast tick so the loop iterates at least once.
        settings = Settings(
            jupyter_enabled=False,
            scheduler_enabled=False,
            scheduler_tick_seconds=60,
            soyuz_catalog_url="http://127.0.0.1:8080",
        )
        sched = Scheduler(scheduler_factory, settings, registry=KindRegistry())
        sched.start()
        sched.start()  # second start is a no-op
        await sched.stop()
        # Second stop is a no-op.
        await sched.stop()


# -- Route tests --


def _admin_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    )


def _non_admin_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_non_admin_cookie,
    )


@pytest.fixture(autouse=True)
def _patch_for_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route per-request client construction through app.state.uc_client."""
    app.state.uc_client = MagicMock(spec=UnityCatalogClient)
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: app.state.uc_client),
    )


class TestJobRoutes:
    async def test_admin_can_create_job(self) -> None:
        async with _admin_client() as client:
            resp = await client.post(
                "/api/jobs",
                json={
                    "name": "sync-analytics",
                    "cron_expr": "*/5 * * * *",
                    "kind": "python",
                    "config": {"entry_point": "my_job"},
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "sync-analytics"
        assert data["kind"] == "python"
        assert data["is_paused"] is False

    async def test_non_admin_create_forbidden(self) -> None:
        async with _non_admin_client() as client:
            resp = await client.post(
                "/api/jobs",
                json={
                    "name": "x",
                    "cron_expr": "* * * * *",
                    "kind": "python",
                    "config": {"entry_point": "x"},
                },
            )
        assert resp.status_code == 403

    async def test_invalid_cron_rejected(self) -> None:
        async with _admin_client() as client:
            resp = await client.post(
                "/api/jobs",
                json={
                    "name": "bad",
                    "cron_expr": "not-a-cron",
                    "kind": "python",
                    "config": {},
                },
            )
        assert resp.status_code == 422

    async def test_unknown_kind_rejected(self) -> None:
        async with _admin_client() as client:
            resp = await client.post(
                "/api/jobs",
                json={
                    "name": "bad",
                    "cron_expr": "* * * * *",
                    "kind": "does-not-exist",
                    "config": {},
                },
            )
        assert resp.status_code == 422

    async def test_list_filters_by_ownership(self) -> None:
        factory = app.state.session_factory
        # Seed: admin-owned job and non-admin-owned job.
        with factory() as session:
            admin_user = session.scalars(
                select(User).where(User.email == "test@test.com")
            ).first()
            non_admin_user = session.scalars(
                select(User).where(User.email == "nonadmin@test.com")
            ).first()
            assert admin_user is not None and non_admin_user is not None
            now = datetime.datetime.now(datetime.UTC)
            session.add(
                Job(
                    name="admin-owned",
                    cron_expr="* * * * *",
                    run_as_user_id=admin_user.id,
                    kind="python",
                    config="{}",
                    is_paused=False,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                Job(
                    name="user-owned",
                    cron_expr="* * * * *",
                    run_as_user_id=non_admin_user.id,
                    kind="python",
                    config="{}",
                    is_paused=False,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()

        async with _admin_client() as client:
            resp = await client.get("/api/jobs")
        assert resp.status_code == 200
        names = {j["name"] for j in resp.json()}
        assert names == {"admin-owned", "user-owned"}

        async with _non_admin_client() as client:
            resp = await client.get("/api/jobs")
        assert resp.status_code == 200
        names = {j["name"] for j in resp.json()}
        assert names == {"user-owned"}

    async def test_manual_run_and_pause_unpause(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Register a fake kind so we don't require pg_sync plumbing.
        recording_registry = _RecordingRegistry()

        # Swap the module-level registry for the duration of the test.
        from pointlessql.api import main as api_main

        monkeypatch.setattr(api_main, "_JOB_REGISTRY", recording_registry)

        factory = app.state.session_factory
        with factory() as session:
            admin_user = session.scalars(
                select(User).where(User.email == "test@test.com")
            ).first()
            assert admin_user is not None
            now = datetime.datetime.now(datetime.UTC)
            job = Job(
                name="manual-fake",
                cron_expr="* * * * *",
                run_as_user_id=admin_user.id,
                kind="fake",
                config="{}",
                is_paused=False,
                created_at=now,
                updated_at=now,
            )
            session.add(job)
            session.commit()
            job_id = job.id

        async with _admin_client() as client:
            run_resp = await client.post(f"/api/jobs/{job_id}/run")
        assert run_resp.status_code == 200
        assert run_resp.json()["status"] == "succeeded"
        assert run_resp.json()["trigger"] == "manual"
        assert len(recording_registry.calls) == 1

        async with _admin_client() as client:
            pause_resp = await client.post(f"/api/jobs/{job_id}/pause")
        assert pause_resp.status_code == 200
        assert pause_resp.json()["is_paused"] is True

        async with _admin_client() as client:
            unpause_resp = await client.post(f"/api/jobs/{job_id}/unpause")
        assert unpause_resp.status_code == 200
        assert unpause_resp.json()["is_paused"] is False

    async def test_non_owner_cannot_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        factory = app.state.session_factory
        with factory() as session:
            admin_user = session.scalars(
                select(User).where(User.email == "test@test.com")
            ).first()
            assert admin_user is not None
            now = datetime.datetime.now(datetime.UTC)
            job = Job(
                name="admin-only",
                cron_expr="* * * * *",
                run_as_user_id=admin_user.id,
                kind="python",
                config="{}",
                is_paused=False,
                created_at=now,
                updated_at=now,
            )
            session.add(job)
            session.commit()
            job_id = job.id

        # Non-admin cannot see or act on a job they do not own.
        async with _non_admin_client() as client:
            resp = await client.post(f"/api/jobs/{job_id}/run")
        assert resp.status_code == 404

    async def test_jobs_page_renders(self) -> None:
        async with _admin_client() as client:
            resp = await client.get("/jobs")
        assert resp.status_code == 200
        assert "Jobs" in resp.text

    async def test_job_detail_renders_runs(self) -> None:
        factory = app.state.session_factory
        with factory() as session:
            admin_user = session.scalars(
                select(User).where(User.email == "test@test.com")
            ).first()
            assert admin_user is not None
            now = datetime.datetime.now(datetime.UTC)
            job = Job(
                name="my-job",
                cron_expr="* * * * *",
                run_as_user_id=admin_user.id,
                kind="python",
                config="{}",
                is_paused=False,
                created_at=now,
                updated_at=now,
            )
            session.add(job)
            session.commit()
            job_id = job.id
            session.add(
                JobRun(
                    job_id=job_id,
                    started_at=now,
                    finished_at=now + datetime.timedelta(seconds=2),
                    status="succeeded",
                    trigger="manual",
                )
            )
            session.commit()

        async with _admin_client() as client:
            resp = await client.get(f"/jobs/{job_id}")
        assert resp.status_code == 200
        assert "my-job" in resp.text
        assert "succeeded" in resp.text
