"""Audit-Read API backbone — Sprint 18.0.

Three read-only JSON endpoints over the audit data lake.  Every
later 18.x sprint (cross-axis navigation, PII masking, saved
queries, run-diff, anomaly highlighting) and every 19.x consumer
(Hermes audit-read tools, Audit-Reviewer-Agent, Grafana panels)
reads through this surface so the WHERE-clause logic lives in one
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
from sqlalchemy import select

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import get_user, require_admin, require_auditor
from pointlessql.exceptions import ValidationError
from pointlessql.models import LineageValueChange
from pointlessql.services import audit_aggregator as agg
from pointlessql.services.query_history import VALID_READ_KINDS, list_queries, record_query

logger = logging.getLogger(__name__)

router = APIRouter(tags=["audit"])


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
            read_kind="audit_api",
        )
    except Exception as exc:  # noqa: BLE001 — audit-of-audit must never break the audit response
        logger.warning("audit_api: failed to self-track %s: %s", endpoint, exc)


@router.get("/api/audit/summary")
async def api_audit_summary(
    request: Request,
    since: str | None = Query(default=None, description="ISO-8601 lower bound"),
    until: str | None = Query(default=None, description="ISO-8601 upper bound (exclusive)"),
    principal: str | None = Query(default=None, description="AgentRun.principal filter"),
    agent_id: str | None = Query(default=None, description="AgentRun.agent_id filter"),
    table: str | None = Query(default=None, description="Three-part UC name target"),
) -> dict[str, Any]:
    """Single-dict counts of every cockpit metric.

    Powers the cockpit home stat cards and the
    ``pql_audit_summary`` Hermes tool (Sprint 19.1).

    Args:
        request: Incoming FastAPI request.
        since: ISO-8601 lower bound on each metric's primary
            timestamp.  Inclusive.  ``None`` returns all-time.
        until: ISO-8601 upper bound.  Exclusive.  ``None`` is "now".
        principal: ``AgentRun.principal`` filter.
        agent_id: ``AgentRun.agent_id`` filter.
        table: Three-part UC name applied to op/lineage metrics.

    Returns:
        ``{"since", "until", "principal", "agent_id", "table",
        "counts": {...}}``.
    """
    require_auditor(request)
    started_at = datetime.datetime.now(datetime.UTC)
    since_dt = _parse_iso8601("since", since)
    until_dt = _parse_iso8601("until", until)
    counts = agg.summary(
        request.app.state.session_factory,
        since=since_dt,
        until=until_dt,
        principal=principal,
        agent_id=agent_id,
        table=table,
    )
    response = {
        "since": since_dt.isoformat() if since_dt else None,
        "until": until_dt.isoformat() if until_dt else None,
        "principal": principal,
        "agent_id": agent_id,
        "table": table,
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
        },
        started_at=started_at,
    )
    return response


@router.get("/api/audit/timeseries")
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
    )
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
        },
        started_at=started_at,
    )
    return response


@router.get("/api/audit/anomalies")
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
    )
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

    Sprint 18.2 — admin-only.  Looks up the
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


@router.get("/api/audit/history")
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

    Sprint 19.1 — gives the daily Audit-Reviewer-Agent (and the
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
