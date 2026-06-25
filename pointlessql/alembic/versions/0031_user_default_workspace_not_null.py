"""users.default_workspace_id flipped to NOT NULL

Sprint 28.6 — every user has a default workspace from the
Sprint-28.0 bootstrap (``UPDATE users SET default_workspace_id = 1``)
or from the admin UI shipped in this sprint.  The column was kept
nullable in 28.0 to make the rollout safe; once 28.6 lands the admin
UI surface, every code path that creates a user assigns a workspace,
so the NOT NULL flip is finally appropriate.

Pre-flight backfill: any user with a NULL ``default_workspace_id`` is
filled with workspace ``id=1`` (the seeded default).  This catches
edge cases like users created via direct ORM in tests or during
rollout windows where 28.0 ran but 28.6 hadn't yet.

Revision ID: 0031
Revises: 0030
Create Date: 2026-05-05 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Flip ``users.default_workspace_id`` to NOT NULL after a defensive backfill."""
    bind = op.get_bind()
    bind.execute(
        sa.text("UPDATE users SET default_workspace_id = 1 WHERE default_workspace_id IS NULL")
    )

    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "default_workspace_id",
            existing_type=sa.Integer(),
            nullable=False,
        )


def downgrade() -> None:
    """Re-allow NULLs on ``users.default_workspace_id``."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "default_workspace_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
