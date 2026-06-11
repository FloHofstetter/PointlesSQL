"""AI/BI dashboards — widget canvases over saved queries and SQL.

Two tables for the Lakeview-style BI surface (distinct from
``dashboards``, which publishes notebook-job output):

* ``bi_dashboards`` — one canvas per row: slug-addressable, owned,
  workspace-scoped, with dashboard-level parameters and an optional
  public-share token.
* ``bi_dashboard_widgets`` — one widget per row: a chart / counter /
  table backed by inline SQL or a saved query, or a markdown block.
  ``position`` carries the gridstack rectangle, ``chart_spec`` the
  ECharts encoding; both are JSON strings interpreted client-side
  so widget look-and-feel iterates without migrations.

Visibility mirrors the notebook-dashboard surface: every logged-in
workspace user can view, owner + admins mutate.  A published
dashboard is additionally reachable unauthenticated under its
``public_token``; its widget queries then execute as the owner
(embedded-credentials model), which is why publishing is owner-only
and revocable.
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
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

BI_WIDGET_KINDS: tuple[str, ...] = ("chart", "counter", "table", "markdown")
"""Widget renderers the view page knows how to draw."""


class BiDashboard(Base):
    """One BI dashboard canvas.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: FK to ``workspaces.id``; hard isolation
            boundary like every other metadata row.
        slug: URL-visible identifier, unique across all rows
            (mirrors ``saved_queries.slug`` semantics).
        title: Human-readable name.
        description: Optional free-form description.
        owner_id: FK to ``users.id`` — the creator; mutations are
            owner + admin only.
        params: JSON-encoded list of dashboard-level parameters
            (``{"name", "label", "type": "string"|"number"|"date",
            "default"}``).  Widget SQL references them as
            ``{{name}}``; substitution happens server-side with
            type-checked literal escaping.
        public_token: Random URL token; non-``NULL`` means the
            dashboard is published and reachable unauthenticated
            under ``/bi/public/{token}`` with widget queries running
            as the owner.
        created_at: Timestamp when the dashboard was created.
        updated_at: Timestamp of the most recent mutation.
    """

    __tablename__ = "bi_dashboards"

    __table_args__ = (
        Index("ix_bi_dashboards_workspace", "workspace_id"),
        Index("ix_bi_dashboards_owner", "owner_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    params: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    public_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BiDashboardWidget(Base):
    """One widget on one BI dashboard.

    Exactly one data source applies per kind: ``markdown`` widgets
    carry ``markdown`` text, the data-backed kinds carry either
    inline ``sql_text`` or a ``saved_query_id`` reference (the
    referenced query runs regardless of its ``is_shared`` flag —
    embedding it in a dashboard is the owner's publishing decision).

    Attributes:
        id: Auto-incremented primary key.
        dashboard_id: FK to :class:`BiDashboard` with ``ON DELETE
            CASCADE`` — widgets follow their canvas.
        kind: One of :data:`BI_WIDGET_KINDS`.
        title: Optional widget header.
        sql_text: Inline SQL (single SELECT) for data-backed kinds.
        saved_query_id: FK to ``saved_queries.id`` with ``ON DELETE
            SET NULL`` — alternative to ``sql_text``; the widget
            renders an unbound state when the query is deleted.
        markdown: Markdown body for ``markdown`` widgets.
        chart_spec: JSON-encoded ECharts encoding (chart type, x/y
            field names, series, value/format options).  Interpreted
            client-side.
        position: JSON-encoded gridstack rectangle
            (``{"x", "y", "w", "h"}``).
        created_at: Timestamp when the widget was added.
        updated_at: Timestamp of the most recent mutation.
    """

    __tablename__ = "bi_dashboard_widgets"

    __table_args__ = (
        Index("ix_bi_dashboard_widgets_dashboard", "dashboard_id"),
        CheckConstraint(
            "kind IN ('chart', 'counter', 'table', 'markdown')",
            name="ck_bi_dashboard_widgets_kind",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dashboard_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("bi_dashboards.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sql_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    saved_query_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("saved_queries.id", ondelete="SET NULL"),
        nullable=True,
    )
    markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    chart_spec: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")
    position: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default='{"x": 0, "y": 0, "w": 6, "h": 4}',
        server_default='{"x": 0, "y": 0, "w": 6, "h": 4}',
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
