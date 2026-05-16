"""PII cleartext-reveal endpoint.

Single-route module because cleartext-revealing a masked PII value is
a uniquely sensitive action: admin-only, every successful reveal
writes an audit-log row, and the audit-of-audit trail must survive
the cleartext leaving the server.  Keeping it isolated from the bulk
metric / history routes makes the privilege boundary visually
obvious.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request
from sqlalchemy import select

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import require_admin
from pointlessql.exceptions import ValidationError
from pointlessql.models import LineageValueChange

router = APIRouter(tags=["audit"])


@router.post("/api/audit/pii/reveal")
async def api_audit_pii_reveal(
    request: Request,
    body: dict[str, Any] = Body(..., description="Reveal-target metadata"),
) -> dict[str, Any]:
    """Return the cleartext for one masked PII value, audit-logged.

    admin-only.  Looks up the
    :class:`LineageValueChange` row identified by ``(run_id, op_id,
    table, row_id, column)`` and returns its raw old/new values.
    Every successful reveal writes an :class:`AuditLog` row of
    ``action='pii.value_revealed'`` so the trail survives the
    cleartext leaving the server.

    Args:
        request: Incoming FastAPI request.
        body: ``{"run_id", "op_id", "table", "row_id", "column"}``.

    Returns:
        ``{"found": bool, "old_value": str | None,
        "new_value": str | None}``.

    Raises:
        ValidationError: Required keys missing from ``body`` or
            ``op_id`` not coercible to int.
    """
    require_admin(request)
    run_id = str(body.get("run_id") or "").strip()
    op_id_raw = body.get("op_id")
    table = str(body.get("table") or "").strip()
    row_id = str(body.get("row_id") or "").strip()
    column = str(body.get("column") or "").strip()
    if not (run_id and op_id_raw is not None and table and row_id and column):
        raise ValidationError(
            "run_id, op_id, table, row_id, column are all required",
        )
    try:
        op_id = int(op_id_raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError("op_id must be an integer") from exc

    factory = request.app.state.session_factory
    with factory() as session:
        stmt = select(LineageValueChange).where(
            LineageValueChange.run_id == run_id,
            LineageValueChange.op_id == op_id,
            LineageValueChange.target_table == table,
            LineageValueChange.target_row_id == row_id,
            LineageValueChange.target_column == column,
        )
        row = session.scalars(stmt).first()
    if row is None:
        await audit(
            request,
            "pii.value_reveal_missed",
            f"{table}.{column}",
            {
                "run_id": run_id,
                "op_id": op_id,
                "row_id": row_id,
                "reason": "no_value_change_row",
            },
        )
        return {"found": False, "old_value": None, "new_value": None}
    await audit(
        request,
        "pii.value_revealed",
        f"{table}.{column}",
        {
            "run_id": run_id,
            "op_id": op_id,
            "row_id": row_id,
        },
    )
    return {
        "found": True,
        "old_value": row.old_value,
        "new_value": row.new_value,
    }
