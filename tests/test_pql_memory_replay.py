"""unit tests for ``pql.memory.replay`` dispatcher.

The dispatcher's behaviour is bucketed into three outcome
classes (replayable, data_unavailable, unsafe) plus the
``policy=STRICT`` raise.  These tests cover each path with the
in-memory SQLite fixture; the real-execution path is
intentionally out-of-scope (see ``_replay.py``
module docstring).
"""

from __future__ import annotations

import datetime
import json
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.exceptions import ValidationError
from pointlessql.models import AgentRun, AgentRunOperation, Base
from pointlessql.pql import memory
from pointlessql.services.agent_runs.memory._replay import (
    DATA_UNAVAILABLE_OPS,
    REPLAYABLE_OPS,
    UNSAFE_OPS,
    ReplayUnsafeOpError,
    _rewrite_schema_refs_in_query,
    _rewrite_target_table,
    _split_branch_fqn,
)
from pointlessql.services.agent_runs.memory._replay_policy import ReplayPolicy
from pointlessql.types import OpName, RunId


@pytest.fixture
def factory() -> sessionmaker:  # type: ignore[type-arg]
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _seed_run_with_ops(
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    agent_id: str = "agent-alpha",
    ops: list[tuple[str, dict, str | None]] | None = None,
) -> RunId:
    """Seed a run with a sequence of ops.

    Each op tuple is ``(op_name, params_dict, target_table)``.
    """
    if ops is None:
        ops = []
    run_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    with factory() as s:
        s.add(
            AgentRun(
                id=run_id,
                principal="test@example.com",
                agent_id=agent_id,
                notebook_path="replay_test.py",
                status="succeeded",
                started_at=now,
                finished_at=now,
            )
        )
        s.flush()
        for i, (op_name, params, target) in enumerate(ops, start=1):
            s.add(
                AgentRunOperation(
                    agent_run_id=run_id,
                    ordinal=i,
                    op_name=op_name,
                    params_json=json.dumps(params, default=str),
                    target_table=target,
                    started_at=now,
                    finished_at=now,
                )
            )
        s.commit()
    return RunId(run_id)


class TestUtilities:
    """Pure-Python helpers — no DB needed."""

    def test_split_branch_fqn_happy(self) -> None:
        assert _split_branch_fqn("main.branch_x") == ("main", "branch_x")

    def test_split_branch_fqn_three_parts_raises(self) -> None:
        with pytest.raises(ValidationError):
            _split_branch_fqn("a.b.c")

    def test_split_branch_fqn_one_part_raises(self) -> None:
        with pytest.raises(ValidationError):
            _split_branch_fqn("noschema")

    def test_rewrite_target_table_three_part(self) -> None:
        result = _rewrite_target_table("main.bronze.orders", "main", "mem_x")
        assert result == "main.mem_x.orders"

    def test_rewrite_target_table_none(self) -> None:
        assert _rewrite_target_table(None, "main", "mem_x") is None

    def test_rewrite_target_table_non_three_part_passthrough(self) -> None:
        # Best-effort: don't fail the whole replay over one weird target
        assert _rewrite_target_table("weird", "main", "mem_x") == "weird"

    def test_rewrite_schema_refs_in_query_happy(self) -> None:
        original = "SELECT * FROM main.bronze.orders WHERE id > 0"
        rewritten = _rewrite_schema_refs_in_query(original, "main.bronze", "main.mem_x")
        assert rewritten == "SELECT * FROM main.mem_x.orders WHERE id > 0"

    def test_rewrite_schema_refs_only_word_boundary(self) -> None:
        # Should not match inside 'main.bronze_old.orders'
        original = "SELECT * FROM main.bronze_old.orders"
        rewritten = _rewrite_schema_refs_in_query(original, "main.bronze", "main.mem_x")
        assert rewritten == original


