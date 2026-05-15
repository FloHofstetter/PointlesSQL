"""Auto-generated data-product passport rows (Phase 73.4).

Markdown briefing built from the lineage graph + freshness
profile.  Distinct from :class:`EntityReadme`: the
passport is *system-authored*; readme is *steward-authored*.
The DP detail page renders both stacked on the README tab.

The passport refreshes on
``EVENT_TYPE_DATA_PRODUCT_SCHEMA_CHANGED`` (and via the
periodic ``_data_product_passport_loop``).  Each refresh
inserts a new row with a monotonic ``version_int`` per
``(workspace, dp)`` — no in-place UPDATEs so the history
stays auditable.
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
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

PASSPORT_TRIGGERS: tuple[str, ...] = ("schema_changed", "manual", "periodic")


class DataProductPassport(Base):
    """One versioned auto-generated passport.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Tenant scope.
        data_product_id: FK on ``data_products.id`` with
            ``ondelete='CASCADE'``.
        version_int: Monotonic per ``(workspace, dp)``.
        body_md: The rendered markdown briefing.
        source_tables_json: Serialised list of upstream
            ``"catalog.schema.table"`` values pulled from
            ``lineage_column_map``.
        downstream_tables_json: Serialised list of downstream
            tables.
        column_count: Total column edges contributing to the
            DAG snapshot.
        edge_count: Total directed edges (rows in
            ``lineage_column_map``).
        refreshed_at: Wall-clock at insert.
        refresh_trigger: One of :data:`PASSPORT_TRIGGERS`.
            CHECK at DB.
    """

    __tablename__ = "data_product_passports"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "data_product_id",
            "version_int",
            name="uq_dp_passport_version",
        ),
        Index(
            "ix_dp_passport_dp_v",
            "data_product_id",
            "version_int",
        ),
        CheckConstraint(
            "refresh_trigger IN ('schema_changed', 'manual', 'periodic')",
            name="ck_dp_passport_trigger",
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
    version_int: Mapped[int] = mapped_column(Integer, nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    source_tables_json: Mapped[str] = mapped_column(Text, nullable=False)
    downstream_tables_json: Mapped[str] = mapped_column(Text, nullable=False)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False)
    edge_count: Mapped[int] = mapped_column(Integer, nullable=False)
    refreshed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    refresh_trigger: Mapped[str] = mapped_column(String(20), nullable=False)
