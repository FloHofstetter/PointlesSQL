"""Tests for the foreign-catalog UI + API surface.

Covers:
- ``POST /api/catalogs`` (admin-only) for managed and foreign variants.
- ``PATCH /api/catalogs/{name}`` round-trip of ``options`` (inline edit).
- The catalog detail HTML page renders the foreign-catalog card +
  FOREIGN badge when ``connection_name`` is present, and hides both
  when it is not.
- The home page renders the "Create foreign catalog" modal for admins
  with the Connection dropdown pre-populated from
  ``UnityCatalogClient.list_connections``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.services.unitycatalog import UnityCatalogClient

_FOREIGN_CATALOG = {
    "name": "pg_cat",
    "type": "FOREIGN",
    "connection_name": "my_pg",
    "options": {"database": "analytics", "schema_filter": "public"},
    "comment": "",
    "properties": {},
    "created_at": 1700000000000,
    "updated_at": None,
    "created_by": None,
    "updated_by": None,
    "owner": None,
    "id": "foreign-uuid",
    "storage_root": None,
    "storage_location": None,
}

_MANAGED_CATALOG = {
    "name": "managed_cat",
    "type": "MANAGED",
    "comment": "",
    "properties": {},
    "created_at": 1700000000000,
    "updated_at": None,
    "created_by": None,
    "updated_by": None,
    "owner": None,
    "id": "managed-uuid",
    "storage_root": "/tmp/warehouse",
    "storage_location": None,
}


def _make_uc_mock(
    *,
    catalog: dict[str, object] | None = None,
    connections: list[dict[str, object]] | None = None,
) -> MagicMock:
    """Build a UnityCatalogClient mock wired for the routes under test."""
    client = MagicMock(spec=UnityCatalogClient)
    client.list_catalogs = AsyncMock(return_value=[catalog or _MANAGED_CATALOG])
    client.list_connections = AsyncMock(return_value=connections or [])
    client.get_catalog = AsyncMock(return_value=catalog or _MANAGED_CATALOG)
    client.get_tags = AsyncMock(return_value=[])
    client.get_permissions = AsyncMock(return_value=[])
    client.get_effective_permissions = AsyncMock(return_value=[])
    client.create_catalog = AsyncMock(return_value=_FOREIGN_CATALOG)
    client.update_catalog = AsyncMock(return_value=_FOREIGN_CATALOG)
    return client


@pytest.fixture(autouse=True)
def _patch_for_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route per-request client construction through ``app.state.uc_client``."""
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: app.state.uc_client),  # type: ignore[arg-type]
    )


class TestCreateCatalogRoute:
    async def test_admin_can_create_foreign_catalog(self, admin_client: httpx.AsyncClient) -> None:
        app.state.uc_client = _make_uc_mock()
        payload = {
            "name": "pg_cat",
            "type": "FOREIGN",
            "connection_name": "my_pg",
            "options": {"database": "analytics"},
        }
        resp = await admin_client.post("/api/catalogs", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["connection_name"] == "my_pg"
        app.state.uc_client.create_catalog.assert_awaited_once_with(payload)

    async def test_admin_can_create_managed_catalog(self, admin_client: httpx.AsyncClient) -> None:
        app.state.uc_client = _make_uc_mock()
        app.state.uc_client.create_catalog = AsyncMock(return_value=_MANAGED_CATALOG)
        resp = await admin_client.post("/api/catalogs", json={"name": "m"})
        assert resp.status_code == 200
        assert resp.json()["type"] == "MANAGED"

    async def test_non_admin_forbidden(self, non_admin_client: httpx.AsyncClient) -> None:
        app.state.uc_client = _make_uc_mock()
        resp = await non_admin_client.post(
            "/api/catalogs",
            json={
                "name": "pg_cat",
                "type": "FOREIGN",
                "connection_name": "my_pg",
            },
        )
        assert resp.status_code == 403
        # create_catalog must never be called for a non-admin.
        app.state.uc_client.create_catalog.assert_not_awaited()


class TestPatchOptions:
    async def test_inline_options_edit_forwards_dict(self, admin_client: httpx.AsyncClient) -> None:
        app.state.uc_client = _make_uc_mock(catalog=_FOREIGN_CATALOG)
        new_options = {"database": "analytics", "schema_filter": "reporting"}
        resp = await admin_client.patch("/api/catalogs/pg_cat", json={"options": new_options})
        assert resp.status_code == 200
        app.state.uc_client.update_catalog.assert_awaited_once_with(
            "pg_cat", {"options": new_options}
        )


class TestCatalogDetailHtml:
    async def test_foreign_badge_and_card_render(self, admin_client: httpx.AsyncClient) -> None:
        app.state.uc_client = _make_uc_mock(catalog=_FOREIGN_CATALOG)
        resp = await admin_client.get("/catalogs/pg_cat")
        assert resp.status_code == 200
        text = resp.text
        # Card shows the bound connection link.
        assert 'href="/connections/my_pg"' in text
        # Options are wired into the optionsEditor alpine component.
        assert "optionsEditor" in text
        assert "schema_filter" in text
        # The heading-area FOREIGN badge is rendered server-side next to the
        # h1 in schemas.html — distinct from the sidebar's Alpine ``<template
        # x-if>`` block, which ships as a raw ``<template>`` element and so
        # shows up in every catalog's HTML regardless of type.
        assert "FOREIGN</span>" in text

    async def test_managed_catalog_has_no_foreign_card(
        self, admin_client: httpx.AsyncClient
    ) -> None:
        app.state.uc_client = _make_uc_mock(catalog=_MANAGED_CATALOG)
        resp = await admin_client.get("/catalogs/managed_cat")
        assert resp.status_code == 200
        text = resp.text
        # The card's Alpine component is the unique marker — the sidebar
        # ``<template x-if>`` uses the FOREIGN string too, but never mounts
        # an optionsEditor.
        assert "optionsEditor" not in text
        # Storage root is shown instead.
        assert "/tmp/warehouse" in text


class TestConnectionsPageForeignCatalogModal:
    """The "Create foreign catalog" modal lives on the Connections page."""

    async def test_admin_sees_create_button_and_connection_options(
        self, admin_client: httpx.AsyncClient
    ) -> None:
        app.state.uc_client = _make_uc_mock(
            connections=[{"name": "my_pg", "connection_type": "POSTGRESQL"}]
        )
        resp = await admin_client.get("/connections")
        assert resp.status_code == 200
        text = resp.text
        assert "Create foreign catalog" in text
        assert "createForeignCatalogModal" in text
        # Alpine data-bootstrap JSON carries the connection list.
        assert "my_pg" in text
        assert "POSTGRESQL" in text

    async def test_non_admin_cannot_reach_connections(
        self, non_admin_client: httpx.AsyncClient
    ) -> None:
        app.state.uc_client = _make_uc_mock()
        # Federation connections are admin-only, so foreign-catalog
        # creation is unreachable for non-admins.
        resp = await non_admin_client.get("/connections")
        assert resp.status_code in (401, 403)
