"""Tests for App Spaces — governance grouping of hosted apps."""

from __future__ import annotations

import datetime
import uuid

import httpx
import pytest

from pointlessql.api.main import app as fastapi_app
from pointlessql.exceptions import ValidationError
from pointlessql.models import HostedApp, Workspace
from pointlessql.services import app_spaces


def _factory():
    return fastapi_app.state.session_factory


def _fresh_workspace() -> int:
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        ws = Workspace(slug=f"as-{uuid.uuid4().hex[:10]}", name="App space test", created_at=now)
        session.add(ws)
        session.commit()
        session.refresh(ws)
        return int(ws.id)


def _seed_app(ws: int, *, slug: str, title: str = "App") -> int:
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        app = HostedApp(
            workspace_id=ws,
            slug=slug,
            title=title,
            kind="fastapi",
            source_code="",
            state="stopped",
            created_by_user_id=1,
            created_at=now,
            updated_at=now,
        )
        session.add(app)
        session.commit()
        session.refresh(app)
        return int(app.id)


def test_create_dedupes_scopes_and_lists() -> None:
    ws = _fresh_workspace()
    space = app_spaces.create_space(
        _factory(), workspace_id=ws, name="grp", description="d", api_scopes=["a", "b", "a", " "]
    )
    assert space["api_scopes"] == ["a", "b"]
    assert space["app_count"] == 0
    listed = app_spaces.list_spaces(_factory(), workspace_id=ws)
    assert [s["name"] for s in listed] == ["grp"]


def test_create_validations() -> None:
    ws = _fresh_workspace()
    with pytest.raises(ValidationError, match="required"):
        app_spaces.create_space(_factory(), workspace_id=ws, name="")
    app_spaces.create_space(_factory(), workspace_id=ws, name="dup")
    with pytest.raises(ValidationError, match="already exists"):
        app_spaces.create_space(_factory(), workspace_id=ws, name="dup")


def test_assign_and_effective_scopes() -> None:
    ws = _fresh_workspace()
    space = app_spaces.create_space(
        _factory(), workspace_id=ws, name="grp", api_scopes=["sql.read"]
    )
    app_id = _seed_app(ws, slug="a1")
    app_spaces.assign_app(_factory(), workspace_id=ws, app_id=app_id, space_id=space["id"])

    eff = app_spaces.effective_app_scopes(_factory(), app_id=app_id)
    assert eff["space_id"] == space["id"]
    assert eff["api_scopes"] == ["sql.read"]

    # Detaching clears the effective scopes.
    app_spaces.assign_app(_factory(), workspace_id=ws, app_id=app_id, space_id=None)
    assert app_spaces.effective_app_scopes(_factory(), app_id=app_id)["api_scopes"] == []


def test_assign_rejects_foreign() -> None:
    ws = _fresh_workspace()
    space = app_spaces.create_space(_factory(), workspace_id=ws, name="grp")
    with pytest.raises(ValidationError, match="hosted app"):
        app_spaces.assign_app(_factory(), workspace_id=ws, app_id=987654, space_id=space["id"])
    app_id = _seed_app(ws, slug="a2")
    with pytest.raises(ValidationError, match="app space"):
        app_spaces.assign_app(_factory(), workspace_id=ws, app_id=app_id, space_id=987654)


def test_delete_ungroups_member_apps() -> None:
    ws = _fresh_workspace()
    space = app_spaces.create_space(_factory(), workspace_id=ws, name="grp", api_scopes=["x"])
    app_id = _seed_app(ws, slug="a3")
    app_spaces.assign_app(_factory(), workspace_id=ws, app_id=app_id, space_id=space["id"])

    assert app_spaces.delete_space(_factory(), space_id=space["id"], workspace_id=ws) is True
    assert app_spaces.delete_space(_factory(), space_id=space["id"], workspace_id=ws) is False
    # The app survives, now ungrouped.
    assert app_spaces.effective_app_scopes(_factory(), app_id=app_id)["api_scopes"] == []


