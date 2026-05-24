"""SavedView model for non-tech read-only DP consumption.

A saved view is parameterised, SELECT-only SQL that a consumer can
run without touching the SQL editor.  Title + description + a
declared list of parameters surface as a friendly form in the UI;
the underlying SQL stays hidden by default.

Unlike :class:`~pointlessql.models.SavedQuery` (user-owned scratch
pads, owner+shared visibility), a SavedView is **workspace-public
by default** — every workspace member sees it on the views index
and on any DP / table page it scopes to.  Only the owner and
workspace admins may edit or delete.

``parameters_json`` carries an ordered list of
``{name, label, type, default, required}`` dicts.  ``type`` is one
of ``string`` / ``integer`` / ``number`` / ``date`` / ``boolean``.
At run-time every ``${name}`` placeholder in ``sql_text`` is
rewritten to a positional ``?`` and the values are bound via
DuckDB's prepared-statement API — no string interpolation.
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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

# Parameter types accepted in ``parameters_json``.  Anything else is
# rejected at create / update time.
SAVED_VIEW_PARAM_TYPES: tuple[str, ...] = (
    "string",
    "integer",
    "number",
    "date",
    "boolean",
)


class SavedView(Base):
    """A parameterised, SELECT-only view a consumer can run on demand.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: FK to ``workspaces.id``.  Workspace-scoped.
        owner_id: FK to ``users.id``.  Only owner + admin may mutate.
        slug: URL-safe identifier, unique across all rows.  Generated
            from ``slugify(title) + "-" + short-random``.
        title: Human-readable name shown on lists and headers.
        description: Optional free-form blurb.
        sql_text: The verbatim SELECT, with ``${name}`` placeholders
            for every parameter declared in :attr:`parameters_json`.
        parameters_json: JSON-encoded list of parameter declarations
            ``[{name, label, type, default, required}, ...]``.
        dp_id: Optional FK to ``data_products.id``.  When set, the
            view shows up on that DP's "Views" tab; otherwise it
            lives only on the global ``/views`` index.
        target_fqn: Optional 3-part table FQN.  Mutually exclusive
            with :attr:`dp_id` in practice — pick one scope.
        is_active: When ``False`` the view is hidden from indexes
            but the URL still resolves (lets owners "archive"
            without breaking deep links).
        created_at: Timestamp when the row was first persisted.
        updated_at: Timestamp of the most recent mutation.
    """

    __tablename__ = "saved_views"

    __table_args__ = (
        UniqueConstraint("slug", name="uq_saved_views_slug"),
        Index("ix_saved_views_workspace_active", "workspace_id", "is_active"),
        Index("ix_saved_views_dp", "dp_id"),
        Index("ix_saved_views_target_fqn", "target_fqn"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False
    )
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    parameters_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    dp_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("data_products.id"), nullable=True
    )
    target_fqn: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
