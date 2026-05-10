"""Dashboards routes — publishing surface for notebook job output.

A dashboard is a stable slug-addressable view of a notebook job's
latest succeeded run, rendered with ``exclude_input=True`` so
consumers see outputs only.  The ``job_id`` FK is nullable so a
dashboard can outlive its bound job (FK uses ``ON DELETE SET
NULL``); when no job is bound or no successful run exists, the
detail page renders an empty state.

Visibility model: dashboards are visible to every logged-in user
(consumer-facing publishing surface).  Mutations + Refresh require
admin.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import get_user, require_admin
from pointlessql.api.jobs_routes import JOB_REGISTRY, serialize_run
from pointlessql.config import Settings
from pointlessql.exceptions import ValidationError
from pointlessql.services import notebook_render as notebook_render_service
from pointlessql.services import scheduler as scheduler_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboards"])

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,199}$")


def _templates(request: Request) -> Jinja2Templates:
    """Return the shared Jinja2Templates instance from app state."""
    return request.app.state.templates


def serialize_dashboard(
    dashboard: Any,
    *,
    latest_run_id: int | None = None,
) -> dict[str, Any]:
    """Render a :class:`Dashboard` ORM row for JSON + template responses."""
    return {
        "id": dashboard.id,
        "slug": dashboard.slug,
        "title": dashboard.title,
        "description": dashboard.description,
        "notebook_path": dashboard.notebook_path,
        "job_id": dashboard.job_id,
        "owner_id": dashboard.owner_id,
        "latest_run_id": latest_run_id,
        "created_at": dashboard.created_at.isoformat() if dashboard.created_at else None,
        "updated_at": dashboard.updated_at.isoformat() if dashboard.updated_at else None,
    }


def load_dashboard_or_404(request: Request, slug: str) -> Any:
    """Fetch a :class:`Dashboard` by slug; 404 when missing.

    Dashboards are visible to every logged-in user — they are the
    consumer-facing surface — so there is no per-user filter here.
    The admin gate lives on the mutating routes and on Refresh.
    """
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.models import Dashboard as DashboardModel

    factory = request.app.state.session_factory
    with factory() as session:
        from sqlalchemy import select as _select

        row = session.scalar(_select(DashboardModel).where(DashboardModel.slug == slug))
        if row is None:
            raise CatalogNotFoundError(f"Dashboard {slug!r} not found")
        session.expunge(row)
        return row


def latest_succeeded_run_id(request: Request, job_id: int) -> int | None:
    """Return the most recent succeeded :class:`JobRun` id for *job_id*.

    Used by the dashboard detail route to pick which run's output to
    render. ``None`` when the job has never produced a successful run.
    """
    from sqlalchemy import select as _select

    from pointlessql.models import JobRun as JobRunModel

    factory = request.app.state.session_factory
    with factory() as session:
        stmt = (
            _select(JobRunModel.id)
            .where(JobRunModel.job_id == job_id)
            .where(JobRunModel.status == "succeeded")
            .order_by(JobRunModel.started_at.desc())
            .limit(1)
        )
        return session.scalar(stmt)


@router.get("/api/dashboards")
async def api_list_dashboards(request: Request) -> list[dict[str, Any]]:
    """Return every dashboard in creation order (any logged-in user)."""
    from sqlalchemy import select as _select

    from pointlessql.models import Dashboard as DashboardModel

    factory = request.app.state.session_factory
    with factory() as session:
        stmt = _select(DashboardModel).order_by(DashboardModel.id)
        rows = list(session.scalars(stmt).all())
        for r in rows:
            session.expunge(r)
    return [serialize_dashboard(r) for r in rows]


@router.get("/api/dashboards/tree")
async def api_dashboards_tree(request: Request) -> list[dict[str, Any]]:
    """Return a flat list shaped for the dashboards sidebar component.

    The shape mirrors the workspace tree enough that the Alpine
    component is a straightforward copy.  ``/api/dashboards``
    already returns the same rows — the dedicated tree endpoint
    keeps the Alpine fetch call symmetrical with the catalog tree.
    """
    return await api_list_dashboards(request)


@router.post("/api/dashboards")
async def api_create_dashboard(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Create a new dashboard (admin-only)."""
    from pointlessql.models import Dashboard as DashboardModel

    require_admin(request)
    user = get_user(request)

    slug_raw = body.get("slug")
    title = body.get("title")
    notebook_path = body.get("notebook_path")
    if not slug_raw or not title or not notebook_path:
        raise ValidationError("slug, title and notebook_path are required")
    slug = str(slug_raw).strip()
    if not SLUG_PATTERN.match(slug):
        raise ValidationError("slug must be lowercase letters, digits and hyphens (1-200 chars)")

    description_raw = body.get("description")
    description: str | None = None
    if description_raw is not None:
        if not isinstance(description_raw, str):
            raise ValidationError("description must be a string when provided")
        description = description_raw.strip() or None

    job_id_raw = body.get("job_id")
    job_id: int | None = None
    if job_id_raw not in (None, ""):
        try:
            job_id = int(job_id_raw)
        except (TypeError, ValueError) as exc:
            raise ValidationError("job_id must be an integer") from exc

    now = datetime.now(UTC)
    factory = request.app.state.session_factory
    with factory() as session:
        from sqlalchemy import select as _select

        existing = session.scalar(_select(DashboardModel).where(DashboardModel.slug == slug))
        if existing is not None:
            raise ValidationError(f"dashboard slug {slug!r} already exists")

        dashboard = DashboardModel(
            slug=slug,
            title=str(title).strip(),
            description=description,
            notebook_path=str(notebook_path).strip(),
            job_id=job_id,
            owner_id=user["id"],
            created_at=now,
            updated_at=now,
        )
        session.add(dashboard)
        session.commit()
        session.refresh(dashboard)
        session.expunge(dashboard)
    await audit(request, "create_dashboard", f"dashboard:{slug}", json.dumps(body))
    return serialize_dashboard(dashboard)


