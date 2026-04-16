"""Tests for Sprint 20 DAG engine: topology, retries, concurrency, logging."""

from __future__ import annotations

import asyncio
import datetime
import itertools
import json
import logging
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from pointlessql.exceptions import ValidationError
from pointlessql.logging_config import (
    job_run_id_var,
    task_id_var,
)
from pointlessql.models import (
    Base,
    Job,
    JobLog,
    JobRun,
    JobTask,
    TaskRun,
    User,
)
from pointlessql.services import scheduler as scheduler_service
from pointlessql.services.scheduler import (
    KindRegistry,
    execute_run,
    log_job,
    tick_once,
    validate_dag,
)
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.settings import Settings
from pointlessql.types import UserInfo

_SEED_COUNTER = itertools.count()


@pytest.fixture
def dag_factory() -> Any:
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


def _seed_job_with_tasks(
    factory: Any,
    tasks_spec: list[dict[str, Any]],
    *,
    cron_expr: str = "* * * * *",
    max_parallel_runs: int = 1,
) -> tuple[int, dict[str, int]]:
    """Create a job with :class:`JobTask` rows mirroring *tasks_spec*.

    ``tasks_spec`` is a list of dicts with keys:
    ``name, kind (default "fake"), config, depends_on (names),
    max_retries, retry_backoff_seconds``.

    Returns ``(job_id, {task_name: task_id})``.
    """
    now = datetime.datetime(2026, 4, 1, tzinfo=datetime.UTC)
    with factory() as session:
        user = session.scalars(select(User)).first()
        assert user is not None
        job = Job(
            name=f"dag-{next(_SEED_COUNTER)}",
            cron_expr=cron_expr,
            run_as_user_id=user.id,
            kind="fake",
            config="{}",
            is_paused=False,
            max_parallel_runs=max_parallel_runs,
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        session.flush()
        name_to_id: dict[str, int] = {}
        for spec in tasks_spec:
            jt = JobTask(
                job_id=job.id,
                name=spec["name"],
                order=0,
                kind=spec.get("kind", "fake"),
                config=json.dumps(spec.get("config") or {}),
                depends_on="[]",
                max_retries=int(spec.get("max_retries", 0)),
                retry_backoff_seconds=int(spec.get("retry_backoff_seconds", 0)),
            )
            session.add(jt)
            session.flush()
            name_to_id[spec["name"]] = jt.id
        # Second pass: resolve depends_on names → ids.
        for spec in tasks_spec:
            deps_names = spec.get("depends_on") or []
            resolved = [name_to_id[n] for n in deps_names]
            row = session.get(JobTask, name_to_id[spec["name"]])
            assert row is not None
            row.depends_on = json.dumps(resolved)
        session.commit()
        return job.id, name_to_id


class _RecordingRegistry(KindRegistry):
    """Registry that records every invocation per-task for assertions."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []  # task names in order
        self.fail_names: set[str] = set()
        self.fail_names_until_attempt: dict[str, int] = {}
        self.attempts_per_name: dict[str, int] = {}

        async def _fake(
            job_run_id: int,
            user_info: UserInfo,
            config: dict[str, Any],
            uc_client: UnityCatalogClient,
        ) -> None:
            name = str(config.get("_name", ""))
            self.calls.append(name)
            self.attempts_per_name[name] = self.attempts_per_name.get(name, 0) + 1
            if name in self.fail_names:
                raise RuntimeError(f"{name} always fails")
            thresh = self.fail_names_until_attempt.get(name)
            if thresh is not None and self.attempts_per_name[name] < thresh:
                raise RuntimeError(
                    f"{name} failing attempt {self.attempts_per_name[name]}"
                )

        self.register("fake", _fake)


class TestValidateDag:
    def test_cycle_detected(self) -> None:
        a = JobTask(
            id=1, job_id=1, name="a", order=0, kind="fake",
            config="{}", depends_on=json.dumps([2]),
            max_retries=0, retry_backoff_seconds=0,
        )
        b = JobTask(
            id=2, job_id=1, name="b", order=0, kind="fake",
            config="{}", depends_on=json.dumps([1]),
            max_retries=0, retry_backoff_seconds=0,
        )
        with pytest.raises(ValidationError, match="cycle"):
            validate_dag([a, b])

    def test_self_loop_detected(self) -> None:
        a = JobTask(
            id=1, job_id=1, name="a", order=0, kind="fake",
            config="{}", depends_on=json.dumps([1]),
            max_retries=0, retry_backoff_seconds=0,
        )
        with pytest.raises(ValidationError, match="cycle"):
            validate_dag([a])

    def test_unknown_dependency_rejected(self) -> None:
        a = JobTask(
            id=1, job_id=1, name="a", order=0, kind="fake",
            config="{}", depends_on=json.dumps([99]),
            max_retries=0, retry_backoff_seconds=0,
        )
        with pytest.raises(ValidationError, match="unknown task"):
            validate_dag([a])

    def test_valid_diamond_passes(self) -> None:
        # a → b,c → d
        a = JobTask(id=1, job_id=1, name="a", order=0, kind="fake",
                    config="{}", depends_on=json.dumps([]),
                    max_retries=0, retry_backoff_seconds=0)
        b = JobTask(id=2, job_id=1, name="b", order=0, kind="fake",
                    config="{}", depends_on=json.dumps([1]),
                    max_retries=0, retry_backoff_seconds=0)
        c = JobTask(id=3, job_id=1, name="c", order=0, kind="fake",
                    config="{}", depends_on=json.dumps([1]),
                    max_retries=0, retry_backoff_seconds=0)
        d = JobTask(id=4, job_id=1, name="d", order=0, kind="fake",
                    config="{}", depends_on=json.dumps([2, 3]),
                    max_retries=0, retry_backoff_seconds=0)
        # Should not raise.
        validate_dag([a, b, c, d])


class TestTopologicalExecution:
    async def test_diamond_executes_in_topological_order(
        self, dag_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            UnityCatalogClient,
            "for_principal",
            classmethod(lambda cls, s, p: MagicMock(spec=UnityCatalogClient)),
        )
        registry = _RecordingRegistry()
        # Diamond: a → b,c → d. Pass task names via config for tracking.
        job_id, _names = _seed_job_with_tasks(
            dag_factory,
            [
                {"name": "a", "config": {"_name": "a"}},
                {"name": "b", "config": {"_name": "b"}, "depends_on": ["a"]},
                {"name": "c", "config": {"_name": "c"}, "depends_on": ["a"]},
                {"name": "d", "config": {"_name": "d"}, "depends_on": ["b", "c"]},
            ],
        )

        run = await execute_run(
            dag_factory, _settings(), registry, job_id, "manual"
        )
        assert run.status == "succeeded"
        # "a" runs first, "d" runs last; b and c both come between.
        assert registry.calls[0] == "a"
        assert registry.calls[-1] == "d"
        assert set(registry.calls[1:3]) == {"b", "c"}

    async def test_upstream_failure_skips_downstream(
        self, dag_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            UnityCatalogClient,
            "for_principal",
            classmethod(lambda cls, s, p: MagicMock(spec=UnityCatalogClient)),
        )
        registry = _RecordingRegistry()
        registry.fail_names.add("a")
        job_id, names = _seed_job_with_tasks(
            dag_factory,
            [
                {"name": "a", "config": {"_name": "a"}},
                {"name": "b", "config": {"_name": "b"}, "depends_on": ["a"]},
                {"name": "c", "config": {"_name": "c"}, "depends_on": ["b"]},
            ],
        )
        run = await execute_run(
            dag_factory, _settings(), registry, job_id, "manual"
        )
        assert run.status == "failed"
        # "b" and "c" should be marked skipped — executor never invoked.
        assert registry.calls == ["a"]
        with dag_factory() as session:
            task_runs = list(
                session.scalars(
                    select(TaskRun).where(TaskRun.job_run_id == run.id)
                ).all()
            )
        statuses = {tr.task_id: tr.status for tr in task_runs}
        assert statuses[names["a"]] == "failed"
        assert statuses[names["b"]] == "skipped"
        assert statuses[names["c"]] == "skipped"


class TestRetryPolicy:
    async def test_retry_with_backoff_eventually_succeeds(
        self, dag_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            UnityCatalogClient,
            "for_principal",
            classmethod(lambda cls, s, p: MagicMock(spec=UnityCatalogClient)),
        )
        sleep_calls: list[float] = []

        async def _fake_sleep(delay: float) -> None:
            sleep_calls.append(delay)

        monkeypatch.setattr(scheduler_service, "_sleep", _fake_sleep)
        registry = _RecordingRegistry()
        registry.fail_names_until_attempt["flaky"] = 3  # fail attempts 1,2; succeed on 3

        job_id, names = _seed_job_with_tasks(
            dag_factory,
            [
                {
                    "name": "flaky",
                    "config": {"_name": "flaky"},
                    "max_retries": 3,
                    "retry_backoff_seconds": 2,
                }
            ],
        )
        run = await execute_run(
            dag_factory, _settings(), registry, job_id, "manual"
        )
        assert run.status == "succeeded"
        # Three attempts total.
        assert registry.attempts_per_name["flaky"] == 3
        # Two sleeps (after attempts 1 and 2). Linear backoff: 1*2=2, 2*2=4.
        assert sleep_calls == [2.0, 4.0]
        with dag_factory() as session:
            tr = session.scalars(
                select(TaskRun).where(TaskRun.task_id == names["flaky"])
            ).first()
        assert tr is not None
        assert tr.status == "succeeded"
        assert tr.attempts == 3

    async def test_retry_exhaustion_marks_failed(
        self, dag_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            UnityCatalogClient,
            "for_principal",
            classmethod(lambda cls, s, p: MagicMock(spec=UnityCatalogClient)),
        )

        async def _fake_sleep(delay: float) -> None:
            del delay

        monkeypatch.setattr(scheduler_service, "_sleep", _fake_sleep)
        registry = _RecordingRegistry()
        registry.fail_names.add("doomed")

        job_id, names = _seed_job_with_tasks(
            dag_factory,
            [
                {
                    "name": "doomed",
                    "config": {"_name": "doomed"},
                    "max_retries": 2,
                    "retry_backoff_seconds": 1,
                }
            ],
        )
        run = await execute_run(
            dag_factory, _settings(), registry, job_id, "manual"
        )
        assert run.status == "failed"
        assert registry.attempts_per_name["doomed"] == 3  # initial + 2 retries
        with dag_factory() as session:
            tr = session.scalars(
                select(TaskRun).where(TaskRun.task_id == names["doomed"])
            ).first()
        assert tr is not None
        assert tr.status == "failed"
        assert tr.attempts == 3
        assert tr.error is not None
        assert "doomed" in tr.error


class TestConcurrencyCaps:
    async def test_per_job_max_parallel_runs_blocks_overlapping(
        self, dag_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            UnityCatalogClient,
            "for_principal",
            classmethod(lambda cls, s, p: MagicMock(spec=UnityCatalogClient)),
        )
        registry = _RecordingRegistry()
        # max_parallel_runs=2 means up to two ``running`` concurrently.
        job_id, _ = _seed_job_with_tasks(
            dag_factory,
            [{"name": "a", "config": {"_name": "a"}}],
        )
        with dag_factory() as session:
            job = session.get(Job, job_id)
            assert job is not None
            job.max_parallel_runs = 2
            session.commit()

        # Seed 2 currently-running rows to saturate the per-job cap.
        with dag_factory() as session:
            for _ in range(2):
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
        runs = await tick_once(dag_factory, _settings(), registry, now=now)
        # Expect skipped because 2 running >= cap 2.
        assert len(runs) == 1
        assert runs[0].status == "skipped"

    async def test_global_semaphore_limits_concurrent_runs(
        self, dag_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            UnityCatalogClient,
            "for_principal",
            classmethod(lambda cls, s, p: MagicMock(spec=UnityCatalogClient)),
        )
        # Track concurrent in-flight executor calls. Cap is 1.
        max_seen = 0
        current = 0

        async def _slow_fake(
            job_run_id: int,
            user_info: UserInfo,
            config: dict[str, Any],
            uc_client: UnityCatalogClient,
        ) -> None:
            nonlocal max_seen, current
            current += 1
            max_seen = max(max_seen, current)
            await asyncio.sleep(0.05)
            current -= 1

        registry = KindRegistry()
        registry.register("fake", _slow_fake)

        # Seed 3 jobs.
        job_ids: list[int] = []
        for i in range(3):
            jid, _ = _seed_job_with_tasks(
                dag_factory,
                [{"name": f"t{i}", "config": {"_name": f"t{i}"}}],
            )
            job_ids.append(jid)

        # Run all three concurrently, all guarded by the same 1-permit
        # global semaphore. If the cap is honoured, max_seen stays at 1.
        global_sem = asyncio.Semaphore(1)
        per_job: dict[int, asyncio.Semaphore] = {}

        async def _run(jid: int) -> Any:
            return await scheduler_service._execute_with_semaphores(
                dag_factory,
                _settings(),
                registry,
                jid,
                "manual",
                global_sem,
                per_job,
            )

        await asyncio.gather(*[_run(jid) for jid in job_ids])
        assert max_seen == 1, f"expected serialized runs; saw {max_seen} parallel"


class TestContextVars:
    async def test_contextvars_set_and_reset(
        self,
        dag_factory: Any,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setattr(
            UnityCatalogClient,
            "for_principal",
            classmethod(lambda cls, s, p: MagicMock(spec=UnityCatalogClient)),
        )

        seen_job_ids: list[str | None] = []
        seen_task_ids: list[str | None] = []

        async def _capture(
            job_run_id: int,
            user_info: UserInfo,
            config: dict[str, Any],
            uc_client: UnityCatalogClient,
        ) -> None:
            del job_run_id, user_info, config, uc_client
            seen_job_ids.append(job_run_id_var.get())
            seen_task_ids.append(task_id_var.get())
            logging.getLogger("pointlessql.test").info("task body running")

        registry = KindRegistry()
        registry.register("fake", _capture)

        job_id, names = _seed_job_with_tasks(
            dag_factory, [{"name": "only", "config": {}}]
        )

        caplog.set_level(logging.INFO, logger="pointlessql.test")
        run = await execute_run(
            dag_factory, _settings(), registry, job_id, "manual"
        )
        assert run.status == "succeeded"
        # Both contextvars were set during executor invocation.
        assert seen_job_ids == [str(run.id)]
        assert seen_task_ids == [str(names["only"])]
        # Ctx vars reset after execute_run returns.
        assert job_run_id_var.get() is None
        assert task_id_var.get() is None
        # Caplog saw the task-body record with both correlation ids.
        matching = [
            r
            for r in caplog.records
            if r.name == "pointlessql.test"
            and getattr(r, "job_run_id", None) == str(run.id)
            and getattr(r, "task_id", None) == str(names["only"])
        ]
        assert matching, "expected task body log stamped with correlation ids"


class TestLogJobWriter:
    def test_log_job_writes_row(self, dag_factory: Any) -> None:
        # Seed a job + run to satisfy the FK.
        with dag_factory() as session:
            user = session.scalars(select(User)).first()
            assert user is not None
            now = datetime.datetime(2026, 4, 1, tzinfo=datetime.UTC)
            job = Job(
                name="j", cron_expr="* * * * *", run_as_user_id=user.id,
                kind="fake", config="{}", is_paused=False,
                max_parallel_runs=1, created_at=now, updated_at=now,
            )
            session.add(job)
            session.flush()
            jr = JobRun(
                job_id=job.id, started_at=now, status="running",
                trigger="manual",
            )
            session.add(jr)
            session.commit()
            run_id = jr.id

        log_job(dag_factory, run_id, None, "INFO", "hello")
        with dag_factory() as session:
            rows = list(session.scalars(select(JobLog)).all())
        assert len(rows) == 1
        assert rows[0].level == "INFO"
        assert rows[0].message == "hello"
        assert rows[0].task_id is None


class TestRouteDagCreation:
    async def test_cycle_at_create_time_raises_validation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pointlessql.api.main import app

        monkeypatch.setattr(
            UnityCatalogClient,
            "for_principal",
            classmethod(lambda cls, s, p: MagicMock(spec=UnityCatalogClient)),
        )
        import httpx

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies=app.state._test_auth_cookie,
        ) as client:
            resp = await client.post(
                "/api/jobs",
                json={
                    "name": "cyclic",
                    "cron_expr": "* * * * *",
                    "tasks": [
                        {
                            "name": "a",
                            "kind": "python",
                            "config": {"entry_point": "x"},
                            "depends_on": ["b"],
                        },
                        {
                            "name": "b",
                            "kind": "python",
                            "config": {"entry_point": "x"},
                            "depends_on": ["a"],
                        },
                    ],
                },
            )
        assert resp.status_code == 422
        assert "cycle" in resp.text.lower()
