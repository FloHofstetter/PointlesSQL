"""Polysemic identity: shared business entities across data products.

Two tables that give the mesh a common identity vocabulary so columns
in *different* products can be recognised as the same real-world thing:

* ``mesh_entities`` — a named business entity (e.g. "Customer",
  "Order") declared once per workspace.  It is the polysemic
  identifier: a stable name that several products can point their
  columns at.
* ``mesh_entity_bindings`` — binds one entity to one UC column
  (``catalog.schema.table.column``) inside a product.  When two
  products each bind a column to the same entity, the platform can
  suggest a meaningful cross-product join key — the join helper reads
  these rows.

Storage decision: PointlesSQL metadata DB.  Edited via the steward/admin
API + agent plugin tools, mirroring the business glossary — agents
propose, owners approve.
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


class MeshEntity(Base):
    """A named business entity shared across the mesh.

    Declared once per workspace; it is the *polysemic identifier* that
    several products' columns can bind to so the platform understands
    they denote the same real-world thing.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Workspace this entity belongs to.  FK on
            ``workspaces.id``; ``server_default='1'`` so a fresh
            single-tenant install adopts the seeded default workspace.
        slug: URL-safe identifier, unique per workspace (e.g.
            ``customer``).
        name: Human label (e.g. "Customer").
        description: Free-form note on what the entity represents.
        created_by_user_id: Nullable FK on ``users.id``.
        created_at: Wall-clock the entity was declared.
    """

    __tablename__ = "mesh_entities"

    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="uq_mesh_entities_ws_slug"),
        Index("ix_mesh_entities_workspace", "workspace_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
        server_default="1",
    )
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MeshEntityBinding(Base):
    """Binds one mesh entity to one UC column inside a product.

    When two products each bind a column to the same entity, those
    columns are the natural cross-product join key — the join helper
    pairs them.  The column identity is stored denormalised
    (``catalog.schema_name.table_name.column_name``) so the lookup the
    helper + discovery use needs no join back to the catalog.

    Attributes:
        id: Auto-incremented primary key.
        mesh_entity_id: FK on ``mesh_entities.id`` with CASCADE delete.
        data_product_id: FK on ``data_products.id`` with CASCADE
            delete.
        catalog: UC catalog segment.
        schema_name: UC schema segment.
        table_name: UC table name (last segment).
        column_name: UC column name.
        created_by_user_id: Nullable FK on ``users.id``.
        created_at: Wall-clock the binding was declared.
    """

    __tablename__ = "mesh_entity_bindings"

    __table_args__ = (
        UniqueConstraint(
            "mesh_entity_id",
            "data_product_id",
            "table_name",
            "column_name",
            name="uq_mesh_binding_identity",
        ),
        Index("ix_mesh_binding_entity", "mesh_entity_id"),
        Index("ix_mesh_binding_product", "data_product_id"),
        Index(
            "ix_mesh_binding_column",
            "catalog",
            "schema_name",
            "table_name",
            "column_name",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mesh_entity_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("mesh_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    catalog: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(255), nullable=False)
    table_name: Mapped[str] = mapped_column(String(255), nullable=False)
    column_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
