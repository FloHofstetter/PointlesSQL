"""Tests for Phase 99 — widget-cells + per-notebook permissions."""

from __future__ import annotations

import datetime
import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.api.main import app
from pointlessql.exceptions import ValidationError
from pointlessql.models import Base, Notebook, User
from pointlessql.services.notebook import permissions as notebook_perms_service
from pointlessql.services.notebook import widgets as notebook_widgets_service


@pytest.fixture
def factory() -> sessionmaker:  # type: ignore[type-arg]
    """In-memory SQLite session factory."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _seed_notebook(factory: sessionmaker) -> str:  # type: ignore[type-arg]
    """Insert one ``notebooks`` row and return its UUID."""
    nb_id = str(uuid.uuid4())
    with factory() as s:
        s.add(Notebook(id=nb_id, workspace_id=1, file_path="n.py"))
        s.commit()
    return nb_id


def _seed_user(factory: sessionmaker) -> int:  # type: ignore[type-arg]
    """Insert one ``users`` row and return its id."""
    with factory() as s:
        u = User(
            email=f"u-{uuid.uuid4().hex[:8]}@test",
            display_name="t",
            password_hash="x",
            is_admin=False,
            created_at=datetime.datetime.now(datetime.UTC),
        )
        s.add(u)
        s.commit()
        return u.id


# -- widgets: service --------------------------------------------------------


def test_upsert_dropdown_widget(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """Dropdown insert persists name + options."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        row = notebook_widgets_service.upsert_widget(
            session,
            notebook_id=nb_id,
            name="region",
            widget_kind="dropdown",
            label="Region",
            config={"options": [{"value": "us", "label": "US"}]},
            default_value="us",
        )
        assert row.name == "region"
        assert row.default_value is not None and "us" in row.default_value
        session.commit()


