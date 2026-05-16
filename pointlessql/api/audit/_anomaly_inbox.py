"""Cross-run anomaly inbox + ack lifecycle.

Three endpoints around a single concern: surface anomaly bins that
breach the σ-threshold, let an auditor ack (or snooze) a bin, and
re-surface it via DELETE.  Named ``_anomaly_inbox`` instead of just
``_inbox`` to avoid colliding with the existing top-level
:mod:`pointlessql.api.audit.inbox`, which renders the HTML cockpit
page; this file owns the JSON API the cockpit (and the Hermes audit
tools) consume.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from sqlalchemy import select

from pointlessql.api._audit_helpers import audit
from pointlessql.api.audit._helpers import parse_iso8601, record_self
from pointlessql.api.dependencies import get_user, require_auditor
from pointlessql.api.error_responses import STANDARD_ERROR_RESPONSES
from pointlessql.exceptions import CatalogNotFoundError, ValidationError
from pointlessql.models import AnomalyAck
from pointlessql.services import audit_aggregator as agg

router = APIRouter(tags=["audit"])


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
    since_dt = parse_iso8601("since", since)
    until_dt = parse_iso8601("until", until)
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
    record_self(
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
