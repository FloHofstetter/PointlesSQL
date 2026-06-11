"""Table certifications: tag mapping, the PUT route gate, and the badge.

The certification endpoint lives on the access-requests router, which
ships unregistered — the module-scoped fixture mounts it for the
duration of this file, mirroring the serving cockpit tests.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from pointlessql.api import access_requests_routes
from pointlessql.api.main import app
from pointlessql.exceptions import ValidationError
from pointlessql.services import certifications as svc
from pointlessql.services.unitycatalog import UnityCatalogClient

_CERT_PATH = "/api/tables/{full_name}/certification"


@pytest.fixture(autouse=True, scope="module")
def _mount_router():
    """Mount the unregistered router for this module's duration."""
    mounted = {getattr(route, "path", None) for route in app.router.routes}
    if _CERT_PATH in mounted:
        yield
        return
    before = len(app.router.routes)
    app.include_router(access_requests_routes.router)
    added = list(app.router.routes[before:])
    yield
    for route in added:
        app.router.routes.remove(route)


@pytest.fixture(autouse=True)
def _patch_for_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route ``UnityCatalogClient.for_principal`` to ``app.state.uc_client``."""
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: app.state.uc_client),  # type: ignore[arg-type]
    )


def _make_uc_mock(
    *,
    owner: str = "someone-else@test.com",
    effective: list[dict[str, Any]] | None = None,
    tags: list[dict[str, Any]] | None = None,
    updated_tags: list[dict[str, Any]] | None = None,
) -> MagicMock:
    client = MagicMock(spec=UnityCatalogClient)
    client.get_table = AsyncMock(
        return_value={
            "name": "orders",
            "catalog_name": "shop",
            "schema_name": "sales",
            "table_type": "MANAGED",
            "data_source_format": "DELTA",
            "storage_location": "/tmp/orders",
            "owner": owner,
            "columns": [],
            "comment": "",
            "properties": {},
            "created_at": 1700000000000,
            "updated_at": None,
            "created_by": None,
            "updated_by": None,
        }
    )
    client.get_effective_permissions = AsyncMock(return_value=effective or [])
    client.get_permissions = AsyncMock(return_value=[])
    client.get_tags = AsyncMock(return_value=tags or [])
    client.update_tags = AsyncMock(return_value=updated_tags or [])
    client.update_permissions = AsyncMock(return_value=[])
    client.get_lineage = AsyncMock(
        return_value={
            "upstream": {"nodes": [], "edges": []},
            "downstream": {"nodes": [], "edges": []},
        }
    )
    return client


# ---------------------------------------------------------------------------
# Pure mapping + service
# ---------------------------------------------------------------------------


class TestTagMapping:
    def test_from_tags_reads_status_and_note(self) -> None:
        tags = [
            {"key": "owner-team", "value": "sales"},
            {"key": svc.TAG_KEY, "value": "certified"},
            {"key": svc.NOTE_KEY, "value": "verified by steward"},
        ]
        assert svc.certification_from_tags(tags) == {
            "status": "certified",
            "note": "verified by steward",
        }

    def test_from_tags_unknown_value_reads_as_unset(self) -> None:
        assert svc.certification_from_tags([{"key": svc.TAG_KEY, "value": "golden"}]) is None
        assert svc.certification_from_tags([]) is None
        assert svc.certification_from_tags(["not-a-dict"]) is None

    async def test_get_certification_fetches_tags(self) -> None:
        uc = _make_uc_mock(tags=[{"key": svc.TAG_KEY, "value": "deprecated"}])
        result = await svc.get_certification(uc, "shop.sales.orders")
        assert result == {"status": "deprecated", "note": None}
        uc.get_tags.assert_awaited_once_with("table", "shop.sales.orders")

    async def test_set_certified_with_note_sets_both_tags(self) -> None:
        uc = _make_uc_mock(
            updated_tags=[
                {"key": svc.TAG_KEY, "value": "certified"},
                {"key": svc.NOTE_KEY, "value": "looks good"},
            ]
        )
        result = await svc.set_certification(uc, "shop.sales.orders", "certified", "looks good")
        assert result == {"status": "certified", "note": "looks good"}
        uc.update_tags.assert_awaited_once_with(
            "table",
            "shop.sales.orders",
            [
                {"key": svc.TAG_KEY, "op": "set", "value": "certified"},
                {"key": svc.NOTE_KEY, "op": "set", "value": "looks good"},
            ],
        )

    async def test_set_without_note_removes_stale_note(self) -> None:
        uc = _make_uc_mock(updated_tags=[{"key": svc.TAG_KEY, "value": "deprecated"}])
        result = await svc.set_certification(uc, "shop.sales.orders", "deprecated", "  ")
        assert result == {"status": "deprecated", "note": None}
        uc.update_tags.assert_awaited_once_with(
            "table",
            "shop.sales.orders",
            [
                {"key": svc.TAG_KEY, "op": "set", "value": "deprecated"},
                {"key": svc.NOTE_KEY, "op": "remove"},
            ],
        )

    async def test_clear_removes_both_tags(self) -> None:
        uc = _make_uc_mock(updated_tags=[])
        result = await svc.set_certification(uc, "shop.sales.orders", None, None)
        assert result is None
        uc.update_tags.assert_awaited_once_with(
            "table",
            "shop.sales.orders",
            [
                {"key": svc.TAG_KEY, "op": "remove"},
                {"key": svc.NOTE_KEY, "op": "remove"},
            ],
        )

    async def test_set_rejects_unknown_status(self) -> None:
        uc = _make_uc_mock()
        with pytest.raises(ValidationError):
            await svc.set_certification(uc, "shop.sales.orders", "golden", None)
        uc.update_tags.assert_not_awaited()


# ---------------------------------------------------------------------------
# Route gate
# ---------------------------------------------------------------------------

_URL = "/api/tables/shop.sales.orders/certification"


class TestCertificationRoute:
    async def test_admin_may_set(self, admin_client: httpx.AsyncClient) -> None:
        uc = _make_uc_mock(updated_tags=[{"key": svc.TAG_KEY, "value": "certified"}])
        app.state.uc_client = uc
        resp = await admin_client.put(_URL, json={"status": "certified"})
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "full_name": "shop.sales.orders",
            "certification": {"status": "certified", "note": None},
        }
        uc.update_tags.assert_awaited_once()

    async def test_owner_may_set(self, non_admin_client: httpx.AsyncClient) -> None:
        uc = _make_uc_mock(
            owner="nonadmin@test.com",
            updated_tags=[
                {"key": svc.TAG_KEY, "value": "deprecated"},
                {"key": svc.NOTE_KEY, "value": "use shop.sales.orders_v2"},
            ],
        )
        app.state.uc_client = uc
        resp = await non_admin_client.put(
            _URL, json={"status": "deprecated", "note": "use shop.sales.orders_v2"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["certification"]["note"] == "use shop.sales.orders_v2"

    async def test_non_owner_non_admin_is_403(self, non_admin_client: httpx.AsyncClient) -> None:
        uc = _make_uc_mock(owner="someone-else@test.com")
        app.state.uc_client = uc
        resp = await non_admin_client.put(_URL, json={"status": "certified"})
        assert resp.status_code == 403
        uc.update_tags.assert_not_awaited()

    async def test_admin_may_clear(self, admin_client: httpx.AsyncClient) -> None:
        uc = _make_uc_mock(updated_tags=[])
        app.state.uc_client = uc
        resp = await admin_client.put(_URL, json={"status": None})
        assert resp.status_code == 200
        assert resp.json()["certification"] is None

    async def test_unknown_status_is_422(self, admin_client: httpx.AsyncClient) -> None:
        app.state.uc_client = _make_uc_mock()
        resp = await admin_client.put(_URL, json={"status": "golden"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Table-page badge + banner
# ---------------------------------------------------------------------------

_TABLE_URL = "/catalogs/shop/schemas/sales/tables/orders"


class TestTablePageBadge:
    async def test_certified_badge_renders(self, admin_client: httpx.AsyncClient) -> None:
        app.state.uc_client = _make_uc_mock(tags=[{"key": svc.TAG_KEY, "value": "certified"}])
        resp = await admin_client.get(_TABLE_URL)
        assert resp.status_code == 200
        assert "bi-patch-check" in resp.text
        assert "Certified" in resp.text

    async def test_deprecated_banner_carries_note(self, admin_client: httpx.AsyncClient) -> None:
        app.state.uc_client = _make_uc_mock(
            tags=[
                {"key": svc.TAG_KEY, "value": "deprecated"},
                {"key": svc.NOTE_KEY, "value": "use shop.sales.orders_v2"},
            ]
        )
        resp = await admin_client.get(_TABLE_URL)
        assert resp.status_code == 200
        assert "This table is deprecated." in resp.text
        assert "use shop.sales.orders_v2" in resp.text

    async def test_admin_sees_certification_dropdown(self, admin_client: httpx.AsyncClient) -> None:
        app.state.uc_client = _make_uc_mock()
        resp = await admin_client.get(_TABLE_URL)
        assert resp.status_code == 200
        assert "x-data='tableCertification(" in resp.text

    async def test_plain_reader_sees_no_dropdown(self, non_admin_client: httpx.AsyncClient) -> None:
        app.state.uc_client = _make_uc_mock(
            effective=[{"principal": "nonadmin@test.com", "privileges": ["SELECT"]}]
        )
        resp = await non_admin_client.get(_TABLE_URL)
        assert resp.status_code == 200
        assert "tableCertification(" not in resp.text
