"""Cross-DP co-occurrence cache rows.

One row per ``(workspace, dp, co_dp, window_end)``.  A
periodic loop walks ``agent_run_operations`` per
``agent_run_id``, projects ``target_table`` onto the
matching ``DataProduct`` row, and counts how often each pair
of DPs is touched by the same run within the rolling window.

The "Related products" card on the DP detail page reads this
table; the "Recommended for you" strip on
``/data-products/followed`` joins it with the caller's
follow set.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class DataProductCooccurrence(Base):
    """One directional pair count.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Tenant scope.
        data_product_id: Source DP id; FK on
            ``data_products.id`` with ``ondelete='CASCADE'``.
        co_data_product_id: Other DP id; same FK shape.
        cooccurrence_count: Distinct agent_run_id values that
            touched both DPs within the window.
        window_start: Lower bound of the rolling window.
        window_end: Upper bound; UNIQUE per
            ``(workspace, dp, co_dp, window_end)``.
        refreshed_at: Wall-clock at UPSERT.
    """

    __tablename__ = "data_product_cooccurrence"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "data_product_id",
            "co_data_product_id",
            "window_end",
            name="uq_dp_cooccurrence_pair",
        ),
        Index(
            "ix_dp_cooccurrence_ws_dp",
            "workspace_id",
            "data_product_id",
        ),
        CheckConstraint(
            "data_product_id != co_data_product_id",
            name="ck_dp_cooccurrence_distinct",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
        server_default="1",
    )
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    co_data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    cooccurrence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    window_start: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refreshed_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
