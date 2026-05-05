"""Value-lineage service unit tests (Sprint 15.7.1).

Exercises :func:`pointlessql.services.lineage_edges.record_value_changes`,
:func:`count_value_changes_for_op`, and
:func:`fetch_value_changes_for_row` with synthetic
``lineage_value_changes`` rows so the persistence shape lands without
spinning up soyuz / deltalake / Change Data Feed.  The matching
end-to-end replay lives in Sprint 15.7.5.
"""

from __future__ import annotations

import datetime
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    Base,
    LineageValueChange,
)
from pointlessql.services.lineage_edges import (
    MAX_VALUE_CHANGES_PER_OP,
    ValueChangeCapExceeded,
    ValueChangeSpec,
    count_value_changes_for_op,
    fetch_value_changes_for_row,
    record_value_changes,
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
                    agent_id="phase-15.7-test",
                    notebook_path="lineage_values_unit.py",
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


class TestRecordValueChanges:
    """``record_value_changes`` bulk-inserts and respects the 100k cap."""

    def test_writes_rows(self, factory: sessionmaker) -> None:  # type: ignore[type-arg]
        run_id, op_id = _seed_run_op(factory)
        changes = [
            ValueChangeSpec(
                target_table="main.silver.orders",
                target_row_id="aaa",
                target_column="unit_price",
                old_value="2.5",
                new_value="2.51",
            ),
            ValueChangeSpec(
                target_table="main.silver.orders",
                target_row_id="bbb",
                target_column="qty",
                old_value=None,
                new_value="3",
            ),
        ]
        result = record_value_changes(factory, run_id=run_id, op_id=op_id, changes=changes)
        assert result is None

        with factory() as s:
            rows = list(s.scalars(select(LineageValueChange)))
        assert len(rows) == 2
        cols = {r.target_column for r in rows}
        assert cols == {"unit_price", "qty"}
        # NULL old_value passes through as Python None.
        null_old = next(r for r in rows if r.target_column == "qty")
        assert null_old.old_value is None
        assert null_old.new_value == "3"

    def test_empty_input_is_noop(self, factory: sessionmaker) -> None:  # type: ignore[type-arg]
        run_id, op_id = _seed_run_op(factory)
        result = record_value_changes(factory, run_id=run_id, op_id=op_id, changes=[])
        assert result is None
        with factory() as s:
            rows = list(s.scalars(select(LineageValueChange)))
        assert rows == []

    def test_cap_exceeded_skips_insert(self, factory: sessionmaker) -> None:  # type: ignore[type-arg]
        run_id, op_id = _seed_run_op(factory)
        changes = [
            ValueChangeSpec(
                target_table="t",
                target_row_id=f"r{i}",
                target_column="c",
                old_value="0",
                new_value="1",
            )
            for i in range(MAX_VALUE_CHANGES_PER_OP + 1)
        ]
        result = record_value_changes(factory, run_id=run_id, op_id=op_id, changes=changes)
        assert isinstance(result, ValueChangeCapExceeded)
        with factory() as s:
            rows = list(s.scalars(select(LineageValueChange)))
        assert rows == []

    def test_text_column_accepts_long_value(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """``old_value`` / ``new_value`` are ``Text`` — no 500-char cap."""
        run_id, op_id = _seed_run_op(factory)
        long_payload = "x" * 5000
        changes = [
            ValueChangeSpec(
                target_table="t",
                target_row_id="r",
                target_column="c",
                old_value=long_payload,
                new_value=long_payload + "y",
            )
        ]
        result = record_value_changes(factory, run_id=run_id, op_id=op_id, changes=changes)
        assert result is None
        with factory() as s:
            row = s.scalar(select(LineageValueChange))
            assert row is not None
            assert row.old_value is not None
            assert len(row.old_value) == 5000


class TestCountValueChangesForOp:
    """``count_value_changes_for_op`` returns per-op counts."""

    def test_counts_per_op(self, factory: sessionmaker) -> None:  # type: ignore[type-arg]
        run_id, op_a = _seed_run_op(factory, ordinal=1)
        _, op_b = _seed_run_op(factory, ordinal=2, run_id=run_id)
        record_value_changes(
            factory,
            run_id=run_id,
            op_id=op_a,
            changes=[
                ValueChangeSpec("t", "r1", "c1", "0", "1"),
                ValueChangeSpec("t", "r1", "c2", "0", "1"),
            ],
        )
        record_value_changes(
            factory,
            run_id=run_id,
            op_id=op_b,
            changes=[ValueChangeSpec("t", "r2", "c1", "0", "1")],
        )
        counts = count_value_changes_for_op(factory, [op_a, op_b])
        assert counts == {op_a: 2, op_b: 1}

    def test_empty_input(self, factory: sessionmaker) -> None:  # type: ignore[type-arg]
        assert count_value_changes_for_op(factory, []) == {}


class TestFetchValueChangesForRow:
    """``fetch_value_changes_for_row`` filters and orders the change list."""

    def test_returns_all_columns_for_row(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id, op_id = _seed_run_op(factory)
        record_value_changes(
            factory,
            run_id=run_id,
            op_id=op_id,
            changes=[
                ValueChangeSpec("main.silver.orders", "rrr", "qty", "1", "2"),
                ValueChangeSpec("main.silver.orders", "rrr", "unit_price", "2.5", "2.51"),
                ValueChangeSpec("main.silver.orders", "sss", "qty", "1", "5"),
            ],
        )

        rows = fetch_value_changes_for_row(
            factory,
            target_table="main.silver.orders",
            target_row_id="rrr",
        )
        assert len(rows) == 2
        assert {r.target_column for r in rows} == {"qty", "unit_price"}

    def test_column_filter_narrows_to_one_cell(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id, op_id = _seed_run_op(factory)
        record_value_changes(
            factory,
            run_id=run_id,
            op_id=op_id,
            changes=[
                ValueChangeSpec("main.silver.orders", "rrr", "qty", "1", "2"),
                ValueChangeSpec("main.silver.orders", "rrr", "unit_price", "2.5", "2.51"),
            ],
        )
        rows = fetch_value_changes_for_row(
            factory,
            target_table="main.silver.orders",
            target_row_id="rrr",
            column="unit_price",
        )
        assert len(rows) == 1
        assert rows[0].target_column == "unit_price"
        assert rows[0].old_value == "2.5"
        assert rows[0].new_value == "2.51"

    def test_unknown_row_returns_empty(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        rows = fetch_value_changes_for_row(
            factory,
            target_table="main.silver.orders",
            target_row_id="never-existed",
        )
        assert rows == []
