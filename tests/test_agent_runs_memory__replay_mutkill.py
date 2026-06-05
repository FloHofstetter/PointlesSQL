"""Mutation-killing tests for the replay dispatcher.

These pin the dispatcher's observable behaviour: the columns written
onto the new replay :class:`AgentRun`, the rewritten target/query on
re-recorded ops, the ``ReplaySkip`` fields for each skip bucket, the
replayed counter, the dispatch-failure path, and the returned
``ReplayResult`` timestamps.  They complement ``test_pql_memory_replay``
by asserting on the exact values a mutant would corrupt.
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
from pointlessql.services.agent_runs.memory import _replay as replay_mod
from pointlessql.services.agent_runs.memory._replay import (
    _split_branch_fqn,
)
from pointlessql.types import RunId


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
    principal: str = "test@example.com",
    workspace_id: int = 1,
    ops: list[tuple[str, dict, str | None]] | None = None,
) -> RunId:
    """Seed a run with a sequence of ``(op_name, params, target)`` ops."""
    if ops is None:
        ops = []
    run_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    with factory() as s:
        s.add(
            AgentRun(
                id=run_id,
                workspace_id=workspace_id,
                principal=principal,
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


def _seed_run_with_raw_op(
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    op_name: str,
    params_json: str,
    target_table: str | None = None,
) -> RunId:
    """Seed a run with one op whose ``params_json`` is written verbatim.

    Used to plant malformed JSON that the ORM's ``json.dumps`` helper
    would otherwise prevent, exercising the dispatcher's
    ``dispatch_failed`` path.
    """
    run_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    with factory() as s:
        s.add(
            AgentRun(
                id=run_id,
                workspace_id=1,
                principal="test@example.com",
                agent_id="agent-alpha",
                notebook_path="replay_test.py",
                status="succeeded",
                started_at=now,
                finished_at=now,
            )
        )
        s.flush()
        s.add(
            AgentRunOperation(
                agent_run_id=run_id,
                ordinal=1,
                op_name=op_name,
                params_json=params_json,
                target_table=target_table,
                started_at=now,
                finished_at=now,
            )
        )
        s.commit()
    return RunId(run_id)


def _replay(factory, run_id, **kwargs):  # type: ignore[no-untyped-def]
    defaults = {
        "client": object(),
        "engine": object(),
        "session_factory": factory,
        "branch_schema_fqn": "main.mem_x",
        "source_run_id": run_id,
        "unreachable_msg": "x",
    }
    defaults.update(kwargs)
    return memory.replay(**defaults)


def _replay_run_row(factory, replay_run_id) -> AgentRun:  # type: ignore[no-untyped-def]
    with factory() as s:
        row = s.get(AgentRun, str(replay_run_id))
    assert row is not None
    return row


def _replay_ops(factory, replay_run_id) -> list[AgentRunOperation]:  # type: ignore[no-untyped-def]
    with factory() as s:
        return list(
            s.scalars(
                select(AgentRunOperation)
                .where(AgentRunOperation.agent_run_id == str(replay_run_id))
                .order_by(AgentRunOperation.ordinal)
            ).all()
        )


class TestReplayRunColumns:
    """The new replay :class:`AgentRun` mirrors the source's columns."""

    def test_tables_touched_records_branch_fqn_as_json_list(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        # Pins tables_touched = json.dumps([branch_schema_fqn]); a mutant
        # that drops it, nulls it, or json.dumps(None) would differ.
        run_id = _seed_run_with_ops(factory, ops=[("sql", {"query": "SELECT 1"}, None)])
        result = _replay(factory, run_id)
        row = _replay_run_row(factory, result.replay_run_id)
        assert row.tables_touched == json.dumps(["main.mem_x"])

    def test_workspace_id_copied_from_source(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        # Seed with a non-default workspace so dropping the kwarg (which
        # falls back to the server_default of 1) or nulling it is observable.
        run_id = _seed_run_with_ops(
            factory,
            workspace_id=42,
            ops=[("sql", {"query": "SELECT 1"}, None)],
        )
        result = _replay(factory, run_id)
        replay = _replay_run_row(factory, result.replay_run_id)
        assert replay.workspace_id == 42

    def test_principal_copied_from_source(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_run_with_ops(
            factory,
            principal="alice@example.com",
            ops=[("sql", {"query": "SELECT 1"}, None)],
        )
        result = _replay(factory, run_id)
        replay = _replay_run_row(factory, result.replay_run_id)
        assert replay.principal == "alice@example.com"

    def test_replay_run_id_is_a_real_uuid(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        # str(uuid.uuid4()) -> str(None) would yield "None"; assert the id
        # parses as a UUID instead.
        run_id = _seed_run_with_ops(factory, ops=[("sql", {"query": "SELECT 1"}, None)])
        result = _replay(factory, run_id)
        parsed = uuid.UUID(str(result.replay_run_id))
        assert str(parsed) == str(result.replay_run_id)
        assert str(result.replay_run_id) != "None"


class TestReplayedOpRewrites:
    """Re-recorded replayable ops carry the rewritten branch target/query."""

    def test_replayable_target_rewritten_to_branch_schema(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        # autoload is replayable AND carries a 3-part target.  The recorded
        # replay op's target must be the branch-rewritten FQN, not None and
        # not a 'None.'/'.None.' string from a nulled rewrite arg.
        run_id = _seed_run_with_ops(
            factory,
            ops=[("autoload", {"full_name": "main.bronze.orders"}, "main.bronze.orders")],
        )
        result = _replay(factory, run_id)
        assert result.ops_replayed == 1
        ops = _replay_ops(factory, result.replay_run_id)
        assert len(ops) == 1
        assert ops[0].target_table == "main.mem_x.orders"

    def test_replayable_sql_query_rewritten(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_run_with_ops(
            factory,
            ops=[
                ("write_table", {}, "main.bronze.orders"),
                ("sql", {"query": "SELECT * FROM main.bronze.orders"}, None),
            ],
        )
        result = _replay(factory, run_id)
        ops = _replay_ops(factory, result.replay_run_id)
        params = json.loads(ops[0].params_json)
        assert params["query"] == "SELECT * FROM main.mem_x.orders"


class TestSkipBucketFields:
    """Each ``ReplaySkip`` carries the source op's id and name."""

    def test_unsafe_skip_carries_op_id_and_name(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_run_with_ops(
            factory,
            ops=[("dbt_model", {"unique_id": "model.x"}, "main.bronze.t")],
        )
        with factory() as s:
            source_op = s.scalars(
                select(AgentRunOperation).where(AgentRunOperation.agent_run_id == str(run_id))
            ).one()
            source_op_id = source_op.id
        result = _replay(factory, run_id)
        unsafe = [sk for sk in result.ops_skipped if sk.reason == "unsafe_op"]
        assert len(unsafe) == 1
        assert unsafe[0].op_id == source_op_id
        assert unsafe[0].op_name == "dbt_model"

    def test_data_unavailable_skip_carries_op_id_and_name(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_run_with_ops(
            factory,
            ops=[("merge", {}, "main.bronze.t")],
        )
        with factory() as s:
            source_op = s.scalars(
                select(AgentRunOperation).where(AgentRunOperation.agent_run_id == str(run_id))
            ).one()
            source_op_id = source_op.id
        result = _replay(factory, run_id)
        skips = [sk for sk in result.ops_skipped if sk.reason == "data_unavailable"]
        assert len(skips) == 1
        assert skips[0].op_id == source_op_id
        assert skips[0].op_name == "merge"


class TestReplayedCounter:
    """The replayed counter accumulates across every replayable op."""

    def test_two_replayable_ops_increment_counter_to_two(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        # `replayed += 1` -> `replayed = 1` would stick the count at 1.
        run_id = _seed_run_with_ops(
            factory,
            ops=[
                ("sql", {"query": "SELECT 1"}, None),
                ("sql", {"query": "SELECT 2"}, None),
                ("sql", {"query": "SELECT 3"}, None),
            ],
        )
        result = _replay(factory, run_id)
        assert result.ops_replayed == 3


class TestDispatchFailedPath:
    """A replayable op with malformed params_json yields a dispatch skip."""

    def test_malformed_params_records_dispatch_failed_skip(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_run_with_raw_op(
            factory,
            op_name="sql",
            params_json="{not valid json",
        )
        result = _replay(factory, run_id)
        # The op is replayable but un-parseable: no op replayed, one skip
        # with a dispatch_failed reason that names the source op.
        assert result.ops_replayed == 0
        assert len(result.ops_skipped) == 1
        skip = result.ops_skipped[0]
        assert skip is not None
        assert skip.reason.startswith("dispatch_failed")
        assert "malformed params_json" in skip.reason
        assert skip.op_name == "sql"

    def test_dispatch_skip_carries_source_op_id(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_run_with_raw_op(
            factory,
            op_name="sql",
            params_json="{still bad",
        )
        with factory() as s:
            source_op = s.scalars(
                select(AgentRunOperation).where(AgentRunOperation.agent_run_id == str(run_id))
            ).one()
            source_op_id = source_op.id
        result = _replay(factory, run_id)
        assert result.ops_skipped[0].op_id == source_op_id

    def test_dispatch_failure_does_not_halt_later_ops(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        # The `continue` after a replayable op must NOT become a `break`:
        # an unsafe op AFTER a (failed) replayable op must still be visited.
        run_id = _seed_run_with_ops(
            factory,
            ops=[
                ("sql", {"query": "SELECT 1"}, None),
                ("dbt_model", {"unique_id": "model.x"}, "main.bronze.t"),
            ],
        )
        result = _replay(factory, run_id)
        assert result.ops_replayed == 1
        reasons = [sk.reason for sk in result.ops_skipped]
        assert "unsafe_op" in reasons


class TestReplayResultTimestamps:
    """The returned ``ReplayResult`` carries tz-aware start/finish stamps."""

    def test_started_and_finished_are_present(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_run_with_ops(factory, ops=[("sql", {"query": "SELECT 1"}, None)])
        result = _replay(factory, run_id)
        assert result.started_at is not None
        assert result.finished_at is not None

    def test_started_and_finished_are_timezone_aware(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        # now(datetime.UTC) -> now(None) drops tzinfo on the in-memory result.
        run_id = _seed_run_with_ops(factory, ops=[("sql", {"query": "SELECT 1"}, None)])
        result = _replay(factory, run_id)
        assert result.started_at.tzinfo is not None
        assert result.finished_at.tzinfo is not None


class TestSplitBranchFqnErrorMessage:
    """The two-part FQN guard names the offending value in its message."""

    def test_error_message_describes_two_part_requirement(self) -> None:
        with pytest.raises(ValidationError) as exc:
            _split_branch_fqn("a.b.c")
        assert "must be two-part" in str(exc.value)
        assert "a.b.c" in str(exc.value)


class TestInitialReplayRunStatus:
    """The new replay run is created with the literal ``"running"`` status.

    The finalise step always overwrites the status to ``"succeeded"`` /
    ``"failed"`` before the call returns, so the transient ``"running"``
    value is only observable if finalisation is suppressed.  Stubbing the
    finaliser to a no-op exposes the exact literal the create step wrote,
    pinning it against case / sentinel-string corruption.
    """

    def test_freshly_created_replay_run_has_running_status(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        run_id = _seed_run_with_ops(factory, ops=[("sql", {"query": "SELECT 1"}, None)])
        monkeypatch.setattr(replay_mod, "_finalise_replay_run", lambda *a, **k: None)
        result = _replay(factory, run_id)
        row = _replay_run_row(factory, result.replay_run_id)
        # Without finalisation the create-step literal survives verbatim:
        # "RUNNING" / "XXrunningXX" would not equal "running".
        assert row.status == "running"
