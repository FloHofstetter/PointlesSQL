"""Per-product infrastructure declaration.

Steward-edited 1:1 row per product describing storage class, compute
runtime, declared access methods, region, and freeform notes.  Pure
metadata — no enforcement; surfaced in the discovery envelope so a
consumer of the URI can answer "where does this product live?".
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

#: Allowed values for :attr:`DataProductInfrastructure.storage_class`.
INFRASTRUCTURE_STORAGE_CLASSES: tuple[str, ...] = (
    "delta",
    "parquet",
    "external",
)


class DataProductInfrastructure(Base):
    """Producer-declared infrastructure topology for one product.

    Attributes:
        id: Auto-incremented primary key.
        data_product_id: FK on ``data_products.id`` with CASCADE
            delete; unique.
        storage_class: One of :data:`INFRASTRUCTURE_STORAGE_CLASSES`,
            or ``None`` when undeclared.
        compute_runtime: Free-form runtime identifier (e.g. ``"pql"``,
            ``"spark"``, ``"dbt"``).
        access_methods_json: JSON array of declared access methods,
            ``["sql","file","event"]``-style.
        region: Free-form geo identifier (e.g. ``"eu-central"``).
        notes: Free-form note.
        updated_by_user_id: Nullable FK on ``users.id``.
        created_at: Wall-clock the row was first inserted.
        updated_at: Wall-clock of the last edit.
    """

    __tablename__ = "data_product_infrastructure"

    __table_args__ = (
        UniqueConstraint("data_product_id", name="uq_dp_infrastructure_product"),
        CheckConstraint(
            "storage_class IS NULL OR storage_class IN ('delta','parquet','external')",
            name="ck_dp_infrastructure_storage_class",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    storage_class: Mapped[str | None] = mapped_column(String(32), nullable=True)
    compute_runtime: Mapped[str | None] = mapped_column(String(64), nullable=True)
    access_methods_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    region: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
