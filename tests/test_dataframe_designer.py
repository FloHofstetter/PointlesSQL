"""Tests for the NL-prompt → DataFrame Studio pipeline generator."""

from __future__ import annotations

import json

import httpx
import pytest

from pointlessql.services import dataframe_designer
from pointlessql.services.canvas_df import ColumnSpec, PinSchema


def _orders_seed() -> PinSchema:
    return PinSchema(
        kind="table",
        columns=[
            ColumnSpec(name="id", duckdb_type="BIGINT", nullable=False),
            ColumnSpec(name="amount", duckdb_type="DECIMAL(10,2)", nullable=True),
        ],
    )


def test_build_canvas_from_plan_wires_linear_chain() -> None:
    doc, errors = dataframe_designer.build_canvas_from_plan(
        "main.s.orders",
        [
            {"block_type": "Filter", "config": {"predicate": "amount > 0"}},
            {"block_type": "Limit", "config": {"n": 10}},
        ],
        seed_schema=_orders_seed(),
    )
    assert errors == []
    assert doc is not None
    assert [n.block_type for n in doc.nodes] == ["InputPort", "Filter", "Limit"]
    assert doc.nodes[0].config == {"table_fqn": "main.s.orders"}
    # The chain is wired src.out -> filter.in -> limit.in.
    assert [(e.source_node_id, e.target_node_id) for e in doc.edges] == [
        ("n0", "n1"),
        ("n1", "n2"),
    ]


def test_build_canvas_rejects_disallowed_block() -> None:
    doc, errors = dataframe_designer.build_canvas_from_plan(
        "main.s.orders",
        [{"block_type": "Join", "config": {}}],
    )
    assert doc is None
    assert any(e.kind == "unknown_block" for e in errors)


def test_build_canvas_requires_input_table() -> None:
    doc, errors = dataframe_designer.build_canvas_from_plan("  ", [])
    assert doc is None
    assert errors[0].kind == "bad_config"


def test_seed_from_columns() -> None:
    seed = dataframe_designer.seed_from_columns(
        [{"name": "id", "duckdb_type": "BIGINT", "nullable": False}, {"name": ""}]
    )
    assert seed is not None
    assert [c.name for c in seed.columns] == ["id"]
    assert dataframe_designer.seed_from_columns([]) is None


def test_generate_pipeline_with_fake_completer() -> None:
    plan = {"steps": [{"block_type": "Filter", "config": {"predicate": "amount > 0"}}]}

    def _complete(system: str, user: str) -> str:
        assert "orders" in user
        return "Here you go: " + json.dumps(plan)

    result = dataframe_designer.generate_pipeline(
        prompt="keep positive amounts",
        input_table="main.s.orders",
        columns=[{"name": "amount", "duckdb_type": "DECIMAL(10,2)"}],
        complete=_complete,
    )
    assert result["document"] is not None
    assert result["errors"] == []
    assert result["steps"] == plan["steps"]
    block_types = [n["block_type"] for n in result["document"]["nodes"]]
    assert block_types == ["InputPort", "Filter"]


def test_generate_pipeline_handles_unparseable_reply() -> None:
    result = dataframe_designer.generate_pipeline(
        prompt="x",
        input_table="main.s.orders",
        columns=None,
        complete=lambda system, user: "sorry, I cannot help with that",
    )
    assert result["document"] is None
    assert result["errors"][0]["kind"] == "bad_config"


def test_generate_pipeline_surfaces_disallowed_block() -> None:
    plan = {"steps": [{"block_type": "Join", "config": {}}]}
    result = dataframe_designer.generate_pipeline(
        prompt="join things",
        input_table="main.s.orders",
        columns=None,
        complete=lambda system, user: json.dumps(plan),
    )
    assert result["document"] is None
    assert any(e["kind"] == "unknown_block" for e in result["errors"])


@pytest.mark.asyncio
async def test_route_rejects_empty_prompt(admin_client: httpx.AsyncClient) -> None:
    # Empty prompt is rejected by request validation before any LLM call.
    resp = await admin_client.post(
        "/api/dataframe-studio/generate",
        json={"prompt": "", "input_table": "main.s.orders"},
    )
    assert resp.status_code == 422
