"""phase 142: per-product contract tests + synthetic fixtures

Adds the three tables the contract-test surface needs:

* ``data_product_fixtures`` — Faker-driven row-generator specs per
  declared table (one row per fixture, unique inside the product).
* ``data_product_contract_tests`` — declarative assertion definitions
  with a CHECK-bounded ``assertion_kind`` (one of the six the assertion
  evaluator knows) plus severity + enabled flag.
* ``data_product_contract_test_results`` — per-run ledger; status
  CHECK in (pass, fail, error).  Result rows are accumulating, never
  upserted — the surface paginates by ``run_at``.

Revision ID: d1p3r5t7v9x1
Revises: b9n1p3r5t7v9
Create Date: 2026-05-30 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1p3r5t7v9x1"
down_revision: str | None = "b9n1p3r5t7v9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the fixtures + contract-tests + results tables."""
    op.create_table(
        "data_product_fixtures",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("table_name", sa.String(length=200), nullable=False),
        sa.Column("generator_spec_json", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="100"),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "data_product_id",
            "table_name",
            name="uq_data_product_fixtures_product_table",
        ),
    )

    op.create_table(
        "data_product_contract_tests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("assertion_kind", sa.String(length=32), nullable=False),
        sa.Column("assertion_spec_json", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=8), nullable=False, server_default="warn"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "assertion_kind IN ('row_count_range','column_present',"
            "'value_distribution','null_rate','referential','freshness')",
            name="ck_contract_tests_assertion_kind",
        ),
        sa.CheckConstraint(
            "severity IN ('info','warn','error')",
            name="ck_contract_tests_severity",
        ),
        sa.UniqueConstraint("data_product_id", "name", name="uq_contract_tests_product_name"),
    )

    op.create_table(
        "data_product_contract_test_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "contract_test_id",
            sa.Integer(),
            sa.ForeignKey("data_product_contract_tests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("observation_json", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pass','fail','error')",
            name="ck_contract_test_results_status",
        ),
    )
    op.create_index(
        "ix_contract_test_results_test",
        "data_product_contract_test_results",
        ["contract_test_id", "run_at"],
    )


def downgrade() -> None:
    """Drop the three tables in reverse FK order."""
    op.drop_index(
        "ix_contract_test_results_test",
        table_name="data_product_contract_test_results",
    )
    op.drop_table("data_product_contract_test_results")
    op.drop_table("data_product_contract_tests")
    op.drop_table("data_product_fixtures")
