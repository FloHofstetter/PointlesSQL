"""Per-product bitemporal-policy override.

One row per product (UNIQUE on ``data_product_id``).  Each field is
nullable; a ``NULL`` field inherits the workspace-level
:class:`pointlessql.config.BitemporalSettings` value.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

#: Allowed values for :attr:`DataProductBitemporalPolicy.enforcement`.
BITEMPORAL_ENFORCEMENT_MODES: tuple[str, ...] = ("off", "opt_in", "required")


class DataProductBitemporalPolicy(Base):
    """Per-product bitemporal-convention override.

    Attributes:
        id: Auto-incremented primary key.
        data_product_id: FK on ``data_products.id`` with CASCADE
            delete; unique.
        enforcement: Per-product override for the workspace
            :attr:`BitemporalSettings.enforcement` field; ``None``
            inherits the workspace value.  One of
            :data:`BITEMPORAL_ENFORCEMENT_MODES`.
        processing_time_column: Override column name; ``None``
            inherits.
        event_time_column: Override column name; ``None`` inherits.
        require_event_time: Override require flag; ``None`` inherits.
        updated_by_user_id: Nullable FK on ``users.id``.
        created_at: Wall-clock the row was first inserted.
        updated_at: Wall-clock of the last edit.
    """

    __tablename__ = "data_product_bitemporal_policy"

    __table_args__ = (
        UniqueConstraint("data_product_id", name="uq_dp_bitemporal_policy_product"),
        CheckConstraint(
            "enforcement IS NULL OR enforcement IN ('off','opt_in','required')",
            name="ck_dp_bitemporal_policy_enforcement",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    enforcement: Mapped[str | None] = mapped_column(String(16), nullable=True)
    processing_time_column: Mapped[str | None] = mapped_column(String(120), nullable=True)
    event_time_column: Mapped[str | None] = mapped_column(String(120), nullable=True)
    require_event_time: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
