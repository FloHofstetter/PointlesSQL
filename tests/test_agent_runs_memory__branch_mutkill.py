"""Mutation-killing tests for ``services.agent_runs.memory._branch``.

These pin the observable behaviour of the branch-from-run helper:
the source-schema/version derivation query (filter + ordering),
the auto-generated branch name (hyphen-stripping, char sanitising),
the kwargs forwarded into ``create_branch_schema``, the returned
dict keys, and the audit-payload stamp (intent / pinned version /
stamped_at / sort-keys / which row gets stamped).

The real ``create_branch_schema`` does heavy IO, so it is stubbed;
the stub records its call kwargs and optionally seeds an audit row.
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
    """In-memory SQLite with the full ORM schema."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _add_run(
    s,  # type: ignore[no-untyped-def]
    *,
    run_id: str,
    agent_id: str = "agent-alpha",
    notebook_path: str = "branch_test.py",
) -> None:
    """Insert one AgentRun row in the open session."""
    s.add(
        AgentRun(
            id=run_id,
            principal="test@example.com",
            agent_id=agent_id,
            notebook_path=notebook_path,
            status="running",
            started_at=datetime.datetime.now(datetime.UTC),
        )
    )


def _add_op(
    s,  # type: ignore[no-untyped-def]
    *,
    run_id: str,
    ordinal: int,
    target_table: str | None,
    delta_version_before: int | None = 7,
    op_name: str = "write_table",
) -> None:
    """Insert one AgentRunOperation row in the open session."""
    s.add(
        AgentRunOperation(
            agent_run_id=run_id,
            ordinal=ordinal,
            op_name=op_name,
            params_json="{}",
            target_table=target_table,
            delta_version_before=delta_version_before,
            started_at=datetime.datetime.now(datetime.UTC),
        )
    )


def _seed_run_with_write_op(
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    agent_id: str = "agent-alpha",
    target_table: str = "main.bronze.orders",
    delta_version_before: int | None = 7,
) -> RunId:
    """Insert an AgentRun + a single write op the helper can branch from."""
    run_id = str(uuid.uuid4())
    with factory() as s:
        _add_run(s, run_id=run_id, agent_id=agent_id)
        s.flush()
        _add_op(
            s,
            run_id=run_id,
            ordinal=1,
            target_table=target_table,
            delta_version_before=delta_version_before,
        )
        s.commit()
    return RunId(run_id)


def _seed_read_only_run(
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    agent_id: str = "agent-alpha",
) -> RunId:
    """Insert an AgentRun + a single read-only op (no target_table)."""
    run_id = str(uuid.uuid4())
    with factory() as s:
        _add_run(s, run_id=run_id, agent_id=agent_id, notebook_path="readonly.py")
        s.flush()
        _add_op(s, run_id=run_id, ordinal=1, target_table=None, op_name="sql")
        s.commit()
    return RunId(run_id)


def _patch_create_branch_schema(
    monkeypatch: pytest.MonkeyPatch,
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    return_fqn: str = "main.mem_agent_alpha_abcdef12",
    seed_audit_row: bool = True,
    seed_payload: dict[str, object] | str | None = None,
) -> list[dict[str, object]]:
    """Stub ``create_branch_schema`` to record calls + seed an audit row.

    Records the full forwarded kwargs (client/settings included) so
    tests can pin which arguments the helper passes through, and
    optionally lands a :class:`BranchAuditLog` row whose payload the
    post-call stamp will update.

    Returns:
        A list the stub appends each call's kwargs into.
    """
    calls: list[dict[str, object]] = []

    if seed_payload is None:
        payload_text: str | None = json.dumps({"strategy": "symlink", "table_count": 1})
    elif isinstance(seed_payload, str):
        payload_text = seed_payload
    else:
        payload_text = json.dumps(seed_payload)

    def fake_create(*, client, source_schema_fqn, branch_name, settings, agent_run_id=None, **_):
        calls.append(
            {
                "client": client,
                "settings": settings,
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
                        payload_json=payload_text,
                        created_at=datetime.datetime.now(datetime.UTC),
                    )
                )
                s.commit()
        return return_fqn

    monkeypatch.setattr(branch_service, "create_branch_schema", fake_create)
    return calls


