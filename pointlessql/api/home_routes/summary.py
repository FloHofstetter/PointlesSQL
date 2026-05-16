"""Home dashboard payload + the two endpoints that surface it.

* ``GET /`` renders ``pages/home.html`` from
  :func:`build_home_summary` so the server-rendered first paint
  matches the JSON twin exactly.
* ``GET /api/home/summary`` returns the same payload as JSON for
  in-page refreshes.

The aggregator pulls the soyuz catalog count concurrently with the
local DB blocks and falls back per-source so a partial outage does
not 502 the whole page — same resilience contract as ``/api/search``.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import get_templates, get_uc_client, get_user
from pointlessql.exceptions import CatalogUnavailableError
from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)

router = APIRouter(tags=["home"])


async def build_home_summary(request: Request, user: UserInfo) -> dict[str, Any]:
    """Aggregate the payload that powers the home dashboard.

    Shared by the HTML ``/`` handler and the JSON ``/api/home/summary``
    endpoint so first-paint and subsequent refreshes see the same
    shape. The soyuz catalog count is fetched concurrently with the
    local DB aggregates; a soyuz outage downgrades to
    ``catalogs.unavailable = True`` but does not fail the whole
    response, matching the error-resilience rule used by
    ``/api/search`` above.

    Args:
        request: The incoming FastAPI request. Used for the UC client
            and the session factory.
        user: The current user's info dict.

    Returns:
        A dict with keys ``user``, ``catalogs``, ``jobs``,
        ``dashboards``, ``latest_runs``, ``sparkline``, and
        ``onboarding``. See ``/api/home/summary`` for the documented
        shape.
    """
    client = get_uc_client(request)
    is_admin = bool(user.get("is_admin"))
    user_id = int(user.get("id") or 0)

    async def _catalogs_block() -> dict[str, Any]:
        try:
            catalogs = await client.list_catalogs()
        except CatalogUnavailableError as exc:
            logger.warning("home: soyuz catalog list unavailable", exc_info=True)
            return {
                "count": 0,
                "has_catalogs": False,
                "unavailable": True,
                "error": exc.detail,
            }
        count = len(catalogs)
        return {
            "count": count,
            "has_catalogs": count > 0,
            "unavailable": False,
            "error": None,
        }

    def _db_block() -> dict[str, Any]:
        from sqlalchemy import func
        from sqlalchemy import select as _select

        from pointlessql.models import Dashboard as DashboardModel
        from pointlessql.models import Job as JobModel
        from pointlessql.models import JobRun as JobRunModel

        factory = request.app.state.session_factory
        with factory() as session:
            jobs_stmt = _select(JobModel)
            if not is_admin:
                jobs_stmt = jobs_stmt.where(JobModel.run_as_user_id == user_id)
            jobs_rows = list(session.scalars(jobs_stmt).all())
            count_visible = len(jobs_rows)
            count_paused = sum(1 for j in jobs_rows if j.is_paused)
            visible_job_ids = [j.id for j in jobs_rows]

            latest_runs: list[dict[str, Any]] = []
            if visible_job_ids:
                runs_stmt = (
                    _select(JobRunModel, JobModel.name)
                    .join(JobModel, JobRunModel.job_id == JobModel.id)
                    .where(JobRunModel.job_id.in_(visible_job_ids))
                    .order_by(JobRunModel.started_at.desc())
                    .limit(10)
                )
                for run, job_name in session.execute(runs_stmt).all():
                    duration: float | None = None
                    if run.started_at and run.finished_at:
                        duration = (run.finished_at - run.started_at).total_seconds()
                    latest_runs.append(
                        {
                            "id": run.id,
                            "job_id": run.job_id,
                            "job_name": job_name,
                            "status": run.status,
                            "trigger": run.trigger,
                            "started_at": run.started_at.isoformat() if run.started_at else None,
                            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                            "duration_s": duration,
                        },
                    )

            # 7-day rolling window including today. Only terminal runs
            # (succeeded + failed) count: pending/running would make the
            # rate drift mid-day, skipped is a scheduler signal, not a
            # real outcome.
            today = datetime.now(UTC).date()
            start_day = today - timedelta(days=6)
            window_start = datetime(start_day.year, start_day.month, start_day.day, tzinfo=UTC)
            days: list[dict[str, Any]] = [
                {
                    "date": (start_day + timedelta(days=i)).isoformat(),
                    "total": 0,
                    "succeeded": 0,
                    "rate": None,
                }
                for i in range(7)
            ]
            if visible_job_ids:
                spark_stmt = (
                    _select(JobRunModel.started_at, JobRunModel.status)
                    .where(JobRunModel.job_id.in_(visible_job_ids))
                    .where(JobRunModel.started_at >= window_start)
                    .where(JobRunModel.status.in_(["succeeded", "failed"]))
                )
                for started_at, status in session.execute(spark_stmt).all():
                    started_at_dt = cast(datetime, started_at)
                    idx = (started_at_dt.date() - start_day).days
                    if 0 <= idx < 7:
                        bucket = days[idx]
                        bucket["total"] += 1
                        if status == "succeeded":
                            bucket["succeeded"] += 1
                for bucket in days:
                    if bucket["total"] > 0:
                        bucket["rate"] = bucket["succeeded"] / bucket["total"]
            # Pre-compute the SVG bar styling server-side. Alpine's
            # ``<template x-for>`` inside ``<svg>`` doesn't work —
            # ``<template>.content`` is HTML-namespaced so inner
            # ``<rect>`` elements get parsed as unknown HTML, leaving
            # the bars unbound. Moving the branch here keeps the
            # template a plain Jinja ``{% for %}`` loop.
            for bucket in days:
                rate = bucket["rate"]
                if rate is None:
                    bucket["bar_height"] = 2
                    bucket["bar_class"] = "pql-spark--empty"
                    bucket["bar_title"] = f"{bucket['date']}: no runs"
                else:
                    bucket["bar_height"] = round(max(2.0, rate * 36), 2)
                    if rate >= 0.9:
                        bucket["bar_class"] = "pql-spark--ok"
                    elif rate >= 0.5:
                        bucket["bar_class"] = "pql-spark--warn"
                    else:
                        bucket["bar_class"] = "pql-spark--bad"
                    pct = round(rate * 100)
                    bucket["bar_title"] = (
                        f"{bucket['date']}: {bucket['succeeded']}/"
                        f"{bucket['total']} succeeded ({pct}%)"
                    )

            count_total = session.scalar(_select(func.count()).select_from(DashboardModel)) or 0
            count_mine = (
                session.scalar(
                    _select(func.count())
                    .select_from(DashboardModel)
                    .where(DashboardModel.owner_id == user_id),
                )
                or 0
            )
            mine_rows = list(
                session.scalars(
                    _select(DashboardModel)
                    .where(DashboardModel.owner_id == user_id)
                    .order_by(DashboardModel.updated_at.desc())
                    .limit(5),
                ).all(),
            )
            mine: list[dict[str, Any]] = [
                {
                    "slug": d.slug,
                    "title": d.title,
                    "notebook_path": d.notebook_path,
                    "job_id": d.job_id,
                    "updated_at": d.updated_at.isoformat() if d.updated_at else None,
                }
                for d in mine_rows
            ]

        return {
            "jobs": {"count_visible": count_visible, "count_paused": count_paused},
            "dashboards": {
                "count_total": int(count_total),
                "count_mine": int(count_mine),
                "mine": mine,
            },
            "latest_runs": latest_runs,
            "sparkline": {"days": days},
        }

    def _anomalies_block() -> dict[str, int]:
        """Count today's anomaly verdicts for the home banner.

        Best-effort: any failure (table missing on a fresh install,
        SQL hiccup) downgrades to ``{warn: 0, critical: 0}`` so the
        home dashboard never breaks because the cockpit aggregator
        is.  Admin-only display is enforced template-side.
        """
        if not is_admin:
            return {"warn": 0, "critical": 0}
        try:
            from pointlessql.services import audit_aggregator as agg

            settings = request.app.state.settings
            window_days = settings.audit.anomaly_baseline_window_days
            sigma = settings.audit.anomaly_threshold_sigma
            warn = 0
            critical = 0
            for metric in ("rejects", "errored_ops", "external_writes"):
                result = agg.anomalies(
                    request.app.state.session_factory,
                    metric=metric,  # type: ignore[arg-type]
                    window_days=window_days,
                    sigma=sigma,
                    bin_="day",
                )
                if not result["points"]:
                    continue
                latest = result["points"][-1]
                if latest["severity"] == "critical":
                    critical += 1
                elif latest["severity"] == "warn":
                    warn += 1
            return {"warn": warn, "critical": critical}
        except Exception:  # noqa: BLE001 — anomaly surface is best-effort
            logger.warning("home: anomaly aggregation failed", exc_info=True)
            return {"warn": 0, "critical": 0}

    def _latest_review_block() -> dict[str, Any] | None:
        """Surface yesterday's Audit-Reviewer-Agent verdict.

        Best-effort, mirrors :func:`_anomalies_block`: any failure
        (table missing on a fresh install, no review yet) returns
        ``None`` so the home page renders without the card.  Admin-
        gated display, same as the anomaly banner, because the
        Markdown body may quote run principals.
        """
        if not is_admin:
            return None
        try:
            from sqlalchemy import desc, select

            from pointlessql.models.agent._reviews import AgentReview

            with request.app.state.session_factory() as session:
                row = session.scalars(
                    select(AgentReview).order_by(desc(AgentReview.created_at)).limit(1)
                ).first()
                if row is None:
                    return None
                return {
                    "id": row.id,
                    "severity": row.severity,
                    "summary_md": row.summary_md,
                    "period_start": row.period_start.astimezone(UTC).isoformat(),
                    "period_end": row.period_end.astimezone(UTC).isoformat(),
                    "created_at": row.created_at.astimezone(UTC).isoformat(),
                }
        except Exception:  # noqa: BLE001 — review surface is best-effort
            logger.warning("home: latest review lookup failed", exc_info=True)
            return None

    def _today_blocks() -> dict[str, Any]:
        """Compute the Phase-80.3 Today-digest blocks in one session.

        Three aggregates power the new home cards (approval queue,
        unread inbox, firing alerts) plus the rail badges threaded
        via :func:`_resolve_nav_badges`.  Each query is workspace-
        or user-scoped; failures degrade silently to empty rows so
        the home dashboard never breaks because one aggregator does.
        """
        from sqlalchemy import desc, func
        from sqlalchemy import select as _select

        try:
            from pointlessql.models import Alert as AlertModel
            from pointlessql.models.agent._runs import (
                STATUS_NEEDS_APPROVAL,
            )
            from pointlessql.models.agent._runs import (
                AgentRun as AgentRunModel,
            )
            from pointlessql.models.notifications import UserNotification

            factory = request.app.state.session_factory
            workspace_id = int(user.get("workspace_id") or 0)
            with factory() as session:
                pending_stmt = (
                    _select(AgentRunModel)
                    .where(AgentRunModel.status == STATUS_NEEDS_APPROVAL)
                    .order_by(desc(AgentRunModel.started_at))
                    .limit(5)
                )
                if workspace_id:
                    pending_stmt = pending_stmt.where(
                        AgentRunModel.workspace_id == workspace_id
                    )
                pending_rows = list(session.scalars(pending_stmt).all())
                pending_count_stmt = _select(func.count()).select_from(AgentRunModel).where(
                    AgentRunModel.status == STATUS_NEEDS_APPROVAL
                )
                if workspace_id:
                    pending_count_stmt = pending_count_stmt.where(
                        AgentRunModel.workspace_id == workspace_id
                    )
                pending_count = int(session.scalar(pending_count_stmt) or 0)

                inbox_stmt = (
                    _select(UserNotification)
                    .where(UserNotification.recipient_user_id == user_id)
                    .where(UserNotification.read_at.is_(None))
                    .order_by(desc(UserNotification.created_at))
                    .limit(5)
                )
                inbox_rows = list(session.scalars(inbox_stmt).all())
                inbox_count_stmt = (
                    _select(func.count())
                    .select_from(UserNotification)
                    .where(UserNotification.recipient_user_id == user_id)
                    .where(UserNotification.read_at.is_(None))
                )
                inbox_count = int(session.scalar(inbox_count_stmt) or 0)

                alerts_stmt = _select(func.count()).select_from(AlertModel).where(
                    AlertModel.is_active.is_(True)
                )
                if workspace_id:
                    alerts_stmt = alerts_stmt.where(
                        AlertModel.workspace_id == workspace_id
                    )
                alerts_count = int(session.scalar(alerts_stmt) or 0)

                return {
                    "approval_queue": {
                        "count": pending_count,
                        "items": [
                            {
                                "id": r.id,
                                "principal": getattr(r, "principal_user_id", None),
                                "status": r.status,
                                "started_at": (
                                    r.started_at.isoformat() if r.started_at else None
                                ),
                            }
                            for r in pending_rows
                        ],
                    },
                    "unread_inbox": {
                        "count": inbox_count,
                        "items": [
                            {
                                "id": n.id,
                                "event_type": getattr(n, "event_type", "notification"),
                                "created_at": (
                                    n.created_at.isoformat() if n.created_at else None
                                ),
                            }
                            for n in inbox_rows
                        ],
                    },
                    "alerts_firing": {"count": alerts_count},
                }
        except Exception:  # noqa: BLE001 — Today surface is best-effort
            logger.warning("home: today aggregates failed", exc_info=True)
            return {
                "approval_queue": {"count": 0, "items": []},
                "unread_inbox": {"count": 0, "items": []},
                "alerts_firing": {"count": 0},
            }

    catalogs_block, db_block, anomalies_block, latest_review, today_block = (
        await asyncio.gather(
            _catalogs_block(),
            asyncio.to_thread(_db_block),
            asyncio.to_thread(_anomalies_block),
            asyncio.to_thread(_latest_review_block),
            asyncio.to_thread(_today_blocks),
        )
    )

    have_catalogs = bool(catalogs_block["has_catalogs"])
    have_jobs = db_block["jobs"]["count_visible"] > 0
    have_dashboards = db_block["dashboards"]["count_total"] > 0
    unavailable = bool(catalogs_block["unavailable"])
    # Suppress onboarding when soyuz is down — "connect a data source"
    # is the wrong prompt for a user whose data is fine but whose
    # catalog server is momentarily unreachable.
    show_onboarding = (
        not unavailable and not have_catalogs and not have_jobs and not have_dashboards
    )

    return {
        "user": {
            "display_name": user.get("display_name") or user.get("email", ""),
            "email": user.get("email", ""),
            "is_admin": is_admin,
        },
        "catalogs": catalogs_block,
        "jobs": db_block["jobs"],
        "dashboards": db_block["dashboards"],
        "latest_runs": db_block["latest_runs"],
        "sparkline": db_block["sparkline"],
        "anomalies": anomalies_block,
        "latest_review": latest_review,
        "approval_queue": today_block["approval_queue"],
        "unread_inbox": today_block["unread_inbox"],
        "alerts_firing": today_block["alerts_firing"],
        "onboarding": {
            "show": show_onboarding,
            "have_catalogs": have_catalogs,
            "have_jobs": have_jobs,
            "have_dashboards": have_dashboards,
        },
    }

@router.get("/", response_class=HTMLResponse)
async def catalogs_index(request: Request) -> HTMLResponse:
    """Render the home dashboard.

    Assembles every server-side card (catalog count, recent job runs,
    7-day sparkline, dashboards owned by the user, onboarding
    checklist) through :func:`build_home_summary` so the first-paint
    payload matches exactly what ``/api/home/summary`` would return.
    Admins additionally get the connections list so the "Create
    foreign catalog" modal has a pre-populated dropdown.
    """
    user = get_user(request)
    summary = await build_home_summary(request, user)
    connections: list[dict[str, Any]] = []
    if user.get("is_admin") and not summary["catalogs"]["unavailable"]:
        try:
            connections = await get_uc_client(request).list_connections()
        except CatalogUnavailableError:
            logger.warning("home: soyuz connections list unavailable", exc_info=True)
    from pointlessql.services import output_rendering as output_rendering_service

    return get_templates(request).TemplateResponse(
        request,
        "pages/home.html",
        {
            "summary": summary,
            "connections": connections,
            "is_admin": user.get("is_admin", False),
            "active_page": "home",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
            "render_markdown": output_rendering_service.render_markdown_source,
        },
    )


@router.get("/api/home/summary")
async def api_home_summary(request: Request) -> dict[str, Any]:
    """Return the aggregated payload that powers the home dashboard.

    One round-trip for every server-side card on ``/``: catalog count,
    jobs + paused counters, 10 most recent cross-job runs visible to
    the user, a 7-day success-rate bucket list for the sparkline, and
    the user's own dashboards + total dashboard count. Recent catalogs
    are client-side in ``localStorage["pql.recentCatalogs"]`` and do
    not flow through this endpoint.
    """
    user = get_user(request)
    return await build_home_summary(request, user)
