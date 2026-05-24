"""Tests — revision history + diff."""

from __future__ import annotations

import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.api.main import app
from pointlessql.exceptions import ValidationError
from pointlessql.models import Base, Notebook
from pointlessql.services.notebook import revisions as notebook_revisions_service


@pytest.fixture
def factory() -> sessionmaker:  # type: ignore[type-arg]
    """Build an in-memory SQLite session factory with the schema applied."""
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


# -- canonical hashing -------------------------------------------------------


def test_canonical_payload_is_byte_stable_across_dict_orderings() -> None:
    """Permuting input dict keys still yields the same SHA-256."""
    a_cells = [{"content_hash": "h1", "cell_type": "code", "source": "x = 1"}]
    a_outputs = [
        {
            "content_hash": "h1",
            "kernel_session_id": "s1",
            "output_index": 0,
            "msg_type": "stream",
            "content": {"text": "ok"},
            "metadata": None,
        }
    ]
    b_cells = [{"source": "x = 1", "content_hash": "h1", "cell_type": "code"}]
    b_outputs = [
        {
            "msg_type": "stream",
            "kernel_session_id": "s1",
            "output_index": 0,
            "content": {"text": "ok"},
            "content_hash": "h1",
            "metadata": None,
        }
    ]
    _, _, sha_a = notebook_revisions_service.canonical_payload(cells=a_cells, outputs=a_outputs)
    _, _, sha_b = notebook_revisions_service.canonical_payload(cells=b_cells, outputs=b_outputs)
    assert sha_a == sha_b


def test_canonical_payload_changes_when_source_changes() -> None:
    """Hash shifts when the underlying source text changes."""
    _, _, sha_a = notebook_revisions_service.canonical_payload(
        cells=[{"content_hash": "h1", "cell_type": "code", "source": "x = 1"}],
        outputs=[],
    )
    _, _, sha_b = notebook_revisions_service.canonical_payload(
        cells=[{"content_hash": "h1", "cell_type": "code", "source": "x = 2"}],
        outputs=[],
    )
    assert sha_a != sha_b


# -- create + idempotency -----------------------------------------------------


def test_create_revision_inserts_new_row(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """First snapshot writes a row with the canonical sha."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        row = notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[{"content_hash": "h1", "cell_type": "code", "source": "x"}],
            outputs=[],
            created_by="user@test",
            message="initial",
        )
        assert row.notebook_id == nb_id
        assert row.message == "initial"
        assert row.parent_revision_id is None
        assert len(row.content_sha256) == 64
        session.commit()


def test_create_revision_idempotent_on_identical_content(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """A second save with identical content returns the existing row."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        first = notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[{"content_hash": "h1", "cell_type": "code", "source": "x"}],
            outputs=[],
            created_by="user@test",
        )
        second = notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[{"content_hash": "h1", "cell_type": "code", "source": "x"}],
            outputs=[],
            created_by="user@test",
        )
        assert first.revision_uuid == second.revision_uuid
        session.commit()


def test_create_revision_unknown_notebook_raises(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Bad ``notebook_id`` surfaces as a ValidationError."""
    with factory() as session:
        with pytest.raises(ValidationError):
            notebook_revisions_service.create_revision(
                session,
                notebook_id="00000000-0000-0000-0000-000000000000",
                cells=[],
                outputs=[],
                created_by=None,
            )


def test_create_revision_sets_parent_to_previous(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Sequential saves chain via ``parent_revision_id``."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        first = notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[{"content_hash": "h1", "cell_type": "code", "source": "a"}],
            outputs=[],
            created_by="u",
        )
        first_id = first.id
        session.commit()
        second = notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[{"content_hash": "h2", "cell_type": "code", "source": "b"}],
            outputs=[],
            created_by="u",
        )
        assert second.parent_revision_id == first_id
        session.commit()


# -- list + get ---------------------------------------------------------------


def test_list_revisions_newest_first(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """List returns latest first."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[{"content_hash": "h1", "cell_type": "code", "source": "a"}],
            outputs=[],
            created_by="u",
        )
        session.commit()
        notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[{"content_hash": "h2", "cell_type": "code", "source": "b"}],
            outputs=[],
            created_by="u",
        )
        session.commit()
    with factory() as session:
        rows = notebook_revisions_service.list_revisions(session, notebook_id=nb_id)
    assert len(rows) == 2
    # newest first → second-created comes back at index 0
    assert rows[0]["created_at"] >= rows[1]["created_at"]


