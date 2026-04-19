"""FastAPI entrypoint for PointlesSQL."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.responses import (
    HTMLResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pointlessql.api.alerts_routes import router as alerts_router
from pointlessql.api.auth_routes import router as auth_router
from pointlessql.api.catalog_routes import router as catalog_router
from pointlessql.api.dashboards_routes import router as dashboards_router
from pointlessql.api.dependencies import (
    get_uc_client as _get_uc_client,
)
from pointlessql.api.dependencies import (
    get_user as _get_user,
)
from pointlessql.api.dependencies import (
    require_admin as _require_admin,
)
from pointlessql.api.federation_routes import router as federation_router
from pointlessql.api.governance_routes import router as governance_router
from pointlessql.api.jobs_routes import (
    router as jobs_router,
)
from pointlessql.api.middleware import register_middleware
from pointlessql.api.notebook_kernel_ws import router as notebook_ws_router
from pointlessql.api.notebooks_routes import router as notebooks_router
from pointlessql.api.queries_routes import router as queries_router
from pointlessql.api.sql_routes import router as sql_router
from pointlessql.api.volumes_routes import (
    DELTA_PRIMITIVE_TO_UC as _DELTA_PRIMITIVE_TO_UC,  # noqa: F401  # pyright: ignore[reportUnusedImport]
)
from pointlessql.api.volumes_routes import (
    delta_field_to_uc as _delta_field_to_uc,  # noqa: F401  # pyright: ignore[reportUnusedImport]
)
from pointlessql.api.volumes_routes import (
    router as volumes_router,
)
from pointlessql.db import get_session_factory, init_db
from pointlessql.exceptions import (
    CatalogUnavailableError,
    PointlessSQLError,
)
from pointlessql.logging_config import configure_logging
from pointlessql.services import audit as audit_service
from pointlessql.services import kernel_session as kernel_session_service
from pointlessql.services import metrics as metrics_service
from pointlessql.services import notebook_workspace as notebook_workspace_service
from pointlessql.services import pg_sync as pg_sync_service
from pointlessql.services import scheduler as scheduler_service
from pointlessql.services.authorization import (
    MANAGE_GRANTS,
    SELECT,
    USE_CATALOG,
    USE_SCHEMA,
    check_privilege_from_effective,
    has_privilege,
)
from pointlessql.services.soyuz_client import make_soyuz_client
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.settings import Settings
from pointlessql.types import UserInfo

# Configure logging at module import time so it takes effect in every
# process that serves traffic — the uvicorn --reload worker imports
# this module but does not go through cli(). Idempotent; subsequent
# calls replace our own handlers without disturbing pytest's caplog.
_startup_settings = Settings()
configure_logging(_startup_settings.logging.level, _startup_settings.logging.format)

logger = logging.getLogger(__name__)

# In a dev checkout the frontend dir is at the repo root; in an
# installed wheel hatchling force-includes it as pointlessql/_frontend.
_dev_dir = Path(__file__).resolve().parents[2] / "frontend"
_FRONTEND_DIR = _dev_dir if _dev_dir.is_dir() else Path(__file__).resolve().parents[1] / "_frontend"
_TEMPLATES = Jinja2Templates(directory=str(_FRONTEND_DIR / "templates"))


def _format_epoch_ms(value: Any) -> str:
    """Format Unity Catalog epoch-millisecond timestamps as a local datetime."""
    if value is None:
        return "—"
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    except TypeError, ValueError:
        return str(value)


_TEMPLATES.env.filters["epoch_ms"] = _format_epoch_ms


_original_template_response = _TEMPLATES.TemplateResponse


def _template_response_with_user(request: Request, *args: Any, **kwargs: Any) -> Response:
    """Wrap TemplateResponse to inject ``current_user`` into every context."""
    # TemplateResponse(request, name, context) or (name, context, request=request)
    # Starlette 0.37+ signature: TemplateResponse(request, name, context={}, ...)
    if "context" in kwargs:
        kwargs["context"].setdefault("current_user", getattr(request.state, "user", None))
    elif len(args) >= 2 and isinstance(args[1], dict):
        mutable = list(args)
        mutable[1].setdefault("current_user", getattr(request.state, "user", None))
        args = tuple(mutable)
    return _original_template_response(request, *args, **kwargs)


_TEMPLATES.TemplateResponse = _template_response_with_user  # type: ignore[assignment]


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create shared services and manage the Jupyter subprocess."""
    settings = Settings()
    logger.info(
        "PointlesSQL starting on %s:%d (engine=%s, log_format=%s)",
        settings.server.host,
        settings.server.port,
        settings.delta.engine,
        settings.logging.format,
    )
    soyuz = make_soyuz_client(settings)
    app.state.uc_client = UnityCatalogClient(soyuz)
    app.state.settings = settings
    app.state.templates = _TEMPLATES

    init_db(settings.db.url)
    app.state.session_factory = get_session_factory()

    scheduler: scheduler_service.Scheduler | None = None
    if settings.scheduler.enabled:
        scheduler = scheduler_service.Scheduler(app.state.session_factory, settings)
        scheduler.start()
    app.state.scheduler = scheduler

    # Sprint 48: periodic audit-log retention sweep. Runs on its own
    # tick cadence (``audit.cleanup_interval_seconds``) so it does
    # not compete with the job scheduler; swallows its own errors
    # via ``cleanup_old_entries`` so a transient DB hiccup never
    # takes the lifespan down.
    audit_task = asyncio.create_task(
        _audit_retention_loop(app.state.session_factory, settings),
        name="audit-retention",
    )

    kernel_registry = kernel_session_service.KernelRegistry(
        settings.jupyter.notebooks_dir.resolve()
    )
    app.state.kernel_registry = kernel_registry

    # Sprint 63: the embedded JupyterLab subprocess is retired.  The
    # native Phase-12.6 editor + per-notebook ipykernel registry
    # (Sprint 59) serve every notebook-facing use case; papermill
    # spawns its own kernel per run.  Nothing else to start here.
    try:
        yield
    finally:
        audit_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await audit_task
        if scheduler is not None:
            await scheduler.stop()
        await kernel_registry.shutdown_all()
        await app.state.uc_client.aclose()


