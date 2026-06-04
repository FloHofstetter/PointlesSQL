"""Behaviour tests that pin down the ``pql.facts`` facade semantics.

These complement ``test_notebook_facts.py`` by asserting the exact
wiring the facade performs on top of the service layer:

* ``_resolve_run_id`` env-bridge resolution + the precise error text,
* the agent path (env-bridge → workspace + agent_id resolution →
  ``pin_revision_fact`` → a parallel ``pin_fact`` operation row),
* explicit-kwarg passthrough of the optional pin fields, and
* ``list_facts_for_notebook`` defaults + filter passthrough.
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
from pointlessql.models import AgentRun, AgentRunOperation, Base, Notebook
from pointlessql.pql import facts as facts_facade
from pointlessql.pql.facts import _resolve_run_id
from pointlessql.services.notebook import facts as facts_service
from pointlessql.services.notebook import revisions as revisions_service


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


def _seed_notebook_and_revision(
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    workspace_id: int = 1,
) -> tuple[str, str]:
    """Insert one notebook + one revision; return ``(nb_id, rev_uuid)``."""
    nb_id = str(uuid.uuid4())
    with factory() as s:
        # Unique file_path per notebook — the table has a UNIQUE
        # (workspace_id, file_path) constraint, so two seeds in one
        # workspace must not collide.
        s.add(Notebook(id=nb_id, workspace_id=workspace_id, file_path=f"{nb_id}.py"))
        rev = revisions_service.create_revision(
            s,
            notebook_id=nb_id,
            cells=[{"content_hash": "h1", "cell_type": "code", "source": "x"}],
            outputs=[],
            created_by="u@test",
        )
        s.commit()
        return nb_id, rev.revision_uuid


def _seed_agent_run(
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    run_id: str,
    workspace_id: int,
    agent_id: str | None,
) -> None:
    """Register one :class:`AgentRun` so the agent path can resolve it."""
    with factory() as s:
        s.add(
            AgentRun(
                id=run_id,
                principal=None,
                agent_id=agent_id,
                notebook_path="demo/x.py",
                status="running",
                workspace_id=workspace_id,
                started_at=datetime.datetime.now(datetime.UTC),
            )
        )
        s.commit()


# -- _resolve_run_id ----------------------------------------------------------


def test_resolve_run_id_prefers_explicit_kwarg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit ``agent_run_id`` wins over the env var entirely."""
    monkeypatch.setenv("POINTLESSQL_AGENT_RUN_ID", "from-env")
    assert _resolve_run_id("from-kwarg") == "from-kwarg"


def test_resolve_run_id_reads_the_exact_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no kwarg, the value comes from POINTLESSQL_AGENT_RUN_ID.

    Kills the mutants that blank the lookup (``env = None``) or read a
    different / case-folded variable name: those all fall through to
    the ValidationError instead of returning the env value.
    """
    monkeypatch.setenv("POINTLESSQL_AGENT_RUN_ID", "run-xyz")
    # Make sure no case-folded sibling is what is actually being read.
    monkeypatch.delenv("pointlessql_agent_run_id", raising=False)
    assert _resolve_run_id(None) == "run-xyz"
    assert _resolve_run_id("") == "run-xyz"  # empty kwarg is falsy → env


def test_resolve_run_id_raises_with_exact_message_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No kwarg and no env var raises ValidationError with the precise text.

    Asserting the full message text kills the string-content mutants on
    the error literal (case-folding / XX-wrapping / None-ing the arg).
    """
    monkeypatch.delenv("POINTLESSQL_AGENT_RUN_ID", raising=False)
    with pytest.raises(ValidationError) as exc:
        _resolve_run_id(None)
    assert str(exc.value) == (
        "pql.facts.pin requires agent_run_id (kwarg or "
        "POINTLESSQL_AGENT_RUN_ID environment variable)"
    )


