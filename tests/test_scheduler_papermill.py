"""Tests for the Sprint 24 papermill executor and Sprint 26 run routes."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.exceptions import EngineError, ValidationError
from pointlessql.models import Job, JobRun, User
from pointlessql.services.scheduler import (
    _papermill_executor,
    build_default_registry,
    resolve_notebook_path,
)
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo


@pytest.fixture
def notebooks_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the executor at an isolated notebooks directory and seed a stub."""
    root = tmp_path / "notebooks"
    root.mkdir()
    (root / "smoke.ipynb").write_text("{}\n")
    monkeypatch.setenv("POINTLESSQL_JUPYTER_NOTEBOOKS_DIR", str(root))
    return root


@pytest.fixture
def user_info() -> UserInfo:
    return UserInfo(
        id=1,
        email="runner@test.com",
        display_name="Runner",
        is_admin=False,
    )


@pytest.fixture
def uc_client() -> UnityCatalogClient:
    return MagicMock(spec=UnityCatalogClient)


def test_registry_includes_papermill() -> None:
    """``build_default_registry`` exposes ``papermill`` alongside the old kinds."""
    registry = build_default_registry()
    assert registry.get("papermill") is _papermill_executor
    assert registry.get("pg_sync") is not None
    assert registry.get("python") is not None


def test_resolve_rejects_absolute_path(tmp_path: Path) -> None:
    """Absolute paths never escape the notebooks directory."""
    with pytest.raises(ValidationError, match="must be relative"):
        resolve_notebook_path(tmp_path, "/etc/passwd")


def test_resolve_rejects_traversal(tmp_path: Path) -> None:
    """``..``-relative paths that escape the root are rejected."""
    root = tmp_path / "notebooks"
    root.mkdir()
    with pytest.raises(ValidationError, match="escapes the notebooks directory"):
        resolve_notebook_path(root, "../outside.ipynb")


def test_resolve_rejects_missing_file(tmp_path: Path) -> None:
    """Non-existent notebook inside the root is a validation error."""
    root = tmp_path / "notebooks"
    root.mkdir()
    with pytest.raises(ValidationError, match="notebook not found"):
        resolve_notebook_path(root, "does_not_exist.ipynb")


async def test_missing_notebook_path_raises(
    user_info: UserInfo,
    uc_client: UnityCatalogClient,
    notebooks_dir: Path,
) -> None:
    """Config without ``notebook_path`` raises ``ValidationError`` at entry."""
    with pytest.raises(ValidationError, match="notebook_path"):
        await _papermill_executor(1, user_info, {}, uc_client)


async def test_non_dict_parameters_raises(
    user_info: UserInfo,
    uc_client: UnityCatalogClient,
    notebooks_dir: Path,
) -> None:
    """``parameters`` must be an object."""
    with pytest.raises(ValidationError, match="parameters"):
        await _papermill_executor(
            1,
            user_info,
            {"notebook_path": "smoke.ipynb", "parameters": ["not", "a", "dict"]},
            uc_client,
        )


async def test_invalid_timeout_raises(
    user_info: UserInfo,
    uc_client: UnityCatalogClient,
    notebooks_dir: Path,
) -> None:
    """Non-positive ``timeout_seconds`` is a validation error."""
    with pytest.raises(ValidationError, match="timeout_seconds"):
        await _papermill_executor(
            1,
            user_info,
            {"notebook_path": "smoke.ipynb", "timeout_seconds": 0},
            uc_client,
        )


