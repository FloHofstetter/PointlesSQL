"""End-to-end tests for ``pql.rollback`` (Sprint 16.1).

Exercises the primitive directly — no FastAPI / soyuz live server.
A throwaway in-memory SQLite gets the audit schema, a real Delta
table on ``tmp_path`` carries the data, and a tiny stub satisfies
the soyuz-catalog client's ``get_table`` call so the
``storage_location`` resolves.

The four refusal modes plus the happy-path + force-path are each
their own test.  All gates must be evaluated *before*
``DeltaTable.restore`` is called, so refusal cases must leave the
Delta state untouched.
"""

from __future__ import annotations

import datetime
import json
import uuid
from pathlib import Path
from typing import Any

import deltalake
import pyarrow as pa
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.models import AgentRun, AgentRunOperation, Base
from pointlessql.pql import _rollback as rollback_module
from pointlessql.pql._cdf import cdf_creation_config
from pointlessql.pql._rollback import (
    RollbackResult,
    rollback_table,
)
from pointlessql.services.agent_runs.operations import (
    RollbackAmbiguous,
    RollbackInvalid,
    RollbackStale,
    RollbackTargetNotFound,
)


@pytest.fixture
def factory() -> sessionmaker:  # type: ignore[type-arg]
    """In-memory SQLite session factory with the audit schema applied."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture(autouse=True)
def _patch_get_session_factory(
    monkeypatch: pytest.MonkeyPatch,
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Wire the test-local factory into ``pointlessql.db.get_session_factory``."""
    monkeypatch.setattr("pointlessql.db.get_session_factory", lambda: factory)


@pytest.fixture(autouse=True)
def _patch_target_resolution(monkeypatch: pytest.MonkeyPatch, target_path: Path) -> None:
    """Stub soyuz-catalog so ``rollback_table`` resolves *target* to ``target_path``."""

    def fake_resolve(_client: Any, full_name: str, _msg: str) -> str:
        del full_name
        return str(target_path)

    monkeypatch.setattr(rollback_module, "_resolve_target_location", fake_resolve)


@pytest.fixture
def target_path(tmp_path: Path) -> Path:
    """Path to the silver table the tests will mutate."""
    return tmp_path / "silver"


def _seed_run(
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    run_id: str | None = None,
    notebook: str = "rollback_unit.py",
) -> str:
    """Insert one ``agent_runs`` row and return its id."""
    run_id = run_id or str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add(
            AgentRun(
                id=run_id,
                principal="test",
                agent_id="phase-16-test",
                notebook_path=notebook,
                status="running",
                started_at=now,
            )
        )
        session.commit()
    return run_id


def _seed_op(
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    run_id: str,
    target: str,
    op_name: str = "merge",
    delta_version_before: int | None = 0,
    delta_version_after: int | None = 1,
    ordinal: int = 1,
) -> int:
    """Insert one ``agent_run_operations`` row and return its id."""
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        op = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=ordinal,
            op_name=op_name,
            params_json=json.dumps({"target": target}),
            target_table=target,
            delta_version_before=delta_version_before,
            delta_version_after=delta_version_after,
            started_at=now,
            finished_at=now,
        )
        session.add(op)
        session.commit()
        session.refresh(op)
        return op.id


def _bootstrap_silver(target: Path) -> None:
    """Create v0 of the silver table with three rows."""
    rows = pa.table(
        {
            "order_id": ["A", "B", "C"],
            "qty": [1, 2, 3],
            "unit_price": [2.5, 3.0, 4.5],
        }
    )
    deltalake.write_deltalake(str(target), rows, configuration=cdf_creation_config())


def _append_to_silver(target: Path, *, order_id: str, unit_price: float) -> None:
    """Append a single row, bumping the Delta version by 1."""
    rows = pa.table({"order_id": [order_id], "qty": [1], "unit_price": [unit_price]})
    deltalake.write_deltalake(str(target), rows, mode="append")


def _silver_count(target: Path) -> int:
    return deltalake.DeltaTable(str(target)).to_pyarrow_table().num_rows


