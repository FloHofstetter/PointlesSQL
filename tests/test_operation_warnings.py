"""Tests for the BUG-grand-08 ``warnings_json`` separation.

Pre-fix: ``_stamp_audit_marker`` appended ``[lineage_emit_failed]``
into ``error_message`` whenever a soyuz post-commit hook failed,
which made the run-detail Operations tab paint successful merges
as ``status=error``.

Post-fix: ``error_message`` is reserved for "the primitive itself
raised"; non-fatal post-commit markers go into the new
``warnings_json`` column as a JSON-encoded
``{"markers": [str, ...]}`` blob.
"""

from __future__ import annotations

import datetime as _dt
import json
import uuid

from pointlessql.api.main import app
from pointlessql.models import AgentRun, AgentRunOperation
from pointlessql.services.agent_runs.operations import (
    _stamp_audit_marker,
    operation_context,
)


def _seed_run(factory, run_id: str) -> None:
    now = _dt.datetime.now(_dt.UTC)
    with factory() as session:
        session.add(
            AgentRun(
                id=run_id,
                principal="alice",
                notebook_path=f"/tmp/{run_id}.py",
                status="running",
                started_at=now,
            )
        )
        session.commit()


def test_stamp_marker_writes_warnings_not_error_message() -> None:
    """A single ``_stamp_audit_marker`` call lands in warnings_json."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    _seed_run(factory, run_id)

    with operation_context(factory, agent_run_id=run_id, op_name="sql", params={}):
        pass

    with factory() as session:
        op = session.query(AgentRunOperation).filter_by(agent_run_id=run_id).one()

    _stamp_audit_marker(factory, op_id=op.id, marker="[lineage_emit_failed] boom")

    with factory() as session:
        refreshed = session.get(AgentRunOperation, op.id)
        assert refreshed is not None
        assert refreshed.error_message is None
        assert refreshed.warnings_json is not None
        parsed = json.loads(refreshed.warnings_json)
        assert parsed == {"markers": ["[lineage_emit_failed] boom"]}


def test_stamp_marker_appends_to_existing_warnings() -> None:
    """Multiple stamps accumulate into the markers list, in order."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    _seed_run(factory, run_id)

    with operation_context(factory, agent_run_id=run_id, op_name="sql", params={}):
        pass
    with factory() as session:
        op = session.query(AgentRunOperation).filter_by(agent_run_id=run_id).one()

    _stamp_audit_marker(factory, op_id=op.id, marker="[lineage_emit_failed] one")
    _stamp_audit_marker(factory, op_id=op.id, marker="[lineage_edges_partial] two")
    _stamp_audit_marker(factory, op_id=op.id, marker="[lineage_value_partial] three")

    with factory() as session:
        refreshed = session.get(AgentRunOperation, op.id)
        assert refreshed is not None
        parsed = json.loads(refreshed.warnings_json or "{}")
    assert parsed["markers"] == [
        "[lineage_emit_failed] one",
        "[lineage_edges_partial] two",
        "[lineage_value_partial] three",
    ]


def test_primitive_failure_still_uses_error_message() -> None:
    """When the primitive raises, error_message is set; warnings stay None."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    _seed_run(factory, run_id)

    class Boom(RuntimeError):
        pass

    try:
        with operation_context(factory, agent_run_id=run_id, op_name="sql", params={}):
            raise Boom("primitive crash")
    except Boom:
        pass

    with factory() as session:
        op = session.query(AgentRunOperation).filter_by(agent_run_id=run_id).one()
    assert op.error_message is not None
    assert "primitive crash" in op.error_message
    assert op.warnings_json is None


def test_lineage_emit_failure_populates_warnings_via_operation_context(monkeypatch) -> None:
    """End-to-end: when soyuz emit raises, warnings is set, status stays ok."""
    from pointlessql.services import soyuz_lineage

    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    _seed_run(factory, run_id)

    monkeypatch.setattr(
        soyuz_lineage,
        "emit_event_sync",
        lambda **kw: "soyuz unreachable: connection refused",
    )

    with operation_context(
        factory,
        agent_run_id=run_id,
        op_name="write_table",
        params={"source_table_fqn": "cat.bronze.t"},
        target_table="cat.silver.t",
    ) as recorder:
        recorder.extra_params = {"source_table_fqn": "cat.bronze.t"}

    with factory() as session:
        op = session.query(AgentRunOperation).filter_by(agent_run_id=run_id).one()
    # error_message stays clean — the primitive itself succeeded.
    assert op.error_message is None
    # warnings_json carries the soyuz emit failure marker.
    assert op.warnings_json is not None
    parsed = json.loads(op.warnings_json)
    markers = parsed.get("markers", [])
    assert any("[lineage_emit_failed]" in m for m in markers)
