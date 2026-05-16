"""Audit cockpit metric endpoints: summary, timeseries, anomalies.

All three are auditor-scoped, all three honour the super-admin lens,
and all three call :mod:`pointlessql.services.audit_aggregator` for
the actual SQL.  They sit together because the cockpit home and the
Hermes ``pql_audit_*`` tools always pull these three in tandem.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Query, Request

from pointlessql.api.audit._helpers import parse_iso8601, record_self, resolve_workspace_lens
from pointlessql.api.dependencies import require_auditor
from pointlessql.api.error_responses import STANDARD_ERROR_RESPONSES
from pointlessql.exceptions import ValidationError
from pointlessql.services import audit_aggregator as agg
from pointlessql.types import ReadKind

router = APIRouter(tags=["audit"])


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
    since_dt = parse_iso8601("since", since)
    until_dt = parse_iso8601("until", until)
    workspace_id, lens_mode = resolve_workspace_lens(request, workspace)
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
    record_self(
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
        read_kind=ReadKind.AUDIT_API_CROSS_WORKSPACE if lens_mode == "all" else ReadKind.AUDIT_API,
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
    since_dt = parse_iso8601("since", since)
    until_dt = parse_iso8601("until", until)
    workspace_id, lens_mode = resolve_workspace_lens(request, workspace)
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
    record_self(
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
        read_kind=ReadKind.AUDIT_API_CROSS_WORKSPACE if lens_mode == "all" else ReadKind.AUDIT_API,
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
    since_dt = parse_iso8601("since", since)
    until_dt = parse_iso8601("until", until)
    workspace_id, lens_mode = resolve_workspace_lens(request, workspace)
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
    record_self(
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
        read_kind=ReadKind.AUDIT_API_CROSS_WORKSPACE if lens_mode == "all" else ReadKind.AUDIT_API,
    )
    return response
