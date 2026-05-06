"""Saved audit queries — admin-scoped SQL bookmarks for the cockpit.

separate from :class:`SavedQuery` because:

* visibility is admin-only, not the owner-+-shared model the SQL
  editor uses;
* a starter set ships with the migration (compliance-shaped
  queries every install benefits from);
* the runner enforces a table allow-list scoped to the audit
  surface so a typo can't read the lakehouse.

Five starter rows seed at upgrade time:

* ``pii_writes_last_90d``
* ``rollbacks_last_quarter``
* ``cost_gate_denials_this_week``
* ``unacknowledged_external_writes``
* ``top_mutating_principals_30d``

The :attr:`is_starter` flag prevents PATCH/DELETE on those rows
so an upgrade keeps the canonical examples stable.
``alert_threshold_count`` plugs into 's saved-query
alert mechanism: when a scheduled run of the query returns more
rows than this number, an alert fires through the existing
``/api/alerts`` machinery.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class SavedAuditQuery(Base):
    """One named audit-cockpit SQL snippet.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: FK to :class:`Workspace`.  Workspace-scoped
            audit-cockpit bookmarks.  Starter rows seed in
            workspace=1.
        slug: URL-visible identifier, unique across all rows.
        title: Human-readable name.
        description: Optional explanation of what the query
            answers + how to read the result.
        sql_text: Verbatim SQL.  Validated at run time against
            the audit-table allow-list; not at insert time, so
            broken starter rows surface immediately on first run
            instead of blocking ``alembic upgrade``.
        owner_id: FK to ``users.id`` for non-starter rows; ``NULL``
            on starter rows so the row survives any user deletion.
        is_shared: Always ``True`` in practice (the surface is
            admin-only anyway), kept for parity with
            :class:`SavedQuery`.
        is_starter: ``True`` for shipped-with-the-app rows; PATCH
            and DELETE refuse on those.
        alert_threshold_count: when set and a
            scheduled run returns more rows than this number, the
            alert dispatcher fires.  ``None`` disables alerting.
        created_at: Insert timestamp.
        updated_at: Last mutation timestamp.
    """

    __tablename__ = "saved_audit_queries"

    __table_args__ = (
        Index("ix_saved_audit_queries_owner_updated", "owner_id", "updated_at"),
        Index("ix_saved_audit_queries_starter", "is_starter"),
        Index("ix_saved_audit_queries_workspace", "workspace_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Workspace-scoped audit-cockpit bookmarks.  Starter rows seed in
    # workspace=1; future workspaces start with an empty set their
    # admin can populate (or copy from default).
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_starter: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    alert_threshold_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
