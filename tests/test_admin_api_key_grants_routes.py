"""Tests for the grants CRUD admin endpoints."""

from __future__ import annotations

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import ApiKey, ApiKeyCatalogGrant, ApiKeyIpGrant
from pointlessql.services import api_keys as api_keys_service


def _wipe() -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.query(ApiKeyIpGrant).delete()
        session.query(ApiKeyCatalogGrant).delete()
        session.query(ApiKey).delete()
        session.commit()
    api_keys_service.invalidate_cache()


@pytest.mark.asyncio
async def test_list_grants_returns_empty_for_fresh_key(
    admin_client: httpx.AsyncClient,
) -> None:
    _wipe()
    await admin_client.post("/api/admin/api-keys", json={"name": "fresh"})
    resp = await admin_client.get("/api/admin/api-keys/fresh/grants")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"catalog_grants": [], "ip_grants": []}
    _wipe()


@pytest.mark.asyncio
async def test_add_catalog_grant_with_schema(admin_client: httpx.AsyncClient) -> None:
    _wipe()
    await admin_client.post("/api/admin/api-keys", json={"name": "cg"})
    resp = await admin_client.post(
        "/api/admin/api-keys/cg/grants/catalog",
        json={"catalog_name": "main", "schema_name": "sales"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["catalog_name"] == "main"
    assert body["schema_name"] == "sales"
    assert isinstance(body["id"], int)

    listing = await admin_client.get("/api/admin/api-keys/cg/grants")
    assert len(listing.json()["catalog_grants"]) == 1
    _wipe()


@pytest.mark.asyncio
async def test_add_catalog_grant_wildcard_schema(
    admin_client: httpx.AsyncClient,
) -> None:
    _wipe()
    await admin_client.post("/api/admin/api-keys", json={"name": "cgw"})
    resp = await admin_client.post(
        "/api/admin/api-keys/cgw/grants/catalog", json={"catalog_name": "main"}
    )
    assert resp.status_code == 200
    assert resp.json()["schema_name"] is None
    _wipe()


@pytest.mark.asyncio
async def test_add_catalog_grant_rejects_duplicate(
    admin_client: httpx.AsyncClient,
) -> None:
    _wipe()
    await admin_client.post("/api/admin/api-keys", json={"name": "dup"})
    first = await admin_client.post(
        "/api/admin/api-keys/dup/grants/catalog",
        json={"catalog_name": "main", "schema_name": "sales"},
    )
    assert first.status_code == 200
    second = await admin_client.post(
        "/api/admin/api-keys/dup/grants/catalog",
        json={"catalog_name": "main", "schema_name": "sales"},
    )
    assert second.status_code == 422
    _wipe()


@pytest.mark.asyncio
async def test_delete_catalog_grant(admin_client: httpx.AsyncClient) -> None:
    _wipe()
    await admin_client.post("/api/admin/api-keys", json={"name": "del-cg"})
    add_resp = await admin_client.post(
        "/api/admin/api-keys/del-cg/grants/catalog",
        json={"catalog_name": "main", "schema_name": "sales"},
    )
    grant_id = add_resp.json()["id"]
    del_resp = await admin_client.delete(f"/api/admin/api-keys/del-cg/grants/catalog/{grant_id}")
    assert del_resp.status_code == 200 and del_resp.json()["deleted"] is True
    listing = await admin_client.get("/api/admin/api-keys/del-cg/grants")
    assert listing.json()["catalog_grants"] == []
    _wipe()


@pytest.mark.asyncio
async def test_add_ip_grant_canonicalises_cidr(
    admin_client: httpx.AsyncClient,
) -> None:
    _wipe()
    await admin_client.post("/api/admin/api-keys", json={"name": "ip"})
    resp = await admin_client.post(
        "/api/admin/api-keys/ip/grants/ip",
        json={"cidr": "10.5.7.3/8", "label": "office"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # validate_cidr strips host bits when strict=False.
    assert body["cidr"] == "10.0.0.0/8"
    assert body["label"] == "office"
    _wipe()


@pytest.mark.asyncio
async def test_add_ip_grant_rejects_bad_cidr(admin_client: httpx.AsyncClient) -> None:
    _wipe()
    await admin_client.post("/api/admin/api-keys", json={"name": "badip"})
    resp = await admin_client.post(
        "/api/admin/api-keys/badip/grants/ip",
        json={"cidr": "not-a-cidr"},
    )
    assert resp.status_code == 422
    _wipe()


@pytest.mark.asyncio
async def test_delete_ip_grant(admin_client: httpx.AsyncClient) -> None:
    _wipe()
    await admin_client.post("/api/admin/api-keys", json={"name": "delip"})
    add_resp = await admin_client.post(
        "/api/admin/api-keys/delip/grants/ip",
        json={"cidr": "10.0.0.0/8"},
    )
    grant_id = add_resp.json()["id"]
    del_resp = await admin_client.delete(f"/api/admin/api-keys/delip/grants/ip/{grant_id}")
    assert del_resp.status_code == 200
    listing = await admin_client.get("/api/admin/api-keys/delip/grants")
    assert listing.json()["ip_grants"] == []
    _wipe()


@pytest.mark.asyncio
async def test_grants_routes_require_admin(non_admin_client: httpx.AsyncClient) -> None:
    _wipe()
    list_resp = await non_admin_client.get("/api/admin/api-keys/x/grants")
    assert list_resp.status_code == 403
    add_resp = await non_admin_client.post(
        "/api/admin/api-keys/x/grants/catalog",
        json={"catalog_name": "main"},
    )
    assert add_resp.status_code == 403
    _wipe()