async def _audit_retention_loop(
    factory: Any,
    settings: Settings,
) -> None:
    """Run ``cleanup_old_entries`` on a fixed cadence for the lifetime of the app.

    A separate task rather than a scheduler-kind keeps the
    cleanup path independent of the job scheduler — operators who
    disable the scheduler (``POINTLESSQL_SCHEDULER_ENABLED=false``)
    still want retention to run.

    Args:
        factory: SQLAlchemy session factory shared with the rest
            of the app.
        settings: Snapshotted :class:`Settings` — only
            ``audit.retention_days`` and
            ``audit.cleanup_interval_seconds`` are read.
    """
    interval = max(60, settings.audit.cleanup_interval_seconds)
    retention = settings.audit.retention_days
    while True:
        try:
            await asyncio.to_thread(
                audit_service.cleanup_old_entries, factory, retention
            )
        except Exception:  # noqa: BLE001 — retention loop must survive everything
            logger.exception("audit: retention loop tick raised")
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return


app = FastAPI(title="PointlesSQL", version="0.1.0", lifespan=_lifespan)

from pointlessql.api.error_handlers import register_error_handlers  # noqa: E402

register_error_handlers(app)

app.include_router(auth_router)
app.include_router(catalog_router)
app.include_router(sql_router)
app.include_router(queries_router)
app.include_router(alerts_router)
app.include_router(volumes_router)
app.include_router(governance_router)
app.include_router(notebooks_router)
app.include_router(notebook_ws_router)
app.include_router(federation_router)
app.include_router(jobs_router)
app.include_router(dashboards_router)
app.mount(
    "/static",
    StaticFiles(directory=str(_FRONTEND_DIR)),
    name="static",
)

