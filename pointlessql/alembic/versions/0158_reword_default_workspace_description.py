"""reword default workspace description

Revision ID: 0158
Revises: 0157
Create Date: 2026-06-13 18:41:07.386436
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0158"
down_revision: str | None = "0157"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The default workspace shipped with an internal bootstrap blurb in its
# description — release jargon that surfaced verbatim in the workspace
# header. Replace it with a user-facing explanation of what the default
# workspace actually holds, but only when the row still carries the old
# seeded text so a hand-edited description is never clobbered.
_OLD_DESCRIPTION = (
    "Auto-created by Sprint 28.0 bootstrap.  Holds every audit row, "
    "job, dashboard, saved query, recent table, and alert that pre-dates "
    "Phase 28's workspace isolation."
)
_NEW_DESCRIPTION = (
    "The default workspace. Holds every audit row, job, dashboard, "
    "saved query, recent table, and alert that isn't assigned to a "
    "workspace of its own."
)


def _swap_description(old: str, new: str) -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE workspaces SET description = :new WHERE slug = 'default' AND description = :old"
        ),
        {"new": new, "old": old},
    )


def upgrade() -> None:
    """Replace the default workspace's internal bootstrap blurb."""
    _swap_description(_OLD_DESCRIPTION, _NEW_DESCRIPTION)


def downgrade() -> None:
    """Restore the original seeded description."""
    _swap_description(_NEW_DESCRIPTION, _OLD_DESCRIPTION)
