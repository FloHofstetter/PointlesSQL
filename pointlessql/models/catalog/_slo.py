"""Declared service-level objectives (SLOs) of a data product.

One table, ``data_product_slos``, that lets a product declare the full
SLO set the Data-Mesh literature calls for — not just freshness.  Each
row is one objective: a kind, a numeric target, a comparator, and an
optional unit, scoped either to a single table or to the whole product.

The platform *measures* the objectives that are derivable from data it
already holds — freshness (Delta commit age), volume (row count),
completeness (null ratio), statistical-shape drift (the self-generated
statistics history), and lineage coverage (declared input ports) — and
honestly leaves the rest (precision/accuracy, availability, performance)
as declarations surfaced in the discovery contract.  ``sla_minutes`` on
:class:`DataProduct` stays the canonical *freshness* objective; this
table carries the additional kinds without duplicating it.

Storage decision: PointlesSQL metadata DB.  Edited via the steward/admin
API + agent plugin tools, mirroring ports/classifications — agents
propose, owners approve.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

#: Every SLO kind a product can declare, following Dehghani's set.  The
#: first five are the ones the platform actually measures (see
#: :data:`MEASURABLE_SLO_KINDS`); the rest are honest declarations the
#: discovery contract advertises but a single-node app cannot verify.
SLO_KINDS: tuple[str, ...] = (
    "freshness",
    "timeliness",
    "completeness",
    "volume",
    "statistical_shape",
    "lineage",
    "precision_accuracy",
    "availability",
    "performance",
    "interval_of_change",
)

#: The subset of :data:`SLO_KINDS` the SLO evaluator can compute a
#: verdict for from data the platform already holds.  Kinds outside this
#: set evaluate to ``"unmeasured"``.
MEASURABLE_SLO_KINDS: tuple[str, ...] = (
    "freshness",
    "completeness",
    "volume",
    "statistical_shape",
    "lineage",
    "interval_of_change",
)

#: How an observed value is compared against the declared target.
#: ``lte`` (observed ≤ target) suits freshness/drift; ``gte`` suits
#: completeness/volume floors; ``eq`` is an exact-match expectation.
SLO_COMPARATORS: tuple[str, ...] = ("lte", "gte", "eq")


class DataProductSLO(Base):
    """One declared service-level objective for a data product.

    A product may declare several objectives (e.g. a volume floor plus
    a completeness floor plus a drift ceiling), so this is a
    one-to-many table.  A ``NULL`` ``table_name`` makes the objective
    product-wide; a set ``table_name`` scopes it to one table.

    Attributes:
        id: Auto-incremented primary key.
        data_product_id: FK on ``data_products.id`` with CASCADE
            delete.
        table_name: UC table the objective applies to, or ``None`` for
            a product-wide objective.
        slo_kind: One of :data:`SLO_KINDS`.
        target_value: The numeric target the observed value is compared
            against; ``None`` for declaration-only kinds with no
            threshold.
        comparator: One of :data:`SLO_COMPARATORS` — how observed is
            compared to target.
        unit: Optional human unit label (e.g. ``minutes``, ``rows``,
            ``percent``, ``sigma``); ``None`` when self-evident.
        enabled: Whether the evaluator considers this objective.
        created_by_user_id: Nullable FK on ``users.id``.
        created_at: Wall-clock the objective was declared.
        last_measured_at: Wall-clock of the latest evaluator run that
            measured this objective, or ``None`` before the first run.
        last_measurement_detail_json: JSON payload of the latest
            measurement (observed value, verdict, inputs), or ``None``.
    """

    __tablename__ = "data_product_slos"

    __table_args__ = (
        UniqueConstraint(
            "data_product_id",
            "table_name",
            "slo_kind",
            name="uq_dp_slos_identity",
        ),
        Index("ix_dp_slos_product", "data_product_id"),
        CheckConstraint(
            "slo_kind IN ('freshness','timeliness','completeness','volume',"
            "'statistical_shape','lineage','precision_accuracy','availability',"
            "'performance','interval_of_change')",
            name="ck_dp_slos_kind",
        ),
        CheckConstraint(
            "comparator IN ('lte','gte','eq')",
            name="ck_dp_slos_comparator",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    table_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    slo_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    target_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    comparator: Mapped[str] = mapped_column(
        String(4), nullable=False, default="lte", server_default="lte"
    )
    unit: Mapped[str | None] = mapped_column(String(24), nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_measured_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_measurement_detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
