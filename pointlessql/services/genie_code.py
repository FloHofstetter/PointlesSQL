"""Genie Code — unified agentic-authoring command center.

PointlesSQL already ships every agentic-authoring surface on its own:
NL→SQL (Genie), NL→notebook cell sequences, the agent-proposes / human-
supervises pipeline canvas, ingest connectors, the jobs/scheduler DAG,
agent-run supervision, and the ML model registry.  What was missing is
the single full-page roof that unifies them.

This module supplies that roof: a curated registry of the authoring
entry points across surfaces, plus a cross-surface glance at the most
recent supervised agent runs.  Read-only — it links out to the existing
surfaces and summarises run state; the authoring itself still happens on
each surface.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.models.agent._runs import (
    STATUS_FAILED,
    STATUS_NEEDS_APPROVAL,
    STATUS_SUCCEEDED,
    TERMINAL_STATUSES,
    AgentRun,
)

#: The agentic-authoring entry points the command center unifies, in
#: display order.  Each is an existing PointlesSQL surface; the hub only
#: links to them.
AUTHORING_SURFACES: tuple[dict[str, str], ...] = (
    {
        "key": "sql",
        "label": "NL → SQL",
        "description": "Ask in natural language; Genie writes and runs the SQL.",
        "href": "/genie",
        "icon": "bi-chat-square-text",
    },
    {
        "key": "notebook",
        "label": "NL → Notebook cells",
        "description": "Generate a notebook cell sequence from a prompt.",
        "href": "/notebooks/workspace",
        "icon": "bi-journal-code",
    },
    {
        "key": "pipeline",
        "label": "Pipeline canvas",
        "description": "An agent proposes a pipeline; you supervise it on the canvas.",
        "href": "/data-products",
        "icon": "bi-diagram-2",
    },
    {
        "key": "ingest",
        "label": "Ingest connectors",
        "description": "Author managed ingestion connectors from a source.",
        "href": "/ingest/sources",
        "icon": "bi-cloud-download",
    },
    {
        "key": "jobs",
        "label": "Jobs & scheduler",
        "description": "Build jobs with tasks, triggers and dependencies.",
        "href": "/jobs",
        "icon": "bi-calendar2-check",
    },
    {
        "key": "runs",
        "label": "Agent run supervision",
        "description": "Watch, compare and approve supervised agent runs.",
        "href": "/runs",
        "icon": "bi-robot",
    },
    {
        "key": "ml",
        "label": "ML model registry",
        "description": "Register and track models in Unity Catalog.",
        "href": "/models",
        "icon": "bi-cpu",
    },
)

#: How many runs the recent-runs query scans for the glance stats.
_SCAN_LIMIT = 200


def authoring_surfaces() -> list[dict[str, str]]:
    """Return the agentic-authoring entry-point registry as fresh dicts.

    Returns:
        A list of ``{"key", "label", "description", "href", "icon"}``
        dicts in display order; each is a copy so a caller cannot mutate
        the module constant.
    """
    return [dict(surface) for surface in AUTHORING_SURFACES]


def command_center_overview(
    session_factory: sessionmaker[Session],
    *,
    workspace_id: int,
    limit: int = 10,
) -> dict[str, Any]:
    """Build the Genie Code command-center overview for a workspace.

    Args:
        session_factory: Sessionmaker callable for the metadata DB.
        workspace_id: Workspace whose agent runs to glance at.
        limit: How many recent runs to return in the detail list.

    Returns:
        A JSON-safe dict with the authoring ``surfaces`` registry, a
        ``stats`` rollup over the most recent runs (total / active /
        succeeded / failed / needs_approval), and a capped
        ``recent_runs`` detail list, newest first.
    """
    stats = {"total": 0, "active": 0, "succeeded": 0, "failed": 0, "needs_approval": 0}
    recent: list[dict[str, Any]] = []

    with session_factory() as session:
        rows = session.scalars(
            select(AgentRun)
            .where(AgentRun.workspace_id == workspace_id)
            .order_by(AgentRun.started_at.desc())
            .limit(_SCAN_LIMIT)
        ).all()

    for row in rows:
        stats["total"] += 1
        if row.status == STATUS_SUCCEEDED:
            stats["succeeded"] += 1
        elif row.status == STATUS_FAILED:
            stats["failed"] += 1
        elif row.status == STATUS_NEEDS_APPROVAL:
            stats["needs_approval"] += 1
        if row.status not in TERMINAL_STATUSES:
            stats["active"] += 1
        if len(recent) < limit:
            recent.append(
                {
                    "id": row.id,
                    "status": row.status,
                    "agent_id": row.agent_id,
                    "harness": row.harness,
                    "principal": row.principal,
                    "notebook_path": row.notebook_path,
                    "started_at": row.started_at.isoformat() if row.started_at else None,
                }
            )

    return {
        "surfaces": authoring_surfaces(),
        "stats": stats,
        "recent_runs": recent,
    }
