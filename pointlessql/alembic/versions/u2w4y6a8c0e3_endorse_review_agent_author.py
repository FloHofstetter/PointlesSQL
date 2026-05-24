"""agent authorship on endorsements + reviews + active-reviewer agent_slug

Extends the Phase 76.5 agent-authorship discriminator from
``data_product_comments`` to the remaining two write surfaces
that the original Phase 76 plan called out (Track E.3):
endorsements and reviews.  Adds the optional ``agent_slug``
column to ``data_product_active_reviewer_configs`` so the
Phase 74 Active Reviewer can post under an agent identity.

Both new ``*_agent_id`` columns mirror the comment design:
the existing ``*_user_id`` column stays NOT NULL (it always
carries the human accountable — caller when direct, principal
when speaking-as-agent), and the new agent column is the
optional presentation-layer override.

Implementation note — same raw-SQL pattern as the Phase 76.5
migration:  SQLite's ``ALTER TABLE ADD COLUMN`` works natively
and bypasses the batch-table-recreate failure mode that trips
over the prior unnamed CHECKs on these tables.  Postgres also
honours ``ALTER TABLE ADD COLUMN``; the FK is enforced there
but not on SQLite (which only honours FKs declared at
``CREATE TABLE`` time).  The route layer is the canonical
gate so the FK is defence-in-depth, not the primary invariant.

Revision ID: u2w4y6a8c0e3
Revises: t1v3x5z7b9d1
Create Date: 2026-05-13 23:55:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "u2w4y6a8c0e3"
down_revision: str | None = "t1v3x5z7b9d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add agent-authorship columns on endorsements + reviews + reviewer cfg."""
    op.execute("ALTER TABLE data_product_endorsements ADD COLUMN applied_by_agent_id INTEGER")
    op.execute("ALTER TABLE data_product_reviews ADD COLUMN author_agent_id INTEGER")
    op.execute("ALTER TABLE data_product_active_reviewer_configs ADD COLUMN agent_slug VARCHAR(60)")


def downgrade() -> None:
    """Drop the columns added in :func:`upgrade`."""
    op.execute("ALTER TABLE data_product_active_reviewer_configs DROP COLUMN agent_slug")
    op.execute("ALTER TABLE data_product_reviews DROP COLUMN author_agent_id")
    op.execute("ALTER TABLE data_product_endorsements DROP COLUMN applied_by_agent_id")
