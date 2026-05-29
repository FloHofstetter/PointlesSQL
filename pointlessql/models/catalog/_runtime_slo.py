"""Runtime-SLO sample tables.

Two tables that back the availability + performance measurers.  The
availability table records probe outcomes; the perf-samples table
records SELECT-duration outcomes.  The perf-samples table is the
substrate the cost-attribution surface later extends with cost
columns.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

AVAILABILITY_STATUSES: tuple[str, ...] = ("ok", "fail", "timeout", "error")
PERF_STATUSES: tuple[str, ...] = ("ok", "fail", "timeout")


class DataProductAvailabilityProbe(Base):
    """One scheduled availability probe outcome."""

    __tablename__ = "data_product_availability_probes"

    __table_args__ = (
        CheckConstraint(
            "status IN ('ok','fail','timeout','error')",
            name="ck_dp_availability_probes_status",
        ),
        Index(
            "ix_dp_availability_probes_product",
            "data_product_id", "probed_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    output_port_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    port_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    probed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(8), nullable=False)


class DataProductQueryPerfSample(Base):
    """One SELECT-duration outcome (also feeds phase 146 cost-rollup)."""

    __tablename__ = "data_product_query_perf_samples"

    __table_args__ = (
        CheckConstraint(
            "status IN ('ok','fail','timeout')",
            name="ck_dp_query_perf_status",
        ),
        Index(
            "ix_dp_query_perf_product",
            "data_product_id", "started_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_product_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=True,
    )
    table_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False)
