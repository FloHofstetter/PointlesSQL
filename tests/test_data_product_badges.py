"""Tests for the auto-computed endorsement badges.

Covers each of the four badges:

* ``downstream_count`` reflects ``LineageColumnMap`` out-edges.
* ``agent_run_count_7d`` counts distinct runs in the 7d window
  and excludes older runs.
* ``last_rollback_passed`` reads the most recent ``rollback`` op
  and reports True/False/None.
* ``freshness_on_time_30d_pct`` drops 5pp per
  ``sla_violated`` envelope in the 30d window.

Also covers the bulk-compute helper used by the listing route
and the listing/detail JSON payload shape.
"""

from __future__ import annotations

import datetime
import json
import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.agent._audit import AgentRunOperation
from pointlessql.models.agent._runs import AgentRun
from pointlessql.models.audit._sinks import GovernanceEvent
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.lineage._core import LineageColumnMap
from pointlessql.services.data_products import (
    compute_badges_bulk,
    compute_badges_for_dp,
)

VALID_YAML = """\
data_product:
  name: Sales Orders
  version: "1.0.0"
  description: Curated orders facts.
  catalog: main
  schema: sales_gold
  steward_email: alice@example.com
  sla_minutes: 60
  tables:
    - name: orders
      primary_key: [order_id]
      columns:
        - {name: order_id, type: long, nullable: false}
"""


def _seed_dp(tmp_path: Path) -> int:
    """Seed one DP; return its id."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return session.execute(select(DataProduct)).scalar_one().id


def _seed_lineage_edge(source: str, target: str) -> None:
    """Seed one LineageColumnMap row."""
    factory = app.state.session_factory
    when = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add(
            LineageColumnMap(
                workspace_id=1,
                run_id=None,
                op_id=None,
                source_table=source,
                source_column="x",
                target_table=target,
                target_column="x",
                transform_kind="identity",
                transform_detail=None,
                producer=None,
                external_event_id=None,
                created_at=when,
            )
        )
        session.commit()


def _seed_op(
    target: str, *, op_name: str = "write_table", age_seconds: int = 0, error: str | None = None
) -> str:
    """Seed one AgentRun + Op; return the agent_run_id."""
    factory = app.state.session_factory
    when = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=age_seconds)
    with factory() as session:
        run = AgentRun(
            id=str(uuid.uuid4()),
            workspace_id=1,
            principal="t@t.com",
            agent_id="a",
            notebook_path="/x",
            status="finished",
            started_at=when,
            finished_at=when,
        )
        session.add(run)
        session.flush()
        op = AgentRunOperation(
            workspace_id=1,
            agent_run_id=run.id,
            ordinal=1,
            op_name=op_name,
            params_json="{}",
            target_table=target,
            started_at=when,
            finished_at=when,
            error_message=error,
        )
        session.add(op)
        session.commit()
        return run.id


def _seed_sla_envelope(dp_ref: str, *, age_seconds: int = 1) -> None:
    """Seed one sla_violated envelope referencing *dp_ref*."""
    factory = app.state.session_factory
    when = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=age_seconds)
    envelope = {
        "specversion": "1.0",
        "id": uuid.uuid4().hex,
        "type": "pointlessql.data_product.sla_violated",
        "data": {"data_product_ref": dp_ref},
    }
    with factory() as session:
        session.add(
            GovernanceEvent(
                workspace_id=1,
                event_id=envelope["id"],
                event_type=envelope["type"],
                fired_at=when,
                outcome="delivered",
                payload_json=json.dumps(envelope),
            )
        )
        session.commit()


# ---------------------------------------------------------------------------
# Per-badge unit tests
# ---------------------------------------------------------------------------


def test_downstream_count_zero_with_no_edges(tmp_path: Path) -> None:
    """No lineage edges → ``downstream_count == 0``."""
    _seed_dp(tmp_path)
    factory = app.state.session_factory
    with factory() as session:
        dp = session.execute(select(DataProduct)).scalar_one()
        badges = compute_badges_for_dp(session, workspace_id=1, dp=dp)
    assert badges["downstream_count"] == 0


def test_downstream_count_counts_out_edges(tmp_path: Path) -> None:
    """Edges from this DP's table to downstream tables are counted."""
    _seed_dp(tmp_path)
    _seed_lineage_edge("main.sales_gold.orders", "main.consumer_a.facts")
    _seed_lineage_edge("main.sales_gold.orders", "main.consumer_b.facts")
    factory = app.state.session_factory
    with factory() as session:
        dp = session.execute(select(DataProduct)).scalar_one()
        badges = compute_badges_for_dp(session, workspace_id=1, dp=dp)
    assert badges["downstream_count"] == 2


