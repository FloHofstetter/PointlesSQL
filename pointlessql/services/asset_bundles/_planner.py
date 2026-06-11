"""Diff a :class:`BundleSpec` against the live metadata DB.

One :class:`PlanEntry` per declared resource, keyed by its identity
(job name / pipeline slug-or-title / dashboard slug) with an action of
``create`` / ``update`` / ``unchanged`` and a human-readable change
list.  The planner never plans deletes — live resources absent from
the spec are reported informatively as :class:`OrphanEntry` rows.

The per-resource diff helpers are shared with the applier so the two
always agree on what "unchanged" means; that is what makes a second
``apply`` of the same spec a no-op.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from sqlalchemy import select

from pointlessql.models import BiDashboard, BiDashboardWidget, Job, JobTask, Pipeline, User
from pointlessql.services.asset_bundles._spec import (
    BundleSpec,
    DashboardSpec,
    JobSpec,
    PipelineSpec,
)
from pointlessql.services.bi_dashboards import validate_params
from pointlessql.services.pipelines import PipelineValidationError, validate_datasets
from pointlessql.types import SessionFactory


@dataclasses.dataclass(slots=True, frozen=True)
class PlanEntry:
    """One reconciliation decision for one declared resource.

    Attributes:
        resource_type: ``job`` / ``pipeline`` / ``dashboard``.
        identity: Spec-side identity (job name, pipeline slug or
            title, dashboard slug).
        action: ``create`` / ``update`` / ``unchanged``.
        changes: Human-readable field-level differences; empty for
            ``create`` and ``unchanged``.
    """

    resource_type: str
    identity: str
    action: str
    changes: list[str]


@dataclasses.dataclass(slots=True, frozen=True)
class OrphanEntry:
    """One live resource the spec does not mention (informative only).

    Attributes:
        resource_type: ``job`` / ``pipeline`` / ``dashboard``.
        identity: Live-side identity of the unmanaged resource.
    """

    resource_type: str
    identity: str


@dataclasses.dataclass(slots=True, frozen=True)
class BundlePlan:
    """The full diff for one bundle.

    Attributes:
        entries: One :class:`PlanEntry` per declared resource, in
            spec order (jobs, then pipelines, then dashboards).
        orphans: Live resources in the workspace that the spec does
            not declare.  Never acted on — deletes are out of scope.
    """

    entries: list[PlanEntry]
    orphans: list[OrphanEntry]

    def is_noop(self) -> bool:
        """Return True when every entry is ``unchanged``."""
        return all(entry.action == "unchanged" for entry in self.entries)


def plan_bundle(
    session_factory: SessionFactory,
    *,
    spec: BundleSpec,
    workspace_id: int = 1,
) -> BundlePlan:
    """Compute a :class:`BundlePlan` for *spec* against the live DB.

    Args:
        session_factory: SQLAlchemy session factory for the metadata DB.
        spec: The parsed bundle.
        workspace_id: Workspace scope for pipeline / dashboard lookup
            and the orphan listing.

    Returns:
        The per-resource plan plus the informative orphan list.
        A :class:`ValueError` propagates when a declared pipeline's
        datasets do not validate or a dashboard's live widgets are
        ambiguous under ``(kind, title)`` matching.
    """
    entries: list[PlanEntry] = []
    for job in spec.jobs:
        entries.append(diff_job(session_factory, job_spec=job))
    for pipeline in spec.pipelines:
        entries.append(
            diff_pipeline(session_factory, pipeline_spec=pipeline, workspace_id=workspace_id)
        )
    for dashboard in spec.dashboards:
        entries.append(
            diff_dashboard(session_factory, dashboard_spec=dashboard, workspace_id=workspace_id)
        )
    return BundlePlan(entries=entries, orphans=_orphans(session_factory, spec, workspace_id))


def _orphans(
    session_factory: SessionFactory, spec: BundleSpec, workspace_id: int
) -> list[OrphanEntry]:
    """List workspace resources the spec does not declare."""
    job_names = {j.name for j in spec.jobs}
    pipeline_ids = {p.identity() for p in spec.pipelines}
    dashboard_slugs = {d.slug for d in spec.dashboards}
    orphans: list[OrphanEntry] = []
    with session_factory() as session:
        for (name,) in session.execute(
            select(Job.name).where(Job.workspace_id == workspace_id).order_by(Job.name)
        ):
            if name not in job_names:
                orphans.append(OrphanEntry(resource_type="job", identity=str(name)))
        for slug, title in session.execute(
            select(Pipeline.slug, Pipeline.title)
            .where(Pipeline.workspace_id == workspace_id)
            .order_by(Pipeline.slug)
        ):
            if slug not in pipeline_ids and title not in pipeline_ids:
                orphans.append(OrphanEntry(resource_type="pipeline", identity=str(slug)))
        for (slug,) in session.execute(
            select(BiDashboard.slug)
            .where(BiDashboard.workspace_id == workspace_id)
            .order_by(BiDashboard.slug)
        ):
            if slug not in dashboard_slugs:
                orphans.append(OrphanEntry(resource_type="dashboard", identity=str(slug)))
    return orphans


def _note(changes: list[str], field: str, before: object, after: object) -> None:
    """Append a ``field: before -> after`` line when the values differ."""
    if before != after:
        changes.append(f"{field}: {before!r} -> {after!r}")


def diff_job(session_factory: SessionFactory, *, job_spec: JobSpec) -> PlanEntry:
    """Diff one declared job against the live row matched by name.

    Job names carry a global unique constraint, so matching ignores
    the workspace — re-declaring a name that exists in another
    workspace updates that job rather than colliding on insert.

    Args:
        session_factory: SQLAlchemy session factory.
        job_spec: The declared job.

    Returns:
        The plan entry for this job.
    """
    changes: list[str] = []
    with session_factory() as session:
        row = session.scalar(select(Job).where(Job.name == job_spec.name))
        if row is None:
            return PlanEntry(
                resource_type="job", identity=job_spec.name, action="create", changes=[]
            )
        _note(changes, "cron_expr", row.cron_expr, job_spec.effective_cron())
        _note(changes, "trigger_kind", row.trigger_kind, job_spec.trigger_kind())
        _note(
            changes,
            "trigger_config",
            json.loads(row.trigger_config or "{}"),
            job_spec.trigger_config(),
        )
        _note(changes, "kind", row.kind, job_spec.effective_kind())
        _note(changes, "config", json.loads(row.config or "{}"), job_spec.config)
        _note(changes, "paused", bool(row.is_paused), job_spec.paused)
        _note(changes, "max_parallel_runs", int(row.max_parallel_runs), job_spec.max_parallel_runs)
        _note(changes, "notify_on", json.loads(row.notify_on or "[]"), job_spec.notify_on)
        if job_spec.run_as is not None:
            current = session.scalar(select(User.email).where(User.id == row.run_as_user_id))
            _note(changes, "run_as", current, job_spec.run_as)
        _diff_tasks(session, row, job_spec, changes)
    action = "update" if changes else "unchanged"
    return PlanEntry(resource_type="job", identity=job_spec.name, action=action, changes=changes)


def _diff_tasks(session: Any, row: Job, job_spec: JobSpec, changes: list[str]) -> None:
    """Append task-level differences (added / changed / removed) for one job."""
    live = list(
        session.scalars(
            select(JobTask).where(JobTask.job_id == row.id).order_by(JobTask.order, JobTask.id)
        )
    )
    id_to_name = {int(t.id): str(t.name) for t in live}
    by_name = {str(t.name): t for t in live}
    spec_names = {t.name for t in job_spec.tasks}
    for order, task in enumerate(job_spec.tasks):
        existing = by_name.get(task.name)
        if existing is None:
            changes.append(f"task added: {task.name}")
            continue
        live_deps = sorted(
            id_to_name.get(int(dep), f"#{dep}") for dep in json.loads(existing.depends_on or "[]")
        )
        live_for_each = (
            json.loads(existing.for_each_json) if existing.for_each_json is not None else None
        )
        before = {
            "kind": existing.kind,
            "config": json.loads(existing.config or "{}"),
            "depends_on": live_deps,
            "max_retries": int(existing.max_retries),
            "retry_backoff_seconds": int(existing.retry_backoff_seconds),
            "run_if": existing.run_if,
            "for_each": live_for_each,
            "order": int(existing.order),
        }
        after = {
            "kind": task.kind,
            "config": task.config,
            "depends_on": sorted(task.depends_on),
            "max_retries": task.max_retries,
            "retry_backoff_seconds": task.retry_backoff_seconds,
            "run_if": task.run_if,
            "for_each": task.for_each,
            "order": order,
        }
        if before != after:
            changes.append(f"task changed: {task.name}")
    for name in by_name:
        if name not in spec_names:
            changes.append(f"task removed: {name}")


def normalised_datasets(pipeline_spec: PipelineSpec) -> list[dict[str, Any]]:
    """Run the pipeline CRUD's dataset validation on the spec's datasets.

    Args:
        pipeline_spec: The declared pipeline.

    Returns:
        The normalised dataset list (refs extracted, expectations
        validated) — the exact shape stored on ``Pipeline.datasets``.

    Raises:
        ValueError: When the datasets do not validate (bad target FQN,
            unknown kind, non-SELECT SQL, cyclic references, …).
    """
    try:
        return validate_datasets([d.model_dump() for d in pipeline_spec.datasets])
    except PipelineValidationError as exc:
        raise ValueError(f"pipeline {pipeline_spec.identity()!r}: {exc}") from exc


def find_pipeline(
    session: Any, *, pipeline_spec: PipelineSpec, workspace_id: int
) -> Pipeline | None:
    """Return the live pipeline matched by slug (or, lacking one, title)."""
    if pipeline_spec.slug:
        return session.scalar(
            select(Pipeline).where(
                Pipeline.workspace_id == workspace_id,
                Pipeline.slug == pipeline_spec.slug,
            )
        )
    return session.scalar(
        select(Pipeline)
        .where(
            Pipeline.workspace_id == workspace_id,
            Pipeline.title == pipeline_spec.title,
        )
        .order_by(Pipeline.id)
        .limit(1)
    )


def diff_pipeline(
    session_factory: SessionFactory, *, pipeline_spec: PipelineSpec, workspace_id: int
) -> PlanEntry:
    """Diff one declared pipeline against the live row.

    Args:
        session_factory: SQLAlchemy session factory.
        pipeline_spec: The declared pipeline.
        workspace_id: Workspace the pipeline lives in.

    Returns:
        The plan entry for this pipeline.  A :class:`ValueError`
        propagates when the declared datasets do not validate.
    """
    identity = pipeline_spec.identity()
    desired = normalised_datasets(pipeline_spec)
    changes: list[str] = []
    with session_factory() as session:
        row = find_pipeline(session, pipeline_spec=pipeline_spec, workspace_id=workspace_id)
        if row is None:
            return PlanEntry(
                resource_type="pipeline", identity=identity, action="create", changes=[]
            )
        _note(changes, "title", row.title, pipeline_spec.title)
        _note(changes, "description", row.description, pipeline_spec.description)
        if json.loads(row.datasets or "[]") != desired:
            changes.append("datasets")
    action = "update" if changes else "unchanged"
    return PlanEntry(resource_type="pipeline", identity=identity, action=action, changes=changes)


def live_widgets_by_key(
    session: Any, *, dashboard_id: int, dashboard_slug: str
) -> dict[tuple[str, str], BiDashboardWidget]:
    """Map a dashboard's live widgets by their ``(kind, title)`` key.

    Args:
        session: Open SQLAlchemy session.
        dashboard_id: The dashboard's primary key.
        dashboard_slug: Slug used in the ambiguity error message.

    Returns:
        ``(kind, title)`` → widget row map.

    Raises:
        ValueError: When two live widgets share a ``(kind, title)``
            pair — matching would be ambiguous.
    """
    rows = list(
        session.scalars(
            select(BiDashboardWidget)
            .where(BiDashboardWidget.dashboard_id == dashboard_id)
            .order_by(BiDashboardWidget.id)
        )
    )
    by_key: dict[tuple[str, str], BiDashboardWidget] = {}
    for widget in rows:
        key = (str(widget.kind), str(widget.title or ""))
        if key in by_key:
            raise ValueError(
                f"dashboard {dashboard_slug!r}: widget matching is ambiguous — two live "
                f"widgets share (kind, title) {key!r}; rename one before applying"
            )
        by_key[key] = widget
    return by_key


def _widget_changed(spec_widget: Any, row: BiDashboardWidget) -> bool:
    """Return True when the declared widget differs from the live row.

    ``chart_spec`` / ``position`` left out of the spec mean "keep the
    live value" and are not compared.
    """
    desired_sql = (spec_widget.sql or None) if spec_widget.kind != "markdown" else None
    if desired_sql != (row.sql_text or None):
        return True
    if (spec_widget.markdown or None) != (row.markdown or None):
        return True
    if row.saved_query_id is not None:
        return True
    if spec_widget.chart_spec is not None and spec_widget.chart_spec != json.loads(
        row.chart_spec or "{}"
    ):
        return True
    return spec_widget.position is not None and spec_widget.position != json.loads(
        row.position or "{}"
    )


def desired_params(dashboard_spec: DashboardSpec) -> list[dict[str, Any]]:
    """Return the normalised parameter list the dashboard should carry.

    Args:
        dashboard_spec: The declared dashboard.

    Returns:
        The list in the exact shape stored on ``BiDashboard.params``.
        The validator's :class:`ValueError` propagates on a malformed
        list.
    """
    return validate_params([p.model_dump() for p in dashboard_spec.params])


def diff_dashboard(
    session_factory: SessionFactory, *, dashboard_spec: DashboardSpec, workspace_id: int
) -> PlanEntry:
    """Diff one declared dashboard (including widgets) against the live row.

    Args:
        session_factory: SQLAlchemy session factory.
        dashboard_spec: The declared dashboard.
        workspace_id: Workspace the dashboard lives in.

    Returns:
        The plan entry for this dashboard.  A :class:`ValueError`
        propagates when the parameter list does not validate or live
        widget matching is ambiguous.
    """
    changes: list[str] = []
    params = desired_params(dashboard_spec)
    with session_factory() as session:
        row = session.scalar(
            select(BiDashboard).where(
                BiDashboard.workspace_id == workspace_id,
                BiDashboard.slug == dashboard_spec.slug,
            )
        )
        if row is None:
            return PlanEntry(
                resource_type="dashboard",
                identity=dashboard_spec.slug,
                action="create",
                changes=[],
            )
        _note(changes, "title", row.title, dashboard_spec.title)
        _note(changes, "description", row.description, dashboard_spec.description)
        if json.loads(row.params or "[]") != params:
            changes.append("params")
        by_key = live_widgets_by_key(
            session, dashboard_id=int(row.id), dashboard_slug=dashboard_spec.slug
        )
        spec_keys: set[tuple[str, str]] = set()
        for widget in dashboard_spec.widgets:
            key = widget.matching_key()
            spec_keys.add(key)
            live = by_key.get(key)
            if live is None:
                changes.append(f"widget added: {key[0]}:{key[1]}")
            elif _widget_changed(widget, live):
                changes.append(f"widget changed: {key[0]}:{key[1]}")
        for key in by_key:
            if key not in spec_keys:
                changes.append(f"widget removed: {key[0]}:{key[1]}")
    action = "update" if changes else "unchanged"
    return PlanEntry(
        resource_type="dashboard", identity=dashboard_spec.slug, action=action, changes=changes
    )
