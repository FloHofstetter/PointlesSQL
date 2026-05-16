"""Tests for the Phase-72.1 data-product activity feed.

Covers:

* Each of the 4 streams contributes when present
  (agent_op / audit / contract / freshness).
* Sort order is newest-first.
* Pagination (limit / offset).
* ``source_url`` shape per stream.
* Cross-workspace isolation.
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
from pointlessql.models.audit._log import AuditLog
from pointlessql.models.audit._sinks import GovernanceEvent
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_products import (
    DataProduct,
    DataProductContractEvent,
)
from pointlessql.models.workspace import Workspace, WorkspaceMember

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
    """Seed one data product; return its id."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return session.execute(select(DataProduct)).scalar_one().id


def _seed_agent_op(target_table: str, *, age_seconds: int = 0) -> int:
    """Seed one AgentRun + AgentRunOperation hitting *target_table*."""
    factory = app.state.session_factory
    when = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=age_seconds)
    with factory() as session:
        run = AgentRun(
            id=str(uuid.uuid4()),
            workspace_id=1,
            principal="test@test.com",
            agent_id="test-agent",
            notebook_path="/tmp/test.py",
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
            op_name="write_table",
            params_json="{}",
            target_table=target_table,
            rows_affected=42,
            started_at=when,
            finished_at=when,
        )
        session.add(op)
        session.commit()
        return op.id


def _seed_audit_row(target: str, *, age_seconds: int = 1) -> int:
    """Seed one AuditLog row."""
    factory = app.state.session_factory
    when = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=age_seconds)
    with factory() as session:
        row = AuditLog(
            workspace_id=1,
            user_id=1,
            user_email="test@test.com",
            actor_role="user",
            action="update_catalog",
            target=target,
            client_ip=None,
            detail=None,
            created_at=when,
        )
        session.add(row)
        session.commit()
        return row.id


def _seed_contract_event(dp_id: int, *, age_seconds: int = 2) -> int:
    """Seed one DataProductContractEvent (with a backing op row)."""
    op_id = _seed_agent_op("main.sales_gold.orders", age_seconds=age_seconds)
    factory = app.state.session_factory
    when = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=age_seconds)
    with factory() as session:
        ev = DataProductContractEvent(
            agent_run_operation_id=op_id,
            data_product_id=dp_id,
            outcome="compliant",
            details_json="{}",
            created_at=when,
        )
        session.add(ev)
        session.commit()
        return ev.id


def _seed_freshness_envelope(dp_ref: str, *, age_seconds: int = 3) -> int:
    """Seed one sla_violated governance event for *dp_ref*."""
    factory = app.state.session_factory
    when = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=age_seconds)
    envelope = {
        "specversion": "1.0",
        "id": uuid.uuid4().hex,
        "source": "/pointlessql/governance",
        "type": "pointlessql.data_product.sla_violated",
        "time": when.isoformat(),
        "data": {"data_product_ref": dp_ref, "age_minutes": 99},
    }
    with factory() as session:
        ev = GovernanceEvent(
            workspace_id=1,
            event_id=envelope["id"],
            event_type=envelope["type"],
            fired_at=when,
            outcome="delivered",
            payload_json=json.dumps(envelope),
        )
        session.add(ev)
        session.commit()
        return ev.id


