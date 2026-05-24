"""Tests for the / Sprint-41.1 Lineage sub-pills on /runs/{id}.

three new sub-pills (Row trace,
Column trace, Value changes) sit next to the existing Summary +
Graph pills inside the Lineage top-tab.  The new sub-pills wrap
existing JSON endpoints; backend changes are limited to surfacing
``sample_target_row_id`` on the lineage summary loader so the
Summary "Trace target row" buttons can deep-link concretely.
"""

from __future__ import annotations

import datetime
import uuid
from unittest.mock import MagicMock

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.api.runs_routes import load_lineage_summary_for_run
from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    AgentRunSource,
    LineageRowEdge,
)


@pytest.fixture(autouse=True)
def _stub_uc_client() -> None:
    app.state.uc_client = MagicMock()


def _seed_run_with_one_edge() -> tuple[str, int, str]:
    """Seed a run with one op and one ``LineageRowEdge``.

    Returns the ``(run_id, op_id, target_row_id)`` triple.
    """
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    run_id = str(uuid.uuid4())
    target_row_id = "row-" + uuid.uuid4().hex[:12]
    with factory() as s:
        s.add(
            AgentRun(
                id=run_id,
                principal="alice@example.com",
                agent_id="etl",
                notebook_path="nb.py",
                status="succeeded",
                started_at=now,
                finished_at=now,
            )
        )
        s.flush()
        s.add(
            AgentRunSource(
                agent_run_id=run_id,
                source_bytes="print('seed')\n",
                source_sha="0" * 64,
                captured_at=now,
            )
        )
        op = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=1,
            op_name="merge",
            params_json="{}",
            target_table="cat.sch.silver",
            rows_affected=1,
            started_at=now,
            finished_at=now,
        )
        s.add(op)
        s.flush()
        s.add(
            LineageRowEdge(
                run_id=run_id,
                op_id=op.id,
                source_table="cat.sch.bronze",
                source_row_id="src-1",
                target_table="cat.sch.silver",
                target_row_id=target_row_id,
                created_at=now,
            )
        )
        s.commit()
        s.refresh(op)
        return run_id, op.id, target_row_id


def test_lineage_summary_loader_surfaces_sample_target_row_id() -> None:
    """The loader must include ``sample_target_row_id`` per group.

    added the column so the Lineage sub-pills can
    deep-link a Summary-row click into the Row-trace pane.
    """
    run_id, _op_id, target_row_id = _seed_run_with_one_edge()

    class _R:
        app = app

    payload = load_lineage_summary_for_run(_R(), run_id)  # type: ignore[arg-type]
    assert payload["total_edges"] == 1
    assert len(payload["rows"]) == 1
    row = payload["rows"][0]
    assert row["sample_target_row_id"] == target_row_id


@pytest.mark.asyncio
async def test_run_detail_renders_three_new_lineage_subpills() -> None:
    """The run-detail HTML must mount the Row / Column / Value pills.

    Asserts the three new ``data-bs-target`` ids and their factory
    ``x-data`` attributes are present so Alpine can resolve the
    factories at template parse time.
    """
    run_id, _op_id, _target_row_id = _seed_run_with_one_edge()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        resp = await client.get(f"/runs/{run_id}")
    assert resp.status_code == 200, resp.text
    body = resp.text
    # Tab buttons.
    assert 'id="tab-lineage-row-trace-btn"' in body
    assert 'id="tab-lineage-column-trace-btn"' in body
    assert 'id="tab-lineage-value-changes-btn"' in body
    # Tab pane targets.
    assert 'id="tab-lineage-row-trace"' in body
    assert 'id="tab-lineage-column-trace"' in body
    assert 'id="tab-lineage-value-changes"' in body
    # Alpine factories must be referenced so window.* lookup works.
    assert 'x-data="rowTracePane()"' in body
    assert 'x-data="columnTracePane()"' in body
    assert 'x-data="valueChangesPane()"' in body


@pytest.mark.asyncio
async def test_summary_trace_button_carries_table_and_row_id() -> None:
    """The Summary "Trace target row" button must declare deep-link attrs.

    Cannot drive the JS event-bus from pytest, but the button's
    ``data-pql-trace-row="1"`` + ``data-table`` + ``data-row-id``
    attrs are the contract that the frontend ``bindLineageTraceButtons``
    handler reads.  Assert they are set on the rendered HTML.
    """
    run_id, _op_id, target_row_id = _seed_run_with_one_edge()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        resp = await client.get(f"/runs/{run_id}")
    assert resp.status_code == 200, resp.text
    body = resp.text
    assert 'data-pql-trace-row="1"' in body
    assert 'data-table="cat.sch.silver"' in body
    assert f'data-row-id="{target_row_id}"' in body
