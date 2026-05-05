"""Sprint 28.6 — admin workspace CRUD + member management routes."""

from __future__ import annotations

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.services import auth as auth_service
from pointlessql.services import workspaces as workspaces_service


def _factory():
    return app.state.session_factory


# ---------------------------------------------------------------------------
# workspace CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_create_and_list_workspace() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        post = await client.post(
            "/api/admin/workspaces",
            json={"slug": "admin-create-a", "name": "Admin Create A"},
        )
    assert post.status_code == 200
    body = post.json()
    assert body["slug"] == "admin-create-a"
    assert body["name"] == "Admin Create A"
    assert body["archived_at"] is None

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        listing = await client.get("/api/admin/workspaces")
    slugs = {ws["slug"] for ws in listing.json()["workspaces"]}
    assert "default" in slugs
    assert "admin-create-a" in slugs


@pytest.mark.asyncio
async def test_admin_create_rejects_duplicate_slug() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        first = await client.post(
            "/api/admin/workspaces",
            json={"slug": "admin-dup", "name": "Dup"},
        )
        assert first.status_code == 200
        second = await client.post(
            "/api/admin/workspaces",
            json={"slug": "admin-dup", "name": "Dup again"},
        )
    assert second.status_code in (400, 422)


@pytest.mark.asyncio
async def test_admin_create_requires_admin() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_non_admin_cookie,
    ) as client:
        response = await client.post(
            "/api/admin/workspaces",
            json={"slug": "admin-non-admin", "name": "x"},
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_update_workspace_renames() -> None:
    ws = workspaces_service.create_workspace(_factory(), slug="admin-rename", name="original")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.patch(
            f"/api/admin/workspaces/{ws.id}",
            json={"name": "updated", "description": "new desc"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "updated"
    assert body["description"] == "new desc"


@pytest.mark.asyncio
async def test_admin_archive_workspace_sets_timestamp() -> None:
    ws = workspaces_service.create_workspace(
        _factory(), slug="admin-archive-target", name="Archive Me"
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.post(f"/api/admin/workspaces/{ws.id}/archive")
    assert response.status_code == 200
    assert response.json()["archived_at"] is not None


@pytest.mark.asyncio
async def test_admin_cannot_archive_default_workspace() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.post("/api/admin/workspaces/1/archive")
    assert response.status_code in (400, 422)


# ---------------------------------------------------------------------------
# members
# ---------------------------------------------------------------------------


def _create_extra_user(email: str) -> int:
    user = auth_service.register(_factory(), email, email.split("@")[0], "password123")
    assert user is not None
    return user.id


@pytest.mark.asyncio
async def test_admin_add_member_by_email() -> None:
    ws = workspaces_service.create_workspace(_factory(), slug="admin-mem-a", name="MemA")
    extra_email = "extra-member-a@test.com"
    _create_extra_user(extra_email)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.post(
            f"/api/admin/workspaces/{ws.id}/members",
            json={"user_email": extra_email, "role": "admin"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["user_email"] == extra_email
    assert body["role"] == "admin"


@pytest.mark.asyncio
async def test_admin_change_member_role() -> None:
    ws = workspaces_service.create_workspace(_factory(), slug="admin-mem-b", name="MemB")
    user_id = _create_extra_user("extra-role@test.com")
    workspaces_service.add_member(_factory(), workspace_id=ws.id, user_id=user_id, role="member")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.patch(
            f"/api/admin/workspaces/{ws.id}/members/{user_id}",
            json={"role": "admin"},
        )
    assert response.status_code == 200
    assert response.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_admin_remove_member() -> None:
    ws = workspaces_service.create_workspace(_factory(), slug="admin-mem-c", name="MemC")
    user_id = _create_extra_user("extra-remove@test.com")
    workspaces_service.add_member(_factory(), workspace_id=ws.id, user_id=user_id, role="member")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.delete(f"/api/admin/workspaces/{ws.id}/members/{user_id}")
    assert response.status_code == 200
    assert response.json()["deleted"] is True


@pytest.mark.asyncio
async def test_admin_list_members_includes_emails() -> None:
    ws = workspaces_service.create_workspace(_factory(), slug="admin-mem-d", name="MemD")
    user_id = _create_extra_user("extra-list@test.com")
    workspaces_service.add_member(_factory(), workspace_id=ws.id, user_id=user_id, role="member")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.get(f"/api/admin/workspaces/{ws.id}/members")
    body = response.json()
    emails = {m["user_email"] for m in body["members"]}
    assert "extra-list@test.com" in emails


# ---------------------------------------------------------------------------
# HTML page
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_workspaces_page_renders() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.get("/admin/workspaces")
    assert response.status_code == 200
    body = response.text
    assert "Workspaces" in body
    assert "Create workspace" in body


@pytest.mark.asyncio
async def test_admin_workspaces_page_403s_for_non_admin() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_non_admin_cookie,
    ) as client:
        response = await client.get("/admin/workspaces")
    assert response.status_code == 403
