"""``GET /api/memory/{agent_id}/recall`` — filtered operation log.

Powers the memory page's recall-bar (free-text filter over op_name
/ target_table / status / date-range).  Server-side composition
goes through the :mod:`pointlessql.services.agent_runs.memory._recall`
helper so the SELECT is shared with :func:`pql.memory.recall`.
"""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Query, Request

from pointlessql.api.dependencies import require_user
from pointlessql.exceptions import BadRequestError
from pointlessql.services.agent_runs.memory._recall import recall_operations
from pointlessql.types import OpName

router = APIRouter()


def _parse_op_name(value: str | None) -> OpName | None:
    """Validate and convert the ``op_name`` query parameter.

    Args:
        value: Raw query string or ``None``.

    Returns:
        Enum member, or ``None`` when the input is unset.

    Raises:
        HTTPException: 400 when *value* is non-empty but not a
            recognised :class:`OpName` member.
    """
    if value is None or value == "":
        return None
    try:
        return OpName(value)
    except ValueError as exc:
        raise BadRequestError(f"unknown op_name {value!r}") from exc


def _parse_iso_datetime(value: str | None, *, field: str) -> datetime.datetime | None:
    """Parse an ISO-8601 timestamp from the query string.

    Args:
        value: Raw query string or ``None``.
        field: Field name used in the error message.

    Returns:
        Parsed datetime, or ``None`` when *value* is unset.

    Raises:
        HTTPException: 400 when *value* is non-empty but
            unparseable.
    """
    if value is None or value == "":
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except ValueError as exc:
        raise BadRequestError(
            f"{field}: expected ISO-8601 datetime, got {value!r}"
        ) from exc


@router.get("/{agent_id}/recall")
async def recall_endpoint(
    agent_id: str,
    request: Request,
    op_name: str | None = Query(default=None),
    target_table: str | None = Query(default=None),
    status: str | None = Query(default=None),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict[str, object]:
    """Filter the agent's operation log.

    Args:
        agent_id: Free-form runtime identifier.
        request: Incoming FastAPI request.
        op_name: Optional :class:`OpName` member name to filter on.
        target_table: Optional exact-match filter.
        status: One of ``"success"`` / ``"failed"`` / ``"running"``.
        since: ISO-8601 inclusive lower bound on ``started_at``.
        until: ISO-8601 exclusive upper bound on ``started_at``.
        limit: Cap on returned rows (1..1000).

    Returns:
        ``{"agent_id": str, "operations": [...], "count": int}``.

    Raises:
        HTTPException: 400 when a query parameter is malformed.
    """
    require_user(request)
    factory = request.app.state.session_factory

    op_name_enum = _parse_op_name(op_name)
    since_dt = _parse_iso_datetime(since, field="since")
    until_dt = _parse_iso_datetime(until, field="until")

    try:
        ops = recall_operations(
            factory,
            agent_id=agent_id,
            op_name=op_name_enum,
            target_table=target_table,
            status=status,
            since=since_dt,
            until=until_dt,
            limit=limit,
        )
    except ValueError as exc:
        # bare-http-ok: surfaces the recall_operations ValueError
        # (e.g. unknown status filter) as a 400 with the cause text.
        raise BadRequestError(str(exc)) from exc

    return {
        "agent_id": agent_id,
        "count": len(ops),
        "operations": [
            {
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
            for op in ops
        ],
    }
