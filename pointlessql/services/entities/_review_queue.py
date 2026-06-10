"""Steward review queue for entity-link candidates.

Three terminal actions:

* :func:`accept_candidate` — promote to an :class:`EntityLink` row
  via the existing :func:`link_entities` helper.
* :func:`reject_candidate` — stamp ``decision='rejected'``.
* :func:`defer_candidate` — stamp ``decision='deferred'`` (visible
  on a separate filter but not in the pending queue).
"""

from __future__ import annotations

import datetime
import json
from typing import Any

from sqlalchemy import select

from pointlessql.models import EntityLinkCandidate
from pointlessql.services.entities._crud import link_entities
from pointlessql.types import SessionFactory


def list_pending_candidates(
    session_factory: SessionFactory,
    *,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return pending (un-decided) candidates ordered by confidence desc."""
    return _list_candidates(
        session_factory,
        decision_filter=None,
        limit=limit,
        offset=offset,
    )


def list_candidates_by_decision(
    session_factory: SessionFactory,
    *,
    decision: str,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return candidates with the given decision value."""
    return _list_candidates(
        session_factory,
        decision_filter=decision,
        limit=limit,
        offset=offset,
    )


def accept_candidate(
    session_factory: SessionFactory,
    *,
    candidate_id: int,
    reviewed_by_user_id: int | None,
) -> dict[str, Any]:
    """Promote a candidate into an :class:`EntityLink`.

    Args:
        session_factory: Sessionmaker backing the candidate and
            entity-link tables.
        candidate_id: PK of the :class:`EntityLinkCandidate` row to
            accept.
        reviewed_by_user_id: User credited with the decision (also
            recorded as the new link's declarer), or ``None`` for
            system-driven acceptance.

    Returns:
        Summary dict carrying the candidate id, the ``"accepted"``
        decision, and the linked source/target entity ids plus the
        link kind.

    Raises:
        LookupError: When the candidate id is unknown.
        ValueError: When the candidate is already decided.
    """
    with session_factory() as session:
        row = session.get(EntityLinkCandidate, candidate_id)
        if row is None:
            raise LookupError(f"candidate {candidate_id} not found")
        if row.decision is not None:
            raise ValueError(f"candidate {candidate_id} already decided: {row.decision}")
        row.decision = "accepted"
        row.reviewed_at = datetime.datetime.now(datetime.UTC)
        row.reviewed_by_user_id = reviewed_by_user_id
        source = int(row.source_entity_id)
        target = int(row.target_entity_id)
        kind = str(row.kind)
        confidence = float(row.confidence_score)
        session.commit()
    link_entities(
        session_factory,
        source_entity_id=source,
        target_entity_id=target,
        kind=kind,
        confidence=confidence,
        declared_by_user_id=reviewed_by_user_id,
    )
    return {
        "candidate_id": candidate_id,
        "decision": "accepted",
        "source_entity_id": source,
        "target_entity_id": target,
        "kind": kind,
    }


def reject_candidate(
    session_factory: SessionFactory,
    *,
    candidate_id: int,
    reviewed_by_user_id: int | None,
) -> dict[str, Any]:
    """Mark a candidate as rejected (no entity_link is created)."""
    return _set_decision(
        session_factory,
        candidate_id=candidate_id,
        decision="rejected",
        reviewed_by_user_id=reviewed_by_user_id,
    )


def defer_candidate(
    session_factory: SessionFactory,
    *,
    candidate_id: int,
    reviewed_by_user_id: int | None,
) -> dict[str, Any]:
    """Mark a candidate as deferred (re-review later)."""
    return _set_decision(
        session_factory,
        candidate_id=candidate_id,
        decision="deferred",
        reviewed_by_user_id=reviewed_by_user_id,
    )


def _set_decision(
    session_factory: SessionFactory,
    *,
    candidate_id: int,
    decision: str,
    reviewed_by_user_id: int | None,
) -> dict[str, Any]:
    with session_factory() as session:
        row = session.get(EntityLinkCandidate, candidate_id)
        if row is None:
            raise LookupError(f"candidate {candidate_id} not found")
        if row.decision is not None:
            raise ValueError(f"candidate {candidate_id} already decided: {row.decision}")
        row.decision = decision
        row.reviewed_at = datetime.datetime.now(datetime.UTC)
        row.reviewed_by_user_id = reviewed_by_user_id
        session.commit()
    return {
        "candidate_id": candidate_id,
        "decision": decision,
    }


def _list_candidates(
    session_factory: SessionFactory,
    *,
    decision_filter: str | None,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    with session_factory() as session:
        stmt = select(EntityLinkCandidate)
        if decision_filter is None:
            stmt = stmt.where(EntityLinkCandidate.decision.is_(None))
        else:
            stmt = stmt.where(EntityLinkCandidate.decision == decision_filter)
        stmt = (
            stmt.order_by(EntityLinkCandidate.confidence_score.desc())
            .limit(max(1, min(limit, 500)))
            .offset(max(0, offset))
        )
        rows = session.scalars(stmt).all()
        out: list[dict[str, Any]] = []
        for row in rows:
            evidence: dict[str, Any] = {}
            if row.evidence_json:
                try:
                    decoded = json.loads(row.evidence_json)
                    if isinstance(decoded, dict):
                        evidence = decoded
                except json.JSONDecodeError, ValueError:
                    pass
            out.append(
                {
                    "id": int(row.id),
                    "source_entity_id": int(row.source_entity_id),
                    "target_entity_id": int(row.target_entity_id),
                    "kind": row.kind,
                    "confidence_score": float(row.confidence_score),
                    "evidence": evidence,
                    "discovered_at": row.discovered_at.isoformat(),
                    "decision": row.decision,
                    "reviewed_at": (
                        row.reviewed_at.isoformat() if row.reviewed_at is not None else None
                    ),
                }
            )
        return out
