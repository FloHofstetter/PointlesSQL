"""Self-service access requests for catalog securables.

A user who lacks a privilege (typically ``SELECT``) on a table files
a request; the table owner (or an admin) approves it, at which point
the app issues the real grant through the soyuz client — PointlesSQL
never writes lakehouse permissions directly, only this own-metadata
request ledger.

Status is a small state machine: ``pending`` → ``approved`` /
``denied`` (decided by the owner or an admin) or ``cancelled``
(withdrawn by the requester).  All three outcomes are terminal; a
denied or cancelled request does not block re-requesting later
because the duplicate guard only looks at ``pending`` rows.

The owner's e-mail is snapshotted at request time so the decider
inbox stays stable even when the table changes hands afterwards —
the decision right follows the snapshot, mirroring how the request
was routed when it was filed.
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

ACCESS_REQUEST_STATUSES: tuple[str, ...] = (
    "pending",
    "approved",
    "denied",
    "cancelled",
)
"""Lifecycle of one access request (only ``pending`` is non-terminal)."""


class AccessRequest(Base):
    """One user's request for privileges on a catalog securable.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: FK to ``workspaces.id``; requests are
            workspace-scoped like the rest of the metadata DB.
        securable_type: Kind of securable the request targets
            (``table`` for now; the column keeps the door open for
            schemas / catalogs without a schema change).
        full_name: Dotted UC name of the securable.
        requester_user_id: FK to ``users.id`` — who asked.
        requester_email: E-mail snapshot of the requester, used as
            the grant principal on approval.
        owner_email_snapshot: Owner of the securable at request
            time; drives the decider inbox.
        privileges: JSON list of requested privilege strings
            (e.g. ``["SELECT"]``).
        justification: Optional free-form reason from the requester.
        status: One of :data:`ACCESS_REQUEST_STATUSES`.
        decided_by_user_id: FK to ``users.id`` of the decider;
            ``None`` while pending or after a requester cancel.
        decision_note: Optional note carried on the decision
            (required for denials at the service layer).
        created_at: Wall-clock at request time.
        decided_at: Wall-clock of the terminal transition; ``None``
            while pending.
    """

    __tablename__ = "access_requests"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'denied', 'cancelled')",
            name="ck_access_requests_status",
        ),
        Index("ix_access_requests_workspace_status", "workspace_id", "status"),
        Index("ix_access_requests_full_name_status", "full_name", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        server_default="1",
    )
    securable_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="table", server_default="table"
    )
    full_name: Mapped[str] = mapped_column(String(256), nullable=False)
    requester_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    requester_email: Mapped[str] = mapped_column(String(254), nullable=False)
    owner_email_snapshot: Mapped[str] = mapped_column(
        String(254), nullable=False, default="", server_default=""
    )
    privileges: Mapped[str] = mapped_column(
        Text, nullable=False, default='["SELECT"]', server_default='["SELECT"]'
    )
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    decided_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
