"""FastAPI entrypoint for PointlesSQL."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import Body, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from soyuz_catalog_client.errors import UnexpectedStatus

from pointlessql.services.soyuz_client import make_soyuz_client
from pointlessql.services.unitycatalog import UnityCatalogClient

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


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create and dispose the shared Unity Catalog client."""
    soyuz = make_soyuz_client()
    app.state.uc_client = UnityCatalogClient(soyuz)
    try:
        yield
    finally:
        await app.state.uc_client.aclose()


app = FastAPI(title="PointlesSQL", version="0.1.0", lifespan=_lifespan)
app.mount(
    "/static",
    StaticFiles(directory=str(_FRONTEND_DIR)),
    name="static",
)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Return service health."""
    return {"status": "ok"}


@app.get("/api/tree")
async def api_tree(request: Request) -> list[dict[str, object]]:
    """Return the full catalog/schema/table tree for the sidebar."""
    client: UnityCatalogClient = request.app.state.uc_client
    return await client.get_tree()


@app.get("/api/catalogs")
async def api_catalogs(request: Request) -> list[dict[str, object]]:
    """Return all catalogs as JSON."""
    client: UnityCatalogClient = request.app.state.uc_client
    return await client.list_catalogs()


@app.get("/api/catalogs/{catalog_name}/schemas")
async def api_schemas(
    request: Request, catalog_name: str
) -> list[dict[str, object]]:
    """Return schemas inside a catalog as JSON."""
    client: UnityCatalogClient = request.app.state.uc_client
    return await client.list_schemas(catalog_name)


@app.get("/api/catalogs/{catalog_name}/schemas/{schema_name}/tables")
async def api_tables(
    request: Request, catalog_name: str, schema_name: str
) -> list[dict[str, object]]:
    """Return tables inside a schema as JSON."""
    client: UnityCatalogClient = request.app.state.uc_client
    return await client.list_tables(catalog_name, schema_name)


@app.patch("/api/catalogs/{catalog_name}")
async def api_update_catalog(
    request: Request,
    catalog_name: str,
    patch: dict[str, Any] = Body(...),
) -> dict[str, object]:
    """Apply a partial update to a catalog."""
    client: UnityCatalogClient = request.app.state.uc_client
    return await client.update_catalog(catalog_name, patch)


@app.patch("/api/catalogs/{catalog_name}/schemas/{schema_name}")
async def api_update_schema(
    request: Request,
    catalog_name: str,
    schema_name: str,
    patch: dict[str, Any] = Body(...),
) -> dict[str, object]:
    """Apply a partial update to a schema."""
    client: UnityCatalogClient = request.app.state.uc_client
    return await client.update_schema(catalog_name, schema_name, patch)


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
    error: str | None = None
    try:
        catalog = await client.get_catalog(catalog_name)
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        error = str(exc)
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/schemas.html",
        {
            "catalog_name": catalog_name,
            "catalog": catalog,
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
    error: str | None = None
    try:
        schema = await client.get_schema(catalog_name, schema_name)
    except (httpx.HTTPError, UnexpectedStatus) as exc:
        error = str(exc)
    return _TEMPLATES.TemplateResponse(
        request,
        "pages/tables.html",
        {
            "catalog_name": catalog_name,
            "schema_name": schema_name,
            "schema": schema,
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
    error: str | None = None
    try:
        table = await client.get_table(catalog_name, schema_name, table_name)
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
            "error": error,
            "active_catalog": catalog_name,
            "active_schema": schema_name,
            "active_table": table_name,
        },
    )


def cli() -> None:
    """Run the development server."""
    import uvicorn

    uvicorn.run("pointlessql.api.main:app", host="127.0.0.1", port=8000, reload=True)
