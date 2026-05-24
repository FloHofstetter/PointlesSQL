"""Cross-run operation-log query for the agent-memory facade.

Backs :func:`pointlessql.pql.memory.recall`.  The composition lives
in its own service helper (instead of inlining in the facade)
because the SELECT is shared between the public facade and the
``/api/memory/{agent_id}/recall`` JSON route — both want the same
filter surface.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from pointlessql.models import AgentRun, AgentRunOperation
from pointlessql.types import OpName

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


_VALID_STATUS_FILTERS: frozenset[str] = frozenset({"success", "failed", "running"})


def recall_operations(
    session_factory: sessionmaker[Session],
    *,
    agent_id: str,
    op_name: OpName | None = None,
    target_table: str | None = None,
    status: str | None = None,
    since: datetime.datetime | None = None,
    until: datetime.datetime | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[AgentRunOperation]:
    """Query the operation log for an agent across all its runs.

    The JOIN to :class:`AgentRun` is what binds ``agent_id`` to a
    set of run IDs — the operations table itself only carries the
    ``agent_run_id`` FK.  Result rows are ordered by
    ``started_at DESC`` so the most recent activity comes first;
    the UI's operation-tape paginates by passing ``limit``.

    Args:
        session_factory: SQLAlchemy session factory.
        agent_id: Free-form runtime-side identifier
            (:attr:`AgentRun.agent_id`).
        op_name: Restrict to a single op type.  ``None`` means all.
        target_table: Restrict to ops whose target_table matches
            exactly.  ``None`` means all.  Wildcard / glob support
            is intentionally not here — the UI can ask the user for
            a precise FQN once the table is known.
        status: One of ``"success"``, ``"failed"``, ``"running"``.
            ``"success"`` filters ``error_message IS NULL AND
            finished_at IS NOT NULL``; ``"failed"`` filters
            ``error_message IS NOT NULL``; ``"running"`` filters
            ``finished_at IS NULL``.  ``None`` means all.
        since: Lower bound (inclusive) on ``started_at``.
        until: Upper bound (exclusive) on ``started_at``.
        limit: Max rows to return.  Capped at 1000 silently so a
            malformed UI request can't pull a multi-million-row log.
        offset: Zero-indexed row offset for paginated reads.
            Defaults to 0 (no skip).  Not capped — only ``limit`` is.

    Returns:
        Operations ordered ``started_at DESC``.  Empty list when no
        run carries the given ``agent_id`` — there is no "agent
        registry" separate from the run table, so an unknown
        ``agent_id`` is indistinguishable from an agent with zero
        operations.

    Raises:
        ValueError: When ``status`` is set to anything other than
            the three accepted strings.
    """
    if status is not None and status not in _VALID_STATUS_FILTERS:
        raise ValueError(
            f"recall_operations: status must be one of {sorted(_VALID_STATUS_FILTERS)}, "
            f"got {status!r}"
        )

    capped_limit = min(max(limit, 1), 1000)

    stmt = (
        select(AgentRunOperation)
        .join(AgentRun, AgentRunOperation.agent_run_id == AgentRun.id)
        .where(AgentRun.agent_id == agent_id)
    )
    if op_name is not None:
        stmt = stmt.where(AgentRunOperation.op_name == op_name.value)
    if target_table is not None:
        stmt = stmt.where(AgentRunOperation.target_table == target_table)
    if status == "success":
        stmt = stmt.where(
            AgentRunOperation.error_message.is_(None),
            AgentRunOperation.finished_at.is_not(None),
        )
    elif status == "failed":
        stmt = stmt.where(AgentRunOperation.error_message.is_not(None))
    elif status == "running":
        stmt = stmt.where(AgentRunOperation.finished_at.is_(None))
    if since is not None:
        stmt = stmt.where(AgentRunOperation.started_at >= since)
    if until is not None:
        stmt = stmt.where(AgentRunOperation.started_at < until)

    stmt = (
        stmt.order_by(AgentRunOperation.started_at.desc())
        .offset(max(0, int(offset)))
        .limit(capped_limit)
    )

    with session_factory() as session:
        return list(session.scalars(stmt).all())
