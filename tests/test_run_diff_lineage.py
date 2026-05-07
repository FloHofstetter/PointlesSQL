"""Tests for Sprint 18.4 lineage_diff service + diff HTML route.

Covers:

* :func:`run_diff.build_lineage_diff` produces correct
  per-bucket deltas for rejects, value-changes, rows.
* The JSON ``/api/agent-runs/diff?detail=true`` carries the new
  ``lineage_diff`` payload.
* The HTML ``/runs/{a}/diff/{b}`` route renders the page with
  the four stat cards and the Chart.js payload script.
"""

from __future__ import annotations

import datetime
import uuid
from unittest.mock import MagicMock

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    AgentRunSource,
    LineageRowReject,
    LineageValueChange,
)
from pointlessql.services import run_diff


@pytest.fixture(autouse=True)
def _stub_uc_client() -> None:
    app.state.uc_client = MagicMock()


def _seed_run(
    *,
    rejects_by_reason: dict[str, int] | None = None,
    value_changes: dict[str, int] | None = None,
    rows_per_table: dict[str, int] | None = None,
) -> str:
    """Create a run + 1 op + the requested rejects / value-changes."""
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    run_id = str(uuid.uuid4())
    with factory() as s:
        s.add(
            AgentRun(
                id=run_id,
                principal="alice@example.com",
                agent_id="etl",
                notebook_path="x.py",
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
        ord_counter = 0
        for table, rows in (rows_per_table or {}).items():
            ord_counter += 1
            s.add(
                AgentRunOperation(
                    agent_run_id=run_id,
                    ordinal=ord_counter,
                    op_name="merge",
                    params_json="{}",
                    target_table=table,
                    rows_affected=rows,
                    started_at=now,
                    finished_at=now,
                )
            )
        s.flush()
        # Single sentinel op for rejects + value-changes attribution.
        sentinel = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=ord_counter + 1,
            op_name="merge",
            params_json="{}",
            target_table="cat.sch.sentinel",
            rows_affected=0,
            started_at=now,
            finished_at=now,
        )
        s.add(sentinel)
        s.flush()
        for reason, n in (rejects_by_reason or {}).items():
            for j in range(n):
                s.add(
                    LineageRowReject(
                        run_id=run_id,
                        op_id=sentinel.id,
                        source_table="cat.sch.bronze",
                        source_row_id=f"r{reason}_{j}",
                        reason=reason,
                        created_at=now,
                    )
                )
        for table, n in (value_changes or {}).items():
            for j in range(n):
                s.add(
                    LineageValueChange(
                        run_id=run_id,
                        op_id=sentinel.id,
                        target_table=table,
                        target_row_id=f"row{j}",
                        target_column="email",
                        old_value="o",
                        new_value="n",
                        created_at=now,
                    )
                )
        s.commit()
    return run_id


# ---------------------------------------------------------------------
# build_lineage_diff
# ---------------------------------------------------------------------


def test_lineage_diff_reject_buckets() -> None:
    a = _seed_run(rejects_by_reason={"on_key_null": 5})
    b = _seed_run(rejects_by_reason={"on_key_null": 2, "schema_mismatch": 7})
    factory = app.state.session_factory
    diff = run_diff.build_lineage_diff(factory, run_a_id=a, run_b_id=b)
    shift = diff["reject_pattern_shift"]
    assert shift["a"] == {"on_key_null": 5, "schema_mismatch": 0}
    assert shift["b"] == {"on_key_null": 2, "schema_mismatch": 7}
    assert shift["delta"] == {"on_key_null": -3, "schema_mismatch": 7}


def test_lineage_diff_value_change_per_table() -> None:
    a = _seed_run(value_changes={"cat.sch.silver": 3})
    b = _seed_run(value_changes={"cat.sch.silver": 5, "cat.sch.gold": 8})
    factory = app.state.session_factory
    diff = run_diff.build_lineage_diff(factory, run_a_id=a, run_b_id=b)
    delta = diff["value_change_volume_per_table"]["delta"]
    assert delta == {"cat.sch.silver": 2, "cat.sch.gold": 8}


def test_lineage_diff_row_counts_per_table() -> None:
    a = _seed_run(rows_per_table={"cat.sch.t1": 100})
    b = _seed_run(rows_per_table={"cat.sch.t1": 250, "cat.sch.t2": 5})
    factory = app.state.session_factory
    diff = run_diff.build_lineage_diff(factory, run_a_id=a, run_b_id=b)
    delta = diff["row_count_delta_per_table"]["delta"]
    # Sentinel op rows are 0; only the seeded merges count.
    assert delta["cat.sch.t1"] == 150
    assert delta["cat.sch.t2"] == 5


# ---------------------------------------------------------------------
# Diff JSON endpoint extension
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_diff_json_includes_lineage_diff_when_detail_true(
    admin_client: httpx.AsyncClient,
) -> None:
    a = _seed_run(rejects_by_reason={"on_key_null": 1})
    b = _seed_run(rejects_by_reason={"on_key_null": 2})
    r = await admin_client.get(
        "/api/agent-runs/diff",
        params={"a": a, "b": b, "detail": True, "align": "content"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "lineage_diff" in body
    assert "reject_pattern_shift" in body["lineage_diff"]


@pytest.mark.asyncio
async def test_diff_json_omits_lineage_when_detail_false(admin_client: httpx.AsyncClient) -> None:
    a = _seed_run()
    b = _seed_run()
    r = await admin_client.get("/api/agent-runs/diff", params={"a": a, "b": b})
    assert r.status_code == 200
    assert "lineage_diff" not in r.json()


# ---------------------------------------------------------------------
# HTML route
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_html_diff_renders_stat_cards_and_chart_payload(
    admin_client: httpx.AsyncClient,
) -> None:
    a = _seed_run(
        rejects_by_reason={"on_key_null": 5},
        value_changes={"cat.sch.silver": 3},
        rows_per_table={"cat.sch.silver": 100},
    )
    b = _seed_run(
        rejects_by_reason={"on_key_null": 2, "schema_mismatch": 4},
        value_changes={"cat.sch.silver": 5, "cat.sch.gold": 8},
        rows_per_table={"cat.sch.silver": 200, "cat.sch.gold": 5},
    )
    r = await admin_client.get(f"/runs/{a}/diff/{b}")
    assert r.status_code == 200
    body = r.text
    assert "Compare runs" in body
    assert "lineage-diff-payload" in body
    # Stat cards
    assert "Rows touched" in body
    assert "Value changes" in body
    assert "Errored ops" in body
    assert "Rejects" in body
    # Chart canvases
    assert 'id="chart-rejects"' in body
    assert 'id="chart-value-changes"' in body


@pytest.mark.asyncio
async def test_html_diff_404_on_missing_run(admin_client: httpx.AsyncClient) -> None:
    r = await admin_client.get(f"/runs/nope-{uuid.uuid4()}/diff/{uuid.uuid4()}")
    assert r.status_code == 404
