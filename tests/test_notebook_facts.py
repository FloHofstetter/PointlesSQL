"""Tests Rest — pin-to-memory notebook revision facts."""

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
from pointlessql.models import (
    Base,
    Notebook,
)
from pointlessql.models.social._social_target import SocialTarget
from pointlessql.pql import facts as facts_facade
from pointlessql.services.notebook import facts as facts_service
from pointlessql.services.notebook import revisions as revisions_service


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


def _seed_notebook_and_revision(
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    workspace_id: int = 1,
) -> tuple[str, str, int]:
    """Insert one notebook + one revision and return ``(nb_id, rev_uuid, rev_id)``."""
    nb_id = str(uuid.uuid4())
    with factory() as s:
        s.add(Notebook(id=nb_id, workspace_id=workspace_id, file_path="n.py"))
        rev = revisions_service.create_revision(
            s,
            notebook_id=nb_id,
            cells=[{"content_hash": "h1", "cell_type": "code", "source": "x"}],
            outputs=[],
            created_by="u@test",
        )
        s.commit()
        return nb_id, rev.revision_uuid, rev.id


# -- pin_revision_fact --------------------------------------------------------


def test_pin_creates_active_row_with_uuid(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """A whole-revision pin mints a UUID and a social target."""
    _, rev_uuid, _ = _seed_notebook_and_revision(factory)
    with factory() as session:
        row = facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rev_uuid,
            title="Q3 spike",
            pinned_by_user_id=42,
        )
        session.commit()
        assert len(row.fact_uuid) == 36
        assert row.unpinned_at is None
        assert row.cell_content_hash is None
        target = session.get(SocialTarget, row.social_target_id)
        assert target is not None
        assert target.entity_kind == "notebook_revision"
        assert target.entity_ref == rev_uuid