def test_downstream_count_excludes_internal_edges(tmp_path: Path) -> None:
    """Edges that stay inside the same DP don't inflate the count."""
    _seed_dp(tmp_path)
    _seed_lineage_edge("main.sales_gold.orders", "main.sales_gold.orders_audit")
    factory = app.state.session_factory
    with factory() as session:
        dp = session.execute(select(DataProduct)).scalar_one()
        badges = compute_badges_for_dp(session, workspace_id=1, dp=dp)
    assert badges["downstream_count"] == 0


def test_agent_run_count_7d_within_window(tmp_path: Path) -> None:
    """Runs in the 7d window count; runs older do not."""
    _seed_dp(tmp_path)
    _seed_op("main.sales_gold.orders", age_seconds=60)  # in window
    _seed_op("main.sales_gold.orders", age_seconds=8 * 86400)  # outside
    factory = app.state.session_factory
    with factory() as session:
        dp = session.execute(select(DataProduct)).scalar_one()
        badges = compute_badges_for_dp(session, workspace_id=1, dp=dp)
    assert badges["agent_run_count_7d"] == 1


def test_last_rollback_none_when_no_rollback(tmp_path: Path) -> None:
    """No rollback ops → ``last_rollback_passed is None``."""
    _seed_dp(tmp_path)
    factory = app.state.session_factory
    with factory() as session:
        dp = session.execute(select(DataProduct)).scalar_one()
        badges = compute_badges_for_dp(session, workspace_id=1, dp=dp)
    assert badges["last_rollback_passed"] is None


def test_last_rollback_passed_true_on_clean_rollback(tmp_path: Path) -> None:
    """Most recent rollback with no ``error_message`` → True."""
    _seed_dp(tmp_path)
    _seed_op("main.sales_gold.orders", op_name="rollback", error=None)
    factory = app.state.session_factory
    with factory() as session:
        dp = session.execute(select(DataProduct)).scalar_one()
        badges = compute_badges_for_dp(session, workspace_id=1, dp=dp)
    assert badges["last_rollback_passed"] is True


def test_last_rollback_passed_false_on_errored_rollback(tmp_path: Path) -> None:
    """Most recent rollback with an error → False."""
    _seed_dp(tmp_path)
    _seed_op("main.sales_gold.orders", op_name="rollback", error="boom")
    factory = app.state.session_factory
    with factory() as session:
        dp = session.execute(select(DataProduct)).scalar_one()
        badges = compute_badges_for_dp(session, workspace_id=1, dp=dp)
    assert badges["last_rollback_passed"] is False


def test_freshness_100_when_no_violations(tmp_path: Path) -> None:
    """No sla_violated envelopes → 100%."""
    _seed_dp(tmp_path)
    factory = app.state.session_factory
    with factory() as session:
        dp = session.execute(select(DataProduct)).scalar_one()
        badges = compute_badges_for_dp(session, workspace_id=1, dp=dp)
    assert badges["freshness_on_time_30d_pct"] == 100.0


def test_freshness_drops_per_violation(tmp_path: Path) -> None:
    """Each sla_violated envelope drops 5pp; 2 → 90%."""
    _seed_dp(tmp_path)
    _seed_sla_envelope("main.sales_gold")
    _seed_sla_envelope("main.sales_gold", age_seconds=2)
    factory = app.state.session_factory
    with factory() as session:
        dp = session.execute(select(DataProduct)).scalar_one()
        badges = compute_badges_for_dp(session, workspace_id=1, dp=dp)
    assert badges["freshness_on_time_30d_pct"] == 90.0


# ---------------------------------------------------------------------------
# Bulk + listing payload
# ---------------------------------------------------------------------------


def test_compute_badges_bulk_empty(tmp_path: Path) -> None:
    """Empty input → empty output."""
    factory = app.state.session_factory
    with factory() as session:
        result = compute_badges_bulk(session, workspace_id=1, dps=[])
    assert result == {}


@pytest.mark.asyncio
async def test_listing_includes_badges_field(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """``GET /api/data-products`` carries the new ``badges`` field."""
    _seed_dp(tmp_path)
    res = await admin_client.get("/api/data-products")
    assert res.status_code == 200
    products = res.json()["data_products"]
    assert len(products) == 1
    assert "badges" in products[0]
    for key in (
        "downstream_count",
        "agent_run_count_7d",
        "last_rollback_passed",
        "freshness_on_time_30d_pct",
    ):
        assert key in products[0]["badges"]


@pytest.mark.asyncio
async def test_detail_includes_badges_field(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """``GET /api/data-products/{cat}/{sch}`` carries the new ``badges`` field."""
    _seed_dp(tmp_path)
    res = await admin_client.get("/api/data-products/main/sales_gold")
    assert res.status_code == 200
    body = res.json()
    assert "badges" in body
    assert body["badges"]["downstream_count"] == 0
