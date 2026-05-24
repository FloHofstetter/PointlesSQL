"""Delta-Branch ↔ DP cross-link.

A "fork" of a DP is a live Delta branch whose ``parent_schema_fqn``
is ``<catalog>.<schema>`` (the DP's UC schema).  We read directly
from the workspace-local :class:`BranchAuditLog` instead of
walking soyuz catalog tags — the audit log is in our DB so the
endpoint is cheap, workspace-scoped automatically, and does not
require the ``supervisor`` scope the soyuz branch listing demands.

Each fork carries its most-recent action (``create`` / ``promote``
/ ``discard``) so the DP page can color-code the row.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import desc, select

from pointlessql.api.dependencies import current_workspace_id, require_user
from pointlessql.models import BranchAuditLog

logger = logging.getLogger(__name__)

router = APIRouter(tags=["data-products", "forks"])


@router.get("/api/data-products/{catalog}/{schema}/forks")
async def api_dp_forks(
    request: Request, catalog: str, schema: str
) -> dict[str, Any]:
    """List active Delta-branch forks of the DP's UC schema.

    Args:
        request: Incoming FastAPI request.
        catalog: UC catalog of the DP.
        schema: UC schema of the DP.

    Returns:
        ``{"forks": [{branch_schema_fqn, last_action, last_action_at}, ...]}``
        ordered by most-recently-touched first.
    """
    require_user(request)
    _ = current_workspace_id(request)  # auth-gate, log scope is global
    parent = f"{catalog}.{schema}"
    factory = request.app.state.session_factory
    with factory() as session:
        rows = list(
            session.scalars(
                select(BranchAuditLog)
                .where(BranchAuditLog.parent_schema_fqn == parent)
                .order_by(desc(BranchAuditLog.created_at))
            ).all()
        )

    # Collapse to one row per branch — pick the latest action.
    by_branch: dict[str, dict[str, Any]] = {}
    for r in rows:
        fqn = r.branch_schema_fqn
        if fqn in by_branch:
            continue
        by_branch[fqn] = {
            "branch_schema_fqn": fqn,
            "last_action": r.action,
            "last_action_at": r.created_at.isoformat() if r.created_at else None,
        }
    forks = list(by_branch.values())
    return {"forks": forks}
