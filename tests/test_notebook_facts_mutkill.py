"""Mutation-killing tests for notebook revision facts.

These pin the observable behaviour of the storage-focused facts service:
deterministic ``pinned_at desc`` ordering with offset/limit caps, the
multi-filter bulk cell lookup (workspace / notebook / cell-hash / active),
the title-length boundary, the timezone-aware unpin stamp, and the exact
dict keys of the REST envelope.
"""

from __future__ import annotations

import datetime
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.exceptions import ValidationError
from pointlessql.models import Base, Notebook
from pointlessql.models.notebook import NotebookRevisionFact
from pointlessql.models.social._social_target import SocialTarget
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
    file_path: str = "n.py",
) -> tuple[str, str, int]:
    """Insert one notebook + one revision and return ``(nb_id, rev_uuid, rev_id)``."""
    nb_id = str(uuid.uuid4())
    with factory() as s:
        s.add(Notebook(id=nb_id, workspace_id=workspace_id, file_path=file_path))
        rev = revisions_service.create_revision(
            s,
            notebook_id=nb_id,
            cells=[{"content_hash": "h1", "cell_type": "code", "source": "x"}],
            outputs=[],
            created_by="u@test",
        )
        s.commit()
        return nb_id, rev.revision_uuid, rev.id


# -- list_facts ordering ------------------------------------------------------


def test_list_facts_orders_by_pinned_at_desc(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Newest ``pinned_at`` comes first, independent of insertion order."""
    _, rev_uuid, _ = _seed_notebook_and_revision(factory)
    with factory() as session:
        # Insert "older" first, "newer" second, then force pinned_at so the
        # desired output order is the REVERSE of insertion order.  A mutant
        # that drops the ORDER BY (or sorts on NULL) falls back to insertion
        # order and produces [older, newer] instead.
        older = facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rev_uuid,
            title="older",
            pinned_by_user_id=1,
        )
        session.commit()
        older.pinned_at = datetime.datetime(2020, 1, 1)
        session.commit()
        newer = facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rev_uuid,
            title="newer",
            cell_content_hash="h1",
            pinned_by_user_id=1,
        )
        session.commit()
        newer.pinned_at = datetime.datetime(2025, 1, 1)
        session.commit()

        result = facts_service.list_facts(session, workspace_id=1)
        assert [r.title for r in result] == ["newer", "older"]


# -- list_facts offset / limit ------------------------------------------------


def _seed_three_dated_facts(
    factory: sessionmaker,  # type: ignore[type-arg]
    rev_uuid: str,
) -> None:
    """Pin three facts with strictly increasing pinned_at (t0<t1<t2)."""
    with factory() as session:
        for i, (h, year) in enumerate([("h1", 2020), ("h2", 2021), ("h3", 2022)]):
            row = facts_service.pin_revision_fact(
                session,
                workspace_id=1,
                revision_uuid=rev_uuid,
                title=f"t{i}",
                cell_content_hash=h,
                pinned_by_user_id=1,
            )
            session.commit()
            row.pinned_at = datetime.datetime(year, 1, 1)
            session.commit()


def test_list_facts_offset_skips_rows(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """A positive offset drops the newest rows; offset(None) would keep them."""
    _, rev_uuid, _ = _seed_notebook_and_revision(factory)
    _seed_three_dated_facts(factory, rev_uuid)
    with factory() as session:
        result = facts_service.list_facts(session, workspace_id=1, offset=1)
        # desc order is [t2, t1, t0]; offset 1 yields exactly [t1, t0].
        assert [r.title for r in result] == ["t1", "t0"]


def test_list_facts_limit_one_returns_single_newest(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """limit=1 returns exactly one row; max(2, ...) would return two."""
    _, rev_uuid, _ = _seed_notebook_and_revision(factory)
    _seed_three_dated_facts(factory, rev_uuid)
    with factory() as session:
        result = facts_service.list_facts(session, workspace_id=1, limit=1)
        assert len(result) == 1
        assert result[0].title == "t2"


def test_list_facts_limit_caps_at_500(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """The upper bound is 500 even when a larger limit is requested."""
    _, rev_uuid, rev_id = _seed_notebook_and_revision(factory)
    with factory() as session:
        target = SocialTarget(
            workspace_id=1,
            entity_kind="notebook_revision",
            entity_ref="bulk",
        )
        session.add(target)
        session.flush()
        for _ in range(501):
            session.add(
                NotebookRevisionFact(
                    fact_uuid=str(uuid.uuid4()),
                    workspace_id=1,
                    social_target_id=target.id,
                    revision_id=rev_id,
                    title="bulk",
                    pinned_by_user_id=1,
                )
            )
        session.commit()
        result = facts_service.list_facts(session, workspace_id=1, limit=501)
        # min(500, 501) -> 500.  A mutant raising the cap to 501 returns 501.
        assert len(result) == 500


# -- list_facts_for_cells filters ---------------------------------------------


def test_list_facts_for_cells_applies_all_filters(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Bulk lookup is scoped by workspace, notebook, cell-hash, and active flag."""
    nb1, rv1, _ = _seed_notebook_and_revision(factory, workspace_id=1, file_path="a.py")
    nb1b, rv1b, _ = _seed_notebook_and_revision(factory, workspace_id=1, file_path="b.py")
    _, rv2, _ = _seed_notebook_and_revision(factory, workspace_id=2, file_path="c.py")
    with factory() as session:
        facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rv1,
            title="target-hA",
            cell_content_hash="hA",
            pinned_by_user_id=1,
        )
        will_unpin = facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rv1,
            title="target-hB",
            cell_content_hash="hB",
            pinned_by_user_id=1,
        )
        # hC is in the same workspace+notebook but NOT in the query list.
        facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rv1,
            title="target-hC",
            cell_content_hash="hC",
            pinned_by_user_id=1,
        )
        # Same workspace, DIFFERENT notebook, same hash hA.
        facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rv1b,
            title="other-notebook-hA",
            cell_content_hash="hA",
            pinned_by_user_id=1,
        )
        # DIFFERENT workspace, same hash hA.
        facts_service.pin_revision_fact(
            session,
            workspace_id=2,
            revision_uuid=rv2,
            title="other-workspace-hA",
            cell_content_hash="hA",
            pinned_by_user_id=1,
        )
        session.commit()
        facts_service.unpin_fact(session, fact_uuid=will_unpin.fact_uuid)
        session.commit()

        grouped = facts_service.list_facts_for_cells(
            session,
            workspace_id=1,
            notebook_id=nb1,
            cell_content_hashes=["hA", "hB"],
        )
        # Only the active hA fact from this workspace+notebook survives.
        assert sorted(grouped.keys()) == ["hA"]
        assert [r.title for r in grouped["hA"]] == ["target-hA"]
        # hB was unpinned (active filter); hC was not requested (hash filter).
        assert "hB" not in grouped
        assert "hC" not in grouped


