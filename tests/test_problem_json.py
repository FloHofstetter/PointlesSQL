"""Tests for the Sprint 44 RFC 9457 problem+json envelope + HTMX toast bridge.

``test_error_handlers.py`` already covers the happy-path JSON envelope
and the HTML page renderer; this file adds the three scenarios that are
specific to Sprint 44: the HTMX fragment toast branch, the boosted-
navigation fallthrough to the HTML page, and RFC 9457 compliance
details (media type, extension members, validation-error shape).

The scenarios use an endpoint that raises before any DB access so the
conftest's auth-only schema suffices. ``_require_admin`` on
``/connections`` is ideal: a non-admin cookie triggers
:class:`AuthorizationError` at the top of the handler.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.exceptions import (
    AuthorizationError,
    CatalogUnavailableError,
    ValidationError,
)
from pointlessql.services.unitycatalog import UnityCatalogClient


@pytest.fixture(autouse=True)
def _app_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    app.state.jupyter_process = None
    client = MagicMock(spec=UnityCatalogClient)
    client.list_catalogs = AsyncMock(return_value=[])
    client.get_tree = AsyncMock(return_value=[])
    client.list_connections = AsyncMock(return_value=[])
    app.state.uc_client = client
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: client),  # type: ignore[arg-type]
    )




class TestHtmxFragmentToast:
    """Non-boosted HTMX fragment requests get an ``HX-Trigger`` toast."""

    async def test_htmx_fragment_receives_trigger_header(self, non_admin_client: httpx.AsyncClient) -> None:
        """Non-admin on ``/connections`` + ``HX-Request: true`` → toast trigger.

        ``_require_admin`` raises :class:`AuthorizationError` before any
        DB-backed code runs, so this path is independent of the home-
        page ``jobs`` query that ``test_api_errors`` needs.
        """
        resp = await non_admin_client.get("/connections", headers={"HX-Request": "true"})
        # htmx suppresses the swap on non-2xx, but the HX-Trigger header
        # must fire so the browser-side listener shows a toast.
        assert resp.status_code == 403
        assert "HX-Trigger" in resp.headers
        payload = json.loads(resp.headers["HX-Trigger"])
        toast = payload["pqlToast"]
        assert toast["level"] == "error"
        assert toast["code"] == "authorization_error"
        assert toast["message"].startswith("nonadmin@test.com lacks")
        assert toast["request_id"] is not None
        # Body is intentionally empty — htmx will not swap it and we
        # do not want to ship an HTML page as the toast body.
        assert resp.content == b""

    async def test_boosted_navigation_falls_back_to_html_page(self, non_admin_client: httpx.AsyncClient) -> None:
        """``HX-Boosted: true`` callers get the branded HTML error page."""
        resp = await non_admin_client.get(
            "/connections",
            headers={"HX-Request": "true", "HX-Boosted": "true"},
        )
        # Boosted navigations do not get the HX-Trigger shortcut; they
        # get the branded HTML shell so htmx can swap #main-content.
        assert "HX-Trigger" not in resp.headers
        assert resp.headers["content-type"].startswith("text/html")
        assert resp.status_code == 403


class TestRfc9457Compliance:
    """Header, body shape, and extension-member correctness."""

    async def test_problem_media_type_on_api(self, admin_client: httpx.AsyncClient) -> None:
        app.state.uc_client.get_tree = AsyncMock(side_effect=CatalogUnavailableError("down"))
        resp = await admin_client.get("/api/tree")
        assert resp.headers["content-type"].startswith("application/problem+json")

    async def test_problem_media_type_when_accept_json(self, non_admin_client: httpx.AsyncClient) -> None:
        """Non-API paths honour ``Accept: application/json`` too."""
        resp = await non_admin_client.get(
            "/connections",
            headers={"accept": "application/json"},
        )
        assert resp.headers["content-type"].startswith("application/problem+json")
        body = resp.json()
        # Core RFC 9457 members must all be present.
        assert set(body).issuperset({"type", "title", "status", "detail", "code"})
        assert body["type"] == "about:blank"

    async def test_authorization_extension_members_in_body(self, admin_client: httpx.AsyncClient) -> None:
        """``AuthorizationError`` carries extra context as RFC 9457 extensions."""
        app.state.uc_client.get_tree = AsyncMock(
            side_effect=AuthorizationError("user@test.com", "MODIFY", "schema", "cat.sch")
        )
        resp = await admin_client.get("/api/tree")
        body = resp.json()
        assert body["code"] == "authorization_error"
        assert body["required_privilege"] == "MODIFY"
        assert body["securable_type"] == "schema"
        assert body["full_name"] == "cat.sch"

    async def test_domain_validation_error_422(self, admin_client: httpx.AsyncClient) -> None:
        """Our own ``ValidationError`` still maps to 422 with the right code."""
        app.state.uc_client.get_tree = AsyncMock(side_effect=ValidationError("bad name"))
        resp = await admin_client.get("/api/tree")
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == "validation_error"
        assert body["detail"] == "bad name"
