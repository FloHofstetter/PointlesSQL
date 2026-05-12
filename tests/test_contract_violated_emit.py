"""Tests for the Phase-71 follow-up B.2 — contract_violated emit.

The post-commit hook
:func:`pointlessql.services.agent_runs.operations._contract_events.record_contract_event_after_commit`
now schedules a fire-and-forget ``emit_governance_event`` task
when the outcome is ``violated`` and an event loop is running.

Covers:

* Compliant outcome → no governance event (only the row).
* Violated outcome inside an event loop → exactly one
  ``EVENT_TYPE_DATA_PRODUCT_CONTRACT_VIOLATED`` envelope in
  ``governance_events``.
* Violated outcome outside an event loop → row still persists,
  no crash, no envelope (best-effort streaming).
"""

from __future__ import annotations

import asyncio
import datetime
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.agent._audit import AgentRunOperation
from pointlessql.models.agent._runs import AgentRun
from pointlessql.models.audit._sinks import GovernanceEvent
from pointlessql.models.catalog._data_products import (
    DataProduct,
    DataProductContractEvent,
)
from pointlessql.services.agent_runs.operations._contract_events import (
    record_contract_event_after_commit,
)
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_DATA_PRODUCT_CONTRACT_VIOLATED,
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
    """Seed one data product; return its id."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return session.execute(select(DataProduct)).scalar_one().id


def _seed_run_and_op() -> int:
    """Seed one AgentRun + AgentRunOperation; return the op id."""
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        run = AgentRun(
            id=str(uuid.uuid4()),
            workspace_id=1,
            principal="test@test.com",
            agent_id="test-agent",
            notebook_path="/tmp/test.py",
            status="finished",
            started_at=now,
            finished_at=now,
        )
        session.add(run)
        session.flush()
        op = AgentRunOperation(
            workspace_id=1,
            agent_run_id=run.id,
            ordinal=1,
            op_name="write_table",
            params_json="{}",
            target_table="main.sales_gold.orders",
            started_at=now,
            finished_at=now,
        )
        session.add(op)
        session.commit()
        return op.id


def _count_violated_envelopes() -> int:
    """Count contract_violated envelopes in governance_events."""
    factory = app.state.session_factory
    with factory() as session:
        return len(
            session.execute(
                select(GovernanceEvent).where(
                    GovernanceEvent.event_type
                    == EVENT_TYPE_DATA_PRODUCT_CONTRACT_VIOLATED
                )
            )
            .scalars()
            .all()
        )


def _count_dp_contract_events() -> int:
    """Count rows in the authoritative per-write audit table."""
    factory = app.state.session_factory
    with factory() as session:
        return len(
            session.execute(select(DataProductContractEvent)).scalars().all()
        )


@pytest.mark.asyncio
async def test_compliant_outcome_no_emit(tmp_path: Path) -> None:
    """Compliant writes record the row but skip the streaming envelope."""
    dp_id = _seed_dp(tmp_path)
    op_id = _seed_run_and_op()
    record_contract_event_after_commit(
        app.state.session_factory,
        op_id=op_id,
        pending=("compliant", {"info": "ok"}, dp_id),
    )
    await asyncio.sleep(0)  # let any spuriously-scheduled task run
    assert _count_dp_contract_events() == 1
    assert _count_violated_envelopes() == 0


@pytest.mark.asyncio
async def test_violated_outcome_emits_once(tmp_path: Path) -> None:
    """Violated writes record the row AND schedule one envelope."""
    dp_id = _seed_dp(tmp_path)
    op_id = _seed_run_and_op()
    record_contract_event_after_commit(
        app.state.session_factory,
        op_id=op_id,
        pending=("violated", {"breaking": True, "mode": "overwrite"}, dp_id),
    )
    # The hook schedules via loop.create_task; yield long enough for
    # the fire-and-forget coroutine to persist the envelope row.
    await asyncio.sleep(0.05)
    assert _count_dp_contract_events() == 1
    assert _count_violated_envelopes() == 1


def test_violated_outcome_outside_event_loop(tmp_path: Path) -> None:
    """When no loop is running, the row still persists; no crash."""
    dp_id = _seed_dp(tmp_path)
    op_id = _seed_run_and_op()
    record_contract_event_after_commit(
        app.state.session_factory,
        op_id=op_id,
        pending=("violated", {"breaking": True}, dp_id),
    )
    assert _count_dp_contract_events() == 1
    assert _count_violated_envelopes() == 0
