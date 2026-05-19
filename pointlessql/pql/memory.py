"""Public ``pql.memory`` facade — Delta-first agent memory primitive.

This module names the existing audit + branching infrastructure
(``agent_runs``, ``agent_run_operations``, ``branch_service``) as
**the agent's persistent memory** and gives it a five-function API
matching what Lakebase markets as "persistent memory for AI agents"
on its Postgres-OLTP backend.  The facade does not introduce new
tables or new business logic — every method delegates to an existing
service.  What is new is the ergonomic shape of the surface (one
verb per agent-memory operation, instead of five different service
imports per primitive).

Public methods:

* :func:`record` — append an operation to an agent's run timeline.
* :func:`recall` — query the operation log for an agent.
* :func:`branch` — create a Delta branch off the schema state at
  run start (with optional version-pinning via deltalake
  time-travel for deterministic replay).
* :func:`fork` — semantic alias of :func:`branch` that labels the
  resulting :class:`BranchAuditLog` row's ``action`` as
  ``"fork"`` rather than ``"create"``.
* :func:`replay` — re-invoke an agent run's operations onto a
  branch, skipping operations whose semantics make blind replay
  unsafe (DML, dbt nodes, training).

See ``docs/concepts/agent-memory.md`` for the conceptual model and
the Lakebase comparison.
"""

from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from pointlessql.services.agent_runs.memory._recall import recall_operations
from pointlessql.services.agent_runs.memory._replay_policy import (
    ReplayPolicy,
    ReplayResult,
)
from pointlessql.services.agent_runs.operations._lifecycle import record_operation
from pointlessql.types import OpId, OpName, RunId

if TYPE_CHECKING:
    from soyuz_catalog_client import Client
    from sqlalchemy.orm import Session, sessionmaker

    from pointlessql.models import AgentRunOperation
    from pointlessql.pql.engine import Engine


def record(
    *,
    session_factory: sessionmaker[Session],
    agent_run_id: RunId,
    op_name: OpName,
    params: Mapping[str, Any],
    target_table: str | None = None,
    started_at: datetime.datetime | None = None,
    finished_at: datetime.datetime | None = None,
    error_message: str | None = None,
    rows_affected: int | None = None,
) -> OpId:
    """Append one operation to an agent's run timeline.

    Pure pass-through to
    :func:`pointlessql.services.agent_runs.operations.record_operation`
    with the audit columns (``input_sha``, ``delta_version_*``,
    ``training_params_json``) left at ``None``.  This is the
    *interactive* entry point — for primitive-internal recording,
    keep using :func:`operation_context` directly so the
    post-commit lineage / column-edge / value-change hooks fire.

    Args:
        session_factory: SQLAlchemy session factory.
        agent_run_id: UUID string of the owning :class:`AgentRun`.
            Must already exist; the registry enforces the FK.
        op_name: One of the :class:`OpName` enum members.
        params: Arbitrary JSON-serialisable params describing the
            op shape.  Serialised into ``params_json``.
        target_table: Optional ``catalog.schema.table`` the op
            wrote to.  ``None`` for read-only ops.
        started_at: Wall-clock instant the op began.  Defaults to
            ``now()`` so the simplest case ("just record what
            happened") does not need a timestamp from the caller.
        finished_at: Wall-clock instant the op ended.  Defaults to
            ``started_at`` so the row reads as "instantaneous".
        error_message: ``repr(exc)`` on failure; ``None`` on
            success.
        rows_affected: Row count produced; ``None`` when not
            applicable.

    Returns:
        The auto-assigned primary key of the new row.

    Raises:
        AuditUnavailableError: When the run does not exist, the
            op_name is unknown, or any DB error blocks the insert.
    """  # noqa: DOC502 — delegate raises
    now = datetime.datetime.now(datetime.UTC)
    began_at = started_at or now
    ended_at = finished_at or began_at
    return record_operation(
        session_factory,
        agent_run_id=agent_run_id,
        op_name=op_name,
        params=dict(params),
        target_table=target_table,
        input_sha=None,
        rows_affected=rows_affected,
        delta_version_before=None,
        delta_version_after=None,
        started_at=began_at,
        finished_at=ended_at,
        error_message=error_message,
    )


