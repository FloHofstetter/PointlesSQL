"""Job CRUD endpoints: list, create, run, pause, unpause.

These five endpoints all mutate or list the visible job set.  They
share the ``JOB_REGISTRY`` and the visibility/ownership helpers from
:mod:`._access`.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import get_user, require_admin
from pointlessql.api.jobs_routes._access import (
    JOB_REGISTRY,
    load_job_or_404,
    require_job_owner_or_admin,
)
from pointlessql.api.jobs_routes._serializers import (
    latest_run_per_job,
    serialize_job,
    serialize_run,
)
from pointlessql.config import Settings
from pointlessql.services import scheduler as scheduler_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jobs"])


@router.get("/api/jobs")
async def api_list_jobs(request: Request) -> list[dict[str, Any]]:
    """Return jobs visible to the current user.

    Admin sees everything; a regular user only sees jobs whose
    ``run_as_user_id`` matches their user id, matching the detail-page
    visibility so the two surfaces cannot drift.
    """
    from sqlalchemy import select as _select

    from pointlessql.models import Job as JobModel

    user = get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = _select(JobModel).order_by(JobModel.id)
        if not user.get("is_admin"):
            stmt = stmt.where(JobModel.run_as_user_id == user["id"])
        rows = list(session.scalars(stmt).all())
        latest = latest_run_per_job(session, [r.id for r in rows])
        for row in rows:
            session.expunge(row)
    return [serialize_job(r, last_run=latest.get(r.id)) for r in rows]


@router.post("/api/jobs")
async def api_create_job(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Create a new job (admin-only).

    Two shapes are accepted:

    * Single-task (legacy shape):
      ``{name, cron_expr, kind, config, ...}`` — the scheduler walks
      ``job.kind`` / ``job.config`` directly.
    * DAG:
      ``{name, cron_expr, tasks: [{name, kind, config, depends_on?,
      max_retries?, retry_backoff_seconds?}, ...], max_parallel_runs?}``.
      ``depends_on`` inside the payload references *task names* because
      the ids do not exist yet; the route resolves them to integer ids
      during insert and also validates the resulting graph is acyclic
      via :func:`pointlessql.services.scheduler.validate_dag` before
      committing so a bad payload never lands in the DB.

    ``run_as_user_id`` defaults to the caller so an admin scheduling a
    job for themselves does not have to look up their own id.
    """
    from croniter import croniter as _croniter

    from pointlessql.exceptions import ValidationError as _VE
    from pointlessql.models import Job as JobModel
    from pointlessql.models import JobTask as JobTaskModel

    require_admin(request)
    user = get_user(request)

    name = body.get("name")
    cron_expr = body.get("cron_expr")
    if not name or not cron_expr:
        raise _VE("name and cron_expr are required")
    if not _croniter.is_valid(str(cron_expr)):
        raise _VE(f"Invalid cron expression: {cron_expr!r}")

    tasks_payload = body.get("tasks")
    if tasks_payload is not None and not isinstance(tasks_payload, list):
        raise _VE("tasks must be a JSON array when provided")

    # Single-task shortcut: validate kind + config inline.
    if not tasks_payload:
        kind = body.get("kind")
        if not kind:
            raise _VE("kind is required when 'tasks' is not provided")
        JOB_REGISTRY.get(str(kind))
        config = body.get("config") or {}
        if not isinstance(config, dict):
            raise _VE("config must be a JSON object")
    else:
        kind = body.get("kind") or "python"  # placeholder on the Job row
        config = {}
        # Pre-flight each task entry so we fail fast before any INSERT.
        task_names: set[str] = set()
        for entry in tasks_payload:  # pyright: ignore[reportUnknownVariableType]
            if not isinstance(entry, dict):
                raise _VE("each task must be a JSON object")
            t_entry: dict[str, Any] = entry
            t_name = t_entry.get("name")
            t_kind = t_entry.get("kind")
            if not t_name or not t_kind:
                raise _VE("each task requires name and kind")
            if t_name in task_names:
                raise _VE(f"duplicate task name: {t_name!r}")
            task_names.add(str(t_name))
            JOB_REGISTRY.get(str(t_kind))
            t_config = t_entry.get("config") or {}
            if not isinstance(t_config, dict):
                raise _VE(f"task {t_name!r}: config must be a JSON object")
            t_deps = t_entry.get("depends_on") or []
            if not isinstance(t_deps, list):
                raise _VE(f"task {t_name!r}: depends_on must be a JSON array")

    run_as_user_id = int(body.get("run_as_user_id") or user["id"])
    is_paused = bool(body.get("is_paused", False))
    max_parallel_runs = int(body.get("max_parallel_runs") or 1)
    if max_parallel_runs < 1:
        raise _VE("max_parallel_runs must be >= 1")
    on_failure_url_raw = body.get("on_failure_url")
    on_failure_url: str | None = None
    if on_failure_url_raw is not None:
        if not isinstance(on_failure_url_raw, str) or not on_failure_url_raw.strip():
            raise _VE("on_failure_url must be a non-empty string when provided")
        on_failure_url = on_failure_url_raw.strip()

    now = datetime.now(UTC)
    factory = request.app.state.session_factory
    with factory() as session:
        job = JobModel(
            name=str(name),
            cron_expr=str(cron_expr),
            run_as_user_id=run_as_user_id,
            kind=str(kind),
            config=json.dumps(config),
            is_paused=is_paused,
            max_parallel_runs=max_parallel_runs,
            on_failure_url=on_failure_url,
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        # Flush-only, not commit: if DAG validation below fails, the
        # ``with factory() as session:`` context closes without commit
        # and the job row never lands in the DB.
        session.flush()

        if tasks_payload:
            # First pass: insert rows without depends_on so we learn ids.
            by_name: dict[str, JobTaskModel] = {}
            for order, entry in enumerate(tasks_payload):  # pyright: ignore[reportUnknownVariableType]
                if not isinstance(entry, dict):
                    continue
                t_entry: dict[str, Any] = entry
                jt = JobTaskModel(
                    job_id=job.id,
                    name=str(t_entry["name"]),
                    order=order,
                    kind=str(t_entry["kind"]),
                    config=json.dumps(t_entry.get("config") or {}),
                    depends_on="[]",
                    max_retries=int(t_entry.get("max_retries") or 0),
                    retry_backoff_seconds=int(t_entry.get("retry_backoff_seconds") or 0),
                )
                session.add(jt)
                session.flush()
                by_name[str(t_entry["name"])] = jt

            # Second pass: resolve depends_on names to ids.
            for entry in tasks_payload:  # pyright: ignore[reportUnknownVariableType]
                if not isinstance(entry, dict):
                    continue
                t_entry = entry
                t_name = str(t_entry["name"])
                deps_names = t_entry.get("depends_on") or []
                resolved: list[int] = []
                for dn in deps_names:  # pyright: ignore[reportUnknownVariableType]
                    if dn not in by_name:
                        raise _VE(f"task {t_name!r} depends on unknown task {dn!r}")
                    resolved.append(by_name[str(dn)].id)
                by_name[t_name].depends_on = json.dumps(resolved)

            # Validate the resulting graph is acyclic BEFORE committing
            # so a failed validation leaves no job or task rows behind.
            scheduler_service.validate_dag(list(by_name.values()))

        # All validation passed — commit job + tasks atomically.
        session.commit()
        session.refresh(job)
        session.expunge(job)
    # opportunistic notebook-job-link write. Lets the
    # editor's "Jobs of this notebook" panel look up the schedule
    # without scanning ``jobs.config`` JSON. Per-link rows are a
    # derived index — if writing fails or skips, the canonical truth
    # still lives in ``Job.config``.
    if str(kind) == "papermill" and isinstance(config, dict):
        nb_path = config.get("notebook_path")
        if isinstance(nb_path, str) and nb_path:
            from pointlessql.models import NotebookJobLink as _NJL

            with factory() as link_session:
                link_session.add(
                    _NJL(
                        workspace_id=1,
                        notebook_path=nb_path,
                        job_id=int(job.id),
                        created_at=now,
                    ),
                )
                link_session.commit()

    await audit(request, "create_job", f"job:{name}", json.dumps(body))
    return serialize_job(job)


@router.post("/api/jobs/{job_id}/run")
async def api_run_job(request: Request, job_id: int) -> dict[str, Any]:
    """Manually trigger a run of *job_id* (admin or owner only).

    Calls into the same :func:`scheduler_service.execute_run` path
    the cron tick uses, but stamps ``trigger="manual"`` so the run
    list can badge interactive launches separately from scheduled
    ones.  Records ``run_job`` in ``audit_log`` so a "why did this
    job run outside the schedule?" question has a tamper-evident
    answer.
    """
    job = load_job_or_404(request, job_id)
    require_job_owner_or_admin(request, job)
    settings: Settings = request.app.state.settings
    factory = request.app.state.session_factory
    run = await scheduler_service.execute_run(factory, settings, JOB_REGISTRY, job_id, "manual")
    await audit(request, "run_job", f"job:{job.name}")
    return serialize_run(run)


@router.post("/api/jobs/{job_id}/pause")
async def api_pause_job(request: Request, job_id: int) -> dict[str, Any]:
    """Pause *job_id* (admin or owner only).

    Flips ``Job.is_paused = True`` so the next scheduler tick
    skips the job; in-flight runs are not interrupted (paused is
    a "no new launches" flag, not a stop signal).  Audit-logs the
    transition so a paused production job leaves a tamper-evident
    record of who paused it and when.
    """
    from pointlessql.models import Job as JobModel

    job = load_job_or_404(request, job_id)
    require_job_owner_or_admin(request, job)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(JobModel, job_id)
        assert row is not None
        row.is_paused = True
        row.updated_at = datetime.now(UTC)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    await audit(request, "pause_job", f"job:{row.name}")
    return serialize_job(row)


@router.post("/api/jobs/{job_id}/unpause")
async def api_unpause_job(request: Request, job_id: int) -> dict[str, Any]:
    """Resume *job_id* (admin or owner only).

    Flips ``Job.is_paused = False`` so the next scheduler tick
    becomes eligible to launch a run.  Does not retroactively
    trigger missed cron ticks — only the next one matching the
    expression fires.  Audit-logs the resume so paired pause /
    resume events are visible together in ``audit_log``.
    """
    from pointlessql.models import Job as JobModel

    job = load_job_or_404(request, job_id)
    require_job_owner_or_admin(request, job)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(JobModel, job_id)
        assert row is not None
        row.is_paused = False
        row.updated_at = datetime.now(UTC)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    await audit(request, "unpause_job", f"job:{row.name}")
    return serialize_job(row)


