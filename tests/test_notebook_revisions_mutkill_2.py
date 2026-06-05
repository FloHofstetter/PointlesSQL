"""Mutation-killing tests — revision diff envelope + canonical output encoding.

These pin the deterministic canonical JSON encoding of the ``outputs``
half of a revision payload and the exact key/value shape of the
``compute_diff`` envelope (added / removed / changed / moved /
unchanged), including the list-collapse bookkeeping.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.models import Base, Notebook
from pointlessql.services.notebook import revisions as svc


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


def _cell(h: str, src: str) -> dict[str, object]:
    return {"content_hash": h, "cell_type": "code", "source": src}


def _make_rev(factory: sessionmaker, nb_id: str, cells: list[dict[str, object]]) -> str:  # type: ignore[type-arg]
    """Create a revision from ``cells`` and return its UUID."""
    with factory() as session:
        rev = svc.create_revision(
            session,
            notebook_id=nb_id,
            cells=cells,
            outputs=[],
            created_by="u",
        )
        rev_uuid = rev.revision_uuid
        session.commit()
    return rev_uuid


# -- canonical output encoding -----------------------------------------------


def test_canonical_payload_outputs_json_is_sorted_and_compact() -> None:
    """The outputs JSON is key-sorted with whitespace-free separators.

    Pins the exact byte shape of ``outputs_json`` so any drift in the
    ``sort_keys`` / ``separators`` arguments (which would re-order keys
    or re-introduce spaces) is observable.
    """
    cells = [_cell("h1", "x")]
    outputs = [
        {
            "content_hash": "oh",
            "kernel_session_id": "ks",
            "output_index": 3,
            "msg_type": "stream",
            "content": {"zeta": 1, "alpha": 2},
            "metadata": {"yy": 1, "aa": 2},
        }
    ]
    _, outputs_json, _ = svc.canonical_payload(cells=cells, outputs=outputs)
    assert outputs_json == (
        '[{"content":{"alpha":2,"zeta":1},"content_hash":"oh",'
        '"kernel_session_id":"ks","metadata":{"aa":2,"yy":1},'
        '"msg_type":"stream","output_index":3}]'
    )


def test_canonical_payload_sha_tracks_output_key_ordering() -> None:
    """The SHA depends on the sorted/compact output encoding.

    A non-sorted or spaced encoding would yield different bytes and a
    different digest; pin the digest to the canonical form.
    """
    outputs_sorted = [
        {
            "content_hash": "oh",
            "kernel_session_id": "ks",
            "output_index": 0,
            "msg_type": "stream",
            "content": {"alpha": 1, "zeta": 2},
            "metadata": None,
        }
    ]
    outputs_permuted = [
        {
            "metadata": None,
            "content": {"zeta": 2, "alpha": 1},
            "msg_type": "stream",
            "output_index": 0,
            "kernel_session_id": "ks",
            "content_hash": "oh",
        }
    ]
    _, _, sha_a = svc.canonical_payload(cells=[_cell("h", "x")], outputs=outputs_sorted)
    _, _, sha_b = svc.canonical_payload(cells=[_cell("h", "x")], outputs=outputs_permuted)
    # Permuting nested + top-level keys must not change the digest.
    assert sha_a == sha_b


# -- compute_diff envelope keys ----------------------------------------------


def test_compute_diff_envelope_has_expected_top_level_keys(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """The diff envelope carries the exact bucket names."""
    nb_id = _seed_notebook(factory)
    left = _make_rev(factory, nb_id, [_cell("h1", "a")])
    right = _make_rev(factory, nb_id, [_cell("h2", "b")])
    with factory() as session:
        diff = svc.compute_diff(session, left_uuid=left, right_uuid=right)
    assert set(diff) == {
        "left_uuid",
        "right_uuid",
        "added",
        "removed",
        "changed",
        "moved",
        "unchanged",
    }


def test_compute_diff_added_entry_has_position_and_cell_keys(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """An added entry is ``{position, cell}`` exactly."""
    nb_id = _seed_notebook(factory)
    left = _make_rev(factory, nb_id, [_cell("h1", "a")])
    right = _make_rev(factory, nb_id, [_cell("h1", "a"), _cell("h2", "b")])
    with factory() as session:
        diff = svc.compute_diff(session, left_uuid=left, right_uuid=right)
    assert len(diff["added"]) == 1
    entry = diff["added"][0]
    assert set(entry) == {"position", "cell"}
    assert entry["position"] == 1
    assert entry["cell"]["content_hash"] == "h2"


def test_compute_diff_removed_entry_has_position_and_cell_keys(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """A removed entry is ``{position, cell}`` exactly (and not None).

    Also pins that the removed loop unpacks a real ``(idx, cell)`` pair
    rather than ``None``.
    """
    nb_id = _seed_notebook(factory)
    left = _make_rev(factory, nb_id, [_cell("h1", "a"), _cell("h2", "b")])
    right = _make_rev(factory, nb_id, [_cell("h1", "a")])
    with factory() as session:
        diff = svc.compute_diff(session, left_uuid=left, right_uuid=right)
    assert len(diff["removed"]) == 1
    entry = diff["removed"][0]
    assert entry is not None
    assert set(entry) == {"position", "cell"}
    assert entry["position"] == 1
    assert entry["cell"]["content_hash"] == "h2"


def test_compute_diff_moved_entry_keys_and_not_none(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """A moved entry carries content_hash + both positions + cell."""
    nb_id = _seed_notebook(factory)
    left = _make_rev(factory, nb_id, [_cell("h1", "a"), _cell("h2", "b")])
    right = _make_rev(factory, nb_id, [_cell("h2", "b"), _cell("h1", "a")])
    with factory() as session:
        diff = svc.compute_diff(session, left_uuid=left, right_uuid=right)
    assert len(diff["moved"]) == 2
    for entry in diff["moved"]:
        assert entry is not None
        assert set(entry) == {"content_hash", "left_position", "right_position", "cell"}
    by_hash = {e["content_hash"]: e for e in diff["moved"]}
    # h1 moved from index 0 to index 1.
    assert by_hash["h1"]["left_position"] == 0
    assert by_hash["h1"]["right_position"] == 1


def test_compute_diff_unchanged_entry_keys_and_not_none(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """An unchanged cell (same hash, same position) carries the full entry."""
    nb_id = _seed_notebook(factory)
    left = _make_rev(factory, nb_id, [_cell("h1", "a"), _cell("h2", "b")])
    right = _make_rev(factory, nb_id, [_cell("h1", "a"), _cell("hX", "c")])
    with factory() as session:
        diff = svc.compute_diff(session, left_uuid=left, right_uuid=right)
    assert len(diff["unchanged"]) == 1
    entry = diff["unchanged"][0]
    assert entry is not None
    assert set(entry) == {"content_hash", "left_position", "right_position", "cell"}
    assert entry["content_hash"] == "h1"
    assert entry["left_position"] == 0
    assert entry["right_position"] == 0


# -- changed-bucket collapse --------------------------------------------------


def test_compute_diff_changed_collapses_same_position_pair(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """A replaced cell at one position becomes a single ``changed`` entry.

    Pins the ``{position, old, new}`` shape and that the collapse moves
    the pair OUT of ``added`` / ``removed`` (the used-index bookkeeping).
    """
    nb_id = _seed_notebook(factory)
    left = _make_rev(factory, nb_id, [_cell("L0", "old")])
    right = _make_rev(factory, nb_id, [_cell("R0", "new")])
    with factory() as session:
        diff = svc.compute_diff(session, left_uuid=left, right_uuid=right)
    assert len(diff["changed"]) == 1
    entry = diff["changed"][0]
    assert entry is not None
    assert set(entry) == {"position", "old", "new"}
    assert entry["position"] == 0
    assert entry["old"]["content_hash"] == "L0"
    assert entry["new"]["content_hash"] == "R0"
    # Collapsed pair is removed from both raw buckets.
    assert diff["added"] == []
    assert diff["removed"] == []


def test_compute_diff_changed_requires_in_used_check(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """The collapse only skips ALREADY-USED removed indices.

    With the membership test inverted (``not in``) every fresh removed
    index would be skipped and nothing would ever collapse, so a true
    replacement would surface as raw added+removed instead of changed.
    """
    nb_id = _seed_notebook(factory)
    left = _make_rev(factory, nb_id, [_cell("L0", "old")])
    right = _make_rev(factory, nb_id, [_cell("R0", "new")])
    with factory() as session:
        diff = svc.compute_diff(session, left_uuid=left, right_uuid=right)
    assert len(diff["changed"]) == 1


def test_compute_diff_collapse_matches_on_equal_position(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """A replacement only collapses when positions are equal.

    Two independent replacements at distinct positions both collapse;
    flipping the equality to inequality would mis-pair them (and the
    ``old``/``new`` would refer to the wrong cells).
    """
    nb_id = _seed_notebook(factory)
    left = _make_rev(factory, nb_id, [_cell("L0", "o0"), _cell("L1", "o1")])
    right = _make_rev(factory, nb_id, [_cell("R0", "n0"), _cell("R1", "n1")])
    with factory() as session:
        diff = svc.compute_diff(session, left_uuid=left, right_uuid=right)
    assert len(diff["changed"]) == 2
    assert diff["added"] == []
    assert diff["removed"] == []
    by_pos = {e["position"]: e for e in diff["changed"]}
    assert set(by_pos) == {0, 1}
    # Position 0 pairs L0->R0, position 1 pairs L1->R1.
    assert by_pos[0]["old"]["content_hash"] == "L0"
    assert by_pos[0]["new"]["content_hash"] == "R0"
    assert by_pos[1]["old"]["content_hash"] == "L1"
    assert by_pos[1]["new"]["content_hash"] == "R1"


def test_compute_diff_collapse_marks_added_index_used(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """A collapsed added cell is filtered out of the raw ``added`` list.

    Pins ``used_added.add(idx)`` recording the real index — recording
    ``None`` instead would leave the collapsed cell duplicated in
    ``added``.
    """
    nb_id = _seed_notebook(factory)
    left = _make_rev(factory, nb_id, [_cell("L0", "old")])
    right = _make_rev(factory, nb_id, [_cell("R0", "new")])
    with factory() as session:
        diff = svc.compute_diff(session, left_uuid=left, right_uuid=right)
    assert diff["added"] == []


def test_compute_diff_collapse_marks_removed_index_used(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """A collapsed removed cell is filtered out of the raw ``removed`` list.

    Pins both ``used_removed.add(ridx)`` (recording the real index) and
    the ``i not in used_removed`` final filter — either being inverted
    or fed ``None`` would leave the old cell in ``removed``.
    """
    nb_id = _seed_notebook(factory)
    left = _make_rev(factory, nb_id, [_cell("L0", "old")])
    right = _make_rev(factory, nb_id, [_cell("R0", "new")])
    with factory() as session:
        diff = svc.compute_diff(session, left_uuid=left, right_uuid=right)
    assert diff["removed"] == []


def test_compute_diff_returns_dict_not_none_after_collapse(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """The function returns the full envelope even after a collapse.

    A replacement exercises the collapse ``break``; if that were a
    bare ``return`` the function would yield ``None`` instead of the
    envelope.
    """
    nb_id = _seed_notebook(factory)
    left = _make_rev(factory, nb_id, [_cell("L0", "old")])
    right = _make_rev(factory, nb_id, [_cell("R0", "new")])
    with factory() as session:
        diff = svc.compute_diff(session, left_uuid=left, right_uuid=right)
    assert diff is not None
    assert isinstance(diff, dict)
    assert diff["left_uuid"] == left
    assert diff["right_uuid"] == right