def recall(
    *,
    session_factory: sessionmaker[Session],
    agent_id: str,
    op_name: OpName | None = None,
    target_table: str | None = None,
    status: str | None = None,
    since: datetime.datetime | None = None,
    until: datetime.datetime | None = None,
    limit: int = 200,
) -> list[AgentRunOperation]:
    """Query the operation log for an agent across all runs.

    The facade is a thin wrapper around
    :func:`recall_operations` — see that function's docstring for
    the full filter semantics.  Kept as a facade method so callers
    using ``pql.memory.recall`` do not need to know about the
    ``services.agent_runs.memory`` package layout.

    Args:
        session_factory: SQLAlchemy session factory.
        agent_id: Free-form runtime-side identifier
            (:attr:`AgentRun.agent_id`).
        op_name: Restrict to a single op type.  ``None`` means all.
        target_table: Restrict to ops whose target_table matches
            exactly.  ``None`` means all.
        status: One of ``"success"`` / ``"failed"`` / ``"running"``,
            or ``None`` for all states.
        since: Lower bound (inclusive) on ``started_at``.
        until: Upper bound (exclusive) on ``started_at``.
        limit: Max rows to return.  Capped at 1000 silently.

    Returns:
        Operations ordered ``started_at DESC``.

    Raises:
        ValueError: When ``status`` is not one of the accepted
            three strings.
    """  # noqa: DOC502 — delegate raises
    return recall_operations(
        session_factory,
        agent_id=agent_id,
        op_name=op_name,
        target_table=target_table,
        status=status,
        since=since,
        until=until,
        limit=limit,
    )


def branch(
    *,
    client: Client,
    session_factory: sessionmaker[Session],
    agent_id: str,
    from_run_id: RunId,
    branch_name: str | None = None,
    pin_to_version: bool = True,
    unreachable_msg: str,
) -> dict[str, Any]:
    """Create a Delta branch off the schema state at run start.

    Concrete implementation lives in
    :func:`pointlessql.services.agent_runs.memory._branch.branch_from_run`;
    the facade delegates to it.  Importing lazily keeps the
    facade's top-level import light when callers only ever use
    :func:`record` / :func:`recall`.

    Args:
        client: Configured soyuz-catalog client.
        session_factory: SQLAlchemy session factory.
        agent_id: Identifier of the agent the run belongs to —
            used as the branch-name prefix when ``branch_name`` is
            ``None``.
        from_run_id: Source run whose schema state the branch
            captures.
        branch_name: Optional override for the branch suffix; when
            ``None`` defaults to ``f"{agent_id}_{from_run_id[:8]}"``.
        pin_to_version: When ``True`` (default), reads the source
            run's first-write ``delta_version_before`` and uses
            deltalake time-travel to snapshot tables at that
            version.  Gives :func:`replay` a deterministic
            starting state.  When ``False`` the branch is taken
            from the live schema (cheaper, non-deterministic).
        unreachable_msg: Pre-rendered catalog error text (caller
            controls URL visibility).

    Returns:
        ``{"branch_schema_fqn": ..., "parent_schema_fqn": ...,
        "pinned_delta_version": <int|None>}``.

    Raises:
        ValidationError: When the source run is unknown or has no
            recorded operations to branch from.
        BranchVersionUnavailableError: When ``pin_to_version`` is
            ``True`` but the requested Delta version was already
            VACUUM'd.
        CatalogUnavailableError: When soyuz-catalog is
            unreachable.
    """  # noqa: DOC502 — delegate raises
    from pointlessql.services.agent_runs.memory._branch import branch_from_run

    return branch_from_run(
        client=client,
        session_factory=session_factory,
        agent_id=agent_id,
        from_run_id=from_run_id,
        branch_name=branch_name,
        pin_to_version=pin_to_version,
        action="create",
        unreachable_msg=unreachable_msg,
    )


