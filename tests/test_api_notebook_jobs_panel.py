"""Tests for ``GET /api/notebooks/jobs`` (Phase 67.4 panel endpoint).

The editor surfaces scheduled jobs + recent runs for the open
notebook via a single side-panel. This endpoint joins
:class:`NotebookJobLink` to :class:`Job` and the most-recent
:class:`JobRun` rows so the panel renders without a JSON-LIKE scan
on ``Job.config``.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import Job, JobRun, NotebookJobLink, User


@pytest.fixture
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "notebooks"
    root.mkdir()
    monkeypatch.setattr(app.state.settings.jupyter, "notebooks_dir", root)
    return root


def _seed_job_with_link(path: str, *, name: str = "nb-job") -> int:
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        user = session.scalars(select(User).where(User.email == "test@test.com")).first()
        assert user is not None
        job = Job(
            name=name,
            cron_expr="0 5 * * *",
            run_as_user_id=user.id,
            kind="papermill",
            config=f'{{"notebook_path": "{path}", "parameters": {{}}}}',
            is_paused=False,
            max_parallel_runs=1,
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        link = NotebookJobLink(
            workspace_id=1,
            notebook_path=path,
            job_id=int(job.id),
            created_at=now,
        )
        session.add(link)
        session.commit()
        return int(job.id)


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


async def test_empty_when_no_jobs(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """No links → empty lists for both."""
    resp = await admin_client.get("/api/notebooks/jobs", params={"path": "nojobs.py"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"scheduled_jobs": [], "recent_runs": []}


async def test_lists_scheduled_jobs(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """A linked job appears in scheduled_jobs."""
    _seed_job_with_link("demo.py", name="daily-demo")
    resp = await admin_client.get("/api/notebooks/jobs", params={"path": "demo.py"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["scheduled_jobs"]) == 1
    job = body["scheduled_jobs"][0]
    assert job["name"] == "daily-demo"
    assert job["kind"] == "papermill"
    assert job["cron_expr"] == "0 5 * * *"


async def test_lists_recent_runs(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Runs from any linked job appear newest-first."""
    job_id = _seed_job_with_link("etl.py", name="etl-daily")
    run_a = _seed_run(job_id, status="succeeded")
    run_b = _seed_run(job_id, status="failed")
    resp = await admin_client.get("/api/notebooks/jobs", params={"path": "etl.py"})
    assert resp.status_code == 200, resp.text
    runs = resp.json()["recent_runs"]
    ids = [r["id"] for r in runs]
    assert run_a in ids
    assert run_b in ids
    # Newest first — see test_jobs_routes::test_list_job_runs comment.
    assert ids.index(run_b) <= ids.index(run_a)


async def test_other_notebook_excluded(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """A different notebook path returns nothing."""
    _seed_job_with_link("a.py")
    resp = await admin_client.get("/api/notebooks/jobs", params={"path": "b.py"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["scheduled_jobs"] == []
    assert resp.json()["recent_runs"] == []


async def test_limit_honored(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """``?limit=1`` trims recent_runs to one row."""
    job_id = _seed_job_with_link("multi.py")
    _seed_run(job_id)
    _seed_run(job_id)
    resp = await admin_client.get(
        "/api/notebooks/jobs", params={"path": "multi.py", "limit": 1}
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["recent_runs"]) == 1


async def test_non_admin_accessible(
    workspace_dir: Path, non_admin_client: httpx.AsyncClient
) -> None:
    """Phase 70: any authenticated user can read the jobs panel."""
    resp = await non_admin_client.get(
        "/api/notebooks/jobs", params={"path": "x.py"}
    )
    assert resp.status_code == 200


async def test_link_written_via_post_jobs(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """POST /api/jobs with kind=papermill writes a NotebookJobLink row."""
    body = {
        "name": "scheduled-from-test",
        "cron_expr": "0 5 * * *",
        "kind": "papermill",
        "config": {"notebook_path": "via_post.py", "parameters": {}},
    }
    resp = await admin_client.post("/api/jobs", json=body)
    assert resp.status_code == 200, resp.text
    factory = app.state.session_factory
    with factory() as session:
        link = session.scalars(
            select(NotebookJobLink).where(NotebookJobLink.notebook_path == "via_post.py")
        ).first()
        assert link is not None
        assert link.job_id == resp.json()["id"]
