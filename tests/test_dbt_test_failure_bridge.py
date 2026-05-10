"""Tests for the test-failure → lineage_row_rejects bridge.

Sprint 36.3 wires dbt's per-test outcome into PointlesSQL's
``lineage_row_rejects`` table so a failing dbt test surfaces in the
cockpit alongside merge-time rejects.  This test asserts:

1. ``emit_test_failure_rejects`` writes one row per failing test
   with ``reason='expectation_failed'`` and the dbt failure message
   on ``detail``.
2. Passing tests + non-test nodes (models) do not produce rejects.
3. The new ``expectation_failures`` axis on the audit aggregator
   counts those rejects via the row-level ``reason`` filter.
4. The end-to-end ``/api/dbt/run`` route reports
   ``rejects_inserted`` in its summary.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models.agent._runs import STATUS_RUNNING, AgentRun
from pointlessql.models.lineage import LineageRowReject
from pointlessql.services.dbt import (
    DBTExecutor,
    DBTRunResult,
    emit_operations_for_dbt_run,
    emit_test_failure_rejects,
    merge_manifest_and_results,
    parse_manifest,
    parse_run_results,
)

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "dbt_minimal" / "target"
_MANIFEST = _FIXTURE_DIR / "manifest.json"
_RESULTS = _FIXTURE_DIR / "run_results.json"


def _register_parent_run(session_factory: Any) -> str:
    """Insert a fake AgentRun + return its id."""
    run_id = str(uuid.uuid4())
    with session_factory() as session:
        session.add(
            AgentRun(
                id=run_id,
                workspace_id=1,
                principal="bridge-test@example.com",
                agent_id="dbt-cli",
                notebook_path="dbt:run",
                status=STATUS_RUNNING,
                started_at=datetime.now(UTC),
            ),
        )
        session.commit()
    return run_id


def test_emit_test_failure_rejects_writes_one_row_per_failing_test() -> None:
    """Only failing tests (``status='fail'``) produce reject rows."""
    factory = app.state.session_factory
    run_id = _register_parent_run(factory)
    m = parse_manifest(_MANIFEST)
    rs = parse_run_results(_RESULTS)
    nodes = merge_manifest_and_results(m, rs)
    op_ids = emit_operations_for_dbt_run(
        factory,
        agent_run_id=run_id,
        nodes=nodes,
        started_at=datetime.now(UTC),
    )

    inserted = emit_test_failure_rejects(
        factory,
        agent_run_id=run_id,
        nodes=nodes,
        op_ids=op_ids,
    )
    # Fixture has 1 failing test (unique_silver_clean_id) and 1 passing
    # test (not_null_silver_clean_id) — only the failing one rejects.
    assert inserted == 1

    with factory() as session:
        rejects = session.scalars(
            select(LineageRowReject).where(LineageRowReject.run_id == run_id),
        ).all()
    assert len(rejects) == 1
    rej = rejects[0]
    assert rej.reason == "expectation_failed"
    # Source row id = the test's unique_id so the row-trace UI can
    # link from failure to test definition.
    assert rej.source_row_id == "test.pql_test.unique_silver_clean_id.def456"
    # detail carries dbt's failure message verbatim.
    assert rej.detail is not None
    assert "Got 3 results" in rej.detail


def test_emit_test_failure_rejects_validates_lengths() -> None:
    """Mismatched nodes / op_ids lists fail loud rather than silent."""
    factory = app.state.session_factory
    with pytest.raises(ValueError, match="same length"):
        emit_test_failure_rejects(
            factory,
            agent_run_id="x",
            nodes=[],
            op_ids=[1, 2, 3],
        )


def test_audit_aggregator_recognises_expectation_failures_metric() -> None:
    """``expectation_failures`` is a first-class metric with a SQL spec."""
    from pointlessql.services.audit_aggregator import VALID_METRICS, metric_spec

    assert "expectation_failures" in VALID_METRICS
    spec = metric_spec("expectation_failures")
    # Filter is a row-level WHERE on the reject reason — not None.
    assert spec.where is not None
    # And it points at lineage_row_rejects, not a separate table.
    assert spec.table is LineageRowReject


@pytest.fixture
def stub_executor(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Patch :meth:`DBTExecutor._run` so no real dbt subprocess runs."""

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
async def test_route_reports_rejects_inserted(
    auth_cookies: dict[str, str],
    stub_executor: None,  # noqa: ARG001
) -> None:
    """``/api/dbt/run`` summary surfaces the rejects-inserted count."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", cookies=auth_cookies
    ) as c:
        resp = await c.post("/api/dbt/run", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["rejects_inserted"] == 1
    # And the matching reject lives in the DB under the new run id.
    factory = app.state.session_factory
    with factory() as session:
        rejects = session.scalars(
            select(LineageRowReject).where(
                LineageRowReject.run_id == body["agent_run_id"],
            ),
        ).all()
    assert len(rejects) == 1
    assert rejects[0].reason == "expectation_failed"
