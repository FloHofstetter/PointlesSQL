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


@pytest.mark.asyncio
async def test_create_returns_token_format_and_env_fields(
    admin_client: httpx.AsyncClient,
) -> None:
    """Phase 118 — create response surfaces token_format + token_env."""
    _wipe()
    response = await admin_client.post(
        "/api/admin/api-keys", json={"name": "v1-key"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_format"] == "v1"
    assert body["token_env"] == "live"
    assert body["secret"].startswith("pql_live_v1_")
    _wipe()


@pytest.mark.asyncio
async def test_create_with_env_test_yields_test_token(
    admin_client: httpx.AsyncClient,
) -> None:
    _wipe()
    response = await admin_client.post(
        "/api/admin/api-keys", json={"name": "staging", "env": "test"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_env"] == "test"
    assert body["secret"].startswith("pql_test_v1_")
    _wipe()


@pytest.mark.asyncio
async def test_create_rejects_unknown_env(
    admin_client: httpx.AsyncClient,
) -> None:
    _wipe()
    response = await admin_client.post(
        "/api/admin/api-keys", json={"name": "k", "env": "prod"}
    )
    assert response.status_code == 422
    _wipe()


@pytest.mark.asyncio
async def test_list_includes_token_format_and_env(
    admin_client: httpx.AsyncClient,
) -> None:
    _wipe()
    await admin_client.post(
        "/api/admin/api-keys", json={"name": "k", "env": "test"}
    )
    listing = await admin_client.get("/api/admin/api-keys")
    keys = listing.json()["keys"]
    assert len(keys) == 1
    assert keys[0]["token_format"] == "v1"
    assert keys[0]["token_env"] == "test"
    _wipe()


# ---------------------------------------------------------------------------
# Phase 119 — lifecycle admin endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rotate_mints_successor_with_same_scopes(
    admin_client: httpx.AsyncClient,
) -> None:
    _wipe()
    await admin_client.post(
        "/api/admin/api-keys",
        json={"name": "rot", "supervisor": True, "auditor": True, "env": "test"},
    )
    resp = await admin_client.post(
        "/api/admin/api-keys/rot/rotate", json={"grace_seconds": 3600}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["predecessor"] == "rot"
    assert body["grace_seconds"] == 3600
    succ = body["successor"]
    assert succ["name"].startswith("rot-rotated-")
    assert succ["secret"].startswith("pql_test_v1_")  # env inherited
    assert succ["supervisor"] is True and succ["auditor"] is True
    _wipe()


@pytest.mark.asyncio
async def test_rotate_returns_404_for_missing_or_already_rotated(
    admin_client: httpx.AsyncClient,
) -> None:
    _wipe()
    resp_missing = await admin_client.post("/api/admin/api-keys/none/rotate")
    assert resp_missing.status_code == 404
    await admin_client.post("/api/admin/api-keys", json={"name": "twice"})
    first = await admin_client.post("/api/admin/api-keys/twice/rotate")
    assert first.status_code == 200
    second = await admin_client.post("/api/admin/api-keys/twice/rotate")
    assert second.status_code == 404
    _wipe()


@pytest.mark.asyncio
async def test_rotate_rejects_invalid_grace_seconds(
    admin_client: httpx.AsyncClient,
) -> None:
    _wipe()
    await admin_client.post("/api/admin/api-keys", json={"name": "k"})
    resp = await admin_client.post(
        "/api/admin/api-keys/k/rotate", json={"grace_seconds": -1}
    )
    assert resp.status_code == 422
    _wipe()


@pytest.mark.asyncio
async def test_quarantine_and_unquarantine_round_trip(
    admin_client: httpx.AsyncClient,
) -> None:
    _wipe()
    create = await admin_client.post("/api/admin/api-keys", json={"name": "q1"})
    secret = create.json()["secret"]

    q_resp = await admin_client.post(
        "/api/admin/api-keys/q1/quarantine", json={"reason": "drill"}
    )
    assert q_resp.status_code == 200 and q_resp.json()["quarantined"] is True

    # Bearer auth must fail while quarantined.
    from pointlessql.api.main import app
    from pointlessql.services import api_keys as api_keys_service

    api_keys_service.invalidate_cache()
    assert (
        api_keys_service.verify_bearer(f"Bearer {secret}", app.state.session_factory)
        is None
    )

    u_resp = await admin_client.post("/api/admin/api-keys/q1/unquarantine")
    assert u_resp.status_code == 200 and u_resp.json()["quarantined"] is False

    # Cache was invalidated; auth works again.
    assert (
        api_keys_service.verify_bearer(f"Bearer {secret}", app.state.session_factory)
        is not None
    )
    _wipe()


@pytest.mark.asyncio
async def test_quarantine_rejects_missing_reason(
    admin_client: httpx.AsyncClient,
) -> None:
    _wipe()
    await admin_client.post("/api/admin/api-keys", json={"name": "noargs"})
    resp = await admin_client.post(
        "/api/admin/api-keys/noargs/quarantine", json={}
    )
    assert resp.status_code == 422
    _wipe()


@pytest.mark.asyncio
async def test_patch_expires_at_set_then_clear(
    admin_client: httpx.AsyncClient,
) -> None:
    from datetime import UTC, datetime, timedelta

    _wipe()
    await admin_client.post("/api/admin/api-keys", json={"name": "ttl"})
    future = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    set_resp = await admin_client.patch(
        "/api/admin/api-keys/ttl", json={"expires_at": future}
    )
    assert set_resp.status_code == 200
    listing = await admin_client.get("/api/admin/api-keys")
    row = next(k for k in listing.json()["keys"] if k["name"] == "ttl")
    assert row["expires_at"] is not None

    clear_resp = await admin_client.patch(
        "/api/admin/api-keys/ttl", json={"expires_at": None}
    )
    assert clear_resp.status_code == 200
    listing2 = await admin_client.get("/api/admin/api-keys")
    row2 = next(k for k in listing2.json()["keys"] if k["name"] == "ttl")
    assert row2["expires_at"] is None
    _wipe()


@pytest.mark.asyncio
async def test_patch_rejects_unparseable_expires_at(
    admin_client: httpx.AsyncClient,
) -> None:
    _wipe()
    await admin_client.post("/api/admin/api-keys", json={"name": "bad"})
    resp = await admin_client.patch(
        "/api/admin/api-keys/bad", json={"expires_at": "not-a-datetime"}
    )
    assert resp.status_code == 422
    _wipe()
