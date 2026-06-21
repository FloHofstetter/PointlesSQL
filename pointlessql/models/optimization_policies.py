"""Predictive-optimization maintenance policies.

Databricks' Predictive Optimization autonomously maintains Unity-Catalog
managed tables (OPTIMIZE / compaction, VACUUM, ANALYZE).  PointlesSQL
owns the *control* side: a per-catalog / schema / table policy declaring
which maintenance operations should run, resolved most-specific-first so
one catalog-wide rule governs every table beneath it without per-table
config.  The engine that runs the compaction is the existing PQL /
deltalake path; these rows only say what should be maintained.

One row per scope in our own metadata DB.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

OPTIMIZATION_SCOPE_TYPES: tuple[str, ...] = ("catalog", "schema", "table")
"""Securable scopes a maintenance policy can attach to.

A ``table`` policy beats a ``schema`` policy beats a ``catalog`` policy
for the same table.  Mirrored to a CHECK constraint.
"""


class OptimizationPolicy(Base):
    """One predictive-optimization policy at a catalog / schema / table scope.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: FK to ``workspaces.id``; policies are
            workspace-scoped.
        scope_type: One of :data:`OPTIMIZATION_SCOPE_TYPES`.
        scope_value: The securable name — one part for ``catalog``
            (``"main"``), two for ``schema`` (``"main.sales"``), three
            for ``table`` (``"main.sales.orders"``).
        enabled: Master switch — when false the table is excluded from
            autonomous maintenance even if a broader scope enables it.
        optimize: Run OPTIMIZE / file compaction.
        vacuum: Run VACUUM to expire tombstoned files.
        analyze: Refresh table / column statistics (ANALYZE).
        vacuum_retention_hours: Optional VACUUM retention override.
        created_by: E-mail of the creating principal.
        created_at: Creation timestamp.
        updated_at: Timestamp of the most recent mutation.
    """

    __tablename__ = "optimization_policies"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "scope_type", "scope_value", name="uq_optimization_policies_scope"
        ),
        Index("ix_optimization_policies_workspace", "workspace_id"),
        CheckConstraint(
            "scope_type IN ('catalog', 'schema', 'table')",
            name="ck_optimization_policies_scope_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_value: Mapped[str] = mapped_column(String(768), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    optimize: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    vacuum: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    analyze: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    vacuum_retention_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(254), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
