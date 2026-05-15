"""Home dashboard + global search routes.

Owns three routes that make up the user's landing surface:

* ``GET /`` (HTML) — the home dashboard rendered from
  :func:`build_home_summary` so first-paint matches the JSON
  endpoint shape.  Admins additionally get the connections list
  for the "Create foreign catalog" modal.
* ``GET /api/home/summary`` — the JSON twin of the home page;
  same payload, used by any in-page refresh.
* ``GET /api/search`` — Cmd+K command-palette search.  Aggregates
  catalog / schema / table / federation hits from soyuz with
  local jobs / dashboards / (admin-only) workspace notebooks and
  scores prefix-matches over substring matches.  Soyuz outages
  degrade per-source instead of failing the whole palette.

The shared score helpers (``score_match`` + ``epoch_seconds``) are
exported under those names so the catalog HTML pages still in
main.py — which do not call them today — could pick them up
later without re-implementing.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from pointlessql.api.dependencies import get_uc_client, get_user
from pointlessql.config import Settings
from pointlessql.exceptions import CatalogUnavailableError, PointlessSQLError
from pointlessql.services.notebook import _workspace as notebook_workspace_service
from pointlessql.types import TableFqn, UserInfo

logger = logging.getLogger(__name__)

router = APIRouter(tags=["home"])


def _templates(request: Request) -> Jinja2Templates:
    """Return the shared Jinja2Templates instance from app state."""
    return request.app.state.templates


def score_match(needle: str, haystack: str) -> float | None:
    """Return the match score or ``None`` when *needle* is absent.

    Prefix matches outrank substring matches so that typing ``prod`` ranks
    ``prod_orders`` above ``backup_prod``. Needle is assumed already
    casefolded; haystack is casefolded here so callers can pass raw names.
    """
    if not haystack:
        return None
    hay = haystack.casefold()
    if hay.startswith(needle):
        return 2.0
    if needle in hay:
        return 1.0
    return None


def epoch_seconds(value: Any) -> float:
    """Normalize a soyuz epoch-ms int or ORM ``datetime`` to float seconds.

    Used as the tiebreak key for `/api/search`. ``None`` and unrecognized
    types collapse to ``0.0`` so those hits always lose the tiebreak
    rather than raising mid-sort.
    """
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value) / 1000.0
    if isinstance(value, datetime):
        return value.timestamp()
    return 0.0


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

    return _templates(request).TemplateResponse(
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


@router.get("/api/search")
async def api_search(request: Request, q: str = "", limit: int = 50) -> list[dict[str, Any]]:
    """Aggregate global search hits for the Cmd+K command palette.

    Merges catalog / schema / table / federation objects from soyuz with
    local jobs, dashboards, and (for admins) workspace notebooks. Scoring
    favours prefix matches over substring matches; ties resolve by
    ``updated_at`` descending. An empty query returns ``[]``; the frontend
    renders the localStorage recent-searches in that case so we avoid the
    roundtrip entirely.

    Each soyuz source is wrapped individually: a partial outage (e.g. the
    connections list is momentarily 502) degrades to "those hits missing"
    rather than 502'ing the whole palette, which would make the shortcut
    disproportionately fragile for a supplementary navigation surface.
    """
    raw = q.strip()
    if not raw:
        return []
    limit = max(1, min(int(limit), 100))

    # Phase 80.6 operator parsing — Slack convention.  ``@<term>``
    # narrows to ``user`` results; ``#<term>`` narrows to ``topic``
    # results.  The leading sigil is stripped before scoring; a bare
    # ``@`` or ``#`` (no term) lists every member of the selected kind
    # — matches the Slack/Linear muscle-memory for "show me people /
    # topics" without making the user type a substring first.
    kind_filter: str | None = None
    if raw.startswith("@"):
        kind_filter = "user"
        raw = raw[1:]
    elif raw.startswith("#"):
        kind_filter = "topic"
        raw = raw[1:]
    needle = raw.casefold()
    if not needle and kind_filter is None:
        return []

    user = get_user(request)
    client = get_uc_client(request)
    workspace_id = int(getattr(request.state, "workspace_id", 0) or 0)

    async def _soyuz_tree() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        try:
            tree = await client.get_tree()
        except PointlessSQLError:
            logger.warning("search: soyuz tree unavailable", exc_info=True)
            return out
        for cat in tree:
            cat_name = str(cat.get("name") or "")
            cat_score = score_match(needle, cat_name)
            if cat_score is not None:
                out.append(
                    {
                        "type": "catalog",
                        "label": cat_name,
                        "description": str(cat.get("comment") or ""),
                        "url": f"/catalogs/{cat_name}",
                        "updated_at": epoch_seconds(cat.get("updated_at")),
                        "score": cat_score,
                    },
                )
            schemas_raw = cast(list[dict[str, Any]], cat.get("schemas") or [])
            for schema in schemas_raw:
                s_name = str(schema.get("name") or "")
                s_score = score_match(needle, s_name)
                if s_score is not None:
                    out.append(
                        {
                            "type": "schema",
                            "label": f"{cat_name}.{s_name}",
                            "description": str(schema.get("comment") or ""),
                            "url": f"/catalogs/{cat_name}/schemas/{s_name}",
                            "updated_at": epoch_seconds(schema.get("updated_at")),
                            "score": s_score,
                        },
                    )
                tables_raw = cast(list[dict[str, Any]], schema.get("tables") or [])
                for table in tables_raw:
                    t_name = str(table.get("name") or "")
                    t_score = score_match(needle, t_name)
                    if t_score is None:
                        continue
                    out.append(
                        {
                            "type": "table",
                            "label": TableFqn.from_parts(cat_name, s_name, t_name),
                            "description": str(table.get("comment") or ""),
                            "url": (f"/catalogs/{cat_name}/schemas/{s_name}/tables/{t_name}"),
                            "updated_at": epoch_seconds(table.get("updated_at")),
                            "score": t_score,
                        },
                    )
        return out

    async def _soyuz_federation() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        sources: list[tuple[str, Any, str]] = [
            ("connection", client.list_connections, "/connections/{name}"),
            ("credential", client.list_credentials, "/credentials/{name}"),
            (
                "external_location",
                client.list_external_locations,
                "/external-locations/{name}",
            ),
        ]
        for type_name, fetcher, url_tmpl in sources:
            try:
                rows = await fetcher()
            except PointlessSQLError:
                logger.warning("search: %s list unavailable", type_name, exc_info=True)
                continue
            for row in rows:
                name = str(row.get("name") or "")
                score = score_match(needle, name)
                if score is None:
                    continue
                out.append(
                    {
                        "type": type_name,
                        "label": name,
                        "description": str(row.get("comment") or ""),
                        "url": url_tmpl.format(name=name),
                        "updated_at": epoch_seconds(row.get("updated_at")),
                        "score": score,
                    },
                )
        return out

    def _local_jobs() -> list[dict[str, Any]]:
        from sqlalchemy import select as _select

        from pointlessql.models import Job as JobModel

        out: list[dict[str, Any]] = []
        factory = request.app.state.session_factory
        with factory() as session:
            stmt = _select(JobModel)
            if not user.get("is_admin"):
                stmt = stmt.where(JobModel.run_as_user_id == user["id"])
            for row in session.scalars(stmt).all():
                score = score_match(needle, row.name)
                if score is None:
                    continue
                out.append(
                    {
                        "type": "job",
                        "label": row.name,
                        "description": f"{row.kind} · {row.cron_expr}",
                        "url": f"/jobs/{row.id}",
                        "updated_at": epoch_seconds(row.updated_at),
                        "score": score,
                    },
                )
        return out

    def _local_dashboards() -> list[dict[str, Any]]:
        from sqlalchemy import select as _select

        from pointlessql.models import Dashboard as DashboardModel

        out: list[dict[str, Any]] = []
        factory = request.app.state.session_factory
        with factory() as session:
            for row in session.scalars(_select(DashboardModel)).all():
                title_score = score_match(needle, row.title)
                slug_score = score_match(needle, row.slug)
                score = title_score
                if slug_score is not None and (score is None or slug_score > score):
                    score = slug_score
                if score is None:
                    continue
                out.append(
                    {
                        "type": "dashboard",
                        "label": row.title,
                        "description": row.description or row.slug,
                        "url": f"/dashboards/{row.slug}",
                        "updated_at": epoch_seconds(row.updated_at),
                        "score": score,
                    },
                )
        return out

    def _local_notebooks() -> list[dict[str, Any]]:
        # Matches the admin boundary on /api/notebooks/tree.
        if not user.get("is_admin"):
            return []
        settings_obj: Settings = request.app.state.settings
        try:
            tree = notebook_workspace_service.list_workspace_tree(
                settings_obj.jupyter.notebooks_dir.resolve(),
            )
        except Exception:  # noqa: BLE001 — search must never fail the page
            logger.warning("search: notebook tree unavailable", exc_info=True)
            return []
        out: list[dict[str, Any]] = []

        def _walk(nodes: list[dict[str, Any]]) -> None:
            for node in nodes:
                kind = node.get("kind")
                if kind == "notebook":
                    name = str(node.get("name") or "")
                    path = str(node.get("path") or "")
                    score = score_match(needle, name) or score_match(needle, path)
                    if score is None:
                        continue
                    out.append(
                        {
                            "type": "notebook",
                            "label": name,
                            "description": path,
                            "url": f"/notebooks/workspace?path={path}",
                            "updated_at": 0.0,
                            "score": score,
                        },
                    )
                elif kind == "dir":
                    children = cast(list[dict[str, Any]], node.get("children") or [])
                    _walk(children)

        _walk(tree)
        return out

    def _local_phase80(  # noqa: C901 — flat dispatch over 8 entity kinds
    ) -> list[dict[str, Any]]:
        """Search the Phase 80.6 entity kinds.

        Covers data products, topics, issues, users, agents,
        workspaces, and saved queries.

        Best-effort: any model missing on an upgrade race or DB
        hiccup downgrades to an empty list rather than 502-ing the
        palette.  All queries are workspace-scoped where the model
        carries ``workspace_id``.
        """
        out: list[dict[str, Any]] = []
        factory = request.app.state.session_factory
        try:
            from sqlalchemy import or_
            from sqlalchemy import select as _select

            from pointlessql.models import (
                Agent,
                DataProduct,
                SavedQuery,
                Topic,
                Workspace,
            )
            from pointlessql.models.auth import User
            from pointlessql.models.social._issue import Issue
            from pointlessql.models.workspace._core import WorkspaceMember

            with factory() as session:
                # Data products
                dp_stmt = _select(DataProduct)
                if workspace_id:
                    dp_stmt = dp_stmt.where(
                        DataProduct.workspace_id == workspace_id
                    )
                for row in session.scalars(dp_stmt).all():
                    fqn = f"{row.catalog_name}.{row.schema_name}"
                    score = score_match(needle, fqn) or score_match(
                        needle, row.description or ""
                    )
                    if score is None:
                        continue
                    out.append(
                        {
                            "type": "data_product",
                            "label": fqn,
                            "description": (row.description or "")[:120],
                            "url": (
                                f"/data-products/{row.catalog_name}/{row.schema_name}"
                            ),
                            "updated_at": epoch_seconds(getattr(row, "updated_at", None)),
                            "score": score,
                        },
                    )
                # Topics
                topic_stmt = _select(Topic)
                if workspace_id:
                    topic_stmt = topic_stmt.where(Topic.workspace_id == workspace_id)
                for row in session.scalars(topic_stmt).all():
                    name = getattr(row, "display_name", None) or row.slug
                    desc = getattr(row, "description_md", "") or ""
                    score = score_match(needle, name) or score_match(
                        needle, row.slug
                    ) or score_match(needle, desc)
                    if score is None:
                        continue
                    out.append(
                        {
                            "type": "topic",
                            "label": name,
                            "description": desc[:120],
                            "url": f"/topics/{row.slug}",
                            "updated_at": epoch_seconds(
                                getattr(row, "created_at", None)
                            ),
                            "score": score,
                        },
                    )
                # Issues
                issue_stmt = _select(Issue)
                if workspace_id:
                    issue_stmt = issue_stmt.where(Issue.workspace_id == workspace_id)
                for row in session.scalars(issue_stmt).all():
                    title = getattr(row, "title", "")
                    score = score_match(needle, title)
                    if score is None:
                        continue
                    out.append(
                        {
                            "type": "issue",
                            "label": f"#{row.id}: {title}",
                            "description": getattr(row, "state", "") or "",
                            "url": f"/issues/{row.id}",
                            "updated_at": epoch_seconds(
                                getattr(row, "updated_at", None)
                            ),
                            "score": score,
                        },
                    )
                # Users (workspace members)
                user_stmt = (
                    _select(User)
                    .join(
                        WorkspaceMember,
                        WorkspaceMember.user_id == User.id,
                    )
                )
                if workspace_id:
                    user_stmt = user_stmt.where(
                        WorkspaceMember.workspace_id == workspace_id
                    )
                for row in session.scalars(user_stmt).all():
                    score = score_match(needle, row.display_name or "") or score_match(
                        needle, row.email
                    )
                    if score is None:
                        continue
                    out.append(
                        {
                            "type": "user",
                            "label": row.display_name or row.email,
                            "description": row.email,
                            "url": f"/users/{row.id}",
                            "updated_at": epoch_seconds(
                                getattr(row, "created_at", None)
                            ),
                            "score": score,
                        },
                    )
                # Agents
                agent_stmt = _select(Agent)
                if workspace_id:
                    agent_stmt = agent_stmt.where(Agent.workspace_id == workspace_id)
                for row in session.scalars(agent_stmt).all():
                    slug = getattr(row, "slug", "")
                    name = getattr(row, "display_name", None) or slug
                    score = score_match(needle, slug) or score_match(needle, name)
                    if score is None:
                        continue
                    out.append(
                        {
                            "type": "agent",
                            "label": name,
                            "description": slug,
                            "url": f"/agents/{slug}",
                            "updated_at": epoch_seconds(
                                getattr(row, "updated_at", None)
                            ),
                            "score": score,
                        },
                    )
                # Workspaces the caller is a member of
                ws_stmt = _select(Workspace).join(
                    WorkspaceMember,
                    WorkspaceMember.workspace_id == Workspace.id,
                ).where(WorkspaceMember.user_id == user["id"])
                for row in session.scalars(ws_stmt).all():
                    name = getattr(row, "name", row.slug)
                    score = score_match(needle, name) or score_match(needle, row.slug)
                    if score is None:
                        continue
                    out.append(
                        {
                            "type": "workspace",
                            "label": name,
                            "description": f"slug: {row.slug}",
                            "url": f"/workspaces/{row.slug}",
                            "updated_at": epoch_seconds(
                                getattr(row, "updated_at", None)
                            ),
                            "score": score,
                        },
                    )
                # Saved queries (the saved_queries table powers
                # /audit/queries + SQL editor saves)
                try:
                    sq_stmt = _select(SavedQuery)
                    for row in session.scalars(sq_stmt).all():
                        title = getattr(row, "title", "") or ""
                        body = getattr(row, "sql_body", "") or ""
                        score = score_match(needle, title) or score_match(
                            needle, body[:200]
                        )
                        if score is None:
                            continue
                        out.append(
                            {
                                "type": "saved_query",
                                "label": title or f"query #{row.id}",
                                "description": (body or "")[:120],
                                "url": f"/audit/queries/{row.id}",
                                "updated_at": epoch_seconds(
                                    getattr(row, "updated_at", None)
                                ),
                                "score": score,
                            },
                        )
                except Exception:  # noqa: BLE001 — SavedQuery may not exist
                    # bare-broad-ok: SavedQuery rows are best-effort —
                    # an upgrade-race or partial schema downgrades to
                    # empty saved-query hits without breaking the palette.
                    logger.debug("search: saved-query block failed", exc_info=True)
                _ = or_  # marker the import is intentional
        except Exception:  # noqa: BLE001 — palette must never fail the page
            logger.debug("search: phase 80.6 entity search failed", exc_info=True)
            return []
        return out

    tree_hits, fed_hits = await asyncio.gather(_soyuz_tree(), _soyuz_federation())
    hits: list[dict[str, Any]] = []
    hits.extend(tree_hits)
    hits.extend(fed_hits)
    hits.extend(_local_jobs())
    hits.extend(_local_dashboards())
    hits.extend(_local_notebooks())
    hits.extend(_local_phase80())

    if kind_filter is not None:
        hits = [h for h in hits if h["type"] == kind_filter]

    hits.sort(key=lambda h: (-float(h["score"]), -float(h["updated_at"])))
    return hits[:limit]
