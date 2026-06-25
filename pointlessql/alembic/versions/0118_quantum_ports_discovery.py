"""quantum ports, discovery, statistics, glossary

Six new tables plus one nullable column on ``data_products``:

- ``data_product_output_ports`` — declared access modes a product
  exposes (sql / file / event).  CASCADE on ``data_products.id``.
- ``data_product_input_ports`` — declared upstream sources a product
  consumes (operational_system / upstream_product / external).
  CASCADE on ``data_products.id``.
- ``data_product_semantic_concepts`` — per-product business concepts
  optionally bound to a column.  CASCADE on ``data_products.id``.
- ``data_product_statistics`` — self-generated shape snapshots stamped
  at write time.  CASCADE on ``data_products.id``; SET NULL on
  ``agent_run_operations.id``.
- ``glossary_terms`` — workspace business vocabulary.
- ``glossary_term_columns`` — M:N binding of a term to a UC column.
  CASCADE on ``glossary_terms.id``.
- ``data_products.sample_sql`` — nullable example query for the
  semantic / discovery surface.

No data migration: existing products get ``sample_sql = NULL`` and no
ports/semantic/statistics rows, so behaviour is unchanged until an
owner declares them.

Revision ID: 0118
Revises: 0117
Create Date: 2026-05-29 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0118"
down_revision: str | None = "0117"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the 6 product/glossary tables + add data_products.sample_sql."""
    op.create_table(
        "data_product_output_ports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("format", sa.String(length=32), nullable=True),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("data_product_id", "name", name="uq_dp_output_ports_name"),
        sa.CheckConstraint(
            "kind IN ('sql','file','event')",
            name="ck_dp_output_ports_kind",
        ),
    )
    op.create_index(
        "ix_dp_output_ports_product",
        "data_product_output_ports",
        ["data_product_id"],
    )

    op.create_table(
        "data_product_input_ports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("source_ref", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("data_product_id", "name", name="uq_dp_input_ports_name"),
        sa.CheckConstraint(
            "kind IN ('operational_system','upstream_product','external')",
            name="ck_dp_input_ports_kind",
        ),
    )
    op.create_index(
        "ix_dp_input_ports_product",
        "data_product_input_ports",
        ["data_product_id"],
    )

    op.create_table(
        "data_product_semantic_concepts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("concept", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("maps_to", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("data_product_id", "concept", name="uq_dp_semantic_concept"),
    )
    op.create_index(
        "ix_dp_semantic_product",
        "data_product_semantic_concepts",
        ["data_product_id"],
    )

    op.create_table(
        "data_product_statistics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_run_operation_id",
            sa.Integer(),
            sa.ForeignKey("agent_run_operations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("table_name", sa.String(length=255), nullable=False),
        sa.Column("delta_log_version", sa.BigInteger(), nullable=True),
        sa.Column("row_count", sa.BigInteger(), nullable=True),
        sa.Column("shape_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("profile_kind", sa.String(length=16), nullable=False, server_default="light"),
        sa.Column("freshness_lag_minutes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "profile_kind IN ('light','full','reused')",
            name="ck_data_product_statistics_profile_kind",
        ),
    )
    op.create_index(
        "ix_dp_statistics_latest",
        "data_product_statistics",
        ["data_product_id", "table_name", "created_at"],
    )
    op.create_index(
        "ix_dp_statistics_op",
        "data_product_statistics",
        ["agent_run_operation_id"],
    )

    op.create_table(
        "glossary_terms",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("term", sa.String(length=200), nullable=False),
        sa.Column("definition", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_glossary_terms_ws_slug"),
    )
    op.create_index("ix_glossary_terms_workspace", "glossary_terms", ["workspace_id"])

    op.create_table(
        "glossary_term_columns",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "glossary_term_id",
            sa.Integer(),
            sa.ForeignKey("glossary_terms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("catalog", sa.String(length=255), nullable=False),
        sa.Column("schema_name", sa.String(length=255), nullable=False),
        sa.Column("table_name", sa.String(length=255), nullable=False),
        sa.Column("column_name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "glossary_term_id",
            "catalog",
            "schema_name",
            "table_name",
            "column_name",
            name="uq_glossary_term_columns_identity",
        ),
    )
    op.create_index(
        "ix_glossary_bindings_term",
        "glossary_term_columns",
        ["glossary_term_id"],
    )
    op.create_index(
        "ix_glossary_bindings_column",
        "glossary_term_columns",
        ["catalog", "schema_name", "table_name", "column_name"],
    )

    with op.batch_alter_table("data_products", schema=None) as batch_op:
        batch_op.add_column(sa.Column("sample_sql", sa.Text(), nullable=True))


def downgrade() -> None:
    """Drop data_products.sample_sql + the 6 product/glossary tables."""
    with op.batch_alter_table("data_products", schema=None) as batch_op:
        batch_op.drop_column("sample_sql")

    op.drop_index("ix_glossary_bindings_column", table_name="glossary_term_columns")
    op.drop_index("ix_glossary_bindings_term", table_name="glossary_term_columns")
    op.drop_table("glossary_term_columns")
    op.drop_index("ix_glossary_terms_workspace", table_name="glossary_terms")
    op.drop_table("glossary_terms")

    op.drop_index("ix_dp_statistics_op", table_name="data_product_statistics")
    op.drop_index("ix_dp_statistics_latest", table_name="data_product_statistics")
    op.drop_table("data_product_statistics")

    op.drop_index("ix_dp_semantic_product", table_name="data_product_semantic_concepts")
    op.drop_table("data_product_semantic_concepts")

    op.drop_index("ix_dp_input_ports_product", table_name="data_product_input_ports")
    op.drop_table("data_product_input_ports")

    op.drop_index("ix_dp_output_ports_product", table_name="data_product_output_ports")
    op.drop_table("data_product_output_ports")