async def test_executor_writes_output_and_forwards_principal(
    user_info: UserInfo,
    uc_client: UnityCatalogClient,
    notebooks_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stubbed papermill touches the output path and sees ``POINTLESSQL_PRINCIPAL``."""
    import os

    captured: dict[str, Any] = {}

    def fake_execute(
        input_path: str,
        output_path: str,
        parameters: dict[str, Any],
        kernel_name: str,
        cwd: str,
        execution_timeout: int,
        progress_bar: bool,
    ) -> None:
        captured["input_path"] = input_path
        captured["output_path"] = output_path
        captured["parameters"] = parameters
        captured["cwd"] = cwd
        captured["execution_timeout"] = execution_timeout
        captured["principal"] = os.environ.get("POINTLESSQL_PRINCIPAL")
        Path(output_path).write_text("{}\n")

    fake_module = MagicMock()
    fake_module.execute_notebook = fake_execute
    monkeypatch.setitem(__import__("sys").modules, "papermill", fake_module)

    fake_exc_module = MagicMock()

    class _FakeErr(Exception):
        pass

    fake_exc_module.PapermillExecutionError = _FakeErr
    monkeypatch.setitem(__import__("sys").modules, "papermill.exceptions", fake_exc_module)

    await _papermill_executor(
        42,
        user_info,
        {"notebook_path": "smoke.ipynb", "parameters": {"date": "2026-04-17"}},
        uc_client,
    )

    assert captured["parameters"] == {"date": "2026-04-17"}
    assert captured["principal"] == "runner@test.com"
    assert captured["output_path"].endswith("/runs/42.ipynb")
    assert captured["input_path"].endswith("/smoke.ipynb")
    # Env var is restored after the run.
    assert "POINTLESSQL_PRINCIPAL" not in os.environ or (
        os.environ.get("POINTLESSQL_PRINCIPAL") != "runner@test.com"
    )
    assert (notebooks_dir / "runs" / "42.ipynb").is_file()


async def test_executor_papermill_execution_error_becomes_engine_error(
    user_info: UserInfo,
    uc_client: UnityCatalogClient,
    notebooks_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``PapermillExecutionError`` from a failing cell is re-raised as ``EngineError``."""

    class _FakeErr(Exception):
        def __init__(self) -> None:
            self.exec_count = 3
            self.ename = "ZeroDivisionError"
            self.evalue = "division by zero"

    fake_exc_module = MagicMock()
    fake_exc_module.PapermillExecutionError = _FakeErr
    monkeypatch.setitem(__import__("sys").modules, "papermill.exceptions", fake_exc_module)

    def failing_execute(**_: Any) -> None:
        raise _FakeErr()

    fake_module = MagicMock()
    fake_module.execute_notebook = failing_execute
    monkeypatch.setitem(__import__("sys").modules, "papermill", fake_module)

    with pytest.raises(EngineError, match="cell 3.*ZeroDivisionError"):
        await _papermill_executor(
            99,
            user_info,
            {"notebook_path": "smoke.ipynb"},
            uc_client,
        )


# -- Sprint 26: /jobs/{id}/runs/{rid}/notebook + /download routes --


def _minimal_ipynb_source() -> str:
    """Return a valid ipynb-4.5 document as a JSON string."""
    return json.dumps(
        {
            "cells": [
                {
                    "cell_type": "code",
                    "source": "print('sprint-26-route-smoke')",
                    "outputs": [],
                    "execution_count": 1,
                    "metadata": {},
                }
            ],
            "metadata": {
                "kernelspec": {"name": "python3", "display_name": "Python 3"},
                "language_info": {"name": "python"},
            },
            "nbformat": 4,
            "nbformat_minor": 5,
        }
    )


def _seed_papermill_job_and_run(
    *, kind: str = "papermill", owner_email: str = "test@test.com"
) -> tuple[int, int]:
    """Seed one :class:`Job` (optionally non-papermill) plus a succeeded run.

    Returns ``(job_id, run_id)`` so the caller can hit the new routes.
    """
    factory = app.state.session_factory
    with factory() as session:
        owner = session.scalars(select(User).where(User.email == owner_email)).first()
        assert owner is not None
        now = datetime.datetime.now(datetime.UTC)
        job = Job(
            name=f"sprint26-{kind}-{owner.id}-{now.timestamp()}",
            cron_expr="* * * * *",
            run_as_user_id=owner.id,
            kind=kind,
            config=json.dumps({"notebook_path": "ignored.ipynb"}),
            is_paused=False,
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        session.commit()
        run = JobRun(
            job_id=job.id,
            started_at=now,
            finished_at=now + datetime.timedelta(seconds=1),
            status="succeeded",
            trigger="manual",
        )
        session.add(run)
        session.commit()
        return job.id, run.id


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


@pytest.fixture
def run_output_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``settings.jupyter.notebooks_dir`` at an isolated workspace with a ``runs/``."""
    nb_root = tmp_path / "notebooks"
    runs = nb_root / "runs"
    runs.mkdir(parents=True)
    monkeypatch.setattr(app.state.settings.jupyter, "notebooks_dir", nb_root)
    return runs


async def test_render_route_serves_nbconvert_html(run_output_dir: Path) -> None:
    """Happy path: owner requests the inline render and gets the cell source back."""
    job_id, run_id = _seed_papermill_job_and_run()
    (run_output_dir / f"{run_id}.ipynb").write_text(_minimal_ipynb_source())

    async with _admin_client() as client:
        resp = await client.get(f"/jobs/{job_id}/runs/{run_id}/notebook")

    assert resp.status_code == 200
    assert "sprint-26-route-smoke" in resp.text
    assert (run_output_dir / f"{run_id}.html").is_file()


async def test_render_route_missing_ipynb_404s(run_output_dir: Path) -> None:
    """A run with no output ipynb surfaces as 404 via CatalogNotFoundError."""
    job_id, run_id = _seed_papermill_job_and_run()

    async with _admin_client() as client:
        resp = await client.get(f"/jobs/{job_id}/runs/{run_id}/notebook")

    assert resp.status_code == 404


async def test_render_route_cross_job_run_id_404s(run_output_dir: Path) -> None:
    """A run_id from a different job cannot be rendered under this job."""
    job_a, run_a = _seed_papermill_job_and_run()
    _job_b, run_b = _seed_papermill_job_and_run()
    (run_output_dir / f"{run_b}.ipynb").write_text(_minimal_ipynb_source())

    async with _admin_client() as client:
        resp = await client.get(f"/jobs/{job_a}/runs/{run_b}/notebook")

    assert resp.status_code == 404


async def test_render_route_rejects_non_papermill_job(run_output_dir: Path) -> None:
    """Only papermill jobs expose the render route; other kinds 404."""
    job_id, run_id = _seed_papermill_job_and_run(kind="python")
    (run_output_dir / f"{run_id}.ipynb").write_text(_minimal_ipynb_source())

    async with _admin_client() as client:
        resp = await client.get(f"/jobs/{job_id}/runs/{run_id}/notebook")

    assert resp.status_code == 404


async def test_render_route_non_owner_404s(run_output_dir: Path) -> None:
    """Non-admin non-owner cannot see another user's job output."""
    job_id, run_id = _seed_papermill_job_and_run(owner_email="test@test.com")
    (run_output_dir / f"{run_id}.ipynb").write_text(_minimal_ipynb_source())

    async with _non_admin_client() as client:
        resp = await client.get(f"/jobs/{job_id}/runs/{run_id}/notebook")

    assert resp.status_code == 404


async def test_download_ipynb_serves_raw_file(run_output_dir: Path) -> None:
    """``?format=ipynb`` returns the raw notebook bytes with a download filename."""
    job_id, run_id = _seed_papermill_job_and_run()
    (run_output_dir / f"{run_id}.ipynb").write_text(_minimal_ipynb_source())

    async with _admin_client() as client:
        resp = await client.get(f"/jobs/{job_id}/runs/{run_id}/notebook/download?format=ipynb")

    assert resp.status_code == 200
    assert "sprint-26-route-smoke" in resp.text
    assert f"job{job_id}_run{run_id}.ipynb" in resp.headers.get("content-disposition", "")


async def test_download_html_triggers_render(run_output_dir: Path) -> None:
    """``?format=html`` writes the sidecar on first hit and serves it."""
    job_id, run_id = _seed_papermill_job_and_run()
    (run_output_dir / f"{run_id}.ipynb").write_text(_minimal_ipynb_source())

    async with _admin_client() as client:
        resp = await client.get(f"/jobs/{job_id}/runs/{run_id}/notebook/download?format=html")

    assert resp.status_code == 200
    assert (run_output_dir / f"{run_id}.html").is_file()
    assert "sprint-26-route-smoke" in resp.text
