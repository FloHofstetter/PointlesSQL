"""Business glossary — the seed of a cross-product semantic layer.

Two tables that let a workspace define shared business vocabulary and
bind each term to the concrete columns that realise it across data
products:

* ``glossary_terms`` — one row per business term inside a workspace
  (e.g. "Net Revenue"), with a definition.  Browsed by everyone,
  managed by admins (mirrors the domains surface).
* ``glossary_term_columns`` — M:N binding of a term to a specific UC
  column (``catalog.schema.table.column``).  The reverse lookup
  ("which terms describe this column?") surfaces glossary badges on a
  product's Contract tab, so meaning travels with the data.

This is the beginning of the semantic-layer / knowledge-graph
capability: as terms get bound across products, an emergent graph of
shared meaning forms from local declarations.

Storage decision: PointlesSQL metadata DB.  The column bindings
reference UC by name (no FK — UC lives in a separate process).
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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

GLOSSARY_TERM_RELATION_KINDS: tuple[str, ...] = (
    "parent",
    "child",
    "synonym",
    "related",
    "antonym",
)


class GlossaryTerm(Base):
    """One business term inside a workspace.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Workspace this term belongs to.  FK on
            ``workspaces.id``; ``server_default='1'`` so a fresh
            single-tenant install adopts the seeded default
            workspace without a data migration.
        slug: URL-safe identifier, unique per workspace.  Used in
            ``/glossary/{slug}``.
        term: Human-readable label (e.g. "Net Revenue").
        definition: Free-form definition (nullable).
        created_by_user_id: Nullable FK on ``users.id``.
        created_at: Wall-clock the term was created.
    """

    __tablename__ = "glossary_terms"

    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="uq_glossary_terms_ws_slug"),
        Index("ix_glossary_terms_workspace", "workspace_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
        server_default="1",
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    term: Mapped[str] = mapped_column(String(200), nullable=False)
    definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GlossaryTermColumn(Base):
    """Binds one glossary term to one UC column.

    The binding is the join between shared vocabulary and concrete
    data; the reverse lookup powers the per-column glossary badges on
    the product Contract tab.

    Attributes:
        id: Auto-incremented primary key.
        glossary_term_id: FK on ``glossary_terms.id`` with CASCADE
            delete.
        catalog: UC catalog segment.
        schema_name: UC schema segment.
        table_name: UC table name (last segment).
        column_name: UC column name.
        created_at: Wall-clock the binding was created.
    """

    __tablename__ = "glossary_term_columns"

    __table_args__ = (
        UniqueConstraint(
            "glossary_term_id",
            "catalog",
            "schema_name",
            "table_name",
            "column_name",
            name="uq_glossary_term_columns_identity",
        ),
        Index("ix_glossary_bindings_term", "glossary_term_id"),
        Index(
            "ix_glossary_bindings_column",
            "catalog",
            "schema_name",
            "table_name",
            "column_name",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    glossary_term_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("glossary_terms.id", ondelete="CASCADE"),
        nullable=False,
    )
    catalog: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(255), nullable=False)
    table_name: Mapped[str] = mapped_column(String(255), nullable=False)
    column_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GlossaryTermRelation(Base):
    """Directed relation between two glossary terms.

    Builds the knowledge-graph the binding surface (M:N to columns)
    lacked: hierarchy (``parent``/``child``), lateral synonyms,
    softer ``related`` references, and inverse ``antonym`` links.

    Attributes:
        id: Auto-incremented primary key.
        source_term_id: FK on ``glossary_terms.id`` with CASCADE
            delete.
        target_term_id: FK on ``glossary_terms.id`` with CASCADE
            delete.
        kind: One of :data:`GLOSSARY_TERM_RELATION_KINDS`.
        created_by_user_id: Author of the declaration, nullable FK
            on ``users.id``.
        created_at: Wall-clock the relation was created.
    """

    __tablename__ = "glossary_term_relations"

    __table_args__ = (
        UniqueConstraint(
            "source_term_id",
            "target_term_id",
            "kind",
            name="uq_glossary_term_relations_identity",
        ),
        CheckConstraint(
            "kind IN ('parent','child','synonym','related','antonym')",
            name="ck_glossary_term_relations_kind",
        ),
        Index("ix_glossary_term_relations_source", "source_term_id"),
        Index("ix_glossary_term_relations_target", "target_term_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_term_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("glossary_terms.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_term_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("glossary_terms.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
