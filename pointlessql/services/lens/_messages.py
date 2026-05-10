"""Lens message append + list helpers.

Every message goes through :func:`append_message` so the session's
``last_message_at`` and ``updated_at`` stay fresh and the cost
accumulator is bumped in lock-step.  Direct ORM writes bypass the
sidebar invariants and should be avoided.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from pointlessql.models import LensMessage
from pointlessql.services.lens._sessions import touch_session, update_session_cost

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


def append_message(
    factory: sessionmaker[Session],
    *,
    session_id: int,
    role: str,
    content: str | None = None,
    tool_name: str | None = None,
    tool_args: Any | None = None,
    tool_result: Any | None = None,
    tool_status: str | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_estimate: float = 0.0,
    duration_ms: int | None = None,
) -> LensMessage:
    """Persist one message turn and return the detached row.

    Side effect: bumps ``LensSession.last_message_at`` and adds
    *cost_estimate* to ``LensSession.total_cost_estimate`` in the
    same transaction context.

    Args:
        factory: SQLAlchemy sessionmaker.
        session_id: Owning Lens session.
        role: One of :data:`VALID_ROLES`.
        content: Plain text payload for ``user`` / ``assistant`` rows;
            short label for ``tool`` rows.
        tool_name: Required on ``tool`` rows.
        tool_args: JSON-serialisable input payload for ``tool`` rows.
        tool_result: JSON-serialisable output payload for ``tool`` rows.
        tool_status: One of :data:`VALID_TOOL_STATUSES`.
        tokens_in: LLM input token count for assistant rows.
        tokens_out: LLM output token count for assistant rows.
        cost_estimate: Cost delta to accumulate on the session.
        duration_ms: Wall-clock for tool / assistant rows.

    Returns:
        The detached :class:`LensMessage` row.
    """
    now = datetime.datetime.now(datetime.UTC)
    row = LensMessage(
        session_id=session_id,
        role=role,
        content=content,
        tool_name=tool_name,
        tool_args=tool_args,
        tool_result=tool_result,
        tool_status=tool_status,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_estimate=cost_estimate,
        duration_ms=duration_ms,
        created_at=now,
    )
    with factory() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    touch_session(factory, session_id=session_id)
    if cost_estimate > 0:
        update_session_cost(factory, session_id=session_id, delta=cost_estimate)
    return row


def list_session_messages(
    factory: sessionmaker[Session],
    *,
    session_id: int,
    limit: int | None = None,
) -> list[LensMessage]:
    """Return every message for *session_id* in chronological order.

    Args:
        factory: SQLAlchemy sessionmaker.
        session_id: Owning Lens session.
        limit: Optional cap (oldest dropped).  ``None`` returns every
            message — fine for typical thread sizes (≤ 100 msgs per
            :class:`LensSettings.max_messages_per_session`).

    Returns:
        Detached rows ordered by ``created_at ASC``.
    """
    with factory() as session:
        stmt = (
            select(LensMessage)
            .where(LensMessage.session_id == session_id)
            .order_by(LensMessage.created_at.asc(), LensMessage.id.asc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = list(session.scalars(stmt).all())
        for row in rows:
            session.expunge(row)
        return rows
