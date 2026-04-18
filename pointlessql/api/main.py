"""FastAPI entrypoint for PointlesSQL."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import Body, FastAPI, File, Form, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pointlessql.api.auth_routes import router as auth_router
from pointlessql.api.csrf_middleware import csrf_middleware as _csrf_middleware
from pointlessql.api.rate_limit_middleware import (
    rate_limit_middleware as _rate_limit_middleware,
)
from pointlessql.db import get_session_factory, init_db
from pointlessql.exceptions import (
    AuthorizationError,
    CatalogUnavailableError,
    PointlessSQLError,
    ValidationError,
)
from pointlessql.logging_config import configure_logging, request_id_var
from pointlessql.services import audit as audit_service
from pointlessql.services import auth as auth_service
from pointlessql.services import metrics as metrics_service
from pointlessql.services import notebook_render as notebook_render_service
from pointlessql.services import notebook_workspace as notebook_workspace_service
from pointlessql.services import pg_sync as pg_sync_service
from pointlessql.services import scheduler as scheduler_service
from pointlessql.services.authorization import (
    MANAGE_GRANTS,
    MODIFY,
    SELECT,
    USE_CATALOG,
    USE_SCHEMA,
    check_privilege,
    check_privilege_from_effective,
    has_privilege,
)
from pointlessql.services.jupyter import managed_jupyter
from pointlessql.services.soyuz_client import make_principal_client, make_soyuz_client
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

    async with managed_jupyter(settings) as jupyter_proc:
        app.state.jupyter_process = jupyter_proc
        try:
            yield
        finally:
            if scheduler is not None:
                await scheduler.stop()
            await app.state.uc_client.aclose()


app = FastAPI(title="PointlesSQL", version="0.1.0", lifespan=_lifespan)

from pointlessql.api.error_handlers import register_error_handlers  # noqa: E402

register_error_handlers(app)

app.include_router(auth_router)
app.mount(
    "/static",
    StaticFiles(directory=str(_FRONTEND_DIR)),
    name="static",
)

# Paths that do not require authentication.
_PUBLIC_PREFIXES = ("/auth/", "/static/", "/healthz")


@app.middleware("http")
async def auth_middleware(request: Request, call_next: Any) -> Response:
    """Extract user from JWT cookie; redirect to login if unauthenticated."""
    path = request.url.path

    # Always try to resolve user from cookie (even on public paths,
    # so templates can show the navbar user menu).
    token = request.cookies.get(auth_service.COOKIE_NAME)
    if token is not None:
        factory = getattr(request.app.state, "session_factory", None)
        settings = getattr(request.app.state, "settings", None)
        if factory is not None and settings is not None:
            user = auth_service.get_current_user(factory, token, settings.auth.secret_key)
            if user is not None:
                request.state.user = user

    # Public paths pass through regardless of auth.
    if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
        return await call_next(request)

    # Protected paths require authentication.
    if getattr(request.state, "user", None) is not None:
        return await call_next(request)

    # Unauthenticated — redirect HTML requests, 401 for API.
    if path.startswith("/api/"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    return RedirectResponse(url="/auth/login", status_code=303)


# Rate limiting on /auth/* runs inside CSRF but outside auth: a
# cross-site flood must still fail the cheap CSRF check before it
# burns a bucket slot, but a CSRF-clean flood is caught before
# auth_middleware runs bcrypt + JWT-decode on every attempt.
# Starlette stacks middleware LIFO (last-registered is outermost),
# so registering it after auth and before csrf puts it at that exact
# position in the execution order. Sprint 43.
app.middleware("http")(_rate_limit_middleware)


# CSRF enforcement runs between auth and request_id: Starlette stacks
# middleware LIFO (last-registered is outermost), so request_id wraps
# csrf wraps auth. A CSRF failure short-circuits before auth's user
# lookup, and the 403 response still carries the outer request-id
# header for ops. Sprint 42.
app.middleware("http")(_csrf_middleware)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next: Any) -> Response:
    """Attach a unique request ID to every request and echo it in the response.

    The ID is stored both on ``request.state`` (for the error handler)
    and in the ``request_id_var`` contextvar (so service-layer log
    records emitted during this request pick it up via the
    ``RequestIdFilter``). The contextvar is reset in ``finally`` so
    concurrent requests never leak IDs into each other's scope.
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    token = request_id_var.set(request_id)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = request_id
    return response


def _get_uc_client(request: Request) -> UnityCatalogClient:
    """Return a per-request UC facade with the current user's principal."""
    user = getattr(request.state, "user", None)
    if user is not None:
        return UnityCatalogClient.for_principal(request.app.state.settings, user["email"])
    return request.app.state.uc_client


def _get_user(request: Request) -> UserInfo:
    """Return the current user dict from request state."""
    user: UserInfo | None = getattr(request.state, "user", None)
    if user is None:
        return UserInfo(id=0, email="", display_name="", is_admin=False)
    return user


def _require_admin(request: Request) -> None:
    """Raise :class:`AuthorizationError` if the current user is not an admin."""
    user = _get_user(request)
    if not user.get("is_admin"):
        raise AuthorizationError(
            principal=user.get("email", ""),
            privilege="admin",
            securable_type="system",
            full_name="admin",
        )


def _audit(request: Request, action: str, target: str, detail: str | None = None) -> None:
    """Write an audit log entry for the current user."""
    user = _get_user(request)
    factory = getattr(request.app.state, "session_factory", None)
    if factory is not None and user["id"]:
        audit_service.log_action(factory, user["id"], user["email"], action, target, detail)


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


@app.get("/api/tree")
async def api_tree(request: Request) -> list[dict[str, object]]:
    """Return the full catalog/schema/table tree for the sidebar."""
    client = _get_uc_client(request)
    return await client.get_tree()


@app.get("/api/catalogs")
async def api_catalogs(request: Request) -> list[dict[str, object]]:
    """Return all catalogs as JSON."""
    client = _get_uc_client(request)
    return await client.list_catalogs()


@app.get("/api/catalogs/{catalog_name}/schemas")
async def api_schemas(request: Request, catalog_name: str) -> list[dict[str, object]]:
    """Return schemas inside a catalog as JSON."""
    client = _get_uc_client(request)
    user = _get_user(request)
    await check_privilege(
        client,
        user.get("email", ""),
        user.get("is_admin", False),
        "catalog",
        catalog_name,
        USE_CATALOG,
    )
    return await client.list_schemas(catalog_name)


@app.get("/api/catalogs/{catalog_name}/schemas/{schema_name}/tables")
async def api_tables(
    request: Request, catalog_name: str, schema_name: str
) -> list[dict[str, object]]:
    """Return tables inside a schema as JSON."""
    client = _get_uc_client(request)
    user = _get_user(request)
    await check_privilege(
        client,
        user.get("email", ""),
        user.get("is_admin", False),
        "schema",
        f"{catalog_name}.{schema_name}",
        USE_SCHEMA,
    )
    return await client.list_tables(catalog_name, schema_name)


