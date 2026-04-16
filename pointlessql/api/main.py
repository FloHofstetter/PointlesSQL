"""FastAPI entrypoint for PointlesSQL."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import Body, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from soyuz_catalog_client.errors import UnexpectedStatus

from pointlessql.api.auth_routes import router as auth_router
from pointlessql.db import get_session_factory, init_db
from pointlessql.services import auth as auth_service
from pointlessql.services.jupyter import managed_jupyter
from pointlessql.services.soyuz_client import make_soyuz_client
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.settings import Settings

_FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
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


def _template_response_with_user(request, *args, **kwargs):
    """Wrap TemplateResponse to inject ``current_user`` into every context."""
    # TemplateResponse(request, name, context) or (name, context, request=request)
    # Starlette 0.37+ signature: TemplateResponse(request, name, context={}, ...)
    if "context" in kwargs:
        kwargs["context"].setdefault(
            "current_user", getattr(request.state, "user", None)
        )
    elif len(args) >= 2 and isinstance(args[1], dict):
        args = list(args)
        args[1].setdefault("current_user", getattr(request.state, "user", None))
        args = tuple(args)
    return _original_template_response(request, *args, **kwargs)


_TEMPLATES.TemplateResponse = _template_response_with_user  # type: ignore[assignment]


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create shared services and manage the Jupyter subprocess."""
    settings = Settings()
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
app.include_router(auth_router)
app.mount(
    "/static",
    StaticFiles(directory=str(_FRONTEND_DIR)),
    name="static",
)

# Paths that do not require authentication.
_PUBLIC_PREFIXES = ("/auth/", "/static/", "/healthz")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
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


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Return service health."""
    return {"status": "ok"}


@app.get("/api/tree", response_model=None)
async def api_tree(request: Request) -> list[dict[str, object]] | JSONResponse:
    """Return the full catalog/schema/table tree for the sidebar."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        return await client.get_tree()
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


@app.get("/api/catalogs", response_model=None)
async def api_catalogs(request: Request) -> list[dict[str, object]] | JSONResponse:
    """Return all catalogs as JSON."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        return await client.list_catalogs()
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


@app.get("/api/catalogs/{catalog_name}/schemas", response_model=None)
async def api_schemas(
    request: Request, catalog_name: str
) -> list[dict[str, object]] | JSONResponse:
    """Return schemas inside a catalog as JSON."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        return await client.list_schemas(catalog_name)
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


@app.get("/api/catalogs/{catalog_name}/schemas/{schema_name}/tables", response_model=None)
async def api_tables(
    request: Request, catalog_name: str, schema_name: str
) -> list[dict[str, object]] | JSONResponse:
    """Return tables inside a schema as JSON."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        return await client.list_tables(catalog_name, schema_name)
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


@app.patch("/api/catalogs/{catalog_name}", response_model=None)
async def api_update_catalog(
    request: Request,
    catalog_name: str,
    patch: dict[str, Any] = Body(...),
) -> dict[str, object] | JSONResponse:
    """Apply a partial update to a catalog."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        return await client.update_catalog(catalog_name, patch)
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


@app.patch("/api/catalogs/{catalog_name}/schemas/{schema_name}", response_model=None)
async def api_update_schema(
    request: Request,
    catalog_name: str,
    schema_name: str,
    patch: dict[str, Any] = Body(...),
) -> dict[str, object] | JSONResponse:
    """Apply a partial update to a schema."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        return await client.update_schema(catalog_name, schema_name, patch)
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


@app.get("/api/tags/{securable_type}/{full_name:path}", response_model=None)
async def api_get_tags(
    request: Request, securable_type: str, full_name: str
) -> list[dict[str, object]] | JSONResponse:
    """Return tags for a securable."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        return await client.get_tags(securable_type, full_name)
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


@app.patch("/api/tags/{securable_type}/{full_name:path}", response_model=None)
async def api_update_tags(
    request: Request,
    securable_type: str,
    full_name: str,
    body: dict[str, Any] = Body(...),
) -> list[dict[str, object]] | JSONResponse:
    """Update tags for a securable. Body: {"changes": [...]}."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        return await client.update_tags(
            securable_type, full_name, body.get("changes", [])
        )
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


@app.get("/api/permissions/{securable_type}/{full_name:path}", response_model=None)
async def api_get_permissions(
    request: Request, securable_type: str, full_name: str
) -> list[dict[str, object]] | JSONResponse:
    """Return privilege assignments for a securable."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        return await client.get_permissions(securable_type, full_name)
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


