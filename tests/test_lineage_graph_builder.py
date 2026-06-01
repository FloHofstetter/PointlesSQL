"""Unit tests for the run-scoped lineage DAG builder.

``build_lineage_graph`` reads ``lineage_row_edges`` + ``lineage_column_map``
for one run and folds them into a flat ``{nodes, edges}`` payload. The
tests seed those tables directly through the app's session factory (the
same pattern the model tests use) and assert the node/edge aggregation,
the op-filter, the NULL-source column annotation, the row-only edge
fallback, and the stable ordering contract.
"""

from __future__ import annotations

import datetime as _dt
from types import SimpleNamespace
from typing import Any

from pointlessql.api.main import app
from pointlessql.models import AgentRun, AgentRunOperation, LineageColumnMap, LineageRowEdge
from pointlessql.services.lineage.graph_builder import build_lineage_graph

_NOW = _dt.datetime(2026, 1, 1, tzinfo=_dt.UTC)


def _fake_request() -> Any:
    """A stand-in request exposing only ``app.state.session_factory``."""
    return SimpleNamespace(app=SimpleNamespace(state=app.state))


def _seed_op(run_id: str, *, ordinal: int = 1, op_name: str = "merge") -> int:
    """Insert an AgentRun + one operation; return the op id."""
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            AgentRun(
                id=run_id,
                principal="alice",
                notebook_path=f"/tmp/{run_id}.py",
                status="completed",
                started_at=_NOW,
            )
        )
        session.flush()
        op = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=ordinal,
            op_name=op_name,
            params_json="{}",
            target_table="cat.sch.tgt",
            started_at=_NOW,
            finished_at=_NOW,
        )
        session.add(op)
        session.flush()
        op_id = int(op.id)
        session.commit()
    return op_id


def test_empty_run_returns_empty_graph() -> None:
    graph = build_lineage_graph(_fake_request(), "no-such-run")
    assert graph["nodes"] == []
    assert graph["edges"] == []
    assert graph["run_id"] == "no-such-run"
    assert graph["op_id"] is None


def test_single_edge_with_column_map() -> None:
    run_id = "gb-single"
    op_id = _seed_op(run_id, ordinal=3, op_name="sql")
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            LineageRowEdge(
                run_id=run_id,
                op_id=op_id,
                source_table="cat.sch.src",
                source_row_id="r1",
                target_table="cat.sch.tgt",
                target_row_id="r1",
                created_at=_NOW,
            )
        )
        session.add(
            LineageColumnMap(
                run_id=run_id,
                op_id=op_id,
                source_table="cat.sch.src",
                source_column="amount",
                target_table="cat.sch.tgt",
                target_column="total",
                transform_kind="rename",
                created_at=_NOW,
            )
        )
        session.commit()

    graph = build_lineage_graph(_fake_request(), run_id)
    assert [n["id"] for n in graph["nodes"]] == ["cat.sch.src", "cat.sch.tgt"]
    assert len(graph["edges"]) == 1
    edge = graph["edges"][0]
    assert edge["source"] == "cat.sch.src"
    assert edge["target"] == "cat.sch.tgt"
    assert edge["op_id"] == op_id
    assert edge["op_ordinal"] == 3
    assert edge["op_name"] == "sql"
    assert edge["transform_kinds"] == ["rename"]
    assert edge["column_pairs"] == [
        {"source_column": "amount", "target_column": "total", "transform_kind": "rename"}
    ]
    assert edge["row_edge_count"] == 1


def test_op_filter_restricts_to_single_op() -> None:
    run_id = "gb-opfilter"
    op_a = _seed_op(run_id, ordinal=1, op_name="merge")
    factory = app.state.session_factory
    with factory() as session:
        op_b = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=2,
            op_name="aggregate",
            params_json="{}",
            started_at=_NOW,
        )
        session.add(op_b)
        session.flush()
        op_b_id = int(op_b.id)
        for op_id, src in ((op_a, "cat.sch.a"), (op_b_id, "cat.sch.b")):
            session.add(
                LineageRowEdge(
                    run_id=run_id,
                    op_id=op_id,
                    source_table=src,
                    source_row_id="r1",
                    target_table="cat.sch.tgt",
                    target_row_id="r1",
                    created_at=_NOW,
                )
            )
        session.commit()

    graph = build_lineage_graph(_fake_request(), run_id, op_id=op_b_id)
    srcs = {e["source"] for e in graph["edges"]}
    assert srcs == {"cat.sch.b"}


def test_null_source_column_annotates_target_only() -> None:
    run_id = "gb-nullsrc"
    op_id = _seed_op(run_id)
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            LineageColumnMap(
                run_id=run_id,
                op_id=op_id,
                source_table=None,
                source_column=None,
                target_table="cat.sch.tgt",
                target_column="generated_id",
                transform_kind="unknown_origin",
                created_at=_NOW,
            )
        )
        session.commit()

    graph = build_lineage_graph(_fake_request(), run_id)
    # No inter-table edge, but the target node carries the column.
    assert graph["edges"] == []
    tgt = next(n for n in graph["nodes"] if n["id"] == "cat.sch.tgt")
    assert "generated_id" in tgt["columns"]


def test_row_only_edge_surfaces_without_column_map() -> None:
    run_id = "gb-rowonly"
    op_id = _seed_op(run_id)
    factory = app.state.session_factory
    with factory() as session:
        for i in range(3):
            session.add(
                LineageRowEdge(
                    run_id=run_id,
                    op_id=op_id,
                    source_table="cat.sch.src",
                    source_row_id=f"r{i}",
                    target_table="cat.sch.tgt",
                    target_row_id=f"r{i}",
                    created_at=_NOW,
                )
            )
        session.commit()

    graph = build_lineage_graph(_fake_request(), run_id)
    assert len(graph["edges"]) == 1
    assert graph["edges"][0]["row_edge_count"] == 3
    assert graph["edges"][0]["column_pairs"] == []


def test_nodes_and_edges_are_stably_ordered() -> None:
    run_id = "gb-order"
    op_id = _seed_op(run_id, ordinal=5)
    factory = app.state.session_factory
    with factory() as session:
        for src in ("cat.sch.zeta", "cat.sch.alpha"):
            session.add(
                LineageRowEdge(
                    run_id=run_id,
                    op_id=op_id,
                    source_table=src,
                    source_row_id="r1",
                    target_table="cat.sch.tgt",
                    target_row_id="r1",
                    created_at=_NOW,
                )
            )
        session.commit()

    graph = build_lineage_graph(_fake_request(), run_id)
    # Nodes alphabetical by id.
    ids = [n["id"] for n in graph["nodes"]]
    assert ids == sorted(ids)
    # Edges ordered by (op_ordinal, source, target).
    sources = [e["source"] for e in graph["edges"]]
    assert sources == sorted(sources)