# -- pin_revision_fact title-length boundary ----------------------------------


def test_pin_accepts_title_of_exactly_200_chars(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """200 chars is the inclusive maximum (``> 200``, not ``>= 200``)."""
    _, rev_uuid, _ = _seed_notebook_and_revision(factory)
    with factory() as session:
        row = facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rev_uuid,
            title="a" * 200,
            pinned_by_user_id=1,
        )
        session.commit()
        assert len(row.title) == 200


def test_pin_rejects_title_of_201_chars(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """201 chars is over the limit (``> 200``, not ``> 201``)."""
    _, rev_uuid, _ = _seed_notebook_and_revision(factory)
    with factory() as session, pytest.raises(ValidationError):
        facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rev_uuid,
            title="a" * 201,
            pinned_by_user_id=1,
        )


# -- unpin_fact timezone awareness --------------------------------------------


def test_unpin_stamps_timezone_aware_utc(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """``unpinned_at`` is timezone-aware UTC, not naive local time."""
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
        updated = facts_service.unpin_fact(session, fact_uuid=row.fact_uuid)
        assert updated.unpinned_at is not None
        # now(None) would produce a naive datetime (tzinfo is None).
        assert updated.unpinned_at.tzinfo is not None
        assert updated.unpinned_at.utcoffset() == datetime.timedelta(0)


# -- row_to_envelope dict keys ------------------------------------------------


def test_row_to_envelope_uses_exact_keys(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """The REST envelope carries every documented snake_case key verbatim."""
    _, rev_uuid, _ = _seed_notebook_and_revision(factory)
    with factory() as session:
        row = facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rev_uuid,
            title="enveloped",
            cell_content_hash="h1",
            pinned_by_user_id=7,
            pinned_by_agent_id="agent-9",
        )
        session.commit()
        envelope = facts_service.row_to_envelope(row)

        assert envelope["workspace_id"] == 1
        assert envelope["social_target_id"] == row.social_target_id
        assert envelope["revision_id"] == row.revision_id
        assert envelope["pinned_by_user_id"] == 7
        assert envelope["pinned_by_agent_id"] == "agent-9"
        # pinned_at has a server default, so it is always serialised.
        assert envelope["pinned_at"] is not None
        # The mutated-key variants would drop these keys entirely.
        for key in (
            "workspace_id",
            "social_target_id",
            "revision_id",
            "pinned_by_user_id",
            "pinned_by_agent_id",
            "pinned_at",
        ):
            assert key in envelope


# -- list_facts_for_cells workspace scope + empty-hash key --------------------


def test_list_facts_for_cells_excludes_other_workspace_same_notebook(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """The bulk lookup is scoped by ``workspace_id`` even on a shared revision.

    Two facts point at the *same* revision (hence the same notebook) but
    live in different workspaces.  Dropping the workspace filter on the
    query would surface the foreign-workspace fact too.
    """
    nb_id, rev_uuid, rev_id = _seed_notebook_and_revision(factory)
    with factory() as session:
        facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rev_uuid,
            title="ws1-hA",
            cell_content_hash="hA",
            pinned_by_user_id=1,
        )
        session.commit()
        # A workspace-2 fact on the SAME revision/notebook + hash, inserted
        # directly (the service would reject a cross-workspace pin upstream).
        target = SocialTarget(
            workspace_id=2,
            entity_kind="notebook_cell_output",
            entity_ref="ws2",
        )
        session.add(target)
        session.flush()
        session.add(
            NotebookRevisionFact(
                fact_uuid=str(uuid.uuid4()),
                workspace_id=2,
                social_target_id=target.id,
                revision_id=rev_id,
                cell_content_hash="hA",
                title="ws2-hA",
                pinned_by_user_id=1,
            )
        )
        session.commit()

        grouped = facts_service.list_facts_for_cells(
            session,
            workspace_id=1,
            notebook_id=nb_id,
            cell_content_hashes=["hA"],
        )
        assert sorted(r.title for r in grouped["hA"]) == ["ws1-hA"]


def test_list_facts_for_cells_keys_empty_hash_as_empty_string(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """A falsy (empty-string) ``cell_content_hash`` groups under ``""``.

    The ``or "..."`` fallback only fires for a falsy hash; an empty-string
    hash queried back must land in the ``""`` bucket, not a literal default.
    """
    nb_id, rev_uuid, rev_id = _seed_notebook_and_revision(factory)
    with factory() as session:
        target = SocialTarget(
            workspace_id=1,
            entity_kind="notebook_cell_output",
            entity_ref="empty",
        )
        session.add(target)
        session.flush()
        session.add(
            NotebookRevisionFact(
                fact_uuid=str(uuid.uuid4()),
                workspace_id=1,
                social_target_id=target.id,
                revision_id=rev_id,
                cell_content_hash="",
                title="empty-hash",
                pinned_by_user_id=1,
            )
        )
        session.commit()

        grouped = facts_service.list_facts_for_cells(
            session,
            workspace_id=1,
            notebook_id=nb_id,
            cell_content_hashes=[""],
        )
        assert list(grouped.keys()) == [""]
        assert [r.title for r in grouped[""]] == ["empty-hash"]


# -- pin_revision_fact idempotency workspace scope ----------------------------


def test_pin_idempotency_lookup_is_workspace_scoped(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """A foreign-workspace active fact on the same revision is not reused.

    The idempotent active-row lookup filters on ``workspace_id``; without
    it, pinning into workspace 1 would return the pre-existing workspace-2
    row instead of minting a fresh workspace-1 fact.
    """
    _, rev_uuid, rev_id = _seed_notebook_and_revision(factory)
    with factory() as session:
        target = SocialTarget(
            workspace_id=2,
            entity_kind="notebook_revision",
            entity_ref="ws2",
        )
        session.add(target)
        session.flush()
        foreign = NotebookRevisionFact(
            fact_uuid=str(uuid.uuid4()),
            workspace_id=2,
            social_target_id=target.id,
            revision_id=rev_id,
            cell_content_hash=None,
            title="ws2-existing",
            pinned_by_user_id=1,
        )
        session.add(foreign)
        session.commit()
        foreign_uuid = foreign.fact_uuid

        row = facts_service.pin_revision_fact(
            session,
            workspace_id=1,
            revision_uuid=rev_uuid,
            title="ws1-new",
            pinned_by_user_id=1,
        )
        session.commit()
        assert row.workspace_id == 1
        assert row.title == "ws1-new"
        assert row.fact_uuid != foreign_uuid


# -- exact ValidationError detail strings -------------------------------------
#
# The detail text flows into ``ValidationError.detail`` (and from there into
# the RFC 9457 error envelope), so each branch's exact message is part of the
# contract.  Asserting it kills the None / case-flip / literal-swap mutants.


def test_pin_empty_title_detail_message(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """An empty title raises with the exact non-empty-string message."""
    _, rev_uuid, _ = _seed_notebook_and_revision(factory)
    with factory() as session:
        with pytest.raises(ValidationError) as excinfo:
            facts_service.pin_revision_fact(
                session,
                workspace_id=1,
                revision_uuid=rev_uuid,
                title="",
                pinned_by_user_id=1,
            )
        assert excinfo.value.detail == "title must be a non-empty string"


def test_pin_overlong_title_detail_message(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """An over-200 title raises with the exact length-limit message."""
    _, rev_uuid, _ = _seed_notebook_and_revision(factory)
    with factory() as session:
        with pytest.raises(ValidationError) as excinfo:
            facts_service.pin_revision_fact(
                session,
                workspace_id=1,
                revision_uuid=rev_uuid,
                title="a" * 201,
                pinned_by_user_id=1,
            )
        assert excinfo.value.detail == "title must be at most 200 characters"


def test_pin_missing_attribution_detail_message(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Missing attribution raises with the exact requires-either message."""
    _, rev_uuid, _ = _seed_notebook_and_revision(factory)
    with factory() as session:
        with pytest.raises(ValidationError) as excinfo:
            facts_service.pin_revision_fact(
                session,
                workspace_id=1,
                revision_uuid=rev_uuid,
                title="x",
                pinned_by_user_id=None,
                pinned_by_agent_id=None,
            )
        assert excinfo.value.detail == "pin requires either pinned_by_user_id or pinned_by_agent_id"


def test_pin_unknown_revision_detail_message(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """An unknown revision raises with the exact not-found message."""
    bad = "00000000-0000-0000-0000-000000000000"
    with factory() as session:
        with pytest.raises(ValidationError) as excinfo:
            facts_service.pin_revision_fact(
                session,
                workspace_id=1,
                revision_uuid=bad,
                title="x",
                pinned_by_user_id=1,
            )
        assert excinfo.value.detail == f"revision {bad!r} not found"


def test_pin_cross_workspace_detail_message(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """A cross-workspace pin raises with the exact not-in-workspace message."""
    _, rev_uuid, _ = _seed_notebook_and_revision(factory, workspace_id=1)
    with factory() as session:
        with pytest.raises(ValidationError) as excinfo:
            facts_service.pin_revision_fact(
                session,
                workspace_id=2,
                revision_uuid=rev_uuid,
                title="x",
                pinned_by_user_id=1,
            )
        assert excinfo.value.detail == f"revision {rev_uuid!r} is not in workspace 2"


def test_unpin_unknown_fact_detail_message(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Unpinning an unknown UUID raises with the exact not-found message."""
    with factory() as session:
        with pytest.raises(ValidationError) as excinfo:
            facts_service.unpin_fact(session, fact_uuid="missing")
        assert excinfo.value.detail == "fact 'missing' not found"


def test_unpin_already_unpinned_detail_message(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Re-unpinning raises with the exact already-unpinned message."""
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
        facts_service.unpin_fact(session, fact_uuid=row.fact_uuid)
        session.commit()
        with pytest.raises(ValidationError) as excinfo:
            facts_service.unpin_fact(session, fact_uuid=row.fact_uuid)
        assert excinfo.value.detail == f"fact {row.fact_uuid!r} is already unpinned"
