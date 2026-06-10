"""Self-service access requests for a data product.

A consumer who lacks ``SELECT`` on a product's tables files a request;
the product steward (or an admin) approves it, at which point the app
grants ``SELECT`` through the soyuz client — PointlesSQL never writes
lakehouse permissions directly, only this own-metadata request ledger.

Status is a small state machine: ``pending`` → ``approved`` / ``denied``
(both terminal).  The partial unique index keeps a consumer from
stacking duplicate open requests on the same product while one is still
pending; a decided request is exempt so they can re-request later.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

ACCESS_REQUEST_STATUSES: tuple[str, ...] = ("pending", "approved", "denied")


class DataProductAccessRequest(Base):
    """One consumer's request for SELECT access to a data product.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Tenant scope.
        data_product_id: FK on ``data_products.id`` (``CASCADE``).
        requester_user_id: The consumer asking for access.
        status: One of :data:`ACCESS_REQUEST_STATUSES`.
        request_note: Optional free-form justification from the
            requester.
        created_at: Wall-clock at request time.
        decided_at: Wall-clock when a steward approved / denied;
            ``None`` while pending.
        decided_by_user_id: The steward / admin who decided; ``None``
            while pending.
        decision_reason: Optional note carried on a denial (or an
            approval).
    """

    __tablename__ = "data_product_access_requests"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'denied')",
            name="ck_dp_access_request_status",
        ),
        # One open request per (product, requester) — a decided request
        # is exempt so a consumer can ask again after a denial.
        Index(
            "uq_dp_access_request_open",
            "data_product_id",
            "requester_user_id",
            unique=True,
            sqlite_where=text("status = 'pending'"),
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "ix_dp_access_request_ws_status",
            "workspace_id",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        server_default="1",
    )
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    requester_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    request_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decided_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