def test_get_revision_includes_full_payload(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """``get_revision`` returns parsed cells + outputs lists."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        row = notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[{"content_hash": "h1", "cell_type": "code", "source": "a"}],
            outputs=[],
            created_by="u",
        )
        rev_uuid = row.revision_uuid
        session.commit()
        envelope = notebook_revisions_service.get_revision(session, revision_uuid=rev_uuid)
        assert envelope is not None
        assert envelope["cells"][0]["content_hash"] == "h1"
        assert envelope["outputs"] == []


# -- diff ---------------------------------------------------------------------


def test_compute_diff_added_cell(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """A new cell in ``right`` lands in ``added``."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        left = notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[{"content_hash": "h1", "cell_type": "code", "source": "a"}],
            outputs=[],
            created_by="u",
        )
        session.commit()
        right = notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[
                {"content_hash": "h1", "cell_type": "code", "source": "a"},
                {"content_hash": "h2", "cell_type": "code", "source": "b"},
            ],
            outputs=[],
            created_by="u",
        )
        left_uuid = left.revision_uuid
        right_uuid = right.revision_uuid
        session.commit()
        diff = notebook_revisions_service.compute_diff(
            session,
            left_uuid=left_uuid,
            right_uuid=right_uuid,
        )
        assert len(diff["added"]) == 1
        assert diff["added"][0]["cell"]["content_hash"] == "h2"
        assert diff["removed"] == []


def test_compute_diff_moved_cell(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """A reordered cell lands in ``moved`` (not ``added`` or ``removed``)."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        left = notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[
                {"content_hash": "h1", "cell_type": "code", "source": "a"},
                {"content_hash": "h2", "cell_type": "code", "source": "b"},
            ],
            outputs=[],
            created_by="u",
        )
        session.commit()
        right = notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[
                {"content_hash": "h2", "cell_type": "code", "source": "b"},
                {"content_hash": "h1", "cell_type": "code", "source": "a"},
            ],
            outputs=[],
            created_by="u",
        )
        left_uuid = left.revision_uuid
        right_uuid = right.revision_uuid
        session.commit()
        diff = notebook_revisions_service.compute_diff(
            session,
            left_uuid=left_uuid,
            right_uuid=right_uuid,
        )
        assert len(diff["moved"]) == 2
        assert diff["added"] == [] and diff["removed"] == []


def test_compute_diff_unknown_uuid_raises(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Unknown UUID surfaces as ValidationError."""
    with factory() as session:
        with pytest.raises(ValidationError):
            notebook_revisions_service.compute_diff(
                session,
                left_uuid="ghost1",
                right_uuid="ghost2",
            )


# -- REST surface -------------------------------------------------------------


@pytest.fixture
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``settings.jupyter.notebooks_dir`` at a tmp directory."""
    root = tmp_path / "notebooks"
    root.mkdir()
    monkeypatch.setattr(app.state.settings.jupyter, "notebooks_dir", root)
    return root


async def test_api_create_and_list_revisions(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """POST snapshots; GET returns newest first."""
    nb_path = workspace_dir / "report.py"
    nb_path.write_text("# %%\nprint(1)\n")
    create = await admin_client.post(
        "/api/notebooks/revisions",
        json={"path": "report.py", "message": "initial"},
    )
    assert create.status_code == 201
    rev_uuid = create.json()["revision_uuid"]
    assert create.json()["created"] is True

    # Idempotent re-snapshot
    again = await admin_client.post(
        "/api/notebooks/revisions",
        json={"path": "report.py", "message": "redo"},
    )
    assert again.json()["created"] is False
    assert again.json()["revision_uuid"] == rev_uuid

    listed = await admin_client.get("/api/notebooks/revisions", params={"path": "report.py"})
    assert listed.status_code == 200
    assert len(listed.json()["revisions"]) == 1


async def test_api_get_revision_returns_full_payload(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """GET /api/notebooks/revisions/{uuid} returns parsed cells."""
    (workspace_dir / "x.py").write_text("# %%\nprint(1)\n")
    create = await admin_client.post("/api/notebooks/revisions", json={"path": "x.py"})
    rev_uuid = create.json()["revision_uuid"]
    resp = await admin_client.get(f"/api/notebooks/revisions/{rev_uuid}")
    assert resp.status_code == 200
    assert isinstance(resp.json()["cells"], list)


async def test_api_diff_two_revisions(workspace_dir: Path, admin_client: httpx.AsyncClient) -> None:
    """GET /api/notebooks/revisions/diff returns the envelope."""
    nb_path = workspace_dir / "x.py"
    nb_path.write_text("# %%\nprint(1)\n")
    first = await admin_client.post("/api/notebooks/revisions", json={"path": "x.py"})
    nb_path.write_text("# %%\nprint(1)\n\n# %%\nprint(2)\n")
    second = await admin_client.post("/api/notebooks/revisions", json={"path": "x.py"})
    resp = await admin_client.get(
        "/api/notebooks/revisions/diff",
        params={
            "left": first.json()["revision_uuid"],
            "right": second.json()["revision_uuid"],
        },
    )
    assert resp.status_code == 200
    diff = resp.json()
    assert diff["left_uuid"] == first.json()["revision_uuid"]
    assert diff["right_uuid"] == second.json()["revision_uuid"]
    # The second snapshot added at least one cell.
    assert len(diff["added"]) + len(diff["changed"]) >= 1
