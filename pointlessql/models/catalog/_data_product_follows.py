"""Follow / subscribe rows per data product (Phase 71.3).

One table:

* ``data_product_follows`` — composite-PK row per ``(workspace_id,
  data_product_id, user_id)`` triple.  The composite PK enforces
  idempotency at the DB layer so a POST endpoint can blindly
  insert; subsequent inserts no-op without an integrity error in
  the application path (we let SQLAlchemy handle the round-trip).

No soft-delete: a DELETE drops the row outright.  Audit-trail
coverage of follow events is handled by the Phase-71.4
notification fan-out and the Phase-20 audit-stream forwarder.
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class DataProductFollow(Base):
    """One user-follows-product link.

    Attributes:
        workspace_id: PK part 1 + tenant scope.
        data_product_id: PK part 2.  ``ondelete='CASCADE'`` keeps
            the table tidy when a yaml is deleted.
        user_id: PK part 3.  ``ondelete='CASCADE'`` keeps the
            table tidy when a user is removed.
        created_at: Wall-clock when the follow link was created.
    """

    __tablename__ = "data_product_follows"

    __table_args__ = (
        Index("ix_dp_follows_user", "user_id", "created_at"),
        Index(
            "ix_data_product_follows_social_target",
            "social_target_id",
        ),
    )

    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        primary_key=True,
        server_default="1",
    )
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Phase 77.0.B — polymorphic anchor (see _data_product_comments.py).
    social_target_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("social_targets.id"),
        nullable=False,
    )