def test_pin_is_idempotent_on_same_revision_and_cell(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Re-pinning the same target returns the existing row."""
    _, rev_uuid, _ = _seed_notebook_and_revision(factory)
    with factory() as session:
        first = facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rev_uuid,
            title="One",
            pinned_by_user_id=1,
        )
        second = facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rev_uuid,
            title="ignored on re-pin",
            pinned_by_user_id=1,
        )
        assert first.id == second.id
        assert second.title == "One"  # original title sticks


def test_cell_output_pin_uses_distinct_social_kind(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """A cell-output pin gets kind='notebook_cell_output' on the anchor."""
    _, rev_uuid, _ = _seed_notebook_and_revision(factory)
    with factory() as session:
        row = facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rev_uuid,
            title="Cell-output fact",
            cell_content_hash="h1",
            pinned_by_user_id=2,
        )
        session.commit()
        target = session.get(SocialTarget, row.social_target_id)
        assert target is not None
        assert target.entity_kind == "notebook_cell_output"
        assert target.entity_ref == f"{rev_uuid}:h1"


def test_pin_rejects_cross_workspace_revision(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Pinning a revision from workspace A into B raises."""
    _, rev_uuid, _ = _seed_notebook_and_revision(factory, workspace_id=1)
    with factory() as session, pytest.raises(ValidationError):
        facts_service.pin_revision_fact(
            session,
            workspace_id=2,
            revision_uuid=rev_uuid,
            title="x",
            pinned_by_user_id=1,
        )


def test_pin_requires_attribution(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """At least one of (user_id, agent_id) must be set."""
    _, rev_uuid, _ = _seed_notebook_and_revision(factory)
    with factory() as session, pytest.raises(ValidationError):
        facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rev_uuid,
            title="x",
            pinned_by_user_id=None,
            pinned_by_agent_id=None,
        )


def test_pin_rejects_unknown_revision(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """An unknown revision UUID surfaces a ValidationError."""
    with factory() as session, pytest.raises(ValidationError):
        facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid="00000000-0000-0000-0000-000000000000",
            title="x",
            pinned_by_user_id=1,
        )


# -- unpin --------------------------------------------------------------------


def test_unpin_marks_row_inactive(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """``unpin_fact`` stamps ``unpinned_at`` without deleting the row."""
    _, rev_uuid, _ = _seed_notebook_and_revision(factory)
    with factory() as session:
        row = facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rev_uuid,
            title="x",
            pinned_by_user_id=1,
        )
        session.commit()
        fact_uuid = row.fact_uuid
        updated = facts_service.unpin_fact(session, fact_uuid=fact_uuid)
        session.commit()
        assert updated.unpinned_at is not None
        # Still in DB
        again = facts_service.get_fact(session, fact_uuid=fact_uuid)
        assert again is not None
        assert again.unpinned_at is not None


def test_repin_after_unpin_mints_fresh_row(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Partial UNIQUE on ``unpinned_at IS NULL`` lets a re-pin add a new row."""
    _, rev_uuid, _ = _seed_notebook_and_revision(factory)
    with factory() as session:
        first = facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rev_uuid,
            title="one",
            pinned_by_user_id=1,
        )
        session.commit()
        facts_service.unpin_fact(session, fact_uuid=first.fact_uuid)
        session.commit()
        second = facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rev_uuid,
            title="two",
            pinned_by_user_id=1,
        )
        session.commit()
        assert second.fact_uuid != first.fact_uuid


def test_unpin_unknown_fact_raises(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Unknown UUID surfaces a ValidationError."""
    with factory() as session, pytest.raises(ValidationError):
        facts_service.unpin_fact(session, fact_uuid="not-a-real-uuid")


# -- list / bulk --------------------------------------------------------------


def test_list_facts_returns_active_only_by_default(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Soft-deleted rows are hidden unless ``include_unpinned=True``."""
    _, rev_uuid, _ = _seed_notebook_and_revision(factory)
    with factory() as session:
        active = facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rev_uuid,
            title="active",
            pinned_by_user_id=1,
        )
        session.commit()
        old = facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rev_uuid,
            title="will-unpin",
            cell_content_hash="h1",
            pinned_by_user_id=1,
        )
        session.commit()
        facts_service.unpin_fact(session, fact_uuid=old.fact_uuid)
        session.commit()
        only_active = facts_service.list_facts(session, workspace_id=1)
        all_incl = facts_service.list_facts(session, workspace_id=1, include_unpinned=True)
        assert {r.fact_uuid for r in only_active} == {active.fact_uuid}
        assert {r.fact_uuid for r in all_incl} == {
            active.fact_uuid,
            old.fact_uuid,
        }


def test_list_facts_for_cells_groups_by_content_hash(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Bulk lookup groups by ``cell_content_hash`` for the editor chip."""
    nb_id, rev_uuid, _ = _seed_notebook_and_revision(factory)
    with factory() as session:
        facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rev_uuid,
            title="cell-a",
            cell_content_hash="hA",
            pinned_by_user_id=1,
        )
        facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rev_uuid,
            title="cell-b",
            cell_content_hash="hB",
            pinned_by_user_id=1,
        )
        session.commit()
        grouped = facts_service.list_facts_for_cells(
            session,
            workspace_id=1,
            notebook_id=nb_id,
            cell_content_hashes=["hA", "hB", "hZ-missing"],
        )
        assert set(grouped.keys()) == {"hA", "hB"}
        assert len(grouped["hA"]) == 1
        assert grouped["hA"][0].title == "cell-a"


# -- get_fact_detail ----------------------------------------------------------


def test_get_fact_detail_expands_revision_uuid_and_notebook(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Detail envelope carries revision_uuid + notebook_id + snapshot blob."""
    nb_id, rev_uuid, _ = _seed_notebook_and_revision(factory)
    with factory() as session:
        row = facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rev_uuid,
            title="x",
            cell_content_hash="h1",
            result_snapshot_json='{"columns": ["x"], "rows": [[1]]}',
            pinned_by_user_id=1,
        )
        session.commit()
        envelope = facts_service.get_fact_detail(session, fact_uuid=row.fact_uuid)
        assert envelope is not None
        assert envelope["revision_uuid"] == rev_uuid
        assert envelope["notebook_id"] == nb_id
        assert envelope["result_snapshot_json"].startswith('{"columns"')
        assert envelope["cell_content_hash"] == "h1"
        assert envelope["active"] is True


# -- pql.facts facade (env-bridge + explicit kwargs) --------------------------


def test_pql_facade_pin_explicit_kwargs(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """`pql.facts.pin` with explicit ``session_factory + workspace_id`` works."""
    _, rev_uuid, _ = _seed_notebook_and_revision(factory)
    row = facts_facade.pin(
        rev_uuid,
        title="from facade",
        session_factory=factory,
        workspace_id=1,
        pinned_by_user_id=99,
    )
    assert row.fact_uuid is not None
    assert row.title == "from facade"
    assert row.pinned_by_user_id == 99
    # Round-trip via list_facts_for_notebook
    envelopes = facts_facade.list_facts_for_notebook(workspace_id=1, session_factory=factory)
    assert any(e["fact_uuid"] == row.fact_uuid for e in envelopes)


def test_pql_facade_pin_without_agent_or_workspace_raises(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """The facade refuses to silently default to workspace 1."""
    _, rev_uuid, _ = _seed_notebook_and_revision(factory)
    with pytest.raises(ValidationError):
        facts_facade.pin(
            rev_uuid,
            title="x",
            session_factory=factory,
            # No workspace_id, no agent_run_id, no env — must raise.
            pinned_by_user_id=None,
        )


# -- REST routes --------------------------------------------------------------


@pytest.fixture
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the editor's notebooks_dir at a tmp directory."""
    root = tmp_path / "notebooks"
    root.mkdir()
    monkeypatch.setattr(app.state.settings.jupyter, "notebooks_dir", root)
    return root


def _write_notebook(workspace_dir: Path, name: str = "facts.py") -> None:
    (workspace_dir / name).write_text("# %% [markdown]\n# # Heading\n\n# %%\nx = 1\n")


async def test_api_pin_and_list_roundtrip(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """POST creates a fact, GET surfaces it in the workspace list."""
    _write_notebook(workspace_dir)
    await admin_client.post("/api/notebooks/create", json={"path": "facts.py"})
    create_rev = await admin_client.post(
        "/api/notebooks/revisions",
        json={"path": "facts.py", "message": "pin-source"},
    )
    assert create_rev.status_code == 201, create_rev.text
    rev_uuid = create_rev.json()["revision_uuid"]

    pin = await admin_client.post(
        "/api/notebooks/facts",
        json={
            "revision_uuid": rev_uuid,
            "title": "Important",
        },
    )
    assert pin.status_code == 201, pin.text
    fact_uuid = pin.json()["fact_uuid"]
    assert fact_uuid

    listing = await admin_client.get("/api/notebooks/facts")
    assert listing.status_code == 200
    body = listing.json()
    assert any(f["fact_uuid"] == fact_uuid for f in body["facts"])


async def test_api_bulk_lookup_groups_by_cell_hash(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """``GET /api/notebooks/facts/bulk`` returns active per-cell facts."""
    _write_notebook(workspace_dir)
    await admin_client.post("/api/notebooks/create", json={"path": "facts.py"})
    create_rev = await admin_client.post("/api/notebooks/revisions", json={"path": "facts.py"})
    rev_uuid = create_rev.json()["revision_uuid"]
    # Pin two cell-output facts on two different content hashes.
    await admin_client.post(
        "/api/notebooks/facts",
        json={
            "revision_uuid": rev_uuid,
            "title": "cell-A",
            "cell_content_hash": "hA",
        },
    )
    await admin_client.post(
        "/api/notebooks/facts",
        json={
            "revision_uuid": rev_uuid,
            "title": "cell-B",
            "cell_content_hash": "hB",
        },
    )
    bulk = await admin_client.get(
        "/api/notebooks/facts/bulk?notebook_path=facts.py&cell_content_hashes=hA,hB,hMissing"
    )
    assert bulk.status_code == 200
    payload = bulk.json()
    assert set(payload["facts"].keys()) == {"hA", "hB"}
    assert payload["facts"]["hA"][0]["title"] == "cell-A"


async def test_library_facts_page_renders(
    admin_client: httpx.AsyncClient,
) -> None:
    """``GET /library/facts`` returns the browse shell."""
    page = await admin_client.get("/library/facts")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    # The Alpine factory + the page heading are both literal strings in
    # the template; checking presence catches a 404 → 200-wrong-template
    # regression.
    assert "factsLibrary()" in page.text
    assert "Pinned facts" in page.text


async def test_api_unpin_hides_from_default_list(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """DELETE flips the row inactive; default list excludes it."""
    _write_notebook(workspace_dir)
    await admin_client.post("/api/notebooks/create", json={"path": "facts.py"})
    create_rev = await admin_client.post("/api/notebooks/revisions", json={"path": "facts.py"})
    rev_uuid = create_rev.json()["revision_uuid"]
    pin = await admin_client.post(
        "/api/notebooks/facts",
        json={"revision_uuid": rev_uuid, "title": "tmp"},
    )
    fact_uuid = pin.json()["fact_uuid"]

    unpinned = await admin_client.delete(f"/api/notebooks/facts/{fact_uuid}")
    assert unpinned.status_code == 200
    body = unpinned.json()
    assert body["unpinned_at"] is not None
    assert body["active"] is False

    listing = await admin_client.get("/api/notebooks/facts")
    assert all(f["fact_uuid"] != fact_uuid for f in listing.json()["facts"])

    # But include_unpinned=true surfaces it again.
    audit_listing = await admin_client.get("/api/notebooks/facts?include_unpinned=true")
    assert any(f["fact_uuid"] == fact_uuid for f in audit_listing.json()["facts"])
