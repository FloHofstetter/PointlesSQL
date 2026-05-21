"""Public ``pql.facts`` facade — pin notebook revisions as facts.

A *fact* is a long-lived bookmark on a :class:`NotebookRevision` that
adds a human-readable shape (``title`` + ``description_md``) on top of
the deterministic content hash already on the revision row.  Agents
running through the kernel call into this facade so the action lands
on the workspace's library *and* in the agent's operation timeline:

    from pointlessql.pql import facts

    facts.pin(
        revision_uuid="…",
        title="Q3 EU sales spike, Aug 12",
        description_md="See run-12345 for the rationale.",
    )

The agent uses the env-bridge form — no session_factory / workspace_id
arguments — because the call site sits inside an agent run with
``POINTLESSQL_AGENT_RUN_ID`` set; the facade resolves the owning
workspace from :class:`AgentRun.workspace_id` and stamps
``pinned_by_agent_id`` from :class:`AgentRun.agent_id`.  Unit tests +
non-agent library callers pass the kwargs explicitly.

Every pin records a parallel :data:`OpName.PIN_FACT` operation on
``agent_run_operations`` so the run's reflexive memory shows the
action alongside reads / writes / SQL.  Re-pinning the same
``(workspace, revision, cell_content_hash)`` is idempotent — the
service returns the existing active row and the recorder still emits
the (no-op) operation row so the audit trail captures the intent.
"""

from __future__ import annotations

import datetime
import os
from typing import TYPE_CHECKING

from pointlessql.exceptions import ValidationError
from pointlessql.services.notebook import facts as facts_service
from pointlessql.types import OpName, RunId

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

    from pointlessql.models.notebook import NotebookRevisionFact


def _resolve_run_id(agent_run_id: str | None) -> str:
    """Pick the agent run UUID from kwarg or the kernel env-bridge."""
    if agent_run_id:
        return agent_run_id
    env = os.environ.get("POINTLESSQL_AGENT_RUN_ID")
    if not env:
        raise ValidationError(
            "pql.facts.pin requires agent_run_id (kwarg or "
            "POINTLESSQL_AGENT_RUN_ID environment variable)"
        )
    return env


def _resolve_session_factory(
    session_factory: sessionmaker[Session] | None,
) -> sessionmaker[Session]:
    """Pick the session factory from kwarg or the lazy db init."""
    if session_factory is not None:
        return session_factory
    # Subprocess-spawned agent notebooks bypass the FastAPI lifespan,
    # so :func:`get_session_factory` may raise.  ``PQL.__init__`` does
    # the lazy bootstrap already, so by the time the agent reaches
    # ``pql.facts.pin`` the factory is available — we just look it up.
    from pointlessql.db import get_session_factory

    return get_session_factory()


def _agent_context(
    session_factory: sessionmaker[Session], agent_run_id: str
) -> tuple[int, str | None]:
    """Resolve ``(workspace_id, agent_id)`` for *agent_run_id*.

    Args:
        session_factory: SQLAlchemy session factory.
        agent_run_id: Active :class:`AgentRun` UUID.

    Returns:
        Pair of ``(workspace_id, agent_id)``.  ``agent_id`` may be
        ``None`` when the run was registered without one.

    Raises:
        ValidationError: When the run is unknown — the facade should
            never silently fall back to a default workspace.
    """
    from pointlessql.models import AgentRun

    with session_factory() as session:
        run = session.get(AgentRun, agent_run_id)
        if run is None:
            raise ValidationError(
                f"pql.facts: agent_run {agent_run_id!r} is not registered"
            )
        return int(run.workspace_id), run.agent_id


