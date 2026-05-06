"""Tests for the dbt → AgentRunOperation bridge.

Reads fixture ``manifest.json`` + ``run_results.json`` from
``tests/fixtures/dbt_minimal/`` (committed alongside this test) and
asserts that the bridge:

1. Parses both files into the dataclass shape.
2. Picks the right ``op_name`` per resource type.
3. Captures status / target_table / message / depends_on / severity
   on the params + columns of each emitted row.
4. Raises :class:`AuditUnavailableError` when the parent run id is
   not registered (strict-mode invariant from
   :func:`record_operation`).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.exceptions import AuditUnavailableError
from pointlessql.models import AgentRunOperation
from pointlessql.models.agent_runs import STATUS_RUNNING, AgentRun
from pointlessql.services.dbt_bridge import (
    DBTNodeResult,
    emit_operations_for_dbt_run,
    merge_manifest_and_results,
    parse_manifest,
    parse_run_results,
    summarise,
)

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "dbt_minimal" / "target"
_MANIFEST = _FIXTURE_DIR / "manifest.json"
_RESULTS = _FIXTURE_DIR / "run_results.json"


@pytest.fixture
def app_session_factory() -> Any:
    """Return the session factory mounted on the app under test."""
    return app.state.session_factory


def test_parse_manifest_returns_dict_with_nodes() -> None:
    """Manifest parses into a dict and exposes the four fixture nodes."""
    m = parse_manifest(_MANIFEST)
    assert "nodes" in m
    assert len(m["nodes"]) == 4
    assert "model.pql_test.bronze_raw" in m["nodes"]


def test_parse_run_results_returns_only_dict_entries() -> None:
    """Result parser filters out non-dict entries defensively."""
    rs = parse_run_results(_RESULTS)
    assert len(rs) == 4
    assert all(isinstance(r, dict) for r in rs)


def test_parse_manifest_raises_for_invalid_json(tmp_path: Path) -> None:
    """Invalid JSON surfaces as ValueError, not JSONDecodeError."""
    bad = tmp_path / "bad.json"
    bad.write_text("not json at all")
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_manifest(bad)


def test_merge_combines_manifest_metadata_with_status() -> None:
    """Merged dataclass carries relation, severity, depends_on, status."""
    m = parse_manifest(_MANIFEST)
    rs = parse_run_results(_RESULTS)
    nodes = merge_manifest_and_results(m, rs)
    assert len(nodes) == 4

    by_id = {n.unique_id: n for n in nodes}
    bronze = by_id["model.pql_test.bronze_raw"]
    assert bronze.resource_type == "model"
    assert bronze.relation_name == "main.bronze.bronze_raw"
    assert bronze.status == "success"
    assert bronze.materialization == "table"
    assert bronze.depends_on == []
    assert bronze.rows_affected == 100

    silver = by_id["model.pql_test.silver_clean"]
    assert silver.depends_on == ["model.pql_test.bronze_raw"]
    assert silver.materialization == "incremental"

    not_null = by_id["test.pql_test.not_null_silver_clean_id.abc123"]
    assert not_null.resource_type == "test"
    # Tests carry a relation name pointing at dbt_test__audit.* where
    # ``--store-failures`` would materialise the failing rows.
    assert not_null.relation_name == "main.dbt_test__audit.not_null_silver_clean_id"
    assert not_null.severity == "error"
    assert not_null.status == "pass"

    unique_warn = by_id["test.pql_test.unique_silver_clean_id.def456"]
    assert unique_warn.severity == "warn"
    assert unique_warn.status == "fail"
    assert unique_warn.message is not None
    assert "Got 3 results" in unique_warn.message


def test_summarise_counts_per_status() -> None:
    """Summary buckets nodes by status family."""
    m = parse_manifest(_MANIFEST)
    rs = parse_run_results(_RESULTS)
    nodes = merge_manifest_and_results(m, rs)
    summary = summarise("run-x", nodes)
    assert summary.ok_count == 3  # 2 successful models + 1 passed test
    assert summary.fail_count == 1  # the failing unique test
    assert summary.warn_count == 0
    assert summary.skipped_count == 0


def _register_parent_run(session_factory: Any) -> str:
    """Register a fake AgentRun so emit_operations has a valid FK target."""
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


def test_emit_operations_writes_one_row_per_node(app_session_factory: Any) -> None:
    """All four fixture nodes land as ``agent_run_operations`` rows."""
    run_id = _register_parent_run(app_session_factory)
    m = parse_manifest(_MANIFEST)
    rs = parse_run_results(_RESULTS)
    nodes = merge_manifest_and_results(m, rs)

    op_ids = emit_operations_for_dbt_run(
        app_session_factory,
        agent_run_id=run_id,
        nodes=nodes,
        started_at=datetime.now(UTC),
    )
    assert len(op_ids) == 4

    with app_session_factory() as session:
        ops = session.scalars(
            select(AgentRunOperation).where(AgentRunOperation.agent_run_id == run_id),
        ).all()
    op_names = sorted(o.op_name for o in ops)
    assert op_names == ["dbt_model", "dbt_model", "dbt_test", "dbt_test"]

    targets = {o.target_table for o in ops if o.op_name == "dbt_model"}
    assert targets == {"main.bronze.bronze_raw", "main.silver.silver_clean"}

    # Failing test row carries the dbt failure message.
    failing = [o for o in ops if o.error_message is not None]
    assert len(failing) == 1
    assert "Got 3 results" in (failing[0].error_message or "")
    # And captures the test's unique_id + severity in params_json.
    params = json.loads(failing[0].params_json or "{}")
    assert params["severity"] == "warn"
    assert params["resource_type"] == "test"
    assert params["status"] == "fail"


def test_emit_operations_raises_when_parent_run_unknown(
    app_session_factory: Any,
) -> None:
    """Strict-mode FK check refuses to emit under a missing run id."""
    nodes = [
        DBTNodeResult(
            unique_id="model.x.foo",
            resource_type="model",
            relation_name="main.x.foo",
            status="success",
            execution_time=0.1,
            message=None,
            rows_affected=1,
            depends_on=[],
            materialization="table",
            severity=None,
        ),
    ]
    with pytest.raises(AuditUnavailableError):
        emit_operations_for_dbt_run(
            app_session_factory,
            agent_run_id="not-a-real-run",
            nodes=nodes,
            started_at=datetime.now(UTC),
        )