@app.patch("/api/permissions/{securable_type}/{full_name:path}", response_model=None)
async def api_update_permissions(
    request: Request,
    securable_type: str,
    full_name: str,
    body: dict[str, Any] = Body(...),
) -> list[dict[str, object]] | JSONResponse:
    """Update permissions for a securable. Body: {"changes": [...]}."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        return await client.update_permissions(
            securable_type, full_name, body.get("changes", [])
        )
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


@app.get("/api/effective-permissions/{securable_type}/{full_name:path}", response_model=None)
async def api_get_effective_permissions(
    request: Request, securable_type: str, full_name: str
) -> list[dict[str, object]] | JSONResponse:
    """Return effective (inherited) permissions for a securable."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        return await client.get_effective_permissions(securable_type, full_name)
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


@app.get("/api/lineage/{full_name:path}", response_model=None)
async def api_lineage(
    request: Request, full_name: str, depth: int = 3
) -> dict[str, object] | JSONResponse:
    """Return combined upstream/downstream lineage for a table."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        return await client.get_lineage(full_name, depth)
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


@app.get("/", response_class=HTMLResponse)
async def catalogs_index(request: Request) -> HTMLResponse:
    """Render the welcome screen with the catalog count."""
    client: UnityCatalogClient = request.app.state.uc_client
    catalog_count = 0
    error: str | None = None
    try:
        catalog_count = len(await client.list_catalogs())
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        error = str(exc)
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/catalogs.html",
        {
            "catalog_count": catalog_count,
            "error": error,
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@app.get("/catalogs/{catalog_name}", response_class=HTMLResponse)
async def catalog_detail(request: Request, catalog_name: str) -> HTMLResponse:
    """Render metadata for a single catalog."""
    client: UnityCatalogClient = request.app.state.uc_client
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
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        error = str(exc)
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/schemas.html",
        {
            "catalog_name": catalog_name,
            "catalog": catalog,
            "tags": tags,
            "permissions": permissions,
            "effective": effective,
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
    client: UnityCatalogClient = request.app.state.uc_client
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
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        error = str(exc)
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
    client: UnityCatalogClient = request.app.state.uc_client
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
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        error = str(exc)
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


@app.get("/api/connections", response_model=None)
async def api_list_connections(
    request: Request,
) -> list[dict[str, object]] | JSONResponse:
    """Return all connections."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        return await client.list_connections()
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


@app.post("/api/connections", response_model=None)
async def api_create_connection(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, object] | JSONResponse:
    """Create a new connection."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        return await client.create_connection(body)
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


@app.get("/api/connections/{name}", response_model=None)
async def api_get_connection(
    request: Request, name: str
) -> dict[str, object] | JSONResponse:
    """Return a single connection."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        return await client.get_connection(name)
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


@app.patch("/api/connections/{name}", response_model=None)
async def api_update_connection(
    request: Request, name: str, body: dict[str, Any] = Body(...)
) -> dict[str, object] | JSONResponse:
    """Update a connection."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        return await client.update_connection(name, body)
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


@app.delete("/api/connections/{name}", response_model=None)
async def api_delete_connection(
    request: Request, name: str
) -> dict[str, str] | JSONResponse:
    """Delete a connection."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        await client.delete_connection(name)
        return {"status": "deleted"}
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


# -- Federation: External Locations --


@app.get("/api/external-locations", response_model=None)
async def api_list_external_locations(
    request: Request,
) -> list[dict[str, object]] | JSONResponse:
    """Return all external locations."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        return await client.list_external_locations()
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


@app.post("/api/external-locations", response_model=None)
async def api_create_external_location(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, object] | JSONResponse:
    """Create a new external location."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        return await client.create_external_location(body)
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


@app.get("/api/external-locations/{name}", response_model=None)
async def api_get_external_location(
    request: Request, name: str
) -> dict[str, object] | JSONResponse:
    """Return a single external location."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        return await client.get_external_location(name)
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


@app.patch("/api/external-locations/{name}", response_model=None)
async def api_update_external_location(
    request: Request, name: str, body: dict[str, Any] = Body(...)
) -> dict[str, object] | JSONResponse:
    """Update an external location."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        return await client.update_external_location(name, body)
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


