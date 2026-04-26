"""Column-lineage service unit tests (Sprint 15.6.1).

Exercises :func:`pointlessql.services.lineage_edges.record_column_edges`,
:func:`walk_back_columns`, and :func:`count_column_edges_for_op` with
synthetic ``lineage_column_map`` rows so the column-trace shape lands
without spinning up soyuz / deltalake.  The matching end-to-end replay
lives in Sprint 15.6.5.
"""

from __future__ import annotations

import datetime
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    Base,
    LineageColumnMap,
)
from pointlessql.services.lineage_edges import (
    MAX_COLUMN_EDGES_PER_OP,
    ColumnEdgeCapExceeded,
    ColumnEdgeSpec,
    count_column_edges_for_op,
    record_column_edges,
    walk_back_columns,
)


@pytest.fixture
def factory() -> sessionmaker:  # type: ignore[type-arg]
    """In-memory SQLite session factory with the schema applied."""
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
    op_name: str = "merge",
    target_table: str = "main.silver.t",
    ordinal: int = 1,
    run_id: str | None = None,
) -> tuple[str, int]:
    """Insert one ``agent_runs`` + ``agent_run_operations`` row."""
    run_id = run_id or str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    with factory() as s:
        if not s.scalar(select(AgentRun.id).where(AgentRun.id == run_id)):
            s.add(
                AgentRun(
                    id=run_id,
                    principal="test",
                    agent_id="phase-15.6-test",
                    notebook_path="lineage_columns_unit.py",
                    status="running",
                    started_at=now,
                )
            )
            s.flush()
        op = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=ordinal,
            op_name=op_name,
            params_json="{}",
            target_table=target_table,
            started_at=now,
        )
        s.add(op)
        s.commit()
        s.refresh(op)
        return run_id, op.id


class TestRecordColumnEdges:
    """``record_column_edges`` bulk-inserts and respects the cap."""

    def test_writes_rows(self, factory: sessionmaker) -> None:  # type: ignore[type-arg]
        run_id, op_id = _seed_run_op(factory)
        edges = [
            ColumnEdgeSpec(
                source_table="main.bronze.t",
                source_column="qty",
                target_table="main.silver.t",
                target_column="qty",
                transform_kind="identity",
            ),
            ColumnEdgeSpec(
                source_table="main.bronze.t",
                source_column="placed_at",
                target_table="main.silver.t",
                target_column="placed_day",
                transform_kind="derived",
                transform_detail="dt.floor('D')",
            ),
        ]
        result = record_column_edges(factory, run_id=run_id, op_id=op_id, edges=edges)
        assert result is None

        with factory() as s:
            rows = list(s.scalars(select(LineageColumnMap)))
        assert len(rows) == 2
        kinds = {r.transform_kind for r in rows}
        assert kinds == {"identity", "derived"}

    def test_empty_input_is_noop(self, factory: sessionmaker) -> None:  # type: ignore[type-arg]
        run_id, op_id = _seed_run_op(factory)
        result = record_column_edges(factory, run_id=run_id, op_id=op_id, edges=[])
        assert result is None
        with factory() as s:
            rows = list(s.scalars(select(LineageColumnMap)))
        assert rows == []

    def test_cap_exceeded_skips_insert(self, factory: sessionmaker) -> None:  # type: ignore[type-arg]
        run_id, op_id = _seed_run_op(factory)
        edges = [
            ColumnEdgeSpec(
                source_table="t",
                source_column=f"c{i}",
                target_table="u",
                target_column=f"c{i}",
                transform_kind="identity",
            )
            for i in range(MAX_COLUMN_EDGES_PER_OP + 1)
        ]
        result = record_column_edges(factory, run_id=run_id, op_id=op_id, edges=edges)
        assert isinstance(result, ColumnEdgeCapExceeded)
        with factory() as s:
            rows = list(s.scalars(select(LineageColumnMap)))
        assert rows == []

    def test_check_constraint_rejects_unknown_kind(
        self, factory: sessionmaker  # type: ignore[type-arg]
    ) -> None:
        run_id, op_id = _seed_run_op(factory)
        edges = [
            ColumnEdgeSpec(
                source_table="main.bronze.t",
                source_column="qty",
                target_table="main.silver.t",
                target_column="qty",
                transform_kind="not_a_real_kind",
            )
        ]
        result = record_column_edges(factory, run_id=run_id, op_id=op_id, edges=edges)
        # SQLAlchemy returns the IntegrityError instead of raising.
        assert isinstance(result, IntegrityError)

    def test_unknown_origin_allows_null_source(
        self, factory: sessionmaker  # type: ignore[type-arg]
    ) -> None:
        run_id, op_id = _seed_run_op(factory)
        edges = [
            ColumnEdgeSpec(
                source_table=None,
                source_column=None,
                target_table="main.bronze.t",
                target_column="_ingested_at",
                transform_kind="unknown_origin",
                transform_detail="audit",
            )
        ]
        result = record_column_edges(factory, run_id=run_id, op_id=op_id, edges=edges)
        assert result is None
        with factory() as s:
            row = s.scalar(select(LineageColumnMap))
            assert row is not None
            assert row.source_table is None
            assert row.source_column is None
            assert row.transform_detail == "audit"


