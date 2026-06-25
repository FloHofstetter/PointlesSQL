"""output-port schema-contract versioning

Adds the persistence the schema-contract surface needs:

* ``data_product_output_ports.version_semver`` — current MAJOR.MINOR.PATCH
  version of the port's schema contract, default ``"0.1.0"``.
* ``output_port_schema_versions`` — append-only history of every schema
  bump; CHECK-bounded ``change_kind`` in (major, minor, patch).
* ``workspace_governance_policies.breaking_change_policy`` +
  ``data_product_policies.breaking_change_policy`` — CHECK-bounded in
  (block, warn, off).  Default ``warn``.

SQLite needs ``batch_alter_table`` for the CHECK constraints on the
existing policy tables.

Revision ID: 0133
Revises: 0132
Create Date: 2026-05-30 19:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0133"
down_revision: str | None = "0132"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add version + history + policy columns."""
    op.add_column(
        "data_product_output_ports",
        sa.Column(
            "version_semver",
            sa.String(length=16),
            nullable=False,
            server_default="0.1.0",
        ),
    )

    op.create_table(
        "output_port_schema_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "output_port_id",
            sa.Integer(),
            sa.ForeignKey("data_product_output_ports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_semver", sa.String(length=16), nullable=False),
        sa.Column("schema_json", sa.Text(), nullable=False),
        sa.Column("change_kind", sa.String(length=8), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("bumped_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "bumped_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "change_kind IN ('major','minor','patch')",
            name="ck_output_port_schema_versions_kind",
        ),
        sa.UniqueConstraint(
            "output_port_id",
            "version_semver",
            name="uq_output_port_schema_versions_port_version",
        ),
    )
    op.create_index(
        "ix_output_port_schema_versions_port",
        "output_port_schema_versions",
        ["output_port_id", "bumped_at"],
    )

    with op.batch_alter_table("workspace_governance_policies") as batch:
        batch.add_column(
            sa.Column(
                "breaking_change_policy",
                sa.String(length=8),
                nullable=False,
                server_default="warn",
            )
        )
        batch.create_check_constraint(
            "ck_workspace_governance_policies_breaking_change",
            "breaking_change_policy IN ('block','warn','off')",
        )

    with op.batch_alter_table("data_product_policies") as batch:
        batch.add_column(
            sa.Column(
                "breaking_change_policy",
                sa.String(length=8),
                nullable=True,
            )
        )
        batch.create_check_constraint(
            "ck_data_product_policies_breaking_change",
            "breaking_change_policy IS NULL OR breaking_change_policy IN ('block','warn','off')",
        )


def downgrade() -> None:
    """Drop the columns + history table in reverse order."""
    with op.batch_alter_table("data_product_policies") as batch:
        batch.drop_constraint("ck_data_product_policies_breaking_change", type_="check")
        batch.drop_column("breaking_change_policy")
    with op.batch_alter_table("workspace_governance_policies") as batch:
        batch.drop_constraint("ck_workspace_governance_policies_breaking_change", type_="check")
        batch.drop_column("breaking_change_policy")
    op.drop_index(
        "ix_output_port_schema_versions_port",
        table_name="output_port_schema_versions",
    )
    op.drop_table("output_port_schema_versions")
    op.drop_column("data_product_output_ports", "version_semver")
