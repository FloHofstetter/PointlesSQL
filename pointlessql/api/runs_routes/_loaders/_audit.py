"""Audit axis — local audit-log entries + soyuz UC mutations."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy import select

from pointlessql.models import AuditLog


def load_audit_entries_for_run(
    request: Request,
    run_id: str,
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return the audit-log rows whose ``target`` references this run.

    Surfaces the audit trail next to the run metadata so the
    operator can see who created / approved / denied the run
    without leaving the detail page.  Both the registry routes
    and the Approve / Deny buttons write rows with
    ``target = "agent_run:{run_id}"``.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID string of the owning run.
        limit: Hard cap on rows returned; the sidebar is small.

    Returns:
        List of dicts in newest-first order.
    """
    factory = request.app.state.session_factory
    target_str = f"agent_run:{run_id}"
    out: list[dict[str, Any]] = []
    with factory() as session:
        stmt = (
            select(AuditLog)
            .where(AuditLog.target == target_str)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        for row in session.scalars(stmt).all():
            out.append(
                {
                    "id": row.id,
                    "action": row.action,
                    "actor_email": row.user_email,
                    "actor_role": row.actor_role,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "detail": row.detail,
                }
            )
    return out


async def load_uc_mutations_for_run(
    request: Request,
    run_id: str,
) -> list[dict[str, Any]]:
    """Return soyuz audit-log rows attributed to *run_id*.

    Asks soyuz's ``GET /audit-log?agent_run_id=`` cross-reference
    surface.  Returns ``[]`` against older soyuz versions that lack
    the endpoint — the run-detail "UC mutations" tab simply renders
    empty.

    Args:
        request: Incoming FastAPI request — provides
            ``app.state.uc_client``.
        run_id: Owning ``AgentRun.id``.

    Returns:
        Raw soyuz JSON dicts (``id`` / ``action`` / ``target`` /
        ``principal`` / ``agent_run_id`` / ``client_ip`` /
        ``detail`` / ``created_at``) ready for the template.
    """
    from pointlessql.services.audit import _soyuz as soyuz_audit

    uc = request.app.state.uc_client
    return await soyuz_audit.fetch_for_run(uc, run_id, limit=200)
