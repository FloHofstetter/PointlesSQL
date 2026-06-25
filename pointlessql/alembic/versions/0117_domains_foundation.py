"""domain ownership foundation

Three new tables plus one nullable column on ``data_products``:

- ``domains`` — one row per business domain in a workspace, carrying
  an archetype (source-aligned / aggregate / consumer-aligned) and a
  soft-archive ``archived_at``.  Unique slug per workspace.
- ``domain_members`` — M:M user↔domain junction with an
  owner/developer ``role``.  CASCADE on ``domains.id``.
- ``data_product_transformations`` — binds a notebook (FK) or a
  named dbt model (string) to a data product.  CASCADE on
  ``data_products.id``.
- ``data_products.domain_id`` — nullable FK on ``domains.id``
  (SET NULL on delete) so a product can be assigned to a domain.

No data migration: every existing data product gets ``domain_id =
NULL`` (unassigned), so behaviour is unchanged until an admin creates
a domain and assigns products to it.

Revision ID: 0117
Revises: 0116
Create Date: 2026-05-29 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0117"
down_revision: str | None = "0116"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the 3 domain tables + add data_products.domain_id."""
    op.create_table(
        "domains",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("archetype", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_domains_ws_slug"),
        sa.CheckConstraint(
            "archetype IN ('source-aligned','aggregate','consumer-aligned')",
            name="ck_domains_archetype",
        ),
    )
    op.create_index("ix_domains_workspace", "domains", ["workspace_id"])

    op.create_table(
        "domain_members",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "domain_id",
            sa.Integer(),
            sa.ForeignKey("domains.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("domain_id", "user_id", name="uq_domain_members_identity"),
        sa.CheckConstraint(
            "role IN ('owner','developer')",
            name="ck_domain_members_role",
        ),
    )
    op.create_index("ix_domain_members_user", "domain_members", ["user_id"])

    op.create_table(
        "data_product_transformations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column(
            "notebook_id",
            sa.String(length=36),
            sa.ForeignKey("notebooks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("dbt_model_name", sa.String(length=255), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('notebook','dbt_model')",
            name="ck_dp_transformations_kind",
        ),
    )
    op.create_index(
        "ix_dp_transformations_product",
        "data_product_transformations",
        ["data_product_id"],
    )

    with op.batch_alter_table("data_products", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "domain_id",
                sa.Integer(),
                sa.ForeignKey("domains.id", name="fk_data_products_domain_id", ondelete="SET NULL"),
                nullable=True,
            )
        )
    op.create_index("ix_data_products_domain", "data_products", ["domain_id"])


def downgrade() -> None:
    """Drop data_products.domain_id + the 3 domain tables."""
    op.drop_index("ix_data_products_domain", table_name="data_products")
    with op.batch_alter_table("data_products", schema=None) as batch_op:
        batch_op.drop_column("domain_id")

    op.drop_index("ix_dp_transformations_product", table_name="data_product_transformations")
    op.drop_table("data_product_transformations")
    op.drop_index("ix_domain_members_user", table_name="domain_members")
    op.drop_table("domain_members")
    op.drop_index("ix_domains_workspace", table_name="domains")
    op.drop_table("domains")
