"""FastAPI entrypoint for PointlesSQL."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Body, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pointlessql.api.auth_routes import router as auth_router
from pointlessql.db import get_session_factory, init_db
from pointlessql.exceptions import AuthorizationError, CatalogUnavailableError
from pointlessql.logging_config import configure_logging, request_id_var
from pointlessql.services import audit as audit_service
from pointlessql.services import auth as auth_service
from pointlessql.services import pg_sync as pg_sync_service
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
from pointlessql.services.soyuz_client import make_soyuz_client
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.settings import Settings
from pointlessql.types import UserInfo

# Configure logging at module import time so it takes effect in every
# process that serves traffic — the uvicorn --reload worker imports
# this module but does not go through cli(). Idempotent; subsequent
# calls replace our own handlers without disturbing pytest's caplog.
_startup_settings = Settings()
configure_logging(_startup_settings.log_level, _startup_settings.log_format)

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
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC).strftime(
            "%Y-%m-%d %H:%M UTC"
        )
    except (TypeError, ValueError):
        return str(value)


_TEMPLATES.env.filters["epoch_ms"] = _format_epoch_ms


_original_template_response = _TEMPLATES.TemplateResponse


def _template_response_with_user(request: Request, *args: Any, **kwargs: Any) -> Response:
    """Wrap TemplateResponse to inject ``current_user`` into every context."""
    # TemplateResponse(request, name, context) or (name, context, request=request)
    # Starlette 0.37+ signature: TemplateResponse(request, name, context={}, ...)
    if "context" in kwargs:
        kwargs["context"].setdefault(
            "current_user", getattr(request.state, "user", None)
        )
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
        settings.host,
        settings.port,
        settings.engine,
        settings.log_format,
    )
    soyuz = make_soyuz_client(settings)
    app.state.uc_client = UnityCatalogClient(soyuz)
    app.state.settings = settings
    app.state.templates = _TEMPLATES

    init_db(settings.database_url)
    app.state.session_factory = get_session_factory()

    async with managed_jupyter(settings) as jupyter_proc:
        app.state.jupyter_process = jupyter_proc
        try:
            yield
        finally:
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
            user = auth_service.get_current_user(factory, token, settings.secret_key)
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
        return UnityCatalogClient.for_principal(
            request.app.state.settings, user["email"]
        )
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
        audit_service.log_action(
            factory, user["id"], user["email"], action, target, detail
        )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Return service health."""
    return {"status": "ok"}


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
async def api_schemas(
    request: Request, catalog_name: str
) -> list[dict[str, object]]:
    """Return schemas inside a catalog as JSON."""
    client = _get_uc_client(request)
    user = _get_user(request)
    await check_privilege(
        client, user.get("email", ""), user.get("is_admin", False),
        "catalog", catalog_name, USE_CATALOG,
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
        client, user.get("email", ""), user.get("is_admin", False),
        "schema", f"{catalog_name}.{schema_name}", USE_SCHEMA,
    )
    return await client.list_tables(catalog_name, schema_name)


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
    _audit(
        request, "create_catalog", f"catalog:{body.get('name', '?')}", json.dumps(body)
    )
    return result


