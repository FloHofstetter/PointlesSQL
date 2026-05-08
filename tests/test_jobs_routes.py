"""Sprint 57.6 — coverage extension for jobs_routes.py.

The existing ``tests/test_scheduler.py::TestJobRoutes`` already
covers list / create / run / pause / unpause and the two HTML
pages.  This file adds the previously-untested DAG / log /
papermill-output endpoints (5 routes).
"""

from __future__ import annotations

import datetime

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import Job, JobLog, JobRun, JobTask, TaskRun, User


def _seed_job(*, owner_email: str = "test@test.com", name: str = "job-a") -> int:
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        user = session.scalars(select(User).where(User.email == owner_email)).first()
        assert user is not None
        job = Job(
            name=name,
            cron_expr="* * * * *",
            run_as_user_id=user.id,
            kind="python",
            config="{}",
            is_paused=False,
            max_parallel_runs=1,
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        return int(job.id)


def _seed_task(job_id: int, name: str = "t1", order: int = 0) -> int:
    factory = app.state.session_factory
    with factory() as session:
        task = JobTask(
            job_id=job_id,
            name=name,
            order=order,
            kind="python",
            config="{}",
            depends_on="[]",
        )
        session.add(task)
        session.commit()
        session.refresh(task)
        return int(task.id)


def _seed_run(job_id: int, status: str = "succeeded") -> int:
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        run = JobRun(
            job_id=job_id,
            started_at=now,
            finished_at=now + datetime.timedelta(seconds=1),
            status=status,
            trigger="manual",
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        return int(run.id)


def _seed_task_run(job_run_id: int, task_id: int, status: str = "succeeded") -> int:
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        tr = TaskRun(
            job_run_id=job_run_id,
            task_id=task_id,
            started_at=now,
            finished_at=now + datetime.timedelta(seconds=1),
            status=status,
        )
        session.add(tr)
        session.commit()
        session.refresh(tr)
        return int(tr.id)


def _seed_log(job_run_id: int, task_id: int | None = None, message: str = "hi") -> None:
    factory = app.state.session_factory
    with factory() as session:
        log = JobLog(
            job_run_id=job_run_id,
            task_id=task_id,
            ts=datetime.datetime.now(datetime.UTC),
            level="INFO",
            message=message,
        )
        session.add(log)
        session.commit()


@pytest.fixture(autouse=True)
def _wipe_jobs() -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.query(JobLog).delete()
        session.query(TaskRun).delete()
        session.query(JobRun).delete()
        session.query(JobTask).delete()
        session.query(Job).delete()
        session.commit()


# -- /api/jobs/{job_id}/tasks --


async def test_list_job_tasks_empty(admin_client: httpx.AsyncClient) -> None:
    job_id = _seed_job()
    resp = await admin_client.get(f"/api/jobs/{job_id}/tasks")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_job_tasks_returns_dag(admin_client: httpx.AsyncClient) -> None:
    job_id = _seed_job()
    _seed_task(job_id, "t1", 0)
    _seed_task(job_id, "t2", 1)
    resp = await admin_client.get(f"/api/jobs/{job_id}/tasks")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert {row["name"] for row in body} == {"t1", "t2"}


async def test_list_job_tasks_unknown_job_404(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.get("/api/jobs/99999/tasks")
    assert resp.status_code == 404


async def test_list_job_tasks_non_owner_404(non_admin_client: httpx.AsyncClient) -> None:
    """load_job_or_404 collapses missing-vs-forbidden to 404."""
    job_id = _seed_job()  # admin-owned
    resp = await non_admin_client.get(f"/api/jobs/{job_id}/tasks")
    assert resp.status_code == 404


# -- /api/jobs/{job_id}/runs/{run_id}/tasks --


async def test_list_task_runs_returns_empty_for_fresh_run(
    admin_client: httpx.AsyncClient,
) -> None:
    job_id = _seed_job()
    run_id = _seed_run(job_id)
    resp = await admin_client.get(f"/api/jobs/{job_id}/runs/{run_id}/tasks")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_task_runs_returns_seeded_rows(
    admin_client: httpx.AsyncClient,
) -> None:
    job_id = _seed_job()
    task_id = _seed_task(job_id)
    run_id = _seed_run(job_id)
    _seed_task_run(run_id, task_id, status="succeeded")
    resp = await admin_client.get(f"/api/jobs/{job_id}/runs/{run_id}/tasks")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["status"] == "succeeded"


async def test_list_task_runs_unknown_job_404(
    admin_client: httpx.AsyncClient,
) -> None:
    resp = await admin_client.get("/api/jobs/99999/runs/1/tasks")
    assert resp.status_code == 404


# -- /api/jobs/{job_id}/runs/{run_id}/logs --


async def test_list_job_logs_returns_lines(admin_client: httpx.AsyncClient) -> None:
    job_id = _seed_job()
    run_id = _seed_run(job_id)
    _seed_log(run_id, message="hello")
    _seed_log(run_id, message="world")
    resp = await admin_client.get(f"/api/jobs/{job_id}/runs/{run_id}/logs")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    messages = {row.get("message") or row.get("line") for row in body}
    assert messages == {"hello", "world"}


async def test_list_job_logs_filters_by_task(
    admin_client: httpx.AsyncClient,
) -> None:
    job_id = _seed_job()
    task_id = _seed_task(job_id)
    run_id = _seed_run(job_id)
    _seed_log(run_id, task_id=task_id, message="task line")
    _seed_log(run_id, task_id=None, message="job line")
    resp = await admin_client.get(
        f"/api/jobs/{job_id}/runs/{run_id}/logs?task_id={task_id}"
    )
    assert resp.status_code == 200
    body = resp.json()
    messages = {row.get("message") or row.get("line") for row in body}
    assert messages == {"task line"}


async def test_list_job_logs_unknown_job_404(
    admin_client: httpx.AsyncClient,
) -> None:
    resp = await admin_client.get("/api/jobs/99999/runs/1/logs")
    assert resp.status_code == 404


# -- /jobs/{job_id}/runs/{run_id}/notebook (HTML, papermill output) --


async def test_notebook_view_404_when_no_papermill_output(
    admin_client: httpx.AsyncClient,
) -> None:
    """The notebook view requires a papermill output_path on the run row."""
    job_id = _seed_job()
    run_id = _seed_run(job_id)
    resp = await admin_client.get(f"/jobs/{job_id}/runs/{run_id}/notebook")
    assert resp.status_code == 404


async def test_notebook_download_404_when_no_papermill_output(
    admin_client: httpx.AsyncClient,
) -> None:
    job_id = _seed_job()
    run_id = _seed_run(job_id)
    resp = await admin_client.get(f"/jobs/{job_id}/runs/{run_id}/notebook/download")
    assert resp.status_code == 404


# -- /jobs/{job_id}/runs/{run_id}/compare (HTML, run-vs-run diff) --


async def test_compare_404_for_non_papermill_job(
    admin_client: httpx.AsyncClient,
) -> None:
    """compare requires a papermill job; python jobs reject before lookup."""
    job_id = _seed_job()  # kind=python by default
    run_id = _seed_run(job_id)
    other_run_id = _seed_run(job_id)
    resp = await admin_client.get(
        f"/jobs/{job_id}/runs/{run_id}/compare?to={other_run_id}"
    )
    assert resp.status_code == 404


async def test_compare_404_for_unknown_run(admin_client: httpx.AsyncClient) -> None:
    job_id = _seed_job()
    resp = await admin_client.get(f"/jobs/{job_id}/runs/99999/compare?to=12345")
    assert resp.status_code == 404
