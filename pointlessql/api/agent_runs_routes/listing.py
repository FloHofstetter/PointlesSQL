"""JSON listing endpoints for runs and operations.

Two read-only endpoints back the Hermes Family-B tools and the
``/runs`` HTML sibling: ``GET /api/agent-runs`` lists recent runs
filtered by principal/agent/status/since, and
``GET /api/agent-runs/operations`` lists operation rows filtered by
target/errored/since.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from pointlessql.api.agent_runs_routes._serializers import serialize_agent_run
from pointlessql.exceptions import ValidationError
from pointlessql.models import AgentRunOperation
from pointlessql.models.agent._runs import AgentRun

router = APIRouter()


@router.get("/api/agent-runs/operations")
async def api_list_agent_run_operations(
    request: Request,
    target: str | None = Query(default=None, description="catalog.schema.table"),
    errored: bool = Query(default=False, description="Only return rows with error_message"),
    since: str | None = Query(default=None, description="ISO-8601 lower bound on started_at"),
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    """List ``agent_run_operations`` rows with the given filters applied.

    Backs the ``pql_recent_failures`` Hermes tool — when an agent is
    about to retry a write, asking "did this exact target fail
    recently for someone else?" should be one HTTP call instead of a
    join through ``/runs``.

    All three filters are optional and AND-ed together.  Rows are
    returned newest-first by ``started_at`` so the freshest failure
    is at the top.

    Args:
        request: Incoming FastAPI request.
        target: Three-part UC identifier to scope to.  ``None``
            returns rows across every target.
        errored: When ``True`` (or any truthy query value), only
            rows with a non-null ``error_message`` are returned.
        since: ISO-8601 timestamp (UTC); rows with
            ``started_at >= since`` are kept.  ``None`` keeps all.
        limit: Hard cap (default 50, max 500).

    Returns:
        ``{"operations": [...]}`` with each entry shaped like the
        per-run operations payload from ``runs_routes.load_operations_for_run``
        plus an ``agent_run_id`` so the caller can drill back into
        ``/runs/{id}``.

    Raises:
        ValidationError: ``since`` is provided but not parseable as
            ISO-8601.
    """
    since_dt: datetime | None = None
    if since is not None and since.strip():
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError as exc:
            raise ValidationError("since must be ISO-8601") from exc
        if since_dt.tzinfo is None:
            since_dt = since_dt.replace(tzinfo=UTC)

    factory = request.app.state.session_factory
    workspace_id = int(getattr(request.state, "workspace_id", 1))
    out: list[dict[str, Any]] = []
    with factory() as session:
        stmt = (
            select(AgentRunOperation)
            .where(AgentRunOperation.workspace_id == workspace_id)
            .order_by(AgentRunOperation.started_at.desc())
        )
        if target is not None and target.strip():
            stmt = stmt.where(AgentRunOperation.target_table == target.strip())
        if errored:
            stmt = stmt.where(AgentRunOperation.error_message.is_not(None))
        if since_dt is not None:
            stmt = stmt.where(AgentRunOperation.started_at >= since_dt)
        stmt = stmt.limit(limit)
        for row in session.scalars(stmt).all():
            duration_ms: int | None = None
            if row.finished_at is not None and row.started_at is not None:
                duration_ms = int((row.finished_at - row.started_at).total_seconds() * 1000)
            try:
                params = json.loads(row.params_json)
            except json.JSONDecodeError:
                params = {}
            out.append(
                {
                    "id": row.id,
                    "agent_run_id": row.agent_run_id,
                    "ordinal": row.ordinal,
                    "op_name": row.op_name,
                    "params": params,
                    "target_table": row.target_table,
                    "rows_affected": row.rows_affected,
                    "delta_version_before": row.delta_version_before,
                    "delta_version_after": row.delta_version_after,
                    "started_at": row.started_at.isoformat() if row.started_at else None,
                    "finished_at": (row.finished_at.isoformat() if row.finished_at else None),
                    "duration_ms": duration_ms,
                    "error_message": row.error_message,
                    "status": "error" if row.error_message else "ok",
                }
            )
    return {"operations": out}


@router.get("/api/agent-runs")
async def api_list_agent_runs(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    principal: str | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    since: str | None = Query(default=None, description="ISO-8601 lower bound on started_at"),
) -> dict[str, Any]:
    """List recent agent runs as JSON, optionally filtered.

    A companion to ``GET /runs`` for machine consumers (the Hermes
    plugin, curl probes, dashboards).  Ordered newest-first by
    ``started_at``.

    Optional ``principal`` / ``agent_id`` / ``status`` / ``since``
    filters back the Family-B ``pql_runs_by_principal`` and
    ``pql_runs_by_agent`` tools through a single backing route.
    Filters are AND-ed; missing filters fall through to "match all".

    Args:
        request: Incoming FastAPI request.
        limit: Maximum number of rows to return (1-500).
        principal: Exact-match filter on
            ``agent_runs.principal``.
        agent_id: Exact-match filter on ``agent_runs.agent_id``.
        status: Exact-match filter on ``agent_runs.status``.
        since: ISO-8601 lower bound on ``started_at``.

    Returns:
        ``{"runs": [...]}`` with each entry shaped by
        :func:`serialize_agent_run`.

    Raises:
        ValidationError: ``since`` is provided but not parseable as
            ISO-8601.
    """
    since_dt: datetime | None = None
    if since is not None and since.strip():
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError as exc:
            raise ValidationError("since must be ISO-8601") from exc
        if since_dt.tzinfo is None:
            since_dt = since_dt.replace(tzinfo=UTC)

    factory = request.app.state.session_factory
    workspace_id = int(getattr(request.state, "workspace_id", 1))
    with factory() as session:
        stmt = (
            select(AgentRun)
            .where(AgentRun.workspace_id == workspace_id)
            .order_by(AgentRun.started_at.desc())
            .limit(limit)
        )
        if principal is not None and principal.strip():
            stmt = stmt.where(AgentRun.principal == principal.strip())
        if agent_id is not None and agent_id.strip():
            stmt = stmt.where(AgentRun.agent_id == agent_id.strip())
        if status is not None and status.strip():
            stmt = stmt.where(AgentRun.status == status.strip())
        if since_dt is not None:
            stmt = stmt.where(AgentRun.started_at >= since_dt)
        rows = list(session.scalars(stmt).all())
        payload = [serialize_agent_run(r) for r in rows]
    return {"runs": payload}