class TestClassification:
    """Op-name buckets — guard against accidental reshuffles."""

    def test_replayable_does_not_overlap_data_unavailable(self) -> None:
        assert REPLAYABLE_OPS.isdisjoint(DATA_UNAVAILABLE_OPS)

    def test_replayable_does_not_overlap_unsafe(self) -> None:
        assert REPLAYABLE_OPS.isdisjoint(UNSAFE_OPS)

    def test_unsafe_does_not_overlap_data_unavailable(self) -> None:
        assert UNSAFE_OPS.isdisjoint(DATA_UNAVAILABLE_OPS)

    def test_sql_is_replayable(self) -> None:
        assert OpName.SQL.value in REPLAYABLE_OPS

    def test_merge_is_data_unavailable(self) -> None:
        assert OpName.MERGE.value in DATA_UNAVAILABLE_OPS

    def test_dbt_test_is_unsafe(self) -> None:
        assert OpName.DBT_TEST.value in UNSAFE_OPS

    def test_branch_create_is_unsafe(self) -> None:
        assert OpName.BRANCH_CREATE.value in UNSAFE_OPS


class TestReplayHappyPath:
    """End-to-end against the in-memory fixture."""

    def test_replay_unknown_run_raises(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        with pytest.raises(ValidationError, match="not registered"):
            memory.replay(
                client=object(),
                engine=object(),
                session_factory=factory,
                branch_schema_fqn="main.mem_x",
                source_run_id=RunId("00000000-0000-0000-0000-000000000000"),
                unreachable_msg="x",
            )

    def test_replay_run_with_no_ops_raises(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_run_with_ops(factory, ops=[])
        with pytest.raises(ValidationError, match="zero operations"):
            memory.replay(
                client=object(),
                engine=object(),
                session_factory=factory,
                branch_schema_fqn="main.mem_x",
                source_run_id=run_id,
                unreachable_msg="x",
            )

    def test_replay_sql_rewrites_schema_refs(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_run_with_ops(
            factory,
            ops=[
                (
                    "write_table",
                    {"full_name": "main.bronze.orders"},
                    "main.bronze.orders",
                ),
                (
                    "sql",
                    {"query": "SELECT count(*) FROM main.bronze.orders"},
                    None,
                ),
            ],
        )
        result = memory.replay(
            client=object(),
            engine=object(),
            session_factory=factory,
            branch_schema_fqn="main.mem_x",
            source_run_id=run_id,
            unreachable_msg="x",
        )
        # write_table → data_unavailable, sql → replayable
        assert result.ops_replayed == 1
        skip_reasons = {s.reason for s in result.ops_skipped}
        assert skip_reasons == {"data_unavailable"}

        # Verify the replay run got a re-recorded SQL op with rewritten query
        with factory() as s:
            replay_ops = list(
                s.scalars(
                    select(AgentRunOperation).where(
                        AgentRunOperation.agent_run_id == str(result.replay_run_id)
                    )
                ).all()
            )
        assert len(replay_ops) == 1
        params = json.loads(replay_ops[0].params_json)
        assert params["query"] == "SELECT count(*) FROM main.mem_x.orders"
        assert params["_original_query"] == "SELECT count(*) FROM main.bronze.orders"
        assert params["_replay_recorded_only"] is True

    def test_replay_creates_new_agent_run(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_run_with_ops(
            factory,
            agent_id="agent-x",
            ops=[
                ("write_table", {}, "main.bronze.t"),
                ("sql", {"query": "SELECT 1"}, None),
            ],
        )
        result = memory.replay(
            client=object(),
            engine=object(),
            session_factory=factory,
            branch_schema_fqn="main.mem_x",
            source_run_id=run_id,
            unreachable_msg="x",
        )
        with factory() as s:
            replay_run = s.get(AgentRun, str(result.replay_run_id))
        assert replay_run is not None
        assert replay_run.agent_id == "agent-x"
        assert replay_run.status == "succeeded"
        assert replay_run.notebook_path == f"<replay of {run_id}>"
        assert replay_run.finished_at is not None

    def test_replay_skips_unsafe_ops_under_skip_unsafe_policy(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_run_with_ops(
            factory,
            ops=[
                ("write_table", {}, "main.bronze.t"),
                ("dbt_model", {"unique_id": "model.x"}, "main.bronze.t"),
                ("train_model", {"framework": "sklearn"}, None),
                ("sql", {"query": "SELECT 1"}, None),
            ],
        )
        result = memory.replay(
            client=object(),
            engine=object(),
            session_factory=factory,
            branch_schema_fqn="main.mem_x",
            source_run_id=run_id,
            policy=ReplayPolicy.SKIP_UNSAFE,
            unreachable_msg="x",
        )
        assert result.ops_replayed == 1  # only sql
        reasons = [s.reason for s in result.ops_skipped]
        assert reasons.count("unsafe_op") == 2  # dbt_model + train_model
        assert reasons.count("data_unavailable") == 1  # write_table

    def test_replay_strict_policy_raises_on_unsafe(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_run_with_ops(
            factory,
            ops=[
                ("write_table", {}, "main.bronze.t"),
                ("dbt_model", {"unique_id": "model.x"}, "main.bronze.t"),
            ],
        )
        with pytest.raises(ReplayUnsafeOpError, match="dbt_model"):
            memory.replay(
                client=object(),
                engine=object(),
                session_factory=factory,
                branch_schema_fqn="main.mem_x",
                source_run_id=run_id,
                policy=ReplayPolicy.STRICT,
                unreachable_msg="x",
            )

        # Replay run should be marked failed
        with factory() as s:
            replay_runs = list(
                s.scalars(select(AgentRun).where(AgentRun.notebook_path.like("<replay%"))).all()
            )
        assert len(replay_runs) == 1
        assert replay_runs[0].status == "failed"

    def test_replay_agent_id_override(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_run_with_ops(
            factory,
            agent_id="source-agent",
            ops=[("sql", {"query": "SELECT 1"}, None)],
        )
        result = memory.replay(
            client=object(),
            engine=object(),
            session_factory=factory,
            branch_schema_fqn="main.mem_x",
            source_run_id=run_id,
            agent_id="replay-agent",
            unreachable_msg="x",
        )
        with factory() as s:
            replay_run = s.get(AgentRun, str(result.replay_run_id))
        assert replay_run is not None
        assert replay_run.agent_id == "replay-agent"

    def test_replay_stamps_replay_of_marker(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_run_with_ops(
            factory,
            ops=[("sql", {"query": "SELECT 1"}, None)],
        )
        result = memory.replay(
            client=object(),
            engine=object(),
            session_factory=factory,
            branch_schema_fqn="main.mem_x",
            source_run_id=run_id,
            unreachable_msg="x",
        )
        with factory() as s:
            replay_op = s.scalars(
                select(AgentRunOperation).where(
                    AgentRunOperation.agent_run_id == str(result.replay_run_id)
                )
            ).first()
            source_op = s.scalars(
                select(AgentRunOperation).where(AgentRunOperation.agent_run_id == str(run_id))
            ).first()
        assert replay_op is not None
        assert source_op is not None
        params = json.loads(replay_op.params_json)
        assert params["_replay_of"] == source_op.id
        assert result.ops_replayed == 1


class TestReplayUnknownOpName:
    """An op_name that's neither replayable nor unsafe gets ``unknown_op_name``."""

    def test_unrecognised_op_name_records_skip(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        # Bypass the OpName enum by inserting a row directly with an
        # op_name string that's not in REPLAYABLE/UNSAFE/DATA_UNAVAILABLE.
        # Note: SQLAlchemy CHECK constraint would reject truly unknown
        # values, so we have to pick an enum value that isn't in any
        # bucket.  Looking at OpName: all 19 values are covered, so
        # this test is a guard against future enum-vs-bucket drift.
        # We seed with a real value and assert the buckets stay
        # exhaustive instead.
        run_id = _seed_run_with_ops(
            factory,
            ops=[(op_name.value, {}, None) for op_name in OpName],
        )
        result = memory.replay(
            client=object(),
            engine=object(),
            session_factory=factory,
            branch_schema_fqn="main.mem_x",
            source_run_id=run_id,
            policy=ReplayPolicy.SKIP_UNSAFE,
            unreachable_msg="x",
        )
        unknown_count = sum(1 for s in result.ops_skipped if s.reason == "unknown_op_name")
        assert unknown_count == 0, (
            "OpName enum has values not classified into replay/unsafe/data_unavailable; "
            "extend the buckets in _replay.py"
        )
