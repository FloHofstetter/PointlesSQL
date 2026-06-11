"""Jobs v2: run_if conditions, for_each, repair runs, event triggers, notify_on."""

from __future__ import annotations

import datetime
import itertools
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import deltalake
import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from pointlessql.config import Settings
from pointlessql.models import (
    Base,
    Job,
    JobTask,
    TaskRun,
    User,
    UserNotification,
)
from pointlessql.services.scheduler import (
    KindRegistry,
    evaluate_event_trigger,
    execute_run,
    tick_once,
)
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo

_SEED_COUNTER = itertools.count()
_NOW = datetime.datetime(2026, 6, 1, tzinfo=datetime.UTC)


@pytest.fixture
def factory() -> Any:
    """In-memory session factory seeded with one runner user."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        session.add(
            User(
                email="runner@test.com",
                display_name="Runner",
                password_hash="x",
                is_admin=False,
                created_at=_NOW,
            )
        )
        session.commit()
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(autouse=True)
def _stub_uc(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Stub the principal client so no HTTP leaves the test."""
    client = MagicMock(spec=UnityCatalogClient)
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: client),  # type: ignore[arg-type]
    )
    return client


def _settings() -> Settings:
    return Settings(
        jupyter={"enabled": False},
        scheduler={"enabled": False},
        soyuz={"catalog_url": "http://127.0.0.1:8080"},
    )


def _seed_job(
    factory: Any,
    tasks_spec: list[dict[str, Any]] | None = None,
    **job_kwargs: Any,
) -> tuple[int, dict[str, int]]:
    """Create a job (+ optional DAG tasks); returns (job_id, name→task_id)."""
    with factory() as session:
        user = session.scalars(select(User)).first()
        assert user is not None
        job = Job(
            name=job_kwargs.pop("name", f"v2-{next(_SEED_COUNTER)}"),
            cron_expr=job_kwargs.pop("cron_expr", "* * * * *"),
            run_as_user_id=user.id,
            kind=job_kwargs.pop("kind", "fake"),
            config=job_kwargs.pop("config", "{}"),
            is_paused=False,
            max_parallel_runs=1,
            created_at=_NOW,
            updated_at=_NOW,
            **job_kwargs,
        )
        session.add(job)
        session.flush()
        name_to_id: dict[str, int] = {}
        for spec in tasks_spec or []:
            jt = JobTask(
                job_id=job.id,
                name=spec["name"],
                order=0,
                kind=spec.get("kind", "fake"),
                config=json.dumps(spec.get("config") or {}),
                depends_on="[]",
                max_retries=int(spec.get("max_retries", 0)),
                retry_backoff_seconds=0,
                run_if=spec.get("run_if", "all_success"),
                for_each_json=(
                    json.dumps(spec["for_each"]) if spec.get("for_each") is not None else None
                ),
            )
            session.add(jt)
            session.flush()
            name_to_id[spec["name"]] = jt.id
        for spec in tasks_spec or []:
            resolved = [name_to_id[n] for n in spec.get("depends_on") or []]
            row = session.get(JobTask, name_to_id[spec["name"]])
            assert row is not None
            row.depends_on = json.dumps(resolved)
        session.commit()
        return job.id, name_to_id