def test_resolve_run_id_empty_env_is_treated_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty-string env value is falsy and must raise, not be returned."""
    monkeypatch.setenv("POINTLESSQL_AGENT_RUN_ID", "")
    with pytest.raises(ValidationError):
        _resolve_run_id(None)


# -- pin: explicit-kwarg passthrough ------------------------------------------


def test_pin_explicit_kwargs_passes_through_all_optional_fields(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Every optional pin field reaches the persisted row verbatim.

    Pins a cell-output fact with a description + snapshot and reads the
    row back, so dropping/Noning any of ``description_md`` /
    ``cell_content_hash`` / ``result_snapshot_json`` is observable.
    """
    _, rev_uuid = _seed_notebook_and_revision(factory)
    row = facts_facade.pin(
        rev_uuid,
        title="kwargs fact",
        description_md="# why this matters",
        cell_content_hash="h1",
        result_snapshot_json='{"columns": ["x"], "rows": [[1]]}',
        session_factory=factory,
        workspace_id=1,
        pinned_by_user_id=7,
    )
    assert row.description_md == "# why this matters"
    assert row.cell_content_hash == "h1"
    assert row.result_snapshot_json == '{"columns": ["x"], "rows": [[1]]}'
    assert row.pinned_by_user_id == 7
    assert row.pinned_by_agent_id is None

    # Confirm it actually persisted (the row is usable post-session).
    with factory() as session:
        detail = facts_service.get_fact_detail(session, fact_uuid=row.fact_uuid)
    assert detail is not None
    assert detail["cell_content_hash"] == "h1"
    assert detail["description_md"] == "# why this matters"
    assert detail["result_snapshot_json"] == '{"columns": ["x"], "rows": [[1]]}'


