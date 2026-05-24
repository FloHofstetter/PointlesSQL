"""Tests for ``POST /api/notebooks/run-once``.

The endpoint creates an ephemeral paused :class:`Job` row + fires a
manual papermill run, returning ``{job_id, job_run_id}`` so the
browser can poll until the run is terminal. These tests cover the
synchronous HTTP-layer behaviour: row creation, parameter pass-
through, validation gates. The integration test in
``test_notebook_run_once_integration.py`` exercises the full
papermill round-trip end-to-end and is marked
``@pytest.mark.integration``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from pointlessql.api.main import app

_PARAM_NOTEBOOK = (
    '# %% tags=["parameters"]\ncutoff_date = "2026-01-01"\n\n# %%\nprint(cutoff_date)\n'
)


@pytest.fixture
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "notebooks"
    root.mkdir()
    monkeypatch.setattr(app.state.settings.jupyter, "notebooks_dir", root)
    return root


async def _noop_execute_run(*_args: object, **_kwargs: object) -> None:
    """Stub for execute_run so the test never actually spawns papermill."""
    return None


async def test_run_once_creates_job_and_returns_ids(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Happy path: route returns job_id + job_run_id (or None during stub)."""
    (workspace_dir / "demo.py").write_text(_PARAM_NOTEBOOK)
    with patch(
        "pointlessql.api.notebooks_routes.jobs.scheduler_service.execute_run",
        new=_noop_execute_run,
    ):
        resp = await admin_client.post(
            "/api/notebooks/run-once",
            json={"path": "demo.py", "parameters": {"cutoff_date": "2026-05-10"}},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body["job_id"], int) and body["job_id"] > 0
    assert body["status"] == "started"
    # job_run_id may be None if execute_run was stubbed without writing a
    # JobRun row — the persistent Job row is the audit-trail anchor and is
    # what the browser keys on.
    assert "job_run_id" in body


async def test_run_once_persists_parameters_in_config(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    (workspace_dir / "demo.py").write_text(_PARAM_NOTEBOOK)
    overrides = {"cutoff_date": "2026-05-10", "window": 14}
    with patch(
        "pointlessql.api.notebooks_routes.jobs.scheduler_service.execute_run",
        new=_noop_execute_run,
    ):
        resp = await admin_client.post(
            "/api/notebooks/run-once",
            json={"path": "demo.py", "parameters": overrides},
        )
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]
    factory = app.state.session_factory
    from pointlessql.models import Job as JobModel

    with factory() as session:
        job = session.get(JobModel, job_id)
        assert job is not None
        assert job.kind == "papermill"
        assert job.is_paused is True
        cfg = json.loads(job.config)
        assert cfg["notebook_path"] == "demo.py"
        assert cfg["parameters"] == overrides


async def test_run_once_rejects_bad_path(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Traversal attempts must 422 before any job row is written."""
    resp = await admin_client.post(
        "/api/notebooks/run-once",
        json={"path": "../escape.py", "parameters": {}},
    )
    assert resp.status_code == 422


async def test_run_once_rejects_missing_path(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    resp = await admin_client.post(
        "/api/notebooks/run-once",
        json={"parameters": {}},
    )
    assert resp.status_code == 422


async def test_run_once_rejects_non_dict_parameters(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    (workspace_dir / "demo.py").write_text(_PARAM_NOTEBOOK)
    resp = await admin_client.post(
        "/api/notebooks/run-once",
        json={"path": "demo.py", "parameters": "not a dict"},
    )
    assert resp.status_code == 422


async def test_run_once_non_admin_accessible(
    workspace_dir: Path, non_admin_client: httpx.AsyncClient
) -> None:
    """any authenticated user can trigger a run-once."""
    (workspace_dir / "demo.py").write_text(_PARAM_NOTEBOOK)
    resp = await non_admin_client.post(
        "/api/notebooks/run-once",
        json={"path": "demo.py", "parameters": {}},
    )
    assert resp.status_code == 200


# Give event-loop cleanup a tick so the asyncio.create_task() spawned in
# the stub path can settle before pytest closes the loop.
@pytest.fixture(autouse=True)
async def _drain_event_loop() -> object:
    yield
    await asyncio.sleep(0)
