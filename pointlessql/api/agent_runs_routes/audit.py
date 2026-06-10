"""Five per-run audit-axis JSON endpoints.

Each route is supervisor-scope and short-circuits on a stale
``run_id`` via :func:`ensure_run_visible`.  Three of the five
delegate the actual SQL into
:mod:`pointlessql.api.runs_routes` — the value-changes and
column-lineage endpoints stay self-contained because they apply
PII masking / column-axis projections that the runs_routes side
does not need.

Every route also writes a self-tracking ``query_history``
breadcrumb via :func:`record_audit_self` so the cockpit/Hermes
audit traffic stays visible inside the same audit lake it queries.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from pointlessql.api.agent_runs_routes._audit_helpers import (
    ensure_run_visible,
    record_audit_self,
)
from pointlessql.api.dependencies import get_user, require_supervisor
from pointlessql.models import LineageColumnMap, LineageValueChange

router = APIRouter()


@router.get("/api/agent-runs/{run_id}/audit/lineage")
async def api_agent_run_audit_lineage(
    request: Request,
    run_id: str,
    op_id: int | None = Query(default=None, description="Restrict to a single op's edges"),
) -> dict[str, Any]:
    """Return :class:`LineageRowEdge` aggregates per op for one run.

    JSON sibling to the run-detail Lineage tab, consumed by the
    ``pql_query_row_lineage``-style Hermes tools.  Calls into
    :func:`runs_routes.load_lineage_summary_for_run` so the SQL
    stays in one place.

    Propagates :class:`AuthorizationError` when the caller lacks the
    supervisor or auditor scope, and :class:`CatalogNotFoundError`
    (from :func:`ensure_run_visible`) when no run with that id exists.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID of the run.
        op_id: Optional cross-axis filter — restrict aggregate to a
            single op.  Stale ids fall back to "no rows".

    Returns:
        ``{"run_id", "op_id", "total_edges", "rows": [...]}`` (rows
        carry ``ordinal``/``op_name``/``source_table``/``target_table``/
        ``edge_count``).
    """
    require_supervisor(request)
    started_at = datetime.now(UTC)
    factory = request.app.state.session_factory
    ensure_run_visible(factory, run_id, workspace_id=int(getattr(request.state, "workspace_id", 1)))
    from pointlessql.api.runs_routes import load_lineage_summary_for_run

    payload = load_lineage_summary_for_run(request, run_id, op_id=op_id)
    response = {"run_id": run_id, "op_id": op_id, **payload}
    record_audit_self(
        request,
        endpoint="/api/agent-runs/{run_id}/audit/lineage",
        params={"run_id": run_id, "op_id": op_id},
        started_at=started_at,
    )
    return response


@router.get("/api/agent-runs/{run_id}/audit/rejects")
async def api_agent_run_audit_rejects(
    request: Request,
    run_id: str,
    op_id: int | None = Query(default=None, description="Restrict to one op's rejects"),
) -> dict[str, Any]:
    """Return :class:`LineageRowReject` rows for one run as JSON.

    Wraps :func:`runs_routes.load_rejects_for_run`.  Reject reasons
    are stored verbatim in the DB; PII handling is the caller's
    problem (PointlesSQL doesn't mask rejects today).

    Propagates :class:`AuthorizationError` when the caller lacks the
    supervisor or auditor scope, and :class:`CatalogNotFoundError`
    (from :func:`ensure_run_visible`) when no run with that id exists.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID of the run.
        op_id: Optional filter — restrict to a single op.

    Returns:
        ``{"run_id", "op_id", "row_count", "rows": [...]}`` (rows
        carry ``op_id``/``source_table``/``source_row_id``/``reason``/
        ``detail``/``created_at``).
    """
    require_supervisor(request)
    started_at = datetime.now(UTC)
    factory = request.app.state.session_factory
    ensure_run_visible(factory, run_id, workspace_id=int(getattr(request.state, "workspace_id", 1)))
    from pointlessql.api.runs_routes import load_rejects_for_run

    rows = load_rejects_for_run(request, run_id, op_id=op_id)
    serialised = [
        {
            **{k: v for k, v in row.items() if k != "created_at"},
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        }
        for row in rows
    ]
    response = {
        "run_id": run_id,
        "op_id": op_id,
        "row_count": len(serialised),
        "rows": serialised,
    }
    record_audit_self(
        request,
        endpoint="/api/agent-runs/{run_id}/audit/rejects",
        params={"run_id": run_id, "op_id": op_id},
        started_at=started_at,
    )
    return response


@router.get("/api/agent-runs/{run_id}/audit/value-changes")
async def api_agent_run_audit_value_changes(
    request: Request,
    run_id: str,
    table: str | None = Query(default=None, description="Restrict to a target table FQN"),
    op_id: int | None = Query(default=None, description="Restrict to a single op"),
    limit: int = Query(default=200, ge=1, le=1000),
    mask: bool = Query(
        default=True,
        description="Mask reversible cell values; admin-only PII reveal at /api/audit/pii/reveal",
    ),
) -> dict[str, Any]:
    """Return :class:`LineageValueChange` rows for one run.

    Value-axis JSON view.  By default all ``old_value`` /
    ``new_value`` cells are masked at the API boundary; un-masking
    still requires admin via :func:`api_audit_pii_reveal`.  This
    keeps an auditor-key bound Hermes flow from inadvertently
    echoing reversible cleartext into a webhook.

    Propagates :class:`AuthorizationError` when the caller lacks the
    supervisor or auditor scope, and :class:`CatalogNotFoundError`
    (from :func:`ensure_run_visible`) when no run with that id exists.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID of the run.
        table: Optional target-table filter (three-part UC name).
        op_id: Optional op filter.
        limit: Hard row cap (1–1000).
        mask: When ``True`` (default), ``old_value`` / ``new_value``
            are replaced with ``"***"`` placeholders.  When
            ``False``, the API still strips both values to ``None``
            and surfaces only the row-level metadata — auditor scope
            does not authorise cleartext, period.  ``mask=false``
            is honoured only for the cookie-authenticated admin.

    Returns:
        ``{"run_id", "table", "op_id", "row_count", "masked": bool,
        "rows": [...]}``.
    """
    require_supervisor(request)
    started_at = datetime.now(UTC)
    factory = request.app.state.session_factory
    ensure_run_visible(factory, run_id, workspace_id=int(getattr(request.state, "workspace_id", 1)))
    user = get_user(request)
    cleartext_authorised = bool(user.get("is_admin")) and not mask
    rows: list[dict[str, Any]] = []
    with factory() as session:
        stmt = (
            select(LineageValueChange)
            .where(LineageValueChange.run_id == run_id)
            .order_by(LineageValueChange.id)
            .limit(limit)
        )
        if table is not None and table.strip():
            stmt = stmt.where(LineageValueChange.target_table == table.strip())
        if op_id is not None:
            stmt = stmt.where(LineageValueChange.op_id == op_id)
        for r in session.scalars(stmt):
            rows.append(
                {
                    "op_id": r.op_id,
                    "target_table": r.target_table,
                    "target_row_id": r.target_row_id,
                    "target_column": r.target_column,
                    "old_value": r.old_value if cleartext_authorised else None,
                    "new_value": r.new_value if cleartext_authorised else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
            )
    response = {
        "run_id": run_id,
        "table": table,
        "op_id": op_id,
        "row_count": len(rows),
        "masked": not cleartext_authorised,
        "rows": rows,
    }
    record_audit_self(
        request,
        endpoint="/api/agent-runs/{run_id}/audit/value-changes",
        params={"run_id": run_id, "table": table, "op_id": op_id, "limit": limit, "mask": mask},
        started_at=started_at,
    )
    return response


@router.get("/api/agent-runs/{run_id}/audit/external-writes")
async def api_agent_run_audit_external_writes(
    request: Request,
    run_id: str,
) -> dict[str, Any]:
    """Return ``unattributed_writes`` rows touching this run's tables.

    JSON over the existing :func:`runs_routes.load_unattributed_for_run`
    helper.  Filters to the tables the run actually touched (via
    ``AgentRun.tables_touched`` JSON) and to unacknowledged rows
    so the response mirrors the run-detail "External writes" tab.

    Propagates :class:`AuthorizationError` when the caller lacks the
    supervisor or auditor scope, and :class:`CatalogNotFoundError`
    (from :func:`ensure_run_visible`) when no run with that id exists.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID of the run.

    Returns:
        ``{"run_id", "tables_touched", "row_count", "rows": [...]}``.
    """
    require_supervisor(request)
    started_at = datetime.now(UTC)
    factory = request.app.state.session_factory
    run_row = ensure_run_visible(
        factory, run_id, workspace_id=int(getattr(request.state, "workspace_id", 1))
    )
    tables_touched: list[str] = []
    if run_row.tables_touched:
        try:
            decoded: Any = json.loads(run_row.tables_touched)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, list):
            tables_touched = [
                str(t)  # pyright: ignore[reportUnknownArgumentType]
                for t in decoded  # pyright: ignore[reportUnknownVariableType]
            ]
    from pointlessql.api.runs_routes import load_unattributed_for_run

    rows = load_unattributed_for_run(request, tables_touched=tables_touched)
    response = {
        "run_id": run_id,
        "tables_touched": tables_touched,
        "row_count": len(rows),
        "rows": rows,
    }
    record_audit_self(
        request,
        endpoint="/api/agent-runs/{run_id}/audit/external-writes",
        params={"run_id": run_id},
        started_at=started_at,
    )
    return response


@router.get("/api/agent-runs/{run_id}/audit/column-lineage")
async def api_agent_run_audit_column_lineage(
    request: Request,
    run_id: str,
    table: str | None = Query(default=None, description="Restrict to a target table FQN"),
    op_id: int | None = Query(default=None, description="Restrict to a single op"),
) -> dict[str, Any]:
    """Return :class:`LineageColumnMap` rows for one run.

    Column-axis JSON view.  Powers the ``pql_query_column_lineage``
    Hermes tool and is the backing surface the run-detail
    column-trace links also call.

    Propagates :class:`AuthorizationError` when the caller lacks the
    supervisor or auditor scope, and :class:`CatalogNotFoundError`
    (from :func:`ensure_run_visible`) when no run with that id exists.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID of the run.
        table: Optional target-table filter (three-part UC name).
        op_id: Optional op filter.

    Returns:
        ``{"run_id", "table", "op_id", "row_count", "rows": [...]}``
        with rows shaped ``{"op_id", "source_table", "source_column",
        "target_table", "target_column", "transform_kind",
        "transform_detail"}``.
    """
    require_supervisor(request)
    started_at = datetime.now(UTC)
    factory = request.app.state.session_factory
    ensure_run_visible(factory, run_id, workspace_id=int(getattr(request.state, "workspace_id", 1)))
    rows: list[dict[str, Any]] = []
    with factory() as session:
        stmt = (
            select(LineageColumnMap)
            .where(LineageColumnMap.run_id == run_id)
            .order_by(LineageColumnMap.id)
        )
        if table is not None and table.strip():
            stmt = stmt.where(LineageColumnMap.target_table == table.strip())
        if op_id is not None:
            stmt = stmt.where(LineageColumnMap.op_id == op_id)
        for r in session.scalars(stmt):
            rows.append(
                {
                    "op_id": r.op_id,
                    "source_table": r.source_table,
                    "source_column": r.source_column,
                    "target_table": r.target_table,
                    "target_column": r.target_column,
                    "transform_kind": r.transform_kind,
                    "transform_detail": r.transform_detail,
                }
            )
    response = {
        "run_id": run_id,
        "table": table,
        "op_id": op_id,
        "row_count": len(rows),
        "rows": rows,
    }
    record_audit_self(
        request,
        endpoint="/api/agent-runs/{run_id}/audit/column-lineage",
        params={"run_id": run_id, "table": table, "op_id": op_id},
        started_at=started_at,
    )
    return response
