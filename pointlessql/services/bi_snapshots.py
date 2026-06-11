"""BI-dashboard snapshot capture, refresh-schedule CRUD, and delivery.

Three concerns behind ``/api/bi/dashboards/{slug}/schedule`` and
``…/snapshots``:

* :func:`render_snapshot` — run every widget of a dashboard once and
  freeze the results (or the per-widget error) into one
  :class:`~pointlessql.models.bi_schedules.BiDashboardSnapshot` row.
* schedule CRUD (:func:`upsert_schedule` / :func:`get_schedule` /
  :func:`delete_schedule`) with the hidden backing
  :class:`~pointlessql.models.scheduler.Job` lifecycle — the same
  pattern query alerts use, so the existing scheduler drives the
  refresh without a second timing loop.
* :func:`bi_snapshot_executor` — the ``"bi_snapshot"`` job kind:
  capture, stamp ``last_run_at``, then deliver (in-app fan-out to the
  dashboard owner and/or a signed CloudEvents webhook).
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from croniter import croniter
from sqlalchemy import delete, select

from pointlessql.exceptions import ValidationError
from pointlessql.models.bi_dashboards import BiDashboard, BiDashboardWidget
from pointlessql.models.bi_schedules import BiDashboardSchedule, BiDashboardSnapshot
from pointlessql.models.scheduler import Job, JobLog, JobRun
from pointlessql.services import bi_dashboards as bi_service
from pointlessql.services._executor import run_sync
from pointlessql.services.alert_dispatcher import dispatch_webhook
from pointlessql.services.notebook._sql_cell import resolve_select_context
from pointlessql.services.notifications.fanout import fanout_event

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

    from pointlessql.services.unitycatalog import UnityCatalogClient
    from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)

_UNSET: Any = object()
"""Sentinel distinguishing "leave unchanged" from "set to None"."""

_ROW_CAPS: dict[str, int] = {"counter": 10, "table": 1_000, "chart": 10_000}
"""Per-kind row caps — mirrors the live widget-data endpoints."""

SNAPSHOT_EVENT_TYPE = "pointlessql.bi.snapshot_created"
"""Inbox event type stamped on every scheduled-capture fan-out."""

SNAPSHOT_CLOUDEVENT_TYPE = "sql.pointlessql.bi.snapshot.v1"
"""CloudEvents ``type`` of the snapshot webhook envelope."""


def _utcnow() -> datetime.datetime:
    """Return the current UTC wall-clock."""
    return datetime.datetime.now(datetime.UTC)


def serialize_schedule(row: BiDashboardSchedule) -> dict[str, Any]:
    """Project a schedule row to a JSON-safe dict.

    The HMAC secret is surfaced only as a boolean so the frontend
    never sees the raw value (mirrors alert destinations).

    Args:
        row: The schedule row.

    Returns:
        Dict shape consumed by the API routes and the view page.
    """
    return {
        "id": row.id,
        "dashboard_id": row.dashboard_id,
        "cron_expr": row.cron_expr,
        "is_active": row.is_active,
        "deliver_inapp": row.deliver_inapp,
        "webhook_url": row.webhook_url,
        "has_webhook_hmac": bool(row.webhook_hmac_secret),
        "backing_job_id": row.backing_job_id,
        "created_by_user_id": row.created_by_user_id,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def get_schedule(
    factory: sessionmaker[Session], *, dashboard_id: int
) -> BiDashboardSchedule | None:
    """Return the dashboard's schedule, or ``None``.

    Args:
        factory: SQLAlchemy session factory.
        dashboard_id: Owning dashboard's primary key.

    Returns:
        The detached row, or ``None`` when the dashboard is
        unscheduled.
    """
    with factory() as session:
        row = session.scalar(
            select(BiDashboardSchedule).where(BiDashboardSchedule.dashboard_id == dashboard_id)
        )
        if row is not None:
            session.expunge(row)
    return row


def _sync_backing_job(
    session: Session, schedule: BiDashboardSchedule, *, dashboard_slug: str
) -> None:
    """Materialise or update the scheduler Job for *schedule*.

    Unlike alerts (which only create the job on first activation) a
    snapshot schedule always carries its backing job and maps
    ``is_active`` onto the inverted ``Job.is_paused`` — there is no
    schedule state the job cannot mirror, so the 1:1 keeps reasoning
    simple and preserves run history across pauses.

    Args:
        session: Active SQLAlchemy session (caller commits).
        schedule: The schedule whose definition just changed.  Must
            be flushed (needs ``schedule.id`` for the job config).
        dashboard_slug: Slug of the owning dashboard — the job name
            derives from it so the hidden job stays identifiable.
    """
    now = _utcnow()
    job: Job | None = None
    if schedule.backing_job_id is not None:
        job = session.get(Job, schedule.backing_job_id)
    config = json.dumps({"schedule_id": schedule.id}, sort_keys=True)
    if job is None:
        job = Job(
            workspace_id=schedule.workspace_id,
            name=f"bi_snapshot:{dashboard_slug}",
            cron_expr=schedule.cron_expr,
            run_as_user_id=schedule.created_by_user_id,
            kind="bi_snapshot",
            config=config,
            is_paused=not schedule.is_active,
            max_parallel_runs=1,
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        session.flush()
        schedule.backing_job_id = job.id
    else:
        job.cron_expr = schedule.cron_expr
        job.run_as_user_id = schedule.created_by_user_id
        job.config = config
        job.is_paused = not schedule.is_active
        job.updated_at = now


def upsert_schedule(
    factory: sessionmaker[Session],
    *,
    dashboard_id: int,
    workspace_id: int,
    created_by_user_id: int,
    cron_expr: str,
    is_active: bool = True,
    deliver_inapp: bool = True,
    webhook_url: str | None = None,
    webhook_hmac_secret: Any = _UNSET,
) -> BiDashboardSchedule:
    """Create or replace the dashboard's schedule and sync its Job.

    Args:
        factory: SQLAlchemy session factory.
        dashboard_id: Owning dashboard's primary key.
        workspace_id: Tenant scope (denormalised onto the row).
        created_by_user_id: The scheduling user; the backing job runs
            as this principal.
        cron_expr: 5-field croniter expression.
        is_active: ``False`` pauses the backing job without deleting
            run history.
        deliver_inapp: Whether scheduled captures notify the owner.
        webhook_url: Optional CloudEvents delivery URL (``None``
            clears it).
        webhook_hmac_secret: New signing secret, ``None`` to clear,
            or unset to keep the stored one — so a UI save that
            never sees the secret cannot wipe it.

    Returns:
        The persisted schedule row (detached).

    Raises:
        ValidationError: On an invalid cron expression or an unknown
            dashboard.
    """
    clean_cron = (cron_expr or "").strip()
    if not clean_cron or not croniter.is_valid(clean_cron):
        raise ValidationError(f"cron_expr {cron_expr!r} is not a valid 5-field cron expression.")
    now = _utcnow()
    with factory() as session:
        dashboard = session.get(BiDashboard, dashboard_id)
        if dashboard is None:
            raise ValidationError(f"dashboard id={dashboard_id} not found")
        row = session.scalar(
            select(BiDashboardSchedule).where(BiDashboardSchedule.dashboard_id == dashboard_id)
        )
        if row is None:
            row = BiDashboardSchedule(
                workspace_id=workspace_id,
                dashboard_id=dashboard_id,
                cron_expr=clean_cron[:120],
                is_active=bool(is_active),
                deliver_inapp=bool(deliver_inapp),
                webhook_url=webhook_url,
                webhook_hmac_secret=(
                    None if webhook_hmac_secret is _UNSET else webhook_hmac_secret
                ),
                created_by_user_id=created_by_user_id,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
        else:
            row.cron_expr = clean_cron[:120]
            row.is_active = bool(is_active)
            row.deliver_inapp = bool(deliver_inapp)
            row.webhook_url = webhook_url
            if webhook_hmac_secret is not _UNSET:
                row.webhook_hmac_secret = webhook_hmac_secret
            row.created_by_user_id = created_by_user_id
            row.updated_at = now
        _sync_backing_job(session, row, dashboard_slug=dashboard.slug)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def delete_schedule(factory: sessionmaker[Session], *, dashboard_id: int) -> bool:
    """Delete the dashboard's schedule plus its backing Job and runs.

    Children go explicitly in the same transaction — SQLite
    connections without the foreign-key pragma (the test engine among
    them) would otherwise orphan them silently.  Snapshots stay: they
    are capture history, not schedule state.

    Args:
        factory: SQLAlchemy session factory.
        dashboard_id: Owning dashboard's primary key.

    Returns:
        ``True`` when a schedule row was deleted.
    """
    with factory() as session:
        row = session.scalar(
            select(BiDashboardSchedule).where(BiDashboardSchedule.dashboard_id == dashboard_id)
        )
        if row is None:
            return False
        backing_id = row.backing_job_id
        session.delete(row)
        if backing_id is not None:
            run_ids = list(session.scalars(select(JobRun.id).where(JobRun.job_id == backing_id)))
            if run_ids:
                session.execute(delete(JobLog).where(JobLog.job_run_id.in_(run_ids)))
                session.execute(delete(JobRun).where(JobRun.id.in_(run_ids)))
            job = session.get(Job, backing_id)
            if job is not None:
                session.delete(job)
        session.commit()
    return True


def list_snapshots(
    factory: sessionmaker[Session], *, dashboard_id: int, limit: int = 50
) -> list[dict[str, Any]]:
    """Return the dashboard's snapshots, newest first.

    Args:
        factory: SQLAlchemy session factory.
        dashboard_id: Owning dashboard's primary key.
        limit: Hard row cap.

    Returns:
        ``{"id", "captured_at", "triggered_by", "widget_count"}``
        dicts — the payload itself stays behind the detail endpoint.
    """
    with factory() as session:
        rows = list(
            session.scalars(
                select(BiDashboardSnapshot)
                .where(BiDashboardSnapshot.dashboard_id == dashboard_id)
                .order_by(BiDashboardSnapshot.captured_at.desc(), BiDashboardSnapshot.id.desc())
                .limit(limit)
            )
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            try:
                widget_count = len(json.loads(row.payload).get("widgets", []))
            except ValueError:
                widget_count = 0
            result.append(
                {
                    "id": row.id,
                    "captured_at": row.captured_at.isoformat() if row.captured_at else None,
                    "triggered_by": row.triggered_by,
                    "widget_count": widget_count,
                }
            )
    return result


def get_snapshot(
    factory: sessionmaker[Session], *, dashboard_id: int, snapshot_id: int
) -> BiDashboardSnapshot | None:
    """Return one snapshot of one dashboard, or ``None``.

    Args:
        factory: SQLAlchemy session factory.
        dashboard_id: Owning dashboard's primary key (guards against
            cross-dashboard snapshot ids in the URL).
        snapshot_id: Snapshot primary key.

    Returns:
        The detached row, or ``None`` when absent/mismatched.
    """
    with factory() as session:
        row = session.get(BiDashboardSnapshot, snapshot_id)
        if row is None or row.dashboard_id != dashboard_id:
            return None
        session.expunge(row)
    return row


def _run_widget_sql(
    sql: str,
    approved: dict[str, str],
    max_rows: int,
    policies: dict[str, Any] | None,
) -> Any:
    """Execute *sql* in the sync PQL bridge (dispatched via run_sync)."""
    from pointlessql.pql import PQL

    return PQL.sql(sql, approved_tables=approved, max_rows=max_rows, table_policies=policies)


async def _capture_widget(
    factory: sessionmaker[Session],
    widget: BiDashboardWidget,
    *,
    specs: list[dict[str, Any]],
    uc_client: UnityCatalogClient,
    actor_email: str,
    is_admin: bool,
) -> dict[str, Any]:
    """Run one widget and frame its payload entry.

    Every failure mode — unbound SQL, a missing parameter default, a
    privilege miss, an engine error — lands in the entry's ``error``
    field instead of propagating, so one broken widget never kills
    the whole capture.

    Args:
        factory: SQLAlchemy session factory.
        widget: The widget row to capture.
        specs: The dashboard's validated parameter specs (the capture
            substitutes each spec's default value).
        uc_client: UC facade for SELECT enforcement.
        actor_email: Principal the snapshot queries run as.
        is_admin: Whether that principal short-circuits privilege
            checks.

    Returns:
        One ``widgets[]`` entry of the snapshot payload.
    """
    entry: dict[str, Any] = {
        "widget_id": widget.id,
        "kind": widget.kind,
        "title": widget.title,
        "chart_spec": json.loads(widget.chart_spec or "{}"),
        "markdown": widget.markdown if widget.kind == "markdown" else None,
        "columns": None,
        "rows": None,
        "row_count": None,
        "truncated": None,
        "error": None,
    }
    if widget.kind == "markdown":
        return entry
    sql = bi_service.resolve_widget_sql(factory, widget=widget)
    if sql is None:
        entry["error"] = "widget has no SQL bound"
        return entry
    try:
        sql = bi_service.substitute_params(sql, specs=specs, values={})
        approved, policies = await resolve_select_context(
            sql, uc_client=uc_client, actor_email=actor_email, is_admin=is_admin
        )
        result = await run_sync(
            _run_widget_sql, sql, approved, _ROW_CAPS.get(widget.kind, 1_000), policies
        )
    except Exception as exc:  # noqa: BLE001 — per-widget isolation is the contract here
        entry["error"] = str(exc)
        return entry
    entry["columns"] = result.columns
    entry["rows"] = result.rows
    entry["row_count"] = result.row_count
    entry["truncated"] = result.truncated
    return entry


async def render_snapshot(
    factory: sessionmaker[Session],
    *,
    uc_client: UnityCatalogClient,
    dashboard_id: int,
    workspace_id: int,
    actor_email: str,
    is_admin: bool,
    triggered_by: str,
) -> int:
    """Capture every widget of a dashboard into one snapshot row.

    Widget SQL resolves exactly like the live view (inline text or
    saved-query reference, parameters substituted with their
    defaults) and runs under *actor_email*'s SELECT enforcement with
    the same per-kind row caps.  Failures are recorded per widget.

    Args:
        factory: SQLAlchemy session factory.
        uc_client: UC facade for SELECT enforcement.
        dashboard_id: Dashboard to capture.
        workspace_id: Tenant scope stamped on the snapshot row.
        actor_email: Principal the widget queries run as.
        is_admin: Whether that principal short-circuits privilege
            checks.
        triggered_by: ``"schedule"`` or ``"manual"``.

    Returns:
        The new snapshot row's primary key.

    Raises:
        ValidationError: When the dashboard does not exist.
    """
    with factory() as session:
        dashboard = session.get(BiDashboard, dashboard_id)
        if dashboard is None:
            raise ValidationError(f"dashboard id={dashboard_id} not found")
        title = dashboard.title
        specs: list[dict[str, Any]] = json.loads(dashboard.params or "[]")
    widgets = bi_service.list_widgets(factory, dashboard_id=dashboard_id)
    entries = [
        await _capture_widget(
            factory,
            widget,
            specs=specs,
            uc_client=uc_client,
            actor_email=actor_email,
            is_admin=is_admin,
        )
        for widget in widgets
    ]
    row = BiDashboardSnapshot(
        workspace_id=workspace_id,
        dashboard_id=dashboard_id,
        captured_at=_utcnow(),
        triggered_by=triggered_by,
        payload=json.dumps({"title": title, "widgets": entries}, default=str),
    )
    with factory() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        return int(row.id)


def build_snapshot_cloudevent(
    *,
    event_id: str,
    dashboard_slug: str,
    dashboard_title: str,
    snapshot_id: int,
    widget_count: int,
    captured_at: datetime.datetime,
) -> dict[str, Any]:
    """Build the CloudEvents 1.0 envelope for a captured snapshot.

    Args:
        event_id: Unique event id (uuid4 hex).
        dashboard_slug: The captured dashboard's slug.
        dashboard_title: The captured dashboard's title.
        snapshot_id: Primary key of the snapshot row.
        widget_count: Number of widget entries in the payload.
        captured_at: UTC timestamp of the capture.

    Returns:
        A dict ready to serialise onto the wire with
        ``Content-Type: application/cloudevents+json``.
    """
    iso = captured_at.astimezone(datetime.UTC).isoformat()
    return {
        "specversion": "1.0",
        "id": event_id,
        "source": f"/pointlessql/bi/{dashboard_slug}",
        "type": SNAPSHOT_CLOUDEVENT_TYPE,
        "time": iso,
        "datacontenttype": "application/json",
        "subject": dashboard_slug,
        "data": {
            "dashboard_slug": dashboard_slug,
            "dashboard_title": dashboard_title,
            "snapshot_id": snapshot_id,
            "widget_count": widget_count,
            "captured_at": iso,
            "url": f"/bi/{dashboard_slug}/snapshots/{snapshot_id}",
        },
    }


async def bi_snapshot_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Capture a scheduled dashboard snapshot and deliver it.

    Config shape: ``{"schedule_id": 42}``.  Runs the capture as the
    job's run-as user (the schedule creator), stamps the schedule's
    ``last_run_at``, then delivers: an in-app notification to the
    dashboard owner when ``deliver_inapp`` is set, and a signed
    CloudEvents POST when a ``webhook_url`` is configured.  A failed
    webhook delivery is logged but does not fail the run — the
    snapshot itself persisted.

    Args:
        job_run_id: Current run id (unused; the snapshot row carries
            the history).
        user_info: The run-as user; widget reads enforce against
            them.
        config: Must carry an integer ``schedule_id``.
        uc_client: Principal-forwarded facade for the enforcement
            hops.

    Raises:
        ValidationError: When ``schedule_id`` is missing or not an
            integer.
    """
    del job_run_id  # unused; the snapshot row carries the history
    from pointlessql.db import get_session_factory

    schedule_id = config.get("schedule_id")
    if not isinstance(schedule_id, int):
        raise ValidationError("bi_snapshot jobs need an integer schedule_id in config")
    factory = get_session_factory()
    with factory() as session:
        schedule = session.get(BiDashboardSchedule, schedule_id)
        if schedule is None or not schedule.is_active:
            return
        dashboard = session.get(BiDashboard, schedule.dashboard_id)
        if dashboard is None:
            return
        dashboard_id = schedule.dashboard_id
        workspace_id = int(schedule.workspace_id)
        deliver_inapp = bool(schedule.deliver_inapp)
        webhook_url = schedule.webhook_url
        webhook_hmac_secret = schedule.webhook_hmac_secret
        slug = dashboard.slug
        title = dashboard.title
        owner_id = int(dashboard.owner_id)

    snapshot_id = await render_snapshot(
        factory,
        uc_client=uc_client,
        dashboard_id=dashboard_id,
        workspace_id=workspace_id,
        actor_email=str(user_info.get("email") or ""),
        is_admin=bool(user_info.get("is_admin")),
        triggered_by="schedule",
    )

    with factory() as session:
        row = session.get(BiDashboardSchedule, schedule_id)
        if row is not None:
            row.last_run_at = _utcnow()
            session.commit()

    source_url = f"/bi/{slug}/snapshots/{snapshot_id}"
    if deliver_inapp:
        fanout_event(
            factory,
            event_type=SNAPSHOT_EVENT_TYPE,
            entity_kind="bi_dashboard",
            entity_ref=slug,
            workspace_id=workspace_id,
            actor_user_id=None,
            source_url=source_url,
            summary_md=f"Scheduled snapshot of **{title}** is ready.",
            extra_recipients=[owner_id],
        )
    if webhook_url:
        snapshot = get_snapshot(factory, dashboard_id=dashboard_id, snapshot_id=snapshot_id)
        widget_count = 0
        captured_at = _utcnow()
        if snapshot is not None:
            captured_at = snapshot.captured_at
            try:
                widget_count = len(json.loads(snapshot.payload).get("widgets", []))
            except ValueError:
                widget_count = 0
        envelope = build_snapshot_cloudevent(
            event_id=uuid4().hex,
            dashboard_slug=slug,
            dashboard_title=title,
            snapshot_id=snapshot_id,
            widget_count=widget_count,
            captured_at=captured_at,
        )
        delivered = await dispatch_webhook(webhook_url, envelope, hmac_secret=webhook_hmac_secret)
        if not delivered:
            logger.warning(
                "bi snapshot webhook delivery failed",
                extra={"dashboard_slug": slug, "snapshot_id": snapshot_id},
            )
