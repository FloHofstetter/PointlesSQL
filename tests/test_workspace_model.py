"""ORM-level tests for the Sprint 28.0 workspace primitives.

Exercises only the model + service surface — middleware integration
is covered by ``test_workspace_resolver.py`` and the api-key column
plumbing by ``test_api_keys_workspace.py``.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from pointlessql.api.main import app
from pointlessql.models import (
    User,
    Workspace,
    WorkspaceCatalogPin,
    WorkspaceMember,
)
from pointlessql.services.workspace import _crud as workspaces_service


def _factory():
    return app.state.session_factory


def test_default_workspace_seeded_at_id_one() -> None:
    """The conftest seed mirrors the migration: id=1, slug='default'."""
    with _factory()() as session:
        row = session.get(Workspace, 1)
        assert row is not None
        assert row.slug == "default"
        assert row.archived_at is None


def test_create_workspace_validates_slug_shape() -> None:
    factory = _factory()
    with pytest.raises(ValueError):
        workspaces_service.create_workspace(factory, slug="Has Spaces", name="x")
    with pytest.raises(ValueError):
        workspaces_service.create_workspace(factory, slug="", name="x")
    with pytest.raises(ValueError):
        workspaces_service.create_workspace(factory, slug="-leading-dash", name="x")
    with pytest.raises(ValueError):
        workspaces_service.create_workspace(factory, slug="ok-slug", name="")


def test_create_workspace_rejects_duplicate_slug() -> None:
    factory = _factory()
    workspaces_service.create_workspace(factory, slug="dup", name="One")
    with pytest.raises(ValueError):
        workspaces_service.create_workspace(factory, slug="dup", name="Two")


def test_create_workspace_with_creator_adds_admin_membership() -> None:
    factory = _factory()
    with factory() as session:
        creator = session.query(User).filter(User.email == "test@test.com").one()
        creator_id = creator.id

    ws = workspaces_service.create_workspace(
        factory, slug="research", name="Research", creator_user_id=creator_id
    )

    role = workspaces_service.get_membership_role(factory, workspace_id=ws.id, user_id=creator_id)
    assert role == "admin"


def test_add_member_updates_role_in_place() -> None:
    factory = _factory()
    with factory() as session:
        user = session.query(User).filter(User.email == "nonadmin@test.com").one()
        user_id = user.id
    ws = workspaces_service.create_workspace(factory, slug="role-flip", name="x")
    workspaces_service.add_member(factory, workspace_id=ws.id, user_id=user_id, role="member")
    workspaces_service.add_member(factory, workspace_id=ws.id, user_id=user_id, role="admin")
    assert (
        workspaces_service.get_membership_role(factory, workspace_id=ws.id, user_id=user_id)
        == "admin"
    )


def test_add_member_rejects_unknown_role() -> None:
    with pytest.raises(ValueError):
        workspaces_service.add_member(_factory(), workspace_id=1, user_id=1, role="root")


def test_workspace_member_unique_constraint_rejects_dupes() -> None:
    """Direct ORM insert of a duplicate (workspace_id, user_id) pair fails."""
    factory = _factory()
    with factory() as session:
        user = session.query(User).filter(User.email == "test@test.com").one()
        session.add(
            WorkspaceMember(
                workspace_id=1,
                user_id=user.id,
                role="member",
                created_at=dt.datetime.now(dt.UTC),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_list_workspaces_for_user_filters_archived() -> None:
    factory = _factory()
    with factory() as session:
        user = session.query(User).filter(User.email == "test@test.com").one()
        user_id = user.id
    active = workspaces_service.create_workspace(
        factory, slug="active-ws", name="Active", creator_user_id=user_id
    )
    archived = workspaces_service.create_workspace(
        factory, slug="archived-ws", name="Archived", creator_user_id=user_id
    )
    with factory() as session:
        row = session.get(Workspace, archived.id)
        assert row is not None
        row.archived_at = dt.datetime.now(dt.UTC)
        session.commit()

    visible = workspaces_service.list_workspaces_for_user(factory, user_id=user_id)
    visible_ids = {w.id for w in visible}
    assert active.id in visible_ids
    assert archived.id not in visible_ids
    assert 1 in visible_ids  # default workspace from conftest seed

    all_including = workspaces_service.list_workspaces_for_user(
        factory, user_id=user_id, include_archived=True
    )
    all_ids = {w.id for w in all_including}
    assert archived.id in all_ids


def test_workspace_catalog_pin_unique_constraint() -> None:
    """Two pins on the same (workspace, catalog) tuple are rejected."""
    factory = _factory()
    now = dt.datetime.now(dt.UTC)
    with factory() as session:
        session.add(
            WorkspaceCatalogPin(
                workspace_id=1,
                catalog_name="silver",
                mode="primary",
                created_at=now,
            )
        )
        session.commit()
    with factory() as session:
        session.add(
            WorkspaceCatalogPin(
                workspace_id=1,
                catalog_name="silver",
                mode="pinned",
                created_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_get_workspace_by_slug_is_case_insensitive() -> None:
    assert workspaces_service.get_workspace_by_slug(_factory(), slug="DEFAULT").slug == "default"


def test_is_member_returns_false_for_non_member() -> None:
    factory = _factory()
    ws = workspaces_service.create_workspace(factory, slug="empty-ws", name="x")
    with factory() as session:
        user = session.query(User).filter(User.email == "nonadmin@test.com").one()
        user_id = user.id
    assert not workspaces_service.is_member(factory, workspace_id=ws.id, user_id=user_id)
    workspaces_service.add_member(factory, workspace_id=ws.id, user_id=user_id, role="member")
    assert workspaces_service.is_member(factory, workspace_id=ws.id, user_id=user_id)


def test_users_default_workspace_id_backfilled_by_conftest() -> None:
    """The conftest helper sets default_workspace_id for both fixture users."""
    with _factory()() as session:
        rows = session.execute(
            select(User.email, User.default_workspace_id).order_by(User.id)
        ).all()
        assert all(r.default_workspace_id == 1 for r in rows)
