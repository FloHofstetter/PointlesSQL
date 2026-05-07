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