class _Registry(KindRegistry):
    """Registry recording (task_name, item) invocations."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, Any]] = []
        self.fail_names: set[str] = set()

        async def _fake(
            job_run_id: int,
            user_info: UserInfo,
            config: dict[str, Any],
            uc_client: UnityCatalogClient,
        ) -> None:
            name = str(config.get("_name", ""))
            self.calls.append((name, config.get("item")))
            if name in self.fail_names:
                raise RuntimeError(f"{name} fails")

        self.register("fake", _fake)

    def names(self) -> list[str]:
        return [n for n, _ in self.calls]


def _task_statuses(factory: Any, run_id: int, name_to_id: dict[str, int]) -> dict[str, str]:
    id_to_name = {v: k for k, v in name_to_id.items()}
    with factory() as session:
        rows = list(session.scalars(select(TaskRun).where(TaskRun.job_run_id == run_id)).all())
        return {id_to_name[r.task_id]: r.status for r in rows}


# ---------------------------------------------------------------------------
# run_if
# ---------------------------------------------------------------------------


async def test_error_handler_runs_only_on_upstream_failure(factory: Any) -> None:
    registry = _Registry()
    registry.fail_names.add("etl")
    job_id, ids = _seed_job(
        factory,
        [
            {"name": "etl", "config": {"_name": "etl"}},
            {
                "name": "alert",
                "config": {"_name": "alert"},
                "depends_on": ["etl"],
                "run_if": "at_least_one_failed",
            },
        ],
    )
    run = await execute_run(factory, _settings(), registry, job_id, "manual")
    assert run.status == "failed"  # the etl failure still fails the run
    assert "alert" in registry.names()
    assert _task_statuses(factory, run.id, ids) == {"etl": "failed", "alert": "succeeded"}


async def test_error_handler_excluded_when_all_succeed(factory: Any) -> None:
    registry = _Registry()
    job_id, ids = _seed_job(
        factory,
        [
            {"name": "etl", "config": {"_name": "etl"}},
            {
                "name": "alert",
                "config": {"_name": "alert"},
                "depends_on": ["etl"],
                "run_if": "at_least_one_failed",
            },
        ],
    )
    run = await execute_run(factory, _settings(), registry, job_id, "manual")
    assert run.status == "succeeded"  # an unmet handler never fails the run
    assert "alert" not in registry.names()
    assert _task_statuses(factory, run.id, ids)["alert"] == "excluded"


async def test_all_done_runs_despite_upstream_failure(factory: Any) -> None:
    registry = _Registry()
    registry.fail_names.add("etl")
    job_id, ids = _seed_job(
        factory,
        [
            {"name": "etl", "config": {"_name": "etl"}},
            {
                "name": "cleanup",
                "config": {"_name": "cleanup"},
                "depends_on": ["etl"],
                "run_if": "all_done",
            },
        ],
    )
    run = await execute_run(factory, _settings(), registry, job_id, "manual")
    assert run.status == "failed"
    assert _task_statuses(factory, run.id, ids) == {"etl": "failed", "cleanup": "succeeded"}


async def test_exclusion_propagates_benignly(factory: Any) -> None:
    """Downstream of an excluded handler is excluded too, run stays green."""
    registry = _Registry()
    job_id, ids = _seed_job(
        factory,
        [
            {"name": "etl", "config": {"_name": "etl"}},
            {
                "name": "handler",
                "config": {"_name": "handler"},
                "depends_on": ["etl"],
                "run_if": "at_least_one_failed",
            },
            {"name": "post", "config": {"_name": "post"}, "depends_on": ["handler"]},
        ],
    )
    run = await execute_run(factory, _settings(), registry, job_id, "manual")
    assert run.status == "succeeded"
    statuses = _task_statuses(factory, run.id, ids)
    assert statuses == {"etl": "succeeded", "handler": "excluded", "post": "excluded"}


# ---------------------------------------------------------------------------
# for_each
# ---------------------------------------------------------------------------


async def test_for_each_invokes_executor_per_item(factory: Any) -> None:
    registry = _Registry()
    job_id, ids = _seed_job(
        factory,
        [
            {
                "name": "fan",
                "config": {"_name": "fan"},
                "for_each": ["a", "b", "c"],
            }
        ],
    )
    run = await execute_run(factory, _settings(), registry, job_id, "manual")
    assert run.status == "succeeded"
    assert registry.calls == [("fan", "a"), ("fan", "b"), ("fan", "c")]
    assert _task_statuses(factory, run.id, ids) == {"fan": "succeeded"}


async def test_for_each_invalid_json_fails_task(factory: Any) -> None:
    registry = _Registry()
    job_id, ids = _seed_job(factory, [{"name": "fan", "config": {"_name": "fan"}}])
    with factory() as session:
        row = session.get(JobTask, ids["fan"])
        assert row is not None
        row.for_each_json = "{not json"
        session.commit()
    run = await execute_run(factory, _settings(), registry, job_id, "manual")
    assert run.status == "failed"
    assert registry.calls == []


# ---------------------------------------------------------------------------
# repair runs
# ---------------------------------------------------------------------------


async def test_repair_run_reuses_previous_successes(factory: Any) -> None:
    registry = _Registry()
    registry.fail_names.add("load")
    job_id, ids = _seed_job(
        factory,
        [
            {"name": "extract", "config": {"_name": "extract"}},
            {"name": "load", "config": {"_name": "load"}, "depends_on": ["extract"]},
            {"name": "report", "config": {"_name": "report"}, "depends_on": ["load"]},
        ],
    )
    failed = await execute_run(factory, _settings(), registry, job_id, "manual")
    assert failed.status == "failed"
    assert _task_statuses(factory, failed.id, ids) == {
        "extract": "succeeded",
        "load": "failed",
        "report": "skipped",
    }

    registry.fail_names.clear()
    registry.calls.clear()
    repair = await execute_run(
        factory, _settings(), registry, job_id, "repair", repair_of_run_id=failed.id
    )
    assert repair.status == "succeeded"
    assert repair.trigger == "repair"
    assert repair.repair_of_run_id == failed.id
    # extract was NOT re-executed, load + report were.
    assert registry.names() == ["load", "report"]
    assert _task_statuses(factory, repair.id, ids) == {
        "extract": "succeeded",
        "load": "succeeded",
        "report": "succeeded",
    }


# ---------------------------------------------------------------------------
# event triggers
# ---------------------------------------------------------------------------


async def test_file_arrival_baseline_then_fire(factory: Any, tmp_path: Path) -> None:
    job_id, _ = _seed_job(
        factory,
        None,
        cron_expr="@event",
        trigger_kind="file_arrival",
        trigger_config=json.dumps({"path": str(tmp_path / "*.csv")}),
    )
    with factory() as session:
        job = session.get(Job, job_id)
        assert job is not None
        session.expunge(job)

    # first evaluation: baseline only, no fire.
    assert await evaluate_event_trigger(factory, _settings(), job, _NOW) is False
    with factory() as session:
        refreshed = session.get(Job, job_id)
        assert refreshed is not None
        assert refreshed.trigger_cursor is not None
        session.expunge(refreshed)

    # unchanged: no fire.
    assert await evaluate_event_trigger(factory, _settings(), refreshed, _NOW) is False

    # new file: fire once, then quiesce.
    (tmp_path / "orders.csv").write_text("id\n1\n")
    assert await evaluate_event_trigger(factory, _settings(), refreshed, _NOW) is True
    with factory() as session:
        again = session.get(Job, job_id)
        assert again is not None
        session.expunge(again)
    assert await evaluate_event_trigger(factory, _settings(), again, _NOW) is False


async def test_table_update_fires_on_version_bump(
    factory: Any, tmp_path: Path, _stub_uc: MagicMock
) -> None:
    from unittest.mock import AsyncMock

    loc = str(tmp_path / "orders")
    deltalake.write_deltalake(loc, pd.DataFrame({"id": [1]}))
    _stub_uc.get_table = AsyncMock(return_value={"storage_location": loc})

    job_id, _ = _seed_job(
        factory,
        None,
        cron_expr="@event",
        trigger_kind="table_update",
        trigger_config=json.dumps({"table": "main.demo.orders"}),
    )

    def load(jid: int) -> Job:
        with factory() as session:
            row = session.get(Job, jid)
            assert row is not None
            session.expunge(row)
            return row

    assert await evaluate_event_trigger(factory, _settings(), load(job_id), _NOW) is False
    assert await evaluate_event_trigger(factory, _settings(), load(job_id), _NOW) is False
    deltalake.write_deltalake(loc, pd.DataFrame({"id": [2]}), mode="append")
    assert await evaluate_event_trigger(factory, _settings(), load(job_id), _NOW) is True
    assert await evaluate_event_trigger(factory, _settings(), load(job_id), _NOW) is False


async def test_tick_launches_event_job_with_event_trigger(factory: Any, tmp_path: Path) -> None:
    registry = _Registry()
    job_id, _ = _seed_job(
        factory,
        None,
        kind="fake",
        config=json.dumps({"_name": "evt"}),
        cron_expr="@event",
        trigger_kind="file_arrival",
        trigger_config=json.dumps({"path": str(tmp_path / "*.json")}),
    )
    # baseline tick: nothing fires.
    runs = await tick_once(factory, _settings(), registry, _NOW)
    assert runs == []
    (tmp_path / "evt.json").write_text("{}")
    runs = await tick_once(factory, _settings(), registry, _NOW)
    assert len(runs) == 1
    assert runs[0].trigger == "event"
    assert runs[0].status == "succeeded"
    assert registry.names() == ["evt"]
    # cron jobs are untouched by the event evaluation: the event job
    # does not refire without a change.
    assert await tick_once(factory, _settings(), registry, _NOW) == []


# ---------------------------------------------------------------------------
# notify_on
# ---------------------------------------------------------------------------


async def test_notify_on_failure_creates_notification(factory: Any) -> None:
    registry = _Registry()
    registry.fail_names.add("boom")
    job_id, _ = _seed_job(
        factory,
        None,
        kind="fake",
        config=json.dumps({"_name": "boom"}),
        notify_on=json.dumps(["failure"]),
    )
    run = await execute_run(factory, _settings(), registry, job_id, "manual")
    assert run.status == "failed"
    with factory() as session:
        notes = list(session.scalars(select(UserNotification)).all())
        assert len(notes) == 1
        assert notes[0].event_type == "pointlessql.job.run_failed"
        assert "failed" in notes[0].summary_md


async def test_no_notification_without_opt_in(factory: Any) -> None:
    registry = _Registry()
    registry.fail_names.add("boom")
    job_id, _ = _seed_job(factory, None, kind="fake", config=json.dumps({"_name": "boom"}))
    run = await execute_run(factory, _settings(), registry, job_id, "manual")
    assert run.status == "failed"
    with factory() as session:
        assert list(session.scalars(select(UserNotification)).all()) == []


async def test_legacy_dag_behaviour_unchanged(factory: Any) -> None:
    """Default run_if reproduces the historical skip-on-upstream-failure."""
    registry = _Registry()
    registry.fail_names.add("a")
    job_id, ids = _seed_job(
        factory,
        [
            {"name": "a", "config": {"_name": "a"}},
            {"name": "b", "config": {"_name": "b"}, "depends_on": ["a"]},
        ],
    )
    run = await execute_run(factory, _settings(), registry, job_id, "manual")
    assert run.status == "failed"
    assert _task_statuses(factory, run.id, ids) == {"a": "failed", "b": "skipped"}
