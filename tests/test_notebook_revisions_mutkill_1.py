"""Mutation-killing tests — canonical_payload encoding + parent-uuid resolution.

These pin the exact deterministic JSON encoding produced by
``canonical_payload`` (key names, value coercions, default fallbacks,
sort order, separators, and the SHA-256 framing byte) and the
``_parent_uuid`` ancestry lookup so that small behavioural mutations
in either are caught.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.exceptions import ValidationError
from pointlessql.models import Base, Notebook
from pointlessql.models.notebook import NotebookRevision
from pointlessql.services.notebook import revisions as notebook_revisions_service


def _factory() -> sessionmaker:  # type: ignore[type-arg]
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


# -- canonical_payload: exact encoding ---------------------------------------


def test_canonical_payload_emits_exact_sorted_compact_json_and_hash() -> None:
    """Encoding pins every key name, sort order, separators, and the hash.

    Non-default values are chosen for every field so a renamed key, a
    swapped value coercion, a dropped ``sort_keys=True``, an altered
    ``separators`` tuple, or a changed SHA framing byte all change the
    observed output.
    """
    cells = [
        {
            "content_hash": "ch1",
            "cell_type": "markdown",
            "source": "x = 1",
            "result_var": "rv",
            "tags": ["t1", "t2"],
        }
    ]
    outputs = [
        {
            "content_hash": "oh1",
            "kernel_session_id": "ks1",
            "output_index": 3,
            "msg_type": "stream",
            "content": {"text": "ok"},
            "metadata": {"m": 1},
        }
    ]
    cells_json, outputs_json, sha = notebook_revisions_service.canonical_payload(
        cells=cells, outputs=outputs
    )

    # Keys are alphabetically sorted (sort_keys=True) and compact
    # (no whitespace separators). This is the exact byte sequence.
    assert cells_json == (
        '[{"cell_type":"markdown","content_hash":"ch1",'
        '"result_var":"rv","source":"x = 1","tags":["t1","t2"]}]'
    )
    assert outputs_json == (
        '[{"content":{"text":"ok"},"content_hash":"oh1",'
        '"kernel_session_id":"ks1","metadata":{"m":1},'
        '"msg_type":"stream","output_index":3}]'
    )

    # The hash frames cells + outputs with a single ``|`` byte; recompute
    # it explicitly so a changed separator byte or encoding is observable.
    expected = hashlib.sha256()
    expected.update(cells_json.encode("utf-8"))
    expected.update(b"|")
    expected.update(outputs_json.encode("utf-8"))
    assert sha == expected.hexdigest()


def test_canonical_payload_keeps_all_cell_keys() -> None:
    """Every canonical cell key is present under its exact name."""
    cells_json, _, _ = notebook_revisions_service.canonical_payload(
        cells=[
            {
                "content_hash": "h",
                "cell_type": "code",
                "source": "s",
                "result_var": "r",
                "tags": ["a"],
            }
        ],
        outputs=[],
    )
    parsed = json.loads(cells_json)[0]
    assert set(parsed.keys()) == {
        "content_hash",
        "cell_type",
        "source",
        "result_var",
        "tags",
    }
    assert parsed["content_hash"] == "h"
    assert parsed["cell_type"] == "code"
    assert parsed["source"] == "s"
    assert parsed["result_var"] == "r"
    assert parsed["tags"] == ["a"]


def test_canonical_payload_keeps_all_output_keys() -> None:
    """Every canonical output key is present under its exact name."""
    _, outputs_json, _ = notebook_revisions_service.canonical_payload(
        cells=[],
        outputs=[
            {
                "content_hash": "oh",
                "kernel_session_id": "ks",
                "output_index": 7,
                "msg_type": "execute_result",
                "content": {"a": 1},
                "metadata": {"b": 2},
            }
        ],
    )
    parsed = json.loads(outputs_json)[0]
    assert set(parsed.keys()) == {
        "content_hash",
        "kernel_session_id",
        "output_index",
        "msg_type",
        "content",
        "metadata",
    }
    assert parsed["content_hash"] == "oh"
    assert parsed["kernel_session_id"] == "ks"
    assert parsed["output_index"] == 7
    assert parsed["msg_type"] == "execute_result"
    assert parsed["content"] == {"a": 1}
    assert parsed["metadata"] == {"b": 2}


def test_canonical_payload_cell_values_are_coerced_from_source_dict() -> None:
    """Truthy cell values pass through (``x or default`` keeps ``x``)."""
    cells_json, _, _ = notebook_revisions_service.canonical_payload(
        cells=[
            {
                "content_hash": "realhash",
                "cell_type": "markdown",
                "source": "actual source",
                "result_var": "the_var",
                "tags": ["one", "two"],
            }
        ],
        outputs=[],
    )
    parsed = json.loads(cells_json)[0]
    # cell_type pulls the supplied value, not the "code" fallback.
    assert parsed["cell_type"] == "markdown"
    # content_hash / source pull supplied values, not "".
    assert parsed["content_hash"] == "realhash"
    assert parsed["source"] == "actual source"
    # result_var / tags read from the right keys.
    assert parsed["result_var"] == "the_var"
    assert parsed["tags"] == ["one", "two"]


def test_canonical_payload_output_values_are_coerced_from_source_dict() -> None:
    """Truthy output values pass through unchanged."""
    _, outputs_json, _ = notebook_revisions_service.canonical_payload(
        cells=[],
        outputs=[
            {
                "content_hash": "ohash",
                "kernel_session_id": "session-9",
                "output_index": 5,
                "msg_type": "display_data",
                "content": "the content",
                "metadata": "the metadata",
            }
        ],
    )
    parsed = json.loads(outputs_json)[0]
    assert parsed["content_hash"] == "ohash"
    assert parsed["kernel_session_id"] == "session-9"
    assert parsed["output_index"] == 5
    assert parsed["msg_type"] == "display_data"
    assert parsed["content"] == "the content"
    assert parsed["metadata"] == "the metadata"


# -- canonical_payload: default fallbacks on falsy/missing inputs -------------


def test_canonical_payload_cell_defaults_on_empty_values() -> None:
    """Missing/falsy cell fields fall back to the documented defaults."""
    cells_json, _, _ = notebook_revisions_service.canonical_payload(
        cells=[{}],
        outputs=[],
    )
    parsed = json.loads(cells_json)[0]
    assert parsed["content_hash"] == ""
    assert parsed["cell_type"] == "code"
    assert parsed["source"] == ""
    assert parsed["result_var"] is None
    assert parsed["tags"] == []


def test_canonical_payload_output_defaults_on_empty_values() -> None:
    """Missing/falsy output fields fall back to the documented defaults."""
    _, outputs_json, _ = notebook_revisions_service.canonical_payload(
        cells=[],
        outputs=[{}],
    )
    parsed = json.loads(outputs_json)[0]
    assert parsed["content_hash"] == ""
    assert parsed["kernel_session_id"] == ""
    assert parsed["output_index"] == 0
    assert parsed["msg_type"] == ""
    assert parsed["content"] is None
    assert parsed["metadata"] is None


def test_canonical_payload_output_index_zero_default_is_int_zero() -> None:
    """A falsy ``output_index`` collapses to ``0`` (not ``1``)."""
    _, outputs_json, _ = notebook_revisions_service.canonical_payload(
        cells=[],
        outputs=[{"output_index": 0}],
    )
    assert json.loads(outputs_json)[0]["output_index"] == 0


def test_canonical_payload_cell_type_default_is_literal_code() -> None:
    """Empty ``cell_type`` resolves to the literal ``"code"`` string."""
    cells_json, _, _ = notebook_revisions_service.canonical_payload(
        cells=[{"cell_type": ""}],
        outputs=[],
    )
    assert json.loads(cells_json)[0]["cell_type"] == "code"


# -- _parent_uuid -------------------------------------------------------------


def test_parent_uuid_resolves_attached_parent_revision() -> None:
    """A child row attached to a session resolves its parent's UUID.

    This exercises the full happy path: the parent id is set, the row
    is session-attached, and the looked-up parent's ``revision_uuid``
    is returned (not ``None``).
    """
    factory = _factory()
    nb_id = _seed_notebook(factory)
    with factory() as session:
        first = notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[{"content_hash": "h1", "cell_type": "code", "source": "a"}],
            outputs=[],
            created_by="u",
        )
        parent_uuid = first.revision_uuid
        session.commit()
        second = notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[{"content_hash": "h2", "cell_type": "code", "source": "b"}],
            outputs=[],
            created_by="u",
        )
        session.commit()

        # The child has a real parent id, is attached, and the parent
        # exists — so the resolved value is the parent's uuid, not None.
        assert second.parent_revision_id is not None
        resolved = notebook_revisions_service._parent_uuid(second)
        assert resolved == parent_uuid


def test_parent_uuid_none_when_no_parent() -> None:
    """A root revision (no parent id) resolves to ``None``."""
    factory = _factory()
    nb_id = _seed_notebook(factory)
    with factory() as session:
        root = notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[{"content_hash": "h1", "cell_type": "code", "source": "a"}],
            outputs=[],
            created_by="u",
        )
        session.commit()
        assert root.parent_revision_id is None
        assert notebook_revisions_service._parent_uuid(root) is None


def test_parent_uuid_none_when_row_detached_from_session() -> None:
    """A detached row (no live session) resolves to ``None``.

    ``_parent_uuid`` bails out when ``Session.object_session`` returns
    ``None``; a freshly constructed, never-added row reproduces that.
    """
    detached = NotebookRevision(
        revision_uuid=str(uuid.uuid4()),
        notebook_id="nb",
        parent_revision_id=999,
        created_by=None,
        message=None,
        cells_json="[]",
        outputs_json="[]",
        content_sha256="x",
    )
    assert Session.object_session(detached) is None
    assert notebook_revisions_service._parent_uuid(detached) is None


# -- row_to_envelope: exact key set + value coercions ------------------------


def _make_attached_revision(session: Session) -> NotebookRevision:  # type: ignore[type-arg]
    """Build one persisted revision row reachable for envelope tests."""
    rev = NotebookRevision(
        revision_uuid=str(uuid.uuid4()),
        notebook_id="nb-env",
        parent_revision_id=None,
        created_by="author@test",
        message="the message",
        cells_json="[]",
        outputs_json="[]",
        content_sha256="deadbeef",
    )
    session.add(rev)
    session.flush()
    return rev


def test_row_to_envelope_has_exact_key_set() -> None:
    """The envelope's keys are exactly the documented lower-case names.

    Any renamed key (``XXmessageXX``, ``MESSAGE``, ``NOTEBOOK_ID`` …)
    changes this set, so the precise membership pins every key mutation
    at once.
    """
    factory = _factory()
    with factory() as session:
        rev = _make_attached_revision(session)
        envelope = notebook_revisions_service.row_to_envelope(rev)
    assert set(envelope.keys()) == {
        "revision_uuid",
        "notebook_id",
        "parent_revision_uuid",
        "created_by",
        "created_at",
        "message",
        "content_sha256",
        "signed",
        "signature_alg",
    }


def test_row_to_envelope_maps_each_field_to_its_key() -> None:
    """Each scalar row attribute is reachable under its exact key name.

    A key rename would move the value out from under the asserted name
    (``KeyError`` / changed membership), and the ``signed`` assertion
    pins the ``is not None`` polarity.
    """
    factory = _factory()
    with factory() as session:
        rev = _make_attached_revision(session)
        envelope = notebook_revisions_service.row_to_envelope(rev)
    assert envelope["notebook_id"] == "nb-env"
    assert envelope["created_by"] == "author@test"
    assert envelope["message"] == "the message"
    assert envelope["content_sha256"] == "deadbeef"
    assert envelope["parent_revision_uuid"] is None
    assert envelope["signature_alg"] is None
    # An unsigned row reports signed=False; the mutant that flips the
    # ``is not None`` polarity would report True here.
    assert envelope["signed"] is False


def test_row_to_envelope_signed_true_when_signature_present() -> None:
    """A row carrying a signature blob reports ``signed=True``.

    Pins the ``row.signature is not None`` direction: the inverted
    ``is None`` mutant would report ``False`` for a signed row.
    """
    factory = _factory()
    with factory() as session:
        rev = _make_attached_revision(session)
        rev.signature = "sig-blob"
        rev.signature_alg = "ed25519:k1"
        session.flush()
        envelope = notebook_revisions_service.row_to_envelope(rev)
    assert envelope["signed"] is True
    assert envelope["signature_alg"] == "ed25519:k1"


# -- create_revision: created_by persistence ---------------------------------


def test_create_revision_persists_created_by() -> None:
    """The supplied ``created_by`` is stored verbatim, not nulled.

    Kills the mutants that hardcode ``created_by=None`` or drop the
    kwarg (which would let the nullable column default to ``None``).
    """
    factory = _factory()
    nb_id = _seed_notebook(factory)
    with factory() as session:
        row = notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[{"content_hash": "h1", "cell_type": "code", "source": "a"}],
            outputs=[],
            created_by="picked@example.com",
        )
        session.flush()
        assert row.created_by == "picked@example.com"
        # Re-read from the DB so the stored column value is observed.
        fetched = session.get(NotebookRevision, row.id)
        assert fetched is not None
        assert fetched.created_by == "picked@example.com"


# -- create_revision: parent lookup query shape ------------------------------


def test_create_revision_parent_query_is_single_row_capped() -> None:
    """A third save with two priors still resolves a single parent.

    The parent lookup pairs ``.limit(1)`` with ``.scalar_one_or_none()``.
    Mutants that widen the cap (``.limit(None)`` / ``.limit(2)``) would
    pull both prior rows and make ``scalar_one_or_none`` raise
    ``MultipleResultsFound``; the original returns exactly one parent.
    """
    factory = _factory()
    nb_id = _seed_notebook(factory)
    with factory() as session:
        notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[{"content_hash": "h1", "cell_type": "code", "source": "a"}],
            outputs=[],
            created_by="u",
        )
        notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[{"content_hash": "h2", "cell_type": "code", "source": "b"}],
            outputs=[],
            created_by="u",
        )
        # Two priors now exist; the next save must not raise.
        third = notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[{"content_hash": "h3", "cell_type": "code", "source": "c"}],
            outputs=[],
            created_by="u",
        )
        assert third.parent_revision_id is not None


def test_create_revision_parent_is_newest_by_created_at() -> None:
    """The parent is the most-recent prior revision, by ``created_at``.

    With the two priors carrying explicit, distinct timestamps where
    the *higher* rowid holds the *newer* timestamp, the descending
    ``order_by`` picks that newer row.  A dropped ``order_by`` would
    fall back to rowid (insertion) order and pick the older first row
    instead.
    """
    factory = _factory()
    nb_id = _seed_notebook(factory)
    base = datetime.datetime(2024, 1, 1, 0, 0, 0)
    with factory() as session:
        first = notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[{"content_hash": "h1", "cell_type": "code", "source": "a"}],
            outputs=[],
            created_by="u",
        )
        session.flush()
        second = notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[{"content_hash": "h2", "cell_type": "code", "source": "b"}],
            outputs=[],
            created_by="u",
        )
        session.flush()
        # Lower-rowid `first` gets the older stamp; higher-rowid `second`
        # gets the newer one, so rowid order and created_at-desc disagree.
        first.created_at = base + datetime.timedelta(seconds=1)
        second.created_at = base + datetime.timedelta(seconds=10)
        session.flush()
        second_id = second.id
        third = notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[{"content_hash": "h3", "cell_type": "code", "source": "c"}],
            outputs=[],
            created_by="u",
        )
        assert third.parent_revision_id == second_id


# -- create_revision / compute_diff: not-found message carries the id --------


def test_create_revision_unknown_notebook_message_names_id() -> None:
    """The unknown-notebook error message embeds the offending id.

    Kills the mutant that raises ``ValidationError(None)`` (whose
    message is the literal ``"None"``).
    """
    factory = _factory()
    with factory() as session:
        with pytest.raises(ValidationError) as excinfo:
            notebook_revisions_service.create_revision(
                session,
                notebook_id="missing-nb-id",
                cells=[],
                outputs=[],
                created_by=None,
            )
    assert "missing-nb-id" in str(excinfo.value)


def test_compute_diff_unknown_left_message_names_left_uuid() -> None:
    """Unknown ``left`` revision error message embeds the left uuid."""
    factory = _factory()
    with factory() as session:
        with pytest.raises(ValidationError) as excinfo:
            notebook_revisions_service.compute_diff(
                session,
                left_uuid="left-ghost",
                right_uuid="right-ghost",
            )
    assert "left-ghost" in str(excinfo.value)


def test_compute_diff_unknown_right_message_names_right_uuid() -> None:
    """Unknown ``right`` revision error message embeds the right uuid.

    The ``left`` revision must exist so the failure path is the
    ``right is None`` branch specifically.
    """
    factory = _factory()
    nb_id = _seed_notebook(factory)
    with factory() as session:
        left = notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[{"content_hash": "h1", "cell_type": "code", "source": "a"}],
            outputs=[],
            created_by="u",
        )
        left_uuid = left.revision_uuid
        session.flush()
        with pytest.raises(ValidationError) as excinfo:
            notebook_revisions_service.compute_diff(
                session,
                left_uuid=left_uuid,
                right_uuid="right-ghost",
            )
    assert "right-ghost" in str(excinfo.value)


# -- list_revisions: limit / offset / ordering query shape -------------------


def _seed_two_distinct(
    factory: sessionmaker,  # type: ignore[type-arg]
    nb_id: str,
) -> tuple[int, int]:
    """Insert two revisions with distinct, explicit timestamps.

    The lower-rowid row is stamped older; returns ``(older_id,
    newer_id)`` so callers can assert ordering independent of the
    coarse ``CURRENT_TIMESTAMP`` server default.
    """
    base = datetime.datetime(2024, 1, 1, 0, 0, 0)
    with factory() as session:
        older = notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[{"content_hash": "h1", "cell_type": "code", "source": "a"}],
            outputs=[],
            created_by="u",
        )
        session.flush()
        newer = notebook_revisions_service.create_revision(
            session,
            notebook_id=nb_id,
            cells=[{"content_hash": "h2", "cell_type": "code", "source": "b"}],
            outputs=[],
            created_by="u",
        )
        session.flush()
        older.created_at = base + datetime.timedelta(seconds=1)
        newer.created_at = base + datetime.timedelta(seconds=10)
        session.flush()
        ids = (older.id, newer.id)
        session.commit()
    return ids


def test_list_revisions_respects_explicit_limit() -> None:
    """An explicit ``limit`` caps the row count.

    With two rows and ``limit=1`` the original returns one row; a
    dropped ``.limit`` (``.limit(None)``) would return both.
    """
    factory = _factory()
    nb_id = _seed_notebook(factory)
    _seed_two_distinct(factory, nb_id)
    with factory() as session:
        rows = notebook_revisions_service.list_revisions(session, notebook_id=nb_id, limit=1)
    assert len(rows) == 1


def test_list_revisions_respects_explicit_offset() -> None:
    """A positive ``offset`` skips leading rows.

    With two rows and ``offset=1`` the original returns one row; a
    dropped ``.offset`` (``.offset(None)``) would return both.
    """
    factory = _factory()
    nb_id = _seed_notebook(factory)
    _seed_two_distinct(factory, nb_id)
    with factory() as session:
        rows = notebook_revisions_service.list_revisions(session, notebook_id=nb_id, offset=1)
    assert len(rows) == 1


def test_list_revisions_orders_newest_first_by_created_at() -> None:
    """The newest revision (largest ``created_at``) is returned first.

    The two priors are stamped so rowid order and created_at-desc
    order disagree; the original ``order_by(... .desc())`` yields the
    newer row at index 0, while a dropped ``order_by`` would fall back
    to rowid order and put the older row first.
    """
    factory = _factory()
    nb_id = _seed_notebook(factory)
    older_id, newer_id = _seed_two_distinct(factory, nb_id)
    with factory() as session:
        rows = notebook_revisions_service.list_revisions(session, notebook_id=nb_id)
    assert len(rows) == 2
    uuid_to_id: dict[str, int] = {}
    with factory() as session:
        for r in session.execute(
            select(NotebookRevision).where(NotebookRevision.notebook_id == nb_id)
        ).scalars():
            uuid_to_id[r.revision_uuid] = r.id
    assert uuid_to_id[rows[0]["revision_uuid"]] == newer_id
    assert uuid_to_id[rows[1]["revision_uuid"]] == older_id


def test_list_revisions_limit_none_would_overflow_is_capped() -> None:
    """Belt-and-braces: a tiny limit never raises and caps to that size.

    Pairs with the explicit-limit test to also exercise the
    ``MultipleResultsFound``-free ``.scalars().all()`` path under a
    widened result set, distinguishing ``.limit(limit)`` from
    ``.limit(None)``.
    """
    factory = _factory()
    nb_id = _seed_notebook(factory)
    _seed_two_distinct(factory, nb_id)
    with factory() as session:
        capped = notebook_revisions_service.list_revisions(session, notebook_id=nb_id, limit=1)
        uncapped = notebook_revisions_service.list_revisions(session, notebook_id=nb_id, limit=50)
    assert len(capped) == 1
    assert len(uncapped) == 2


def test_create_revision_parent_query_limit_none_raises_on_mutant() -> None:
    """Triple-save guard: original yields one parent without raising.

    Distinct from the earlier parent test in that it asserts a clean
    return value (no ``MultipleResultsFound``) for the third write when
    two priors exist, which is the observable the limit-widening
    mutants break.
    """
    factory = _factory()
    nb_id = _seed_notebook(factory)
    with factory() as session:
        for i, h in enumerate(("h1", "h2")):
            notebook_revisions_service.create_revision(
                session,
                notebook_id=nb_id,
                cells=[{"content_hash": h, "cell_type": "code", "source": str(i)}],
                outputs=[],
                created_by="u",
            )
        try:
            third = notebook_revisions_service.create_revision(
                session,
                notebook_id=nb_id,
                cells=[{"content_hash": "h3", "cell_type": "code", "source": "c"}],
                outputs=[],
                created_by="u",
            )
        except MultipleResultsFound:  # pragma: no cover - asserts original path
            pytest.fail("parent lookup must cap to a single row")
        assert third.parent_revision_id is not None
