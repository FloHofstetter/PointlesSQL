"""Phase 90.0a — unit tests for ``pql.memory.record`` / ``recall``.

Two facades (record, recall) plus the underlying
``recall_operations`` helper.  The fixtures mirror
``test_merge_rejects.py``'s in-memory SQLite + ``Base.metadata`` pattern
so the FK chain (workspace → agent_run → operation) can be exercised
without touching the live ORM bootstrap.
"""

from __future__ import annotations

import datetime
import json
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.exceptions import AuditUnavailableError
from pointlessql.models import AgentRun, AgentRunOperation, Base
from pointlessql.pql import memory
from pointlessql.services.agent_runs.memory._recall import recall_operations
from pointlessql.types import OpName, RunId


@pytest.fixture
def factory() -> sessionmaker:  # type: ignore[type-arg]
    """In-memory SQLite with the full ORM schema applied."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _seed_run(
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    agent_id: str = "agent-alpha",
    started_at: datetime.datetime | None = None,
) -> RunId:
    """Insert a minimal :class:`AgentRun` row and return its id."""
    run_id = str(uuid.uuid4())
    now = started_at or datetime.datetime.now(datetime.UTC)
    with factory() as s:
        s.add(
            AgentRun(
                id=run_id,
                principal="test@example.com",
                agent_id=agent_id,
                notebook_path="memory_test.py",
                status="running",
                started_at=now,
            )
        )
        s.commit()
    return RunId(run_id)


class TestRecord:
    """``pql.memory.record`` happy-path + error-path."""

    def test_record_writes_operation_row(self, factory: sessionmaker) -> None:  # type: ignore[type-arg]
        run_id = _seed_run(factory)
        op_id = memory.record(
            session_factory=factory,
            agent_run_id=run_id,
            op_name=OpName.SQL,
            params={"query": "SELECT 1"},
            target_table=None,
        )
        with factory() as s:
            row = s.get(AgentRunOperation, op_id)
            assert row is not None
            assert row.agent_run_id == run_id
            assert row.op_name == "sql"
            assert json.loads(row.params_json) == {"query": "SELECT 1"}
            assert row.error_message is None
            assert row.ordinal == 1

    def test_record_ordinal_increments(self, factory: sessionmaker) -> None:  # type: ignore[type-arg]
        run_id = _seed_run(factory)
        memory.record(
            session_factory=factory,
            agent_run_id=run_id,
            op_name=OpName.SQL,
            params={},
        )
        memory.record(
            session_factory=factory,
            agent_run_id=run_id,
            op_name=OpName.WRITE_TABLE,
            params={"full_name": "c.s.t"},
            target_table="c.s.t",
            rows_affected=42,
        )
        with factory() as s:
            ordinals = list(
                s.scalars(
                    select(AgentRunOperation.ordinal).where(
                        AgentRunOperation.agent_run_id == run_id
                    )
                ).all()
            )
            assert ordinals == [1, 2]

    def test_record_with_error_message_marks_failure(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_run(factory)
        op_id = memory.record(
            session_factory=factory,
            agent_run_id=run_id,
            op_name=OpName.MERGE,
            params={"target": "c.s.t", "on": ["id"]},
            target_table="c.s.t",
            error_message="ValueError('bad key')",
        )
        with factory() as s:
            row = s.get(AgentRunOperation, op_id)
            assert row is not None
            assert row.error_message == "ValueError('bad key')"

    def test_record_unknown_run_raises(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        with pytest.raises(AuditUnavailableError):
            memory.record(
                session_factory=factory,
                agent_run_id=RunId("00000000-0000-0000-0000-000000000000"),
                op_name=OpName.SQL,
                params={},
            )


class TestRecallFacade:
    """``pql.memory.recall`` end-to-end with the in-memory factory."""

    def test_recall_returns_only_agents_ops(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        alpha_run = _seed_run(factory, agent_id="alpha")
        beta_run = _seed_run(factory, agent_id="beta")
        memory.record(
            session_factory=factory,
            agent_run_id=alpha_run,
            op_name=OpName.SQL,
            params={"q": "alpha-1"},
        )
        memory.record(
            session_factory=factory,
            agent_run_id=beta_run,
            op_name=OpName.SQL,
            params={"q": "beta-1"},
        )
        memory.record(
            session_factory=factory,
            agent_run_id=alpha_run,
            op_name=OpName.WRITE_TABLE,
            params={"q": "alpha-2"},
            target_table="c.s.t",
        )

        alpha_ops = memory.recall(session_factory=factory, agent_id="alpha")
        beta_ops = memory.recall(session_factory=factory, agent_id="beta")
        assert {op.op_name for op in alpha_ops} == {"sql", "write_table"}
        assert {op.op_name for op in beta_ops} == {"sql"}

    def test_recall_filters_by_op_name(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_run(factory)
        memory.record(
            session_factory=factory,
            agent_run_id=run_id,
            op_name=OpName.SQL,
            params={},
        )
        memory.record(
            session_factory=factory,
            agent_run_id=run_id,
            op_name=OpName.MERGE,
            params={"target": "c.s.t", "on": ["id"]},
            target_table="c.s.t",
        )
        merges = memory.recall(
            session_factory=factory,
            agent_id="agent-alpha",
            op_name=OpName.MERGE,
        )
        assert [op.op_name for op in merges] == ["merge"]

    def test_recall_filters_by_target_table(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_run(factory)
        memory.record(
            session_factory=factory,
            agent_run_id=run_id,
            op_name=OpName.WRITE_TABLE,
            params={"full_name": "c.s.bronze_a"},
            target_table="c.s.bronze_a",
        )
        memory.record(
            session_factory=factory,
            agent_run_id=run_id,
            op_name=OpName.WRITE_TABLE,
            params={"full_name": "c.s.bronze_b"},
            target_table="c.s.bronze_b",
        )
        only_a = memory.recall(
            session_factory=factory,
            agent_id="agent-alpha",
            target_table="c.s.bronze_a",
        )
        assert [op.target_table for op in only_a] == ["c.s.bronze_a"]

    def test_recall_filters_by_status_failed(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_run(factory)
        memory.record(
            session_factory=factory,
            agent_run_id=run_id,
            op_name=OpName.SQL,
            params={"q": "ok"},
        )
        memory.record(
            session_factory=factory,
            agent_run_id=run_id,
            op_name=OpName.SQL,
            params={"q": "broken"},
            error_message="RuntimeError('boom')",
        )
        failed = memory.recall(
            session_factory=factory,
            agent_id="agent-alpha",
            status="failed",
        )
        assert len(failed) == 1
        assert failed[0].error_message == "RuntimeError('boom')"

    def test_recall_unknown_status_raises(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        with pytest.raises(ValueError):
            memory.recall(
                session_factory=factory,
                agent_id="agent-alpha",
                status="bogus",
            )

    def test_recall_unknown_agent_returns_empty(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_run(factory, agent_id="alpha")
        memory.record(
            session_factory=factory,
            agent_run_id=run_id,
            op_name=OpName.SQL,
            params={},
        )
        empty = memory.recall(session_factory=factory, agent_id="ghost")
        assert empty == []

    def test_recall_orders_started_at_desc(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_run(factory)
        t0 = datetime.datetime(2026, 5, 1, 10, 0, tzinfo=datetime.UTC)
        t1 = t0 + datetime.timedelta(minutes=5)
        t2 = t0 + datetime.timedelta(minutes=10)
        memory.record(
            session_factory=factory,
            agent_run_id=run_id,
            op_name=OpName.SQL,
            params={"q": "0"},
            started_at=t0,
        )
        memory.record(
            session_factory=factory,
            agent_run_id=run_id,
            op_name=OpName.SQL,
            params={"q": "1"},
            started_at=t1,
        )
        memory.record(
            session_factory=factory,
            agent_run_id=run_id,
            op_name=OpName.SQL,
            params={"q": "2"},
            started_at=t2,
        )
        ops = memory.recall(session_factory=factory, agent_id="agent-alpha")
        # most-recent first
        assert [json.loads(o.params_json)["q"] for o in ops] == ["2", "1", "0"]

    def test_recall_limit_caps_at_1000(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_run(factory)
        for i in range(5):
            memory.record(
                session_factory=factory,
                agent_run_id=run_id,
                op_name=OpName.SQL,
                params={"q": str(i)},
            )
        # request 100_000 but only 5 ops exist; verify call doesn't raise
        ops = memory.recall(
            session_factory=factory,
            agent_id="agent-alpha",
            limit=100_000,
        )
        assert len(ops) == 5


class TestRecallSinceUntil:
    """Time-range filters on :func:`recall_operations`."""

    def test_since_filter_inclusive(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_run(factory)
        t0 = datetime.datetime(2026, 5, 1, 10, 0, tzinfo=datetime.UTC)
        t1 = t0 + datetime.timedelta(hours=1)
        memory.record(
            session_factory=factory,
            agent_run_id=run_id,
            op_name=OpName.SQL,
            params={"q": "early"},
            started_at=t0,
        )
        memory.record(
            session_factory=factory,
            agent_run_id=run_id,
            op_name=OpName.SQL,
            params={"q": "late"},
            started_at=t1,
        )
        late_only = recall_operations(
            factory,
            agent_id="agent-alpha",
            since=t1,
        )
        assert [json.loads(o.params_json)["q"] for o in late_only] == ["late"]

    def test_until_filter_exclusive(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_run(factory)
        t0 = datetime.datetime(2026, 5, 1, 10, 0, tzinfo=datetime.UTC)
        t1 = t0 + datetime.timedelta(hours=1)
        memory.record(
            session_factory=factory,
            agent_run_id=run_id,
            op_name=OpName.SQL,
            params={"q": "early"},
            started_at=t0,
        )
        memory.record(
            session_factory=factory,
            agent_run_id=run_id,
            op_name=OpName.SQL,
            params={"q": "late"},
            started_at=t1,
        )
        early_only = recall_operations(
            factory,
            agent_id="agent-alpha",
            until=t1,
        )
        assert [json.loads(o.params_json)["q"] for o in early_only] == ["early"]
