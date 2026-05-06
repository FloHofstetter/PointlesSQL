"""HTTP route tests for the read-only dbt manifest accessors.

Covers ``GET /api/dbt/manifest``, ``GET /api/dbt/coverage``, and
``GET /api/dbt/test-failures``.  All three are pure-read endpoints
that do not invoke the dbt CLI — they walk the on-disk
``target/manifest.json`` (for the first two) or join
``lineage_row_rejects`` with ``agent_run_operations`` (the third).

Manifest tests rely on the fixture project at
``tests/fixtures/dbt_minimal/`` so a single ``settings.dbt.project_dir``
override drives every read.  The 404-when-missing case writes a
fresh ``tmp_path`` directory with no manifest and confirms the
helper raises a clear hint.
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import AgentRun, AgentRunOperation
from pointlessql.models.lineage import LineageRowReject

_FIXTURE_PROJECT = Path(__file__).parent / "fixtures" / "dbt_minimal"


@pytest.fixture
def fixture_project_dir() -> Iterator[None]:
    """Point ``settings.dbt.project_dir`` at the bundled fixture project.

    Restores the prior value on teardown so unrelated tests are not
    affected.

    Yields:
        None: scope-only fixture; setup happens during ``yield``.
    """
    original = app.state.settings.dbt.project_dir
    app.state.settings.dbt.project_dir = _FIXTURE_PROJECT
    try:
        yield
    finally:
        app.state.settings.dbt.project_dir = original


@pytest.mark.asyncio
async def test_manifest_returns_models_with_attached_tests(
    auth_cookies: dict[str, str],
    fixture_project_dir: None,  # noqa: ARG001
) -> None:
    """``GET /api/dbt/manifest`` projects the fixture into a model summary."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", cookies=auth_cookies
    ) as c:
        resp = await c.get("/api/dbt/manifest")
    assert resp.status_code == 200
    body = resp.json()

    models_by_name = {m["name"]: m for m in body["models"]}
    assert set(models_by_name) == {"bronze_raw", "silver_clean"}

    # silver_clean has the two fixture tests attached via depends_on.
    # The fixture lacks ``test_metadata.name`` so the projection falls
    # through to ``node.name`` (the long generated identifier).
    silver_tests = [t["name"] for t in models_by_name["silver_clean"]["tests"]]
    assert sorted(silver_tests) == [
        "not_null_silver_clean_id",
        "unique_silver_clean_id",
    ]

    # bronze_raw has no tests in the fixture.
    assert models_by_name["bronze_raw"]["tests"] == []


@pytest.mark.asyncio
async def test_manifest_404_when_no_manifest_on_disk(
    auth_cookies: dict[str, str],
    tmp_path: Path,
) -> None:
    """``/api/dbt/manifest`` 404s with a hint when target/manifest.json is missing."""
    original = app.state.settings.dbt.project_dir
    app.state.settings.dbt.project_dir = tmp_path
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://t", cookies=auth_cookies
        ) as c:
            resp = await c.get("/api/dbt/manifest")
        assert resp.status_code == 404
        assert "compile" in resp.json()["detail"].lower()
    finally:
        app.state.settings.dbt.project_dir = original


@pytest.mark.asyncio
async def test_coverage_computes_ratio(
    auth_cookies: dict[str, str],
    fixture_project_dir: None,  # noqa: ARG001
) -> None:
    """``GET /api/dbt/coverage`` reports models / with-tests / ratio."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", cookies=auth_cookies
    ) as c:
        resp = await c.get("/api/dbt/coverage")
    assert resp.status_code == 200
    body = resp.json()
    # Two models in the fixture; only silver_clean has tests.
    assert body["models_total"] == 2
    assert body["models_with_tests"] == 1
    assert body["ratio"] == 0.5
    assert body["untested"] == ["model.pql_test.bronze_raw"]


@pytest.mark.asyncio
async def test_test_failures_filters_to_expectation_failed_rejects(
    auth_cookies: dict[str, str],
) -> None:
    """``GET /api/dbt/test-failures`` returns only ``expectation_failed`` rows.

    Inserts one matching reject + one foreign-reason reject to prove
    the WHERE-clause filter holds.  Joins back to the parent
    ``agent_run_operations`` row so the response carries the
    ``model_relation`` from the op's ``target_table``.
    """
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add(
            AgentRun(
                id=run_id,
                workspace_id=1,
                principal="test@test.com",
                agent_id="dbt-cli",
                notebook_path="dbt:test",
                status="running",
                started_at=now,
            ),
        )
        session.flush()
        op = AgentRunOperation(
            agent_run_id=run_id,
            workspace_id=1,
            ordinal=1,
            op_name="dbt_test",
            params_json='{"unique_id": "test.demo.foo", "severity": "error"}',
            target_table="main.bronze.bronze_raw",
            input_sha=None,
            rows_affected=None,
            delta_version_before=None,
            delta_version_after=None,
            started_at=now,
            finished_at=now,
            error_message="Got 1 result, configured to fail if != 0",
        )
        session.add(op)
        session.flush()
        # Matching reject — surfaces.
        session.add(
            LineageRowReject(
                workspace_id=1,
                run_id=run_id,
                op_id=op.id,
                source_table="main.bronze.bronze_raw",
                source_row_id="test.demo.foo",
                reason="expectation_failed",
                detail="Got 1 result, configured to fail if != 0",
                created_at=now,
            ),
        )
        # Foreign-reason reject — must not surface.
        session.add(
            LineageRowReject(
                workspace_id=1,
                run_id=run_id,
                op_id=op.id,
                source_table="main.bronze.bronze_raw",
                source_row_id="row-12",
                reason="schema_mismatch",
                detail="bad type",
                created_at=now,
            ),
        )
        session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", cookies=auth_cookies
    ) as c:
        resp = await c.get(
            "/api/dbt/test-failures",
            params={"agent_run_id": run_id},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["agent_run_id"] == run_id
    assert body["row_count"] == 1
    row = body["rows"][0]
    assert row["test_unique_id"] == "test.demo.foo"
    assert row["model_relation"] == "main.bronze.bronze_raw"
    assert row["severity"] == "error"
    assert "Got 1 result" in (row["message"] or "")


@pytest.mark.asyncio
async def test_test_failures_requires_supervisor_or_auditor_scope(
    non_admin_cookies: dict[str, str],
) -> None:
    """A plain non-admin / non-supervisor cookie is refused with 403."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", cookies=non_admin_cookies
    ) as c:
        resp = await c.get(
            "/api/dbt/test-failures",
            params={"agent_run_id": str(uuid.uuid4())},
        )
    assert resp.status_code in {401, 403}
