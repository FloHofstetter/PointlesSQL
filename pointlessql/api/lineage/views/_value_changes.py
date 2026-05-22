# pyright: reportPrivateUsage=false
"""Value-changes endpoint: ``/api/lineage/value-changes``."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from pointlessql.api.error_responses import STANDARD_ERROR_RESPONSES
from pointlessql.api.lineage.views._helpers import (
    _enforce_select,
    _get_session_factory,
)
from pointlessql.exceptions import ValidationError
from pointlessql.services.lineage_edges import fetch_value_changes_for_row

router = APIRouter(tags=["lineage"])


@router.get("/api/lineage/value-changes", responses=STANDARD_ERROR_RESPONSES)
async def api_value_changes(
    request: Request,
    table: str = Query(..., description="Three-part UC name"),
    row_id: str = Query(..., description="_lineage_row_id of the target row"),
    column: str | None = Query(None, description="Optional column-name filter"),
) -> dict[str, Any]:
    """Return per-cell preimage/postimage history for one target row.

    value-level analog of the row-trace and
    column-trace endpoints.  Returns every ``lineage_value_changes``
    row that lands on ``(table, row_id)``, optionally narrowed to one
    column.  Same SELECT-privilege enforcement as ``row-trace`` /
    ``column-trace``.

    Args:
        request: FastAPI request.
        table: Three-part UC name of the row's table.
        row_id: ``_lineage_row_id`` of the target row.
        column: Optional column name filter.

    Returns:
        ``{"table", "row_id", "column", "changes": [{"run_id",
        "op_id", "target_column", "old_value", "new_value",
        "created_at"}, ...]}`` ordered by ``created_at`` ascending.

    Raises:
        ValidationError: 400 when ``row_id`` is empty.
    """
    if not row_id:
        raise ValidationError("row_id is required")
    await _enforce_select(request, table)

    factory = _get_session_factory()
    rows = fetch_value_changes_for_row(
        factory,
        target_table=table,
        target_row_id=row_id,
        column=column,
    )
    return {
        "table": table,
        "row_id": row_id,
        "column": column,
        "changes": [
            {
                "run_id": r.run_id,
                "op_id": r.op_id,
                "target_column": r.target_column,
                "old_value": r.old_value,
                "new_value": r.new_value,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }
