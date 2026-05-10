"""Sprint 65.1 — unified Lens provenance trace tests.

Exercises the four trace modes (table / column / row / row+value) and
the empty-trace + hop-cap edge cases.  Uses synthetic
``lineage_row_edges`` / ``lineage_column_map`` / ``lineage_value_changes``
rows directly so we never spin up soyuz / deltalake.
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
    LineageColumnMap,
    LineageRowEdge,
    LineageValueChange,
)
from pointlessql.services.lens.provenance import (
    DEFAULT_MAX_HOPS,
    MAX_ALLOWED_HOPS,
    ProvenanceQuery,
    provenance,
)


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
    """Insert one ``agent_runs`` + ``agent_run_operations`` row."""
    run_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    with factory() as s:
        s.add(
            AgentRun(
                id=run_id,
                principal="test",
                agent_id="lens-prov-test",
                notebook_path="lens_provenance.py",
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


def _seed_row_edge(
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    run_id: str,
    op_id: int,
    source_table: str,
    source_row_id: str,
    target_table: str,
    target_row_id: str,
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
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        s.commit()


def _seed_column_edge(
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    run_id: str,
    op_id: int,
    source_table: str | None,
    source_column: str | None,
    target_table: str,
    target_column: str,
    transform_kind: str = "identity",
    transform_detail: str | None = None,
) -> None:
    with factory() as s:
        s.add(
            LineageColumnMap(
                run_id=run_id,
                op_id=op_id,
                source_table=source_table,
                source_column=source_column,
                target_table=target_table,
                target_column=target_column,
                transform_kind=transform_kind,
                transform_detail=transform_detail,
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        s.commit()


def _seed_value_change(
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    run_id: str,
    op_id: int,
    target_table: str,
    target_row_id: str,
    target_column: str,
    old_value: str | None,
    new_value: str | None,
) -> None:
    with factory() as s:
        s.add(
            LineageValueChange(
                run_id=run_id,
                op_id=op_id,
                target_table=target_table,
                target_row_id=target_row_id,
                target_column=target_column,
                old_value=old_value,
                new_value=new_value,
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        s.commit()


# ---------------------------------------------------------------------------
# Mode resolution
# ---------------------------------------------------------------------------


def test_table_mode_returns_metadata_only(factory) -> None:  # type: ignore[no-untyped-def]
    """Pure table_fqn → mode='table', no walkback, single note."""
    trace = provenance(
        factory, ProvenanceQuery(table_fqn="main.silver.t")
    )
    assert trace.mode == "table"
    assert trace.notes  # at least the "metadata only" hint
    assert trace.row_steps == []
    assert trace.transformations == []


def test_row_mode_walks_back_three_hops(factory) -> None:  # type: ignore[no-untyped-def]
    """Three-hop chain bronze→silver→gold returns 3 walk steps."""
    run_id, op_id_silver = _seed_run_op(
        factory, op_name="merge", target_table="main.silver.t"
    )
    _, op_id_gold = _seed_run_op(
        factory, op_name="merge", target_table="main.gold.t"
    )
    _seed_row_edge(
        factory,
        run_id=run_id,
        op_id=op_id_silver,
        source_table="main.bronze.t",
        source_row_id="b1",
        target_table="main.silver.t",
        target_row_id="s1",
    )
    _seed_row_edge(
        factory,
        run_id=run_id,
        op_id=op_id_gold,
        source_table="main.silver.t",
        source_row_id="s1",
        target_table="main.gold.t",
        target_row_id="g1",
    )

    trace = provenance(
        factory,
        ProvenanceQuery(table_fqn="main.gold.t", row_id="g1"),
    )
    assert trace.mode == "row"
    assert {step.table for step in trace.row_steps} == {
        "main.gold.t",
        "main.silver.t",
        "main.bronze.t",
    }
    assert "main.bronze.t" in {s.table_fqn for s in trace.sources}


def test_column_mode_with_cross_column_rename(factory) -> None:  # type: ignore[no-untyped-def]
    """Column-only renames surface as transformations on the trace."""
    run_id, op_id = _seed_run_op(
        factory, op_name="merge", target_table="main.silver.t"
    )
    _seed_column_edge(
        factory,
        run_id=run_id,
        op_id=op_id,
        source_table="main.bronze.t",
        source_column="raw_amount",
        target_table="main.silver.t",
        target_column="amount_usd",
        transform_kind="rename",
        transform_detail="raw_amount → amount_usd",
    )

    trace = provenance(
        factory,
        ProvenanceQuery(table_fqn="main.silver.t", column="amount_usd"),
    )
    assert trace.mode == "column"
    assert any(
        t.source_column == "raw_amount" and t.target_column == "amount_usd"
        for t in trace.transformations
    )
    assert any(s.table_fqn == "main.bronze.t" for s in trace.sources)


def test_row_value_mode_combines_walk_and_changes(factory) -> None:  # type: ignore[no-untyped-def]
    """Row+column scope returns row walkback plus value changes."""
    run_id, op_id = _seed_run_op(
        factory, op_name="merge", target_table="main.silver.t"
    )
    _seed_row_edge(
        factory,
        run_id=run_id,
        op_id=op_id,
        source_table="main.bronze.t",
        source_row_id="b1",
        target_table="main.silver.t",
        target_row_id="s1",
    )
    _seed_column_edge(
        factory,
        run_id=run_id,
        op_id=op_id,
        source_table="main.bronze.t",
        source_column="amount",
        target_table="main.silver.t",
        target_column="amount",
        transform_kind="identity",
    )
    _seed_value_change(
        factory,
        run_id=run_id,
        op_id=op_id,
        target_table="main.silver.t",
        target_row_id="s1",
        target_column="amount",
        old_value="100",
        new_value="200",
    )

    trace = provenance(
        factory,
        ProvenanceQuery(
            table_fqn="main.silver.t",
            row_id="s1",
            column="amount",
        ),
    )
    assert trace.mode == "row_value"
    assert len(trace.value_changes) == 1
    assert trace.value_changes[0].old_value == "100"
    assert trace.value_changes[0].new_value == "200"
    assert any(s.table_fqn == "main.bronze.t" for s in trace.sources)
    assert len(trace.row_steps) >= 1


def test_empty_trace_yields_explanatory_note(factory) -> None:  # type: ignore[no-untyped-def]
    """No lineage rows → empty payload + explanatory note."""
    trace = provenance(
        factory,
        ProvenanceQuery(
            table_fqn="main.silver.untracked",
            row_id="x1",
        ),
    )
    assert trace.mode == "row"
    assert trace.notes  # "No upstream row lineage recorded"


def test_max_hops_capped(factory) -> None:  # type: ignore[no-untyped-def]
    """Max-hops > MAX_ALLOWED_HOPS raises Pydantic ValidationError."""
    with pytest.raises(ValueError):
        ProvenanceQuery(
            table_fqn="main.silver.t",
            max_hops=MAX_ALLOWED_HOPS + 1,
        )


def test_default_max_hops_applies(factory) -> None:  # type: ignore[no-untyped-def]
    """Defaulted max_hops resolves to DEFAULT_MAX_HOPS."""
    q = ProvenanceQuery(table_fqn="main.silver.t")
    assert q.max_hops == DEFAULT_MAX_HOPS


def test_row_mode_truncated_at_hop_limit(factory) -> None:  # type: ignore[no-untyped-def]
    """A hop chain longer than max_hops surfaces a truncation note."""
    run_id, _ = _seed_run_op(
        factory, op_name="merge", target_table="main.silver.t1"
    )
    # Build a 6-hop chain bronze→t0→t1→t2→t3→target
    chain = ["bronze", "t0", "t1", "t2", "t3", "target"]
    op_ids: list[int] = []
    for idx, _ in enumerate(chain):
        if idx == 0:
            continue
        with factory() as s:
            op = AgentRunOperation(
                agent_run_id=run_id,
                ordinal=10 + idx,
                op_name="merge",
                params_json="{}",
                target_table=f"main.silver.{chain[idx]}",
                started_at=datetime.datetime.now(datetime.UTC),
            )
            s.add(op)
            s.commit()
            s.refresh(op)
            op_ids.append(op.id)

    for idx in range(1, len(chain)):
        _seed_row_edge(
            factory,
            run_id=run_id,
            op_id=op_ids[idx - 1],
            source_table=f"main.silver.{chain[idx - 1]}",
            source_row_id=f"r-{idx - 1}",
            target_table=f"main.silver.{chain[idx]}",
            target_row_id=f"r-{idx}",
        )

    trace = provenance(
        factory,
        ProvenanceQuery(
            table_fqn="main.silver.target",
            row_id="r-5",
            max_hops=2,
        ),
    )
    assert trace.mode == "row"
    assert any("hop limit" in note for note in trace.notes)


def test_column_mode_no_lineage_yields_note(factory) -> None:  # type: ignore[no-untyped-def]
    """Column scope with no edges → explanatory note + empty list."""
    trace = provenance(
        factory,
        ProvenanceQuery(table_fqn="main.silver.x", column="never_recorded"),
    )
    assert trace.mode == "column"
    assert trace.transformations == []
    assert trace.notes


def test_row_value_no_changes_yields_note(factory) -> None:  # type: ignore[no-untyped-def]
    """row_value mode without value changes (track off) → explanatory note."""
    run_id, op_id = _seed_run_op(
        factory, op_name="merge", target_table="main.silver.t"
    )
    _seed_row_edge(
        factory,
        run_id=run_id,
        op_id=op_id,
        source_table="main.bronze.t",
        source_row_id="b1",
        target_table="main.silver.t",
        target_row_id="s1",
    )

    trace = provenance(
        factory,
        ProvenanceQuery(
            table_fqn="main.silver.t",
            row_id="s1",
            column="amount",
        ),
    )
    assert trace.mode == "row_value"
    assert trace.value_changes == []
    assert any("value changes" in note.lower() for note in trace.notes)
