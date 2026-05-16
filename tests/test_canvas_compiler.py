"""Phase 85.1 — Canvas → PQL compiler unit + route smoke tests."""

from __future__ import annotations

import httpx
import pytest

from pointlessql.services.canvas import compile_nodes


def test_compiler_renders_full_pipeline() -> None:
    """A full read → filter → group → write chain renders cleanly."""
    code, errors = compile_nodes(
        [
            {"kind": "read_dp", "config": {"table_fqn": "main.sales.orders"}},
            {"kind": "filter", "config": {"predicate": "country == 'DE'"}},
            {
                "kind": "group_by",
                "config": {
                    "columns": ["country"],
                    "aggregates": {"amount": "sum"},
                },
            },
            {
                "kind": "write_dp",
                "config": {
                    "target_fqn": "main.sales_gold.orders_de",
                    "mode": "overwrite",
                },
            },
        ]
    )
    assert errors == []
    assert "PQL()" in code
    assert "main.sales.orders" in code
    assert "main.sales_gold.orders_de" in code
    assert "groupby" in code


def test_compiler_rejects_empty_canvas() -> None:
    """An empty list yields a clear error."""
    _, errors = compile_nodes([])
    assert errors


def test_compiler_requires_read_dp_first() -> None:
    """Pipeline must start with read_dp."""
    _, errors = compile_nodes(
        [
            {"kind": "filter", "config": {"predicate": "x > 0"}},
            {
                "kind": "write_dp",
                "config": {"target_fqn": "main.s.t", "mode": "append"},
            },
        ]
    )
    assert any("read_dp" in e for e in errors)


def test_compiler_requires_sink_last() -> None:
    """Pipeline must end with write_dp or run_model."""
    _, errors = compile_nodes(
        [
            {"kind": "read_dp", "config": {"table_fqn": "main.s.t"}},
            {"kind": "filter", "config": {"predicate": "x > 0"}},
        ]
    )
    assert any("write_dp" in e for e in errors)


def test_compiler_rejects_write_in_middle() -> None:
    """write_dp may only appear at the tail."""
    _, errors = compile_nodes(
        [
            {"kind": "read_dp", "config": {"table_fqn": "main.s.t"}},
            {
                "kind": "write_dp",
                "config": {"target_fqn": "main.x.y", "mode": "append"},
            },
            {
                "kind": "write_dp",
                "config": {"target_fqn": "main.x.z", "mode": "append"},
            },
        ]
    )
    assert errors


def test_compiler_rejects_bad_fqn() -> None:
    """Non-three-part table_fqn raises."""
    _, errors = compile_nodes(
        [
            {"kind": "read_dp", "config": {"table_fqn": "orders"}},
            {
                "kind": "write_dp",
                "config": {"target_fqn": "main.s.t", "mode": "append"},
            },
        ]
    )
    assert any("table_fqn" in e for e in errors)


def test_compiler_renders_run_model_tail() -> None:
    """A read → run_model pipeline renders without write_dp."""
    code, errors = compile_nodes(
        [
            {"kind": "read_dp", "config": {"table_fqn": "main.s.t"}},
            {
                "kind": "run_model",
                "config": {"model_uri": "models:/fraud/Production"},
            },
        ]
    )
    assert errors == []
    assert "run_model" in code
    assert "predictions" in code


def test_compiler_renders_merge_write() -> None:
    """write_dp with mode='merge' wires through to pql.merge."""
    code, errors = compile_nodes(
        [
            {"kind": "read_dp", "config": {"table_fqn": "main.s.t"}},
            {
                "kind": "write_dp",
                "config": {
                    "target_fqn": "main.s.u",
                    "mode": "merge",
                    "on": "id",
                },
            },
        ]
    )
    assert errors == []
    assert "pql.merge" in code


@pytest.mark.asyncio
async def test_compile_endpoint(admin_client: httpx.AsyncClient) -> None:
    """POST /api/canvas/compile mirrors the unit-level compile."""
    res = await admin_client.post(
        "/api/canvas/compile",
        json={
            "nodes": [
                {"kind": "read_dp", "config": {"table_fqn": "main.s.t"}},
                {
                    "kind": "write_dp",
                    "config": {"target_fqn": "main.x.y", "mode": "append"},
                },
            ]
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["errors"] == []
    assert "PQL()" in body["code"]


@pytest.mark.asyncio
async def test_canvas_page_renders(admin_client: httpx.AsyncClient) -> None:
    """The /canvas page renders 200."""
    res = await admin_client.get("/canvas")
    assert res.status_code == 200
    assert "Dataflow canvas" in res.text
