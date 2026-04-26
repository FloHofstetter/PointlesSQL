"""Walkback fan-in unit tests (Sprint 15.5.2).

Exercises :func:`pointlessql.services.lineage_edges.walk_back` with
synthetic ``lineage_row_edges`` rows so the fan-in shape lands
without spinning up soyuz / deltalake.  The matching end-to-end
replay lives in Sprint 15.5.5.
"""

from __future__ import annotations

import datetime
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    Base,
    LineageRowEdge,
)
from pointlessql.services.lineage_edges import walk_back


@pytest.fixture
def factory() -> sessionmaker:  # type: ignore[type-arg]
    """Build an in-memory SQLite session factory with the schema applied."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _seed_run_op(
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    op_name: str,
    target_table: str,
) -> tuple[str, int]:
    """Insert one ``agent_runs`` + ``agent_run_operations`` row.

    Returns ``(run_id, op_id)`` so callers can attach edges.
    """
    run_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    with factory() as s:
        s.add(
            AgentRun(
                id=run_id,
                principal="test",
                agent_id="phase-15.5-test",
                notebook_path="walk_back_fanin_unit.py",
                status="running",
                started_at=now,
            )
        )
        s.flush()
        op = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=1,
            op_name=op_name,
            params_json="{}",
            target_table=target_table,
            started_at=now,
        )
        s.add(op)
        s.commit()
        s.refresh(op)
        return run_id, op.id


def _seed_edge(
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    run_id: str,
    op_id: int,
    source_table: str,
    source_row_id: str,
    target_table: str,
    target_row_id: str,
    created_at: datetime.datetime | None = None,
) -> None:
    with factory() as s:
        s.add(
            LineageRowEdge(
                run_id=run_id,
                op_id=op_id,
                source_table=source_table,
                source_row_id=source_row_id,
                target_table=target_table,
                target_row_id=target_row_id,
                created_at=created_at or datetime.datetime.now(datetime.UTC),
            )
        )
        s.commit()


class TestWalkBackFanIn:
    """Fan-in (multiple sources → one target) is reflected on the step."""

    def test_aggregate_step_carries_all_predecessors(
        self, factory: sessionmaker  # type: ignore[type-arg]
    ) -> None:
        run_id, op_id = _seed_run_op(
            factory, op_name="aggregate", target_table="main.gold.t"
        )
        # Three silver rows fan into one gold row via op_id.
        for sid in ("s1", "s2", "s3"):
            _seed_edge(
                factory,
                run_id=run_id,
                op_id=op_id,
                source_table="main.silver.t",
                source_row_id=sid,
                target_table="main.gold.t",
                target_row_id="g1",
            )

        steps = walk_back(factory, table="main.gold.t", row_id="g1")

        # Step 0 (the gold row) has 3 predecessors — that is the fan-in.
        assert len(steps) >= 1
        assert steps[0].depth == 0
        assert len(steps[0].predecessors) == 3
        assert sorted(p.row_id for p in steps[0].predecessors) == ["s1", "s2", "s3"]
        # All predecessors share the aggregate op_id.
        assert {p.op_id for p in steps[0].predecessors} == {op_id}

    def test_chain_recursion_picks_oldest(
        self, factory: sessionmaker  # type: ignore[type-arg]
    ) -> None:
        run_id, op_id = _seed_run_op(
            factory, op_name="merge", target_table="main.silver.t"
        )
        # Two predecessors with different timestamps — oldest wins for recursion.
        old = datetime.datetime(2026, 4, 1, 10, 0, tzinfo=datetime.UTC)
        new = datetime.datetime(2026, 4, 2, 10, 0, tzinfo=datetime.UTC)
        _seed_edge(
            factory,
            run_id=run_id,
            op_id=op_id,
            source_table="main.bronze.a",
            source_row_id="aaa",
            target_table="main.silver.t",
            target_row_id="t1",
            created_at=old,
        )
        _seed_edge(
            factory,
            run_id=run_id,
            op_id=op_id,
            source_table="main.bronze.b",
            source_row_id="bbb",
            target_table="main.silver.t",
            target_row_id="t1",
            created_at=new,
        )

        steps = walk_back(factory, table="main.silver.t", row_id="t1")

        # Step 0 = silver (input), step 1 = bronze (chosen oldest = main.bronze.a).
        assert len(steps) == 2
        assert steps[1].table == "main.bronze.a"
        assert steps[1].row_id == "aaa"
        # But step 0 still surfaces BOTH predecessors so the UI can render fan-in.
        assert {(p.table, p.row_id) for p in steps[0].predecessors} == {
            ("main.bronze.a", "aaa"),
            ("main.bronze.b", "bbb"),
        }

    def test_no_predecessors_yields_lineage_break(
        self, factory: sessionmaker  # type: ignore[type-arg]
    ) -> None:
        # No edges seeded.
        steps = walk_back(factory, table="main.gold.empty", row_id="never")

        # walk_back now always returns at least the input row at depth 0.
        assert len(steps) == 1
        assert steps[0].depth == 0
        assert steps[0].predecessors == ()
        assert steps[0].op_id is None

    def test_single_predecessor_produces_two_step_chain(
        self, factory: sessionmaker  # type: ignore[type-arg]
    ) -> None:
        run_id, op_id = _seed_run_op(
            factory, op_name="merge", target_table="main.silver.t"
        )
        _seed_edge(
            factory,
            run_id=run_id,
            op_id=op_id,
            source_table="main.bronze.t",
            source_row_id="b1",
            target_table="main.silver.t",
            target_row_id="s1",
        )

        steps = walk_back(factory, table="main.silver.t", row_id="s1")

        assert len(steps) == 2
        assert steps[0].depth == 0
        assert len(steps[0].predecessors) == 1
        assert steps[1].depth == 1
        assert steps[1].table == "main.bronze.t"
        assert steps[1].row_id == "b1"