_PREVIEW_ROW_LIMIT = 10


def _preview_head(frame: Any, n: int) -> Any:
    """Return at most *n* rows of *frame* as a pandas DataFrame.

    Engine-aware: DuckDB relations expose ``limit``; polars frames
    expose ``to_pandas``; pandas stays untouched. Keeps DuckDB lazy
    instead of materialising the whole relation.

    Args:
        frame: Whatever :meth:`pointlessql.pql.pql.PQL.table` returned —
            a pandas/polars frame or a DuckDB relation.
        n: Maximum number of rows to return.

    Returns:
        A pandas DataFrame holding at most *n* rows.
    """
    import pandas as pd

    if hasattr(frame, "limit") and hasattr(frame, "df"):
        return frame.limit(n).df()
    if hasattr(frame, "head"):
        head = frame.head(n)
        if hasattr(head, "to_pandas"):
            return head.to_pandas()
        return head
    return pd.DataFrame(frame).head(n)


def _run_table_preview(settings: Settings, principal: str, full_name: str) -> dict[str, Any]:
    """Read up to 10 rows of a Delta table and serialise them.

    Runs inside :func:`asyncio.to_thread` so the sync :class:`PQL`
    helper does not block the event loop. Degrades gracefully on any
    failure: a broken table must fail this card, not the page.

    Args:
        settings: Application settings (for soyuz URL + engine).
        principal: User email forwarded as ``X-Principal``. Empty
            string falls back to the anonymous client.
        full_name: Three-part table name ``catalog.schema.table``.

    Returns:
        Either ``{"columns": [...], "rows": [...], "truncated": bool}``
        on success, or ``{"error": "preview_unavailable", "detail":
        str}`` on failure.
    """
    from pointlessql.pql.pql import PQL

    try:
        client = (
            make_principal_client(settings, principal) if principal else make_soyuz_client(settings)
        )
        pql = PQL(client=client, settings=settings)
        frame = pql.table(full_name)
        df = _preview_head(frame, _PREVIEW_ROW_LIMIT + 1)
    except Exception as exc:  # noqa: BLE001 — degrade preview card
        logger.warning("table preview failed for %s: %s", full_name, exc)
        return {"error": "preview_unavailable", "detail": str(exc)}
    truncated = len(df) > _PREVIEW_ROW_LIMIT
    df = df.head(_PREVIEW_ROW_LIMIT)
    columns = [str(c) for c in df.columns]
    rows = df.values.tolist()
    return jsonable_encoder({"columns": columns, "rows": rows, "truncated": truncated})


@app.get("/api/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}/preview")
async def api_table_preview(
    request: Request,
    catalog_name: str,
    schema_name: str,
    table_name: str,
) -> Response:
    """Return up to 10 rows from a Delta table as JSON.

    The row limit is fixed at 10 server-side — no client-tunable
    query param, to keep one fewer attack surface. Response carries
    ``Cache-Control: no-store`` so row data does not sit in the
    browser disk cache after a permission revocation.
    """
    client = _get_uc_client(request)
    user = _get_user(request)
    full_name = f"{catalog_name}.{schema_name}.{table_name}"
    effective = await client.get_effective_permissions("table", full_name)
    check_privilege_from_effective(
        effective,
        user.get("email", ""),
        user.get("is_admin", False),
        "table",
        full_name,
        SELECT,
    )
    settings: Settings = request.app.state.settings
    payload = await asyncio.to_thread(
        _run_table_preview, settings, user.get("email", ""), full_name
    )
    return JSONResponse(content=payload, headers={"Cache-Control": "no-store"})


@app.post("/api/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}/open-in-notebook")
async def api_open_in_notebook(
    request: Request,
    catalog_name: str,
    schema_name: str,
    table_name: str,
) -> dict[str, Any]:
    """Create a scratch notebook pre-filled with ``pql.table(...)``.

    Admin-only to keep the workspace clean. Writes a minimal
    nbformat-4.5 notebook under ``{notebooks_dir}/scratch/`` with a
    markdown header and a single code cell that reads the requested
    table. Returns the on-disk path plus a JupyterLab deep-link the
    client navigates to with ``window.location.assign``.
    """
    import secrets

    import nbformat

    _require_admin(request)
    settings: Settings = request.app.state.settings
    full_name = f"{catalog_name}.{schema_name}.{table_name}"

    sanitiser = re.compile(r"[^A-Za-z0-9_-]")
    stem = "_".join(sanitiser.sub("_", part) for part in (catalog_name, schema_name, table_name))
    filename = f"{stem}_{secrets.token_hex(3)}.ipynb"
    scratch_dir = settings.jupyter.notebooks_dir / "scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    target = notebook_workspace_service.resolve_upload_target(
        settings.jupyter.notebooks_dir, f"scratch/{filename}"
    )

    nb = nbformat.v4.new_notebook()
    nb.cells = [
        nbformat.v4.new_markdown_cell(
            f"# Scratch: `{full_name}`\n\nGenerated from the PointlesSQL table detail page."
        ),
        nbformat.v4.new_code_cell(
            f'from pointlessql import PQL\n\npql = PQL()\ndf = pql.table("{full_name}")\ndf.head()'
        ),
    ]
    with target.open("w", encoding="utf-8") as fh:
        nbformat.write(nb, fh)

    _audit(request, "open_in_notebook", f"table:{full_name}", f"scratch/{filename}")
    host = request.url.hostname or "localhost"
    relative = f"scratch/{filename}"
    lab_url = f"http://{host}:{settings.jupyter.port}/lab/tree/{relative}"
    return {"path": relative, "lab_url": lab_url}


@app.post("/api/catalogs")
async def api_create_catalog(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, object]:
    """Create a new catalog.

    Admin-only so foreign-catalog creation (which binds a Connection)
    stays aligned with the federation admin-only rule. Once soyuz-catalog
    exposes a finer-grained CREATE_CATALOG privilege we can switch to
    ``check_privilege`` on the metastore like the other writes.
    """
    _require_admin(request)
    client = _get_uc_client(request)
    result = await client.create_catalog(body)
    _audit(request, "create_catalog", f"catalog:{body.get('name', '?')}", json.dumps(body))
    return result


