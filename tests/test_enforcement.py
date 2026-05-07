"""Route-level enforcement tests: access allowed, denied, and admin bypass."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.services.unitycatalog import UnityCatalogClient


def _make_uc_mock(
    effective_for_user: list[dict] | None = None,
) -> MagicMock:
    """Build a UnityCatalogClient mock with controllable effective permissions.

    Args:
        effective_for_user: Effective permissions to return. If None,
            returns an empty list (no permissions).
    """
    client = MagicMock(spec=UnityCatalogClient)
    effective = effective_for_user or []

    # Read operations — return enough fields to satisfy Jinja templates.
    client.get_tree = AsyncMock(return_value=[])
    client.list_catalogs = AsyncMock(return_value=[])
    client.list_schemas = AsyncMock(return_value=[])
    client.list_tables = AsyncMock(return_value=[])
    client.get_catalog = AsyncMock(
        return_value={
            "name": "test_cat",
            "comment": "",
            "properties": {},
            "created_at": 1700000000000,
            "updated_at": None,
            "created_by": None,
            "updated_by": None,
        }
    )
    client.get_schema = AsyncMock(
        return_value={
            "name": "test_sch",
            "catalog_name": "test_cat",
            "comment": "",
            "properties": {},
            "created_at": 1700000000000,
            "updated_at": None,
            "created_by": None,
            "updated_by": None,
        }
    )
    client.get_table = AsyncMock(
        return_value={
            "name": "test_tbl",
            "catalog_name": "test_cat",
            "schema_name": "test_sch",
            "table_type": "MANAGED",
            "data_source_format": "DELTA",
            "storage_location": "/tmp/test",
            "columns": [],
            "comment": "",
            "properties": {},
            "created_at": 1700000000000,
            "updated_at": None,
            "created_by": None,
            "updated_by": None,
        }
    )

    # Permissions
    client.get_permissions = AsyncMock(return_value=[])
    client.get_effective_permissions = AsyncMock(return_value=effective)
    client.update_permissions = AsyncMock(return_value=[])

    # Tags
    client.get_tags = AsyncMock(return_value=[])
    client.update_tags = AsyncMock(return_value=[])

    # Lineage
    client.get_lineage = AsyncMock(
        return_value={
            "upstream": {"nodes": [], "edges": []},
            "downstream": {"nodes": [], "edges": []},
        }
    )

    # Write operations
    client.update_catalog = AsyncMock(return_value={"name": "test_cat"})
    client.update_schema = AsyncMock(return_value={"name": "test_sch"})

    # Federation (admin-only)
    client.list_connections = AsyncMock(return_value=[])
    client.get_connection = AsyncMock(return_value={})
    client.create_connection = AsyncMock(return_value={})
    client.update_connection = AsyncMock(return_value={})
    client.delete_connection = AsyncMock(return_value=None)
    client.list_external_locations = AsyncMock(return_value=[])
    client.list_credentials = AsyncMock(return_value=[])
    return client


@pytest.fixture(autouse=True)
def _patch_for_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure for_principal returns whatever mock the test sets on app.state."""
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: app.state.uc_client),  # type: ignore[arg-type]
    )


# -- Catalog enforcement --


class TestCatalogEnforcement:
    async def test_admin_can_view_catalog(self, admin_client: httpx.AsyncClient) -> None:
        app.state.uc_client = _make_uc_mock()
        resp = await admin_client.get("/catalogs/test_cat")
        assert resp.status_code == 200

    async def test_non_admin_denied_without_grant(
        self, non_admin_client: httpx.AsyncClient
    ) -> None:
        app.state.uc_client = _make_uc_mock(effective_for_user=[])
        resp = await non_admin_client.get("/catalogs/test_cat")
        assert resp.status_code == 403
        assert "Access denied" in resp.text

    async def test_non_admin_allowed_with_use_catalog(
        self, non_admin_client: httpx.AsyncClient
    ) -> None:
        app.state.uc_client = _make_uc_mock(
            effective_for_user=[{"principal": "nonadmin@test.com", "privileges": ["USE CATALOG"]}]
        )
        resp = await non_admin_client.get("/catalogs/test_cat")
        assert resp.status_code == 200

    async def test_list_schemas_denied(self, non_admin_client: httpx.AsyncClient) -> None:
        app.state.uc_client = _make_uc_mock(effective_for_user=[])
        resp = await non_admin_client.get("/api/catalogs/test_cat/schemas")
        assert resp.status_code == 403
        data = resp.json()
        assert data["code"] == "authorization_error"


# -- Schema enforcement --


class TestSchemaEnforcement:
    async def test_non_admin_denied_without_grant(
        self, non_admin_client: httpx.AsyncClient
    ) -> None:
        app.state.uc_client = _make_uc_mock(effective_for_user=[])
        resp = await non_admin_client.get("/catalogs/test_cat/schemas/test_sch")
        assert resp.status_code == 403

    async def test_non_admin_allowed_with_use_schema(
        self, non_admin_client: httpx.AsyncClient
    ) -> None:
        app.state.uc_client = _make_uc_mock(
            effective_for_user=[{"principal": "nonadmin@test.com", "privileges": ["USE SCHEMA"]}]
        )
        resp = await non_admin_client.get("/catalogs/test_cat/schemas/test_sch")
        assert resp.status_code == 200


# -- Table enforcement --


