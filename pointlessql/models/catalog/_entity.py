"""Polysemic entity-ID + cross-product entity links.

Three concepts:

* :class:`DataProductEntity` — one row per business concept owned by a
  data product (``Customer``, ``Order``).  Carries the primary-key
  column tuple it lives on, so cross-product joins can be planned
  without column-name conventions.
* :class:`EntityLink` — declares a relation between two entities.
  ``same_as`` realises polysemic identity (one logical entity, many
  data products); ``derives_from`` records ETL provenance at the
  entity level; ``related_to`` is the catch-all weak link.
* The optional ``confidence`` column lets future auto-discovery jobs
  drop candidate links here with a score; manually declared links
  leave it null.

CASCADE on ``data_products.id`` for entities and on the entity FKs
for links keeps the graph consistent under deletes.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

ENTITY_LINK_KINDS: tuple[str, ...] = ("same_as", "derives_from", "related_to")


class DataProductEntity(Base):
    """One business concept owned by a data product.

    Attributes:
        id: Auto-incremented primary key.
        data_product_id: Owning data product.  FK on
            ``data_products.id`` with CASCADE delete.
        entity_name: Short label, unique inside the product (e.g.
            ``Customer``).
        source_table: Table inside the product the entity is sourced
            from.  Stored as a bare table name; the catalog/schema
            come from the product.
        primary_key_columns: JSON-encoded ordered list of column
            names that uniquely identify a row of this entity.
        description: Free-form prose, nullable.
        created_by_user_id: Author of the declaration, nullable FK on
            ``users.id``.
        created_at: Wall-clock the entity was declared.
        updated_at: Wall-clock of the last update.
    """

    __tablename__ = "data_product_entities"

    __table_args__ = (
        UniqueConstraint(
            "data_product_id", "entity_name",
            name="uq_dp_entities_identity",
        ),
        Index("ix_dp_entities_product", "data_product_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_name: Mapped[str] = mapped_column(String(80), nullable=False)
    source_table: Mapped[str] = mapped_column(String(200), nullable=False)
    primary_key_columns: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class EntityLink(Base):
    """Directed link from one entity to another.

    Attributes:
        id: Auto-incremented primary key.
        source_entity_id: FK on ``data_product_entities.id`` with
            CASCADE delete.
        target_entity_id: FK on ``data_product_entities.id`` with
            CASCADE delete.
        kind: One of :data:`ENTITY_LINK_KINDS`.
        confidence: Optional auto-discovery score in [0, 1];
            null for manually declared links.
        declared_by_user_id: Author of the declaration, nullable FK
            on ``users.id``.  Auto-discovery jobs leave it null.
        created_at: Wall-clock the link was created.
    """

    __tablename__ = "entity_links"

    __table_args__ = (
        UniqueConstraint(
            "source_entity_id", "target_entity_id", "kind",
            name="uq_entity_links_identity",
        ),
        CheckConstraint(
            "kind IN ('same_as','derives_from','related_to')",
            name="ck_entity_links_kind",
        ),
        Index("ix_entity_links_source", "source_entity_id"),
        Index("ix_entity_links_target", "target_entity_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_entity_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_product_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_entity_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_product_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    declared_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
