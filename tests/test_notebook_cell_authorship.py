"""Tests — per-cell authorship attribution."""

from __future__ import annotations

import datetime
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.api.main import app
from pointlessql.exceptions import ValidationError
from pointlessql.models import Agent, Base, Notebook
from pointlessql.models.notebook import NotebookCellIdentity
from pointlessql.services.notebook import cell_authorship as cell_authorship_service


@pytest.fixture
def factory() -> sessionmaker:  # type: ignore[type-arg]
    """In-memory SQLite session factory with full schema applied."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _seed_cell(factory: sessionmaker) -> str:  # type: ignore[type-arg]
    """Insert one ``notebook_cells`` row + ancestor ``notebooks`` row."""
    nb_id = str(uuid.uuid4())
    cell_uuid = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    with factory() as s:
        s.add(Notebook(id=nb_id, workspace_id=1, file_path="n.py"))
        s.flush()
        s.add(
            NotebookCellIdentity(
                id=cell_uuid,
                workspace_id=1,
                notebook_id=nb_id,
                current_content_hash="abc",
                ordinal_hint=0,
                created_at=now,
            )
        )
        s.commit()
    return cell_uuid


def _seed_user(factory: sessionmaker) -> int:  # type: ignore[type-arg]
    """Insert one ``users`` row and return its int id."""
    from pointlessql.models import User

    now = datetime.datetime.now(datetime.UTC)
    with factory() as s:
        u = User(
            email=f"u-{uuid.uuid4().hex[:8]}@test",
            display_name="Test User",
            password_hash="x",
            is_admin=False,
            created_at=now,
        )
        s.add(u)
        s.commit()
        return u.id


def _seed_agent(factory: sessionmaker, *, slug: str | None = None) -> int:  # type: ignore[type-arg]
    """Insert one ``agents`` row and return its int id."""
    user_id = _seed_user(factory)
    now = datetime.datetime.now(datetime.UTC)
    with factory() as s:
        a = Agent(
            workspace_id=1,
            slug=slug or f"bot-{uuid.uuid4().hex[:8]}",
            display_name="Test Bot",
            avatar_kind="custom",
            principal_user_id=user_id,
            created_at=now,
            created_by_user_id=user_id,
        )
        s.add(a)
        s.commit()
        return a.id


# -- service: upsert ----------------------------------------------------------


def test_upsert_user_first_save_mints_row(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """A first user save creates the row with both first_* and last_*."""
    cell_uuid = _seed_cell(factory)
    with factory() as session:
        row = cell_authorship_service.upsert_cell_authorship(
            session,
            cell_uuid=cell_uuid,
            kind="user",
            email="user@test",
        )
        assert row.first_author_kind == "user"
        assert row.first_author_email == "user@test"
        assert row.last_modifier_email == "user@test"
        session.commit()


def test_upsert_second_save_preserves_first_author(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Second save updates last_modifier_* but keeps first_*."""
    cell_uuid = _seed_cell(factory)
    with factory() as session:
        cell_authorship_service.upsert_cell_authorship(
            session,
            cell_uuid=cell_uuid,
            kind="user",
            email="first@test",
        )
        session.commit()
        row = cell_authorship_service.upsert_cell_authorship(
            session,
            cell_uuid=cell_uuid,
            kind="user",
            email="second@test",
        )
        assert row.first_author_email == "first@test"
        assert row.last_modifier_email == "second@test"
        session.commit()


