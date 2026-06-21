"""Tests for the governed MCP service registry.

The service-level tests each run in a freshly-created workspace so the
session-scoped test DB (no per-test rollback) cannot leak services
between cases; the route tests hit the admin endpoints in the default
workspace with uniquely-named services and assert shape + auth.
"""

from __future__ import annotations

import datetime
import uuid

import httpx
import pytest

from pointlessql.api.main import app as fastapi_app
from pointlessql.models import Workspace
from pointlessql.services import mcp_registry


def _factory():
    return fastapi_app.state.session_factory


def _fresh_workspace() -> int:
    """Create an isolated workspace and return its id."""
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        ws = Workspace(
            slug=f"mcp-{uuid.uuid4().hex[:10]}",
            name="MCP registry test workspace",
            created_at=now,
        )
        session.add(ws)
        session.commit()
        session.refresh(ws)
        return int(ws.id)


def test_register_and_list_service() -> None:
    ws = _fresh_workspace()
    created = mcp_registry.register_service(
        _factory(),
        workspace_id=ws,
        name="slack",
        url="https://mcp.example.com/sse",
        transport="sse",
        description="Slack workspace tools",
        secret_scope="slack-creds",
        created_by="admin@test.com",
    )
    assert created["name"] == "slack"
    assert created["transport"] == "sse"
    assert created["enabled"] is True
    assert created["tool_count"] == 0

    listed = mcp_registry.list_services(_factory(), workspace_id=ws)
    assert [svc["name"] for svc in listed] == ["slack"]
    assert listed[0]["secret_scope"] == "slack-creds"


def test_register_rejects_bad_transport_and_duplicate() -> None:
    ws = _fresh_workspace()
    with pytest.raises(ValueError, match="transport must be one of"):
        mcp_registry.register_service(
            _factory(), workspace_id=ws, name="x", url="u", transport="grpc"
        )
    mcp_registry.register_service(
        _factory(), workspace_id=ws, name="jira", url="u", transport="http"
    )
    with pytest.raises(ValueError, match="already exists"):
        mcp_registry.register_service(
            _factory(), workspace_id=ws, name="jira", url="u2", transport="http"
        )


def test_tool_lifecycle_and_per_tool_toggle() -> None:
    ws = _fresh_workspace()
    svc = mcp_registry.register_service(
        _factory(), workspace_id=ws, name="github", url="u", transport="sse"
    )
    tool = mcp_registry.add_tool(
        _factory(),
        service_id=svc["id"],
        workspace_id=ws,
        name="create_issue",
        description="Open an issue",
    )
    assert tool["enabled"] is True

    # A second tool, then disable the first.
    mcp_registry.add_tool(_factory(), service_id=svc["id"], workspace_id=ws, name="list_prs")
    mcp_registry.set_tool_enabled(
        _factory(), service_id=svc["id"], workspace_id=ws, tool_id=tool["id"], enabled=False
    )

    full = mcp_registry.get_service(_factory(), service_id=svc["id"], workspace_id=ws)
    assert full is not None
    assert full["tool_count"] == 2
    assert full["enabled_tool_count"] == 1

    # Duplicate tool name is rejected.
    with pytest.raises(ValueError, match="already exists"):
        mcp_registry.add_tool(_factory(), service_id=svc["id"], workspace_id=ws, name="list_prs")


def test_discover_filters_disabled_services_and_tools() -> None:
    ws = _fresh_workspace()
    published = mcp_registry.register_service(
        _factory(), workspace_id=ws, name="published", url="u", transport="sse"
    )
    mcp_registry.add_tool(_factory(), service_id=published["id"], workspace_id=ws, name="ok_tool")
    hidden_tool = mcp_registry.add_tool(
        _factory(), service_id=published["id"], workspace_id=ws, name="hidden_tool"
    )
    mcp_registry.set_tool_enabled(
        _factory(),
        service_id=published["id"],
        workspace_id=ws,
        tool_id=hidden_tool["id"],
        enabled=False,
    )

    # A wholly-disabled service must not appear at all.
    hidden_svc = mcp_registry.register_service(
        _factory(), workspace_id=ws, name="hidden", url="u", transport="sse"
    )
    mcp_registry.set_service_enabled(
        _factory(), service_id=hidden_svc["id"], workspace_id=ws, enabled=False
    )

    discovered = mcp_registry.discover_services(_factory(), workspace_id=ws)
    assert [svc["name"] for svc in discovered] == ["published"]
    tool_names = {tool["name"] for tool in discovered[0]["tools"]}
    assert tool_names == {"ok_tool"}
    assert discovered[0]["enabled_tool_count"] == 1


def test_update_service_rename_collision_and_clear_fields() -> None:
    ws = _fresh_workspace()
    mcp_registry.register_service(_factory(), workspace_id=ws, name="a", url="u", transport="sse")
    svc_b = mcp_registry.register_service(
        _factory(),
        workspace_id=ws,
        name="b",
        url="u",
        transport="sse",
        description="has one",
    )
    with pytest.raises(ValueError, match="already exists"):
        mcp_registry.update_service(_factory(), service_id=svc_b["id"], workspace_id=ws, name="a")

    cleared = mcp_registry.update_service(
        _factory(), service_id=svc_b["id"], workspace_id=ws, description="", transport="http"
    )
    assert cleared["description"] is None
    assert cleared["transport"] == "http"


