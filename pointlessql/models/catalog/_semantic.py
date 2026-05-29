"""Per-product semantic model — the "understandable" affordance.

One table, ``data_product_semantic_concepts``, that lets a product
declare the business *concepts* it represents and bind each to a
concrete column.  This is the product-local semantic layer: a
consumer reading the discovery contract sees "this product is about
Orders / Customers" with each concept pointing at the column that
realises it, rather than having to infer meaning from column names.

The product's example query (``sample_sql``) lives as a column on
``data_products`` rather than here, because it is a single value per
product, not a list.

Storage decision: PointlesSQL metadata DB, edited via the
steward/admin API + agent plugin tools (agents propose, owners
approve), so concepts reference the product by ``data_product_id`` FK
and cascade on product delete.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
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


class DataProductSemanticConcept(Base):
    """One business concept a product declares, optionally column-bound.

    Attributes:
        id: Auto-incremented primary key.
        data_product_id: FK on ``data_products.id`` with CASCADE
            delete.
        concept: Business-entity label (e.g. "Order", "Customer"),
            unique per product.
        description: Free-form note on what the concept means.
        maps_to: Fully-qualified ``catalog.schema.table.column`` the
            concept is realised by; ``None`` when the concept spans
            the product rather than a single column.
        created_at: Wall-clock the concept was declared.
    """

    __tablename__ = "data_product_semantic_concepts"

    __table_args__ = (
        UniqueConstraint("data_product_id", "concept", name="uq_dp_semantic_concept"),
        Index("ix_dp_semantic_product", "data_product_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    concept: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    maps_to: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
