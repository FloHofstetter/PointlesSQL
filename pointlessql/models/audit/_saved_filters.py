"""User-named filter combos for the admin audit-log viewer.

One row per saved filter the user names ("DP creates last week",
"my SQL ops", …).  ``filters_json`` carries a structured payload so
the table doesn't grow a column per future filter dimension; the
admin-audit route deserialises it back into the same filter
arguments the URL would carry.

Owner-private by default; flipping ``is_shared_workspace`` to True
+ setting ``workspace_id`` exposes the filter to every admin in
that workspace.
"""

from __future__ import annotations

import datetime

import sqlalchemy as sa
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


class AuditSavedFilter(Base):
    """One named filter combo for the admin audit cockpit."""

    __tablename__ = "audit_saved_filters"

    __table_args__ = (
        UniqueConstraint("owner_user_id", "name", name="uq_audit_saved_filters_owner_name"),
        Index(
            "ix_audit_saved_filters_workspace_shared",
            "workspace_id",
            "is_shared_workspace",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "users.id",
            name="fk_audit_saved_filters_owner",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    filters_json: Mapped[str] = mapped_column(Text, nullable=False)
    is_shared_workspace: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.false()
    )
    workspace_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "workspaces.id",
            name="fk_audit_saved_filters_workspace",
            ondelete="CASCADE",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


__all__ = ["AuditSavedFilter"]