# ---------------------------------------------------------------------------
# Streams
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_feed_when_no_activity(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Empty feed serializes as ``activity: []``."""
    _seed_dp(tmp_path)
    res = await admin_client.get("/api/data-products/main/sales_gold/activity")
    assert res.status_code == 200
    assert res.json()["activity"] == []


@pytest.mark.asyncio
async def test_agent_op_stream_contributes(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """An ``AgentRunOperation`` hitting the DP appears in the feed."""
    _seed_dp(tmp_path)
    _seed_agent_op("main.sales_gold.orders")
    res = await admin_client.get("/api/data-products/main/sales_gold/activity")
    body = res.json()
    assert len(body["activity"]) == 1
    assert body["activity"][0]["kind"] == "agent_op"
    assert "/runs/" in body["activity"][0]["source_url"]


@pytest.mark.asyncio
async def test_audit_stream_contributes(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """An ``AuditLog`` row mentioning the DP catalog appears."""
    _seed_dp(tmp_path)
    _seed_audit_row("catalog:main")
    res = await admin_client.get("/api/data-products/main/sales_gold/activity")
    kinds = {row["kind"] for row in res.json()["activity"]}
    assert "audit" in kinds


@pytest.mark.asyncio
async def test_contract_stream_contributes(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """A ``DataProductContractEvent`` for the DP appears."""
    dp_id = _seed_dp(tmp_path)
    _seed_contract_event(dp_id)
    res = await admin_client.get("/api/data-products/main/sales_gold/activity")
    kinds = {row["kind"] for row in res.json()["activity"]}
    assert "contract" in kinds


@pytest.mark.asyncio
async def test_freshness_stream_contributes(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """An ``sla_violated`` envelope for the DP appears."""
    _seed_dp(tmp_path)
    _seed_freshness_envelope("main.sales_gold")
    res = await admin_client.get("/api/data-products/main/sales_gold/activity")
    kinds = {row["kind"] for row in res.json()["activity"]}
    assert "freshness" in kinds


@pytest.mark.asyncio
async def test_freshness_envelope_for_other_dp_is_ignored(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """An envelope referencing a different DP-ref is filtered out."""
    _seed_dp(tmp_path)
    _seed_freshness_envelope("main.unrelated_schema")
    res = await admin_client.get("/api/data-products/main/sales_gold/activity")
    assert res.json()["activity"] == []


# ---------------------------------------------------------------------------
# Merge + pagination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feed_sorted_newest_first(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Merged rows are returned in descending timestamp order."""
    dp_id = _seed_dp(tmp_path)
    _seed_agent_op("main.sales_gold.orders", age_seconds=10)  # oldest
    _seed_contract_event(dp_id, age_seconds=5)
    _seed_freshness_envelope("main.sales_gold", age_seconds=1)  # newest
    res = await admin_client.get("/api/data-products/main/sales_gold/activity")
    items = res.json()["activity"]
    timestamps = [r["ts"] for r in items]
    assert timestamps == sorted(timestamps, reverse=True)


@pytest.mark.asyncio
async def test_feed_pagination(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """``limit`` and ``offset`` work end-to-end."""
    dp_id = _seed_dp(tmp_path)
    for i in range(5):
        _seed_contract_event(dp_id, age_seconds=i + 1)
    page1 = await admin_client.get(
        "/api/data-products/main/sales_gold/activity?limit=2&offset=0"
    )
    page2 = await admin_client.get(
        "/api/data-products/main/sales_gold/activity?limit=2&offset=2"
    )
    assert len(page1.json()["activity"]) == 2
    assert len(page2.json()["activity"]) == 2
    page1_ids = {r["source_id"] for r in page1.json()["activity"]}
    page2_ids = {r["source_id"] for r in page2.json()["activity"]}
    assert page1_ids.isdisjoint(page2_ids)


# ---------------------------------------------------------------------------
# Auth + cross-workspace
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anonymous_blocked(
    tmp_path: Path, anonymous_client: httpx.AsyncClient
) -> None:
    """Anonymous users can't read the feed."""
    _seed_dp(tmp_path)
    res = await anonymous_client.get(
        "/api/data-products/main/sales_gold/activity"
    )
    assert res.status_code in (401, 403, 303)


@pytest.mark.asyncio
async def test_cross_workspace_isolation(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """A second workspace cannot reach a workspace-1 DP's feed."""
    _seed_dp(tmp_path)
    _seed_agent_op("main.sales_gold.orders")
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add(
            Workspace(
                id=2, slug="second", name="Second",
                description="iso", created_at=now,
            )
        )
        nonadmin = session.execute(
            select(User).where(User.email == "nonadmin@test.com")
        ).scalar_one()
        session.add(
            WorkspaceMember(
                workspace_id=2, user_id=nonadmin.id, role="member",
                created_at=now,
            )
        )
        nonadmin.default_workspace_id = 2
        session.add(nonadmin)
        session.commit()
    res = await non_admin_client.get(
        "/api/data-products/main/sales_gold/activity",
        headers={"X-Workspace": "second"},
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Template fingerprint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detail_page_includes_activity_tab(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """The DP detail page now ships an Activity tab + pane."""
    _seed_dp(tmp_path)
    res = await admin_client.get("/data-products/main/sales_gold")
    assert res.status_code == 200
    assert 'data-pql-tab-key="activity"' in res.text
    assert 'id="tab-activity"' in res.text