def test_upsert_agent_kind_records_agent_id(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Agent-kind saves persist agent_id + agent_run_id."""
    cell_uuid = _seed_cell(factory)
    agent_id = _seed_agent(factory)
    with factory() as session:
        row = cell_authorship_service.upsert_cell_authorship(
            session,
            cell_uuid=cell_uuid,
            kind="agent",
            agent_id=agent_id,
            agent_run_id="run-1",
        )
        assert row.first_author_kind == "agent"
        assert row.first_author_agent_id == agent_id
        assert row.first_author_agent_run_id == "run-1"
        session.commit()


def test_upsert_user_kind_missing_email_raises(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """``kind='user'`` without ``email`` raises."""
    cell_uuid = _seed_cell(factory)
    with factory() as session:
        with pytest.raises(ValidationError):
            cell_authorship_service.upsert_cell_authorship(
                session, cell_uuid=cell_uuid, kind="user"
            )


def test_upsert_agent_kind_missing_both_identifiers_raises(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """``kind='agent'`` with neither ``agent_id`` nor ``agent_run_id`` raises."""
    cell_uuid = _seed_cell(factory)
    with factory() as session:
        with pytest.raises(ValidationError):
            cell_authorship_service.upsert_cell_authorship(
                session, cell_uuid=cell_uuid, kind="agent"
            )


def test_upsert_agent_kind_accepts_run_id_only(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """``kind='agent'`` with only ``agent_run_id`` is allowed.

    inline editor chat has no
    registered ``Agent`` DB row, so the AI-acceptance authorship
    hook can only supply ``agent_run_id``.  Service accepts the
    weaker attribution and the chip falls back to a generic
    "AI assistant" label client-side.
    """
    cell_uuid = _seed_cell(factory)
    with factory() as session:
        row = cell_authorship_service.upsert_cell_authorship(
            session,
            cell_uuid=cell_uuid,
            kind="agent",
            agent_run_id="run-abc",
        )
        assert row.first_author_kind == "agent"
        assert row.first_author_agent_id is None
        assert row.first_author_agent_run_id == "run-abc"
        session.commit()


def test_upsert_unknown_cell_raises(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """Unknown cell_uuid surfaces as ValidationError."""
    with factory() as session:
        with pytest.raises(ValidationError):
            cell_authorship_service.upsert_cell_authorship(
                session,
                cell_uuid=str(uuid.uuid4()),
                kind="user",
                email="x@test",
            )


def test_upsert_unknown_kind_raises(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """Bogus ``kind`` raises before touching the DB."""
    cell_uuid = _seed_cell(factory)
    with factory() as session:
        with pytest.raises(ValidationError):
            cell_authorship_service.upsert_cell_authorship(
                session,
                cell_uuid=cell_uuid,
                kind="invalid",  # type: ignore[arg-type]
                email="x@test",
            )


# -- service: get + list ------------------------------------------------------


def test_get_attribution_returns_envelope(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """``get_attribution`` parses the row into the REST envelope."""
    cell_uuid = _seed_cell(factory)
    with factory() as session:
        cell_authorship_service.upsert_cell_authorship(
            session,
            cell_uuid=cell_uuid,
            kind="user",
            email="user@test",
        )
        session.commit()
        envelope = cell_authorship_service.get_attribution(session, cell_uuid=cell_uuid)
        assert envelope is not None
        assert envelope["first_author"]["kind"] == "user"
        assert envelope["first_author"]["email"] == "user@test"


def test_get_attribution_unknown_cell_returns_none(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Missing row → ``None``, not exception."""
    with factory() as session:
        out = cell_authorship_service.get_attribution(session, cell_uuid=str(uuid.uuid4()))
        assert out is None


def test_list_authored_by_agent(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """Returns cells whose first_author_agent_id matches."""
    cell_uuid = _seed_cell(factory)
    agent_id = _seed_agent(factory)
    with factory() as session:
        cell_authorship_service.upsert_cell_authorship(
            session,
            cell_uuid=cell_uuid,
            kind="agent",
            agent_id=agent_id,
            agent_run_id="r1",
        )
        session.commit()
        cells = cell_authorship_service.list_authored_by_agent(session, agent_id=agent_id)
        assert len(cells) == 1
        assert cells[0]["cell_uuid"] == cell_uuid
        assert cells[0]["agent_run_id"] == "r1"


# -- REST ---------------------------------------------------------------------


async def test_api_attribution_unknown_returns_422(
    admin_client: httpx.AsyncClient,
) -> None:
    """Unknown cell UUID surfaces as 422 via ValidationError."""
    fake = "00000000-0000-0000-0000-000000000000"
    resp = await admin_client.get(
        "/api/notebooks/cell/attribution",
        params={"cell_uuid": fake},
    )
    assert resp.status_code == 422


async def test_api_attribution_requires_auth(
    anonymous_client: httpx.AsyncClient,
) -> None:
    """Anonymous callers hit the auth gate."""
    fake = "00000000-0000-0000-0000-000000000000"
    resp = await anonymous_client.get(
        "/api/notebooks/cell/attribution",
        params={"cell_uuid": fake},
    )
    assert resp.status_code in (401, 403)


async def test_api_agent_authored_cells_empty(
    admin_client: httpx.AsyncClient,
) -> None:
    """Agent with no authored cells returns an empty list."""
    resp = await admin_client.get("/api/agents/9999/authored-cells")
    assert resp.status_code == 200
    body: dict[str, Any] = resp.json()
    assert body["agent_id"] == 9999
    assert body["cells"] == []


# -- service + REST: bulk attribution ---------------------


def test_list_for_notebook_returns_mapping(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """One JOIN query returns every authorship row for a notebook."""
    nb_id = str(uuid.uuid4())
    cell_a = str(uuid.uuid4())
    cell_b = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    with factory() as s:
        s.add(Notebook(id=nb_id, workspace_id=1, file_path="bulk.py"))
        s.flush()
        for cell_uuid in (cell_a, cell_b):
            s.add(
                NotebookCellIdentity(
                    id=cell_uuid,
                    workspace_id=1,
                    notebook_id=nb_id,
                    current_content_hash="h",
                    ordinal_hint=0,
                    created_at=now,
                )
            )
        s.commit()
    with factory() as session:
        cell_authorship_service.upsert_cell_authorship(
            session, cell_uuid=cell_a, kind="user", email="a@test"
        )
        cell_authorship_service.upsert_cell_authorship(
            session, cell_uuid=cell_b, kind="user", email="b@test"
        )
        session.commit()
        out = cell_authorship_service.list_for_notebook(session, notebook_id=nb_id)
    assert set(out.keys()) == {cell_a, cell_b}
    assert out[cell_a]["first_author"]["email"] == "a@test"
    assert out[cell_b]["first_author"]["email"] == "b@test"


@pytest.fixture
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``settings.jupyter.notebooks_dir`` at an isolated tmp dir."""
    root = tmp_path / "notebooks"
    root.mkdir()
    monkeypatch.setattr(app.state.settings.jupyter, "notebooks_dir", root)
    return root


async def test_api_notebook_attribution_bulk(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """GET /api/notebooks/attribution/bulk returns ``{cell_uuid: envelope}``."""
    nb_path = workspace_dir / "bulk.py"
    nb_path.write_text("# %%\nprint(1)\n")
    resp = await admin_client.get("/api/notebooks/attribution/bulk", params={"path": "bulk.py"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["path"] == "bulk.py"
    assert isinstance(body["notebook_id"], str)
    assert isinstance(body["attributions"], dict)
