"""Unit tests for the row-level lineage edge store.

Covers the bulk-insert no-op guards (empty / mismatched id lists), a
successful edge insert, the predecessor / descendant lookups (ordered by
``created_at``), and the per-op edge counter. Edges are seeded through the
app session factory; an operation is seeded so ``record_edges`` can resolve
its workspace.
"""

from __future__ import annotations

import datetime as _dt

from pointlessql.api.main import app
from pointlessql.models import AgentRun, AgentRunOperation, LineageRowEdge
from pointlessql.services.lineage.rows import (
    count_edges_for_op,
    fetch_source_row_descendants,
    fetch_target_row_predecessors,
    record_edges,
)

_NOW = _dt.datetime(2026, 1, 1, tzinfo=_dt.UTC)


def _seed_op(run_id: str) -> int:
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
            ordinal=1,
            op_name="merge",
            params_json="{}",
            started_at=_NOW,
        )
        session.add(op)
        session.flush()
        op_id = int(op.id)
        session.commit()
    return op_id


def _add_edge(run_id: str, op_id: int, src_id: str, tgt_id: str) -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            LineageRowEdge(
                run_id=run_id,
                op_id=op_id,
                source_table="c.s.src",
                source_row_id=src_id,
                target_table="c.s.tgt",
                target_row_id=tgt_id,
                created_at=_NOW,
            )
        )
        session.commit()


def _count_rows(run_id: str) -> int:
    from sqlalchemy import func, select

    with app.state.session_factory() as session:
        return int(
            session.scalar(
                select(func.count()).select_from(LineageRowEdge).where(
                    LineageRowEdge.run_id == run_id
                )
            )
            or 0
        )


# --- record_edges ---------------------------------------------------------


def test_record_edges_length_mismatch_is_noop() -> None:
    err = record_edges(
        app.state.session_factory,
        run_id="rows-mismatch",
        op_id=1,
        source_table="c.s.src",
        target_table="c.s.tgt",
        source_row_ids=["a", "b"],
        target_row_ids=["x"],
    )
    assert err is None
    assert _count_rows("rows-mismatch") == 0


def test_record_edges_empty_is_noop() -> None:
    err = record_edges(
        app.state.session_factory,
        run_id="rows-empty",
        op_id=1,
        source_table="c.s.src",
        target_table="c.s.tgt",
        source_row_ids=[],
        target_row_ids=[],
    )
    assert err is None
    assert _count_rows("rows-empty") == 0


def test_record_edges_inserts_aligned_pairs() -> None:
    run_id = "rows-ok"
    op_id = _seed_op(run_id)
    err = record_edges(
        app.state.session_factory,
        run_id=run_id,
        op_id=op_id,
        source_table="c.s.src",
        target_table="c.s.tgt",
        source_row_ids=["s1", "s2"],
        target_row_ids=["t1", "t2"],
    )
    assert err is None
    assert _count_rows(run_id) == 2


# --- fetch predecessors / descendants -------------------------------------


def test_fetch_target_predecessors() -> None:
    run_id = "rows-pred"
    op_id = _seed_op(run_id)
    _add_edge(run_id, op_id, "s1", "t1")
    _add_edge(run_id, op_id, "s2", "t1")
    _add_edge(run_id, op_id, "s3", "t2")
    preds = fetch_target_row_predecessors(
        app.state.session_factory, target_table="c.s.tgt", target_row_id="t1"
    )
    assert {e.source_row_id for e in preds} == {"s1", "s2"}


def test_fetch_source_descendants() -> None:
    run_id = "rows-desc"
    op_id = _seed_op(run_id)
    _add_edge(run_id, op_id, "s9", "t1")
    _add_edge(run_id, op_id, "s9", "t2")
    descs = fetch_source_row_descendants(
        app.state.session_factory, source_table="c.s.src", source_row_id="s9"
    )
    assert {e.target_row_id for e in descs} == {"t1", "t2"}


# --- count_edges_for_op ---------------------------------------------------


def test_count_edges_for_op() -> None:
    run_id = "rows-count"
    op_id = _seed_op(run_id)
    _add_edge(run_id, op_id, "s1", "t1")
    _add_edge(run_id, op_id, "s2", "t2")
    counts = count_edges_for_op(app.state.session_factory, [op_id])
    assert counts.get(op_id) == 2


def test_count_edges_for_op_empty_input() -> None:
    assert count_edges_for_op(app.state.session_factory, []) == {}