def pin(
    revision_uuid: str,
    *,
    title: str,
    description_md: str | None = None,
    cell_content_hash: str | None = None,
    result_snapshot_json: str | None = None,
    # Test / library overrides.  Agent callers leave these empty.
    session_factory: sessionmaker[Session] | None = None,
    workspace_id: int | None = None,
    agent_run_id: str | None = None,
    pinned_by_user_id: int | None = None,
) -> NotebookRevisionFact:
    """Promote a revision (or one of its cell outputs) into a fact.

    Agent path: resolve session-factory + workspace + agent_id from
    the env-bridge; record the action under :data:`OpName.PIN_FACT`
    on the active agent run.

    Library / test path: pass *session_factory* + *workspace_id*
    explicitly; *agent_run_id* is optional (skip the operation
    recorder when unset and *pinned_by_user_id* is set instead).

    Args:
        revision_uuid: 36-char :class:`NotebookRevision` UUID.
        title: Human-readable label (≤ 200 chars).
        description_md: Optional Markdown rendered on the library
            detail page.
        cell_content_hash: When set, pins one specific cell's output.
        result_snapshot_json: Optional frozen JSON snapshot of the
            cell's last-known output frame.
        session_factory: Optional override (tests / non-agent).
        workspace_id: Optional override (tests / non-agent).
        agent_run_id: Optional override; agent-runtime callers leave
            this empty and the facade reads
            ``POINTLESSQL_AGENT_RUN_ID``.
        pinned_by_user_id: Used iff the call is on behalf of a human
            (e.g. unit tests).  Mutually exclusive with the agent
            path for attribution purposes — the service requires at
            least one of (agent_id, user_id).

    Returns:
        The persisted (or pre-existing active)
        :class:`NotebookRevisionFact`.

    Raises:
        ValidationError: On bad shape, unknown revision, missing
            attribution, or missing agent context when the env-bridge
            is the only resolver.
    """
    factory = _resolve_session_factory(session_factory)
    pinned_by_agent_id: str | None = None
    resolved_run_id: str | None = None
    if workspace_id is None or pinned_by_user_id is None:
        # Agent path — at least one of (workspace_id, user_id) was
        # unset, so we resolve via the active agent run.
        try:
            resolved_run_id = _resolve_run_id(agent_run_id)
        except ValidationError:
            # Non-agent path with explicit kwargs is still legal;
            # rethrow only when there is no human attribution either.
            if workspace_id is None or pinned_by_user_id is None:
                raise
            resolved_run_id = None
        if resolved_run_id is not None:
            resolved_ws, pinned_by_agent_id = _agent_context(
                factory, resolved_run_id
            )
            if workspace_id is None:
                workspace_id = resolved_ws
    if workspace_id is None:
        raise ValidationError(
            "pql.facts.pin requires workspace_id (kwarg) when no agent "
            "context is available"
        )

    with factory() as session:
        row = facts_service.pin_revision_fact(
            session,
            workspace_id=workspace_id,
            revision_uuid=revision_uuid,
            title=title,
            description_md=description_md,
            cell_content_hash=cell_content_hash,
            result_snapshot_json=result_snapshot_json,
            pinned_by_user_id=pinned_by_user_id,
            pinned_by_agent_id=pinned_by_agent_id,
        )
        session.commit()
        # Detach so the row is usable after the session closes.
        session.refresh(row)
        session.expunge(row)

    if resolved_run_id is not None:
        # Best-effort audit trail.  Failing to record the op row must
        # not undo the pin (which already committed); the memory
        # facade will raise on a missing run / bad op_name and we
        # surface that to the caller as a hint.
        from pointlessql.pql import memory as memory_facade

        memory_facade.record(
            session_factory=factory,
            agent_run_id=RunId(resolved_run_id),
            op_name=OpName.PIN_FACT,
            params={
                "revision_uuid": revision_uuid,
                "cell_content_hash": cell_content_hash,
                "fact_uuid": row.fact_uuid,
                "title": title,
            },
            target_table=None,
            finished_at=datetime.datetime.now(datetime.UTC),
        )
    return row


def unpin(
    fact_uuid: str,
    *,
    session_factory: sessionmaker[Session] | None = None,
) -> None:
    """Soft-delete a fact by stamping ``unpinned_at``.

    Args:
        fact_uuid: 36-char fact UUID.
        session_factory: Optional override.  Agent callers leave empty.

    Raises:
        ValidationError: When the UUID is unknown or already unpinned.
    """  # noqa: DOC502 — delegate raises
    factory = _resolve_session_factory(session_factory)
    with factory() as session:
        facts_service.unpin_fact(session, fact_uuid=fact_uuid)
        session.commit()


def list_facts_for_notebook(
    *,
    workspace_id: int,
    notebook_id: str | None = None,
    include_unpinned: bool = False,
    limit: int = 50,
    session_factory: sessionmaker[Session] | None = None,
) -> list[dict[str, object]]:
    """List facts in a workspace as plain envelopes.

    Returns dicts (not ORM rows) so the caller can iterate after the
    session closes without DetachedInstanceError surprises.
    """
    factory = _resolve_session_factory(session_factory)
    with factory() as session:
        rows = facts_service.list_facts(
            session,
            workspace_id=workspace_id,
            notebook_id=notebook_id,
            include_unpinned=include_unpinned,
            limit=limit,
        )
        return [facts_service.row_to_envelope(r) for r in rows]


__all__ = ["list_facts_for_notebook", "pin", "unpin"]