@app.post("/api/catalogs/{catalog_name}/sync")
async def api_sync_catalog(request: Request, catalog_name: str) -> dict[str, object]:
    """Trigger a Postgres → UC sync for a foreign catalog (admin-only).

    Reads the catalog's bound Connection, resolves a Credential by the
    optional ``credential_name`` key in its options, and runs the
    Sprint 18 sync worker. Returns the :class:`SyncRun` snapshot so
    the UI can render the new history card entry immediately.
    """
    _require_admin(request)
    client = _get_uc_client(request)
    catalog = await client.get_catalog(catalog_name)
    connection_name = catalog.get("connection_name")
    if not connection_name:
        raise AuthorizationError(
            principal=_get_user(request).get("email", ""),
            privilege="sync",
            securable_type="catalog",
            full_name=catalog_name,
        )
    connection = await client.get_connection(str(connection_name))
    credential: dict[str, Any] | None = None
    options = connection.get("options") or {}
    credential_name = options.get("credential_name") if isinstance(options, dict) else None
    if credential_name:
        credential = await client.get_credential(str(credential_name))
    factory = request.app.state.session_factory
    run = await pg_sync_service.run_sync(
        uc=client,
        factory=factory,
        catalog_name=catalog_name,
        introspector=pg_sync_service.PsycopgIntrospector(),
        connection=connection,
        credential=credential,
    )
    _audit(request, "sync_catalog", f"catalog:{catalog_name}")
    return {
        "id": run.id,
        "catalog_name": run.catalog_name,
        "status": run.status,
        "added_count": run.added_count,
        "changed_count": run.changed_count,
        "dropped_count": run.dropped_count,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "error": run.error,
    }


@app.patch("/api/catalogs/{catalog_name}")
async def api_update_catalog(
    request: Request,
    catalog_name: str,
    patch: dict[str, Any] = Body(...),
) -> dict[str, object]:
    """Apply a partial update to a catalog."""
    client = _get_uc_client(request)
    user = _get_user(request)
    await check_privilege(
        client,
        user.get("email", ""),
        user.get("is_admin", False),
        "catalog",
        catalog_name,
        MODIFY,
    )
    result = await client.update_catalog(catalog_name, patch)
    _audit(request, "update_catalog", f"catalog:{catalog_name}", json.dumps(patch))
    return result


@app.patch("/api/catalogs/{catalog_name}/schemas/{schema_name}")
async def api_update_schema(
    request: Request,
    catalog_name: str,
    schema_name: str,
    patch: dict[str, Any] = Body(...),
) -> dict[str, object]:
    """Apply a partial update to a schema."""
    client = _get_uc_client(request)
    user = _get_user(request)
    full_name = f"{catalog_name}.{schema_name}"
    await check_privilege(
        client,
        user.get("email", ""),
        user.get("is_admin", False),
        "schema",
        full_name,
        MODIFY,
    )
    result = await client.update_schema(catalog_name, schema_name, patch)
    _audit(request, "update_schema", f"schema:{full_name}", json.dumps(patch))
    return result


@app.get("/api/tags/{securable_type}/{full_name:path}")
async def api_get_tags(
    request: Request, securable_type: str, full_name: str
) -> list[dict[str, object]]:
    """Return tags for a securable."""
    client = _get_uc_client(request)
    return await client.get_tags(securable_type, full_name)


@app.patch("/api/tags/{securable_type}/{full_name:path}")
async def api_update_tags(
    request: Request,
    securable_type: str,
    full_name: str,
    body: dict[str, Any] = Body(...),
) -> list[dict[str, object]]:
    """Update tags for a securable. Body: {"changes": [...]}."""
    client = _get_uc_client(request)
    user = _get_user(request)
    await check_privilege(
        client,
        user.get("email", ""),
        user.get("is_admin", False),
        securable_type,
        full_name,
        MODIFY,
    )
    result = await client.update_tags(securable_type, full_name, body.get("changes", []))
    _audit(
        request,
        "update_tags",
        f"{securable_type}:{full_name}",
        json.dumps(body.get("changes", [])),
    )
    return result


@app.get("/api/permissions/{securable_type}/{full_name:path}")
async def api_get_permissions(
    request: Request, securable_type: str, full_name: str
) -> list[dict[str, object]]:
    """Return privilege assignments for a securable."""
    client = _get_uc_client(request)
    return await client.get_permissions(securable_type, full_name)


@app.patch("/api/permissions/{securable_type}/{full_name:path}")
async def api_update_permissions(
    request: Request,
    securable_type: str,
    full_name: str,
    body: dict[str, Any] = Body(...),
) -> list[dict[str, object]]:
    """Update permissions for a securable. Body: {"changes": [...]}."""
    client = _get_uc_client(request)
    user = _get_user(request)
    await check_privilege(
        client,
        user.get("email", ""),
        user.get("is_admin", False),
        securable_type,
        full_name,
        MANAGE_GRANTS,
    )
    result = await client.update_permissions(securable_type, full_name, body.get("changes", []))
    _audit(
        request,
        "update_permissions",
        f"{securable_type}:{full_name}",
        json.dumps(body.get("changes", [])),
    )
    return result


@app.get("/api/effective-permissions/{securable_type}/{full_name:path}")
async def api_get_effective_permissions(
    request: Request, securable_type: str, full_name: str
) -> list[dict[str, object]]:
    """Return effective (inherited) permissions for a securable."""
    client = _get_uc_client(request)
    return await client.get_effective_permissions(securable_type, full_name)


@app.get("/api/lineage/{full_name:path}")
async def api_lineage(request: Request, full_name: str, depth: int = 3) -> dict[str, object]:
    """Return combined upstream/downstream lineage for a table."""
    client = _get_uc_client(request)
    user = _get_user(request)
    await check_privilege(
        client,
        user.get("email", ""),
        user.get("is_admin", False),
        "table",
        full_name,
        SELECT,
    )
    return await client.get_lineage(full_name, depth)


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