class TestHappyPath:
    """The non-stale, non-ambiguous case — the demo replay shape."""

    def test_restores_to_recorded_version(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        target_path: Path,
    ) -> None:
        _bootstrap_silver(target_path)
        v0 = deltalake.DeltaTable(str(target_path)).version()
        _append_to_silver(target_path, order_id="D", unit_price=5.0)
        v1 = deltalake.DeltaTable(str(target_path)).version()
        assert v1 == v0 + 1
        assert _silver_count(target_path) == 4

        run_a = _seed_run(factory)
        _seed_op(
            factory,
            run_id=run_a,
            target="main.silver.orders",
            delta_version_before=v0,
            delta_version_after=v1,
        )
        run_b = _seed_run(factory, notebook="rollback_run.py")

        result = rollback_table(
            client=None,  # stubbed via _patch_target_resolution
            target="main.silver.orders",
            before_run=run_a,
            unreachable_msg="(test) catalog unreachable",
            agent_run_id=run_b,
        )

        assert isinstance(result, RollbackResult)
        assert result.target_version_restored == v0
        assert result.version_before == v1
        assert result.version_after == v1 + 1
        assert _silver_count(target_path) == 3  # rolled back to pre-append state

    def test_audit_row_records_rollback(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        target_path: Path,
    ) -> None:
        _bootstrap_silver(target_path)
        v0 = deltalake.DeltaTable(str(target_path)).version()
        _append_to_silver(target_path, order_id="D", unit_price=5.0)
        v1 = deltalake.DeltaTable(str(target_path)).version()

        run_a = _seed_run(factory)
        op_a = _seed_op(
            factory,
            run_id=run_a,
            target="main.silver.orders",
            delta_version_before=v0,
            delta_version_after=v1,
        )
        run_b = _seed_run(factory, notebook="rollback_run.py")

        rollback_table(
            client=None,
            target="main.silver.orders",
            before_run=run_a,
            unreachable_msg="(test)",
            agent_run_id=run_b,
        )

        with factory() as s:
            rollback_op = s.scalar(
                select(AgentRunOperation).where(AgentRunOperation.agent_run_id == run_b)
            )
        assert rollback_op is not None
        assert rollback_op.op_name == "rollback"
        assert rollback_op.target_table == "main.silver.orders"
        assert rollback_op.delta_version_before == v1
        assert rollback_op.delta_version_after == v1 + 1
        params = json.loads(rollback_op.params_json)
        assert params["rolled_back_run"] == run_a
        assert params["rolled_back_op_id"] == op_a
        assert params["target_version_restored"] == v0
        assert params["allow_force"] is False


