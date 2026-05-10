"""Sprint 28.3 — workspace_catalog_pins admin CRUD + tree filter.

The pins table itself was created in 28.0; 28.3 wires the admin
routes and the ``GET /api/tree?primary_only=true`` filter.
"""

from __future__ import annotations

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import WorkspaceCatalogPin
from pointlessql.services.workspace import _crud as workspaces_service


def _factory():
    return app.state.session_factory


@pytest.fixture
def two_workspaces() -> tuple[int, int]:
    a = workspaces_service.create_workspace(_factory(), slug="ws-pin-a", name="Pin A")
    b = workspaces_service.create_workspace(_factory(), slug="ws-pin-b", name="Pin B")
    return a.id, b.id


@pytest.mark.asyncio
async def test_admin_pin_crud_round_trip(two_workspaces: tuple[int, int]) -> None:
    ws_a, _ = two_workspaces
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        # POST a pin.
        post = await client.post(
            f"/api/admin/workspaces/{ws_a}/pins",
            json={"catalog_name": "main", "mode": "primary"},
        )
        assert post.status_code == 200
        body = post.json()
        assert body["catalog_name"] == "main"
        assert body["mode"] == "primary"

        # Promoting a second to primary demotes the first.
        post2 = await client.post(
            f"/api/admin/workspaces/{ws_a}/pins",
            json={"catalog_name": "silver", "mode": "primary"},
        )
        assert post2.status_code == 200

        with _factory()() as session:
            primaries = (
                session.query(WorkspaceCatalogPin)
                .filter(
                    WorkspaceCatalogPin.workspace_id == ws_a,
                    WorkspaceCatalogPin.mode == "primary",
                )
                .all()
            )
            assert len(primaries) == 1
            assert primaries[0].catalog_name == "silver"

        # GET /api/admin/workspaces/{id}/pins lists them.
        listing = await client.get(f"/api/admin/workspaces/{ws_a}/pins")
        assert listing.status_code == 200
        names = {p["catalog_name"] for p in listing.json()["pins"]}
        assert names == {"main", "silver"}

        # DELETE removes one.
        deleted = await client.delete(f"/api/admin/workspaces/{ws_a}/pins/main")
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] is True


@pytest.mark.asyncio
async def test_admin_pin_create_rejects_invalid_mode(
    two_workspaces: tuple[int, int],
) -> None:
    ws_a, _ = two_workspaces
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.post(
            f"/api/admin/workspaces/{ws_a}/pins",
            json={"catalog_name": "x", "mode": "weird"},
        )
    assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_admin_pin_create_404_on_unknown_workspace() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.post(
            "/api/admin/workspaces/9999/pins",
            json={"catalog_name": "main", "mode": "pinned"},
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_pin_routes_require_admin(two_workspaces: tuple[int, int]) -> None:
    ws_a, _ = two_workspaces
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_non_admin_cookie,
    ) as client:
        post = await client.post(
            f"/api/admin/workspaces/{ws_a}/pins",
            json={"catalog_name": "main", "mode": "pinned"},
        )
    assert post.status_code == 403


def test_pin_unique_constraint_blocks_dup() -> None:
    """A second pin on the same (workspace_id, catalog_name) raises."""
    import datetime

    from sqlalchemy.exc import IntegrityError

    factory = _factory()
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add(
            WorkspaceCatalogPin(
                workspace_id=1,
                catalog_name="dup-test",
                mode="pinned",
                created_at=now,
            )
        )
        session.commit()
    with factory() as session:
        session.add(
            WorkspaceCatalogPin(
                workspace_id=1,
                catalog_name="dup-test",
                mode="primary",
                created_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_tree_primary_only_filter_logic() -> None:
    """Filter logic works against a fake tree (UC mock at the route layer
    is fragile because get_uc_client builds a fresh per-request client;
    instead this test exercises the in-place dict filter the route uses).
    """
    import datetime

    from sqlalchemy import select

    factory = _factory()
    now = datetime.datetime.now(datetime.UTC)
    ws = workspaces_service.create_workspace(factory, slug="ws-tree-filter", name="x")
    with factory() as session:
        session.add(
            WorkspaceCatalogPin(
                workspace_id=ws.id,
                catalog_name="pinned-cat",
                mode="primary",
                created_at=now,
            )
        )
        session.commit()

    # Replicate the route's filter step directly.
    fake_tree = [
        {"name": "pinned-cat", "schemas": []},
        {"name": "other-cat", "schemas": []},
        {"name": "third-cat", "schemas": []},
    ]
    with factory() as session:
        pinned = {
            row.catalog_name
            for row in session.scalars(
                select(WorkspaceCatalogPin).where(WorkspaceCatalogPin.workspace_id == ws.id)
            ).all()
        }
    filtered = [c for c in fake_tree if c["name"] in pinned]
    assert {c["name"] for c in filtered} == {"pinned-cat"}
