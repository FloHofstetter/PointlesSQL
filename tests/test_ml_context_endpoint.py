"""Tests for ``GET /api/runs/{id}/ml-context`` (Phase 21.2).

The endpoint joins three sources (agent_runs row + MLflow run +
soyuz model-versions) into one supervisor-only response. These
tests pin auth-gating + the not-found path; the soyuz scan +
MLflow lookup are exercised in the manual e2e flow because they
need both subprocesses live.
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Iterator

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import AgentRun


@pytest.fixture
def supervisor_run(tmp_path) -> Iterator[str]:  # noqa: ARG001
    """Insert a single agent_run row and yield its id."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    with factory() as session:
        run = AgentRun(
            id=run_id,
            principal="test@test.com",
            agent_id="hermes-test",
            notebook_path="notebooks/test.py",
            status="running",
            started_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(run)
        session.commit()
    yield run_id


@pytest.mark.asyncio
async def test_ml_context_requires_supervisor_scope() -> None:
    """Anonymous request → 303 redirect (auth middleware)."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", follow_redirects=False
    ) as c:
        resp = await c.get(f"/api/runs/{uuid.uuid4()}/ml-context")
    # Middleware: /api/* → 401 JSON for unauthenticated.
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ml_context_404_for_unknown_run(auth_cookies: dict[str, str]) -> None:
    """Auth'd request with non-existent run id → CatalogNotFoundError → 404."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", cookies=auth_cookies
    ) as c:
        resp = await c.get(f"/api/runs/{uuid.uuid4()}/ml-context")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ml_context_returns_three_way_join(
    auth_cookies: dict[str, str],
    supervisor_run: str,
) -> None:
    """Existing run with no mlflow_run_id → empty mlflow + model_versions."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", cookies=auth_cookies
    ) as c:
        resp = await c.get(f"/api/runs/{supervisor_run}/ml-context")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["agent_run"]["id"] == supervisor_run
    assert body["agent_run"]["mlflow_run_id"] is None
    # Empty MLflow payload (no run-id to look up).
    assert body["mlflow"] == {}
    # Empty soyuz scan (no linked versions).
    assert isinstance(body["model_versions"], list)
