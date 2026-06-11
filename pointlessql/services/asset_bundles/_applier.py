"""Reconcile a :class:`BundleSpec` into the metadata DB, idempotently.

Each declared resource is upserted directly through the ORM: jobs by
name (tasks reconciled per name — missing created, present updated,
surplus deleted — with the DAG validated before commit), pipelines by
slug or title (datasets validated first), dashboards by slug.

Dashboard widgets belong entirely to the bundle: a managed
dashboard's widgets are matched per ``(kind, title)`` and any live
widget the spec does not declare is **deleted** on apply.  Manual
widget edits on a bundle-managed dashboard therefore do not survive
the next apply — declare them in the bundle instead.

Errors are scoped to the failing resource (an unknown ``run_as``
e-mail or an ambiguous widget match produces one error entry); the
remaining resources still apply.  Applying the same spec twice yields
an all-``unchanged`` second outcome.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import re

from sqlalchemy import select

from pointlessql.models import BiDashboard, BiDashboardWidget, Job, JobTask, Pipeline, User
from pointlessql.services.asset_bundles._planner import (
    desired_params,
    diff_dashboard,
    diff_job,
    diff_pipeline,
    find_pipeline,
    live_widgets_by_key,
    normalised_datasets,
)
from pointlessql.services.asset_bundles._spec import (
    BundleSpec,
    DashboardSpec,
    JobSpec,
    PipelineSpec,
    WidgetSpec,
)
from pointlessql.services.scheduler import validate_dag
from pointlessql.types import SessionFactory

_DEFAULT_POSITION: dict[str, int] = {"x": 0, "y": 0, "w": 6, "h": 4}


@dataclasses.dataclass(slots=True, frozen=True)
class ResourceResult:
    """Outcome of reconciling one declared resource.

    Attributes:
        resource_type: ``job`` / ``pipeline`` / ``dashboard``.
        identity: Spec-side identity of the resource.
        action: ``created`` / ``updated`` / ``unchanged`` / ``error``.
            On a dry run the verbs describe what *would* happen.
        error: Failure detail when ``action == "error"``.
    """

    resource_type: str
    identity: str
    action: str
    error: str | None = None


@dataclasses.dataclass(slots=True, frozen=True)
class BundleApplyOutcome:
    """Summary of one :func:`apply_bundle` call.

    Attributes:
        dry_run: True when no write happened.
        results: One :class:`ResourceResult` per declared resource.
    """

    dry_run: bool
    results: list[ResourceResult]

    def error_count(self) -> int:
        """Return the number of resources that failed."""
        return sum(1 for result in self.results if result.action == "error")

    def has_errors(self) -> bool:
        """Return True when at least one resource failed."""
        return self.error_count() > 0


def _utcnow() -> datetime.datetime:
    """Return the current UTC wall-clock."""
    return datetime.datetime.now(datetime.UTC)


def apply_bundle(
    session_factory: SessionFactory,
    *,
    spec: BundleSpec,
    workspace_id: int = 1,
    actor_user_id: int,
    actor_email: str,
    dry_run: bool = False,
) -> BundleApplyOutcome:
    """Reconcile *spec* into the DB; idempotent on repeat application.

    Args:
        session_factory: SQLAlchemy session factory for the metadata DB.
        spec: The parsed bundle.
        workspace_id: Workspace new resources are created in and
            pipelines / dashboards are matched within.
        actor_user_id: User id new pipelines / dashboards are owned by.
        actor_email: Apply principal — the default ``run_as`` for jobs
            that do not declare one.
        dry_run: When True, compute per-resource actions without
            writing.

    Returns:
        Per-resource results; errors are scoped to their resource.
    """
    results: list[ResourceResult] = []
    for job_spec in spec.jobs:
        results.append(
            _apply_job(
                session_factory,
                job_spec=job_spec,
                workspace_id=workspace_id,
                actor_email=actor_email,
                dry_run=dry_run,
            )
        )
    for pipeline_spec in spec.pipelines:
        results.append(
            _apply_pipeline(
                session_factory,
                pipeline_spec=pipeline_spec,
                workspace_id=workspace_id,
                actor_user_id=actor_user_id,
                dry_run=dry_run,
            )
        )
    for dashboard_spec in spec.dashboards:
        results.append(
            _apply_dashboard(
                session_factory,
                dashboard_spec=dashboard_spec,
                workspace_id=workspace_id,
                actor_user_id=actor_user_id,
                dry_run=dry_run,
            )
        )
    return BundleApplyOutcome(dry_run=dry_run, results=results)


_PLAN_TO_RESULT = {"create": "created", "update": "updated", "unchanged": "unchanged"}


def _apply_job(
    session_factory: SessionFactory,
    *,
    job_spec: JobSpec,
    workspace_id: int,
    actor_email: str,
    dry_run: bool,
) -> ResourceResult:
    """Upsert one job (with task reconciliation) and report the outcome."""
    try:
        run_as_email = job_spec.run_as or actor_email
        with session_factory() as session:
            run_as_user_id = session.scalar(select(User.id).where(User.email == run_as_email))
        if run_as_user_id is None:
            raise LookupError(f"run_as user {run_as_email!r} not found")
        entry = diff_job(session_factory, job_spec=job_spec)
        if entry.action != "unchanged" and not dry_run:
            _upsert_job(
                session_factory,
                job_spec=job_spec,
                workspace_id=workspace_id,
                run_as_user_id=int(run_as_user_id),
            )
        return ResourceResult(
            resource_type="job",
            identity=job_spec.name,
            action=_PLAN_TO_RESULT[entry.action],
        )
    except (ValueError, LookupError) as exc:
        return ResourceResult(
            resource_type="job", identity=job_spec.name, action="error", error=str(exc)
        )


def _upsert_job(
    session_factory: SessionFactory,
    *,
    job_spec: JobSpec,
    workspace_id: int,
    run_as_user_id: int,
) -> None:
    """Write the declared job + tasks; validates the DAG before commit."""
    now = _utcnow()
    with session_factory() as session:
        row = session.scalar(select(Job).where(Job.name == job_spec.name))
        if row is None:
            row = Job(
                workspace_id=workspace_id,
                name=job_spec.name,
                run_as_user_id=run_as_user_id,
                created_at=now,
            )
            session.add(row)
        elif job_spec.run_as is not None:
            row.run_as_user_id = run_as_user_id
        row.cron_expr = job_spec.effective_cron()
        row.kind = job_spec.effective_kind()
        row.config = json.dumps(job_spec.config)
        row.is_paused = job_spec.paused
        row.max_parallel_runs = job_spec.max_parallel_runs
        row.trigger_kind = job_spec.trigger_kind()
        row.trigger_config = json.dumps(job_spec.trigger_config())
        row.notify_on = json.dumps(job_spec.notify_on)
        row.updated_at = now
        session.flush()

        existing = {
            str(task.name): task
            for task in session.scalars(select(JobTask).where(JobTask.job_id == row.id))
        }
        spec_names = {task.name for task in job_spec.tasks}
        by_name: dict[str, JobTask] = {}
        for order, task_spec in enumerate(job_spec.tasks):
            task = existing.get(task_spec.name)
            if task is None:
                task = JobTask(
                    workspace_id=row.workspace_id,
                    job_id=row.id,
                    name=task_spec.name,
                )
                session.add(task)
            task.order = order
            task.kind = task_spec.kind
            task.config = json.dumps(task_spec.config)
            task.depends_on = "[]"
            task.max_retries = task_spec.max_retries
            task.retry_backoff_seconds = task_spec.retry_backoff_seconds
            task.run_if = task_spec.run_if
            task.for_each_json = (
                json.dumps(task_spec.for_each) if task_spec.for_each is not None else None
            )
            session.flush()
            by_name[task_spec.name] = task
        for task_spec in job_spec.tasks:
            resolved = [int(by_name[dep].id) for dep in task_spec.depends_on]
            by_name[task_spec.name].depends_on = json.dumps(resolved)
        for name, task in existing.items():
            if name not in spec_names:
                session.delete(task)
        session.flush()
        # An invalid graph raises before the commit below, so the
        # context manager closes without committing and no partial
        # job / task state lands in the DB.
        validate_dag(list(by_name.values()))
        session.commit()


def _apply_pipeline(
    session_factory: SessionFactory,
    *,
    pipeline_spec: PipelineSpec,
    workspace_id: int,
    actor_user_id: int,
    dry_run: bool,
) -> ResourceResult:
    """Upsert one pipeline and report the outcome."""
    identity = pipeline_spec.identity()
    try:
        entry = diff_pipeline(
            session_factory, pipeline_spec=pipeline_spec, workspace_id=workspace_id
        )
        if entry.action != "unchanged" and not dry_run:
            datasets = normalised_datasets(pipeline_spec)
            now = _utcnow()
            with session_factory() as session:
                row = find_pipeline(session, pipeline_spec=pipeline_spec, workspace_id=workspace_id)
                if row is None:
                    row = Pipeline(
                        workspace_id=workspace_id,
                        slug=pipeline_spec.slug or _deterministic_slug(pipeline_spec.title),
                        owner_id=actor_user_id,
                        created_at=now,
                    )
                    session.add(row)
                row.title = pipeline_spec.title
                row.description = pipeline_spec.description
                row.datasets = json.dumps(datasets)
                row.updated_at = now
                session.commit()
        return ResourceResult(
            resource_type="pipeline", identity=identity, action=_PLAN_TO_RESULT[entry.action]
        )
    except ValueError as exc:
        return ResourceResult(
            resource_type="pipeline", identity=identity, action="error", error=str(exc)
        )


def _deterministic_slug(title: str) -> str:
    """Derive a stable slug from *title* (no random suffix).

    Bundles need apply → export → apply to converge, so the random
    suffix the interactive pipeline CRUD uses is replaced by a plain
    normalisation.  Slugs are globally unique; a cross-workspace
    collision surfaces as a DB error on commit — declare an explicit
    ``slug`` in the spec to resolve it.
    """
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "pipeline"


def _apply_dashboard(
    session_factory: SessionFactory,
    *,
    dashboard_spec: DashboardSpec,
    workspace_id: int,
    actor_user_id: int,
    dry_run: bool,
) -> ResourceResult:
    """Upsert one dashboard (widgets fully reconciled) and report it."""
    try:
        entry = diff_dashboard(
            session_factory, dashboard_spec=dashboard_spec, workspace_id=workspace_id
        )
        if entry.action != "unchanged" and not dry_run:
            _upsert_dashboard(
                session_factory,
                dashboard_spec=dashboard_spec,
                workspace_id=workspace_id,
                actor_user_id=actor_user_id,
            )
        return ResourceResult(
            resource_type="dashboard",
            identity=dashboard_spec.slug,
            action=_PLAN_TO_RESULT[entry.action],
        )
    except ValueError as exc:
        return ResourceResult(
            resource_type="dashboard",
            identity=dashboard_spec.slug,
            action="error",
            error=str(exc),
        )


def _upsert_dashboard(
    session_factory: SessionFactory,
    *,
    dashboard_spec: DashboardSpec,
    workspace_id: int,
    actor_user_id: int,
) -> None:
    """Write the declared dashboard; surplus live widgets are deleted."""
    params = desired_params(dashboard_spec)
    now = _utcnow()
    with session_factory() as session:
        row = session.scalar(
            select(BiDashboard).where(
                BiDashboard.workspace_id == workspace_id,
                BiDashboard.slug == dashboard_spec.slug,
            )
        )
        if row is None:
            row = BiDashboard(
                workspace_id=workspace_id,
                slug=dashboard_spec.slug,
                owner_id=actor_user_id,
                created_at=now,
            )
            session.add(row)
        row.title = dashboard_spec.title
        row.description = dashboard_spec.description
        row.params = json.dumps(params)
        row.updated_at = now
        session.flush()

        by_key = live_widgets_by_key(
            session, dashboard_id=int(row.id), dashboard_slug=dashboard_spec.slug
        )
        spec_keys: set[tuple[str, str]] = set()
        for widget_spec in dashboard_spec.widgets:
            key = widget_spec.matching_key()
            spec_keys.add(key)
            widget = by_key.get(key)
            if widget is None:
                widget = BiDashboardWidget(
                    dashboard_id=row.id,
                    kind=widget_spec.kind,
                    title=widget_spec.title,
                    created_at=now,
                )
                session.add(widget)
            _write_widget_fields(widget, widget_spec, now)
        for key, widget in by_key.items():
            if key not in spec_keys:
                session.delete(widget)
        session.commit()


def _write_widget_fields(
    widget: BiDashboardWidget, widget_spec: WidgetSpec, now: datetime.datetime
) -> None:
    """Copy the declared widget fields onto the ORM row.

    ``chart_spec`` / ``position`` left out of the spec keep their live
    values (new widgets fall back to an empty spec and the standard
    grid rectangle).
    """
    widget.sql_text = widget_spec.sql if widget_spec.kind != "markdown" else None
    widget.markdown = widget_spec.markdown
    widget.saved_query_id = None
    if widget_spec.chart_spec is not None:
        widget.chart_spec = json.dumps(widget_spec.chart_spec)
    elif not widget.chart_spec:
        widget.chart_spec = "{}"
    if widget_spec.position is not None:
        widget.position = json.dumps(widget_spec.position)
    elif not widget.position:
        widget.position = json.dumps(_DEFAULT_POSITION)
    widget.updated_at = now