class TestWalkBackColumns:
    """``walk_back_columns`` mirrors row-trace fan-in."""

    def _seed(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        *,
        run_id: str,
        op_id: int,
        spec: ColumnEdgeSpec,
        created_at: datetime.datetime | None = None,
    ) -> None:
        with factory() as s:
            s.add(
                LineageColumnMap(
                    run_id=run_id,
                    op_id=op_id,
                    source_table=spec.source_table,
                    source_column=spec.source_column,
                    target_table=spec.target_table,
                    target_column=spec.target_column,
                    transform_kind=spec.transform_kind,
                    transform_detail=spec.transform_detail,
                    created_at=created_at or datetime.datetime.now(datetime.UTC),
                )
            )
            s.commit()

    def test_no_edges_yields_one_step(
        self, factory: sessionmaker  # type: ignore[type-arg]
    ) -> None:
        steps = walk_back_columns(factory, table="main.gold.empty", column="x")
        assert len(steps) == 1
        assert steps[0].depth == 0
        assert steps[0].predecessors == ()

    def test_aggregate_fan_in_recurses_first_unique(
        self, factory: sessionmaker  # type: ignore[type-arg]
    ) -> None:
        run_id, op_id = _seed_run_op(
            factory, op_name="aggregate", target_table="main.gold.t"
        )
        # Two source columns feed gold.revenue (aggregate fan-in).
        for source_column in ("qty", "unit_price"):
            self._seed(
                factory,
                run_id=run_id,
                op_id=op_id,
                spec=ColumnEdgeSpec(
                    source_table="main.silver.t",
                    source_column=source_column,
                    target_table="main.gold.t",
                    target_column="revenue",
                    transform_kind="aggregate",
                    transform_detail="sum",
                ),
            )

        steps = walk_back_columns(factory, table="main.gold.t", column="revenue")

        # Depth 0 = gold; depth 1 = first unique source (qty).
        assert len(steps) == 2
        assert steps[0].depth == 0
        assert len(steps[0].predecessors) == 2
        assert {p.column for p in steps[0].predecessors} == {"qty", "unit_price"}
        # Recursion picks the first predecessor returned by the query
        # (created_at order); both share the same created_at here so
        # we just assert one of them was picked.
        assert steps[1].depth == 1
        assert steps[1].column in {"qty", "unit_price"}
        assert steps[1].table == "main.silver.t"

    def test_unknown_origin_breaks_chain(
        self, factory: sessionmaker  # type: ignore[type-arg]
    ) -> None:
        run_id, op_id = _seed_run_op(factory, op_name="autoload")
        self._seed(
            factory,
            run_id=run_id,
            op_id=op_id,
            spec=ColumnEdgeSpec(
                source_table=None,
                source_column=None,
                target_table="main.bronze.t",
                target_column="_ingested_at",
                transform_kind="unknown_origin",
                transform_detail="audit",
            ),
        )
        steps = walk_back_columns(factory, table="main.bronze.t", column="_ingested_at")
        # Step 0 has the unknown_origin predecessor but the walk does
        # not recurse into NULL source.
        assert len(steps) == 1
        assert len(steps[0].predecessors) == 1
        assert steps[0].predecessors[0].table is None

    def test_two_hop_chain_bronze_to_gold(
        self, factory: sessionmaker  # type: ignore[type-arg]
    ) -> None:
        run_id, merge_op = _seed_run_op(
            factory, op_name="merge", target_table="main.silver.t"
        )
        _, agg_op = _seed_run_op(
            factory,
            op_name="aggregate",
            target_table="main.gold.t",
            ordinal=2,
            run_id=run_id,
        )
        # bronze.qty -> silver.qty (identity merge)
        self._seed(
            factory,
            run_id=run_id,
            op_id=merge_op,
            spec=ColumnEdgeSpec(
                source_table="main.bronze.t",
                source_column="qty",
                target_table="main.silver.t",
                target_column="qty",
                transform_kind="identity",
            ),
        )
        # silver.qty -> gold.units_sold (aggregate)
        self._seed(
            factory,
            run_id=run_id,
            op_id=agg_op,
            spec=ColumnEdgeSpec(
                source_table="main.silver.t",
                source_column="qty",
                target_table="main.gold.t",
                target_column="units_sold",
                transform_kind="aggregate",
                transform_detail="sum",
            ),
        )

        steps = walk_back_columns(factory, table="main.gold.t", column="units_sold")
        assert len(steps) == 3
        assert (steps[0].table, steps[0].column) == ("main.gold.t", "units_sold")
        assert (steps[1].table, steps[1].column) == ("main.silver.t", "qty")
        assert (steps[2].table, steps[2].column) == ("main.bronze.t", "qty")


class TestCountColumnEdgesForOp:
    """``count_column_edges_for_op`` returns per-op counts."""

    def test_counts_per_op(self, factory: sessionmaker) -> None:  # type: ignore[type-arg]
        run_id, op_a = _seed_run_op(factory, ordinal=1)
        _, op_b = _seed_run_op(factory, ordinal=2, run_id=run_id)
        record_column_edges(
            factory,
            run_id=run_id,
            op_id=op_a,
            edges=[
                ColumnEdgeSpec(None, None, "t1", "c1", "unknown_origin", None),
                ColumnEdgeSpec(None, None, "t1", "c2", "unknown_origin", None),
            ],
        )
        record_column_edges(
            factory,
            run_id=run_id,
            op_id=op_b,
            edges=[
                ColumnEdgeSpec(None, None, "t2", "c1", "unknown_origin", None),
            ],
        )
        counts = count_column_edges_for_op(factory, [op_a, op_b])
        assert counts == {op_a: 2, op_b: 1}

    def test_empty_input(self, factory: sessionmaker) -> None:  # type: ignore[type-arg]
        assert count_column_edges_for_op(factory, []) == {}