def test_upsert_slider_validates_range(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """Slider with ``min >= max`` raises."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        with pytest.raises(ValidationError):
            notebook_widgets_service.upsert_widget(
                session,
                notebook_id=nb_id,
                name="thr",
                widget_kind="slider",
                label="Thr",
                config={"min": 10, "max": 5},
            )


def test_upsert_rejects_unknown_kind(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """Unknown widget_kind raises before touching the DB."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        with pytest.raises(ValidationError):
            notebook_widgets_service.upsert_widget(
                session,
                notebook_id=nb_id,
                name="x",
                widget_kind="dial",
                label="x",
                config={},
            )


def test_upsert_rejects_bad_name(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """Widget names outside [A-Za-z_][A-Za-z0-9_]* raise."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        with pytest.raises(ValidationError):
            notebook_widgets_service.upsert_widget(
                session,
                notebook_id=nb_id,
                name="9bad",
                widget_kind="text",
                label="x",
                config={},
            )


def test_resolve_widget_values_falls_back_to_default(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Missing overrides → default; provided overrides win."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        notebook_widgets_service.upsert_widget(
            session,
            notebook_id=nb_id,
            name="region",
            widget_kind="dropdown",
            label="r",
            config={"options": [{"value": "us"}, {"value": "eu"}]},
            default_value="us",
        )
        session.commit()
        values = notebook_widgets_service.resolve_widget_values(
            session, notebook_id=nb_id
        )
        assert values["region"] == "us"
        values_override = notebook_widgets_service.resolve_widget_values(
            session, notebook_id=nb_id, overrides={"region": "eu"}
        )
        assert values_override["region"] == "eu"


def test_delete_widget_is_idempotent(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """Second delete of the same widget returns False."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        notebook_widgets_service.upsert_widget(
            session,
            notebook_id=nb_id,
            name="region",
            widget_kind="text",
            label="r",
            config={},
        )
        session.commit()
        assert (
            notebook_widgets_service.delete_widget(
                session, notebook_id=nb_id, name="region"
            )
            is True
        )
        assert (
            notebook_widgets_service.delete_widget(
                session, notebook_id=nb_id, name="region"
            )
            is False
        )


# -- permissions: service ----------------------------------------------------


def test_role_satisfies_lattice() -> None:
    """``edit`` satisfies ``run`` + ``view``; ``view`` does not satisfy ``run``."""
    assert notebook_perms_service.role_satisfies("edit", "view")
    assert notebook_perms_service.role_satisfies("edit", "run")
    assert notebook_perms_service.role_satisfies("run", "view")
    assert not notebook_perms_service.role_satisfies("view", "run")
    assert not notebook_perms_service.role_satisfies(None, "view")


def test_actor_has_role_admin_bypasses(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """Admins pass every required role even without an explicit grant."""
    nb_id = _seed_notebook(factory)
    user_id = _seed_user(factory)
    with factory() as session:
        for needed in ("view", "run", "edit"):
            assert notebook_perms_service.actor_has_role(
                session,
                notebook_id=nb_id,
                user_id=user_id,
                is_admin=True,
                required=needed,
            )


def test_actor_has_role_workspace_default_grants_run(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """No grant → workspace-default lets view+run through but not edit."""
    nb_id = _seed_notebook(factory)
    user_id = _seed_user(factory)
    with factory() as session:
        assert notebook_perms_service.actor_has_role(
            session,
            notebook_id=nb_id,
            user_id=user_id,
            is_admin=False,
            required="view",
        )
        assert notebook_perms_service.actor_has_role(
            session,
            notebook_id=nb_id,
            user_id=user_id,
            is_admin=False,
            required="run",
        )
        assert not notebook_perms_service.actor_has_role(
            session,
            notebook_id=nb_id,
            user_id=user_id,
            is_admin=False,
            required="edit",
        )


def test_actor_has_role_explicit_view_blocks_run(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Explicit ``view`` grant narrows below workspace-default ``run``."""
    nb_id = _seed_notebook(factory)
    user_id = _seed_user(factory)
    with factory() as session:
        notebook_perms_service.grant_permission(
            session,
            notebook_id=nb_id,
            user_id=user_id,
            role="view",
            granted_by_user_id=None,
        )
        session.commit()
        assert notebook_perms_service.actor_has_role(
            session,
            notebook_id=nb_id,
            user_id=user_id,
            is_admin=False,
            required="view",
        )
        assert not notebook_perms_service.actor_has_role(
            session,
            notebook_id=nb_id,
            user_id=user_id,
            is_admin=False,
            required="run",
        )
        assert not notebook_perms_service.actor_has_role(
            session,
            notebook_id=nb_id,
            user_id=user_id,
            is_admin=False,
            required="edit",
        )


def test_grant_and_revoke_permission(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """Grant inserts; revoke deletes; revoke-missing returns False."""
    nb_id = _seed_notebook(factory)
    user_id = _seed_user(factory)
    with factory() as session:
        notebook_perms_service.grant_permission(
            session,
            notebook_id=nb_id,
            user_id=user_id,
            role="view",
            granted_by_user_id=None,
        )
        session.commit()
        assert (
            notebook_perms_service.get_effective_role(
                session, notebook_id=nb_id, user_id=user_id
            )
            == "view"
        )
        notebook_perms_service.grant_permission(
            session,
            notebook_id=nb_id,
            user_id=user_id,
            role="edit",
            granted_by_user_id=None,
        )
        session.commit()
        assert (
            notebook_perms_service.get_effective_role(
                session, notebook_id=nb_id, user_id=user_id
            )
            == "edit"
        )
        assert (
            notebook_perms_service.revoke_permission(
                session, notebook_id=nb_id, user_id=user_id
            )
            is True
        )
        session.commit()
        assert (
            notebook_perms_service.revoke_permission(
                session, notebook_id=nb_id, user_id=user_id
            )
            is False
        )


def test_grant_rejects_bad_role(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """Unknown role raises."""
    nb_id = _seed_notebook(factory)
    user_id = _seed_user(factory)
    with factory() as session:
        with pytest.raises(ValidationError):
            notebook_perms_service.grant_permission(
                session,
                notebook_id=nb_id,
                user_id=user_id,
                role="superuser",
                granted_by_user_id=None,
            )


# -- REST --------------------------------------------------------------------


@pytest.fixture
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``settings.jupyter.notebooks_dir`` at a tmp directory."""
    root = tmp_path / "notebooks"
    root.mkdir()
    monkeypatch.setattr(app.state.settings.jupyter, "notebooks_dir", root)
    return root


async def test_api_widget_crud_roundtrip(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Create notebook → upsert widget → list → resolve → delete."""
    await admin_client.post("/api/notebooks/create", json={"path": "n.py"})

    upsert = await admin_client.put(
        "/api/notebooks/widgets",
        json={
            "path": "n.py",
            "name": "region",
            "widget_kind": "dropdown",
            "label": "Region",
            "config": {"options": [{"value": "us"}, {"value": "eu"}]},
            "default_value": "us",
        },
    )
    assert upsert.status_code == 200
    assert upsert.json()["name"] == "region"

    listed = await admin_client.get(
        "/api/notebooks/widgets", params={"path": "n.py"}
    )
    assert len(listed.json()["widgets"]) == 1

    resolved = await admin_client.post(
        "/api/notebooks/widgets/resolve",
        json={"path": "n.py", "overrides": {"region": "eu"}},
    )
    assert resolved.json()["values"]["region"] == "eu"

    deleted = await admin_client.delete(
        "/api/notebooks/widgets",
        params={"path": "n.py", "name": "region"},
    )
    assert deleted.json()["removed"] is True


async def test_api_widget_rejects_bad_kind(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Unknown widget_kind → 422."""
    await admin_client.post("/api/notebooks/create", json={"path": "n.py"})
    resp = await admin_client.put(
        "/api/notebooks/widgets",
        json={
            "path": "n.py",
            "name": "x",
            "widget_kind": "dial",
            "label": "x",
            "config": {},
        },
    )
    assert resp.status_code == 422


async def test_api_permission_crud(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Permissions list / grant / revoke round-trip."""
    await admin_client.post("/api/notebooks/create", json={"path": "p.py"})
    listed = await admin_client.get(
        "/api/notebooks/permissions", params={"path": "p.py"}
    )
    assert listed.status_code == 200
    assert listed.json()["permissions"] == []
    assert "view" in listed.json()["roles"]

    granted = await admin_client.put(
        "/api/notebooks/permissions",
        json={"path": "p.py", "user_id": 999, "role": "run"},
    )
    assert granted.status_code == 200

    after = await admin_client.get(
        "/api/notebooks/permissions", params={"path": "p.py"}
    )
    roles = {r["role"] for r in after.json()["permissions"]}
    assert "run" in roles

    revoked = await admin_client.delete(
        "/api/notebooks/permissions",
        params={"path": "p.py", "user_id": 999},
    )
    assert revoked.json()["removed"] is True
