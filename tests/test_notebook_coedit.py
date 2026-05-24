"""Tests — coedit Y.Doc sidecar persistence."""

from __future__ import annotations

import datetime
import uuid

import pytest
from pycrdt import Map, Text
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.exceptions import ValidationError
from pointlessql.models import Base, Notebook, NotebookCrdtState
from pointlessql.services.notebook import coedit


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
    """Insert one notebooks row and return its UUID."""
    nb_id = str(uuid.uuid4())
    with factory() as s:
        s.add(Notebook(id=nb_id, workspace_id=1, file_path="co.py"))
        s.commit()
    return nb_id


# -- get_or_init_ydoc --------------------------------------------------------


def test_get_or_init_ydoc_mints_empty_doc_on_cold(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """First call inserts a row + returns an empty-but-structured Doc."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        doc = coedit.get_or_init_ydoc(session, notebook_id=nb_id)
        session.commit()
        assert isinstance(doc[coedit.CELLS_ORDER_KEY].to_py(), list)
        assert doc[coedit.CELLS_ORDER_KEY].to_py() == []
        # Row persisted
        row = session.query(NotebookCrdtState).filter_by(notebook_id=nb_id).one()
        assert len(row.y_doc_blob) > 0


def test_get_or_init_ydoc_with_seed_cells(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Seed list bootstraps the Doc on cold init only."""
    nb_id = _seed_notebook(factory)
    seed = [
        {"cell_uuid": "u1", "source": "x = 1"},
        {"cell_uuid": "u2", "source": "y = 2"},
    ]
    with factory() as session:
        doc = coedit.get_or_init_ydoc(session, notebook_id=nb_id, seed_cells=seed)
        session.commit()
        order = list(doc[coedit.CELLS_ORDER_KEY].to_py())
        assert order == ["u1", "u2"]
        cells_map: Map = doc[coedit.CELLS_TEXT_KEY]
        assert str(cells_map["u1"]) == "x = 1"
        assert str(cells_map["u2"]) == "y = 2"


def test_get_or_init_ydoc_warm_load(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Second call loads the persisted blob (idempotent ordering)."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        seed = [{"cell_uuid": "u1", "source": "x = 1"}]
        coedit.get_or_init_ydoc(session, notebook_id=nb_id, seed_cells=seed)
        session.commit()
    with factory() as session:
        doc = coedit.get_or_init_ydoc(session, notebook_id=nb_id)
        assert list(doc[coedit.CELLS_ORDER_KEY].to_py()) == ["u1"]
        assert str(doc[coedit.CELLS_TEXT_KEY]["u1"]) == "x = 1"


def test_get_or_init_ydoc_unknown_notebook(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Unknown notebook UUID surfaces ValidationError."""
    with factory() as session, pytest.raises(ValidationError):
        coedit.get_or_init_ydoc(session, notebook_id="00000000-0000-0000-0000-000000000000")


def test_seed_ignores_cells_without_uuid(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Missing cell_uuid cells are silently skipped (defensive)."""
    nb_id = _seed_notebook(factory)
    seed = [
        {"cell_uuid": None, "source": "skip"},
        {"cell_uuid": "u1", "source": "keep"},
    ]
    with factory() as session:
        doc = coedit.get_or_init_ydoc(session, notebook_id=nb_id, seed_cells=seed)
        session.commit()
        assert list(doc[coedit.CELLS_ORDER_KEY].to_py()) == ["u1"]


# -- apply_update / cross-replica roundtrip ---------------------------------


def test_apply_update_merges_client_change(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """A client's binary update lands in the server replica."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        coedit.get_or_init_ydoc(
            session,
            notebook_id=nb_id,
            seed_cells=[{"cell_uuid": "u1", "source": "x = 1"}],
        )
        session.commit()

    # Fetch the server snapshot and warm a client Doc from it.
    with factory() as session:
        snapshot = coedit.encode_state_as_update(session, notebook_id=nb_id)
    client = coedit._build_empty_doc()
    client.apply_update(snapshot)
    # Mutate the client and capture the resulting update.
    text: Text = client[coedit.CELLS_TEXT_KEY]["u1"]
    text += " + 2"
    update = client.get_update()

    with factory() as session:
        coedit.apply_update(session, notebook_id=nb_id, update_bytes=update)
        session.commit()
        # Server replica reflects the merged text.
        doc = coedit.get_or_init_ydoc(session, notebook_id=nb_id)
        assert str(doc[coedit.CELLS_TEXT_KEY]["u1"]) == "x = 1 + 2"


def test_encode_state_as_update_empty_on_cold(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """No-state-yet returns empty bytes so a brand-new client doesn't error."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        blob = coedit.encode_state_as_update(session, notebook_id=nb_id)
        assert blob == b""


def test_encode_state_as_update_warm(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """After init, the encoded state matches what apply_update sees."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        coedit.get_or_init_ydoc(
            session,
            notebook_id=nb_id,
            seed_cells=[{"cell_uuid": "u1", "source": "x = 1"}],
        )
        session.commit()
        snapshot = coedit.encode_state_as_update(session, notebook_id=nb_id)
        assert len(snapshot) > 0
        # Re-import in a fresh client and read back.
        client = coedit._build_empty_doc()
        client.apply_update(snapshot)
        assert list(client[coedit.CELLS_ORDER_KEY].to_py()) == ["u1"]


# -- compaction --------------------------------------------------------------


def test_compact_resets_blob_and_stamps_compacted_at(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """``compact`` rewrites the row + sets ``compacted_at``."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        coedit.get_or_init_ydoc(
            session,
            notebook_id=nb_id,
            seed_cells=[{"cell_uuid": "u1", "source": "x"}],
        )
        session.commit()
    with factory() as session:
        coedit.compact(session, notebook_id=nb_id)
        session.commit()
        row = session.query(NotebookCrdtState).filter_by(notebook_id=nb_id).one()
        assert row.compacted_at is not None
        # Still functional after compact
        client = coedit._build_empty_doc()
        client.apply_update(bytes(row.y_doc_blob))
        assert list(client[coedit.CELLS_ORDER_KEY].to_py()) == ["u1"]


def test_needs_compaction_size_threshold() -> None:
    """``needs_compaction`` flips ``True`` once size crosses bound."""
    now = datetime.datetime.now(datetime.UTC)
    small = NotebookCrdtState(
        notebook_id="x",
        y_doc_blob=b"a" * 1024,
        updated_at=now,
        compacted_at=now,
    )
    big = NotebookCrdtState(
        notebook_id="x",
        y_doc_blob=b"a" * (coedit.COMPACTION_SIZE_BYTES + 1),
        updated_at=now,
        compacted_at=now,
    )
    assert coedit.needs_compaction(small) is False
    assert coedit.needs_compaction(big) is True


def test_needs_compaction_ttl_threshold() -> None:
    """``needs_compaction`` flips after the TTL elapses."""
    now = datetime.datetime.now(datetime.UTC)
    fresh = NotebookCrdtState(
        notebook_id="x",
        y_doc_blob=b"a",
        updated_at=now,
        compacted_at=now,
    )
    stale = NotebookCrdtState(
        notebook_id="x",
        y_doc_blob=b"a",
        updated_at=now - 2 * coedit.COMPACTION_TTL,
        compacted_at=now - 2 * coedit.COMPACTION_TTL,
    )
    assert coedit.needs_compaction(fresh) is False
    assert coedit.needs_compaction(stale) is True