register_middleware(app)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Return service health."""
    return {"status": "ok"}


@app.get("/metrics")
async def metrics(request: Request) -> Response:
    """Expose Prometheus metrics for the scheduler (admin-only).

    Returns the default text exposition format so any Prometheus
    scraper works without extra negotiation. Gated by
    :func:`_require_admin` because the metrics surface includes the
    names of every job in the install, which is sensitive information
    on multi-tenant deployments.
    """
    _require_admin(request)
    body, content_type = metrics_service.render_metrics()
    return Response(content=body, media_type=content_type)


# -- JSON API routes --
# Exceptions propagate to the centralized handler in error_handlers.py.
# Catalog tree routes (/api/tree, /api/catalogs, /api/catalogs/.../schemas,
# .../tables, .../preview) live in api/catalog_routes.py since Sprint 86.
# SQL editor routes (/api/sql/execute*, /sql) live in api/sql_routes.py since Sprint 86b.
# Query history + saved-queries routes (/api/queries*, /queries,
# /api/saved-queries*) live in api/queries_routes.py since Sprint 86c.

# Alerts CRUD + feed routes (/api/alerts*, /api/me/feed-token*,
# /alerts/feed.atom|.json, /alerts, /alerts/{slug}) live in api/alerts_routes.py since Sprint 87.


# UC volumes routes (/api/volumes/*, /volumes, /volumes/{full_name})
# live in api/volumes_routes.py since Sprint 87b.


# Governance routes (table profile/stats, open-in-notebook, catalog
# create/sync/patch, schema patch, tags, permissions, effective
# permissions, lineage) live in api/governance_routes.py since Sprint 87c.


# -- HTML pages --


@app.get("/", response_class=HTMLResponse)
async def catalogs_index(request: Request) -> HTMLResponse:
    """Render the home dashboard.

    Assembles every server-side card (catalog count, recent job runs,
    7-day sparkline, dashboards owned by the user, onboarding
    checklist) through :func:`_build_home_summary` so the first-paint
    payload matches exactly what ``/api/home/summary`` would return.
    Admins additionally get the connections list so the "Create
    foreign catalog" modal has a pre-populated dropdown.
    """
    user = _get_user(request)
    summary = await _build_home_summary(request, user)
    connections: list[dict[str, Any]] = []
    if user.get("is_admin") and not summary["catalogs"]["unavailable"]:
        try:
            connections = await _get_uc_client(request).list_connections()
        except CatalogUnavailableError:
            logger.warning("home: soyuz connections list unavailable", exc_info=True)
    return _TEMPLATES.TemplateResponse(
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
        },
    )


@app.get("/catalogs/{catalog_name}", response_class=HTMLResponse)
async def catalog_detail(request: Request, catalog_name: str) -> HTMLResponse:
    """Render metadata for a single catalog."""
    client = _get_uc_client(request)
    user = _get_user(request)
    catalog: dict[str, Any] | None = None
    tags: list[dict[str, Any]] = []
    permissions: list[dict[str, Any]] = []
    effective: list[dict[str, Any]] = []
    schemas: list[dict[str, Any]] = []
    error: str | None = None
    try:
        catalog, tags, permissions, effective, schemas = await asyncio.gather(
            client.get_catalog(catalog_name),
            client.get_tags("catalog", catalog_name),
            client.get_permissions("catalog", catalog_name),
            client.get_effective_permissions("catalog", catalog_name),
            client.list_schemas(catalog_name),
        )
    except CatalogUnavailableError as exc:
        error = exc.detail

    # Enforce after gather so we reuse the effective permissions data.
    # AuthorizationError propagates to the centralized handler → 403.html.
    if error is None:
        check_privilege_from_effective(
            effective,
            user.get("email", ""),
            user.get("is_admin", False),
            "catalog",
            catalog_name,
            USE_CATALOG,
        )

    can_manage = has_privilege(
        effective,
        user.get("email", ""),
        user.get("is_admin", False),
        MANAGE_GRANTS,
    )

    # Load sync history for foreign catalogs so the history card has
    # something to render. Managed catalogs never sync, so we skip the
    # DB hit entirely.
    sync_runs: list[Any] = []
    if (
        error is None
        and catalog is not None
        and catalog.get("connection_name")
        and user.get("is_admin", False)
    ):
        factory = getattr(request.app.state, "session_factory", None)
        if factory is not None:
            sync_runs = pg_sync_service.list_recent_runs(factory, catalog_name)

    return _TEMPLATES.TemplateResponse(
        request,
        "pages/schemas.html",
        {
            "catalog_name": catalog_name,
            "catalog": catalog,
            "tags": tags,
            "permissions": permissions,
            "effective": effective,
            "can_manage": can_manage,
            "sync_runs": sync_runs,
            "schemas": schemas,
            "is_admin": user.get("is_admin", False),
            "error": error,
            "active_catalog": catalog_name,
            "active_schema": None,
            "active_table": None,
        },
    )


@app.get(
    "/catalogs/{catalog_name}/schemas/{schema_name}",
    response_class=HTMLResponse,
)
async def schema_detail(request: Request, catalog_name: str, schema_name: str) -> HTMLResponse:
    """Render metadata for a single schema."""
    client = _get_uc_client(request)
    user = _get_user(request)
    schema: dict[str, Any] | None = None
    tags: list[dict[str, Any]] = []
    permissions: list[dict[str, Any]] = []
    effective: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    error: str | None = None
    full_name = f"{catalog_name}.{schema_name}"
    try:
        schema, tags, permissions, effective, tables = await asyncio.gather(
            client.get_schema(catalog_name, schema_name),
            client.get_tags("schema", full_name),
            client.get_permissions("schema", full_name),
            client.get_effective_permissions("schema", full_name),
            client.list_tables(catalog_name, schema_name),
        )
    except CatalogUnavailableError as exc:
        error = exc.detail

    if error is None:
        check_privilege_from_effective(
            effective,
            user.get("email", ""),
            user.get("is_admin", False),
            "schema",
            full_name,
            USE_SCHEMA,
        )

    can_manage = has_privilege(
        effective,
        user.get("email", ""),
        user.get("is_admin", False),
        MANAGE_GRANTS,
    )
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/tables.html",
        {
            "catalog_name": catalog_name,
            "schema_name": schema_name,
            "schema": schema,
            "tags": tags,
            "permissions": permissions,
            "effective": effective,
            "tables": tables,
            "can_manage": can_manage,
            "error": error,
            "active_catalog": catalog_name,
            "active_schema": schema_name,
            "active_table": None,
        },
    )


@app.get(
    "/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}",
    response_class=HTMLResponse,
)
async def table_detail(
    request: Request,
    catalog_name: str,
    schema_name: str,
    table_name: str,
) -> HTMLResponse:
    """Render metadata and column schema for a single table."""
    client = _get_uc_client(request)
    user = _get_user(request)
    table: dict[str, Any] | None = None
    tags: list[dict[str, Any]] = []
    permissions: list[dict[str, Any]] = []
    effective: list[dict[str, Any]] = []
    lineage: dict[str, Any] = {}
    error: str | None = None
    full_name = f"{catalog_name}.{schema_name}.{table_name}"
    try:
        table, tags, permissions, effective, lineage = await asyncio.gather(
            client.get_table(catalog_name, schema_name, table_name),
            client.get_tags("table", full_name),
            client.get_permissions("table", full_name),
            client.get_effective_permissions("table", full_name),
            client.get_lineage(full_name),
        )
    except CatalogUnavailableError as exc:
        error = exc.detail

    if error is None:
        check_privilege_from_effective(
            effective,
            user.get("email", ""),
            user.get("is_admin", False),
            "table",
            full_name,
            SELECT,
        )

    can_manage = has_privilege(
        effective,
        user.get("email", ""),
        user.get("is_admin", False),
        MANAGE_GRANTS,
    )
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/table.html",
        {
            "catalog_name": catalog_name,
            "schema_name": schema_name,
            "table_name": table_name,
            "table": table,
            "tags": tags,
            "permissions": permissions,
            "effective": effective,
            "lineage": lineage,
            "can_manage": can_manage,
            "is_admin": user.get("is_admin", False),
            "error": error,
            "active_catalog": catalog_name,
            "active_schema": schema_name,
            "active_table": table_name,
        },
    )


# Notebook editor + workspace HTTP routes (/notebook/editor,
# /api/notebook/doc + /api/notebook/cell-runs + /api/notebooks/*
# + /notebooks/workspace) live in api/notebooks_routes.py since Sprint 88a.


# Notebook WebSocket endpoints (/ws/notebook/kernel + /ws/notebook/lsp)
# and the shared resolve_sql_approved_tables helper live in
# api/notebook_kernel_ws.py since Sprint 88b.


# Federation routes (/api/connections, /api/external-locations,
# /api/credentials + their HTML pages) live in api/federation_routes.py
# since Sprint 89a.



# Jobs + scheduler routes (/api/jobs*, /jobs*, papermill artefacts)
# live in api/jobs_routes.py since Sprint 89b.



# Dashboards routes (/api/dashboards*, /dashboards*) live in
# api/dashboards_routes.py since Sprint 89c.



def _score_match(needle: str, haystack: str) -> float | None:
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


def _epoch_seconds(value: Any) -> float:
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


@app.get("/api/search")
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
    needle = q.strip().casefold()
    if not needle:
        return []
    limit = max(1, min(int(limit), 100))

    user = _get_user(request)
    client = _get_uc_client(request)

    async def _soyuz_tree() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        try:
            tree = await client.get_tree()
        except PointlessSQLError:
            logger.warning("search: soyuz tree unavailable", exc_info=True)
            return out
        for cat in tree:
            cat_name = str(cat.get("name") or "")
            cat_score = _score_match(needle, cat_name)
            if cat_score is not None:
                out.append(
                    {
                        "type": "catalog",
                        "label": cat_name,
                        "description": str(cat.get("comment") or ""),
                        "url": f"/catalogs/{cat_name}",
                        "updated_at": _epoch_seconds(cat.get("updated_at")),
                        "score": cat_score,
                    }
                )
            for schema in cat.get("schemas") or []:
                s_name = str(schema.get("name") or "")
                s_score = _score_match(needle, s_name)
                if s_score is not None:
                    out.append(
                        {
                            "type": "schema",
                            "label": f"{cat_name}.{s_name}",
                            "description": str(schema.get("comment") or ""),
                            "url": f"/catalogs/{cat_name}/schemas/{s_name}",
                            "updated_at": _epoch_seconds(schema.get("updated_at")),
                            "score": s_score,
                        }
                    )
                for table in schema.get("tables") or []:
                    t_name = str(table.get("name") or "")
                    t_score = _score_match(needle, t_name)
                    if t_score is None:
                        continue
                    out.append(
                        {
                            "type": "table",
                            "label": f"{cat_name}.{s_name}.{t_name}",
                            "description": str(table.get("comment") or ""),
                            "url": (f"/catalogs/{cat_name}/schemas/{s_name}/tables/{t_name}"),
                            "updated_at": _epoch_seconds(table.get("updated_at")),
                            "score": t_score,
                        }
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
                score = _score_match(needle, name)
                if score is None:
                    continue
                out.append(
                    {
                        "type": type_name,
                        "label": name,
                        "description": str(row.get("comment") or ""),
                        "url": url_tmpl.format(name=name),
                        "updated_at": _epoch_seconds(row.get("updated_at")),
                        "score": score,
                    }
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
                score = _score_match(needle, row.name)
                if score is None:
                    continue
                out.append(
                    {
                        "type": "job",
                        "label": row.name,
                        "description": f"{row.kind} · {row.cron_expr}",
                        "url": f"/jobs/{row.id}",
                        "updated_at": _epoch_seconds(row.updated_at),
                        "score": score,
                    }
                )
        return out

    def _local_dashboards() -> list[dict[str, Any]]:
        from sqlalchemy import select as _select

        from pointlessql.models import Dashboard as DashboardModel

        out: list[dict[str, Any]] = []
        factory = request.app.state.session_factory
        with factory() as session:
            for row in session.scalars(_select(DashboardModel)).all():
                title_score = _score_match(needle, row.title)
                slug_score = _score_match(needle, row.slug)
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
                        "updated_at": _epoch_seconds(row.updated_at),
                        "score": score,
                    }
                )
        return out

    def _local_notebooks() -> list[dict[str, Any]]:
        # Matches the Sprint-27 admin boundary on /api/notebooks/tree.
        if not user.get("is_admin"):
            return []
        settings_obj: Settings = request.app.state.settings
        try:
            tree = notebook_workspace_service.list_workspace_tree(
                settings_obj.jupyter.notebooks_dir.resolve()
            )
        except Exception:
            logger.warning("search: notebook tree unavailable", exc_info=True)
            return []
        out: list[dict[str, Any]] = []

        def _walk(nodes: list[dict[str, Any]]) -> None:
            for node in nodes:
                kind = node.get("kind")
                if kind == "notebook":
                    name = str(node.get("name") or "")
                    path = str(node.get("path") or "")
                    score = _score_match(needle, name) or _score_match(needle, path)
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
                        }
                    )
                elif kind == "dir":
                    children = node.get("children") or []
                    _walk(children)

        _walk(tree)
        return out

    tree_hits, fed_hits = await asyncio.gather(_soyuz_tree(), _soyuz_federation())
    hits: list[dict[str, Any]] = []
    hits.extend(tree_hits)
    hits.extend(fed_hits)
    hits.extend(_local_jobs())
    hits.extend(_local_dashboards())
    hits.extend(_local_notebooks())

    hits.sort(key=lambda h: (-float(h["score"]), -float(h["updated_at"])))
    return hits[:limit]


async def _build_home_summary(request: Request, user: UserInfo) -> dict[str, Any]:
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
    client = _get_uc_client(request)
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
                        }
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
                    idx = (started_at.date() - start_day).days
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
            # the bars unbound (BUG-32-01 found during the Phase 9
            # playbook replay). Moving the branch here keeps the
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
                    .where(DashboardModel.owner_id == user_id)
                )
                or 0
            )
            mine_rows = list(
                session.scalars(
                    _select(DashboardModel)
                    .where(DashboardModel.owner_id == user_id)
                    .order_by(DashboardModel.updated_at.desc())
                    .limit(5)
                ).all()
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

    catalogs_block, db_block = await asyncio.gather(
        _catalogs_block(),
        asyncio.to_thread(_db_block),
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
        "onboarding": {
            "show": show_onboarding,
            "have_catalogs": have_catalogs,
            "have_jobs": have_jobs,
            "have_dashboards": have_dashboards,
        },
    }


@app.get("/api/home/summary")
async def api_home_summary(request: Request) -> dict[str, Any]:
    """Return the aggregated payload that powers the home dashboard.

    One round-trip for every server-side card on ``/``: catalog count,
    jobs + paused counters, 10 most recent cross-job runs visible to
    the user, a 7-day success-rate bucket list for the sparkline, and
    the user's own dashboards + total dashboard count. Recent catalogs
    are client-side in ``localStorage["pql.recentCatalogs"]`` and do
    not flow through this endpoint.
    """
    user = _get_user(request)
    return await _build_home_summary(request, user)








_ADMIN_AUDIT_LIMIT = 1000
_ADMIN_AUDIT_SINCE_WINDOWS: dict[str, timedelta | None] = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "all": None,
}


@app.get("/admin/audit", response_class=HTMLResponse)
async def admin_audit_index(
    request: Request,
    action: str | None = None,
    user: str | None = None,
    target: str | None = None,
    since: Literal["24h", "7d", "30d", "all"] = "7d",
) -> HTMLResponse:
    """Render the admin audit-log viewer.

    Reads from the Sprint-7 ``audit_log`` table (written append-only
    by every admin state-change via :func:`_audit`) and shows the
    newest :data:`_ADMIN_AUDIT_LIMIT` rows matching the requested
    filters. Admin-gated because the log carries cross-user activity
    that a non-admin principal must not see. Re-uses the ``/jobs``
    ``listTable`` Alpine component for search and chip filtering so
    the page inherits sorting, search, and mobile stacking without
    new frontend primitives.
    """
    from sqlalchemy import select as _select

    from pointlessql.models import AuditLog as AuditLogModel

    _require_admin(request)
    current_user = _get_user(request)
    factory = request.app.state.session_factory

    since_delta = _ADMIN_AUDIT_SINCE_WINDOWS[since]
    since_cutoff = datetime.now(UTC) - since_delta if since_delta is not None else None

    stmt = _select(AuditLogModel).order_by(AuditLogModel.created_at.desc())
    if since_cutoff is not None:
        stmt = stmt.where(AuditLogModel.created_at >= since_cutoff)
    if action:
        stmt = stmt.where(AuditLogModel.action == action)
    if user:
        stmt = stmt.where(AuditLogModel.user_email.ilike(f"%{user}%"))
    if target:
        stmt = stmt.where(AuditLogModel.target.ilike(f"%{target}%"))
    # Fetch one extra row so we can tell the page whether the
    # ``_ADMIN_AUDIT_LIMIT`` cap hid older history.
    stmt = stmt.limit(_ADMIN_AUDIT_LIMIT + 1)

    with factory() as session:
        rows = list(session.scalars(stmt).all())
        for row in rows:
            session.expunge(row)

    truncated = len(rows) > _ADMIN_AUDIT_LIMIT
    if truncated:
        rows = rows[:_ADMIN_AUDIT_LIMIT]

    entries = [
        {
            "id": r.id,
            "user_id": r.user_id,
            "user_email": r.user_email,
            "actor_role": r.actor_role,
            "action": r.action,
            "target": r.target,
            "client_ip": r.client_ip,
            "detail": r.detail,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        }
        for r in rows
    ]
    # Distinct action list for the server-side filter dropdown.
    # Derived from the currently-loaded page so new actions show up
    # automatically; the 1000-row cap keeps this cheap.
    distinct_actions = sorted({e["action"] for e in entries})

    return _TEMPLATES.TemplateResponse(
        request,
        "pages/admin_audit.html",
        {
            "entries": entries,
            "distinct_actions": distinct_actions,
            "filter_action": action or "",
            "filter_user": user or "",
            "filter_target": target or "",
            "filter_since": since,
            "truncated": truncated,
            "row_limit": _ADMIN_AUDIT_LIMIT,
            "current_user_id": current_user.get("id"),
            "current_user_email": current_user.get("email"),
            "active_page": "admin_audit",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
            "list_page": True,
        },
    )


_AUDIT_EXPORT_LIMIT = 10_000
_AUDIT_EXPORT_FORMATS: tuple[str, ...] = ("json", "csv")


@app.get("/admin/audit/export")
async def admin_audit_export(
    request: Request,
    fmt: Literal["json", "csv"] = "json",
    action: str | None = None,
    user: str | None = None,
    target: str | None = None,
    since: Literal["24h", "7d", "30d", "all"] = "7d",
) -> Response:
    """Stream the filtered audit log as JSON or CSV.

    Mirrors the :func:`admin_audit_index` filter surface so
    operators can "what you see is what you export" from the same
    query string — just swap ``/admin/audit?…`` for
    ``/admin/audit/export?fmt=csv&…``.  Capped at
    :data:`_AUDIT_EXPORT_LIMIT` rows per call so a broad ``since=all``
    query cannot blow memory; operators wanting more paginate by
    shrinking the time window.

    Args:
        request: The incoming HTTP request (used for admin gate).
        fmt: ``json`` or ``csv``.
        action: Optional exact-match action filter.
        user: Optional ``ILIKE %…%`` filter on ``user_email``.
        target: Optional ``ILIKE %…%`` filter on ``target``.
        since: Time-window preset (same as the HTML viewer).

    Returns:
        Response: Content-Disposition-attachment response; the
            download filename embeds the export timestamp.
    """
    import csv
    import io

    from sqlalchemy import select as _select

    from pointlessql.models import AuditLog as AuditLogModel

    _require_admin(request)
    factory = request.app.state.session_factory

    since_delta = _ADMIN_AUDIT_SINCE_WINDOWS[since]
    since_cutoff = datetime.now(UTC) - since_delta if since_delta is not None else None

    stmt = _select(AuditLogModel).order_by(AuditLogModel.created_at.desc())
    if since_cutoff is not None:
        stmt = stmt.where(AuditLogModel.created_at >= since_cutoff)
    if action:
        stmt = stmt.where(AuditLogModel.action == action)
    if user:
        stmt = stmt.where(AuditLogModel.user_email.ilike(f"%{user}%"))
    if target:
        stmt = stmt.where(AuditLogModel.target.ilike(f"%{target}%"))
    stmt = stmt.limit(_AUDIT_EXPORT_LIMIT)

    def _rows() -> list[dict[str, Any]]:
        with factory() as session:
            result = list(session.scalars(stmt).all())
        return [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else "",
                "user_id": r.user_id,
                "user_email": r.user_email,
                "actor_role": r.actor_role,
                "action": r.action,
                "target": r.target,
                "client_ip": r.client_ip or "",
                "detail": r.detail or "",
            }
            for r in result
        ]

    rows = await asyncio.to_thread(_rows)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    if fmt == "json":
        body = json.dumps({"exported_at": timestamp, "entries": rows}, indent=2)
        return Response(
            content=body,
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="pql-audit-{timestamp}.json"'
                )
            },
        )

    # CSV
    buf = io.StringIO()
    columns = [
        "id",
        "created_at",
        "user_id",
        "user_email",
        "actor_role",
        "action",
        "target",
        "client_ip",
        "detail",
    ]
    writer = csv.DictWriter(buf, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="pql-audit-{timestamp}.csv"'
            )
        },
    )





def cli() -> None:
    """Run the development server."""
    import uvicorn

    settings = Settings()
    # Why: uvicorn's reload watcher defaults to the whole working directory.
    # That includes ``notebooks/``, so the editor's autosave triggers a server
    # reload — kernel + Pyright WebSockets get torn down mid-typing
    # (Sprint 64 BUG-64-03). Pinning reload_dirs to the source trees keeps
    # autosave invisible to the watcher; SQLite files (.db) and Delta tables
    # (notebooks/, /tmp) stay outside scope.
    project_root = Path(__file__).resolve().parent.parent
    uvicorn.run(
        "pointlessql.api.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=True,
        reload_dirs=[str(project_root), str(project_root.parent / "frontend")],
    )
