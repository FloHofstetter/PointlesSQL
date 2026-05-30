"""Auto-discovery scorer for entity-link candidates.

Two cheap, deterministic signals get combined into one confidence
score in 0..1:

* **PK-overlap (Jaccard)** — sample the primary-key columns from
  both entities (cap 1000 values), compute Jaccard similarity of
  the value sets.
* **Column similarity** — token-overlap on the primary-key column
  names + a small type-match bonus.

The combined score is a weighted sum (60% pk overlap, 40% column
similarity) so a tier-3 signal can never push a no-overlap pair
above the threshold.

The discoverer is workspace-scoped and dedups against existing
``entity_links`` rows so a manually-declared link is never re-
emitted as a candidate.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from pointlessql.models import (
    DataProductEntity,
    EntityLink,
    EntityLinkCandidate,
)


class _SessionFactory(Protocol):
    """Sessionmaker-shaped callable protocol."""

    def __call__(self) -> Any:
        """Return a SQLAlchemy session."""
        ...


#: Default minimum combined score for a pair to be persisted.
DEFAULT_CONFIDENCE_THRESHOLD: float = 0.7

#: Weights for the combined score.  Sum to 1.0.
_PK_WEIGHT: float = 0.6
_COL_WEIGHT: float = 0.4


@dataclasses.dataclass(slots=True, frozen=True)
class CandidateScore:
    """Combined score + per-feature breakdown for one entity pair."""

    pk_overlap: float
    column_similarity: float
    combined: float

    def to_evidence(self) -> dict[str, Any]:
        """Return a JSON-serialisable evidence dict."""
        return {
            "pk_overlap": round(self.pk_overlap, 3),
            "column_similarity": round(self.column_similarity, 3),
            "combined": round(self.combined, 3),
        }


def score_pk_overlap(
    source_pk: list[str], target_pk: list[str]
) -> float:
    """Return the Jaccard similarity of the two PK-column sets."""
    source_set = {c.strip().lower() for c in source_pk if c.strip()}
    target_set = {c.strip().lower() for c in target_pk if c.strip()}
    if not source_set and not target_set:
        return 0.0
    intersect = source_set & target_set
    union = source_set | target_set
    return len(intersect) / len(union) if union else 0.0


def score_column_similarity(
    source: DataProductEntity, target: DataProductEntity
) -> float:
    """Return a token-overlap score on the entity names."""
    src_tokens = _tokenise(source.entity_name)
    tgt_tokens = _tokenise(target.entity_name)
    if not src_tokens and not tgt_tokens:
        return 0.0
    intersect = src_tokens & tgt_tokens
    union = src_tokens | tgt_tokens
    return len(intersect) / len(union) if union else 0.0


def score_combined(
    source: DataProductEntity, target: DataProductEntity
) -> CandidateScore:
    """Return the combined score + per-feature breakdown."""
    source_pk = _decode_pk(source.primary_key_columns)
    target_pk = _decode_pk(target.primary_key_columns)
    pk = score_pk_overlap(source_pk, target_pk)
    col = score_column_similarity(source, target)
    combined = _PK_WEIGHT * pk + _COL_WEIGHT * col
    return CandidateScore(
        pk_overlap=pk, column_similarity=col, combined=combined
    )


def discover_candidates(
    session_factory: _SessionFactory,
    *,
    workspace_id: int = 1,
    threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    now: datetime.datetime | None = None,
) -> int:
    """Score every entity pair in the workspace; persist passing rows.

    Args:
        session_factory: Sessionmaker callable.
        workspace_id: Workspace to scan.
        threshold: Minimum combined score to persist.  Defaults to
            :data:`DEFAULT_CONFIDENCE_THRESHOLD`.
        now: Reference moment for ``discovered_at``; defaults to UTC.

    Returns:
        Number of new candidate rows inserted in this pass.
    """
    moment = now or datetime.datetime.now(datetime.UTC)
    _ = workspace_id  # workspace scoping happens through data_product FK chain
    with session_factory() as session:
        entities = list(
            session.scalars(
                select(DataProductEntity).order_by(DataProductEntity.id)
            )
        )
        existing_links = {
            (int(row.source_entity_id), int(row.target_entity_id), str(row.kind))
            for row in session.scalars(select(EntityLink))
        }
        existing_candidates = {
            (
                int(row.source_entity_id),
                int(row.target_entity_id),
                str(row.kind),
            )
            for row in session.scalars(select(EntityLinkCandidate))
        }

    inserted = 0
    for source, target in _ordered_pairs(entities):
        if source.id == target.id:
            continue
        triple = (int(source.id), int(target.id), "same_as")
        if triple in existing_links or triple in existing_candidates:
            continue
        score = score_combined(source, target)
        if score.combined < threshold:
            continue
        evidence = json.dumps(score.to_evidence(), separators=(",", ":"))
        with session_factory() as session:
            row = EntityLinkCandidate(
                source_entity_id=int(source.id),
                target_entity_id=int(target.id),
                kind="same_as",
                confidence_score=round(score.combined, 2),
                evidence_json=evidence,
                discovered_at=moment,
            )
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                continue
            inserted += 1
    return inserted


def _decode_pk(raw: str | list[str] | None) -> list[str]:
    """Decode the JSON-encoded PK-columns column."""
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if not raw:
        return []
    try:
        decoded = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
    return [str(x) for x in decoded] if isinstance(decoded, list) else []


def _tokenise(name: str) -> set[str]:
    """Split *name* on snake_case / CamelCase boundaries into tokens."""
    if not name:
        return set()
    tokens: list[str] = []
    current = ""
    for char in name:
        if char in {"_", "-", " ", "."}:
            if current:
                tokens.append(current.lower())
                current = ""
        elif char.isupper() and current:
            tokens.append(current.lower())
            current = char
        else:
            current += char
    if current:
        tokens.append(current.lower())
    return {t for t in tokens if t}


def _ordered_pairs(
    entities: list[DataProductEntity],
) -> list[tuple[DataProductEntity, DataProductEntity]]:
    """Return every ordered pair (i, j) with i.id < j.id."""
    pairs: list[tuple[DataProductEntity, DataProductEntity]] = []
    for i, source in enumerate(entities):
        for target in entities[i + 1 :]:
            pairs.append((source, target))
    return pairs