def test_update_and_delete_reject_foreign_workspace() -> None:
    # A space owned by one workspace cannot be edited or deleted through
    # another, even with the correct space id.
    owner = _fresh_workspace()
    other = _fresh_workspace()
    space = app_spaces.create_space(_factory(), workspace_id=owner, name="grp", description="keep")
    with pytest.raises(ValidationError, match="not found"):
        app_spaces.update_space(
            _factory(), space_id=space["id"], workspace_id=other, description="hijack"
        )
    assert app_spaces.delete_space(_factory(), space_id=space["id"], workspace_id=other) is False
    # Untouched for the real owner.
    still = app_spaces.list_spaces(_factory(), workspace_id=owner)
    assert still[0]["description"] == "keep"


def test_update_clears_description_on_explicit_null() -> None:
    # A JSON null on the route clears the field rather than storing the
    # literal string "None".
    ws = _fresh_workspace()
    space = app_spaces.create_space(_factory(), workspace_id=ws, name="grp", description="initial")
    updated = app_spaces.update_space(
        _factory(), space_id=space["id"], workspace_id=ws, description=""
    )
    assert updated["description"] is None


def test_list_counts_members() -> None:
    ws = _fresh_workspace()
    space = app_spaces.create_space(_factory(), workspace_id=ws, name="grp")
    for i in range(2):
        aid = _seed_app(ws, slug=f"a-{i}")
        app_spaces.assign_app(_factory(), workspace_id=ws, app_id=aid, space_id=space["id"])
    listed = app_spaces.list_spaces(_factory(), workspace_id=ws)
    assert listed[0]["app_count"] == 2


@pytest.mark.asyncio
async def test_route_create_assign_list(admin_client: httpx.AsyncClient) -> None:
    name = f"sp-{uuid.uuid4().hex[:8]}"
    app_id = _seed_app(1, slug=f"app-{uuid.uuid4().hex[:8]}")

    created = await admin_client.post(
        "/api/admin/app-spaces", json={"name": name, "api_scopes": ["sql.read"]}
    )
    assert created.status_code == 200, created.text
    space_id = created.json()["space"]["id"]

    assigned = await admin_client.post(
        "/api/admin/app-spaces/assign", json={"app_id": app_id, "space_id": space_id}
    )
    assert assigned.status_code == 200
    assert assigned.json()["app_space_id"] == space_id

    listed = await admin_client.get("/api/admin/app-spaces")
    data = listed.json()
    assert any(s["name"] == name and s["app_count"] >= 1 for s in data["spaces"])

    deleted = await admin_client.delete(f"/api/admin/app-spaces/{space_id}")
    assert deleted.json()["deleted"] is True


@pytest.mark.asyncio
async def test_route_patch_null_description_clears(admin_client: httpx.AsyncClient) -> None:
    name = f"sp-{uuid.uuid4().hex[:8]}"
    created = await admin_client.post(
        "/api/admin/app-spaces", json={"name": name, "description": "initial"}
    )
    assert created.status_code == 200, created.text
    space_id = created.json()["space"]["id"]

    patched = await admin_client.patch(
        f"/api/admin/app-spaces/{space_id}", json={"description": None}
    )
    assert patched.status_code == 200, patched.text
    # A JSON null clears the field — it must not persist the text "None".
    assert patched.json()["space"]["description"] is None

    await admin_client.delete(f"/api/admin/app-spaces/{space_id}")


@pytest.mark.asyncio
async def test_route_page_renders(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.get("/admin/app-spaces")
    assert resp.status_code == 200, resp.text
    assert "App spaces" in resp.text


@pytest.mark.asyncio
async def test_route_requires_admin(non_admin_client: httpx.AsyncClient) -> None:
    resp = await non_admin_client.get("/api/admin/app-spaces")
    assert resp.status_code in {401, 403}
