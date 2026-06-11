"""Snapshot live jobs / pipelines / dashboards into a :class:`BundleSpec`.

The export is round-trippable: planning the exported spec against the
same DB yields an all-``unchanged`` plan.  One deliberate exception —
a dashboard widget backed by a saved query is exported with the
query's SQL inlined (the bundle format only carries inline SQL), so
applying such an export converts the widget to an inline-SQL widget.
"""

from __future__ import annotations

import json
from typing import Any

import yaml
from sqlalchemy import select

from pointlessql.models import BiDashboard, BiDashboardWidget, Job, JobTask, Pipeline, User
from pointlessql.models.catalog import SavedQuery
from pointlessql.services.asset_bundles._spec import (
    EVENT_CRON_SENTINEL,
    BundleInfo,
    BundleSpec,
    DashboardParamSpec,
    DashboardSpec,
    DatasetSpec,
    ExpectationSpec,
    JobSpec,
    JobTaskSpec,
    JobTriggerSpec,
    PipelineSpec,
    WidgetSpec,
)
from pointlessql.types import SessionFactory


def export_bundle(
    session_factory: SessionFactory,
    *,
    workspace_id: int = 1,
    jobs: list[str] | None = None,
    pipelines: list[str] | None = None,
    dashboards: list[str] | None = None,
    name: str = "exported-bundle",
) -> BundleSpec:
    """Return a :class:`BundleSpec` snapshotting the selected resources.

    Args:
        session_factory: SQLAlchemy session factory for the metadata DB.
        workspace_id: Workspace scope of the export.
        jobs: Job names to include — ``None`` exports all, an empty
            list exports none.
        pipelines: Pipeline slugs to include — same ``None`` / empty
            semantics.
        dashboards: Dashboard slugs to include — same semantics.
        name: Bundle header name stamped on the export.

    Returns:
        A validated bundle spec ready for :func:`bundle_to_yaml`.
    """
    with session_factory() as session:
        job_specs = _export_jobs(session, workspace_id=workspace_id, names=jobs)
        pipeline_specs = _export_pipelines(session, workspace_id=workspace_id, slugs=pipelines)
        dashboard_specs = _export_dashboards(session, workspace_id=workspace_id, slugs=dashboards)
    return BundleSpec(
        bundle=BundleInfo(name=name),
        jobs=job_specs,
        pipelines=pipeline_specs,
        dashboards=dashboard_specs,
    )


def bundle_to_yaml(spec: BundleSpec) -> str:
    """Render *spec* as YAML (insertion order kept, ``None`` fields omitted).

    Args:
        spec: The bundle to serialise.

    Returns:
        YAML text accepted verbatim by
        :func:`pointlessql.services.asset_bundles.parse_bundle`.
    """
    return yaml.safe_dump(spec.model_dump(exclude_none=True), sort_keys=False)


def _export_jobs(session: Any, *, workspace_id: int, names: list[str] | None) -> list[JobSpec]:
    """Snapshot the workspace's jobs (filtered by *names* when given)."""
    if names is not None and not names:
        return []
    stmt = select(Job).where(Job.workspace_id == workspace_id).order_by(Job.name)
    if names is not None:
        stmt = stmt.where(Job.name.in_(names))
    specs: list[JobSpec] = []
    for row in session.scalars(stmt):
        trigger_config = json.loads(row.trigger_config or "{}")
        trigger: JobTriggerSpec | None = None
        cron: str | None = row.cron_expr
        if row.trigger_kind != "cron":
            trigger = JobTriggerSpec(
                kind=str(row.trigger_kind),
                path=trigger_config.get("path"),
                table=trigger_config.get("table"),
            )
            cron = None
        elif cron == EVENT_CRON_SENTINEL:
            cron = None
        run_as = session.scalar(select(User.email).where(User.id == row.run_as_user_id))
        specs.append(
            JobSpec(
                name=str(row.name),
                cron=cron,
                kind=str(row.kind),
                config=json.loads(row.config or "{}"),
                paused=bool(row.is_paused),
                max_parallel_runs=int(row.max_parallel_runs),
                trigger=trigger,
                notify_on=json.loads(row.notify_on or "[]"),
                run_as=run_as,
                tasks=_export_tasks(session, job_id=int(row.id)),
            )
        )
    return specs


