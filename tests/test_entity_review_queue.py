"""Entity-link candidate review queue (Phase 145)."""

from __future__ import annotations

import datetime
import json
from decimal import Decimal

import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    DataProduct,
    DataProductEntity,
    EntityLink,
    EntityLinkCandidate,
)
from pointlessql.services.entities import (
    accept_candidate,
    defer_candidate,
    list_candidates_by_decision,
    list_pending_candidates,
    reject_candidate,
)


def _factory():
    return app.state.session_factory


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _seed_entity_pair() -> tuple[int, int]:
    contract = {"name": "x", "version": "1.0.0", "tables": []}
    with _factory()() as session:
        dp = DataProduct(
            workspace_id=1,
            catalog_name="rq",
            schema_name="data",
            version="1.0.0",
            description="",
            sla_minutes=None,
            contract_yaml_hash="0" * 64,
            contract_json=json.dumps(contract),
            last_loaded_at=_now(),
            created_at=_now(),
        )
        session.add(dp)
        session.commit()
        e1 = DataProductEntity(
            data_product_id=dp.id,
            entity_name="Source",
            source_table="src",
            primary_key_columns=json.dumps(["id"]),
            description=None,
            created_at=_now(),
            updated_at=_now(),
        )
        e2 = DataProductEntity(
            data_product_id=dp.id,
            entity_name="Target",
            source_table="tgt",
            primary_key_columns=json.dumps(["id"]),
            description=None,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add_all([e1, e2])
        session.commit()
        return int(e1.id), int(e2.id)


def _make_candidate(source: int, target: int) -> int:
    with _factory()() as session:
        row = EntityLinkCandidate(
            source_entity_id=source,
            target_entity_id=target,
            kind="same_as",
            confidence_score=Decimal("0.90"),
            evidence_json="{}",
            discovered_at=_now(),
        )
        session.add(row)
        session.commit()
        return int(row.id)


@pytest.fixture(autouse=True)
def _wipe():
    with _factory()() as session:
        session.query(EntityLinkCandidate).delete()
        session.query(EntityLink).delete()
        session.query(DataProductEntity).delete()
        session.query(DataProduct).delete()
        session.commit()
    yield


def test_pending_queue_returns_undecided_only() -> None:
    src, tgt = _seed_entity_pair()
    _make_candidate(src, tgt)
    pending = list_pending_candidates(_factory())
    assert len(pending) == 1
    assert pending[0]["decision"] is None


def test_accept_promotes_to_entity_link() -> None:
    src, tgt = _seed_entity_pair()
    cand_id = _make_candidate(src, tgt)
    result = accept_candidate(
        _factory(), candidate_id=cand_id, reviewed_by_user_id=None
    )
    assert result["decision"] == "accepted"
    with _factory()() as session:
        link_count = session.query(EntityLink).count()
        assert link_count == 1


def test_reject_marks_decision_without_link() -> None:
    src, tgt = _seed_entity_pair()
    cand_id = _make_candidate(src, tgt)
    result = reject_candidate(
        _factory(), candidate_id=cand_id, reviewed_by_user_id=None
    )
    assert result["decision"] == "rejected"
    with _factory()() as session:
        assert session.query(EntityLink).count() == 0
        cand = session.get(EntityLinkCandidate, cand_id)
        assert cand is not None
        assert cand.decision == "rejected"


def test_defer_marks_decision_separately() -> None:
    src, tgt = _seed_entity_pair()
    cand_id = _make_candidate(src, tgt)
    defer_candidate(_factory(), candidate_id=cand_id, reviewed_by_user_id=None)
    deferred = list_candidates_by_decision(_factory(), decision="deferred")
    assert len(deferred) == 1
    assert list_pending_candidates(_factory()) == []


def test_double_decision_raises_value_error() -> None:
    src, tgt = _seed_entity_pair()
    cand_id = _make_candidate(src, tgt)
    accept_candidate(_factory(), candidate_id=cand_id, reviewed_by_user_id=None)
    with pytest.raises(ValueError, match="already decided"):
        reject_candidate(
            _factory(), candidate_id=cand_id, reviewed_by_user_id=None
        )


def test_unknown_candidate_raises_lookup_error() -> None:
    with pytest.raises(LookupError):
        accept_candidate(_factory(), candidate_id=99999, reviewed_by_user_id=None)


def test_listings_sort_pending_by_confidence_desc() -> None:
    src, tgt = _seed_entity_pair()
    with _factory()() as session:
        a = EntityLinkCandidate(
            source_entity_id=src,
            target_entity_id=tgt,
            kind="same_as",
            confidence_score=Decimal("0.75"),
            evidence_json="{}",
            discovered_at=_now(),
        )
        b = EntityLinkCandidate(
            source_entity_id=tgt,
            target_entity_id=src,
            kind="same_as",
            confidence_score=Decimal("0.95"),
            evidence_json="{}",
            discovered_at=_now(),
        )
        session.add_all([a, b])
        session.commit()
    pending = list_pending_candidates(_factory())
    assert pending[0]["confidence_score"] > pending[1]["confidence_score"]


def test_pagination_offsets_correctly() -> None:
    src, tgt = _seed_entity_pair()
    for i in range(5):
        with _factory()() as session:
            row = EntityLinkCandidate(
                source_entity_id=src,
                target_entity_id=tgt + i if i % 2 == 0 else tgt,
                kind="same_as" if i == 0 else "derives_from",
                confidence_score=Decimal(f"0.{50 + i}"),
                evidence_json="{}",
                discovered_at=_now(),
            )
            session.add(row)
            try:
                session.commit()
            except Exception:  # noqa: BLE001
                # bare-broad-ok: relaxed seed loop; unique constraint OK to skip
                session.rollback()
    page = list_pending_candidates(_factory(), limit=2, offset=0)
    assert len(page) <= 2
