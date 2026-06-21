"""Builder for the agent-memory registry.

The per-agent memory page (``/memory/{agent_id}``) is rich, but it is a
dead end without the agent id in hand: nothing lists which agents have
left a trail.  This builder closes that gap by rolling up the existing
``agent_runs`` / ``agent_run_operations`` rows into one row per
``agent_id`` — run count, operation count, latest activity, the most
recent principal, and a status breakdown — so the registry page can act
as the discovery surface that links into each agent's memory.

It reads only existing tables; there is no new memory store.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy import select

from pointlessql.models import AgentRunOperation
from pointlessql.models.agent._runs import AgentRun


def build_registry(
    request: Request,
    *,
    query: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    """Roll up agent-run history into one registry row per agent id.

    Scoped to the caller's workspace.  Runs are scanned newest-first so
    the first row seen for an agent carries its latest activity and the
    principal it most recently acted for; operation counts come from a
    single pass over the workspace's operations keyed back to their
    agent via the run map.

    Args:
        request: Incoming FastAPI request (carries the workspace scope).
        query: Optional case-insensitive substring filter on ``agent_id``.
        limit: Max registry rows to return after ranking by recency.

    Returns:
        ``{"agents", "total", "query"}`` where each agent row has
        ``agent_id``, ``run_count``, ``op_count``, ``last_activity``,
        ``principal`` and a ``status_counts`` mapping.
    """
    factory = request.app.state.session_factory
    workspace_id = int(getattr(request.state, "workspace_id", 1))
    agents: dict[str, dict[str, Any]] = {}
    run_to_agent: dict[str, str] = {}

    with factory() as session:
        stmt = (
            select(AgentRun)
            .where(AgentRun.workspace_id == workspace_id, AgentRun.agent_id.is_not(None))
            .order_by(AgentRun.started_at.desc())
        )
        if query:
            stmt = stmt.where(AgentRun.agent_id.ilike(f"%{query}%"))
        for run in session.scalars(stmt).all():
            agent_id = run.agent_id
            if agent_id is None:
                continue
            run_to_agent[run.id] = agent_id
            entry = agents.setdefault(
                agent_id,
                {
                    "agent_id": agent_id,
                    "run_count": 0,
                    "op_count": 0,
                    "last_activity": None,
                    "principal": None,
                    "status_counts": {},
                },
            )
            entry["run_count"] += 1
            status_counts = entry["status_counts"]
            status_counts[run.status] = status_counts.get(run.status, 0) + 1
            # Rows arrive newest-first, so the first sighting of an agent
            # is its latest run — stamp recency/principal only then.
            if entry["last_activity"] is None:
                entry["last_activity"] = run.started_at.isoformat() if run.started_at else None
                entry["principal"] = run.principal

        op_stmt = select(AgentRunOperation.agent_run_id).where(
            AgentRunOperation.workspace_id == workspace_id
        )
        for run_id in session.scalars(op_stmt).all():
            agent_id = run_to_agent.get(run_id)
            if agent_id is not None:
                agents[agent_id]["op_count"] += 1

    ranked = sorted(agents.values(), key=lambda row: row["last_activity"] or "", reverse=True)
    return {"agents": ranked[:limit], "total": len(ranked), "query": query or ""}
