"""Rewrite-attempt audit endpoint.

The Hermes plugin's explain-first ``pql_query`` flow POSTs one row
here per rewrite-loop resolution: auto-success, auto-failure,
escalation to human approval, or "agent accepted the original cost-
gate verdict".  The run-detail UI surfaces the rows in a sub-tab on
the Operations top-tab, and the Grafana panel computes
weekly cost savings from the ``auto_rewrite_succeeded`` rows.

Auth model: any authenticated caller (session or API-key) whose
workspace owns the target run.  No additional scope is required —
recording one's own rewrite attempts is a normal agent action.
Workspace mismatch surfaces as 404 (``CatalogNotFoundError``) so we
don't leak the existence of out-of-workspace run UUIDs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from pointlessql.exceptions import CatalogNotFoundError, ValidationError
from pointlessql.models import (
    REWRITE_VERDICTS,
    AgentRun,
    RewriteAttempt,
)

router = APIRouter()


@router.post("/api/agent-runs/{run_id}/rewrite-attempt")
async def api_record_rewrite_attempt(
    request: Request,
    run_id: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Record one SQL rewrite-attempt outcome for *run_id*.

    Body shape::

        {
            "attempt_no": 1,
            "original_sql_hash": "abc123def456",
            "rewritten_sql_hash": "987zyx654wvu",
            "original_cost": 1500000,
            "rewritten_cost": 750,
            "verdict": "auto_rewrite_succeeded",
            "reason": "Added LIMIT 1000."
        }

    ``rewritten_sql_hash`` and ``rewritten_cost`` are optional; they
    are ``NULL`` for the ``human_approval_required`` and
    ``original_approved`` verdicts where no revision happened.
    ``reason`` is always optional.

    Args:
        request: Incoming FastAPI request.  Reads
            ``request.state.workspace_id`` for the workspace gate.
        run_id: The UUID string of the owning :class:`AgentRun`.
        body: JSON payload as documented above.

    Returns:
        ``{"id": <int>, "attempt_no": <int>, "verdict": <str>}``
        — the newly-created row's primary key + echoed verdict.

    Raises:
        CatalogNotFoundError: No run with that id exists in the
            caller's workspace.  Returned as 404.
        ValidationError: Required field is missing/malformed, or
            ``(agent_run_id, attempt_no)`` already has a row.
    """
    attempt_no = body.get("attempt_no")
    if not isinstance(attempt_no, int) or attempt_no < 1:
        raise ValidationError("attempt_no must be a positive integer")

    original_sql_hash = body.get("original_sql_hash")
    if not isinstance(original_sql_hash, str) or not original_sql_hash.strip():
        raise ValidationError("original_sql_hash must be a non-empty string")

    original_cost = body.get("original_cost")
    if not isinstance(original_cost, int) or original_cost < 0:
        raise ValidationError("original_cost must be a non-negative integer")

    verdict = body.get("verdict")
    if not isinstance(verdict, str) or verdict not in REWRITE_VERDICTS:
        raise ValidationError(f"verdict must be one of {sorted(REWRITE_VERDICTS)}")

    rewritten_sql_hash_raw = body.get("rewritten_sql_hash")
    rewritten_sql_hash: str | None
    if rewritten_sql_hash_raw is None:
        rewritten_sql_hash = None
    elif isinstance(rewritten_sql_hash_raw, str) and rewritten_sql_hash_raw.strip():
        rewritten_sql_hash = rewritten_sql_hash_raw.strip()
    else:
        raise ValidationError("rewritten_sql_hash must be a non-empty string or null")

    rewritten_cost_raw = body.get("rewritten_cost")
    rewritten_cost: int | None
    if rewritten_cost_raw is None:
        rewritten_cost = None
    elif isinstance(rewritten_cost_raw, int) and rewritten_cost_raw >= 0:
        rewritten_cost = rewritten_cost_raw
    else:
        raise ValidationError("rewritten_cost must be a non-negative integer or null")

    reason_raw = body.get("reason")
    reason: str | None
    if reason_raw is None:
        reason = None
    elif isinstance(reason_raw, str) and reason_raw.strip():
        reason = reason_raw.strip()
    else:
        reason = None

    workspace_id = int(getattr(request.state, "workspace_id", 1))

    factory = request.app.state.session_factory
    with factory() as session:
        run = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
        if run is None or int(run.workspace_id) != workspace_id:
            raise CatalogNotFoundError(f"agent run {run_id!r} not found")
        row = RewriteAttempt(
            workspace_id=workspace_id,
            agent_run_id=run_id,
            attempt_no=attempt_no,
            original_sql_hash=original_sql_hash.strip(),
            rewritten_sql_hash=rewritten_sql_hash,
            original_cost=original_cost,
            rewritten_cost=rewritten_cost,
            verdict=verdict,
            reason=reason,
            created_at=datetime.now(UTC),
        )
        session.add(row)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise ValidationError(
                f"rewrite-attempt {attempt_no} for run {run_id!r} already recorded"
            ) from exc
        session.refresh(row)
        return {
            "id": row.id,
            "attempt_no": row.attempt_no,
            "verdict": row.verdict,
        }