def test_pin_no_workspace_no_agent_reraises_run_id_error(
    factory: sessionmaker,  # type: ignore[type-arg]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No workspace + no agent context re-raises the run-id ValidationError.

    With ``workspace_id`` unset the facade enters the agent branch,
    ``_resolve_run_id`` raises (no kwarg, no env), and the inner guard
    (``workspace_id is None``) re-raises that error — so the message the
    caller sees is the run-id one, not the workspace-guard one.
    """
    monkeypatch.delenv("POINTLESSQL_AGENT_RUN_ID", raising=False)
    _, rev_uuid = _seed_notebook_and_revision(factory)
    with pytest.raises(ValidationError) as exc:
        facts_facade.pin(
            rev_uuid,
            title="x",
            session_factory=factory,
            workspace_id=None,
            pinned_by_user_id=5,
        )
    assert str(exc.value) == (
        "pql.facts.pin requires agent_run_id (kwarg or "
        "POINTLESSQL_AGENT_RUN_ID environment variable)"
    )


# -- pin: full agent path (env-bridge → workspace + agent_id → op row) --------


def test_pin_agent_path_resolves_workspace_and_records_op(
    factory: sessionmaker,  # type: ignore[type-arg]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The agent env-bridge resolves workspace + agent_id and logs an op.

    This drives the whole agent branch:

    * ``POINTLESSQL_AGENT_RUN_ID`` resolves to the registered run,
    * the run's ``workspace_id`` (2) becomes the pin's workspace,
    * the run's ``agent_id`` is stamped as ``pinned_by_agent_id``,
    * a parallel ``pin_fact`` operation row is recorded carrying the
      exact ``params`` dict (revision_uuid / cell_content_hash /
      fact_uuid / title) the facade builds.
    """
    run_id = "11111111-2222-3333-4444-555555555555"
    _, rev_uuid = _seed_notebook_and_revision(factory, workspace_id=2)
    _seed_agent_run(factory, run_id=run_id, workspace_id=2, agent_id="hermes-7")
    monkeypatch.setenv("POINTLESSQL_AGENT_RUN_ID", run_id)

    row = facts_facade.pin(
        rev_uuid,
        title="agent fact",
        cell_content_hash="h1",
        session_factory=factory,
        # No workspace_id, no user id → agent path is taken.
    )

    # Workspace came from the run (2), not a silent default of 1.
    assert row.workspace_id == 2
    # agent_id was stamped from AgentRun.agent_id.
    assert row.pinned_by_agent_id == "hermes-7"
    assert row.pinned_by_user_id is None

    # A pin_fact operation row was recorded against the run with the
    # full params payload.
    with factory() as session:
        op = session.scalar(
            select(AgentRunOperation).where(AgentRunOperation.agent_run_id == run_id)
        )
    assert op is not None
    assert op.op_name == "pin_fact"
    params = json.loads(op.params_json)
    assert params == {
        "revision_uuid": rev_uuid,
        "cell_content_hash": "h1",
        "fact_uuid": row.fact_uuid,
        "title": "agent fact",
    }
    assert op.target_table is None
    assert op.finished_at is not None


def test_pin_agent_path_with_explicit_workspace_keeps_kwarg_not_run(
    factory: sessionmaker,  # type: ignore[type-arg]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit ``workspace_id`` is NOT overwritten by the run's ws.

    The run lives in workspace 2 but the caller pins into workspace 3
    (where the revision also lives).  The guard ``if workspace_id is
    None`` must leave the explicit 3 in place; an agent_id is still
    stamped from the run, and the op is still recorded.
    """
    run_id = "99999999-8888-7777-6666-555555555555"
    _, rev_uuid = _seed_notebook_and_revision(factory, workspace_id=3)
    _seed_agent_run(factory, run_id=run_id, workspace_id=2, agent_id="hermes-9")
    monkeypatch.setenv("POINTLESSQL_AGENT_RUN_ID", run_id)

    row = facts_facade.pin(
        rev_uuid,
        title="explicit ws under agent",
        session_factory=factory,
        workspace_id=3,
        # pinned_by_user_id left unset → agent path still entered
        # because the OR condition is true (user id is None).
    )
    assert row.workspace_id == 3  # kept the kwarg, not the run's 2
    assert row.pinned_by_agent_id == "hermes-9"  # still stamped from run

    with factory() as session:
        op = session.scalar(
            select(AgentRunOperation).where(AgentRunOperation.agent_run_id == run_id)
        )
    assert op is not None
    assert op.op_name == "pin_fact"


def test_pin_workspace_set_user_none_env_unset_reraises_run_id_error(
    factory: sessionmaker,  # type: ignore[type-arg]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ws set, user unset, env unset → the run-id resolver error wins.

    The outer branch is entered (user is None), ``_resolve_run_id``
    raises (no kwarg, no env), and the inner guard re-raises that error
    because ``pinned_by_user_id is None``.  A mutant that flips the inner
    guard would instead fall through and either pin without attribution
    (service raises a *different* message) — so asserting the exact
    re-raised text pins the branch down.
    """
    monkeypatch.delenv("POINTLESSQL_AGENT_RUN_ID", raising=False)
    _, rev_uuid = _seed_notebook_and_revision(factory, workspace_id=5)
    with pytest.raises(ValidationError) as exc:
        facts_facade.pin(
            rev_uuid,
            title="x",
            session_factory=factory,
            workspace_id=5,
            pinned_by_user_id=None,
        )
    assert str(exc.value) == (
        "pql.facts.pin requires agent_run_id (kwarg or "
        "POINTLESSQL_AGENT_RUN_ID environment variable)"
    )


def test_pin_uses_explicit_agent_run_id_kwarg_over_env(
    factory: sessionmaker,  # type: ignore[type-arg]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit ``agent_run_id`` kwarg drives resolution (no env needed).

    The kwarg is threaded into ``_resolve_run_id`` and must be honoured;
    a mutant that ignores it (resolving ``None`` instead) would fall back
    to the unset env var and raise.
    """
    monkeypatch.delenv("POINTLESSQL_AGENT_RUN_ID", raising=False)
    run_id = "abababab-cdcd-efef-0101-232345456767"
    _, rev_uuid = _seed_notebook_and_revision(factory, workspace_id=4)
    _seed_agent_run(factory, run_id=run_id, workspace_id=4, agent_id="hermes-kw")
    row = facts_facade.pin(
        rev_uuid,
        title="kwarg run",
        session_factory=factory,
        agent_run_id=run_id,
    )
    assert row.workspace_id == 4
    assert row.pinned_by_agent_id == "hermes-kw"
    with factory() as session:
        op = session.scalar(
            select(AgentRunOperation).where(AgentRunOperation.agent_run_id == run_id)
        )
    assert op is not None
    assert op.op_name == "pin_fact"


def test_pin_unknown_agent_run_raises(
    factory: sessionmaker,  # type: ignore[type-arg]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An env-bridge run id that is not registered raises ValidationError."""
    _, rev_uuid = _seed_notebook_and_revision(factory, workspace_id=1)
    monkeypatch.setenv("POINTLESSQL_AGENT_RUN_ID", "deadbeef-0000-0000-0000-000000000000")
    with pytest.raises(ValidationError):
        facts_facade.pin(rev_uuid, title="x", session_factory=factory)


def test_pin_explicit_kwargs_record_no_operation(
    factory: sessionmaker,  # type: ignore[type-arg]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The human/library path (both kwargs set) records no op row.

    With ``workspace_id`` AND ``pinned_by_user_id`` both set, the agent
    branch is skipped entirely, ``resolved_run_id`` stays None and no
    operation is recorded even if an env var is present.
    """
    monkeypatch.setenv("POINTLESSQL_AGENT_RUN_ID", "should-be-ignored")
    _, rev_uuid = _seed_notebook_and_revision(factory)
    facts_facade.pin(
        rev_uuid,
        title="library fact",
        session_factory=factory,
        workspace_id=1,
        pinned_by_user_id=11,
    )
    with factory() as session:
        ops = session.scalars(select(AgentRunOperation)).all()
    assert ops == []


# -- list_facts_for_notebook --------------------------------------------------


def test_list_facts_for_notebook_defaults_hide_unpinned(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """By default an unpinned fact is hidden; include_unpinned surfaces it.

    Kills the default-flip on ``include_unpinned`` and its passthrough:
    if the default were True (or the value dropped), the unpinned row
    would leak into the default listing.
    """
    _, rev_uuid = _seed_notebook_and_revision(factory)
    with factory() as session:
        active = facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rev_uuid,
            title="active",
            pinned_by_user_id=1,
        )
        session.commit()
        gone = facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rev_uuid,
            title="gone",
            cell_content_hash="h1",
            pinned_by_user_id=1,
        )
        session.commit()
        facts_service.unpin_fact(session, fact_uuid=gone.fact_uuid)
        session.commit()
        active_uuid = active.fact_uuid
        gone_uuid = gone.fact_uuid

    default_list = facts_facade.list_facts_for_notebook(workspace_id=1, session_factory=factory)
    default_uuids = {e["fact_uuid"] for e in default_list}
    assert active_uuid in default_uuids
    assert gone_uuid not in default_uuids

    incl = facts_facade.list_facts_for_notebook(
        workspace_id=1, include_unpinned=True, session_factory=factory
    )
    incl_uuids = {e["fact_uuid"] for e in incl}
    assert {active_uuid, gone_uuid} <= incl_uuids


def test_list_facts_for_notebook_filters_by_notebook_id(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """``notebook_id`` restricts results to that notebook's facts.

    Two notebooks each hold one fact; filtering by one notebook id must
    return only its fact.  Dropping / None-ing the notebook_id passthrough
    would leak the other notebook's fact.
    """
    nb_a, rev_a = _seed_notebook_and_revision(factory)
    nb_b, rev_b = _seed_notebook_and_revision(factory)
    with factory() as session:
        fact_a = facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rev_a,
            title="A",
            pinned_by_user_id=1,
        )
        fact_b = facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rev_b,
            title="B",
            pinned_by_user_id=1,
        )
        session.commit()
        uuid_a, uuid_b = fact_a.fact_uuid, fact_b.fact_uuid

    only_a = facts_facade.list_facts_for_notebook(
        workspace_id=1, notebook_id=nb_a, session_factory=factory
    )
    a_uuids = {e["fact_uuid"] for e in only_a}
    assert a_uuids == {uuid_a}
    assert uuid_b not in a_uuids

    # No notebook filter → both show up.
    both = facts_facade.list_facts_for_notebook(workspace_id=1, session_factory=factory)
    assert {uuid_a, uuid_b} <= {e["fact_uuid"] for e in both}
    assert nb_b  # silence unused-var lint; nb_b proven distinct via uuid_b


def test_list_facts_for_notebook_respects_limit(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """A ``limit`` smaller than the row count caps the result length."""
    _, rev_uuid = _seed_notebook_and_revision(factory)
    with factory() as session:
        for i in range(3):
            facts_service.pin_revision_fact(
                session,
                workspace_id=1,
                revision_uuid=rev_uuid,
                title=f"f{i}",
                cell_content_hash=f"h{i}",
                pinned_by_user_id=1,
            )
        session.commit()

    capped = facts_facade.list_facts_for_notebook(workspace_id=1, limit=2, session_factory=factory)
    assert len(capped) == 2
    full = facts_facade.list_facts_for_notebook(workspace_id=1, session_factory=factory)
    assert len(full) == 3
