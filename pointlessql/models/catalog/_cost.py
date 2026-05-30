"""Cost-attribution ledger + hourly rollup + quota-enforcement modes.

Two ledgers + one constant tuple:

* ``data_product_query_cost`` — raw per-query meter row.  Carries
  cost (Numeric), bytes/rows (BigInt), authoring + consumer
  attribution, error_class on failure.
* ``data_product_cost_buckets_hourly`` — hourly rollup the scheduler
  computes.  UNIQUE(hour, product, consumer) keeps re-runs
  idempotent.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
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

#: Quota enforcement modes.  Mirrors consumption_enforcement.
QUOTA_ENFORCEMENT_MODES: tuple[str, ...] = ("off", "warn", "strict")

#: Query kinds the meter tags rows with.  Free-form, but the cost
#: dashboard expects ``select`` to dominate; bumps require a UI tweak.
QUERY_KINDS: tuple[str, ...] = (
    "select",
    "preview",
    "export",
    "agent_select",
)


class DataProductQueryCost(Base):
    """One raw meter row per executed PQL read.

    Attributes:
        id: Auto-incremented primary key.
        started_at: Wall-clock the query started.
        completed_at: Wall-clock the query finished; NULL on error.
        duration_ms: Total runtime in milliseconds; NULL on error.
        estimated_cost: Cost-gate estimate at execution time.
        bytes_scanned: Optional bytes-scanned metric.
        rows_returned: Optional rows-returned metric.
        table_list_json: JSON-encoded list of UC ``catalog.schema.table``
            refs the query touched.
        principal_user_id: Consumer principal.
        api_key_id: API key when the call was bearer-auth.
        authoring_product_id: Product whose schema the read targeted.
        consumer_product_id: Optional product the caller represented.
        query_kind: One of :data:`QUERY_KINDS`.
        error_class: Non-empty when the query failed.
    """

    __tablename__ = "data_product_query_cost"

    __table_args__ = (
        Index("ix_dp_query_cost_started", "started_at"),
        Index(
            "ix_dp_query_cost_product",
            "authoring_product_id",
            "started_at",
        ),
        Index(
            "ix_dp_query_cost_consumer",
            "principal_user_id",
            "started_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=4),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    bytes_scanned: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    rows_returned: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    table_list_json: Mapped[str | None] = mapped_column(Text(), nullable=True)
    principal_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    api_key_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("api_keys.id"), nullable=True
    )
    authoring_product_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="SET NULL"),
        nullable=True,
    )
    consumer_product_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="SET NULL"),
        nullable=True,
    )
    query_kind: Mapped[str] = mapped_column(
        String(24), nullable=False, default="select", server_default="select"
    )
    error_class: Mapped[str | None] = mapped_column(String(64), nullable=True)


class DataProductCostBucketHourly(Base):
    """Hourly rollup of :class:`DataProductQueryCost` rows.

    Attributes:
        id: Auto-incremented primary key.
        bucket_hour: Hour boundary (minute=0, second=0).
        data_product_id: Product the bucket aggregates over.
        consumer_user_id: Consumer; NULL means "all consumers".
        query_count: Number of queries in the bucket.
        total_duration_ms: Sum of duration_ms in the bucket.
        total_estimated_cost: Sum of estimated_cost in the bucket.
        total_bytes_scanned: Sum of bytes_scanned in the bucket.
    """

    __tablename__ = "data_product_cost_buckets_hourly"

    __table_args__ = (
        UniqueConstraint(
            "bucket_hour",
            "data_product_id",
            "consumer_user_id",
            name="uq_dp_cost_buckets_hourly_triple",
        ),
        Index("ix_dp_cost_buckets_hour", "bucket_hour"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bucket_hour: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    consumer_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    query_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    total_duration_ms: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    total_estimated_cost: Mapped[Decimal] = mapped_column(
        Numeric(precision=14, scale=4),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    total_bytes_scanned: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