def fork(
    *,
    client: Client,
    session_factory: sessionmaker[Session],
    agent_id: str,
    from_run_id: RunId,
    branch_name: str | None = None,
    pin_to_version: bool = True,
    unreachable_msg: str,
) -> dict[str, Any]:
    """Semantic alias of :func:`branch` with ``action='fork'``.

    Same machinery, different label on the
    :class:`BranchAuditLog` row.  The split exists because the UI's
    branch-tree pane filters by action — "fork" lets a user pick
    out the branches they explicitly forked off a run from the
    schema-promotion / discard noise.

    Args:
        client: Configured soyuz-catalog client.
        session_factory: SQLAlchemy session factory.
        agent_id: Agent the run belongs to.
        from_run_id: Source run.
        branch_name: Optional override for the branch suffix.
        pin_to_version: Same semantics as :func:`branch`.
        unreachable_msg: Pre-rendered catalog error text.

    Returns:
        Same shape as :func:`branch`.
    """
    from pointlessql.services.agent_runs.memory._branch import branch_from_run

    return branch_from_run(
        client=client,
        session_factory=session_factory,
        agent_id=agent_id,
        from_run_id=from_run_id,
        branch_name=branch_name,
        pin_to_version=pin_to_version,
        action="fork",
        unreachable_msg=unreachable_msg,
    )


def replay(
    *,
    client: Client,
    engine: Engine,
    session_factory: sessionmaker[Session],
    branch_schema_fqn: str,
    source_run_id: RunId,
    agent_id: str | None = None,
    policy: ReplayPolicy = ReplayPolicy.SKIP_UNSAFE,
    unreachable_msg: str,
) -> ReplayResult:
    """Replay a source run's operations onto a branch schema.

    Concrete implementation lives in
    :func:`pointlessql.services.agent_runs.memory._replay.replay_run_on_branch`;
    the facade delegates to it.  Operations are re-invoked in
    ordinal order; targets are rewritten to point at
    ``branch_schema_fqn``.  Unsafe ops (DML mutations, dbt nodes,
    training, schema-destructive branches) are gated by
    ``policy``.

    Args:
        client: Configured soyuz-catalog client.
        engine: Engine to execute the replayed primitives on.
        session_factory: SQLAlchemy session factory.
        branch_schema_fqn: ``catalog.schema`` of the branch the
            replay writes into.
        source_run_id: Source run whose operations are replayed.
        agent_id: Optional agent_id stamped onto the new replay
            run's row; defaults to the source run's ``agent_id``.
        policy: Replay policy.  See :class:`ReplayPolicy`.
        unreachable_msg: Pre-rendered catalog error text.

    Returns:
        :class:`ReplayResult` with the new run id, the number of
        successfully replayed operations, and a tuple of skipped
        ops with reasons.

    Raises:
        ReplayUnsafeOpError: When ``policy`` is
            :attr:`ReplayPolicy.STRICT` and an unsafe op was
            encountered.
        ValidationError: When ``source_run_id`` is unknown or has
            no operations.
        CatalogUnavailableError: When soyuz-catalog is
            unreachable.
    """  # noqa: DOC502 — delegate raises
    from pointlessql.services.agent_runs.memory._replay import replay_run_on_branch

    return replay_run_on_branch(
        client=client,
        engine=engine,
        session_factory=session_factory,
        branch_schema_fqn=branch_schema_fqn,
        source_run_id=source_run_id,
        agent_id=agent_id,
        policy=policy,
        unreachable_msg=unreachable_msg,
    )


__all__ = [
    "ReplayPolicy",
    "ReplayResult",
    "branch",
    "fork",
    "record",
    "recall",
    "replay",
]