@app.delete("/api/external-locations/{name}", response_model=None)
async def api_delete_external_location(
    request: Request, name: str
) -> dict[str, str] | JSONResponse:
    """Delete an external location."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        await client.delete_external_location(name)
        return {"status": "deleted"}
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


# -- Federation: Credentials --


@app.get("/api/credentials", response_model=None)
async def api_list_credentials(
    request: Request,
) -> list[dict[str, object]] | JSONResponse:
    """Return all credentials."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        return await client.list_credentials()
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


@app.post("/api/credentials", response_model=None)
async def api_create_credential(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, object] | JSONResponse:
    """Create a new credential."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        return await client.create_credential(body)
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


@app.get("/api/credentials/{name}", response_model=None)
async def api_get_credential(
    request: Request, name: str
) -> dict[str, object] | JSONResponse:
    """Return a single credential."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        return await client.get_credential(name)
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


@app.patch("/api/credentials/{name}", response_model=None)
async def api_update_credential(
    request: Request, name: str, body: dict[str, Any] = Body(...)
) -> dict[str, object] | JSONResponse:
    """Update a credential."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        return await client.update_credential(name, body)
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


@app.delete("/api/credentials/{name}", response_model=None)
async def api_delete_credential(
    request: Request, name: str
) -> dict[str, str] | JSONResponse:
    """Delete a credential."""
    client: UnityCatalogClient = request.app.state.uc_client
    try:
        await client.delete_credential(name)
        return {"status": "deleted"}
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Catalog server unavailable: {exc}"},
        )


# -- Federation: HTML pages --


@app.get("/connections", response_class=HTMLResponse)
async def connections_index(request: Request) -> HTMLResponse:
    """List all connections."""
    client: UnityCatalogClient = request.app.state.uc_client
    connections: list[dict[str, Any]] = []
    error: str | None = None
    try:
        connections = await client.list_connections()
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        error = str(exc)
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/connections.html",
        {"connections": connections, "error": error, "active_page": "connections"},
    )


@app.get("/connections/{name}", response_class=HTMLResponse)
async def connection_detail(request: Request, name: str) -> HTMLResponse:
    """Show a single connection."""
    client: UnityCatalogClient = request.app.state.uc_client
    connection: dict[str, Any] | None = None
    error: str | None = None
    try:
        connection = await client.get_connection(name)
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        error = str(exc)
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/connection.html",
        {"connection": connection, "name": name, "error": error, "active_page": "connections"},
    )


@app.get("/external-locations", response_class=HTMLResponse)
async def external_locations_index(request: Request) -> HTMLResponse:
    """List all external locations."""
    client: UnityCatalogClient = request.app.state.uc_client
    locations: list[dict[str, Any]] = []
    error: str | None = None
    try:
        locations = await client.list_external_locations()
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        error = str(exc)
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/external_locations.html",
        {"locations": locations, "error": error, "active_page": "external_locations"},
    )


@app.get("/external-locations/{name}", response_class=HTMLResponse)
async def external_location_detail(request: Request, name: str) -> HTMLResponse:
    """Show a single external location."""
    client: UnityCatalogClient = request.app.state.uc_client
    location: dict[str, Any] | None = None
    error: str | None = None
    try:
        location = await client.get_external_location(name)
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        error = str(exc)
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/external_location.html",
        {"location": location, "name": name, "error": error, "active_page": "external_locations"},
    )


@app.get("/credentials", response_class=HTMLResponse)
async def credentials_index(request: Request) -> HTMLResponse:
    """List all credentials."""
    client: UnityCatalogClient = request.app.state.uc_client
    credentials: list[dict[str, Any]] = []
    error: str | None = None
    try:
        credentials = await client.list_credentials()
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        error = str(exc)
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/credentials.html",
        {"credentials": credentials, "error": error, "active_page": "credentials"},
    )


@app.get("/credentials/{name}", response_class=HTMLResponse)
async def credential_detail(request: Request, name: str) -> HTMLResponse:
    """Show a single credential."""
    client: UnityCatalogClient = request.app.state.uc_client
    credential: dict[str, Any] | None = None
    error: str | None = None
    try:
        credential = await client.get_credential(name)
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        error = str(exc)
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/credential.html",
        {"credential": credential, "name": name, "error": error, "active_page": "credentials"},
    )


def cli() -> None:
    """Run the development server."""
    import uvicorn

    uvicorn.run("pointlessql.api.main:app", host="127.0.0.1", port=8000, reload=True)
