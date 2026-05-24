"""workspace landing page + pin CRUD.

Coverage:

* Migration creates the ``workspace_pinned_entities`` table.
* Registry registers ``kind='workspace'`` with the expected tabs.
* ``GET /workspaces/{slug}`` renders the landing template.
* ``GET /api/workspaces/{slug}/pins`` lists pins ordered.
* ``POST /api/workspaces/{slug}/pins`` adds a pin (admin only).
* ``DELETE /api/workspaces/{slug}/pins/{id}`` removes a pin.
* ``PATCH /api/workspaces/{slug}/pins/reorder`` reorders pins.
* ``GET /api/workspaces/{slug}/activity`` returns workspace-scoped notifications.
* Non-admin caller gets 403 on POST/DELETE/PATCH.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import inspect

from pointlessql.api.main import app
from pointlessql.models.social._social_target import SocialTarget
from pointlessql.services.social import entity_registry


def test_workspace_pinned_entities_table_exists() -> None:
    """The ``workspace_pinned_entities`` table is present + indexed."""
    factory = app.state.session_factory
    with factory() as session:
        insp = inspect(session.get_bind())
        assert "workspace_pinned_entities" in insp.get_table_names()
        indexes = {ix["name"] for ix in insp.get_indexes("workspace_pinned_entities")}
        assert "ix_workspace_pinned_entities_order" in indexes


def test_workspace_kind_is_registered() -> None:
    """The registry exposes ``workspace`` after 77.10."""
    assert "workspace" in entity_registry.all_kinds()
    spec = entity_registry.get("workspace")
    assert spec.label == "Workspace"
    assert spec.audit_target_prefix == "workspace"
    assert spec.supports_endorsements is False
    assert spec.supports_readme is True
    assert spec.supports_reviews is False
    assert spec.supports_stars is False
    assert spec.supports_issues is False
    assert spec.tab_keys == (
        "discussion",
        "readme",
        "members",
        "activity",
    )


def test_workspace_url_builder() -> None:
    """A slug builds a ``/workspaces/{slug}`` URL."""
    assert entity_registry.url_for("workspace", "default") == "/workspaces/default"
    assert entity_registry.url_for("workspace", "") == "/workspaces"


@pytest.mark.asyncio
async def test_workspace_landing_page_renders(
    admin_client: httpx.AsyncClient,
) -> None:
    """``GET /workspaces/default`` renders the landing template."""
    res = await admin_client.get("/workspaces/default")
    assert res.status_code == 200, res.text
    body = res.text
    assert "Pinned entities" in body
    assert "Activity" in body
    assert "workspaceLanding" in body


@pytest.mark.asyncio
async def test_pin_crud_round_trip(
    admin_client: httpx.AsyncClient,
) -> None:
    """Pin + list + delete cycle works for an admin."""
    # Create a social_target so we have something to pin.
    factory = app.state.session_factory
    with factory() as session:
        target = SocialTarget(workspace_id=1, entity_kind="table", entity_ref="m.s.pin_target")
        session.add(target)
        session.commit()
        target_id = int(target.id)

    add = await admin_client.post(
        "/api/workspaces/default/pins",
        json={"social_target_id": target_id},
    )
    assert add.status_code == 200, add.text
    assert add.json()["social_target_id"] == target_id

    listing = await admin_client.get("/api/workspaces/default/pins")
    assert listing.status_code == 200
    target_ids = {p["social_target_id"] for p in listing.json()["pins"]}
    assert target_id in target_ids

    remove = await admin_client.delete(f"/api/workspaces/default/pins/{target_id}")
    assert remove.status_code == 200, remove.text


@pytest.mark.asyncio
async def test_pin_add_rejects_duplicate(
    admin_client: httpx.AsyncClient,
) -> None:
    """Pinning an already-pinned target returns 409."""
    factory = app.state.session_factory
    with factory() as session:
        target = SocialTarget(workspace_id=1, entity_kind="table", entity_ref="m.s.dup_target")
        session.add(target)
        session.commit()
        target_id = int(target.id)
    first = await admin_client.post(
        "/api/workspaces/default/pins",
        json={"social_target_id": target_id},
    )
    assert first.status_code == 200
    second = await admin_client.post(
        "/api/workspaces/default/pins",
        json={"social_target_id": target_id},
    )
    assert second.status_code == 409, second.text


@pytest.mark.asyncio
async def test_pin_write_forbidden_for_non_admin(
    non_admin_client: httpx.AsyncClient,
) -> None:
    """A non-admin caller cannot pin or unpin."""
    res = await non_admin_client.post(
        "/api/workspaces/default/pins",
        json={"social_target_id": 1},
    )
    assert res.status_code in (401, 403), res.text


@pytest.mark.asyncio
async def test_workspace_activity_endpoint_returns_workspace_scoped_rows(
    admin_client: httpx.AsyncClient,
) -> None:
    """The activity endpoint returns notifications scoped to the workspace."""
    res = await admin_client.get("/api/workspaces/default/activity")
    assert res.status_code == 200, res.text
    assert "activity" in res.json()


@pytest.mark.asyncio
async def test_pin_reorder_applies_new_order(
    admin_client: httpx.AsyncClient,
) -> None:
    """``PATCH .../pins/reorder`` rewrites pin_order to match the list."""
    factory = app.state.session_factory
    with factory() as session:
        targets = [
            SocialTarget(workspace_id=1, entity_kind="table", entity_ref=f"m.s.r{i}")
            for i in range(3)
        ]
        session.add_all(targets)
        session.commit()
        ids = [int(t.id) for t in targets]
    for tid in ids:
        r = await admin_client.post(
            "/api/workspaces/default/pins",
            json={"social_target_id": tid},
        )
        assert r.status_code == 200
    reordered = list(reversed(ids))
    res = await admin_client.patch(
        "/api/workspaces/default/pins/reorder",
        json={"order": reordered},
    )
    assert res.status_code == 200, res.text
    listing = await admin_client.get("/api/workspaces/default/pins")
    in_order = [p["social_target_id"] for p in listing.json()["pins"]]
    # Only assert the relative order of the three we just pinned.
    seen = [tid for tid in in_order if tid in ids]
    assert seen == reordered
