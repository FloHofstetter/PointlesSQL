"""admin JSON API for workspace-repos.

Covers admin-gating, reveal-once webhook secret on creation,
secret roundtrip metadata-only on subsequent reads, sync
endpoint, secret rotation, and cascade-delete.
"""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_list_repos_requires_admin(non_admin_client: httpx.AsyncClient) -> None:
    res = await non_admin_client.get("/api/admin/repos")
    assert res.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_repo_reveals_webhook_once(admin_client: httpx.AsyncClient) -> None:
    res = await admin_client.post(
        "/api/admin/repos",
        json={
            "slug": "platform-yaml",
            "url": "file:///tmp/no-such-repo.git",
            "default_branch": "main",
            "provider_kind": "generic",
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["slug"] == "platform-yaml"
    assert "webhook_secret" in payload
    assert len(payload["webhook_secret"]) >= 32
    repo_id = payload["id"]

    detail = await admin_client.get(f"/api/admin/repos/{repo_id}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert "webhook_secret" not in detail_payload
    assert detail_payload["secrets"] == []


@pytest.mark.asyncio
async def test_create_repo_with_secret_metadata_visible(admin_client: httpx.AsyncClient) -> None:
    res = await admin_client.post(
        "/api/admin/repos",
        json={
            "slug": "with-secret",
            "url": "https://example.com/repo.git",
            "provider_kind": "generic",
            "initial_secret_kind": "https_token",
            "initial_secret_plaintext": "ghp_test_token",
        },
    )
    assert res.status_code == 200
    repo_id = res.json()["id"]
    detail = await admin_client.get(f"/api/admin/repos/{repo_id}")
    secrets = detail.json()["secrets"]
    assert len(secrets) == 1
    assert secrets[0]["kind"] == "https_token"
    assert "plaintext" not in secrets[0]
    assert "encrypted_value" not in secrets[0]


@pytest.mark.asyncio
async def test_create_repo_rejects_unknown_provider(admin_client: httpx.AsyncClient) -> None:
    res = await admin_client.post(
        "/api/admin/repos",
        json={"slug": "bad", "url": "https://example.com/repo.git", "provider_kind": "gitlab"},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_add_secret_then_revoke(admin_client: httpx.AsyncClient) -> None:
    create = await admin_client.post(
        "/api/admin/repos",
        json={"slug": "rotatable", "url": "https://example.com/repo.git"},
    )
    repo_id = create.json()["id"]

    fake_key = "-----BEGIN OPENSSH PRIVATE KEY-----\nfake\n-----END OPENSSH PRIVATE KEY-----\n"
    add = await admin_client.post(
        f"/api/admin/repos/{repo_id}/secrets",
        json={"kind": "deploy_key", "plaintext": fake_key},
    )
    assert add.status_code == 200
    assert add.json()["kind"] == "deploy_key"

    detail = await admin_client.get(f"/api/admin/repos/{repo_id}")
    assert any(s["kind"] == "deploy_key" for s in detail.json()["secrets"])

    revoke = await admin_client.delete(f"/api/admin/repos/{repo_id}/secrets/deploy_key")
    assert revoke.status_code == 200
    assert revoke.json()["revoked"] is True

    detail2 = await admin_client.get(f"/api/admin/repos/{repo_id}")
    assert all(s["kind"] != "deploy_key" for s in detail2.json()["secrets"])


@pytest.mark.asyncio
async def test_rotate_webhook_secret(admin_client: httpx.AsyncClient) -> None:
    create = await admin_client.post(
        "/api/admin/repos",
        json={"slug": "rotate-me", "url": "https://example.com/repo.git"},
    )
    original = create.json()["webhook_secret"]
    repo_id = create.json()["id"]

    rotate = await admin_client.post(f"/api/admin/repos/{repo_id}/rotate-webhook-secret")
    assert rotate.status_code == 200
    assert rotate.json()["webhook_secret"] != original


@pytest.mark.asyncio
async def test_sync_repo_returns_outcome_envelope(admin_client: httpx.AsyncClient) -> None:
    create = await admin_client.post(
        "/api/admin/repos",
        json={"slug": "syncme", "url": "file:///tmp/does-not-exist.git"},
    )
    repo_id = create.json()["id"]
    res = await admin_client.post(f"/api/admin/repos/{repo_id}/sync")
    assert res.status_code == 200
    payload = res.json()
    # Sync against a bogus URL fails — but the route still returns 200 with
    # ok=False so the admin UI can render the diagnostic.
    assert payload["ok"] is False
    assert payload["error"] is not None


@pytest.mark.asyncio
async def test_delete_repo_returns_deleted_true(admin_client: httpx.AsyncClient) -> None:
    create = await admin_client.post(
        "/api/admin/repos",
        json={"slug": "byebye", "url": "https://example.com/repo.git"},
    )
    repo_id = create.json()["id"]
    res = await admin_client.delete(f"/api/admin/repos/{repo_id}")
    assert res.status_code == 200
    assert res.json()["deleted"] is True
    follow = await admin_client.get(f"/api/admin/repos/{repo_id}")
    assert follow.status_code == 404


@pytest.mark.asyncio
async def test_get_repo_404_for_unknown(admin_client: httpx.AsyncClient) -> None:
    res = await admin_client.get("/api/admin/repos/99999")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_list_repos_filters_by_workspace(admin_client: httpx.AsyncClient) -> None:
    res = await admin_client.get("/api/admin/repos")
    assert res.status_code == 200
    payload = res.json()
    assert "workspace_id" in payload
    assert isinstance(payload["repos"], list)
    for row in payload["repos"]:
        assert row["workspace_id"] == payload["workspace_id"]
