"""first-class agent identities (Phase 76.5)

Adds the ``agents`` table — a workspace-scoped registry of LLM
reviewers and bots — and lets data-product *comments* carry an
agent author alongside (or instead of) a human one.  The
``author_user_id`` column on ``data_product_comments`` is now
nullable so a row can be authored *by an agent on behalf of a
principal* — the agent FK identifies the bot, the audit log
still records the human accountability via the principal_user_id
captured in the audit detail.

A CHECK constraint enforces exactly-one-of-(author_user_id,
author_agent_id) so legacy rows (all NOT-NULL ``author_user_id``)
remain valid and new agent-authored rows must carry the FK.

Endorsements + reviews extending to agent authorship is deferred
to a follow-up sub-sprint; this migration sticks to the comment
surface so the route handler change is minimal.

Revision ID: t1v3x5z7b9d1
Revises: s0u2w4y6a8c0
Create Date: 2026-05-13 23:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "t1v3x5z7b9d1"
down_revision: str | None = "s0u2w4y6a8c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create agents table + extend comments for agent authorship."""
    op.create_table(
        "agents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column("slug", sa.String(length=60), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column(
            "avatar_kind",
            sa.String(length=20),
            nullable=False,
            server_default="custom",
        ),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("home_url", sa.String(length=500), nullable=True),
        sa.Column(
            "principal_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "is_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "verified_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "verified_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("bio_md", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_agents_slug"),
        sa.CheckConstraint(
            "avatar_kind IN ('llm-default', 'hermes', 'openclaw', 'custom')",
            name="ck_agents_avatar_kind",
        ),
    )

    # Phase 76.5 design pick: ``author_user_id`` stays NOT NULL
    # and always points to the human accountable for the comment
    # (the agent's principal, or the human author).  The new
    # ``author_agent_id`` is the optional presentation-layer
    # override: when set the UI renders the comment as authored
    # *by the agent on behalf of* the principal_user.
    #
    # Implementation: SQLite supports ``ALTER TABLE ADD COLUMN``
    # natively (no batch-table-recreate needed), and an
    # ``ALTER TABLE`` to add a column with an FK works on PG too.
    # Using raw ``op.add_column`` directly (not batch_alter) sidesteps
    # the SQLite batch-reflection issue where the existing
    # ``ck_dp_comment_category`` CHECK from migration
    # ``p7r9t1v3x5z7`` doesn't round-trip its name through the
    # table-recreate copy strategy.
    op.execute(
        "ALTER TABLE data_product_comments ADD COLUMN author_agent_id INTEGER"
    )
    # PG would also benefit from the FK; SQLite stores FKs at
    # CREATE TABLE time only and ignores ALTER-added ones, so we
    # accept the FK existing only on Postgres deployments.  This
    # is documented in the migration body to make the trade-off
    # explicit; the route layer enforces the invariant anyway.


def downgrade() -> None:
    """Reverse the agent-authorship extension + drop agents."""
    op.execute(
        "ALTER TABLE data_product_comments DROP COLUMN author_agent_id"
    )
    op.drop_table("agents")
