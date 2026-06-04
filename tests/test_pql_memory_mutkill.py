"""Mutation-killing unit tests for ``pql.memory``.

These tests pin behaviour that the existing ``test_pql_memory.py`` left
unobserved: the timestamp-default wiring inside :func:`memory.record`,
the ``rows_affected`` / ``finished_at`` pass-through, the ``since`` /
``until`` / ``limit`` forwarding inside :func:`memory.recall`, and the
exact keyword arguments the thin :func:`memory.branch` /
:func:`memory.fork` / :func:`memory.replay` facades forward to their
service delegates.

The branch/fork/replay facades import their delegate lazily inside the
function body, so the patch target is the *source* module attribute
(``_branch.branch_from_run`` / ``_replay.replay_run_on_branch``), which
the lazy import resolves at call time.
"""

from __future__ import annotations

import datetime
import json
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.models import AgentRun, AgentRunOperation, Base
from pointlessql.pql import memory
from pointlessql.services.agent_runs.memory import _branch, _replay
from pointlessql.services.agent_runs.memory._replay_policy import (
    ReplayPolicy,
)
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
) -> RunId:
    """Insert a minimal :class:`AgentRun` row and return its id."""
    run_id = str(uuid.uuid4())
    with factory() as s:
        s.add(
            AgentRun(
                id=run_id,
                principal="test@example.com",
                agent_id=agent_id,
                notebook_path="memory_test.py",
                status="running",
                started_at=datetime.datetime.now(datetime.UTC),
            )
        )
        s.commit()
    return RunId(run_id)


class _CaptureRecord:
    """Stub for ``record_operation`` that captures positional + kwargs.

    The facade calls ``record_operation`` with the session factory
    positionally and everything else by keyword; we capture both so the
    timestamp/rows_affected wiring can be asserted *before* any SQLite
    round-trip strips the tzinfo.
    """

    def __init__(self) -> None:
        self.args: tuple[object, ...] = ()
        self.kwargs: dict[str, object] = {}

    def __call__(self, *args: object, **kwargs: object) -> object:
        self.args = args
        self.kwargs = kwargs
        return 7  # an arbitrary OpId


