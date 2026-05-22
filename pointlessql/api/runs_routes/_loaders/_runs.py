"""Run-lifecycle axis — list, source, and lifecycle-event loaders."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy import func, select

from pointlessql.models import AgentRunEvent, AgentRunSource
from pointlessql.models.agent._runs import AgentRun


def load_runs(
    request: Request,
    *,
    offset: int = 0,
    limit: int = 200,
) -> tuple[list[dict[str, Any]], int]:
    """Fetch one page of agent-run rows plus the global count.

    Scoped to the caller's resolved workspace.  The super-admin
    "All workspaces" lens skips the filter via a separate code
    path.

    Args:
        request: Incoming FastAPI request.
        offset: Zero-based offset of the first row in the page.
        limit: Max rows to return; the list page caps at the table
            renderer's natural size.

    Returns:
        ``(rows, total)`` — one dict per row (newest-first, shaped by
        :func:`serialize_agent_run`) plus the unfiltered ``COUNT(*)``
        so the caller can decide whether to render a Load-More CTA.
    """
    from pointlessql.api.agent_runs_routes import serialize_agent_run

    factory = request.app.state.session_factory
    workspace_id = int(getattr(request.state, "workspace_id", 1))
    with factory() as session:
        total = int(
            session.scalar(
                select(func.count())
                .select_from(AgentRun)
                .where(AgentRun.workspace_id == workspace_id)
            )
            or 0
        )
        stmt = (
            select(AgentRun)
            .where(AgentRun.workspace_id == workspace_id)
            .order_by(AgentRun.started_at.desc())
            .offset(max(offset, 0))
            .limit(max(limit, 1))
        )
        rows = list(session.scalars(stmt).all())
        return [serialize_agent_run(row) for row in rows], total


def load_source_for_run(
    request: Request,
    run_id: str,
) -> dict[str, Any] | None:
    """Return the captured ``.py`` source row for *run_id* or ``None``.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID string of the owning run.

    Returns:
        ``{"source_bytes", "source_sha", "captured_at"}`` or ``None``
        when no source was captured (run predates the forced
        source-capture contract).
    """
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.scalar(select(AgentRunSource).where(AgentRunSource.agent_run_id == run_id))
        if row is None:
            return None
        return {
            "source_bytes": row.source_bytes,
            "source_sha": row.source_sha,
            "captured_at": row.captured_at.isoformat() if row.captured_at else None,
        }


def load_events_for_run(
    request: Request,
    run_id: str,
) -> list[dict[str, Any]]:
    """Return all CloudEvents lifecycle rows for *run_id*, oldest first.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID string of the owning run.

    Returns:
        List of dicts with ``event_type``, ``fired_at``, ``outcome``,
        ``event_id``.  Empty list when no events were persisted
        (run predates the lifecycle-event capture contract).
    """
    factory = request.app.state.session_factory
    out: list[dict[str, Any]] = []
    with factory() as session:
        stmt = (
            select(AgentRunEvent)
            .where(AgentRunEvent.agent_run_id == run_id)
            .order_by(AgentRunEvent.fired_at)
        )
        for row in session.scalars(stmt).all():
            out.append(
                {
                    "id": row.id,
                    "event_id": row.event_id,
                    "event_type": row.event_type,
                    "fired_at": row.fired_at.isoformat() if row.fired_at else None,
                    "outcome": row.outcome,
                }
            )
    return out
