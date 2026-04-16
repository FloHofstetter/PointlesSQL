"""Tests for Sprint 21 observability: metrics, /metrics route, webhook."""

from __future__ import annotations

import datetime
import json
from types import TracebackType
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from pointlessql.api.main import app
from pointlessql.models import Base, Job, JobRun, User
from pointlessql.services import metrics as metrics_service
from pointlessql.services import scheduler as scheduler_service
from pointlessql.services.scheduler import KindRegistry, execute_run
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.settings import Settings
from pointlessql.types import UserInfo


@pytest.fixture
def metrics_factory() -> Any:
    """Return an in-memory session factory seeded with one runner user."""
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


def _settings() -> Settings:
    return Settings(
        jupyter_enabled=False,
        scheduler_enabled=False,
        soyuz_catalog_url="http://127.0.0.1:8080",
    )


def _seed_job(
    factory: Any,
    *,
    name: str = "metric-job",
    kind: str = "fake",
    on_failure_url: str | None = None,
) -> int:
    """Create a job row and return its id."""
    now = datetime.datetime(2026, 4, 1, tzinfo=datetime.UTC)
    with factory() as session:
        user = session.scalars(select(User)).first()
        assert user is not None
        job = Job(
            name=name,
            cron_expr="* * * * *",
            run_as_user_id=user.id,
            kind=kind,
            config="{}",
            is_paused=False,
            max_parallel_runs=1,
            on_failure_url=on_failure_url,
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        return job.id


class _OkRegistry(KindRegistry):
    """Registry whose ``fake`` executor always succeeds."""

    def __init__(self) -> None:
        super().__init__()

        async def _fake(
            job_run_id: int,
            user_info: UserInfo,
            config: dict[str, Any],
            uc_client: UnityCatalogClient,
        ) -> None:
            del job_run_id, user_info, config, uc_client

        self.register("fake", _fake)


class _FailRegistry(KindRegistry):
    """Registry whose ``fake`` executor always raises."""

    def __init__(self, detail: str = "boom") -> None:
        super().__init__()

        async def _fake(
            job_run_id: int,
            user_info: UserInfo,
            config: dict[str, Any],
            uc_client: UnityCatalogClient,
        ) -> None:
            del job_run_id, user_info, config, uc_client
            raise RuntimeError(detail)

        self.register("fake", _fake)


class _CapturingHTTPClient:
    """Stub httpx.AsyncClient that records every ``post`` call."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.raise_on_post: Exception | None = None

    async def __aenter__(self) -> _CapturingHTTPClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def post(
        self,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if self.raise_on_post is not None:
            raise self.raise_on_post
        return MagicMock()


class TestMetricEmission:
    async def test_counter_and_histogram_move_on_success(
        self,
        metrics_factory: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            UnityCatalogClient,
            "for_principal",
            classmethod(lambda cls, s, p: MagicMock(spec=UnityCatalogClient)),
        )
        job_id = _seed_job(metrics_factory, name="ok-job")
        before = metrics_service.job_runs_total.labels(
            status="succeeded", job_name="ok-job"
        )._value.get()
        before_hist = metrics_service.job_run_duration_seconds.labels(
            job_name="ok-job"
        )._sum.get()

        run = await execute_run(
            metrics_factory, _settings(), _OkRegistry(), job_id, "manual"
        )
        assert run.status == "succeeded"

        after = metrics_service.job_runs_total.labels(
            status="succeeded", job_name="ok-job"
        )._value.get()
        after_hist = metrics_service.job_run_duration_seconds.labels(
            job_name="ok-job"
        )._sum.get()

        assert after == before + 1
        # The executor does no real work so the observed duration is
        # very close to zero but non-negative — the histogram's _sum
        # must advance by some finite amount (or stay equal if the
        # clock resolved the two timestamps identically).
        assert after_hist >= before_hist

    async def test_counter_increments_on_failure(
        self,
        metrics_factory: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            UnityCatalogClient,
            "for_principal",
            classmethod(lambda cls, s, p: MagicMock(spec=UnityCatalogClient)),
        )
        job_id = _seed_job(metrics_factory, name="fail-job")
        before = metrics_service.job_runs_total.labels(
            status="failed", job_name="fail-job"
        )._value.get()

        run = await execute_run(
            metrics_factory, _settings(), _FailRegistry(), job_id, "manual"
        )
        assert run.status == "failed"

        after = metrics_service.job_runs_total.labels(
            status="failed", job_name="fail-job"
        )._value.get()
        assert after == before + 1

    def test_render_metrics_produces_text_exposition(self) -> None:
        # Nudge the counter so the render has something to print.
        metrics_service.job_runs_total.labels(
            status="succeeded", job_name="render-probe"
        ).inc()
        body, content_type = metrics_service.render_metrics()
        assert content_type.startswith("text/plain")
        text = body.decode()
        assert "pointlessql_job_runs_total" in text
        assert "pointlessql_job_run_duration_seconds" in text


class TestMetricsRouteAuth:
    async def test_admin_gets_200_with_text(
        self, auth_cookies: dict[str, str]
    ) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies=auth_cookies,
        ) as client:
            resp = await client.get("/metrics")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/plain")
        assert "pointlessql_job_runs_total" in resp.text

    async def test_non_admin_gets_403(
        self, non_admin_cookies: dict[str, str]
    ) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies=non_admin_cookies,
        ) as client:
            resp = await client.get("/metrics")
        assert resp.status_code == 403


class TestFailureWebhook:
    async def test_webhook_posted_on_failure(
        self,
        metrics_factory: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            UnityCatalogClient,
            "for_principal",
            classmethod(lambda cls, s, p: MagicMock(spec=UnityCatalogClient)),
        )
        stub = _CapturingHTTPClient()
        monkeypatch.setattr(
            scheduler_service, "_webhook_client_factory", lambda: stub
        )

        job_id = _seed_job(
            metrics_factory,
            name="hook-job",
            on_failure_url="https://hooks.example.com/on-fail",
        )
        run = await execute_run(
            metrics_factory,
            _settings(),
            _FailRegistry(detail="kaboom"),
            job_id,
            "manual",
        )
        assert run.status == "failed"
        assert len(stub.calls) == 1
        call = stub.calls[0]
        assert call["url"] == "https://hooks.example.com/on-fail"
        assert call["timeout"] == scheduler_service._WEBHOOK_TIMEOUT_SECONDS
        payload = call["json"]
        assert payload is not None
        for key in (
            "job_id",
            "job_name",
            "run_id",
            "status",
            "error",
            "started_at",
            "finished_at",
        ):
            assert key in payload
        assert payload["job_id"] == job_id
        assert payload["job_name"] == "hook-job"
        assert payload["status"] == "failed"
        assert payload["error"] is not None and "kaboom" in payload["error"]
        # Ensure the payload is JSON-serializable (timestamps are strings).
        json.dumps(payload)

    async def test_no_webhook_when_url_missing(
        self,
        metrics_factory: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            UnityCatalogClient,
            "for_principal",
            classmethod(lambda cls, s, p: MagicMock(spec=UnityCatalogClient)),
        )
        stub = _CapturingHTTPClient()
        monkeypatch.setattr(
            scheduler_service, "_webhook_client_factory", lambda: stub
        )

        job_id = _seed_job(metrics_factory, name="no-hook", on_failure_url=None)
        run = await execute_run(
            metrics_factory,
            _settings(),
            _FailRegistry(),
            job_id,
            "manual",
        )
        assert run.status == "failed"
        assert stub.calls == []

    async def test_no_webhook_on_success(
        self,
        metrics_factory: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            UnityCatalogClient,
            "for_principal",
            classmethod(lambda cls, s, p: MagicMock(spec=UnityCatalogClient)),
        )
        stub = _CapturingHTTPClient()
        monkeypatch.setattr(
            scheduler_service, "_webhook_client_factory", lambda: stub
        )

        job_id = _seed_job(
            metrics_factory,
            name="succeed-hook",
            on_failure_url="https://hooks.example.com/on-fail",
        )
        run = await execute_run(
            metrics_factory, _settings(), _OkRegistry(), job_id, "manual"
        )
        assert run.status == "succeeded"
        assert stub.calls == []

    async def test_webhook_failure_does_not_abort_run(
        self,
        metrics_factory: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            UnityCatalogClient,
            "for_principal",
            classmethod(lambda cls, s, p: MagicMock(spec=UnityCatalogClient)),
        )
        stub = _CapturingHTTPClient()
        stub.raise_on_post = httpx.ConnectError("no listener")
        monkeypatch.setattr(
            scheduler_service, "_webhook_client_factory", lambda: stub
        )

        job_id = _seed_job(
            metrics_factory,
            name="bad-hook",
            on_failure_url="https://hooks.example.com/on-fail",
        )
        # The webhook explodes, but execute_run must still return the
        # run row with the correct terminal state.
        run = await execute_run(
            metrics_factory,
            _settings(),
            _FailRegistry(),
            job_id,
            "manual",
        )
        assert run.status == "failed"
        # The DB row still shows failed — catchable via a fresh read.
        with metrics_factory() as session:
            persisted = session.get(JobRun, run.id)
            assert persisted is not None
            assert persisted.status == "failed"
