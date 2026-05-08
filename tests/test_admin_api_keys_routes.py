"""Tests for the Sprint 13.11.4a admin api-keys CRUD."""

from __future__ import annotations

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import ApiKey
from pointlessql.services import api_keys as api_keys_service


def _wipe() -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.query(ApiKey).delete()
        session.commit()
    api_keys_service.invalidate_cache()


@pytest.mark.asyncio
async def test_non_admin_cannot_create_or_list(
    non_admin_client: httpx.AsyncClient,
) -> None:
    _wipe()
    list_resp = await non_admin_client.get("/api/admin/api-keys")
    create_resp = await non_admin_client.post("/api/admin/api-keys", json={"name": "evil"})
    assert list_resp.status_code == 403
    assert create_resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_create_returns_plaintext_secret_once(
    admin_client: httpx.AsyncClient,
) -> None:
    _wipe()
    response = await admin_client.post(
        "/api/admin/api-keys",
        json={"name": "hermes", "supervisor": True},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["name"] == "hermes"
    assert payload["supervisor"] is True
    assert isinstance(payload["secret"], str) and len(payload["secret"]) >= 32
    assert payload["secret"].startswith(payload["secret_prefix"])
    _wipe()


@pytest.mark.asyncio
async def test_admin_list_returns_keys_without_plaintext(
    admin_client: httpx.AsyncClient,
) -> None:
    _wipe()
    await admin_client.post("/api/admin/api-keys", json={"name": "k1"})
    await admin_client.post("/api/admin/api-keys", json={"name": "sup", "supervisor": True})
    response = await admin_client.get("/api/admin/api-keys")
    assert response.status_code == 200
    keys = response.json()["keys"]
    names = {k["name"] for k in keys}
    assert names == {"k1", "sup"}
    for k in keys:
        assert "secret" not in k
        assert isinstance(k["secret_prefix"], str)
    _wipe()


@pytest.mark.asyncio
async def test_admin_revoke_marks_revoked_and_blocks_auth(
    admin_client: httpx.AsyncClient,
    anonymous_client: httpx.AsyncClient,
) -> None:
    _wipe()
    create = await admin_client.post("/api/admin/api-keys", json={"name": "rotateme"})
    plaintext = create.json()["secret"]
    revoke = await admin_client.post("/api/admin/api-keys/rotateme/revoke")
    assert revoke.status_code == 200
    assert revoke.json() == {"name": "rotateme", "revoked": True}
    # Use the revoked plaintext on a protected route — must 401.
    response = await anonymous_client.get(
        "/api/agent-runs",
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert response.status_code == 401
    _wipe()


@pytest.mark.asyncio
async def test_admin_revoke_404_for_unknown_name(
    admin_client: httpx.AsyncClient,
) -> None:
    _wipe()
    response = await admin_client.post("/api/admin/api-keys/unknown/revoke")
    assert response.status_code == 404
    _wipe()


# -- Sprint 57.7 — edge-case extension --


@pytest.mark.asyncio
async def test_create_rejects_empty_name(admin_client: httpx.AsyncClient) -> None:
    _wipe()
    response = await admin_client.post("/api/admin/api-keys", json={"name": "  "})
    assert response.status_code == 422
    _wipe()


@pytest.mark.asyncio
async def test_create_rejects_missing_name(admin_client: httpx.AsyncClient) -> None:
    _wipe()
    response = await admin_client.post("/api/admin/api-keys", json={})
    assert response.status_code == 422
    _wipe()


@pytest.mark.asyncio
async def test_create_rejects_non_positive_workspace_id(
    admin_client: httpx.AsyncClient,
) -> None:
    _wipe()
    response = await admin_client.post(
        "/api/admin/api-keys", json={"name": "k", "workspace_id": 0}
    )
    assert response.status_code == 422
    _wipe()


@pytest.mark.asyncio
async def test_create_rejects_duplicate_active_name(
    admin_client: httpx.AsyncClient,
) -> None:
    """A name unique among active keys cannot be reused while the first lives."""
    _wipe()
    first = await admin_client.post("/api/admin/api-keys", json={"name": "dup"})
    assert first.status_code == 200
    second = await admin_client.post("/api/admin/api-keys", json={"name": "dup"})
    assert second.status_code == 422
    _wipe()


@pytest.mark.asyncio
async def test_revoke_twice_returns_404_second_time(
    admin_client: httpx.AsyncClient,
) -> None:
    _wipe()
    await admin_client.post("/api/admin/api-keys", json={"name": "rotateme"})
    first = await admin_client.post("/api/admin/api-keys/rotateme/revoke")
    second = await admin_client.post("/api/admin/api-keys/rotateme/revoke")
    assert first.status_code == 200
    assert second.status_code == 404
    _wipe()


@pytest.mark.asyncio
async def test_list_include_revoked_surfaces_inactive(
    admin_client: httpx.AsyncClient,
) -> None:
    """``?include_revoked=true`` shows revoked keys; default hides them."""
    _wipe()
    await admin_client.post("/api/admin/api-keys", json={"name": "active"})
    await admin_client.post("/api/admin/api-keys", json={"name": "killed"})
    await admin_client.post("/api/admin/api-keys/killed/revoke")

    default = await admin_client.get("/api/admin/api-keys")
    visible = {k["name"] for k in default.json()["keys"]}
    assert visible == {"active"}

    with_revoked = await admin_client.get(
        "/api/admin/api-keys?include_revoked=true"
    )
    visible_all = {k["name"] for k in with_revoked.json()["keys"]}
    assert visible_all == {"active", "killed"}
    _wipe()


@pytest.mark.asyncio
async def test_create_supervisor_and_auditor_combo(
    admin_client: httpx.AsyncClient,
) -> None:
    _wipe()
    response = await admin_client.post(
        "/api/admin/api-keys",
        json={"name": "supaud", "supervisor": True, "auditor": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["supervisor"] is True
    assert body["auditor"] is True
    _wipe()


@pytest.mark.asyncio
async def test_non_admin_cannot_revoke(non_admin_client: httpx.AsyncClient) -> None:
    _wipe()
    # Non-admin can't even reach the revoke handler — the require_admin
    # gate fires before the missing-key 404 path, so we get 403.
    resp = await non_admin_client.post("/api/admin/api-keys/anything/revoke")
    assert resp.status_code == 403
    _wipe()