def _latest_payload(factory: sessionmaker) -> dict[str, object]:  # type: ignore[type-arg]
    """Return the parsed payload of the single seeded audit row."""
    with factory() as s:
        row = s.scalars(select(BranchAuditLog)).first()
        assert row is not None
        assert row.payload_json is not None
        return json.loads(row.payload_json)


class TestDeriveBranchName:
    """``_derive_branch_name`` hyphen-stripping and char sanitising."""

    def test_hyphens_are_stripped_from_run_short(self) -> None:
        # A run id whose first 8 chars include hyphens distinguishes
        # replace("-", "") from a no-op / replace-with-XXXX mutant.
        name = branch_service._derive_branch_name("ag", RunId("12-34-56-78-90abcdef"))
        # "1234567890abcdef"[:8] == "12345678" after hyphens removed.
        assert name == "mem_ag_12345678"

    def test_strip_only_removes_underscores_not_x(self) -> None:
        # strip("_") must keep leading/trailing 'X'; strip("XX_XX")
        # would eat them.
        name = branch_service._derive_branch_name("XagentX", RunId("abcdef12-0000-0000"))
        assert name == "mem_XagentX_abcdef12"

    def test_name_sanitises_special_chars(self) -> None:
        name = branch_service._derive_branch_name(
            "agent/with spaces!", RunId("abcdef12-3456-7890-abcd-ef1234567890")
        )
        assert all(c.isalnum() or c == "_" for c in name)
        assert name.startswith("mem_agent_with_spaces_")
        assert name.endswith("abcdef12")

    def test_name_falls_back_to_agent_when_all_special(self) -> None:
        name = branch_service._derive_branch_name(
            "///", RunId("abcdef12-3456-7890-abcd-ef1234567890")
        )
        assert name == "mem_agent_abcdef12"