@app.post("/api/catalogs/{catalog_name}/sync")
async def api_sync_catalog(
    request: Request, catalog_name: str
) -> dict[str, object]:
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
        client, user.get("email", ""), user.get("is_admin", False),
        "catalog", catalog_name, MODIFY,
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
        client, user.get("email", ""), user.get("is_admin", False),
        "schema", full_name, MODIFY,
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
        client, user.get("email", ""), user.get("is_admin", False),
        securable_type, full_name, MODIFY,
    )
    result = await client.update_tags(
        securable_type, full_name, body.get("changes", [])
    )
    _audit(
        request, "update_tags", f"{securable_type}:{full_name}",
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
        client, user.get("email", ""), user.get("is_admin", False),
        securable_type, full_name, MANAGE_GRANTS,
    )
    result = await client.update_permissions(
        securable_type, full_name, body.get("changes", [])
    )
    _audit(
        request, "update_permissions", f"{securable_type}:{full_name}",
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
async def api_lineage(
    request: Request, full_name: str, depth: int = 3
) -> dict[str, object]:
    """Return combined upstream/downstream lineage for a table."""
    client = _get_uc_client(request)
    user = _get_user(request)
    await check_privilege(
        client, user.get("email", ""), user.get("is_admin", False),
        "table", full_name, SELECT,
    )
    return await client.get_lineage(full_name, depth)


# -- HTML pages --


@app.get("/", response_class=HTMLResponse)
async def catalogs_index(request: Request) -> HTMLResponse:
    """Render the welcome screen with the catalog count.

    Also fetches the connection list for admins so the "Create foreign
    catalog" modal has a pre-populated dropdown. Non-admins see the
    welcome screen without the create button.
    """
    client = _get_uc_client(request)
    user = _get_user(request)
    catalog_count = 0
    connections: list[dict[str, Any]] = []
    error: str | None = None
    try:
        catalog_count = len(await client.list_catalogs())
        if user.get("is_admin", False):
            connections = await client.list_connections()
    except CatalogUnavailableError as exc:
        error = exc.detail
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/catalogs.html",
        {
            "catalog_count": catalog_count,
            "connections": connections,
            "is_admin": user.get("is_admin", False),
            "error": error,
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
    error: str | None = None
    try:
        catalog, tags, permissions, effective = await asyncio.gather(
            client.get_catalog(catalog_name),
            client.get_tags("catalog", catalog_name),
            client.get_permissions("catalog", catalog_name),
            client.get_effective_permissions("catalog", catalog_name),
        )
    except CatalogUnavailableError as exc:
        error = exc.detail

    # Enforce after gather so we reuse the effective permissions data.
    # AuthorizationError propagates to the centralized handler → 403.html.
    if error is None:
        check_privilege_from_effective(
            effective, user.get("email", ""), user.get("is_admin", False),
            "catalog", catalog_name, USE_CATALOG,
        )

    can_manage = has_privilege(
        effective, user.get("email", ""), user.get("is_admin", False), MANAGE_GRANTS,
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
async def schema_detail(
    request: Request, catalog_name: str, schema_name: str
) -> HTMLResponse:
    """Render metadata for a single schema."""
    client = _get_uc_client(request)
    user = _get_user(request)
    schema: dict[str, Any] | None = None
    tags: list[dict[str, Any]] = []
    permissions: list[dict[str, Any]] = []
    effective: list[dict[str, Any]] = []
    error: str | None = None
    full_name = f"{catalog_name}.{schema_name}"
    try:
        schema, tags, permissions, effective = await asyncio.gather(
            client.get_schema(catalog_name, schema_name),
            client.get_tags("schema", full_name),
            client.get_permissions("schema", full_name),
            client.get_effective_permissions("schema", full_name),
        )
    except CatalogUnavailableError as exc:
        error = exc.detail

    if error is None:
        check_privilege_from_effective(
            effective, user.get("email", ""), user.get("is_admin", False),
            "schema", full_name, USE_SCHEMA,
        )

    can_manage = has_privilege(
        effective, user.get("email", ""), user.get("is_admin", False), MANAGE_GRANTS,
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
            effective, user.get("email", ""), user.get("is_admin", False),
            "table", full_name, SELECT,
        )

    can_manage = has_privilege(
        effective, user.get("email", ""), user.get("is_admin", False), MANAGE_GRANTS,
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
            "jupyter_enabled": settings.jupyter_enabled,
            "jupyter_port": settings.jupyter_port,
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
        "enabled": settings.jupyter_enabled,
        "running": running,
        "port": settings.jupyter_port,
    }


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
        {"connections": connections, "error": error, "active_page": "connections"},
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
        {"locations": locations, "error": error, "active_page": "external_locations"},
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
        {"credentials": credentials, "error": error, "active_page": "credentials"},
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


def cli() -> None:
    """Run the development server."""
    import uvicorn

    settings = Settings()
    uvicorn.run("pointlessql.api.main:app", host=settings.host, port=settings.port, reload=True)
