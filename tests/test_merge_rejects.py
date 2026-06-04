"""pre-merge reject detection unit tests.

The end-to-end ``pql.merge(track_rejects=True)`` flow needs deltalake
+ soyuz and is exercised by the live replay.  These
tests cover the pure-Python helper :func:`_detect_rejects` and the
``record_rejects`` persistence helper.
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Iterable

import pandas as pd
import pyarrow as pa
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    Base,
    LineageRowReject,
)
from pointlessql.pql._merge import _detect_rejects
from pointlessql.services.lineage_edges import record_rejects


@pytest.fixture
def factory() -> sessionmaker:  # type: ignore[type-arg]
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _seed_run_op(factory: sessionmaker) -> tuple[str, int]:  # type: ignore[type-arg]
    run_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    with factory() as s:
        s.add(
            AgentRun(
                id=run_id,
                principal="test",
                agent_id="phase-15.5.3-test",
                notebook_path="rejects.py",
                status="running",
                started_at=now,
            )
        )
        s.flush()
        op = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=1,
            op_name="merge",
            params_json="{}",
            target_table="main.silver.t",
            started_at=now,
        )
        s.add(op)
        s.commit()
        s.refresh(op)
        return run_id, op.id


class TestDetectRejects:
    """Pre-merge reject classification."""

    def test_no_lineage_column_returns_no_rejects(self) -> None:
        df = pd.DataFrame({"order_id": [1, 2, 3], "qty": [10, 20, 30]})
        arrow = pa.Table.from_pandas(df, preserve_index=False)
        cleaned, rejects = _detect_rejects(arrow, ["order_id"])
        assert cleaned.num_rows == 3
        assert rejects == []

    def test_null_on_key_is_rejected(self) -> None:
        df = pd.DataFrame(
            {
                "order_id": [1, None, 3],
                "qty": [10, 20, 30],
                "_lineage_row_id": ["a", "b", "c"],
            }
        )
        arrow = pa.Table.from_pandas(df, preserve_index=False)
        cleaned, rejects = _detect_rejects(arrow, ["order_id"])
        assert cleaned.num_rows == 2  # null-row dropped
        assert len(rejects) == 1
        row_id, reason, detail = rejects[0]
        assert row_id == "b"
        assert reason == "on_key_null"
        assert detail is not None and "order_id" in detail

    def test_duplicate_in_source_keeps_first_rejects_rest(self) -> None:
        df = pd.DataFrame(
            {
                "order_id": [1, 1, 2, 1],
                "qty": [10, 20, 30, 40],
                "_lineage_row_id": ["a", "b", "c", "d"],
            }
        )
        arrow = pa.Table.from_pandas(df, preserve_index=False)
        cleaned, rejects = _detect_rejects(arrow, ["order_id"])
        # Two unique keys (1, 2) survive; first occurrence kept.
        assert cleaned.num_rows == 2
        rejected_ids = {r[0] for r in rejects}
        assert rejected_ids == {"b", "d"}
        assert all(r[1] == "duplicate_in_source" for r in rejects)

    def test_combined_null_and_duplicate(self) -> None:
        df = pd.DataFrame(
            {
                "order_id": [1, None, 1],
                "qty": [10, 20, 30],
                "_lineage_row_id": ["a", "b", "c"],
            }
        )
        arrow = pa.Table.from_pandas(df, preserve_index=False)
        cleaned, rejects = _detect_rejects(arrow, ["order_id"])
        # Row a survives. b is null-key reject. c is duplicate of a.
        assert cleaned.num_rows == 1
        rejected_by_reason: dict[str, set[str]] = {}
        for row_id, reason, _ in rejects:
            rejected_by_reason.setdefault(reason, set()).add(row_id)
        assert rejected_by_reason["on_key_null"] == {"b"}
        assert rejected_by_reason["duplicate_in_source"] == {"c"}

    def test_no_rejects_returns_empty_list(self) -> None:
        df = pd.DataFrame(
            {
                "order_id": [1, 2, 3],
                "qty": [10, 20, 30],
                "_lineage_row_id": ["a", "b", "c"],
            }
        )
        arrow = pa.Table.from_pandas(df, preserve_index=False)
        cleaned, rejects = _detect_rejects(arrow, ["order_id"])
        assert cleaned.num_rows == 3
        assert rejects == []

    def test_cleaned_preserves_schema_and_exact_surviving_rows(self) -> None:
        """The cleaned source keeps the input schema and exactly the
        non-rejected rows in source order.

        Guards the row-mask plumbing end to end: a stray index column
        leaking out of ``reset_index`` / ``from_pandas`` would change
        the schema, and any slip in the keep/null/dup masks would change
        which ``_lineage_row_id`` values survive.
        """
        df = pd.DataFrame(
            {
                "order_id": [1, None, 2, 2, 3],
                "qty": [10, 20, 30, 40, 50],
                "_lineage_row_id": ["a", "b", "c", "d", "e"],
            }
        )
        arrow = pa.Table.from_pandas(df, preserve_index=False)
        cleaned, rejects = _detect_rejects(arrow, ["order_id"])

        # No spurious index column may leak into the merged-into table.
        assert cleaned.column_names == ["order_id", "qty", "_lineage_row_id"]

        # "b" is dropped for a null key, "d" as the second occurrence of
        # key 2; "a", "c", "e" survive untouched and in order.
        cleaned_pdf = cleaned.to_pandas()
        assert list(cleaned_pdf["_lineage_row_id"]) == ["a", "c", "e"]
        assert list(cleaned_pdf["qty"]) == [10, 30, 50]

        assert {(row_id, reason) for row_id, reason, _ in rejects} == {
            ("b", "on_key_null"),
            ("d", "duplicate_in_source"),
        }


class TestRecordRejects:
    """Persistence into ``lineage_row_rejects``."""

    def test_round_trip(self, factory: sessionmaker) -> None:  # type: ignore[type-arg]
        run_id, op_id = _seed_run_op(factory)
        rejects: list[tuple[str, str, str | None]] = [
            ("a", "on_key_null", "NULL in 'order_id'"),
            ("b", "duplicate_in_source", "second occurrence of merge key"),
        ]
        failure = record_rejects(
            factory,
            run_id=run_id,
            op_id=op_id,
            source_table="main.bronze.orders",
            rejects=rejects,
        )
        assert failure is None

        with factory() as s:
            stmt = select(LineageRowReject).where(LineageRowReject.run_id == run_id)
            stored: Iterable[LineageRowReject] = s.scalars(stmt).all()
            stored_list = list(stored)
            assert len(stored_list) == 2
            by_id = {r.source_row_id: r for r in stored_list}
            assert by_id["a"].reason == "on_key_null"
            assert by_id["b"].reason == "duplicate_in_source"
            assert by_id["a"].source_table == "main.bronze.orders"

    def test_empty_input_is_noop(self, factory: sessionmaker) -> None:  # type: ignore[type-arg]
        run_id, op_id = _seed_run_op(factory)
        failure = record_rejects(
            factory,
            run_id=run_id,
            op_id=op_id,
            source_table="main.bronze.orders",
            rejects=[],
        )
        assert failure is None
        with factory() as s:
            count = s.scalars(
                select(LineageRowReject).where(LineageRowReject.run_id == run_id)
            ).all()
            assert list(count) == []

    def test_invalid_reason_raises(self, factory: sessionmaker) -> None:  # type: ignore[type-arg]
        run_id, op_id = _seed_run_op(factory)
        # CHECK constraint enforced at DB level — bad reason fails the insert.
        failure = record_rejects(
            factory,
            run_id=run_id,
            op_id=op_id,
            source_table="main.bronze.orders",
            rejects=[("a", "not_a_real_reason", None)],
        )
        # Expect failure (returned, not raised).
        assert failure is not None
