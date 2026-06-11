"""ORM-row serializers shared across the jobs_routes sub-package.

* :func:`serialize_job` + :func:`latest_run_per_job` build the
  job-row payload used by the list and detail endpoints.
* :func:`serialize_task` + :func:`serialize_task_run` cover the
  DAG-task introspection routes.
* :func:`serialize_run` covers individual run rows; re-exported by
  the package facade because :mod:`pointlessql.api.dashboards_routes`
  and :mod:`pointlessql.api.notebooks_routes.jobs` import it.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func


def serialize_job(job: Any, last_run: Any = None) -> dict[str, Any]:
    """Render a :class:`Job` ORM row for JSON responses.

    Pulled out into a helper so both the list and the detail route
    emit the same shape; the helper assumes the ORM row has been
    detached from its session or the caller still holds the session
    open (we never serialize half-loaded jobs).

    When *last_run* is supplied (typically from
    :func:`latest_run_per_job`), the ``last_run_*`` fields are
    populated from it; otherwise they are ``None``. List endpoints
    thread the latest-run map in, detail/mutation endpoints do not —
    the keys are always present so clients never need to branch on
    their existence.

    Args:
        job: Detached :class:`~pointlessql.models.Job` ORM row.
        last_run: Optional latest :class:`~pointlessql.models.JobRun`
            for this job, used to populate ``last_run_*`` fields.

    Returns:
        A dict with the canonical job shape plus ``last_run_status``,
        ``last_run_at``, and ``last_run_duration_s``.
    """
    last_status: str | None = None
    last_at: str | None = None
    last_duration: float | None = None
    if last_run is not None:
        last_status = last_run.status
        last_at = last_run.started_at.isoformat() if last_run.started_at else None
        if last_run.started_at and last_run.finished_at:
            last_duration = (last_run.finished_at - last_run.started_at).total_seconds()
    return {
        "id": job.id,
        "name": job.name,
        "cron_expr": job.cron_expr,
        "run_as_user_id": job.run_as_user_id,
        "kind": job.kind,
        "config": json.loads(job.config or "{}"),
        "is_paused": job.is_paused,
        "max_parallel_runs": job.max_parallel_runs,
        "on_failure_url": job.on_failure_url,
        "trigger_kind": job.trigger_kind,
        "trigger_config": json.loads(job.trigger_config or "{}"),
        "notify_on": json.loads(job.notify_on or "[]"),
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "last_run_status": last_status,
        "last_run_at": last_at,
        "last_run_duration_s": last_duration,
    }


def latest_run_per_job(session: Any, job_ids: list[int]) -> dict[int, Any]:
    """Fetch the most recent :class:`JobRun` row for each of *job_ids*.

    One round-trip: a ``group_by(job_id)`` subquery pulls the max
    ``started_at`` per job, then the outer select joins back to
    ``job_runs`` on both columns to grab the full row. Portable
    across SQLite and Postgres — no window functions, no lateral
    joins — and rides the existing ``(job_id, started_at)`` index
    declared on :class:`~pointlessql.models.JobRun`.

    Args:
        session: An open SQLAlchemy session.
        job_ids: The jobs whose latest run should be fetched. May be
            empty, in which case an empty dict is returned without
            issuing a query.

    Returns:
        A mapping from ``job_id`` to its most recent
        :class:`~pointlessql.models.JobRun`. Jobs with no runs yet are
        simply absent from the dict.
    """
    if not job_ids:
        return {}
    from sqlalchemy import and_
    from sqlalchemy import select as _select

    from pointlessql.models import JobRun as JobRunModel

    latest_sq = (
        _select(
            JobRunModel.job_id.label("job_id"),
            func.max(JobRunModel.started_at).label("last_at"),
        )
        .where(JobRunModel.job_id.in_(job_ids))
        .group_by(JobRunModel.job_id)
        .subquery()
    )
    stmt = _select(JobRunModel).join(
        latest_sq,
        and_(
            JobRunModel.job_id == latest_sq.c.job_id,
            JobRunModel.started_at == latest_sq.c.last_at,
        ),
    )
    out: dict[int, Any] = {}
    for run in session.scalars(stmt).all():
        # Two runs with identical started_at timestamps would both
        # satisfy the join; pick the higher-id one so a single row
        # wins deterministically.
        prev = out.get(run.job_id)
        if prev is None or run.id > prev.id:
            out[run.job_id] = run
    for run in out.values():
        session.expunge(run)
    return out


def serialize_task(task: Any) -> dict[str, Any]:
    """Render a :class:`JobTask` ORM row for JSON responses."""
    return {
        "id": task.id,
        "job_id": task.job_id,
        "name": task.name,
        "kind": task.kind,
        "config": json.loads(task.config or "{}"),
        "depends_on": json.loads(task.depends_on or "[]"),
        "max_retries": task.max_retries,
        "retry_backoff_seconds": task.retry_backoff_seconds,
        "run_if": task.run_if,
        "for_each": json.loads(task.for_each_json) if task.for_each_json else None,
    }


def serialize_task_run(tr: Any) -> dict[str, Any]:
    """Render a :class:`TaskRun` ORM row for JSON responses."""
    return {
        "id": tr.id,
        "job_run_id": tr.job_run_id,
        "task_id": tr.task_id,
        "status": tr.status,
        "started_at": tr.started_at.isoformat() if tr.started_at else None,
        "finished_at": tr.finished_at.isoformat() if tr.finished_at else None,
        "attempts": tr.attempts,
        "error": tr.error,
    }


def serialize_run(run: Any) -> dict[str, Any]:
    """Render a :class:`JobRun` ORM row for JSON responses."""
    duration: float | None = None
    if run.started_at and run.finished_at:
        duration = (run.finished_at - run.started_at).total_seconds()
    return {
        "id": run.id,
        "job_id": run.job_id,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "status": run.status,
        "trigger": run.trigger,
        "error": run.error,
        "repair_of_run_id": run.repair_of_run_id,
        "duration_seconds": duration,
    }
