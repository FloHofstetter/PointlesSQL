"""Audit-Read API backbone.

Three read-only JSON endpoints over the audit data lake.  All the
cockpit cross-axis navigation, PII masking, saved queries,
run-diff, and anomaly highlighting — plus the Hermes audit-read
tools, the Audit-Reviewer-Agent, and the Grafana panels — read
through this surface so the WHERE-clause logic lives in one
place.

Self-tracking — every successful call inserts a synthetic
``query_history`` row with ``read_kind="audit_api"`` so the
cockpit endpoints are themselves visible in the cockpit.  This
closes the "audit-of-audit" gap the roadmap calls out: an admin
who turns into the cockpit and never resurfaces should leave a
trail.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from sqlalchemy import func, select

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_admin,
    require_auditor,
)
from pointlessql.api.error_responses import STANDARD_ERROR_RESPONSES
from pointlessql.exceptions import (
    CatalogNotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from pointlessql.models import AgentRun, AnomalyAck, LineageValueChange
from pointlessql.services import audit_aggregator as agg
from pointlessql.services.query_history import VALID_READ_KINDS, list_queries, record_query

logger = logging.getLogger(__name__)

router = APIRouter(tags=["audit"])


def _resolve_workspace_lens(request: Request, override: str | None) -> tuple[int | None, str]:
    """Pick the audit query's workspace filter from the optional override.

    Implements the super-admin lens.  Three outcomes:

    * ``override is None`` (or whitespace-only) — scope to the request's
      resolved workspace (``request.state.workspace_id``).  The default
      cockpit experience.
    * ``override == "all"`` — admin-only.  Returns ``(None, "all")`` to
      tell :mod:`audit_aggregator` to skip the workspace filter.  Logs
      a ``read_kind="audit_api_cross_workspace"`` row downstream so
      the cross-workspace probe is observable.
    * ``override == "<slug>"`` — admin-only.  Resolves the slug to an
      ``id`` and scopes to it.  A non-admin caller asking for any
      workspace other than their resolved one gets a 403.

    Args:
        request: Incoming FastAPI request.
        override: Raw ``?workspace=`` query value.

    Returns:
        ``(workspace_id, mode)`` — ``workspace_id`` is ``None`` for
        the cross-workspace lens, an int otherwise; ``mode`` is one
        of ``"current"`` / ``"all"`` / ``"named"`` for telemetry.

    Raises:
        HTTPException: 403 when the caller is not a tenant admin and
            asked for ``"all"`` or a different workspace's slug.
        ValidationError: Slug doesn't resolve.
    """
    cleaned = (override or "").strip()
    current_id = int(getattr(request.state, "workspace_id", 1) or 1)
    if not cleaned:
        return current_id, "current"

    user = getattr(request.state, "user", None)
    is_admin = bool(user and user.get("is_admin"))

    if cleaned.lower() == "all":
        if not is_admin:
            raise PermissionDeniedError("?workspace=all requires admin")
        return None, "all"

    # Slug → id
    from pointlessql.services import workspaces as workspaces_service

    factory = request.app.state.session_factory
    ws = workspaces_service.get_workspace_by_slug(factory, slug=cleaned)
    if ws is None:
        raise ValidationError(f"workspace {cleaned!r} not found")
    if ws.id != current_id and not is_admin:
        raise PermissionDeniedError("?workspace=<slug> for a different workspace requires admin")
    return ws.id, "named"


def _parse_iso8601(name: str, value: str | None) -> datetime.datetime | None:
    """Parse an ISO-8601 query-string param, raising 422 on garbage.

    Naive timestamps are coerced to UTC so a caller passing
    ``?since=2026-04-20`` doesn't silently slide by their local
    offset.

    Args:
        name: Human-readable param name for the error message.
        value: Raw query-string value; ``None`` and empty strings
            short-circuit to ``None``.

    Returns:
        Parsed timezone-aware :class:`datetime`, or ``None`` when
        the param was unset.

    Raises:
        ValidationError: ``value`` is non-empty but not parseable.
    """
    if value is None or not value.strip():
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValidationError(f"{name} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.UTC)
    return parsed


def _record_self(
    request: Request,
    *,
    endpoint: str,
    params: dict[str, Any],
    started_at: datetime.datetime,
    read_kind: str = "audit_api",
) -> None:
    """Persist a ``query_history`` row for one ``/api/audit/*`` call.

    Best-effort — a failure to record the audit-of-audit row should
    never fail the actual audit response (the operator on-call
    needs the data more than they need a self-tracking row).

    Args:
        request: FastAPI request, carrying the authenticated user.
        endpoint: Stable string identifier for the route, e.g.
            ``"/api/audit/summary"``.
        params: Query-string params that were honoured (so a
            "weirdly-empty result" can be re-traced via the params
            the cockpit caller actually sent).
        started_at: Wall-clock instant the route began handling.
        read_kind: Defaults to ``"audit_api"``; cross-workspace
            lens calls pass ``"audit_api_cross_workspace"`` so the
            audit-of-audit aggregation can flag tenant-admin
            escalations into the god-eye view.
    """
    user = get_user(request)
    finished_at = datetime.datetime.now(datetime.UTC)
    factory = request.app.state.session_factory
    sql_text = f"-- audit_api: {endpoint} {json.dumps(params, sort_keys=True, default=str)}"
    try:
        record_query(
            factory,
            user_id=int(user.get("id") or 0),
            user_email=str(user.get("email") or "anonymous"),
            sql_text=sql_text,
            started_at=started_at,
            finished_at=finished_at,
            status="succeeded",
            row_count=None,
            duration_ms=int((finished_at - started_at).total_seconds() * 1000),
            referenced_tables=[],
            agent_run_id=None,
            read_kind=read_kind,
        )
    except Exception:  # noqa: BLE001 — audit-of-audit must never break the audit response
        logger.exception(
            "audit_api: failed to self-track",
            extra={"endpoint": endpoint},
        )


@router.get("/api/audit/summary", responses=STANDARD_ERROR_RESPONSES)
async def api_audit_summary(
    request: Request,
    since: str | None = Query(default=None, description="ISO-8601 lower bound"),
    until: str | None = Query(default=None, description="ISO-8601 upper bound (exclusive)"),
    principal: str | None = Query(default=None, description="AgentRun.principal filter"),
    agent_id: str | None = Query(default=None, description="AgentRun.agent_id filter"),
    table: str | None = Query(default=None, description="Three-part UC name target"),
    workspace: str | None = Query(
        default=None,
        description="Workspace lens. Slug or 'all'. Admin-only.",
    ),
) -> dict[str, Any]:
    """Single-dict counts of every cockpit metric.

    Powers the cockpit home stat cards and the
    ``pql_audit_summary`` Hermes tool.

    Args:
        request: Incoming FastAPI request.
        since: ISO-8601 lower bound on each metric's primary
            timestamp.  Inclusive.  ``None`` returns all-time.
        until: ISO-8601 upper bound.  Exclusive.  ``None`` is "now".
        principal: ``AgentRun.principal`` filter.
        agent_id: ``AgentRun.agent_id`` filter.
        table: Three-part UC name applied to op/lineage metrics.
        workspace: Workspace lens.  ``None`` (default) scopes to the
            request's current workspace.  ``"all"`` (admin-only)
            lifts the workspace filter for the super-admin lens.
            Any other slug (admin-only) targets that named
            workspace.

    Returns:
        ``{"since", "until", "principal", "agent_id", "table",
        "workspace", "lens_mode", "counts": {...}}``.
    """
    require_auditor(request)
    started_at = datetime.datetime.now(datetime.UTC)
    since_dt = _parse_iso8601("since", since)
    until_dt = _parse_iso8601("until", until)
    workspace_id, lens_mode = _resolve_workspace_lens(request, workspace)
    counts = agg.summary(
        request.app.state.session_factory,
        since=since_dt,
        until=until_dt,
        principal=principal,
        agent_id=agent_id,
        table=table,
        workspace_id=workspace_id,
    )
    response = {
        "since": since_dt.isoformat() if since_dt else None,
        "until": until_dt.isoformat() if until_dt else None,
        "principal": principal,
        "agent_id": agent_id,
        "table": table,
        "workspace": workspace,
        "lens_mode": lens_mode,
        "counts": counts,
    }
    _record_self(
        request,
        endpoint="/api/audit/summary",
        params={
            "since": since,
            "until": until,
            "principal": principal,
            "agent_id": agent_id,
            "table": table,
            "workspace": workspace,
        },
        started_at=started_at,
        read_kind="audit_api_cross_workspace" if lens_mode == "all" else "audit_api",
    )
    return response


@router.get("/api/audit/timeseries", responses=STANDARD_ERROR_RESPONSES)
async def api_audit_timeseries(
    request: Request,
    metric: str = Query(..., description="Cockpit metric"),
    bin_: str = Query("day", alias="bin", description="hour|day|week"),
    group_by: str = Query("none", description="none|table|principal"),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
    principal: str | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    table: str | None = Query(default=None),
    workspace: str | None = Query(
        default=None,
        description="Workspace lens. Slug or 'all'. Admin-only.",
    ),
) -> dict[str, Any]:
    """Time-binned series for one metric, optionally grouped.

    Args:
        request: Incoming FastAPI request.
        metric: One of :data:`audit_aggregator.VALID_METRICS`.
        bin_: ``"hour"`` / ``"day"`` / ``"week"``.  Aliased as
            ``bin`` in the query string because Python forbids the
            keyword ``bin`` as a parameter name.
        group_by: ``"none"`` / ``"table"`` / ``"principal"``.
        since: ISO-8601 lower bound.
        until: ISO-8601 upper bound (exclusive).
        principal: ``AgentRun.principal`` filter.
        agent_id: ``AgentRun.agent_id`` filter.
        table: Three-part UC name filter.
        workspace: Workspace lens.  See
            :func:`api_audit_summary` for the resolution rules.

    Returns:
        ``{"metric", "bin", "group_by", "points": [...]}``.

    Raises:
        ValidationError: ``metric``/``bin_``/``group_by`` are
            outside their respective whitelists, or ``since``/
            ``until`` are not ISO-8601.
    """
    require_auditor(request)
    if metric not in agg.VALID_METRICS:
        raise ValidationError(f"unknown metric: {metric}")
    if bin_ not in agg.VALID_BINS:
        raise ValidationError(f"unknown bin: {bin_}")
    if group_by not in agg.VALID_GROUP_BY:
        raise ValidationError(f"unknown group_by: {group_by}")
    started_at = datetime.datetime.now(datetime.UTC)
    since_dt = _parse_iso8601("since", since)
    until_dt = _parse_iso8601("until", until)
    workspace_id, lens_mode = _resolve_workspace_lens(request, workspace)
    response = agg.timeseries(
        request.app.state.session_factory,
        metric=metric,  # type: ignore[arg-type]
        bin_=bin_,  # type: ignore[arg-type]
        group_by=group_by,  # type: ignore[arg-type]
        since=since_dt,
        until=until_dt,
        principal=principal,
        agent_id=agent_id,
        table=table,
        workspace_id=workspace_id,
    )
    response["workspace"] = workspace
    response["lens_mode"] = lens_mode
    _record_self(
        request,
        endpoint="/api/audit/timeseries",
        params={
            "metric": metric,
            "bin": bin_,
            "group_by": group_by,
            "since": since,
            "until": until,
            "principal": principal,
            "agent_id": agent_id,
            "table": table,
            "workspace": workspace,
        },
        started_at=started_at,
        read_kind="audit_api_cross_workspace" if lens_mode == "all" else "audit_api",
    )
    return response


@router.get("/api/audit/anomalies", responses=STANDARD_ERROR_RESPONSES)
async def api_audit_anomalies(
    request: Request,
    metric: str = Query(..., description="Cockpit metric"),
    window_days: int = Query(default=7, ge=1, le=90),
    sigma: float = Query(default=2.0, ge=0.5, le=10.0),
    bin_: str = Query("day", alias="bin"),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
    principal: str | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    table: str | None = Query(default=None),
    workspace: str | None = Query(
        default=None,
        description="Workspace lens. Slug or 'all'. Admin-only.",
    ),
) -> dict[str, Any]:
    """One severity verdict per bin against an N-day rolling baseline.

    The defaults pick up :class:`AuditSettings` only when the
    caller omits them; explicit query params always win so an
    operator can drill into a "10-day baseline at 1.5σ" view
    without changing the global config.

    Args:
        request: Incoming FastAPI request.
        metric: One of :data:`audit_aggregator.VALID_METRICS`.
        window_days: Rolling-window size (1–90).
        sigma: σ-multiplier for the warn / critical split (0.5–10).
        bin_: ``"hour"`` / ``"day"`` / ``"week"``.
        since: ISO-8601 lower bound.
        until: ISO-8601 upper bound (exclusive).
        principal: ``AgentRun.principal`` filter.
        agent_id: ``AgentRun.agent_id`` filter.
        table: Three-part UC name filter.
        workspace: Workspace lens.  See
            :func:`api_audit_summary` for the resolution rules.

    Returns:
        ``{"metric", "baseline_window_days", "threshold_sigma",
        "bin", "points": [...]}``.

    Raises:
        ValidationError: ``metric``/``bin_`` outside the whitelist
            or ``since``/``until`` not ISO-8601.
    """
    require_auditor(request)
    if metric not in agg.VALID_METRICS:
        raise ValidationError(f"unknown metric: {metric}")
    if bin_ not in agg.VALID_BINS:
        raise ValidationError(f"unknown bin: {bin_}")
    started_at = datetime.datetime.now(datetime.UTC)
    since_dt = _parse_iso8601("since", since)
    until_dt = _parse_iso8601("until", until)
    workspace_id, lens_mode = _resolve_workspace_lens(request, workspace)
    response = agg.anomalies(
        request.app.state.session_factory,
        metric=metric,  # type: ignore[arg-type]
        window_days=window_days,
        sigma=sigma,
        bin_=bin_,  # type: ignore[arg-type]
        since=since_dt,
        until=until_dt,
        principal=principal,
        agent_id=agent_id,
        table=table,
        workspace_id=workspace_id,
    )
    response["workspace"] = workspace
    response["lens_mode"] = lens_mode
    _record_self(
        request,
        endpoint="/api/audit/anomalies",
        params={
            "metric": metric,
            "window_days": window_days,
            "sigma": sigma,
            "bin": bin_,
            "since": since,
            "until": until,
            "principal": principal,
            "agent_id": agent_id,
            "table": table,
            "workspace": workspace,
        },
        started_at=started_at,
        read_kind="audit_api_cross_workspace" if lens_mode == "all" else "audit_api",
    )
    return response


@router.get("/api/audit/principal-summary", responses=STANDARD_ERROR_RESPONSES)
async def api_audit_principal_summary(
    request: Request,
    principal: str = Query(..., description="AgentRun.principal exact match"),
    since: str | None = Query(default=None, description="ISO-8601 lower bound"),
    until: str | None = Query(default=None, description="ISO-8601 upper bound (exclusive)"),
    limit: int = Query(default=20, ge=1, le=200, description="Cap on returned runs"),
) -> dict[str, Any]:
    """Per-principal activity summary.

    Compliance questions like "which runs did <principal> drive last
    quarter, and what tables did they touch?" need this shape.  The
    five per-run audit axes from  give the deep-dive once
    a run is identified, but enumerating runs by principal across a
    window was missing.

    Aggregates :class:`AgentRun` rows for the principal in the window
    and returns headline counts plus the most recent ``limit`` runs
    (newest first).

    Args:
        request: Incoming FastAPI request.
        principal: Exact match against ``AgentRun.principal``.
        since: ISO-8601 lower bound on ``AgentRun.started_at``.
        until: ISO-8601 upper bound (exclusive).
        limit: Max number of run rows to return (default 20).

    Returns:
        ``{"principal", "since", "until", "counts": {...,
        matched_runs: int}, "runs": [...]}``.
    """
    require_auditor(request)
    started_at = datetime.datetime.now(datetime.UTC)
    since_dt = _parse_iso8601("since", since)
    until_dt = _parse_iso8601("until", until)

    factory = request.app.state.session_factory
    counts = agg.summary(
        factory,
        since=since_dt,
        until=until_dt,
        principal=principal,
        agent_id=None,
        table=None,
    )

    with factory() as session:
        stmt = select(AgentRun).where(AgentRun.principal == principal)
        if since_dt is not None:
            stmt = stmt.where(AgentRun.started_at >= since_dt)
        if until_dt is not None:
            stmt = stmt.where(AgentRun.started_at < until_dt)
        stmt = stmt.order_by(AgentRun.started_at.desc()).limit(limit)
        runs_rows = list(session.scalars(stmt).all())
        run_count_stmt = select(func.count(AgentRun.id)).where(AgentRun.principal == principal)
        if since_dt is not None:
            run_count_stmt = run_count_stmt.where(AgentRun.started_at >= since_dt)
        if until_dt is not None:
            run_count_stmt = run_count_stmt.where(AgentRun.started_at < until_dt)
        total_runs = int(session.scalar(run_count_stmt) or 0)
        runs_payload = [
            {
                "id": r.id,
                "agent_id": r.agent_id,
                "started_at": r.started_at.astimezone(datetime.UTC).isoformat(),
                "finished_at": (
                    r.finished_at.astimezone(datetime.UTC).isoformat() if r.finished_at else None
                ),
                "status": r.status,
                "tables_touched": r.tables_touched,
            }
            for r in runs_rows
        ]

    response = {
        "principal": principal,
        "since": since_dt.isoformat() if since_dt else None,
        "until": until_dt.isoformat() if until_dt else None,
        "counts": {**counts, "matched_runs": total_runs},
        "runs": runs_payload,
    }
    _record_self(
        request,
        endpoint="/api/audit/principal-summary",
        params={
            "principal": principal,
            "since": since,
            "until": until,
            "limit": limit,
        },
        started_at=started_at,
    )
    return response


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


@router.get("/api/audit/history", responses=STANDARD_ERROR_RESPONSES)
async def api_audit_history(
    request: Request,
    since: str | None = Query(default=None, description="ISO-8601 lower bound on started_at"),
    until: str | None = Query(default=None, description="ISO-8601 upper bound (exclusive)"),
    read_kind: str | None = Query(
        default=None,
        description="Filter to a single read_kind; default excludes audit_api to avoid recursion",
    ),
    status: str | None = Query(default=None, description="Filter on query_history.status"),
    limit: int = Query(default=200, ge=1, le=500),
    include_audit_api: bool = Query(
        default=False,
        description="Set true to include audit-of-audit rows; default hides them.",
    ),
) -> dict[str, Any]:
    """Paginated ``query_history`` slice for audit-trail traversal.

    gives the daily Audit-Reviewer-Agent (and the
    compliance / incident demo flows) a way to walk yesterday's
    activity log without the full SQL-editor surface.

    By default the response *excludes* rows whose ``read_kind`` is
    ``audit_api`` (the rows produced by the cockpit endpoints
    themselves, including this route).  Without that filter a
    well-meaning agent would page through its own audit-of-audit
    breadcrumbs forever; admins who do want to inspect the
    cockpit's self-tracking can pass ``?include_audit_api=true`` or
    ``?read_kind=audit_api`` directly.

    Args:
        request: Incoming FastAPI request.
        since: ISO-8601 lower bound on ``started_at``.  ``None`` is
            "all-time".
        until: ISO-8601 upper bound (exclusive).  ``None`` is "now".
        read_kind: Single ``read_kind`` filter.  Unknown values fall
            through to "no filter" (matches :func:`list_queries`'s
            tolerance contract).
        status: Filter to a single status value.  ``None`` returns
            all.
        limit: Hard row cap (1–500).
        include_audit_api: When ``False`` (the default) and no
            explicit ``read_kind`` is set, rows with
            ``read_kind='audit_api'`` are filtered out post-query.
            When ``True`` no recursion filter is applied.

    Returns:
        ``{"since", "until", "read_kind", "status", "include_audit_api",
        "limit", "rows": [...], "row_count": int}``.
    """
    require_auditor(request)
    started_at = datetime.datetime.now(datetime.UTC)
    since_dt = _parse_iso8601("since", since)
    until_dt = _parse_iso8601("until", until)
    factory = request.app.state.session_factory
    rows = list_queries(
        factory,
        since=since_dt,
        read_kind=read_kind,
        status=status,
        limit=limit,
    )
    if until_dt is not None:
        cutoff = until_dt.isoformat()
        rows = [r for r in rows if (r.get("started_at") or "") < cutoff]
    if not include_audit_api and read_kind != "audit_api":
        rows = [r for r in rows if r.get("read_kind") != "audit_api"]
    response: dict[str, Any] = {
        "since": since_dt.isoformat() if since_dt else None,
        "until": until_dt.isoformat() if until_dt else None,
        "read_kind": read_kind if read_kind in VALID_READ_KINDS else None,
        "status": status,
        "include_audit_api": include_audit_api,
        "limit": limit,
        "row_count": len(rows),
        "rows": rows,
    }
    _record_self(
        request,
        endpoint="/api/audit/history",
        params={
            "since": since,
            "until": until,
            "read_kind": read_kind,
            "status": status,
            "limit": limit,
            "include_audit_api": include_audit_api,
        },
        started_at=started_at,
    )
    return response


@router.get("/api/audit/cdf-subscriptions")
async def api_audit_cdf_subscriptions(
    request: Request,
    only_active: bool = Query(default=False, description="When True, omit paused subs"),
) -> dict[str, Any]:
    """List CDF tail subscriptions visible in the caller's workspace.

    Auditor-scope counterpart to the admin-only
    ``GET /api/admin/cdf-subscriptions``.  Reads only — no toggle,
    no register, no delete.  The Audit-Reviewer-Agent uses this to
    surface coverage gaps ("which foreign tables don't have a tail
    subscription yet?").

    Args:
        request: Incoming FastAPI request.
        only_active: When True, omit paused subscriptions.

    Returns:
        ``{"subscriptions": [...]}`` ordered by ``created_at DESC``.
    """
    require_auditor(request)
    started_at = datetime.datetime.now(datetime.UTC)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory

    from pointlessql.models import CdfTailSubscription

    with factory() as session:
        stmt = select(CdfTailSubscription).where(
            CdfTailSubscription.workspace_id == workspace_id
        )
        if only_active:
            stmt = stmt.where(CdfTailSubscription.is_active.is_(True))
        rows = list(
            session.scalars(stmt.order_by(CdfTailSubscription.created_at.desc())).all()
        )
        out = [
            {
                "id": r.id,
                "table_full_name": r.table_full_name,
                "row_id_column": r.row_id_column,
                "producer_label": r.producer_label,
                "is_active": bool(r.is_active),
                "last_version_processed": r.last_version_processed,
                "last_tailed_at": r.last_tailed_at.isoformat() if r.last_tailed_at else None,
                "last_error": r.last_error,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    response = {"subscriptions": out}
    _record_self(
        request,
        endpoint="/api/audit/cdf-subscriptions",
        params={"only_active": only_active},
        started_at=started_at,
    )
    return response


@router.get("/api/audit/cdf-events")
async def api_audit_cdf_events(
    request: Request,
    table: str = Query(..., description="Three-part UC name to read CDF events for"),
    limit: int = Query(default=50, ge=1, le=500, description="Max rows newest-first"),
) -> dict[str, Any]:
    """Read recent foreign-Delta CDF tail events for one table.

    Workspace-scoped: only events captured under the caller's
    current workspace are returned.  Counterpart to the
    table-detail "CDF events" tab; agent / plugin variant.

    Args:
        request: Incoming FastAPI request.
        table: Three-part UC name to read events for.
        limit: Hard cap on returned rows; clamped 1..500 by FastAPI.

    Returns:
        ``{"table", "subscription": {...} | None, "events": [...]}``.
        ``subscription`` is ``None`` when the workspace has no
        registered subscription for the table; ``events`` is then
        always empty.
    """
    require_auditor(request)
    started_at = datetime.datetime.now(datetime.UTC)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory

    from pointlessql.models import CdfTailEvent, CdfTailSubscription

    with factory() as session:
        sub = session.scalars(
            select(CdfTailSubscription).where(
                CdfTailSubscription.workspace_id == workspace_id,
                CdfTailSubscription.table_full_name == table,
            )
        ).first()
        sub_payload: dict[str, Any] | None
        events_payload: list[dict[str, Any]] = []
        if sub is None:
            sub_payload = None
        else:
            sub_payload = {
                "id": sub.id,
                "table_full_name": sub.table_full_name,
                "row_id_column": sub.row_id_column,
                "producer_label": sub.producer_label,
                "is_active": bool(sub.is_active),
                "last_version_processed": sub.last_version_processed,
                "last_tailed_at": sub.last_tailed_at.isoformat()
                if sub.last_tailed_at
                else None,
                "last_error": sub.last_error,
            }
            rows = list(
                session.scalars(
                    select(CdfTailEvent)
                    .where(
                        CdfTailEvent.workspace_id == workspace_id,
                        CdfTailEvent.table_full_name == table,
                    )
                    .order_by(CdfTailEvent.created_at.desc())
                    .limit(limit)
                ).all()
            )
            events_payload = [
                {
                    "id": r.id,
                    "delta_version": r.delta_version,
                    "row_id": r.row_id,
                    "change_type": r.change_type,
                    "commit_timestamp": r.commit_timestamp.isoformat()
                    if r.commit_timestamp
                    else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]

    response = {
        "table": table,
        "subscription": sub_payload,
        "events": events_payload,
    }
    _record_self(
        request,
        endpoint="/api/audit/cdf-events",
        params={"table": table, "limit": limit},
        started_at=started_at,
    )
    return response


_INBOX_SEVERITY_FILTERS: dict[str, tuple[str, ...]] = {
    "all": ("warn", "critical"),
    "warn": ("warn", "critical"),
    "critical": ("critical",),
}
_SEVERITY_RANK: dict[str, int] = {"ok": 0, "warn": 1, "critical": 2}


def _serialize_ack(ack: AnomalyAck) -> dict[str, Any]:
    """Render an :class:`AnomalyAck` into the inbox JSON shape.

    SQLite strips ``tzinfo`` on roundtrip, so naive datetimes are
    treated as UTC before formatting.
    """
    acked_at = ack.acked_at
    if acked_at.tzinfo is None:
        acked_at = acked_at.replace(tzinfo=datetime.UTC)
    dismissed_until: datetime.datetime | None = ack.dismissed_until
    if dismissed_until is not None and dismissed_until.tzinfo is None:
        dismissed_until = dismissed_until.replace(tzinfo=datetime.UTC)
    return {
        "id": ack.id,
        "metric": ack.metric,
        "bin_iso": ack.bin_iso,
        "bin_kind": ack.bin_kind,
        "group_value": ack.group_value,
        "group_kind": ack.group_kind,
        "acked_by": ack.acked_by,
        "acked_at": acked_at.isoformat(),
        "dismissed_until": dismissed_until.isoformat() if dismissed_until else None,
        "comment": ack.comment,
    }


def _ack_is_active(ack: AnomalyAck, now: datetime.datetime) -> bool:
    """Decide whether an ack still hides its anomaly from the inbox.

    Permanent acks (``dismissed_until is None``) are always active;
    snoozed acks expire at the stored timestamp and re-surface the
    anomaly afterwards.  SQLite roundtrips strip the ``tzinfo``, so
    naive timestamps are coerced to UTC before the compare.
    """
    if ack.dismissed_until is None:
        return True
    cutoff = ack.dismissed_until
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=datetime.UTC)
    return cutoff > now


@router.get("/api/audit/inbox", responses=STANDARD_ERROR_RESPONSES)
async def api_audit_inbox(
    request: Request,
    severity: str = Query(
        default="all", description="all | warn | critical (filters returned points)"
    ),
    metric: str | None = Query(
        default=None,
        description=(
            "Single cockpit metric.  Default scans the run-anomaly metric set "
            "(rejects + errored_ops)."
        ),
    ),
    bin_: str = Query("day", alias="bin", description="hour|day|week"),
    window_days: int = Query(default=7, ge=1, le=90),
    sigma: float = Query(default=2.0, ge=0.5, le=10.0),
    since: str | None = Query(default=None, description="ISO-8601 lower bound"),
    until: str | None = Query(default=None, description="ISO-8601 upper bound (exclusive)"),
    principal: str | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    table: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    include_acked: bool = Query(
        default=False,
        description="False (default) hides anomalies whose ack is permanent or still snoozed.",
    ),
) -> dict[str, Any]:
    """Cross-run anomaly inbox — aggregates anomaly points + ack state.

    Walks each metric in :data:`audit_aggregator.RUN_ANOMALY_METRICS`
    (or just the explicitly-named metric), pulls the per-bin anomaly
    series from :func:`audit_aggregator.anomalies`, joins against the
    ``anomaly_acks`` table for ack lifecycle, and returns the
    not-yet-acked breaches sorted severity-desc, then time-desc.

    Args:
        request: Incoming FastAPI request.
        severity: Minimum severity to surface — ``warn`` / ``critical``
            / ``all`` (alias for ``warn``-or-higher).
        metric: Optional single metric.  Falls back to the
            run-anomaly metric pair.
        bin_: ``hour`` / ``day`` / ``week`` — bin width for the
            aggregator and for ack lookups.
        window_days: Rolling-window size in days for the baseline.
        sigma: σ multiplier for the warn / critical split.
        since: ISO-8601 lower bound on the metric's primary
            timestamp; ``None`` is "all-time".
        until: ISO-8601 upper bound (exclusive); ``None`` is "now".
        principal: ``AgentRun.principal`` filter.
        agent_id: ``AgentRun.agent_id`` filter.
        table: Three-part UC name filter applied to op/lineage
            metrics; the inbox treats group_value as ``None`` either
            way (table is a *filter*, not a group axis).
        limit: Hard row cap (1–500).
        include_acked: ``False`` (default) hides anomalies whose ack
            is active.  ``True`` returns every breach with the ack
            payload attached.

    Returns:
        ``{"severity", "bin", "metrics", "since", "until", "principal",
        "agent_id", "table", "limit", "include_acked", "anomalies": [...],
        "total_count": int}``.

    Raises:
        ValidationError: ``severity``/``metric``/``bin_`` outside
            their whitelist or ``since``/``until`` not ISO-8601.
    """
    require_auditor(request)
    if severity not in _INBOX_SEVERITY_FILTERS:
        raise ValidationError(f"unknown severity: {severity!r}")
    if bin_ not in agg.VALID_BINS:
        raise ValidationError(f"unknown bin: {bin_!r}")
    if metric is not None and metric not in agg.VALID_METRICS:
        raise ValidationError(f"unknown metric: {metric!r}")

    started_at = datetime.datetime.now(datetime.UTC)
    since_dt = _parse_iso8601("since", since)
    until_dt = _parse_iso8601("until", until)
    factory = request.app.state.session_factory

    metrics_to_scan: tuple[str, ...] = (
        (metric,) if metric is not None else tuple(agg.RUN_ANOMALY_METRICS)
    )
    severity_whitelist = _INBOX_SEVERITY_FILTERS[severity]

    raw_points: list[dict[str, Any]] = []
    for metric_name in metrics_to_scan:
        result = agg.anomalies(
            factory,
            metric=metric_name,  # type: ignore[arg-type]
            window_days=window_days,
            sigma=sigma,
            bin_=bin_,  # type: ignore[arg-type]
            since=since_dt,
            until=until_dt,
            principal=principal,
            agent_id=agent_id,
            table=table,
        )
        for point in result["points"]:
            if point["severity"] not in severity_whitelist:
                continue
            raw_points.append({"metric": metric_name, **point})

    ack_lookup: dict[tuple[str, str, str], AnomalyAck] = {}
    if raw_points:
        wanted_metrics = sorted({p["metric"] for p in raw_points})
        wanted_bins = sorted({str(p["ts"]) for p in raw_points})
        with factory() as session:
            ack_stmt = select(AnomalyAck).where(
                AnomalyAck.metric.in_(wanted_metrics),
                AnomalyAck.bin_iso.in_(wanted_bins),
                AnomalyAck.bin_kind == bin_,
                AnomalyAck.group_value.is_(None),
                AnomalyAck.group_kind.is_(None),
            )
            for ack in session.scalars(ack_stmt).all():
                ack_lookup[(ack.metric, ack.bin_iso, ack.bin_kind)] = ack

    now = datetime.datetime.now(datetime.UTC)
    enriched: list[dict[str, Any]] = []
    for point in raw_points:
        key = (point["metric"], str(point["ts"]), bin_)
        ack = ack_lookup.get(key)
        ack_active = ack is not None and _ack_is_active(ack, now)
        if ack_active and not include_acked:
            continue
        enriched.append(
            {
                "metric": point["metric"],
                "bin_iso": str(point["ts"]),
                "bin_kind": bin_,
                "severity": point["severity"],
                "observed": point["observed"],
                "baseline_mean": point["baseline_mean"],
                "baseline_std": point["baseline_std"],
                "sigma": point["sigma"],
                "group_value": None,
                "group_kind": None,
                "ack": _serialize_ack(ack) if ack else None,
            }
        )

    enriched.sort(
        key=lambda r: (_SEVERITY_RANK.get(r["severity"], 0), r["bin_iso"]),
        reverse=True,
    )
    total = len(enriched)
    enriched = enriched[:limit]

    response: dict[str, Any] = {
        "severity": severity,
        "metrics": list(metrics_to_scan),
        "bin": bin_,
        "window_days": window_days,
        "threshold_sigma": sigma,
        "since": since_dt.isoformat() if since_dt else None,
        "until": until_dt.isoformat() if until_dt else None,
        "principal": principal,
        "agent_id": agent_id,
        "table": table,
        "limit": limit,
        "include_acked": include_acked,
        "total_count": total,
        "anomalies": enriched,
    }
    _record_self(
        request,
        endpoint="/api/audit/inbox",
        params={
            "severity": severity,
            "metric": metric,
            "bin": bin_,
            "window_days": window_days,
            "sigma": sigma,
            "since": since,
            "until": until,
            "principal": principal,
            "agent_id": agent_id,
            "table": table,
            "limit": limit,
            "include_acked": include_acked,
        },
        started_at=started_at,
    )
    return response


@router.post("/api/audit/anomaly-acks", status_code=201)
async def api_create_anomaly_ack(
    request: Request,
    body: dict[str, Any] = Body(..., description="Ack identity + optional snooze + comment"),
) -> dict[str, Any]:
    """Acknowledge (or snooze) one anomaly bin.

    Identity is the composite ``(metric, bin_iso, bin_kind,
    group_value, group_kind)`` tuple.  Re-acking an already-acked
    identity returns a 422 — un-ack first via ``DELETE``.

    Args:
        request: Incoming FastAPI request.
        body: ``{metric, bin_iso, bin_kind, group_value?,
            group_kind?, dismissed_until?, comment?}``.
            ``dismissed_until`` accepts ISO-8601; absence means a
            permanent ack.

    Returns:
        The :class:`AnomalyAck` row as :func:`_serialize_ack` shapes it.

    Raises:
        ValidationError: Required field missing, invalid metric/bin,
            ``dismissed_until`` not ISO-8601, or the identity is
            already acked.
    """
    require_auditor(request)
    user = get_user(request)

    metric = str(body.get("metric") or "").strip()
    if metric not in agg.VALID_METRICS:
        raise ValidationError(f"metric must be one of {sorted(agg.VALID_METRICS)}")
    bin_iso = str(body.get("bin_iso") or "").strip()
    if not bin_iso:
        raise ValidationError("bin_iso is required")
    bin_kind = str(body.get("bin_kind") or "").strip()
    if bin_kind not in agg.VALID_BINS:
        raise ValidationError(f"bin_kind must be one of {sorted(agg.VALID_BINS)}")

    group_value_raw = body.get("group_value")
    group_value = (
        str(group_value_raw).strip()
        if isinstance(group_value_raw, str) and group_value_raw.strip()
        else None
    )
    group_kind_raw = body.get("group_kind")
    group_kind: str | None = None
    if isinstance(group_kind_raw, str) and group_kind_raw.strip():
        group_kind = group_kind_raw.strip()
        if group_kind not in ("table", "principal"):
            raise ValidationError("group_kind must be 'table' or 'principal'")

    dismissed_until_raw = body.get("dismissed_until")
    dismissed_until: datetime.datetime | None = None
    if isinstance(dismissed_until_raw, str) and dismissed_until_raw.strip():
        try:
            dismissed_until = datetime.datetime.fromisoformat(dismissed_until_raw.strip())
        except ValueError as exc:
            raise ValidationError("dismissed_until must be ISO-8601") from exc
        if dismissed_until.tzinfo is None:
            dismissed_until = dismissed_until.replace(tzinfo=datetime.UTC)

    comment_raw = body.get("comment")
    comment = (
        str(comment_raw).strip() if isinstance(comment_raw, str) and comment_raw.strip() else None
    )

    factory = request.app.state.session_factory
    with factory() as session:
        if group_value is None:
            value_clause = AnomalyAck.group_value.is_(None)
        else:
            value_clause = AnomalyAck.group_value == group_value
        if group_kind is None:
            kind_clause = AnomalyAck.group_kind.is_(None)
        else:
            kind_clause = AnomalyAck.group_kind == group_kind
        # Anomaly acks are workspace-scoped — the UNIQUE constraint
        # includes workspace_id so two workspaces can independently
        # ack the same metric bin.
        workspace_id = int(getattr(request.state, "workspace_id", 1))
        existing = session.scalar(
            select(AnomalyAck).where(
                AnomalyAck.workspace_id == workspace_id,
                AnomalyAck.metric == metric,
                AnomalyAck.bin_iso == bin_iso,
                AnomalyAck.bin_kind == bin_kind,
                value_clause,
                kind_clause,
            )
        )
        if existing is not None:
            raise ValidationError(
                "anomaly already acknowledged — DELETE the existing ack first to re-acknowledge"
            )
        row = AnomalyAck(
            workspace_id=workspace_id,
            metric=metric,
            bin_iso=bin_iso,
            bin_kind=bin_kind,
            group_value=group_value,
            group_kind=group_kind,
            acked_by=str(user.get("email") or "anonymous"),
            acked_at=datetime.datetime.now(datetime.UTC),
            dismissed_until=dismissed_until,
            comment=comment,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)

    await audit(
        request,
        "anomaly_ack",
        f"anomaly:{metric}:{bin_iso}:{bin_kind}",
        {
            "group_value": group_value,
            "group_kind": group_kind,
            "dismissed_until": dismissed_until.isoformat() if dismissed_until else None,
            "comment": comment,
        },
    )
    return _serialize_ack(row)


@router.delete("/api/audit/anomaly-acks/{ack_id}")
async def api_delete_anomaly_ack(
    request: Request,
    ack_id: int,
) -> dict[str, Any]:
    """Remove one anomaly ack — re-surfaces the bin in the inbox.

    Args:
        request: Incoming FastAPI request.
        ack_id: Primary key of the row to remove.

    Returns:
        ``{"deleted": True, "id": ack_id}``.

    Raises:
        CatalogNotFoundError: No ack with that id.
    """
    require_auditor(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.scalar(select(AnomalyAck).where(AnomalyAck.id == ack_id))
        if row is None:
            raise CatalogNotFoundError(f"anomaly ack {ack_id} not found")
        identity = {
            "metric": row.metric,
            "bin_iso": row.bin_iso,
            "bin_kind": row.bin_kind,
            "group_value": row.group_value,
            "group_kind": row.group_kind,
        }
        session.delete(row)
        session.commit()
    await audit(
        request,
        "anomaly_unack",
        f"anomaly_ack:{ack_id}",
        identity,
    )
    return {"deleted": True, "id": ack_id, "identity": identity}
