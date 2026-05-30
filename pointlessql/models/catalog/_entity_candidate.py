"""Auto-discovery entity-link candidates + steward review queue.

The discovery scheduler emits one row per pair of entities whose
combined confidence score exceeds the configured threshold; the
steward UI consumes the pending rows, calls ``accept`` (promotes to
``entity_links``), ``reject`` (decision='rejected') or ``defer``
(decision='deferred').  The UNIQUE constraint on (source, target,
kind) keeps successive ticks from generating duplicate work.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

#: Decision values the steward UI may set.  NULL stays "pending".
CANDIDATE_DECISIONS: tuple[str, ...] = ("accepted", "rejected", "deferred")


class EntityLinkCandidate(Base):
    """One discovered (source, target, kind) candidate.

    Attributes:
        id: Auto-incremented primary key.
        source_entity_id: FK on ``data_product_entities.id`` with
            CASCADE.
        target_entity_id: FK on ``data_product_entities.id`` with
            CASCADE.  Pairs are stored ordered (source.id <
            target.id) so the UNIQUE constraint really enforces
            "one candidate per pair".
        kind: ``same_as`` or ``derives_from`` (CHECK-bounded).
        confidence_score: Numeric(3,2) carrying 0.00..0.99.
        evidence_json: JSON-encoded scorer breakdown
            (per-feature contributions).
        discovered_at: Wall-clock the candidate was first detected.
        reviewed_at: Wall-clock of the steward decision; NULL until
            decided.
        reviewed_by_user_id: Steward who decided; NULL until decided.
        decision: One of :data:`CANDIDATE_DECISIONS` or NULL
            (pending).
    """

    __tablename__ = "entity_link_candidates"

    __table_args__ = (
        CheckConstraint(
            "kind IN ('same_as','derives_from')",
            name="ck_entity_link_candidates_kind",
        ),
        CheckConstraint(
            "decision IS NULL OR decision IN ('accepted','rejected','deferred')",
            name="ck_entity_link_candidates_decision",
        ),
        UniqueConstraint(
            "source_entity_id",
            "target_entity_id",
            "kind",
            name="uq_entity_link_candidates_triple",
        ),
        Index(
            "ix_entity_link_candidates_pending",
            "decision",
            "confidence_score",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_entity_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_product_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_entity_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_product_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence_score: Mapped[Decimal] = mapped_column(
        Numeric(precision=3, scale=2), nullable=False
    )
    evidence_json: Mapped[str] = mapped_column(Text(), nullable=False)
    discovered_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
