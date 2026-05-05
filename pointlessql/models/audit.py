"""Append-only audit log."""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class AuditLog(Base):
    """Append-only log of user actions for accountability.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Workspace the action was performed in (Phase
            28.1b).  Resolved from request.state by
            :func:`audit.log_action` or supplied explicitly by
            non-HTTP callers (CLI / scheduler).  Pre-Phase-28 rows
            backfill to the seeded default workspace (id=1).
        user_id: ID of the user who performed the action (no FK so
            entries survive user deletion).
        user_email: Email snapshot at time of action.
        actor_role: Role of the actor at time of action
            (``admin`` / ``user`` / ``system``).
        action: Short verb describing the action (e.g. ``update_catalog``).
        target: Identifier of the affected resource (e.g. ``catalog:my_cat``).
        client_ip: IPv4/IPv6 address of the requesting client, or
            ``None`` for system-generated rows.
        detail: Optional JSON-encoded context (stored as ``Text`` so
            arbitrarily-sized structured payloads fit).
        created_at: Timestamp when the action occurred.
    """

    __tablename__ = "audit_log"

    __table_args__ = (
        Index("ix_audit_log_user_created", "user_id", "created_at"),
        Index("ix_audit_log_target_created", "target", "created_at"),
        Index("ix_audit_log_created", "created_at"),
        Index("ix_audit_log_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_email: Mapped[str] = mapped_column(String(254), nullable=False)
    actor_role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="user", server_default="user"
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    target: Mapped[str] = mapped_column(String(500), nullable=False)
    client_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
