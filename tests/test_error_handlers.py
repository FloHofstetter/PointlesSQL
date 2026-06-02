"""Tests for the centralized exception handlers and request-ID middleware."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.exceptions import (
    AuthorizationError,
    CatalogNotFoundError,
    CatalogUnavailableError,
    EngineError,
    ValidationError,
)
from pointlessql.services.unitycatalog import UnityCatalogClient


@pytest.fixture(autouse=True)
def _app_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure app.state has the minimum required attributes."""
    app.state.jupyter_process = None

    # Default: a healthy mock (individual tests override side_effect).
    client = MagicMock(spec=UnityCatalogClient)
    client.list_catalogs = AsyncMock(return_value=[])
    client.get_tree = AsyncMock(return_value=[])
    app.state.uc_client = client

    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: client),  # type: ignore[arg-type]
    )


def _authed_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    )


# -- RFC 9457 problem+json envelope tests --


class TestProblemJsonEnvelope:
    async def test_catalog_unavailable_produces_502(self) -> None:
        app.state.uc_client.get_tree = AsyncMock(side_effect=CatalogUnavailableError("server down"))
        async with _authed_client() as client:
            resp = await client.get("/api/tree")
        assert resp.status_code == 502
        assert resp.headers["content-type"].startswith("application/problem+json")
        body = resp.json()
        assert body["type"] == "about:blank"
        assert body["title"] == "Upstream catalog unavailable"
        assert body["status"] == 502
        assert body["code"] == "catalog_unavailable"
        assert body["detail"] == "server down"
        assert body["request_id"] is not None

    async def test_catalog_not_found_produces_404(self) -> None:
        app.state.uc_client.get_tree = AsyncMock(
            side_effect=CatalogNotFoundError("no such catalog")
        )
        async with _authed_client() as client:
            resp = await client.get("/api/tree")
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == "catalog_not_found"
        assert body["status"] == 404
        assert body["detail"] == "no such catalog"

    async def test_authorization_error_produces_403(self) -> None:
        app.state.uc_client.get_tree = AsyncMock(
            side_effect=AuthorizationError("user@test.com", "SELECT", "table", "cat.sch.tbl")
        )
        async with _authed_client() as client:
            resp = await client.get("/api/tree")
        assert resp.status_code == 403
        body = resp.json()
        assert body["code"] == "authorization_error"
        # AuthorizationError surfaces the extra context as RFC 9457 extension members.
        assert body["required_privilege"] == "SELECT"
        assert body["securable_type"] == "table"
        assert body["full_name"] == "cat.sch.tbl"

    async def test_engine_error_produces_500(self) -> None:
        app.state.uc_client.get_tree = AsyncMock(side_effect=EngineError("delta read failed"))
        async with _authed_client() as client:
            resp = await client.get("/api/tree")
        assert resp.status_code == 500
        body = resp.json()
        assert body["code"] == "engine_error"

    async def test_validation_error_produces_422(self) -> None:
        app.state.uc_client.get_tree = AsyncMock(side_effect=ValidationError("bad table name"))
        async with _authed_client() as client:
            resp = await client.get("/api/tree")
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == "validation_error"


# -- HTML error handling --


class TestHtmlErrorHandling:
    async def test_authorization_error_renders_403_page(self) -> None:
        app.state.uc_client.list_connections = AsyncMock(
            side_effect=AuthorizationError("user@test.com", "USE CATALOG", "catalog", "test_cat")
        )
        async with _authed_client() as client:
            resp = await client.get("/connections")
        # render_page_with_fallback catches CatalogUnavailableError but
        # lets AuthorizationError propagate to the centralized handler.
        assert resp.status_code == 403
        # The 403 template renders "Access denied" (lowercase 'd') via
        # both the ``status_title`` context and the static page copy.
        assert "Access denied" in resp.text


# -- Request-ID tests --


class TestRequestId:
    async def test_response_has_request_id_header(self) -> None:
        async with _authed_client() as client:
            resp = await client.get("/api/catalogs")
        assert "X-Request-ID" in resp.headers
        # UUID4 format: 8-4-4-4-12 hex chars
        assert len(resp.headers["X-Request-ID"]) == 36

    async def test_client_request_id_is_forwarded(self) -> None:
        async with _authed_client() as client:
            resp = await client.get(
                "/api/catalogs",
                headers={"X-Request-ID": "my-trace-id"},
            )
        assert resp.headers["X-Request-ID"] == "my-trace-id"

    async def test_request_id_in_problem_body(self) -> None:
        app.state.uc_client.get_tree = AsyncMock(side_effect=CatalogUnavailableError("down"))
        async with _authed_client() as client:
            resp = await client.get("/api/tree", headers={"X-Request-ID": "err-trace-42"})
        assert resp.json()["request_id"] == "err-trace-42"


# -- Admin enforcement via centralized handler --


class TestAdminEnforcement:
    async def test_non_admin_gets_403_json_on_api_route(self) -> None:
        non_admin_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies=app.state._test_non_admin_cookie,
        )
        async with non_admin_client as client:
            resp = await client.get("/api/connections")
        assert resp.status_code == 403
        body = resp.json()
        assert body["code"] == "authorization_error"

    async def test_non_admin_gets_403_html_on_page(self) -> None:
        non_admin_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies=app.state._test_non_admin_cookie,
        )
        async with non_admin_client as client:
            resp = await client.get("/connections")
        assert resp.status_code == 403
        assert "Access denied" in resp.text
