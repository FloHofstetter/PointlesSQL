"""unit tests for ``pql.memory.branch`` / ``fork``.

The real ``create_branch_schema`` needs a running soyuz-catalog +
deltalake on disk, so we monkeypatch it.  The contract we assert
here is the *facade-level* behaviour: source-run validation,
schema-fqn derivation, branch-name auto-generation, version-pin
stamp into the audit payload, ``intent`` differentiation between
``branch`` and ``fork``.
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
from pointlessql.models import AgentRun, AgentRunOperation, Base, BranchAuditLog
from pointlessql.pql import memory
from pointlessql.services.agent_runs.memory import _branch as branch_service
from pointlessql.types import RunId


@pytest.fixture
def factory() -> sessionmaker:  # type: ignore[type-arg]
    """In-memory SQLite with full ORM schema."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _seed_run_with_write_op(
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    agent_id: str = "agent-alpha",
    target_table: str = "main.bronze.orders",
    delta_version_before: int | None = 7,
) -> RunId:
    """Insert AgentRun + one write op so the branch helper can find a target."""
    run_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    with factory() as s:
        s.add(
            AgentRun(
                id=run_id,
                principal="test@example.com",
                agent_id=agent_id,
                notebook_path="branch_test.py",
                status="running",
                started_at=now,
            )
        )
        s.flush()
        s.add(
            AgentRunOperation(
                agent_run_id=run_id,
                ordinal=1,
                op_name="write_table",
                params_json="{}",
                target_table=target_table,
                delta_version_before=delta_version_before,
                started_at=now,
            )
        )
        s.commit()
    return RunId(run_id)


def _seed_read_only_run(
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    agent_id: str = "agent-alpha",
) -> RunId:
    """Insert AgentRun + one read-only op (no target_table)."""
    run_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    with factory() as s:
        s.add(
            AgentRun(
                id=run_id,
                principal="test@example.com",
                agent_id=agent_id,
                notebook_path="readonly.py",
                status="running",
                started_at=now,
            )
        )
        s.flush()
        s.add(
            AgentRunOperation(
                agent_run_id=run_id,
                ordinal=1,
                op_name="sql",
                params_json='{"query": "SELECT 1"}',
                target_table=None,
                started_at=now,
            )
        )
        s.commit()
    return RunId(run_id)


def _patch_create_branch_schema(
    monkeypatch: pytest.MonkeyPatch,
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    return_fqn: str = "main.mem_agent_alpha_abcdef12",
    seed_audit_row: bool = True,
) -> list[dict[str, object]]:
    """Stub :func:`create_branch_schema` to record calls + seed an audit row.

    The real function does heavy IO (soyuz HTTP, deltalake clone);
    we just record the call kwargs and optionally land a
    :class:`BranchAuditLog` row so the post-call payload stamp has
    something to update.

    Returns:
        A list the stub appends each call's kwargs into.
    """
    calls: list[dict[str, object]] = []

    def fake_create(*, client, source_schema_fqn, branch_name, settings, agent_run_id=None, **_):
        calls.append(
            {
                "source_schema_fqn": source_schema_fqn,
                "branch_name": branch_name,
                "agent_run_id": agent_run_id,
            }
        )
        if seed_audit_row:
            with factory() as s:
                s.add(
                    BranchAuditLog(
                        branch_schema_fqn=return_fqn,
                        parent_schema_fqn=source_schema_fqn,
                        action="create",
                        run_id=agent_run_id,
                        payload_json=json.dumps(
                            {"strategy": "symlink", "table_count": 1}
                        ),
                        created_at=datetime.datetime.now(datetime.UTC),
                    )
                )
                s.commit()
        return return_fqn

    monkeypatch.setattr(branch_service, "create_branch_schema", fake_create)
    return calls


