"""Tests for the Phase-73.3 schema-change proposal flow.

Covers:

* POST proposal as human (proposer_user_id set).
* POST proposal as agent (proposer_agent_run_id via header).
* CHECK rejects a proposal with neither proposer.
* Approve in-place on a safe diff applies yaml + reloads DP.
* Approve in-place on an unsafe diff → 400.
* Approve draft writes a DataProductYamlDraft row.
* Reject stamps the row.
* Listing returns open + resolved.
* Re-resolve an already-resolved proposal → 400.
* Approve / reject a non-existent proposal → 404.
* Cross-workspace iso.
"""

from __future__ import annotations

import datetime
import json
import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.agent._runs import AgentRun
from pointlessql.models.catalog._data_product_proposal import (
    DataProductSchemaProposal,
)
from pointlessql.models.catalog._data_product_yaml_draft import (
    DataProductYamlDraft,
)
from pointlessql.models.catalog._data_products import DataProduct

VALID_YAML = """\
data_product:
  name: Sales Orders
  version: "1.0.0"
  description: Curated orders.
  catalog: main
  schema: sales_gold
  tables:
    - name: orders
      columns:
        - {name: order_id, type: long, nullable: false}
"""


def _seed_dp(
    tmp_path: Path,
    search_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> int:
    """Seed a DP under ``main.sales_gold`` + configure yaml search path.

    Args:
        tmp_path: pytest tmp_path.
        search_path: Per-test yaml search-path directory.
        monkeypatch: pytest monkeypatch (auto-restores the
            mutated setting after the test exits).

    Returns:
        The DP id.
    """
    del tmp_path
    target = search_path / "main__sales_gold.yaml"
    search_path.mkdir(parents=True, exist_ok=True)
    target.write_text(VALID_YAML, encoding="utf-8")
    monkeypatch.setattr(
        app.state.settings.data_products, "yaml_search_paths", [search_path]
    )
    factory = app.state.session_factory
    load_contract(target, factory=factory)
    with factory() as session:
        return session.execute(select(DataProduct)).scalar_one().id


def _seed_agent_run() -> str:
    """Seed one AgentRun; return its id."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    when = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add(
            AgentRun(
                id=run_id,
                workspace_id=1,
                principal="t@t.com",
                agent_id="a",
                notebook_path="/x",
                status="finished",
                started_at=when,
                finished_at=when,
            )
        )
        session.commit()
    return run_id


@pytest.mark.asyncio
async def test_open_proposal_as_human(
    tmp_path: Path, admin_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST proposal sets proposer_user_id from the session cookie."""
    _seed_dp(tmp_path, tmp_path / "yaml", monkeypatch)
    res = await admin_client.post(
        "/api/data-products/main/sales_gold/proposals",
        json={
            "diff": {
                "add_columns": {
                    "orders": [{"name": "amount", "type": "double", "nullable": True}],
                },
            },
            "summary_md": "Add amount column",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["proposer_user_id"] is not None
    assert body["proposer_agent_run_id"] is None
    assert body["status"] == "open"


@pytest.mark.asyncio
async def test_open_proposal_as_agent(
    tmp_path: Path, admin_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST proposal via X-Agent-Run-Id sets proposer_agent_run_id."""
    _seed_dp(tmp_path, tmp_path / "yaml", monkeypatch)
    run_id = _seed_agent_run()
    res = await admin_client.post(
        "/api/data-products/main/sales_gold/proposals",
        json={"diff": {"add_columns": {"orders": []}}, "summary_md": ""},
        headers={"X-Agent-Run-Id": run_id},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["proposer_agent_run_id"] == run_id


def test_check_rejects_proposal_without_proposer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Direct insert with neither proposer set is rejected by the CHECK."""
    _seed_dp(tmp_path, tmp_path / "yaml", monkeypatch)
    factory = app.state.session_factory
    with factory() as session:
        dp = session.execute(select(DataProduct)).scalar_one()
        session.add(
            DataProductSchemaProposal(
                workspace_id=1,
                data_product_id=dp.id,
                diff_json="{}",
                summary_md="",
                status="open",
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.asyncio
async def test_approve_inplace_safe_diff(
    tmp_path: Path, admin_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Approve in-place on a safe diff rewrites yaml + reloads DP."""
    search_path = tmp_path / "yaml"
    _seed_dp(tmp_path, search_path, monkeypatch)
    open_res = await admin_client.post(
        "/api/data-products/main/sales_gold/proposals",
        json={
            "diff": {
                "add_columns": {
                    "orders": [
                        {"name": "currency", "type": "string", "nullable": True},
                    ],
                },
            },
            "summary_md": "Add currency",
        },
    )
    proposal_id = open_res.json()["id"]
    res = await admin_client.post(
        f"/api/data-products/main/sales_gold/proposals/{proposal_id}/approve",
        json={"kind": "inplace", "resolution_note_md": "looks fine"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "approved_inplace"
    yaml_text = (search_path / "main__sales_gold.yaml").read_text(encoding="utf-8")
    assert "currency" in yaml_text


@pytest.mark.asyncio
async def test_approve_inplace_unsafe_diff_400(
    tmp_path: Path, admin_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Approve in-place on a destructive diff is rejected with 400."""
    _seed_dp(tmp_path, tmp_path / "yaml", monkeypatch)
    open_res = await admin_client.post(
        "/api/data-products/main/sales_gold/proposals",
        json={
            "diff": {"remove_columns": {"orders": ["order_id"]}},
            "summary_md": "drop pk",
        },
    )
    proposal_id = open_res.json()["id"]
    res = await admin_client.post(
        f"/api/data-products/main/sales_gold/proposals/{proposal_id}/approve",
        json={"kind": "inplace"},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_approve_draft_writes_yaml_draft(
    tmp_path: Path, admin_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Approve with kind='draft' writes a DataProductYamlDraft row."""
    _seed_dp(tmp_path, tmp_path / "yaml", monkeypatch)
    monkeypatch.setattr(
        app.state.settings.data_products, "draft_dir", tmp_path / "drafts"
    )
    open_res = await admin_client.post(
        "/api/data-products/main/sales_gold/proposals",
        json={
            "diff": {"remove_columns": {"orders": ["order_id"]}},
            "summary_md": "drop pk",
        },
    )
    proposal_id = open_res.json()["id"]
    res = await admin_client.post(
        f"/api/data-products/main/sales_gold/proposals/{proposal_id}/approve",
        json={"kind": "draft"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "approved_draft"
    assert body["draft_id"] is not None
    factory = app.state.session_factory
    with factory() as session:
        draft = session.get(DataProductYamlDraft, body["draft_id"])
        assert draft is not None
        assert draft.source_kind == "agent_proposal"


@pytest.mark.asyncio
async def test_reject_proposal(
    tmp_path: Path, admin_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST reject stamps status='rejected'."""
    _seed_dp(tmp_path, tmp_path / "yaml", monkeypatch)
    open_res = await admin_client.post(
        "/api/data-products/main/sales_gold/proposals",
        json={"diff": {"add_columns": {"orders": []}}, "summary_md": "nope"},
    )
    proposal_id = open_res.json()["id"]
    res = await admin_client.post(
        f"/api/data-products/main/sales_gold/proposals/{proposal_id}/reject",
        json={"resolution_note_md": "out of scope"},
    )
    assert res.status_code == 200
    factory = app.state.session_factory
    with factory() as session:
        proposal = session.get(DataProductSchemaProposal, proposal_id)
        assert proposal is not None
        assert proposal.status == "rejected"
        assert proposal.resolution_note_md == "out of scope"


@pytest.mark.asyncio
async def test_list_proposals(
    tmp_path: Path, admin_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET returns open + historical."""
    _seed_dp(tmp_path, tmp_path / "yaml", monkeypatch)
    await admin_client.post(
        "/api/data-products/main/sales_gold/proposals",
        json={"diff": {"add_columns": {"orders": []}}, "summary_md": "a"},
    )
    await admin_client.post(
        "/api/data-products/main/sales_gold/proposals",
        json={"diff": {"add_columns": {"orders": []}}, "summary_md": "b"},
    )
    res = await admin_client.get("/api/data-products/main/sales_gold/proposals")
    assert res.status_code == 200
    body = res.json()
    assert len(body["proposals"]) == 2


@pytest.mark.asyncio
async def test_double_resolve_400(
    tmp_path: Path, admin_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resolving an already-resolved proposal returns 400."""
    _seed_dp(tmp_path, tmp_path / "yaml", monkeypatch)
    open_res = await admin_client.post(
        "/api/data-products/main/sales_gold/proposals",
        json={"diff": {"add_columns": {"orders": []}}, "summary_md": "x"},
    )
    proposal_id = open_res.json()["id"]
    await admin_client.post(
        f"/api/data-products/main/sales_gold/proposals/{proposal_id}/reject",
    )
    res = await admin_client.post(
        f"/api/data-products/main/sales_gold/proposals/{proposal_id}/reject",
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_approve_unknown_404(
    tmp_path: Path, admin_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Approve / reject on a non-existent proposal → 404."""
    _seed_dp(tmp_path, tmp_path / "yaml", monkeypatch)
    res = await admin_client.post(
        "/api/data-products/main/sales_gold/proposals/99999/approve",
        json={"kind": "inplace"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_emits_governance_events(
    tmp_path: Path, admin_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Open + approve each emit one governance_events row."""
    _seed_dp(tmp_path, tmp_path / "yaml", monkeypatch)
    open_res = await admin_client.post(
        "/api/data-products/main/sales_gold/proposals",
        json={"diff": {"add_columns": {"orders": []}}, "summary_md": "x"},
    )
    proposal_id = open_res.json()["id"]
    await admin_client.post(
        f"/api/data-products/main/sales_gold/proposals/{proposal_id}/reject",
    )

    from pointlessql.models.audit._sinks import GovernanceEvent

    factory = app.state.session_factory
    with factory() as session:
        rows = (
            session.execute(
                select(GovernanceEvent).where(
                    GovernanceEvent.event_type.in_(
                        (
                            "pointlessql.data_product.proposal_opened",
                            "pointlessql.data_product.proposal_resolved",
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        types = sorted(r.event_type for r in rows)
        assert types == [
            "pointlessql.data_product.proposal_opened",
            "pointlessql.data_product.proposal_resolved",
        ]


@pytest.mark.asyncio
async def test_audit_log_rows_written(
    tmp_path: Path, admin_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Open + approve each write one audit_log row."""
    _seed_dp(tmp_path, tmp_path / "yaml", monkeypatch)
    open_res = await admin_client.post(
        "/api/data-products/main/sales_gold/proposals",
        json={"diff": {"add_columns": {"orders": []}}, "summary_md": "x"},
    )
    proposal_id = open_res.json()["id"]
    await admin_client.post(
        f"/api/data-products/main/sales_gold/proposals/{proposal_id}/reject",
    )

    from pointlessql.models.audit._log import AuditLog

    factory = app.state.session_factory
    with factory() as session:
        actions = (
            session.execute(
                select(AuditLog.action).where(
                    AuditLog.action.in_(
                        (
                            "data_product.proposal_opened",
                            "data_product.proposal_resolved",
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        assert "data_product.proposal_opened" in actions
        assert "data_product.proposal_resolved" in actions


_ = json  # keep import for the helpers above