class TestRefusalModes:
    """Each refusal must leave the Delta state untouched."""

    def test_target_not_found(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        target_path: Path,
    ) -> None:
        _bootstrap_silver(target_path)
        v_before = deltalake.DeltaTable(str(target_path)).version()
        run_a = _seed_run(factory)
        # No op was seeded for run_a.
        run_b = _seed_run(factory, notebook="rollback_run.py")

        with pytest.raises(RollbackTargetNotFound):
            rollback_table(
                client=None,
                target="main.silver.orders",
                before_run=run_a,
                unreachable_msg="(test)",
                agent_run_id=run_b,
            )

        # Delta untouched.
        assert deltalake.DeltaTable(str(target_path)).version() == v_before

    def test_ambiguous_without_op_ordinal(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        target_path: Path,
    ) -> None:
        _bootstrap_silver(target_path)
        v_before = deltalake.DeltaTable(str(target_path)).version()
        run_a = _seed_run(factory)
        _seed_op(
            factory,
            run_id=run_a,
            target="main.silver.orders",
            delta_version_before=0,
            delta_version_after=1,
            ordinal=1,
        )
        _seed_op(
            factory,
            run_id=run_a,
            target="main.silver.orders",
            delta_version_before=1,
            delta_version_after=2,
            ordinal=2,
        )
        run_b = _seed_run(factory, notebook="rollback_run.py")

        with pytest.raises(RollbackAmbiguous) as excinfo:
            rollback_table(
                client=None,
                target="main.silver.orders",
                before_run=run_a,
                unreachable_msg="(test)",
                agent_run_id=run_b,
            )
        ordinals = [c.ordinal for c in excinfo.value.candidates]
        assert ordinals == [1, 2]
        assert deltalake.DeltaTable(str(target_path)).version() == v_before

    def test_ambiguous_resolved_by_op_ordinal(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        target_path: Path,
    ) -> None:
        _bootstrap_silver(target_path)
        v0 = deltalake.DeltaTable(str(target_path)).version()
        _append_to_silver(target_path, order_id="D", unit_price=5.0)
        v1 = deltalake.DeltaTable(str(target_path)).version()
        _append_to_silver(target_path, order_id="E", unit_price=6.0)
        v2 = deltalake.DeltaTable(str(target_path)).version()

        run_a = _seed_run(factory)
        _seed_op(
            factory,
            run_id=run_a,
            target="main.silver.orders",
            delta_version_before=v0,
            delta_version_after=v1,
            ordinal=1,
        )
        _seed_op(
            factory,
            run_id=run_a,
            target="main.silver.orders",
            delta_version_before=v1,
            delta_version_after=v2,
            ordinal=2,
        )
        run_b = _seed_run(factory, notebook="rollback_run.py")

        # Pick the second op explicitly — it's the current-aligned one,
        # so staleness passes.
        result = rollback_table(
            client=None,
            target="main.silver.orders",
            before_run=run_a,
            unreachable_msg="(test)",
            op_ordinal=2,
            agent_run_id=run_b,
        )
        assert result.target_version_restored == v1

    def test_invalid_when_creation_op(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        target_path: Path,
    ) -> None:
        _bootstrap_silver(target_path)
        v_before = deltalake.DeltaTable(str(target_path)).version()
        run_a = _seed_run(factory)
        _seed_op(
            factory,
            run_id=run_a,
            target="main.silver.orders",
            op_name="write_table",
            delta_version_before=None,  # creation op
            delta_version_after=0,
        )
        run_b = _seed_run(factory, notebook="rollback_run.py")

        with pytest.raises(RollbackInvalid):
            rollback_table(
                client=None,
                target="main.silver.orders",
                before_run=run_a,
                unreachable_msg="(test)",
                agent_run_id=run_b,
            )
        assert deltalake.DeltaTable(str(target_path)).version() == v_before

    def test_stale_without_force(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        target_path: Path,
    ) -> None:
        _bootstrap_silver(target_path)
        v0 = deltalake.DeltaTable(str(target_path)).version()
        _append_to_silver(target_path, order_id="D", unit_price=5.0)
        v1 = deltalake.DeltaTable(str(target_path)).version()
        # Second unrelated write moves table past run_a's recorded version.
        _append_to_silver(target_path, order_id="E", unit_price=6.0)
        v2 = deltalake.DeltaTable(str(target_path)).version()
        assert v2 == v1 + 1

        run_a = _seed_run(factory)
        _seed_op(
            factory,
            run_id=run_a,
            target="main.silver.orders",
            delta_version_before=v0,
            delta_version_after=v1,
            ordinal=1,
        )
        run_c = _seed_run(factory, notebook="other_run.py")
        _seed_op(
            factory,
            run_id=run_c,
            target="main.silver.orders",
            delta_version_before=v1,
            delta_version_after=v2,
            ordinal=1,
        )
        run_b = _seed_run(factory, notebook="rollback_run.py")

        with pytest.raises(RollbackStale) as excinfo:
            rollback_table(
                client=None,
                target="main.silver.orders",
                before_run=run_a,
                unreachable_msg="(test)",
                agent_run_id=run_b,
            )
        assert excinfo.value.current_version == v2
        assert excinfo.value.expected_version == v1
        assert excinfo.value.intervening_op_count == 1
        assert deltalake.DeltaTable(str(target_path)).version() == v2

    def test_stale_with_force_succeeds(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        target_path: Path,
    ) -> None:
        _bootstrap_silver(target_path)
        v0 = deltalake.DeltaTable(str(target_path)).version()
        _append_to_silver(target_path, order_id="D", unit_price=5.0)
        v1 = deltalake.DeltaTable(str(target_path)).version()
        _append_to_silver(target_path, order_id="E", unit_price=6.0)
        v2 = deltalake.DeltaTable(str(target_path)).version()

        run_a = _seed_run(factory)
        _seed_op(
            factory,
            run_id=run_a,
            target="main.silver.orders",
            delta_version_before=v0,
            delta_version_after=v1,
        )
        run_b = _seed_run(factory, notebook="rollback_run.py")

        result = rollback_table(
            client=None,
            target="main.silver.orders",
            before_run=run_a,
            unreachable_msg="(test)",
            allow_force=True,
            agent_run_id=run_b,
        )
        assert result.target_version_restored == v0
        assert result.version_before == v2
        assert result.version_after == v2 + 1
        assert _silver_count(target_path) == 3

        # Audit row records allow_force=True.
        with factory() as s:
            rb = s.scalar(select(AgentRunOperation).where(AgentRunOperation.agent_run_id == run_b))
        assert rb is not None
        assert rb.op_name == "rollback"
        params = json.loads(rb.params_json)
        assert params["allow_force"] is True
