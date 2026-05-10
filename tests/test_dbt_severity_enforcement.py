"""Tests for severity enforcement + dbt CloudEvents emission.

Sprint 36.5 maps dbt's ``severity`` config (``error`` vs ``warn``) to
PointlesSQL's AgentRun terminal status and emits three new
CloudEvents for downstream consumers:

* ``pointlessql.dbt.run.completed`` — once per ``/api/dbt/run|test``
* ``pointlessql.dbt.test.failed`` — per error-severity failing test
* ``pointlessql.dbt.test.warned`` — per warn-severity failing test
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.dbt.routes import _classify_severity
from pointlessql.api.main import app
from pointlessql.models.agent._runs import STATUS_FAILED, STATUS_SUCCEEDED, AgentRun
from pointlessql.models.audit_sinks import GovernanceEvent
from pointlessql.services.dbt import (
    DBTExecutor,
    DBTNodeResult,
    DBTRunResult,
    merge_manifest_and_results,
    parse_manifest,
    parse_run_results,
)
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_DBT_RUN_COMPLETED,
    EVENT_TYPE_DBT_TEST_FAILED,
    EVENT_TYPE_DBT_TEST_WARNED,
)

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "dbt_minimal" / "target"
_MANIFEST = _FIXTURE_DIR / "manifest.json"
_RESULTS = _FIXTURE_DIR / "run_results.json"


def _node(
    *,
    unique_id: str = "test.x.y",
    resource_type: str = "test",
    status: str = "fail",
    severity: str | None = None,
) -> DBTNodeResult:
    """Build a DBTNodeResult fixture for the classifier tests."""
    return DBTNodeResult(
        unique_id=unique_id,
        resource_type=resource_type,
        relation_name=None,
        status=status,
        execution_time=0.1,
        message="msg",
        rows_affected=None,
        depends_on=[],
        materialization=None,
        severity=severity,
    )


def test_classify_severity_error_default() -> None:
    """Failing tests default to error severity when severity is unset."""
    nodes = [_node(severity=None)]
    err, warn = _classify_severity(nodes)
    assert (err, warn) == (1, 0)


def test_classify_severity_warn() -> None:
    """warn-severity test failures count as warn, not error."""
    nodes = [_node(severity="warn")]
    err, warn = _classify_severity(nodes)
    assert (err, warn) == (0, 1)


def test_classify_severity_passing_does_not_count() -> None:
    """Passing nodes never count as failures."""
    err, warn = _classify_severity([_node(status="pass", severity="error")])
    assert (err, warn) == (0, 0)


def test_classify_severity_fixture() -> None:
    """Fixture has 1 warn failure (unique_silver_clean_id) + 0 errors."""
    nodes = merge_manifest_and_results(
        parse_manifest(_MANIFEST),
        parse_run_results(_RESULTS),
    )
    err, warn = _classify_severity(nodes)
    # The failing test in the fixture has severity='warn'.
    assert (err, warn) == (0, 1)


@pytest.fixture
def stub_executor(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Patch ``DBTExecutor._run`` so no real dbt subprocess runs."""

    async def _stub_run(self: DBTExecutor, *args: str) -> DBTRunResult:  # noqa: ARG001
        return DBTRunResult(
            command=["dbt", "run"],
            exit_code=0,
            stdout="OK",
            stderr="",
            manifest_path=_MANIFEST,
            run_results_path=_RESULTS,
            duration_seconds=2.5,
        )

    monkeypatch.setattr(DBTExecutor, "_run", _stub_run)
    yield


@pytest.mark.asyncio
async def test_owned_run_succeeds_when_only_warn_failures(
    auth_cookies: dict[str, str],
    stub_executor: None,  # noqa: ARG001
) -> None:
    """A run with only warn-severity failures finishes as 'succeeded'."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", cookies=auth_cookies
    ) as c:
        resp = await c.post("/api/dbt/run", json={})
    assert resp.status_code == 200
    body = resp.json()
    summary = body["summary"]
    assert summary["err_failures"] == 0
    assert summary["warn_failures"] == 1

    factory = app.state.session_factory
    with factory() as session:
        run = session.scalar(
            select(AgentRun).where(AgentRun.id == body["agent_run_id"]),
        )
    assert run is not None
    assert run.status == STATUS_SUCCEEDED


@pytest.mark.asyncio
async def test_dbt_run_emits_governance_events(
    auth_cookies: dict[str, str],
    stub_executor: None,  # noqa: ARG001
) -> None:
    """A run emits run.completed + one test.warned for the warn failure."""
    factory = app.state.session_factory
    with factory() as session:
        before_count = session.scalar(
            select(GovernanceEvent.id).order_by(GovernanceEvent.id.desc()),
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", cookies=auth_cookies
    ) as c:
        await c.post("/api/dbt/run", json={})

    with factory() as session:
        events = session.scalars(
            select(GovernanceEvent).where(
                GovernanceEvent.id > (before_count or 0),
            ),
        ).all()

    types_seen = {e.event_type for e in events}
    assert EVENT_TYPE_DBT_RUN_COMPLETED in types_seen
    assert EVENT_TYPE_DBT_TEST_WARNED in types_seen
    # No error-severity failures in the fixture, so no test.failed event.
    assert EVENT_TYPE_DBT_TEST_FAILED not in types_seen


@pytest.mark.asyncio
async def test_run_with_error_severity_failure_marks_run_failed(
    auth_cookies: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A run with an error-severity failing test ends as 'failed'."""

    # Build a synthetic run_results.json where the unique test is
    # severity='error' AND status='fail'.
    manifest = json.loads(_MANIFEST.read_text())
    manifest["nodes"]["test.pql_test.unique_silver_clean_id.def456"]["config"]["severity"] = "error"
    manifest_dir = tmp_path / "target"
    manifest_dir.mkdir()
    custom_manifest = manifest_dir / "manifest.json"
    custom_manifest.write_text(json.dumps(manifest))
    custom_results = manifest_dir / "run_results.json"
    custom_results.write_text(_RESULTS.read_text())

    async def _stub_run(self: DBTExecutor, *args: str) -> DBTRunResult:  # noqa: ARG001
        return DBTRunResult(
            command=["dbt", "run"],
            exit_code=1,  # dbt's exit code for any test failure
            stdout="",
            stderr="",
            manifest_path=custom_manifest,
            run_results_path=custom_results,
            duration_seconds=2.5,
        )

    monkeypatch.setattr(DBTExecutor, "_run", _stub_run)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", cookies=auth_cookies
    ) as c:
        resp = await c.post("/api/dbt/run", json={})
    body = resp.json()
    assert body["summary"]["err_failures"] == 1

    factory = app.state.session_factory
    with factory() as session:
        run = session.scalar(
            select(AgentRun).where(AgentRun.id == body["agent_run_id"]),
        )
    assert run is not None
    assert run.status == STATUS_FAILED