class TestRecordTimestampDefaults:
    """The ``now`` / ``began_at`` / ``ended_at`` default wiring.

    Patches ``memory.record_operation`` to capture the exact values the
    facade computes, side-stepping SQLite's tz-stripping on round-trip.
    """

    def test_default_started_at_is_utc_aware_and_now(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``started_at`` defaults to an aware UTC instant near ``now``.

        Kills ``datetime.now(datetime.UTC)`` -> ``datetime.now(None)``:
        the naive variant yields a ``started_at`` with ``tzinfo is None``
        (and the local wall-clock, not UTC).
        """
        cap = _CaptureRecord()
        monkeypatch.setattr(memory, "record_operation", cap)
        before = datetime.datetime.now(datetime.UTC)
        memory.record(
            session_factory=object(),  # type: ignore[arg-type]
            agent_run_id=RunId("run-1"),
            op_name=OpName.SQL,
            params={},
        )
        after = datetime.datetime.now(datetime.UTC)
        started = cap.kwargs["started_at"]
        assert isinstance(started, datetime.datetime)
        assert started.tzinfo is not None
        assert started.utcoffset() == datetime.timedelta(0)
        assert before <= started <= after

    def test_default_finished_at_equals_began_at(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With no ``finished_at``, ``ended_at`` falls back to ``began_at``.

        Kills ``ended_at = finished_at or began_at`` -> ``= None`` and
        -> ``finished_at and began_at`` (both make the passed
        ``finished_at`` ``None`` instead of equal to ``started_at``).
        """
        cap = _CaptureRecord()
        monkeypatch.setattr(memory, "record_operation", cap)
        memory.record(
            session_factory=object(),  # type: ignore[arg-type]
            agent_run_id=RunId("run-1"),
            op_name=OpName.SQL,
            params={},
        )
        assert cap.kwargs["finished_at"] is not None
        assert cap.kwargs["finished_at"] == cap.kwargs["started_at"]

    def test_explicit_started_at_drives_finished_default(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``finished_at`` defaults to the explicit ``started_at``.

        ``began_at`` must be the caller's ``started_at`` (not ``now``),
        and ``ended_at`` must equal it.
        """
        cap = _CaptureRecord()
        monkeypatch.setattr(memory, "record_operation", cap)
        ts = datetime.datetime(2026, 5, 1, 9, 30, tzinfo=datetime.UTC)
        memory.record(
            session_factory=object(),  # type: ignore[arg-type]
            agent_run_id=RunId("run-1"),
            op_name=OpName.SQL,
            params={},
            started_at=ts,
        )
        assert cap.kwargs["started_at"] == ts
        assert cap.kwargs["finished_at"] == ts


class TestRecordPassThrough:
    """``rows_affected`` and an explicit ``finished_at`` reach the delegate."""

    def test_rows_affected_is_forwarded(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Kills ``rows_affected=rows_affected`` -> ``rows_affected=None``."""
        cap = _CaptureRecord()
        monkeypatch.setattr(memory, "record_operation", cap)
        memory.record(
            session_factory=object(),  # type: ignore[arg-type]
            agent_run_id=RunId("run-1"),
            op_name=OpName.WRITE_TABLE,
            params={"full_name": "c.s.t"},
            target_table="c.s.t",
            rows_affected=42,
        )
        assert cap.kwargs["rows_affected"] == 42

    def test_explicit_finished_at_is_forwarded(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Kills ``finished_at=ended_at`` -> ``finished_at=None``.

        An explicit ``finished_at`` distinct from ``started_at`` must be
        the value forwarded to the delegate.
        """
        cap = _CaptureRecord()
        monkeypatch.setattr(memory, "record_operation", cap)
        start = datetime.datetime(2026, 5, 1, 9, 0, tzinfo=datetime.UTC)
        end = datetime.datetime(2026, 5, 1, 9, 5, tzinfo=datetime.UTC)
        memory.record(
            session_factory=object(),  # type: ignore[arg-type]
            agent_run_id=RunId("run-1"),
            op_name=OpName.SQL,
            params={},
            started_at=start,
            finished_at=end,
        )
        assert cap.kwargs["finished_at"] == end
        assert cap.kwargs["finished_at"] != cap.kwargs["started_at"]

    def test_record_persists_through_real_delegate(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """End-to-end smoke: the real delegate stores a recoverable row.

        Guards the capture-based tests above against a wholesale signature
        drift by exercising the unpatched path once.
        """
        run_id = _seed_run(factory)
        op_id = memory.record(
            session_factory=factory,
            agent_run_id=run_id,
            op_name=OpName.WRITE_TABLE,
            params={"full_name": "c.s.t"},
            target_table="c.s.t",
            rows_affected=42,
        )
        with factory() as s:
            row = s.get(AgentRunOperation, op_id)
            assert row is not None
            assert row.rows_affected == 42
            assert row.finished_at is not None


class TestRecallForwarding:
    """``since`` / ``until`` / ``limit`` are forwarded, not dropped."""

    def _seed_two_at(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        t0: datetime.datetime,
        t1: datetime.datetime,
    ) -> None:
        run_id = _seed_run(factory)
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

    def test_since_is_forwarded(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """Kills ``since=since`` -> ``since=None`` / dropped-kwarg.

        Going through the public facade (not the delegate directly)
        proves the facade itself forwards ``since``.
        """
        t0 = datetime.datetime(2026, 5, 1, 10, 0, tzinfo=datetime.UTC)
        t1 = t0 + datetime.timedelta(hours=1)
        self._seed_two_at(factory, t0, t1)
        late = memory.recall(
            session_factory=factory,
            agent_id="agent-alpha",
            since=t1,
        )
        assert len(late) == 1
        assert json.loads(late[0].params_json)["q"] == "late"

    def test_until_is_forwarded(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """Kills ``until=until`` -> ``until=None`` / dropped-kwarg."""
        t0 = datetime.datetime(2026, 5, 1, 10, 0, tzinfo=datetime.UTC)
        t1 = t0 + datetime.timedelta(hours=1)
        self._seed_two_at(factory, t0, t1)
        early = memory.recall(
            session_factory=factory,
            agent_id="agent-alpha",
            until=t1,
        )
        assert len(early) == 1
        assert json.loads(early[0].params_json)["q"] == "early"

    def test_explicit_limit_is_forwarded(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """Kills ``limit=limit`` -> dropped-kwarg (delegate default 200).

        Five ops exist; an explicit ``limit=2`` must cap the result.
        Dropping the kwarg would fall back to the delegate default of
        200 and return all five.
        """
        run_id = _seed_run(factory)
        for i in range(5):
            memory.record(
                session_factory=factory,
                agent_run_id=run_id,
                op_name=OpName.SQL,
                params={"q": str(i)},
            )
        capped = memory.recall(
            session_factory=factory,
            agent_id="agent-alpha",
            limit=2,
        )
        assert len(capped) == 2

    def test_default_limit_is_200(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        """Kills the facade default ``limit: int = 200`` -> ``201``.

        Seed 201 ops; calling ``recall`` with no ``limit`` must return
        exactly 200 (the documented default), not 201.
        """
        run_id = _seed_run(factory)
        with factory() as s:
            base = datetime.datetime(2026, 5, 1, tzinfo=datetime.UTC)
            for i in range(201):
                s.add(
                    AgentRunOperation(
                        agent_run_id=run_id,
                        ordinal=i + 1,
                        op_name="sql",
                        params_json="{}",
                        started_at=base + datetime.timedelta(seconds=i),
                    )
                )
            s.commit()
        default_page = memory.recall(
            session_factory=factory,
            agent_id="agent-alpha",
        )
        assert len(default_page) == 200


class _Recorder:
    """Callable stub that captures the kwargs it was called with."""

    def __init__(self, ret: object) -> None:
        self.ret = ret
        self.kwargs: dict[str, object] | None = None

    def __call__(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        return self.ret


class TestBranchForwarding:
    """:func:`memory.branch` forwards its args verbatim, action='create'."""

    def test_branch_forwards_all_kwargs(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Kills client=None, unreachable_msg=None, pin default-flip, action."""
        sentinel = {"branch_schema_fqn": "c.s_branch"}
        rec = _Recorder(sentinel)
        monkeypatch.setattr(_branch, "branch_from_run", rec)

        client = object()
        factory = object()
        out = memory.branch(
            client=client,  # type: ignore[arg-type]
            session_factory=factory,  # type: ignore[arg-type]
            agent_id="agent-x",
            from_run_id=RunId("run-1"),
            branch_name="mine",
            unreachable_msg="catalog down",
        )
        assert out is sentinel
        assert rec.kwargs is not None
        assert rec.kwargs["client"] is client
        assert rec.kwargs["session_factory"] is factory
        assert rec.kwargs["agent_id"] == "agent-x"
        assert rec.kwargs["from_run_id"] == "run-1"
        assert rec.kwargs["branch_name"] == "mine"
        # Default pin_to_version must be True (kills default-flip to False).
        assert rec.kwargs["pin_to_version"] is True
        assert rec.kwargs["action"] == "create"
        assert rec.kwargs["unreachable_msg"] == "catalog down"


class TestForkForwarding:
    """:func:`memory.fork` is branch with action='fork'."""

    def test_fork_forwards_all_kwargs(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Kills client/branch_name/pin/unreachable=None and pin default-flip."""
        sentinel = {"branch_schema_fqn": "c.s_fork"}
        rec = _Recorder(sentinel)
        monkeypatch.setattr(_branch, "branch_from_run", rec)

        client = object()
        factory = object()
        out = memory.fork(
            client=client,  # type: ignore[arg-type]
            session_factory=factory,  # type: ignore[arg-type]
            agent_id="agent-y",
            from_run_id=RunId("run-2"),
            branch_name="forked",
            pin_to_version=False,
            unreachable_msg="boom",
        )
        assert out is sentinel
        assert rec.kwargs is not None
        assert rec.kwargs["client"] is client
        assert rec.kwargs["branch_name"] == "forked"
        # Explicit False must survive (kills pin_to_version=None passthrough).
        assert rec.kwargs["pin_to_version"] is False
        assert rec.kwargs["action"] == "fork"
        assert rec.kwargs["unreachable_msg"] == "boom"

    def test_fork_default_pin_is_true(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Kills the fork default ``pin_to_version: bool = True`` -> False."""
        rec = _Recorder({})
        monkeypatch.setattr(_branch, "branch_from_run", rec)
        memory.fork(
            client=object(),  # type: ignore[arg-type]
            session_factory=object(),  # type: ignore[arg-type]
            agent_id="agent-z",
            from_run_id=RunId("run-3"),
            unreachable_msg="x",
        )
        assert rec.kwargs is not None
        assert rec.kwargs["pin_to_version"] is True


class TestReplayForwarding:
    """:func:`memory.replay` forwards client/engine/unreachable_msg."""

    def test_replay_forwards_all_kwargs(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Kills client=None, engine=None, unreachable_msg=None."""
        sentinel = object()
        rec = _Recorder(sentinel)
        monkeypatch.setattr(_replay, "replay_run_on_branch", rec)

        client = object()
        engine = object()
        factory = object()
        out = memory.replay(
            client=client,  # type: ignore[arg-type]
            engine=engine,  # type: ignore[arg-type]
            session_factory=factory,  # type: ignore[arg-type]
            branch_schema_fqn="c.s_branch",
            source_run_id=RunId("run-9"),
            policy=ReplayPolicy.STRICT,
            unreachable_msg="catalog unreachable",
        )
        assert out is sentinel
        assert rec.kwargs is not None
        assert rec.kwargs["client"] is client
        assert rec.kwargs["engine"] is engine
        assert rec.kwargs["session_factory"] is factory
        assert rec.kwargs["branch_schema_fqn"] == "c.s_branch"
        assert rec.kwargs["source_run_id"] == "run-9"
        assert rec.kwargs["policy"] is ReplayPolicy.STRICT
        assert rec.kwargs["unreachable_msg"] == "catalog unreachable"