class TestTableEnforcement:
    async def test_non_admin_denied_without_grant(
        self, non_admin_client: httpx.AsyncClient
    ) -> None:
        app.state.uc_client = _make_uc_mock(effective_for_user=[])
        resp = await non_admin_client.get("/catalogs/test_cat/schemas/test_sch/tables/test_tbl")
        assert resp.status_code == 403

    async def test_non_admin_allowed_with_select(self, non_admin_client: httpx.AsyncClient) -> None:
        app.state.uc_client = _make_uc_mock(
            effective_for_user=[{"principal": "nonadmin@test.com", "privileges": ["SELECT"]}]
        )
        resp = await non_admin_client.get("/catalogs/test_cat/schemas/test_sch/tables/test_tbl")
        assert resp.status_code == 200


# -- Write operations enforcement --


class TestUpdateEnforcement:
    async def test_update_catalog_denied(self, non_admin_client: httpx.AsyncClient) -> None:
        app.state.uc_client = _make_uc_mock(effective_for_user=[])
        resp = await non_admin_client.patch("/api/catalogs/test_cat", json={"comment": "hi"})
        assert resp.status_code == 403
        assert resp.json()["code"] == "authorization_error"

    async def test_update_catalog_allowed_with_modify(
        self, non_admin_client: httpx.AsyncClient
    ) -> None:
        app.state.uc_client = _make_uc_mock(
            effective_for_user=[{"principal": "nonadmin@test.com", "privileges": ["MODIFY"]}]
        )
        resp = await non_admin_client.patch("/api/catalogs/test_cat", json={"comment": "hi"})
        assert resp.status_code == 200

    async def test_update_schema_denied(self, non_admin_client: httpx.AsyncClient) -> None:
        app.state.uc_client = _make_uc_mock(effective_for_user=[])
        resp = await non_admin_client.patch(
            "/api/catalogs/test_cat/schemas/test_sch",
            json={"comment": "hi"},
        )
        assert resp.status_code == 403

    async def test_update_tags_denied(self, non_admin_client: httpx.AsyncClient) -> None:
        app.state.uc_client = _make_uc_mock(effective_for_user=[])
        resp = await non_admin_client.patch(
            "/api/tags/catalog/test_cat",
            json={"changes": [{"key": "k", "op": "set", "value": "v"}]},
        )
        assert resp.status_code == 403


# -- Permissions management enforcement --


class TestPermissionsEnforcement:
    async def test_update_permissions_denied_without_manage_grants(
        self, non_admin_client: httpx.AsyncClient
    ) -> None:
        app.state.uc_client = _make_uc_mock(
            effective_for_user=[{"principal": "nonadmin@test.com", "privileges": ["MODIFY"]}]
        )
        resp = await non_admin_client.patch(
            "/api/permissions/catalog/test_cat",
            json={"changes": []},
        )
        assert resp.status_code == 403

    async def test_update_permissions_allowed_with_manage_grants(
        self, non_admin_client: httpx.AsyncClient
    ) -> None:
        app.state.uc_client = _make_uc_mock(
            effective_for_user=[{"principal": "nonadmin@test.com", "privileges": ["MANAGE_GRANTS"]}]
        )
        resp = await non_admin_client.patch(
            "/api/permissions/catalog/test_cat",
            json={"changes": []},
        )
        assert resp.status_code == 200


# -- Federation admin-only enforcement --


class TestFederationAdminOnly:
    async def test_connections_denied_for_non_admin(
        self, non_admin_client: httpx.AsyncClient
    ) -> None:
        app.state.uc_client = _make_uc_mock()
        resp = await non_admin_client.get("/api/connections")
        assert resp.status_code == 403
        assert resp.json()["code"] == "authorization_error"

    async def test_connections_allowed_for_admin(self, admin_client: httpx.AsyncClient) -> None:
        app.state.uc_client = _make_uc_mock()
        resp = await admin_client.get("/api/connections")
        assert resp.status_code == 200

    async def test_ext_locations_denied_for_non_admin(
        self, non_admin_client: httpx.AsyncClient
    ) -> None:
        app.state.uc_client = _make_uc_mock()
        resp = await non_admin_client.get("/api/external-locations")
        assert resp.status_code == 403

    async def test_credentials_denied_for_non_admin(
        self, non_admin_client: httpx.AsyncClient
    ) -> None:
        app.state.uc_client = _make_uc_mock()
        resp = await non_admin_client.get("/api/credentials")
        assert resp.status_code == 403

    async def test_connections_html_denied_for_non_admin(
        self, non_admin_client: httpx.AsyncClient
    ) -> None:
        app.state.uc_client = _make_uc_mock()
        resp = await non_admin_client.get("/connections")
        assert resp.status_code == 403
        assert "Access denied" in resp.text

    async def test_connections_html_allowed_for_admin(
        self, admin_client: httpx.AsyncClient
    ) -> None:
        app.state.uc_client = _make_uc_mock()
        resp = await admin_client.get("/connections")
        assert resp.status_code == 200


# -- Principal header forwarding --


class TestPrincipalForwarding:
    def test_make_principal_client_sets_header(self) -> None:
        """make_principal_client creates a Client with X-Principal header."""
        from pointlessql.services.soyuz_client import make_principal_client
        from pointlessql.settings import Settings

        settings = Settings(jupyter={"enabled": False})
        client = make_principal_client(settings, "user@test.com")
        assert client._headers["X-Principal"] == "user@test.com"

    def test_make_principal_client_preserves_base_url(self) -> None:
        from pointlessql.services.soyuz_client import make_principal_client
        from pointlessql.settings import Settings

        settings = Settings(
            jupyter={"enabled": False},
            soyuz={"catalog_url": "http://custom:9090"},
        )
        client = make_principal_client(settings, "user@test.com")
        assert client._base_url == "http://custom:9090"