def _export_tasks(session: Any, *, job_id: int) -> list[JobTaskSpec]:
    """Snapshot one job's DAG tasks with ``depends_on`` ids back to names."""
    rows = list(
        session.scalars(
            select(JobTask).where(JobTask.job_id == job_id).order_by(JobTask.order, JobTask.id)
        )
    )
    id_to_name = {int(task.id): str(task.name) for task in rows}
    return [
        JobTaskSpec(
            name=str(task.name),
            kind=str(task.kind),
            config=json.loads(task.config or "{}"),
            depends_on=[
                id_to_name[int(dep)]
                for dep in json.loads(task.depends_on or "[]")
                if int(dep) in id_to_name
            ],
            max_retries=int(task.max_retries),
            retry_backoff_seconds=int(task.retry_backoff_seconds),
            run_if=str(task.run_if),
            for_each=(json.loads(task.for_each_json) if task.for_each_json is not None else None),
        )
        for task in rows
    ]


def _export_pipelines(
    session: Any, *, workspace_id: int, slugs: list[str] | None
) -> list[PipelineSpec]:
    """Snapshot the workspace's pipelines (filtered by *slugs* when given)."""
    if slugs is not None and not slugs:
        return []
    stmt = select(Pipeline).where(Pipeline.workspace_id == workspace_id).order_by(Pipeline.slug)
    if slugs is not None:
        stmt = stmt.where(Pipeline.slug.in_(slugs))
    specs: list[PipelineSpec] = []
    for row in session.scalars(stmt):
        specs.append(
            PipelineSpec(
                slug=str(row.slug),
                title=str(row.title),
                description=row.description,
                datasets=[_dataset_spec(entry) for entry in json.loads(row.datasets or "[]")],
            )
        )
    return specs


def _dataset_spec(entry: dict[str, Any]) -> DatasetSpec:
    """Rebuild one stored dataset dict as a spec (``refs`` are derived, not exported)."""
    expectations: list[dict[str, Any]] = list(entry.get("expectations") or [])
    return DatasetSpec(
        name=str(entry.get("name", "")),
        kind=str(entry.get("kind", "")),
        sql=str(entry.get("sql", "")),
        expectations=[
            ExpectationSpec(
                name=str(expectation.get("name", "")),
                constraint=str(expectation.get("constraint", "")),
                action=str(expectation.get("action", "warn")),
            )
            for expectation in expectations
        ],
    )


def _export_dashboards(
    session: Any, *, workspace_id: int, slugs: list[str] | None
) -> list[DashboardSpec]:
    """Snapshot the workspace's dashboards (filtered by *slugs* when given)."""
    if slugs is not None and not slugs:
        return []
    stmt = (
        select(BiDashboard)
        .where(BiDashboard.workspace_id == workspace_id)
        .order_by(BiDashboard.slug)
    )
    if slugs is not None:
        stmt = stmt.where(BiDashboard.slug.in_(slugs))
    specs: list[DashboardSpec] = []
    for row in session.scalars(stmt):
        widgets = [
            _export_widget(session, widget)
            for widget in session.scalars(
                select(BiDashboardWidget)
                .where(BiDashboardWidget.dashboard_id == row.id)
                .order_by(BiDashboardWidget.id)
            )
        ]
        specs.append(
            DashboardSpec(
                slug=str(row.slug),
                title=str(row.title),
                description=row.description,
                params=[
                    DashboardParamSpec(
                        name=str(param.get("name", "")),
                        label=param.get("label"),
                        type=str(param.get("type", "string")),
                        default=param.get("default"),
                    )
                    for param in json.loads(row.params or "[]")
                ],
                widgets=widgets,
            )
        )
    return specs


def _export_widget(session: Any, widget: BiDashboardWidget) -> WidgetSpec:
    """Snapshot one widget; saved-query references are inlined as SQL."""
    sql = widget.sql_text
    if widget.kind != "markdown" and not (sql or "").strip() and widget.saved_query_id is not None:
        saved = session.get(SavedQuery, widget.saved_query_id)
        sql = saved.sql_text if saved is not None else None
    chart_spec = json.loads(widget.chart_spec or "{}") or None
    position = json.loads(widget.position or "{}") or None
    return WidgetSpec(
        kind=str(widget.kind),
        title=widget.title,
        sql=sql if widget.kind != "markdown" else None,
        markdown=widget.markdown,
        chart_spec=chart_spec,
        position=position,
    )
