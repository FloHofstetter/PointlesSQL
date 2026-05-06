"""HTTP route tests for the on-demand dbt endpoints.

Bypasses dbt's real CLI by monkeypatching
:meth:`pointlessql.services.dbt_executor.DBTExecutor._run` to return
a stub :class:`DBTRunResult` that points at the fixture
``manifest.json`` + ``run_results.json``.  This exercises the full
HTTP → executor → bridge → audit-row path end-to-end without
spawning a real dbt subprocess.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import AgentRunOperation
from pointlessql.services.dbt_executor import DBTExecutor, DBTRunResult

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "dbt_minimal" / "target"


def _make_stub_result(exit_code: int = 0) -> DBTRunResult:
    """Build a :class:`DBTRunResult` pointing at the fixture artefacts."""
    return DBTRunResult(
        command=["dbt", "run"],
        exit_code=exit_code,
        stdout="OK",
        stderr="",
        manifest_path=_FIXTURE_DIR / "manifest.json",
        run_results_path=_FIXTURE_DIR / "run_results.json",
        duration_seconds=2.5,
    )


@pytest.fixture
def stub_executor(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Patch :meth:`DBTExecutor._run` to skip the actual dbt subprocess."""

    async def _stub_run(self: DBTExecutor, *args: str) -> DBTRunResult:  # noqa: ARG001
        return _make_stub_result()

    monkeypatch.setattr(DBTExecutor, "_run", _stub_run)
    yield


@pytest.mark.asyncio
async def test_compile_returns_executor_envelope(
    auth_cookies: dict[str, str],
    stub_executor: None,  # noqa: ARG001
) -> None:
    """``/api/dbt/compile`` returns the executor envelope for any auth user."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", cookies=auth_cookies
    ) as c:
        resp = await c.post("/api/dbt/compile", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["exit_code"] == 0
    assert body["agent_run_id"] is None  # compile is not audited as a run
    assert "command" in body


@pytest.mark.asyncio
async def test_run_creates_owned_agent_run_and_emits_ops(
    auth_cookies: dict[str, str],
    stub_executor: None,  # noqa: ARG001
) -> None:
    """``/api/dbt/run`` without ``agent_run_id`` auto-creates one + emits ops."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", cookies=auth_cookies
    ) as c:
        resp = await c.post("/api/dbt/run", json={})
    assert resp.status_code == 200
    body = resp.json()
    run_id = body["agent_run_id"]
    assert isinstance(run_id, str) and len(run_id) > 10

    # Bridge wrote one op per fixture node (2 models + 2 tests).
    summary = body["summary"]
    assert summary["ok"] == 3  # bronze + silver + not_null pass
    assert summary["fail"] == 1  # unique_warn test fails

    factory = app.state.session_factory
    with factory() as session:
        ops = session.scalars(
            select(AgentRunOperation).where(AgentRunOperation.agent_run_id == run_id),
        ).all()
    assert len(ops) == 4
    op_names = sorted(o.op_name for o in ops)
    assert op_names == ["dbt_model", "dbt_model", "dbt_test", "dbt_test"]


@pytest.mark.asyncio
async def test_run_anonymous_request_redirects_to_login() -> None:
    """No auth cookie → middleware redirects to login."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", follow_redirects=False
    ) as c:
        resp = await c.post("/api/dbt/run", json={})
    # CSRF / auth middleware fires before our require_supervisor.
    assert resp.status_code in {303, 401, 403}


@pytest.mark.asyncio
async def test_run_non_admin_lacks_supervisor_scope(
    non_admin_cookies: dict[str, str],
    stub_executor: None,  # noqa: ARG001
) -> None:
    """Non-admin without supervisor flag is refused with an authz error."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", cookies=non_admin_cookies
    ) as c:
        resp = await c.post("/api/dbt/run", json={})
    # AuthorizationError is mapped to 403 by the global exception handler.
    assert resp.status_code in {401, 403}


@pytest.mark.asyncio
async def test_test_endpoint_emits_ops_for_existing_run(
    auth_cookies: dict[str, str],
    stub_executor: None,  # noqa: ARG001
) -> None:
    """``/api/dbt/test`` honours a caller-supplied ``agent_run_id``."""

    # First create a run via /api/dbt/run, then call /api/dbt/test with that id.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", cookies=auth_cookies
    ) as c:
        run_resp = await c.post("/api/dbt/run", json={})
        run_id = run_resp.json()["agent_run_id"]

        test_resp = await c.post(
            "/api/dbt/test",
            json={"agent_run_id": run_id},
        )

    assert test_resp.status_code == 200
    body = test_resp.json()
    assert body["agent_run_id"] == run_id

    # First call wrote 4 ops, second call wrote 4 more (different ordinals).
    factory = app.state.session_factory
    with factory() as session:
        ops = session.scalars(
            select(AgentRunOperation).where(AgentRunOperation.agent_run_id == run_id),
        ).all()
    assert len(ops) == 8
