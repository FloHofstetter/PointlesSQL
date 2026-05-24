"""Cached trending rank per data product.

One row per ``(workspace_id, data_product_id, window_end)``.
A periodic loop (``_data_product_trending_loop``) UPSERTs the
top-N rows per workspace every ``trending_refresh_interval_seconds``;
the ``/api/data-products/trending`` page reads from this table
without recomputing the joins inline (which would scan all of
``agent_run_operations`` on every request).
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class DataProductTrending(Base):
    """One cached "trending"-rank row.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Tenant scope.
        data_product_id: FK on ``data_products.id`` with
            ``ondelete='CASCADE'``.
        window_start: Lower bound of the rolling window (inclusive).
        window_end: Upper bound (exclusive).  UNIQUE per
            ``(workspace_id, data_product_id, window_end)``.
        agent_run_count: Distinct ``agent_run_id`` values in
            ``agent_run_operations`` whose ``target_table`` matched
            the DP prefix within the window.
        write_count: Total ``agent_run_operations`` rows in the
            same window (regardless of distinct runs).
        rank: 1-N per ``(workspace_id, window_end)``, sorted by
            ``agent_run_count`` desc + tie-break ``write_count``
            desc.
        refreshed_at: Wall-clock when this row was UPSERTed.
    """

    __tablename__ = "data_product_trending"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "data_product_id",
            "window_end",
            name="uq_dp_trending_window",
        ),
        Index(
            "ix_dp_trending_workspace_window",
            "workspace_id",
            "window_end",
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
    window_start: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    agent_run_count: Mapped[int] = mapped_column(Integer, nullable=False)
    write_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    refreshed_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