class TestFirstWriteOpQuery:
    """``_first_write_op`` filter + ordering + error message."""

    def test_picks_lowest_ordinal_op_not_insertion_order(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Insert the higher ordinal FIRST so an order_by(None) mutant
        # (insertion order) would pick the wrong op.
        run_id = str(uuid.uuid4())
        with factory() as s:
            _add_run(s, run_id=run_id)
            s.flush()
            _add_op(
                s,
                run_id=run_id,
                ordinal=2,
                target_table="main.silver.late",
                delta_version_before=99,
            )
            _add_op(
                s,
                run_id=run_id,
                ordinal=1,
                target_table="main.bronze.early",
                delta_version_before=7,
            )
            s.commit()

        calls = _patch_create_branch_schema(monkeypatch, factory)
        result = memory.branch(
            client=object(),
            session_factory=factory,
            agent_id="agent-alpha",
            from_run_id=RunId(run_id),
            unreachable_msg="x",
        )
        # Ordinal 1 (inserted second) must win.
        assert calls[0]["source_schema_fqn"] == "main.bronze"
        assert result["parent_schema_fqn"] == "main.bronze"
        assert result["pinned_delta_version"] == 7

    def test_filters_by_run_id(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # A different run's op is inserted first with a lower ordinal;
        # without the agent_run_id filter the query would pick it.
        other_run = str(uuid.uuid4())
        target_run = str(uuid.uuid4())
        with factory() as s:
            _add_run(s, run_id=other_run, agent_id="other")
            _add_run(s, run_id=target_run, agent_id="agent-alpha")
            s.flush()
            _add_op(
                s,
                run_id=other_run,
                ordinal=0,
                target_table="main.foreign.tbl",
                delta_version_before=1,
            )
            _add_op(
                s,
                run_id=target_run,
                ordinal=5,
                target_table="main.bronze.orders",
                delta_version_before=7,
            )
            s.commit()

        calls = _patch_create_branch_schema(monkeypatch, factory)
        result = memory.branch(
            client=object(),
            session_factory=factory,
            agent_id="agent-alpha",
            from_run_id=RunId(target_run),
            unreachable_msg="x",
        )
        assert calls[0]["source_schema_fqn"] == "main.bronze"
        assert result["pinned_delta_version"] == 7

    def test_read_only_run_error_message(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_read_only_run(factory)
        with pytest.raises(ValidationError) as exc:
            memory.branch(
                client=object(),
                session_factory=factory,
                agent_id="agent-alpha",
                from_run_id=run_id,
                unreachable_msg="x",
            )
        # Pin the full message, including the second concatenated clause.
        assert "cannot derive a source schema to branch from" in str(exc.value)


class TestForwardedKwargs:
    """``branch_from_run`` forwards the right kwargs to create_branch_schema."""

    def test_passes_real_client_and_settings(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        run_id = _seed_run_with_write_op(factory)
        calls = _patch_create_branch_schema(monkeypatch, factory)
        sentinel_client = object()

        memory.branch(
            client=sentinel_client,
            session_factory=factory,
            agent_id="agent-alpha",
            from_run_id=run_id,
            unreachable_msg="x",
        )
        assert calls[0]["client"] is sentinel_client
        # settings must be a real resolved Settings, never None.
        assert calls[0]["settings"] is not None

    def test_forwards_run_id_as_agent_run_id(
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
            unreachable_msg="x",
        )
        assert calls[0]["agent_run_id"] == str(run_id)
        assert calls[0]["agent_run_id"] not in (None, "None")

    def test_auto_name_uses_run_short_not_none(
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
            unreachable_msg="x",
        )
        name = str(calls[0]["branch_name"])
        short = str(run_id).replace("-", "")[:8]
        assert name == f"mem_agent_alpha_{short}"
        assert not name.endswith("None")


class TestResultDict:
    """The returned dict carries the exact contracted keys."""

    def test_result_has_branch_schema_fqn_key(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        run_id = _seed_run_with_write_op(factory)
        _patch_create_branch_schema(monkeypatch, factory, return_fqn="main.mem_branch_xyz")
        result = memory.branch(
            client=object(),
            session_factory=factory,
            agent_id="agent-alpha",
            from_run_id=run_id,
            unreachable_msg="x",
        )
        assert "branch_schema_fqn" in result
        assert result["branch_schema_fqn"] == "main.mem_branch_xyz"


class TestStampPayload:
    """``_stamp_intent_in_audit_payload`` payload-mutation coverage."""

    def test_preserves_existing_payload_keys(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # json.loads(None) mutant would drop the seeded keys.
        run_id = _seed_run_with_write_op(factory)
        _patch_create_branch_schema(
            monkeypatch,
            factory,
            seed_payload={"strategy": "symlink", "table_count": 3},
        )
        memory.branch(
            client=object(),
            session_factory=factory,
            agent_id="agent-alpha",
            from_run_id=run_id,
            unreachable_msg="x",
        )
        payload = _latest_payload(factory)
        assert payload["strategy"] == "symlink"
        assert payload["table_count"] == 3
        assert payload["intent"] == "create"

    def test_stamps_when_existing_payload_is_none(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # existing_payload defaults to {} so a None payload_json still
        # gets the stamp; the `= None` mutant would raise here.
        run_id = _seed_run_with_write_op(factory)
        _patch_create_branch_schema(monkeypatch, factory, seed_payload="")
        memory.branch(
            client=object(),
            session_factory=factory,
            agent_id="agent-alpha",
            from_run_id=run_id,
            unreachable_msg="x",
        )
        payload = _latest_payload(factory)
        assert payload["intent"] == "create"
        assert payload["pinned_delta_version"] == 7

    def test_stamps_when_existing_payload_is_malformed(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Invalid JSON falls into the except -> {} branch; the `= None`
        # mutant there would raise instead of stamping.
        run_id = _seed_run_with_write_op(factory)
        _patch_create_branch_schema(monkeypatch, factory, seed_payload="not-json{")
        memory.branch(
            client=object(),
            session_factory=factory,
            agent_id="agent-alpha",
            from_run_id=run_id,
            unreachable_msg="x",
        )
        payload = _latest_payload(factory)
        assert payload["intent"] == "create"

    def test_stamped_at_is_a_utc_aware_isoformat(
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
        payload = _latest_payload(factory)
        # Key spelling + non-None value + UTC offset (now(None) would be naive).
        assert "stamped_at" in payload
        stamped = payload["stamped_at"]
        assert isinstance(stamped, str)
        assert stamped.endswith("+00:00")

    def test_payload_json_is_sorted_by_key(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Seed a key that sorts after "intent" but is inserted first;
        # sort_keys=True/None|False is observable in the raw ordering.
        run_id = _seed_run_with_write_op(factory)
        _patch_create_branch_schema(monkeypatch, factory, seed_payload={"zzz": 1})
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
            raw = row.payload_json
        assert raw is not None
        # Alphabetical order => "intent" before "zzz".
        assert raw.index('"intent"') < raw.index('"zzz"')

    def test_stamps_most_recent_audit_row(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Two rows share the branch fqn; the OLDER one is inserted
        # first.  order_by(created_at desc) must stamp the NEWER row;
        # an order_by(None) mutant would stamp the inserted-first OLD row.
        return_fqn = "main.mem_dup_branch"
        run_id = _seed_run_with_write_op(factory)
        now = datetime.datetime.now(datetime.UTC)
        with factory() as s:
            s.add(
                BranchAuditLog(
                    branch_schema_fqn=return_fqn,
                    parent_schema_fqn="main.bronze",
                    action="create",
                    run_id=None,
                    payload_json=json.dumps({"marker": "OLD"}),
                    created_at=now - datetime.timedelta(hours=1),
                )
            )
            s.commit()

        def fake_create(
            *, client, source_schema_fqn, branch_name, settings, agent_run_id=None, **_
        ):
            with factory() as s:
                s.add(
                    BranchAuditLog(
                        branch_schema_fqn=return_fqn,
                        parent_schema_fqn=source_schema_fqn,
                        action="create",
                        run_id=agent_run_id,
                        payload_json=json.dumps({"marker": "NEW"}),
                        created_at=now,
                    )
                )
                s.commit()
            return return_fqn

        monkeypatch.setattr(branch_service, "create_branch_schema", fake_create)

        memory.branch(
            client=object(),
            session_factory=factory,
            agent_id="agent-alpha",
            from_run_id=run_id,
            unreachable_msg="x",
        )

        with factory() as s:
            rows = {
                json.loads(r.payload_json)["marker"]: json.loads(r.payload_json)
                for r in s.scalars(
                    select(BranchAuditLog).where(BranchAuditLog.branch_schema_fqn == return_fqn)
                )
            }
        # The NEW (most-recent) row got the intent stamp; OLD did not.
        assert "intent" in rows["NEW"]
        assert "intent" not in rows["OLD"]


class TestReadOnlyRunErrorMessageExact:
    """Pin the exact read-only error text, not just a substring.

    A bare ``substring in message`` check is satisfied even when the
    clause is wrapped (``XX...XX``), so this asserts the precise
    rendered suffix and the absence of any wrapping sentinel.
    """

    def test_error_message_has_no_wrapping_sentinel(
        self,
        factory: sessionmaker,  # type: ignore[type-arg]
    ) -> None:
        run_id = _seed_read_only_run(factory)
        with pytest.raises(ValidationError) as exc:
            memory.branch(
                client=object(),
                session_factory=factory,
                agent_id="agent-alpha",
                from_run_id=run_id,
                unreachable_msg="x",
            )
        message = str(exc.value)
        # The clause must appear verbatim with no surrounding wrapper.
        assert message.endswith("cannot derive a source schema to branch from")
        assert "XX" not in message

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
        payload = _latest_payload(factory)
        assert payload["intent"] == "fork"