@app.get("/notebook", response_class=HTMLResponse)
async def notebook_page(request: Request) -> HTMLResponse:
    """Render the embedded JupyterLab notebook page."""
    settings: Settings = request.app.state.settings
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/notebook.html",
        {
            "jupyter_enabled": settings.jupyter.enabled,
            "jupyter_port": settings.jupyter.port,
            "active_page": "notebook",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@app.get("/api/jupyter/status")
async def jupyter_status(request: Request) -> dict[str, object]:
    """Return Jupyter subprocess status."""
    settings: Settings = request.app.state.settings
    proc = getattr(request.app.state, "jupyter_process", None)
    running = proc is not None and proc.returncode is None
    return {
        "enabled": settings.jupyter.enabled,
        "running": running,
        "port": settings.jupyter.port,
    }


@app.get("/api/notebooks/inspect")
async def api_inspect_notebook(request: Request, path: str) -> list[dict[str, Any]]:
    """Return a notebook's declared Papermill parameters.

    Introspects the ``parameters``-tagged cell via
    :func:`papermill.inspect_notebook` and returns one entry per
    declared parameter. The create-job modal uses this to render a
    typed form instead of the raw JSON textarea introduced in
    Sprint 24.

    Args:
        request: Incoming FastAPI request; admin-only.
        path: Relative notebook path, resolved under
            :attr:`Settings.notebooks_dir`. Must not escape the
            directory — uses the same validator as the executor.

    Returns:
        A list of ``{"name", "default", "inferred_type", "help"}``
        dicts. ``default`` is the literal default string Papermill
        extracts (the client coerces it per ``inferred_type``).
    """
    import papermill  # type: ignore[import-untyped]

    _require_admin(request)
    settings: Settings = request.app.state.settings
    resolved = scheduler_service.resolve_notebook_path(
        settings.jupyter.notebooks_dir.resolve(), path
    )
    raw = papermill.inspect_notebook(str(resolved))
    out: list[dict[str, Any]] = []
    for name, meta in raw.items():
        meta_dict: dict[str, Any] = meta
        out.append(
            {
                "name": name,
                "default": meta_dict.get("default"),
                "inferred_type": meta_dict.get("inferred_type_name") or "str",
                "help": meta_dict.get("help", ""),
            }
        )
    return out


@app.get("/api/notebooks/tree")
async def api_notebooks_tree(request: Request) -> list[dict[str, Any]]:
    """Return a nested listing of the notebooks workspace directory.

    Admin-only, matching the inspect + upload routes in this family.
    Each notebook leaf carries a ``parameters_tagged`` flag so the
    workspace UI can hint which files will render a typed form in
    the create-job modal.

    Args:
        request: Incoming FastAPI request; admin-only.

    Returns:
        A list of directory and notebook nodes. See
        :func:`pointlessql.services.notebook_workspace.list_workspace_tree`
        for the shape of each node.
    """
    _require_admin(request)
    settings: Settings = request.app.state.settings
    return notebook_workspace_service.list_workspace_tree(settings.jupyter.notebooks_dir.resolve())


@app.post("/api/notebooks/upload")
async def api_upload_notebook(
    request: Request,
    file: UploadFile = File(...),
    target_path: str = Form(...),
    overwrite: bool = Form(False),
) -> dict[str, str]:
    """Upload an ``.ipynb`` file into the notebooks workspace.

    Admin-only. The ``target_path`` is resolved under
    :attr:`Settings.notebooks_dir` with the same traversal guard the
    executor uses (via
    :func:`pointlessql.services.notebook_workspace.resolve_upload_target`).
    The upload payload must be a well-formed JSON notebook; the body
    is parsed before the file hits disk so a corrupt upload never
    leaves a half-written file in the workspace. Writes are atomic
    via a ``.tmp`` sidecar + :func:`os.replace`.

    Args:
        request: Incoming FastAPI request; admin-only.
        file: The multipart upload. ``file.filename`` must end in
            ``.ipynb``.
        target_path: Relative path under the notebooks directory
            where the upload should land.
        overwrite: When ``True``, an existing file at ``target_path``
            is replaced. When ``False`` (the default), attempting to
            upload over an existing file raises
            :class:`~pointlessql.exceptions.ValidationError`.

    Returns:
        A dict with ``path`` (the relative path the file was written
        to) and ``status`` (``"created"`` or ``"overwritten"``).

    Raises:
        ValidationError: On any of the upload guards (bad filename,
            path traversal, malformed JSON body, existing file
            without ``overwrite=True``). ``AuthorizationError`` is
            raised out of ``_require_admin`` for non-admin callers
            and surfaced as 403 by the centralized error handler.
    """
    import os

    _require_admin(request)
    settings: Settings = request.app.state.settings

    filename = file.filename or ""
    if not filename.endswith(".ipynb"):
        raise ValidationError(f"uploaded file must have an .ipynb extension: {filename!r}")

    resolved = notebook_workspace_service.resolve_upload_target(
        settings.jupyter.notebooks_dir.resolve(), target_path
    )

    raw = await file.read()
    try:
        json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValidationError(f"uploaded file is not valid JSON: {exc}") from exc

    existed = resolved.exists()
    if existed and not overwrite:
        raise ValidationError(
            f"file already exists at {target_path!r}; pass overwrite=true to replace"
        )

    tmp_path = resolved.with_suffix(resolved.suffix + ".tmp")
    tmp_path.write_bytes(raw)
    os.replace(tmp_path, resolved)

    _audit(
        request,
        action="notebook.upload",
        target=target_path,
        detail=f"overwrite={overwrite}",
    )
    logger.info(
        "notebook uploaded to %s (overwrite=%s, existed=%s)",
        target_path,
        overwrite,
        existed,
    )
    return {
        "path": target_path,
        "status": "overwritten" if existed else "created",
    }


@app.get("/notebooks/workspace", response_class=HTMLResponse)
async def notebooks_workspace_page(request: Request) -> HTMLResponse:
    """Render the Sprint 27 workspace file browser (admin-only).

    The page pairs a notebook-tree sidebar (served by
    ``/api/notebooks/tree``) with an upload card. Tree-leaf
    *Schedule…* buttons navigate to
    ``/jobs?prefill_kind=papermill&prefill_notebook_path=<path>``;
    the create-job modal reads those query params on load and
    pre-fills itself.

    Args:
        request: Incoming FastAPI request; admin-only.

    Returns:
        The rendered ``pages/notebooks_workspace.html`` template.
    """
    _require_admin(request)
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/notebooks_workspace.html",
        {
            "active_page": "workspace",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


# -- Federation: Connections --


@app.get("/api/connections")
async def api_list_connections(request: Request) -> list[dict[str, object]]:
    """Return all connections (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    return await client.list_connections()


@app.post("/api/connections")
async def api_create_connection(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, object]:
    """Create a new connection (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    result = await client.create_connection(body)
    _audit(request, "create_connection", f"connection:{body.get('name', '?')}")
    return result


@app.get("/api/connections/{name}")
async def api_get_connection(request: Request, name: str) -> dict[str, object]:
    """Return a single connection (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    return await client.get_connection(name)


@app.patch("/api/connections/{name}")
async def api_update_connection(
    request: Request, name: str, body: dict[str, Any] = Body(...)
) -> dict[str, object]:
    """Update a connection (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    result = await client.update_connection(name, body)
    _audit(request, "update_connection", f"connection:{name}", json.dumps(body))
    return result


@app.delete("/api/connections/{name}")
async def api_delete_connection(request: Request, name: str) -> dict[str, str]:
    """Delete a connection (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    await client.delete_connection(name)
    _audit(request, "delete_connection", f"connection:{name}")
    return {"status": "deleted"}


# -- Federation: External Locations --


@app.get("/api/external-locations")
async def api_list_external_locations(request: Request) -> list[dict[str, object]]:
    """Return all external locations (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    return await client.list_external_locations()


@app.post("/api/external-locations")
async def api_create_external_location(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, object]:
    """Create a new external location (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    result = await client.create_external_location(body)
    _audit(request, "create_ext_location", f"ext_location:{body.get('name', '?')}")
    return result


@app.get("/api/external-locations/{name}")
async def api_get_external_location(request: Request, name: str) -> dict[str, object]:
    """Return a single external location (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    return await client.get_external_location(name)


@app.patch("/api/external-locations/{name}")
async def api_update_external_location(
    request: Request, name: str, body: dict[str, Any] = Body(...)
) -> dict[str, object]:
    """Update an external location (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    result = await client.update_external_location(name, body)
    _audit(request, "update_ext_location", f"ext_location:{name}", json.dumps(body))
    return result


@app.delete("/api/external-locations/{name}")
async def api_delete_external_location(request: Request, name: str) -> dict[str, str]:
    """Delete an external location (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    await client.delete_external_location(name)
    _audit(request, "delete_ext_location", f"ext_location:{name}")
    return {"status": "deleted"}


# -- Federation: Credentials --


@app.get("/api/credentials")
async def api_list_credentials(request: Request) -> list[dict[str, object]]:
    """Return all credentials (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    return await client.list_credentials()


@app.post("/api/credentials")
async def api_create_credential(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, object]:
    """Create a new credential (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    result = await client.create_credential(body)
    _audit(request, "create_credential", f"credential:{body.get('name', '?')}")
    return result


@app.get("/api/credentials/{name}")
async def api_get_credential(request: Request, name: str) -> dict[str, object]:
    """Return a single credential (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    return await client.get_credential(name)


@app.patch("/api/credentials/{name}")
async def api_update_credential(
    request: Request, name: str, body: dict[str, Any] = Body(...)
) -> dict[str, object]:
    """Update a credential (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    result = await client.update_credential(name, body)
    _audit(request, "update_credential", f"credential:{name}", json.dumps(body))
    return result


@app.delete("/api/credentials/{name}")
async def api_delete_credential(request: Request, name: str) -> dict[str, str]:
    """Delete a credential (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    await client.delete_credential(name)
    _audit(request, "delete_credential", f"credential:{name}")
    return {"status": "deleted"}


# -- Federation: HTML pages --


@app.get("/connections", response_class=HTMLResponse)
async def connections_index(request: Request) -> HTMLResponse:
    """List all connections (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    connections: list[dict[str, Any]] = []
    error: str | None = None
    try:
        connections = await client.list_connections()
    except CatalogUnavailableError as exc:
        error = exc.detail
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/connections.html",
        {
            "connections": connections,
            "error": error,
            "active_page": "connections",
            "list_page": True,
        },
    )


@app.get("/connections/{name}", response_class=HTMLResponse)
async def connection_detail(request: Request, name: str) -> HTMLResponse:
    """Show a single connection (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    connection: dict[str, Any] | None = None
    error: str | None = None
    try:
        connection = await client.get_connection(name)
    except CatalogUnavailableError as exc:
        error = exc.detail
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/connection.html",
        {"connection": connection, "name": name, "error": error, "active_page": "connections"},
    )


@app.get("/external-locations", response_class=HTMLResponse)
async def external_locations_index(request: Request) -> HTMLResponse:
    """List all external locations (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    locations: list[dict[str, Any]] = []
    error: str | None = None
    try:
        locations = await client.list_external_locations()
    except CatalogUnavailableError as exc:
        error = exc.detail
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/external_locations.html",
        {
            "locations": locations,
            "error": error,
            "active_page": "external_locations",
            "list_page": True,
        },
    )


@app.get("/external-locations/{name}", response_class=HTMLResponse)
async def external_location_detail(request: Request, name: str) -> HTMLResponse:
    """Show a single external location (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    location: dict[str, Any] | None = None
    error: str | None = None
    try:
        location = await client.get_external_location(name)
    except CatalogUnavailableError as exc:
        error = exc.detail
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/external_location.html",
        {"location": location, "name": name, "error": error, "active_page": "external_locations"},
    )


@app.get("/credentials", response_class=HTMLResponse)
async def credentials_index(request: Request) -> HTMLResponse:
    """List all credentials (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    credentials: list[dict[str, Any]] = []
    error: str | None = None
    try:
        credentials = await client.list_credentials()
    except CatalogUnavailableError as exc:
        error = exc.detail
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/credentials.html",
        {
            "credentials": credentials,
            "error": error,
            "active_page": "credentials",
            "list_page": True,
        },
    )


@app.get("/credentials/{name}", response_class=HTMLResponse)
async def credential_detail(request: Request, name: str) -> HTMLResponse:
    """Show a single credential (admin-only)."""
    _require_admin(request)
    client = _get_uc_client(request)
    credential: dict[str, Any] | None = None
    error: str | None = None
    try:
        credential = await client.get_credential(name)
    except CatalogUnavailableError as exc:
        error = exc.detail
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/credential.html",
        {"credential": credential, "name": name, "error": error, "active_page": "credentials"},
    )


# -- Jobs / scheduler --


_JOB_REGISTRY = scheduler_service.build_default_registry()


def _serialize_job(job: Any, last_run: Any = None) -> dict[str, Any]:
    """Render a :class:`Job` ORM row for JSON responses.

    Pulled out into a helper so both the list and the detail route
    emit the same shape; the helper assumes the ORM row has been
    detached from its session or the caller still holds the session
    open (we never serialize half-loaded jobs).

    When *last_run* is supplied (typically from
    :func:`_latest_run_per_job`), the ``last_run_*`` fields are
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
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "last_run_status": last_status,
        "last_run_at": last_at,
        "last_run_duration_s": last_duration,
    }


def _latest_run_per_job(session: Any, job_ids: list[int]) -> dict[int, Any]:
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
    from sqlalchemy import and_, func
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


def _serialize_task(task: Any) -> dict[str, Any]:
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
    }


def _serialize_task_run(tr: Any) -> dict[str, Any]:
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


def _serialize_run(run: Any) -> dict[str, Any]:
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
        "duration_seconds": duration,
    }


def _load_job_or_404(request: Request, job_id: int) -> Any:
    """Fetch a :class:`Job` with ownership-aware visibility rules.

    Admins see every job; non-admins see only jobs whose
    ``run_as_user_id`` matches their user id. A missing or hidden job
    surfaces as :class:`CatalogNotFoundError` so the centralized
    error handler renders 404 consistently.
    """
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.models import Job as JobModel

    user = _get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        job = session.get(JobModel, job_id)
        if job is None:
            raise CatalogNotFoundError(f"Job {job_id} not found")
        if not user.get("is_admin") and job.run_as_user_id != user["id"]:
            raise CatalogNotFoundError(f"Job {job_id} not found")
        session.expunge(job)
        return job


def _require_job_owner_or_admin(request: Request, job: Any) -> None:
    """Raise :class:`AuthorizationError` if the user can't mutate *job*."""
    user = _get_user(request)
    if user.get("is_admin"):
        return
    if job.run_as_user_id == user["id"]:
        return
    raise AuthorizationError(
        principal=user.get("email", ""),
        privilege="manage",
        securable_type="job",
        full_name=str(job.name),
    )


@app.get("/api/jobs")
async def api_list_jobs(request: Request) -> list[dict[str, Any]]:
    """Return jobs visible to the current user.

    Admin sees everything; a regular user only sees jobs whose
    ``run_as_user_id`` matches their user id, matching the detail-page
    visibility so the two surfaces cannot drift.
    """
    from sqlalchemy import select as _select

    from pointlessql.models import Job as JobModel

    user = _get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = _select(JobModel).order_by(JobModel.id)
        if not user.get("is_admin"):
            stmt = stmt.where(JobModel.run_as_user_id == user["id"])
        rows = list(session.scalars(stmt).all())
        latest = _latest_run_per_job(session, [r.id for r in rows])
        for row in rows:
            session.expunge(row)
    return [_serialize_job(r, last_run=latest.get(r.id)) for r in rows]


@app.post("/api/jobs")
async def api_create_job(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Create a new job (admin-only).

    Two shapes are accepted:

    * Single-task (Sprint 19 compatibility):
      ``{name, cron_expr, kind, config, ...}`` — the scheduler walks
      ``job.kind`` / ``job.config`` directly.
    * DAG (Sprint 20):
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

    _require_admin(request)
    user = _get_user(request)

    name = body.get("name")
    cron_expr = body.get("cron_expr")
    if not name or not cron_expr:
        raise _VE("name and cron_expr are required")
    if not _croniter.is_valid(str(cron_expr)):
        raise _VE(f"Invalid cron expression: {cron_expr!r}")

    tasks_payload = body.get("tasks")
    if tasks_payload is not None and not isinstance(tasks_payload, list):
        raise _VE("tasks must be a JSON array when provided")

    # Single-task shortcut: validate kind + config just like Sprint 19.
    if not tasks_payload:
        kind = body.get("kind")
        if not kind:
            raise _VE("kind is required when 'tasks' is not provided")
        _JOB_REGISTRY.get(str(kind))
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
            _JOB_REGISTRY.get(str(t_kind))
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
        # and the job row never lands in the DB (Sprint 23 BUG-23-02).
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
    _audit(request, "create_job", f"job:{name}", json.dumps(body))
    return _serialize_job(job)


@app.post("/api/jobs/{job_id}/run")
async def api_run_job(request: Request, job_id: int) -> dict[str, Any]:
    """Manually trigger a run of *job_id* (admin or owner only)."""
    job = _load_job_or_404(request, job_id)
    _require_job_owner_or_admin(request, job)
    settings: Settings = request.app.state.settings
    factory = request.app.state.session_factory
    run = await scheduler_service.execute_run(factory, settings, _JOB_REGISTRY, job_id, "manual")
    _audit(request, "run_job", f"job:{job.name}")
    return _serialize_run(run)


@app.get("/api/jobs/{job_id}/tasks")
async def api_list_job_tasks(request: Request, job_id: int) -> list[dict[str, Any]]:
    """Return the :class:`JobTask` DAG nodes for *job_id*."""
    from sqlalchemy import select as _select

    from pointlessql.models import JobTask as JobTaskModel

    _load_job_or_404(request, job_id)
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = _select(JobTaskModel).where(JobTaskModel.job_id == job_id).order_by(JobTaskModel.id)
        rows = list(session.scalars(stmt).all())
        for r in rows:
            session.expunge(r)
    return [_serialize_task(r) for r in rows]


@app.get("/api/jobs/{job_id}/runs/{run_id}/tasks")
async def api_list_task_runs(request: Request, job_id: int, run_id: int) -> list[dict[str, Any]]:
    """Return per-task state rows for one :class:`JobRun`."""
    from sqlalchemy import select as _select

    from pointlessql.models import TaskRun as TaskRunModel

    _load_job_or_404(request, job_id)
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = (
            _select(TaskRunModel).where(TaskRunModel.job_run_id == run_id).order_by(TaskRunModel.id)
        )
        rows = list(session.scalars(stmt).all())
        for r in rows:
            session.expunge(r)
    return [_serialize_task_run(r) for r in rows]


@app.get("/api/jobs/{job_id}/runs/{run_id}/logs")
async def api_list_job_logs(
    request: Request,
    job_id: int,
    run_id: int,
    task_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return log lines for one :class:`JobRun`, optionally filtered by task.

    The log panel on the job detail page fetches this endpoint via
    Alpine.js when the user expands a row; ``task_id`` lets the panel
    scope the view to one DAG node.
    """
    from sqlalchemy import select as _select

    from pointlessql.models import JobLog as JobLogModel

    _load_job_or_404(request, job_id)
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = _select(JobLogModel).where(JobLogModel.job_run_id == run_id)
        if task_id is not None:
            stmt = stmt.where(JobLogModel.task_id == task_id)
        stmt = stmt.order_by(JobLogModel.id)
        rows = list(session.scalars(stmt).all())
        for r in rows:
            session.expunge(r)
    return [
        {
            "id": r.id,
            "job_run_id": r.job_run_id,
            "task_id": r.task_id,
            "ts": r.ts.isoformat() if r.ts else None,
            "level": r.level,
            "message": r.message,
        }
        for r in rows
    ]


def _load_papermill_run_output_path(request: Request, job_id: int, run_id: int) -> Path:
    """Validate *run_id* belongs to papermill *job_id* and return its runs dir.

    Shared validator for the inline render route and the download route.
    Both need the same three checks: caller can see the job, the job is a
    papermill job, and *run_id* really belongs to *job_id*.

    Args:
        request: Incoming FastAPI request; visibility is enforced via
            :func:`_load_job_or_404`.
        job_id: The :class:`Job` id from the URL path.
        run_id: The :class:`JobRun` id from the URL path.

    Returns:
        The absolute ``runs/`` directory where ``{run_id}.ipynb`` lives.

    Raises:
        CatalogNotFoundError: If the job is not visible to the caller,
            the run does not belong to the job, or the job is not a
            papermill kind.
    """
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.models import JobRun as JobRunModel

    job = _load_job_or_404(request, job_id)
    if job.kind != "papermill":
        raise CatalogNotFoundError(f"Job {job_id} is not a papermill job")
    factory = request.app.state.session_factory
    with factory() as session:
        run = session.get(JobRunModel, run_id)
        if run is None or run.job_id != job_id:
            raise CatalogNotFoundError(f"Run {run_id} not found for job {job_id}")
    settings: Settings = request.app.state.settings
    return settings.jupyter.notebooks_dir.resolve() / "runs"


@app.get("/jobs/{job_id}/runs/{run_id}/notebook", response_class=HTMLResponse)
async def job_run_notebook(
    request: Request,
    job_id: int,
    run_id: int,
    exclude_input: bool = False,
) -> HTMLResponse:
    """Render an executed Papermill notebook inline.

    Returns the nbconvert ``lab``-template HTML body for
    ``{notebooks_dir}/runs/{run_id}.ipynb``. The job-detail page embeds
    this route in an iframe inside the "Output artifacts" card. A
    ``runs/{run_id}.html`` sidecar is written on first render so
    subsequent hits skip the nbconvert cost.

    When ``exclude_input=true`` is passed as a query param, the render
    hides code cells and caches to a sibling ``{run_id}.dashboard.html``
    sidecar — used by the Sprint 28 dashboard iframe to publish
    output-only views of the latest succeeded run.
    """
    runs_dir = _load_papermill_run_output_path(request, job_id, run_id)
    html = notebook_render_service.render_run_notebook(
        runs_dir, run_id, exclude_input=exclude_input
    )
    return HTMLResponse(html)


@app.get("/jobs/{job_id}/runs/{run_id}/notebook/download")
async def job_run_notebook_download(
    request: Request,
    job_id: int,
    run_id: int,
    format: Literal["ipynb", "html"] = "ipynb",
) -> FileResponse:
    """Download the raw ipynb or cached-HTML sidecar for a run.

    Sprint 26 chose a visibility-checked route over a StaticFiles mount
    so non-owner logged-in users cannot guess ``run_id`` values and
    exfiltrate another user's job output. ``format=html`` triggers a
    render if the sidecar is not yet present.
    """
    from pointlessql.exceptions import CatalogNotFoundError

    runs_dir = _load_papermill_run_output_path(request, job_id, run_id)
    if format == "html":
        # Ensure the sidecar exists before serving it.
        notebook_render_service.render_run_notebook(runs_dir, run_id)
        path = runs_dir / f"{run_id}.html"
        media_type = "text/html"
    else:
        path = runs_dir / f"{run_id}.ipynb"
        media_type = "application/x-ipynb+json"
    if not path.is_file():
        raise CatalogNotFoundError(f"Run {run_id} {format} artifact not found")
    return FileResponse(
        path,
        filename=f"job{job_id}_run{run_id}.{format}",
        media_type=media_type,
    )


@app.get("/jobs/{job_id}/runs/{run_id}/compare", response_class=HTMLResponse)
async def job_run_compare(
    request: Request,
    job_id: int,
    run_id: int,
    to: int,
) -> HTMLResponse:
    """Render two executed notebooks side-by-side for the same papermill job.

    Both runs must belong to ``job_id`` — this prevents leaking a peek
    at a different job's output by smuggling a foreign ``to=`` run id
    through the query string. The page itself embeds two Sprint 26
    ``/jobs/{id}/runs/{rid}/notebook`` iframes; no cell-level diffing
    (stub — that is a future sprint if demand emerges).
    """
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.models import JobRun as JobRunModel

    job = _load_job_or_404(request, job_id)
    if job.kind != "papermill":
        raise CatalogNotFoundError(f"Job {job_id} is not a papermill job")
    factory = request.app.state.session_factory
    with factory() as session:
        left = session.get(JobRunModel, run_id)
        right = session.get(JobRunModel, to)
        if left is None or left.job_id != job_id:
            raise CatalogNotFoundError(f"Run {run_id} not found for job {job_id}")
        if right is None or right.job_id != job_id:
            raise CatalogNotFoundError(f"Run {to} not found for job {job_id}")
        session.expunge(left)
        session.expunge(right)
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/run_compare.html",
        {
            "job": _serialize_job(job),
            "left": _serialize_run(left),
            "right": _serialize_run(right),
            "active_page": "jobs",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


# -- Dashboards (Sprint 28) --
# A dashboard is a stable slug-addressable view of a notebook job's
# latest succeeded run, rendered with ``exclude_input=True`` so
# consumers see outputs only. The ``job_id`` FK is nullable so a
# dashboard can outlive its bound job (FK uses ``ON DELETE SET NULL``);
# when no job is bound or no successful run exists, the detail page
# renders an empty state.


_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,199}$")


def _serialize_dashboard(dashboard: Any, *, latest_run_id: int | None = None) -> dict[str, Any]:
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


def _load_dashboard_or_404(request: Request, slug: str) -> Any:
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


def _latest_succeeded_run_id(request: Request, job_id: int) -> int | None:
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


@app.get("/api/dashboards")
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
    return [_serialize_dashboard(r) for r in rows]


@app.get("/api/dashboards/tree")
async def api_dashboards_tree(request: Request) -> list[dict[str, Any]]:
    """Return a flat list shaped for the dashboards sidebar component.

    The shape mirrors the Sprint 27 workspace tree enough that the
    Alpine component is a straightforward copy. ``/api/dashboards``
    already returns the same rows — the dedicated tree endpoint keeps
    the Alpine fetch call symmetrical with the catalog tree.
    """
    return await api_list_dashboards(request)


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


@app.post("/api/dashboards")
async def api_create_dashboard(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Create a new dashboard (admin-only)."""
    from pointlessql.models import Dashboard as DashboardModel

    _require_admin(request)
    user = _get_user(request)

    slug_raw = body.get("slug")
    title = body.get("title")
    notebook_path = body.get("notebook_path")
    if not slug_raw or not title or not notebook_path:
        raise ValidationError("slug, title and notebook_path are required")
    slug = str(slug_raw).strip()
    if not _SLUG_PATTERN.match(slug):
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
    _audit(request, "create_dashboard", f"dashboard:{slug}", json.dumps(body))
    return _serialize_dashboard(dashboard)


@app.patch("/api/dashboards/{slug}")
async def api_update_dashboard(
    request: Request, slug: str, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Update mutable dashboard fields (admin-only).

    Editable: title, description, notebook_path, job_id. slug and
    owner_id are immutable — delete + recreate if the URL or owner
    needs to change so callers never observe a half-migrated row.
    """
    from pointlessql.models import Dashboard as DashboardModel

    _require_admin(request)
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
    _audit(request, "update_dashboard", f"dashboard:{slug}", json.dumps(body))
    return _serialize_dashboard(row)


@app.delete("/api/dashboards/{slug}")
async def api_delete_dashboard(request: Request, slug: str) -> dict[str, str]:
    """Delete a dashboard (admin-only)."""
    from pointlessql.models import Dashboard as DashboardModel

    _require_admin(request)
    factory = request.app.state.session_factory
    with factory() as session:
        from sqlalchemy import select as _select

        row = session.scalar(_select(DashboardModel).where(DashboardModel.slug == slug))
        if row is None:
            from pointlessql.exceptions import CatalogNotFoundError as _NF

            raise _NF(f"Dashboard {slug!r} not found")
        session.delete(row)
        session.commit()
    _audit(request, "delete_dashboard", f"dashboard:{slug}")
    return {"status": "deleted", "slug": slug}


@app.post("/api/dashboards/{slug}/refresh")
async def api_refresh_dashboard(request: Request, slug: str) -> dict[str, Any]:
    """Trigger a manual run of the bound job (admin-only).

    Thin wrapper over the scheduler's manual-run helper that powers
    the job-detail "Run now" button — no new execution concept, just
    a shortcut for the dashboard consumer UI.
    """
    _require_admin(request)
    dashboard = _load_dashboard_or_404(request, slug)
    if dashboard.job_id is None:
        raise ValidationError("dashboard has no bound job to refresh")
    settings: Settings = request.app.state.settings
    factory = request.app.state.session_factory
    run = await scheduler_service.execute_run(
        factory, settings, _JOB_REGISTRY, dashboard.job_id, "manual"
    )
    _audit(request, "refresh_dashboard", f"dashboard:{slug}")
    return _serialize_run(run)


@app.get("/dashboards", response_class=HTMLResponse)
async def dashboards_index(request: Request) -> HTMLResponse:
    """Render the dashboards list page (any logged-in user)."""
    from sqlalchemy import select as _select

    from pointlessql.models import Dashboard as DashboardModel
    from pointlessql.models import Job as JobModel

    user = _get_user(request)
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
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/dashboards.html",
        {
            "dashboards": [_serialize_dashboard(d) for d in dashboards],
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


@app.get("/dashboards/{slug}", response_class=HTMLResponse)
async def dashboard_detail(request: Request, slug: str) -> HTMLResponse:
    """Render a dashboard's latest-run output (any logged-in user).

    The iframe src points at :func:`dashboard_output` so the visibility
    boundary is the dashboard itself, not the underlying job — dashboards
    are a consumer/publishing surface. When the bound job has never
    produced a succeeded run — or there is no bound job at all — the
    page renders an empty state instead.
    """
    user = _get_user(request)
    dashboard = _load_dashboard_or_404(request, slug)
    latest_run_id: int | None = None
    if dashboard.job_id is not None:
        latest_run_id = _latest_succeeded_run_id(request, dashboard.job_id)
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/dashboard_detail.html",
        {
            "dashboard": _serialize_dashboard(dashboard, latest_run_id=latest_run_id),
            "is_admin": user.get("is_admin", False),
            "active_page": "dashboards",
            "active_dashboard_slug": slug,
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@app.get("/dashboards/{slug}/output", response_class=HTMLResponse)
async def dashboard_output(request: Request, slug: str) -> HTMLResponse:
    """Render the code-hidden HTML of the dashboard's latest succeeded run.

    This is the iframe source for the dashboard detail page. Unlike
    :func:`job_run_notebook` it does **not** go through
    :func:`_load_papermill_run_output_path` — which enforces
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

    dashboard = _load_dashboard_or_404(request, slug)
    if dashboard.job_id is None:
        raise CatalogNotFoundError(f"Dashboard {slug!r} has no bound job")
    latest_run_id = _latest_succeeded_run_id(request, dashboard.job_id)
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
    runs_dir = settings.jupyter.notebooks_dir.resolve() / "runs"
    html = notebook_render_service.render_run_notebook(runs_dir, latest_run_id, exclude_input=True)
    return HTMLResponse(html)


@app.post("/api/jobs/{job_id}/pause")
async def api_pause_job(request: Request, job_id: int) -> dict[str, Any]:
    """Pause *job_id* (admin or owner only)."""
    from pointlessql.models import Job as JobModel

    job = _load_job_or_404(request, job_id)
    _require_job_owner_or_admin(request, job)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(JobModel, job_id)
        assert row is not None
        row.is_paused = True
        row.updated_at = datetime.now(UTC)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    _audit(request, "pause_job", f"job:{row.name}")
    return _serialize_job(row)


@app.post("/api/jobs/{job_id}/unpause")
async def api_unpause_job(request: Request, job_id: int) -> dict[str, Any]:
    """Resume *job_id* (admin or owner only)."""
    from pointlessql.models import Job as JobModel

    job = _load_job_or_404(request, job_id)
    _require_job_owner_or_admin(request, job)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(JobModel, job_id)
        assert row is not None
        row.is_paused = False
        row.updated_at = datetime.now(UTC)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    _audit(request, "unpause_job", f"job:{row.name}")
    return _serialize_job(row)


@app.get("/jobs", response_class=HTMLResponse)
async def jobs_index(request: Request) -> HTMLResponse:
    """List every job visible to the current user."""
    from sqlalchemy import select as _select

    from pointlessql.models import Job as JobModel

    user = _get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = _select(JobModel).order_by(JobModel.id)
        if not user.get("is_admin"):
            stmt = stmt.where(JobModel.run_as_user_id == user["id"])
        rows = list(session.scalars(stmt).all())
        latest = _latest_run_per_job(session, [r.id for r in rows])
        for row in rows:
            session.expunge(row)
    jobs_data = [_serialize_job(r, last_run=latest.get(r.id)) for r in rows]
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/jobs.html",
        {
            "jobs": jobs_data,
            "is_admin": user.get("is_admin", False),
            "current_user_id": user.get("id"),
            "active_page": "jobs",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
            "list_page": True,
        },
    )


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
            "action": r.action,
            "target": r.target,
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


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_detail(request: Request, job_id: int) -> HTMLResponse:
    """Render job detail with task list, latest task statuses, and run history."""
    from sqlalchemy import select as _select

    from pointlessql.models import JobRun as JobRunModel
    from pointlessql.models import JobTask as JobTaskModel
    from pointlessql.models import TaskRun as TaskRunModel

    job = _load_job_or_404(request, job_id)
    user = _get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        runs_stmt = (
            _select(JobRunModel)
            .where(JobRunModel.job_id == job_id)
            .order_by(JobRunModel.started_at.desc())
            .limit(20)
        )
        runs = list(session.scalars(runs_stmt).all())
        for r in runs:
            session.expunge(r)

        tasks_stmt = (
            _select(JobTaskModel).where(JobTaskModel.job_id == job_id).order_by(JobTaskModel.id)
        )
        tasks = list(session.scalars(tasks_stmt).all())
        for t in tasks:
            session.expunge(t)

        # Fetch the latest :class:`TaskRun` per task so the table can
        # show current status + retry count without a second round-trip.
        latest_task_runs: dict[int, Any] = {}
        if runs and tasks:
            latest_run_id = runs[0].id
            tr_stmt = _select(TaskRunModel).where(TaskRunModel.job_run_id == latest_run_id)
            for tr in session.scalars(tr_stmt).all():
                session.expunge(tr)
                latest_task_runs[tr.task_id] = tr

    can_manage = user.get("is_admin", False) or job.run_as_user_id == user.get("id")

    task_rows: list[dict[str, Any]] = []
    for t in tasks:
        tr = latest_task_runs.get(t.id)
        task_rows.append(
            {
                **_serialize_task(t),
                "latest_status": tr.status if tr is not None else None,
                "latest_attempts": tr.attempts if tr is not None else 0,
                "latest_error": tr.error if tr is not None else None,
                "latest_run_id": tr.job_run_id if tr is not None else None,
            }
        )

    return _TEMPLATES.TemplateResponse(
        request,
        "pages/job_detail.html",
        {
            "job": _serialize_job(job),
            "runs": [_serialize_run(r) for r in runs],
            "tasks": task_rows,
            "can_manage": can_manage,
            "jupyter_port": _startup_settings.jupyter.port,
            "active_page": "jobs",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


def cli() -> None:
    """Run the development server."""
    import uvicorn

    settings = Settings()
    uvicorn.run(
        "pointlessql.api.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=True,
    )
