"""Tests for Sprint 18.1 cross-axis ``?op_id=`` filter.

Covers:

* The three load helpers (``_load_operations_for_run``,
  ``load_rejects_for_run``, ``load_lineage_summary_for_run``)
  honour the optional ``op_id`` keyword.
* The ``/runs/{run_id}`` HTML route accepts ``?op_id=`` as a query
  param and renders the filter chip.
* A stale or non-matching ``op_id`` falls back to the unfiltered
  view rather than 404 (cockpit drill-downs are permissive).
"""

from __future__ import annotations

import datetime
import uuid
from unittest.mock import MagicMock

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.api.runs_routes import (
    _load_operations_for_run,
    load_lineage_summary_for_run,
    load_rejects_for_run,
)
from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    AgentRunSource,
    LineageRowEdge,
    LineageRowReject,
)


@pytest.fixture
def now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


@pytest.fixture(autouse=True)
def _stub_uc_client() -> None:
    """Make ``app.state.uc_client`` a no-op stub so the run-detail
    template render can resolve ``soyuz_audit.fetch_for_run`` (which
    swallows transport errors and returns ``[]`` on its own).

    The shared conftest sets up the session factory but not the soyuz
    client; production lifespan does both.  Cockpit tests don't need
    real soyuz responses so a bare ``MagicMock`` is enough.
    """
    app.state.uc_client = MagicMock()


def _seed_run_with_two_ops(
    now: datetime.datetime,
) -> tuple[str, int, int]:
    """Create one run and two operations.  Return ``(run_id, op1, op2)``."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    with factory() as s:
        run = AgentRun(
            id=run_id,
            principal="alice@example.com",
            agent_id="etl",
            notebook_path="nb.py",
            status="succeeded",
            started_at=now,
            finished_at=now,
        )
        s.add(run)
        # Source row — required so /runs/{id} doesn't 404.
        s.add(
            AgentRunSource(
                agent_run_id=run_id,
                source_bytes="print('seed')\n",
                source_sha="0" * 64,
                captured_at=now,
            )
        )
        op1 = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=1,
            op_name="merge",
            params_json="{}",
            target_table="cat.sch.t1",
            rows_affected=10,
            started_at=now,
            finished_at=now,
        )
        op2 = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=2,
            op_name="merge",
            params_json="{}",
            target_table="cat.sch.t2",
            rows_affected=20,
            started_at=now,
            finished_at=now,
        )
        s.add_all([op1, op2])
        s.commit()
        s.refresh(op1)
        s.refresh(op2)
        return run_id, op1.id, op2.id


def _seed_rejects_and_edges(
    now: datetime.datetime,
    *,
    run_id: str,
    op_id: int,
    rejects: int,
    edges: int,
) -> None:
    factory = app.state.session_factory
    with factory() as s:
        for j in range(rejects):
            s.add(
                LineageRowReject(
                    run_id=run_id,
                    op_id=op_id,
                    source_table="cat.sch.bronze",
                    source_row_id=f"r{op_id}_{j}",
                    reason="on_key_null",
                    created_at=now,
                )
            )
        for k in range(edges):
            s.add(
                LineageRowEdge(
                    run_id=run_id,
                    op_id=op_id,
                    source_table="cat.sch.bronze",
                    source_row_id=f"src{op_id}_{k}",
                    target_table=f"cat.sch.t{op_id}",
                    target_row_id=f"tgt{op_id}_{k}",
                    created_at=now,
                )
            )
        s.commit()


def test_load_operations_filters_to_single_op(now: datetime.datetime) -> None:
    run_id, op1, op2 = _seed_run_with_two_ops(now)

    class _R:
        app = app

    full = _load_operations_for_run(_R(), run_id)  # type: ignore[arg-type]
    assert len(full) == 2

    one = _load_operations_for_run(_R(), run_id, op_id=op1)  # type: ignore[arg-type]
    assert len(one) == 1
    assert one[0]["id"] == op1
    assert one[0]["ordinal"] == 1


def test_load_rejects_filters_to_single_op(now: datetime.datetime) -> None:
    run_id, op1, op2 = _seed_run_with_two_ops(now)
    _seed_rejects_and_edges(now, run_id=run_id, op_id=op1, rejects=3, edges=0)
    _seed_rejects_and_edges(now, run_id=run_id, op_id=op2, rejects=5, edges=0)

    class _R:
        app = app

    full = load_rejects_for_run(_R(), run_id)  # type: ignore[arg-type]
    assert len(full) == 8

    only_op1 = load_rejects_for_run(_R(), run_id, op_id=op1)  # type: ignore[arg-type]
    assert len(only_op1) == 3
    assert all(r["op_id"] == op1 for r in only_op1)


def test_load_lineage_summary_filters_to_single_op(now: datetime.datetime) -> None:
    run_id, op1, op2 = _seed_run_with_two_ops(now)
    _seed_rejects_and_edges(now, run_id=run_id, op_id=op1, rejects=0, edges=4)
    _seed_rejects_and_edges(now, run_id=run_id, op_id=op2, rejects=0, edges=7)

    class _R:
        app = app

    full = load_lineage_summary_for_run(_R(), run_id)  # type: ignore[arg-type]
    assert full["total_edges"] == 11

    only_op1 = load_lineage_summary_for_run(_R(), run_id, op_id=op1)  # type: ignore[arg-type]
    assert only_op1["total_edges"] == 4


@pytest.mark.asyncio
async def test_run_detail_html_renders_filter_chip(now: datetime.datetime) -> None:
    run_id, op1, _op2 = _seed_run_with_two_ops(now)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        r = await client.get(f"/runs/{run_id}", params={"op_id": op1})
    assert r.status_code == 200
    assert "Filtered to operation" in r.text
    assert "Clear filter" in r.text
    # Ordinal 1 is rendered in the chip.
    assert "<strong>#1</strong>" in r.text


@pytest.mark.asyncio
async def test_run_detail_html_no_chip_when_filter_absent(now: datetime.datetime) -> None:
    run_id, _op1, _op2 = _seed_run_with_two_ops(now)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        r = await client.get(f"/runs/{run_id}")
    assert r.status_code == 200
    assert "Filtered to operation" not in r.text


@pytest.mark.asyncio
async def test_run_detail_stale_op_id_falls_back_to_unfiltered(now: datetime.datetime) -> None:
    run_id, _op1, _op2 = _seed_run_with_two_ops(now)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        r = await client.get(f"/runs/{run_id}", params={"op_id": 999_999})
    assert r.status_code == 200
    # No chip, because the op_id didn't match.
    assert "Filtered to operation" not in r.text
