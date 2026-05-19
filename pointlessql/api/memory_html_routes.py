"""HTML page for the agent-memory surface (Phase 90.1).

Single route: ``GET /memory/{agent_id}`` renders the "brain
browser" view of an agent's run timeline.  All interactive bits
(filter bar, branch action, replay action, discussion thread) go
through the JSON endpoints in :mod:`pointlessql.api.memory_routes`.
"""

from __future__ import annotations

import datetime
import json
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import desc, select

from pointlessql.api.dependencies import get_user
from pointlessql.models import AgentRun, AgentRunOperation, BranchAuditLog

router = APIRouter(tags=["memory"])


def _serialise_op_brief(op: AgentRunOperation) -> dict[str, Any]:
    """Compact JSON-serialisable view of one op for the timeline.

    Args:
        op: ORM row.

    Returns:
        Dict with the fields the template + Alpine factory consume.
    """
    return {
        "id": op.id,
        "agent_run_id": op.agent_run_id,
        "ordinal": op.ordinal,
        "op_name": op.op_name,
        "target_table": op.target_table,
        "rows_affected": op.rows_affected,
        "started_at": op.started_at.isoformat() if op.started_at else None,
        "finished_at": op.finished_at.isoformat() if op.finished_at else None,
        "error_message": op.error_message,
    }


def _group_runs_by_day(
    runs: list[AgentRun],
) -> list[dict[str, Any]]:
    """Bucket runs into per-day groups for the timeline pane.

    Args:
        runs: AgentRun rows, ordered however the caller likes.

    Returns:
        List of ``{"day": "YYYY-MM-DD", "runs": [...]}`` dicts,
        sorted most-recent-day first.
    """
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        day = run.started_at.strftime("%Y-%m-%d") if run.started_at else "unknown"
        buckets[day].append(
            {
                "id": run.id,
                "status": run.status,
                "notebook_path": run.notebook_path,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "tables_touched": _parse_tables_touched(run.tables_touched),
            }
        )
    return [
        {"day": day, "runs": runs_for_day}
        for day, runs_for_day in sorted(buckets.items(), reverse=True)
    ]


def _parse_tables_touched(raw: str | None) -> list[str]:
    """Best-effort parse of ``AgentRun.tables_touched``."""
    if not raw:
        return []
    try:
        loaded = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(loaded, list):
        return []
    result: list[str] = []
    for entry in loaded:  # type: ignore[reportUnknownVariableType]
        if isinstance(entry, str):
            result.append(entry)
    return result


def _branch_rows_for_agent(
    session: Any,
    *,
    run_ids: list[str],
) -> list[dict[str, Any]]:
    """Return BranchAuditLog rows whose run_id matches any of the agent's runs.

    Args:
        session: Open SQLAlchemy session.
        run_ids: List of agent-run UUIDs.

    Returns:
        Branch rows serialised with intent + pinned-version stamped
        from the payload_json so the UI can show them inline.
    """
    if not run_ids:
        return []
    rows = list(
        session.scalars(
            select(BranchAuditLog)
            .where(BranchAuditLog.run_id.in_(run_ids))
            .order_by(desc(BranchAuditLog.created_at))
        ).all()
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        payload: dict[str, Any] = {}
        if row.payload_json:
            try:
                payload = json.loads(row.payload_json)
            except (TypeError, ValueError):
                payload = {}
        result.append(
            {
                "id": row.id,
                "branch_schema_fqn": row.branch_schema_fqn,
                "parent_schema_fqn": row.parent_schema_fqn,
                "action": row.action,
                "intent": payload.get("intent", row.action),
                "pinned_delta_version": payload.get("pinned_delta_version"),
                "source_run_id": payload.get("source_run_id") or row.run_id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return result


@router.get("/memory/{agent_id}", response_class=HTMLResponse, response_model=None)
async def memory_page(
    agent_id: str, request: Request
) -> HTMLResponse | RedirectResponse:
    """Render the agent-memory "brain browser" page.

    Auth-gated like every other HTML route: unauthenticated callers
    redirect to ``/auth/login`` with the memory page as the next
    target.  An ``agent_id`` with zero recorded runs renders a
    valid page with empty state — the agent doesn't have to be
    "registered" anywhere; agent_id is just the foreign key on
    :attr:`AgentRun.agent_id`.

    Args:
        agent_id: Free-form runtime identifier.
        request: Incoming FastAPI request.

    Returns:
        Rendered ``pages/memory.html``.
    """
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(
            url=f"/auth/login?next=/memory/{agent_id}", status_code=303
        )
    factory = request.app.state.session_factory
    with factory() as session:
        runs = list(
            session.scalars(
                select(AgentRun)
                .where(AgentRun.agent_id == agent_id)
                .order_by(desc(AgentRun.started_at))
                .limit(200)
            ).all()
        )
        run_ids = [r.id for r in runs]
        operations = list(
            session.scalars(
                select(AgentRunOperation)
                .where(AgentRunOperation.agent_run_id.in_(run_ids))
                .order_by(desc(AgentRunOperation.started_at))
                .limit(200)
            ).all()
        )
        branches = _branch_rows_for_agent(session, run_ids=run_ids)

    last_seen: datetime.datetime | None = None
    for run in runs:
        if run.started_at and (last_seen is None or run.started_at > last_seen):
            last_seen = run.started_at

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/memory.html",
        {
            "active_page": "agents",
            "is_admin": user["is_admin"],
            "current_user_id": user["id"],
            "agent": {
                "id": agent_id,
                "run_count": len(runs),
                "last_seen": last_seen.isoformat() if last_seen else None,
            },
            "timeline": _group_runs_by_day(runs),
            "operations": [_serialise_op_brief(op) for op in operations],
            "branches": branches,
            "social_entity_kind": "agent_memory",
            "social_entity_ref": agent_id,
        },
    )