def test_delete_service_cascades_tools() -> None:
    ws = _fresh_workspace()
    svc = mcp_registry.register_service(
        _factory(), workspace_id=ws, name="doomed", url="u", transport="sse"
    )
    mcp_registry.add_tool(_factory(), service_id=svc["id"], workspace_id=ws, name="t1")
    assert mcp_registry.delete_service(_factory(), service_id=svc["id"], workspace_id=ws) is True
    assert mcp_registry.get_service(_factory(), service_id=svc["id"], workspace_id=ws) is None
    # Idempotent: deleting again reports no row removed.
    assert mcp_registry.delete_service(_factory(), service_id=svc["id"], workspace_id=ws) is False


def test_set_tool_enabled_rejects_cross_service_tool() -> None:
    ws = _fresh_workspace()
    svc1 = mcp_registry.register_service(
        _factory(), workspace_id=ws, name="s1", url="u", transport="sse"
    )
    svc2 = mcp_registry.register_service(
        _factory(), workspace_id=ws, name="s2", url="u", transport="sse"
    )
    tool = mcp_registry.add_tool(_factory(), service_id=svc1["id"], workspace_id=ws, name="t")
    with pytest.raises(ValueError, match="not found"):
        mcp_registry.set_tool_enabled(
            _factory(), service_id=svc2["id"], workspace_id=ws, tool_id=tool["id"], enabled=False
        )


def test_by_id_ops_reject_foreign_workspace() -> None:
    # A service registered in one workspace must be invisible and
    # immutable from another, even with a guessed-correct service id.
    owner = _fresh_workspace()
    other = _fresh_workspace()
    svc = mcp_registry.register_service(
        _factory(), workspace_id=owner, name="owned", url="u", transport="sse"
    )
    tool = mcp_registry.add_tool(_factory(), service_id=svc["id"], workspace_id=owner, name="t")

    assert mcp_registry.get_service(_factory(), service_id=svc["id"], workspace_id=other) is None
    assert (
        mcp_registry.delete_service(_factory(), service_id=svc["id"], workspace_id=other) is False
    )
    assert (
        mcp_registry.delete_tool(
            _factory(), service_id=svc["id"], workspace_id=other, tool_id=tool["id"]
        )
        is False
    )
    for call in (
        lambda: mcp_registry.update_service(
            _factory(), service_id=svc["id"], workspace_id=other, name="x"
        ),
        lambda: mcp_registry.set_service_enabled(
            _factory(), service_id=svc["id"], workspace_id=other, enabled=False
        ),
        lambda: mcp_registry.add_tool(
            _factory(), service_id=svc["id"], workspace_id=other, name="y"
        ),
        lambda: mcp_registry.set_tool_enabled(
            _factory(), service_id=svc["id"], workspace_id=other, tool_id=tool["id"], enabled=False
        ),
    ):
        with pytest.raises(ValueError, match="not found"):
            call()

    # The owner still sees an untouched, enabled service + tool.
    full = mcp_registry.get_service(_factory(), service_id=svc["id"], workspace_id=owner)
    assert full is not None
    assert full["enabled"] is True
    assert full["tools"][0]["enabled"] is True


@pytest.mark.asyncio
async def test_route_register_list_and_toggle(admin_client: httpx.AsyncClient) -> None:
    token = uuid.uuid4().hex[:8]
    name = f"svc_{token}"
    created = await admin_client.post(
        "/api/admin/mcp-services",
        json={"name": name, "url": "https://x/sse", "transport": "sse"},
    )
    assert created.status_code == 200, created.text
    service_id = created.json()["service"]["id"]

    listed = await admin_client.get("/api/admin/mcp-services")
    assert listed.status_code == 200
    assert any(svc["name"] == name for svc in listed.json()["services"])

    # Add a tool, then confirm the published discovery view surfaces it.
    tool_resp = await admin_client.post(
        f"/api/admin/mcp-services/{service_id}/tools", json={"name": "do_thing"}
    )
    assert tool_resp.status_code == 200, tool_resp.text
    tool_id = tool_resp.json()["tool"]["id"]

    discover = await admin_client.get("/api/admin/mcp-services/discover")
    published = {svc["name"]: svc for svc in discover.json()["services"]}
    assert name in published
    assert {t["name"] for t in published[name]["tools"]} == {"do_thing"}

    # Disable the tool → it drops out of discovery.
    await admin_client.patch(
        f"/api/admin/mcp-services/{service_id}/tools/{tool_id}", json={"enabled": False}
    )
    discover2 = await admin_client.get("/api/admin/mcp-services/discover")
    published2 = {svc["name"]: svc for svc in discover2.json()["services"]}
    assert published2[name]["tools"] == []

    # Cleanup keeps the shared default workspace tidy for sibling tests.
    deleted = await admin_client.delete(f"/api/admin/mcp-services/{service_id}")
    assert deleted.json()["deleted"] is True


@pytest.mark.asyncio
async def test_route_page_renders(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.get("/admin/mcp-services")
    assert response.status_code == 200, response.text
    assert "MCP services" in response.text


@pytest.mark.asyncio
async def test_route_requires_admin(non_admin_client: httpx.AsyncClient) -> None:
    response = await non_admin_client.get("/api/admin/mcp-services")
    assert response.status_code in {401, 403}