@router.patch("/api/dashboards/{slug}")
async def api_update_dashboard(
    request: Request,
    slug: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Update mutable dashboard fields (admin-only).

    Editable: title, description, notebook_path, job_id. slug and
    owner_id are immutable — delete + recreate if the URL or owner
    needs to change so callers never observe a half-migrated row.
    """
    from pointlessql.models import Dashboard as DashboardModel

    require_admin(request)
    factory = request.app.state.session_factory
    with factory() as session:
        from sqlalchemy import select as _select

        row = session.scalar(_select(DashboardModel).where(DashboardModel.slug == slug))
        if row is None:
            from pointlessql.exceptions import CatalogNotFoundError as _NF

            raise _NF(f"Dashboard {slug!r} not found")

        if "title" in body:
            title = body["title"]
            if not isinstance(title, str) or not title.strip():
                raise ValidationError("title must be a non-empty string")
            row.title = title.strip()
        if "description" in body:
            desc = body["description"]
            if desc is not None and not isinstance(desc, str):
                raise ValidationError("description must be a string or null")
            row.description = desc.strip() if isinstance(desc, str) and desc.strip() else None
        if "notebook_path" in body:
            path = body["notebook_path"]
            if not isinstance(path, str) or not path.strip():
                raise ValidationError("notebook_path must be a non-empty string")
            row.notebook_path = path.strip()
        if "job_id" in body:
            jid = body["job_id"]
            if jid in (None, ""):
                row.job_id = None
            else:
                try:
                    row.job_id = int(jid)
                except (TypeError, ValueError) as exc:
                    raise ValidationError("job_id must be an integer or null") from exc
        row.updated_at = datetime.now(UTC)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    await audit(request, "update_dashboard", f"dashboard:{slug}", json.dumps(body))
    return serialize_dashboard(row)


@router.delete("/api/dashboards/{slug}")
async def api_delete_dashboard(request: Request, slug: str) -> dict[str, str]:
    """Delete a dashboard (admin-only)."""
    from pointlessql.models import Dashboard as DashboardModel

    require_admin(request)
    factory = request.app.state.session_factory
    with factory() as session:
        from sqlalchemy import select as _select

        row = session.scalar(_select(DashboardModel).where(DashboardModel.slug == slug))
        if row is None:
            from pointlessql.exceptions import CatalogNotFoundError as _NF

            raise _NF(f"Dashboard {slug!r} not found")
        session.delete(row)
        session.commit()
    await audit(request, "delete_dashboard", f"dashboard:{slug}")
    return {"status": "deleted", "slug": slug}


@router.post("/api/dashboards/{slug}/refresh")
async def api_refresh_dashboard(request: Request, slug: str) -> dict[str, Any]:
    """Trigger a manual run of the bound job (admin-only).

    Thin wrapper over the scheduler's manual-run helper that powers
    the job-detail "Run now" button — no new execution concept, just
    a shortcut for the dashboard consumer UI.
    """
    require_admin(request)
    dashboard = load_dashboard_or_404(request, slug)
    if dashboard.job_id is None:
        raise ValidationError("dashboard has no bound job to refresh")
    settings: Settings = request.app.state.settings
    factory = request.app.state.session_factory
    run = await scheduler_service.execute_run(
        factory,
        settings,
        JOB_REGISTRY,
        dashboard.job_id,
        "manual",
    )
    await audit(request, "refresh_dashboard", f"dashboard:{slug}")
    return serialize_run(run)


@router.get("/dashboards", response_class=HTMLResponse)
async def dashboards_index(request: Request) -> HTMLResponse:
    """Render the dashboards list page (any logged-in user)."""
    from sqlalchemy import select as _select

    from pointlessql.models import Dashboard as DashboardModel
    from pointlessql.models import Job as JobModel

    user = get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = _select(DashboardModel).order_by(DashboardModel.id)
        dashboards = list(session.scalars(stmt).all())
        for d in dashboards:
            session.expunge(d)
        # Admins can bind dashboards to any job; fetch the job list
        # once so the create modal's <select> doesn't need an extra
        # round-trip on open.
        job_options: list[dict[str, Any]] = []
        if user.get("is_admin"):
            for j in session.scalars(_select(JobModel).order_by(JobModel.name)).all():
                job_options.append({"id": j.id, "name": j.name, "kind": j.kind})
    return _templates(request).TemplateResponse(
        request,
        "pages/dashboards.html",
        {
            "dashboards": [serialize_dashboard(d) for d in dashboards],
            "is_admin": user.get("is_admin", False),
            "job_options": job_options,
            "active_page": "dashboards",
            "active_dashboard_slug": None,
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
            "list_page": True,
        },
    )


@router.get("/dashboards/{slug}", response_class=HTMLResponse)
async def dashboard_detail(request: Request, slug: str) -> HTMLResponse:
    """Render a dashboard's latest-run output (any logged-in user).

    The iframe src points at :func:`dashboard_output` so the visibility
    boundary is the dashboard itself, not the underlying job — dashboards
    are a consumer/publishing surface. When the bound job has never
    produced a succeeded run — or there is no bound job at all — the
    page renders an empty state instead.
    """
    user = get_user(request)
    dashboard = load_dashboard_or_404(request, slug)
    latest_run_id: int | None = None
    if dashboard.job_id is not None:
        latest_run_id = latest_succeeded_run_id(request, dashboard.job_id)
    return _templates(request).TemplateResponse(
        request,
        "pages/dashboard_detail.html",
        {
            "dashboard": serialize_dashboard(dashboard, latest_run_id=latest_run_id),
            "is_admin": user.get("is_admin", False),
            "active_page": "dashboards",
            "active_dashboard_slug": slug,
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@router.get("/dashboards/{slug}/output", response_class=HTMLResponse)
async def dashboard_output(request: Request, slug: str) -> HTMLResponse:
    """Render the code-hidden HTML of the dashboard's latest succeeded run.

    This is the iframe source for the dashboard detail page. Unlike
    :func:`job_run_notebook` it does **not** go through
    :func:`load_papermill_run_output_path` — which enforces
    admin-or-job-owner visibility — because dashboards are a
    consumer-facing publishing surface: any logged-in user who can see
    the dashboard metadata must be able to see the output it publishes.
    The visibility guard here is the dashboard's existence + a single
    internal check that the run belongs to the bound job.

    Args:
        request: Incoming FastAPI request; any logged-in user.
        slug: Dashboard slug from the URL path.

    Returns:
        HTMLResponse with the nbconvert code-hidden render.

    Raises:
        CatalogNotFoundError: When the dashboard doesn't exist, when it
            has no bound job, or when the bound job has no succeeded run.
    """
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.models import Job as JobModel
    from pointlessql.models import JobRun as JobRunModel

    dashboard = load_dashboard_or_404(request, slug)
    if dashboard.job_id is None:
        raise CatalogNotFoundError(f"Dashboard {slug!r} has no bound job")
    latest_run_id = latest_succeeded_run_id(request, dashboard.job_id)
    if latest_run_id is None:
        raise CatalogNotFoundError(f"Dashboard {slug!r} has no succeeded run yet")

    factory = request.app.state.session_factory
    with factory() as session:
        job = session.get(JobModel, dashboard.job_id)
        run = session.get(JobRunModel, latest_run_id)
        if job is None or run is None or run.job_id != dashboard.job_id:
            raise CatalogNotFoundError(f"Dashboard {slug!r} output not available")
        if job.kind != "papermill":
            raise CatalogNotFoundError(f"Dashboard {slug!r} bound job is not a papermill job")

    settings: Settings = request.app.state.settings
    runs_dir = settings.jupyter.runs_dir.resolve()
    html = notebook_render_service.render_run_notebook(runs_dir, latest_run_id, exclude_input=True)
    return HTMLResponse(html)
