"""API tests for the secret-scopes surface (ACL gating, write-only values)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from pointlessql.api.main import app

ADMIN = "test@test.com"
NON_ADMIN = "nonadmin@test.com"


def _client(cookies: dict[str, str]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=cookies,
    )


async def _create_scope(cookies: dict[str, str], name: str) -> dict[str, Any]:
    async with _client(cookies) as client:
        resp = await client.post("/api/secrets/scopes", json={"name": name})
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_create_scope_and_owner_visibility() -> None:
    body = await _create_scope(app.state._test_non_admin_cookie, "api-own-a")
    assert body["name"] == "api-own-a"
    assert body["permission"] == "MANAGE"
    async with _client(app.state._test_non_admin_cookie) as client:
        listing = await client.get("/api/secrets/scopes")
    names = {s["name"] for s in listing.json()["scopes"]}
    assert "api-own-a" in names
    # admins see every scope
    async with _client(app.state._test_auth_cookie) as client:
        listing = await client.get("/api/secrets/scopes")
    assert "api-own-a" in {s["name"] for s in listing.json()["scopes"]}


@pytest.mark.asyncio
async def test_ungranted_scope_is_invisible_and_404s() -> None:
    await _create_scope(app.state._test_auth_cookie, "api-admin-only")
    async with _client(app.state._test_non_admin_cookie) as client:
        listing = await client.get("/api/secrets/scopes")
        assert "api-admin-only" not in {s["name"] for s in listing.json()["scopes"]}
        keys = await client.get("/api/secrets/scopes/api-admin-only/secrets")
        assert keys.status_code == 404
        value = await client.get("/api/secrets/scopes/api-admin-only/secrets/k/value")
        assert value.status_code == 404


@pytest.mark.asyncio
async def test_secret_roundtrip_values_stay_write_only() -> None:
    await _create_scope(app.state._test_non_admin_cookie, "api-rt")
    async with _client(app.state._test_non_admin_cookie) as client:
        put = await client.put(
            "/api/secrets/scopes/api-rt/secrets/db-password",
            json={"value": "hunter2"},
        )
        assert put.status_code == 200, put.text
        put_body = put.json()
        assert "value" not in put_body
        assert "encrypted_value" not in put_body

        keys = await client.get("/api/secrets/scopes/api-rt/secrets")
        listed = keys.json()["secrets"]
        assert [s["key"] for s in listed] == ["db-password"]
        assert all("value" not in s and "encrypted_value" not in s for s in listed)

        value = await client.get("/api/secrets/scopes/api-rt/secrets/db-password/value")
        assert value.status_code == 200
        assert value.json() == {"scope": "api-rt", "key": "db-password", "value": "hunter2"}

        gone = await client.delete("/api/secrets/scopes/api-rt/secrets/db-password")
        assert gone.json()["deleted"] is True
        miss = await client.get("/api/secrets/scopes/api-rt/secrets/db-password/value")
        assert miss.status_code == 404


@pytest.mark.asyncio
async def test_acl_grant_unlocks_read_but_not_write() -> None:
    await _create_scope(app.state._test_auth_cookie, "api-acl")
    async with _client(app.state._test_auth_cookie) as admin:
        await admin.put("/api/secrets/scopes/api-acl/secrets/token", json={"value": "tok-123"})
        grant = await admin.put(
            f"/api/secrets/scopes/api-acl/acls/{NON_ADMIN}",
            json={"permission": "READ"},
        )
        assert grant.status_code == 200, grant.text

    async with _client(app.state._test_non_admin_cookie) as client:
        value = await client.get("/api/secrets/scopes/api-acl/secrets/token/value")
        assert value.status_code == 200
        assert value.json()["value"] == "tok-123"
        denied_put = await client.put(
            "/api/secrets/scopes/api-acl/secrets/other", json={"value": "x"}
        )
        assert denied_put.status_code == 403
        denied_acls = await client.get("/api/secrets/scopes/api-acl/acls")
        assert denied_acls.status_code == 403


@pytest.mark.asyncio
async def test_acl_listing_and_revocation() -> None:
    await _create_scope(app.state._test_auth_cookie, "api-acl-rm")
    async with _client(app.state._test_auth_cookie) as admin:
        await admin.put(
            f"/api/secrets/scopes/api-acl-rm/acls/{NON_ADMIN}",
            json={"permission": "WRITE"},
        )
        acls = await admin.get("/api/secrets/scopes/api-acl-rm/acls")
        entries = {a["principal"]: a["permission"] for a in acls.json()["acls"]}
        assert entries[NON_ADMIN] == "WRITE"
        assert entries[ADMIN] == "MANAGE"  # creator grant
        revoked = await admin.delete(f"/api/secrets/scopes/api-acl-rm/acls/{NON_ADMIN}")
        assert revoked.json()["deleted"] is True
    async with _client(app.state._test_non_admin_cookie) as client:
        miss = await client.get("/api/secrets/scopes/api-acl-rm/secrets")
        assert miss.status_code == 404


@pytest.mark.asyncio
async def test_scope_delete_requires_manage() -> None:
    await _create_scope(app.state._test_auth_cookie, "api-del")
    async with _client(app.state._test_auth_cookie) as admin:
        await admin.put(
            f"/api/secrets/scopes/api-del/acls/{NON_ADMIN}", json={"permission": "WRITE"}
        )
    async with _client(app.state._test_non_admin_cookie) as client:
        denied = await client.delete("/api/secrets/scopes/api-del")
        assert denied.status_code == 403
    async with _client(app.state._test_auth_cookie) as admin:
        ok = await admin.delete("/api/secrets/scopes/api-del")
        assert ok.json()["deleted"] is True
        miss = await admin.get("/api/secrets/scopes/api-del/secrets")
        assert miss.status_code == 404


@pytest.mark.asyncio
async def test_admin_secrets_page_admin_only() -> None:
    async with _client(app.state._test_auth_cookie) as admin:
        page = await admin.get("/admin/secrets")
        assert page.status_code == 200
        assert 'x-data="adminSecrets()"' in page.text
        assert "admin_secrets.js" in page.text
    async with _client(app.state._test_non_admin_cookie) as client:
        denied = await client.get("/admin/secrets")
        assert denied.status_code == 403


@pytest.mark.asyncio
async def test_validation_errors() -> None:
    async with _client(app.state._test_auth_cookie) as admin:
        bad_name = await admin.post("/api/secrets/scopes", json={"name": "has space"})
        assert bad_name.status_code == 422
        await admin.post("/api/secrets/scopes", json={"name": "api-val"})
        bad_value = await admin.put("/api/secrets/scopes/api-val/secrets/k", json={"value": 42})
        assert bad_value.status_code == 422
        bad_perm = await admin.put(
            "/api/secrets/scopes/api-val/acls/x@test.com", json={"permission": "ALL"}
        )
        assert bad_perm.status_code == 422
