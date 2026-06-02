"""Inline actions on actionable data-health / pipeline signals.

The feed surfaces open ``actionable_signals`` as data-health and
pipeline cards.  Acknowledging a card resolves the signal (an admin
decided it's handled), which drops it from every open feed via the
live union — no per-recipient bookkeeping.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import select

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import current_workspace_id, require_admin
from pointlessql.exceptions import CatalogNotFoundError
from pointlessql.models.actionable_signals import STATUS_OPEN, ActionableSignal
from pointlessql.services.signals import resolve_signal

router = APIRouter(tags=["feed"])


@router.post("/api/feed/signals/{signal_id}/ack")
async def api_acknowledge_signal(request: Request, signal_id: int) -> dict[str, Any]:
    """Acknowledge (resolve) an open data-health / pipeline signal.

    Admin-only: acknowledging marks the underlying problem as handled
    so the card drops from every feed.  If the condition is still
    truly breaching, the next scheduler tick re-opens a fresh signal,
    so an ack can never permanently silence a live problem.

    Args:
        request: Incoming FastAPI request.
        signal_id: The ``actionable_signals.id`` to acknowledge.

    Returns:
        ``{"ok": True, "resolved": bool}``.

    Raises:
        CatalogNotFoundError: No open signal with that id in the
            caller's workspace.
    """
    require_admin(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.scalar(
            select(ActionableSignal).where(
                ActionableSignal.id == signal_id,
                ActionableSignal.workspace_id == workspace_id,
                ActionableSignal.status == STATUS_OPEN,
            )
        )
        if row is None:
            raise CatalogNotFoundError(f"open signal {signal_id} not found")
        dedupe_key = row.dedupe_key
        signal_kind = row.signal_kind
        entity_kind = row.entity_kind
        entity_ref = row.entity_ref
    resolved = resolve_signal(
        factory,
        signal_kind=signal_kind,
        workspace_id=workspace_id,
        entity_kind=entity_kind,
        entity_ref=entity_ref,
        dedupe_key=dedupe_key,
    )
    await audit(request, "acknowledge_signal", f"signal:{signal_id}")
    return {"ok": True, "resolved": resolved}
