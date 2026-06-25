"""agent_reviews.workspace_id + review_destinations.workspace_filter

Two coupled changes that together let an admin scope review fan-out
to a single workspace without changing semantics for installs that
don't care:

* ``agent_reviews.workspace_id`` becomes the routing key.  Defaults
  to the install-default workspace (id=1) so historical reviews
  remain visible under the cross-workspace lens.  Indexed alongside
  ``period_end`` to keep the cockpit "latest review" lookup cheap.
* ``review_destinations.workspace_filter`` carries an optional
  JSON-encoded list of workspace IDs.  ``NULL`` → install-global
  fan-out (back-compat).  ``[1, 2]`` → only reviews whose
  ``workspace_id`` is in the list reach this destination.

The dispatcher predicate lives in
:func:`pointlessql.services.review_dispatcher._select_destinations`;
the route handler at
``POST /api/agent-reviews`` reads ``request.state.workspace_id`` to
populate ``AgentReview.workspace_id``.

Revision ID: 0033
Revises: 0032
Create Date: 2026-05-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add agent_reviews.workspace_id + review_destinations.workspace_filter."""
    with op.batch_alter_table("agent_reviews") as batch:
        batch.add_column(
            sa.Column(
                "workspace_id",
                sa.Integer(),
                sa.ForeignKey(
                    "workspaces.id",
                    name="fk_agent_reviews_workspace_id",
                ),
                nullable=False,
                server_default="1",
            ),
        )
        batch.create_index(
            "ix_agent_reviews_workspace_period",
            ["workspace_id", "period_end"],
        )

    op.add_column(
        "review_destinations",
        sa.Column("workspace_filter", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Revert both 29.2 columns."""
    op.drop_column("review_destinations", "workspace_filter")
    with op.batch_alter_table("agent_reviews") as batch:
        batch.drop_index("ix_agent_reviews_workspace_period")
        batch.drop_constraint("fk_agent_reviews_workspace_id", type_="foreignkey")
        batch.drop_column("workspace_id")