class TestBranchHappyPath:
    """Happy-path coverage for ``pql.memory.branch``."""

    def test_branch_derives_schema_and_auto_name(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        run_id = _seed_run_with_write_op(factory, target_table="main.bronze.orders")
        calls = _patch_create_branch_schema(monkeypatch, factory)

        result = memory.branch(
            client=object(),  # unused by stub
            session_factory=factory,
            agent_id="agent-alpha",
            from_run_id=run_id,
            unreachable_msg="soyuz unreachable",
        )

        assert len(calls) == 1
        assert calls[0]["source_schema_fqn"] == "main.bronze"
        assert str(calls[0]["branch_name"]).startswith("mem_agent_alpha_")
        assert result["parent_schema_fqn"] == "main.bronze"
        assert result["pinned_delta_version"] == 7
        assert result["intent"] == "create"

    def test_branch_respects_explicit_branch_name(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        run_id = _seed_run_with_write_op(factory)
        calls = _patch_create_branch_schema(monkeypatch, factory)

        memory.branch(
            client=object(),
            session_factory=factory,
            agent_id="agent-alpha",
            from_run_id=run_id,
            branch_name="my_custom_branch",
            unreachable_msg="x",
        )
        assert calls[0]["branch_name"] == "my_custom_branch"

    def test_branch_pin_to_version_false_yields_none(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        run_id = _seed_run_with_write_op(factory)
        _patch_create_branch_schema(monkeypatch, factory)

        result = memory.branch(
            client=object(),
            session_factory=factory,
            agent_id="agent-alpha",
            from_run_id=run_id,
            pin_to_version=False,
            unreachable_msg="x",
        )
        assert result["pinned_delta_version"] is None

    def test_branch_stamps_intent_in_audit_payload(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        run_id = _seed_run_with_write_op(factory)
        _patch_create_branch_schema(monkeypatch, factory)

        memory.branch(
            client=object(),
            session_factory=factory,
            agent_id="agent-alpha",
            from_run_id=run_id,
            unreachable_msg="x",
        )

        with factory() as s:
            row = s.scalars(select(BranchAuditLog)).first()
            assert row is not None
            assert row.payload_json is not None
            payload = json.loads(row.payload_json)
            assert payload["intent"] == "create"
            assert payload["pinned_delta_version"] == 7
            assert payload["source_run_id"] == str(run_id)


class TestForkSemantics:
    """``pql.memory.fork`` differs from branch only in the ``intent`` stamp."""

    def test_fork_stamps_fork_intent(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        run_id = _seed_run_with_write_op(factory)
        _patch_create_branch_schema(monkeypatch, factory)

        result = memory.fork(
            client=object(),
            session_factory=factory,
            agent_id="agent-alpha",
            from_run_id=run_id,
            unreachable_msg="x",
        )
        assert result["intent"] == "fork"

        with factory() as s:
            row = s.scalars(select(BranchAuditLog)).first()
            assert row is not None
            payload = json.loads(row.payload_json or "{}")
            assert payload["intent"] == "fork"


class TestBranchValidation:
    """Error paths."""

    def test_unknown_run_raises(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        with pytest.raises(ValidationError, match="not registered"):
            memory.branch(
                client=object(),
                session_factory=factory,
                agent_id="agent-alpha",
                from_run_id=RunId("00000000-0000-0000-0000-000000000000"),
                unreachable_msg="x",
            )

    def test_agent_id_mismatch_raises(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_run_with_write_op(factory, agent_id="alpha")
        with pytest.raises(ValidationError, match="belongs to agent"):
            memory.branch(
                client=object(),
                session_factory=factory,
                agent_id="beta",
                from_run_id=run_id,
                unreachable_msg="x",
            )

    def test_read_only_run_raises(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_read_only_run(factory)
        with pytest.raises(ValidationError, match="no operations with a target_table"):
            memory.branch(
                client=object(),
                session_factory=factory,
                agent_id="agent-alpha",
                from_run_id=run_id,
                unreachable_msg="x",
            )

    def test_malformed_target_table_raises(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        # Seed with a 2-part target_table
        run_id = _seed_run_with_write_op(factory, target_table="schema.table")
        with pytest.raises(ValidationError, match="three-part target_table"):
            memory.branch(
                client=object(),
                session_factory=factory,
                agent_id="agent-alpha",
                from_run_id=run_id,
                unreachable_msg="x",
            )


class TestBranchNameSanitisation:
    """The auto-generated name is UC + filesystem safe."""

    def test_name_sanitises_special_chars(self) -> None:
        run_uuid = RunId("abcdef12-3456-7890-abcd-ef1234567890")
        name = branch_service._derive_branch_name("agent/with spaces!", run_uuid)
        # No special chars, only [a-zA-Z0-9_]
        assert all(c.isalnum() or c == "_" for c in name)
        assert name.startswith("mem_agent_with_spaces_")
        assert name.endswith("abcdef12")

    def test_name_falls_back_to_agent_when_all_special(self) -> None:
        run_uuid = RunId("abcdef12-3456-7890-abcd-ef1234567890")
        name = branch_service._derive_branch_name("///", run_uuid)
        # The "agent" fallback fires when every char gets stripped.
        assert name == "mem_agent_abcdef12"
