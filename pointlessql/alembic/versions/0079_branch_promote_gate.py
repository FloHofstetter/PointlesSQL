"""branch promote-gate workspace setting + endorsement type

Phase 77.3 ships the GitHub-Branch-Protection-style opt-in:
``POST /api/branches/{fqn}/promote`` checks a workspace-level
``branch_promote_requires_endorsement`` flag and (when on)
requires at least one active
``branch-approved-for-promotion`` endorsement from a different
user.  Locked decision #3 keeps the default OFF forever — admins
flip the flag per workspace consciously.

Schema changes:

* ``workspaces.branch_promote_requires_endorsement BOOLEAN
  DEFAULT FALSE NOT NULL`` — the per-workspace gate switch.
* ``data_product_endorsements.endorsement_type`` CHECK
  constraint extended to allow the new
  ``branch-approved-for-promotion`` value.  Existing 4 types
  unchanged.  SQLite rebuilds the table via batch_alter_table.

Revision ID: 0079
Revises: 0078
Create Date: 2026-05-14 15:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0079"
down_revision: str | None = "0078"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_TYPES = (
    "verified-by-steward",
    "production-ready",
    "deprecated",
    "under-review",
)
_NEW_TYPES = (*_OLD_TYPES, "branch-approved-for-promotion")


def _make_check_sql(allowed: tuple[str, ...]) -> str:
    """Build the CHECK constraint expression for *allowed* types."""
    quoted = ", ".join(f"'{t}'" for t in allowed)
    return f"endorsement_type IN ({quoted})"


def upgrade() -> None:
    """Add the workspace gate column + extend the endorsement CHECK."""
    op.add_column(
        "workspaces",
        sa.Column(
            "branch_promote_requires_endorsement",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    with op.batch_alter_table("data_product_endorsements") as batch_op:
        batch_op.drop_constraint("ck_dp_endorsement_type", type_="check")
        batch_op.create_check_constraint(
            "ck_dp_endorsement_type",
            _make_check_sql(_NEW_TYPES),
        )


def downgrade() -> None:
    """Reverse: drop the column + restore the original 4-type CHECK."""
    with op.batch_alter_table("data_product_endorsements") as batch_op:
        batch_op.drop_constraint("ck_dp_endorsement_type", type_="check")
        batch_op.create_check_constraint(
            "ck_dp_endorsement_type",
            _make_check_sql(_OLD_TYPES),
        )

    op.drop_column("workspaces", "branch_promote_requires_endorsement")
