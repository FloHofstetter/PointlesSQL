"""phase 135: polysemic entity-ID + glossary knowledge-graph (F3/F4)

Three new tables that lift the data-product surface from per-table
metadata to a cross-product semantic graph:

- ``data_product_entities``   one entity per business concept inside
  a data product (e.g. "Customer", "Order"), bound to a primary-key
  column tuple on a concrete source table.
- ``entity_links``            cross-product relations between entities
  (``same_as`` / ``derives_from`` / ``related_to``).  Polysemic
  identity is realised by walking the ``same_as`` graph.
- ``glossary_term_relations`` hierarchical + lateral relations between
  glossary terms (``parent`` / ``child`` / ``synonym`` / ``related`` /
  ``antonym``) — the term-graph that sits next to the binding surface.

CASCADE on ``data_products.id`` for entities and on
``glossary_terms.id`` for relations so that removing the parent row
collapses the dependent graph nodes.

Revision ID: r0u2w5y7c1d3
Revises: q8s0u2w5y7a9
Create Date: 2026-05-30 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "r0u2w5y7c1d3"
down_revision: str | None = "q8s0u2w5y7a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the entity + entity-link + term-relation tables."""
    op.create_table(
        "data_product_entities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_name", sa.String(length=80), nullable=False),
        sa.Column("source_table", sa.String(length=200), nullable=False),
        sa.Column("primary_key_columns", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "data_product_id",
            "entity_name",
            name="uq_dp_entities_identity",
        ),
    )
    op.create_index(
        "ix_dp_entities_product",
        "data_product_entities",
        ["data_product_id"],
    )

    op.create_table(
        "entity_links",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "source_entity_id",
            sa.Integer(),
            sa.ForeignKey("data_product_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_entity_id",
            sa.Integer(),
            sa.ForeignKey("data_product_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=True),
        sa.Column(
            "declared_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_entity_id",
            "target_entity_id",
            "kind",
            name="uq_entity_links_identity",
        ),
        sa.CheckConstraint(
            "kind IN ('same_as','derives_from','related_to')",
            name="ck_entity_links_kind",
        ),
    )
    op.create_index(
        "ix_entity_links_source",
        "entity_links",
        ["source_entity_id"],
    )
    op.create_index(
        "ix_entity_links_target",
        "entity_links",
        ["target_entity_id"],
    )

    op.create_table(
        "glossary_term_relations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "source_term_id",
            sa.Integer(),
            sa.ForeignKey("glossary_terms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_term_id",
            sa.Integer(),
            sa.ForeignKey("glossary_terms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_term_id",
            "target_term_id",
            "kind",
            name="uq_glossary_term_relations_identity",
        ),
        sa.CheckConstraint(
            "kind IN ('parent','child','synonym','related','antonym')",
            name="ck_glossary_term_relations_kind",
        ),
    )
    op.create_index(
        "ix_glossary_term_relations_source",
        "glossary_term_relations",
        ["source_term_id"],
    )
    op.create_index(
        "ix_glossary_term_relations_target",
        "glossary_term_relations",
        ["target_term_id"],
    )


def downgrade() -> None:
    """Drop the entity + entity-link + term-relation tables."""
    op.drop_index(
        "ix_glossary_term_relations_target",
        table_name="glossary_term_relations",
    )
    op.drop_index(
        "ix_glossary_term_relations_source",
        table_name="glossary_term_relations",
    )
    op.drop_table("glossary_term_relations")

    op.drop_index("ix_entity_links_target", table_name="entity_links")
    op.drop_index("ix_entity_links_source", table_name="entity_links")
    op.drop_table("entity_links")

    op.drop_index("ix_dp_entities_product", table_name="data_product_entities")
    op.drop_table("data_product_entities")
