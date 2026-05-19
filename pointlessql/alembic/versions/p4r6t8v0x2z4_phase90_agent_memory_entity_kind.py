"""phase90 — add 'agent_memory' to social_targets.entity_kind CHECK

The Phase-90 ``pql.memory`` facade exposes the existing agent-run
+ operations + branch surface as the agent's persistent memory.
The ``/memory/<agent-id>`` UI page hangs the polymorphic
comment / endorsement / follower social rows off a new
``entity_kind='agent_memory'`` anchor — one row per agent,
``entity_ref`` is the ``AgentRun.agent_id`` string.

SQLite enforces CHECK constraints at table-creation time, so
adding ``agent_memory`` to the whitelist requires
``op.batch_alter_table`` which recreates the table with the
updated constraint and copies rows over.  Postgres can drop +
recreate the constraint in-place; ``batch_alter_table`` covers
both dialects.

Revision ID: p4r6t8v0x2z4
Revises: o2q4s6u8w0y2
Create Date: 2026-05-19 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "p4r6t8v0x2z4"
down_revision: str | None = "o2q4s6u8w0y2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_OLD_KINDS_SQL = (
    "entity_kind IN ("
    "'dp', 'table', 'schema', 'catalog', "
    "'model', 'branch', 'run', 'query', "
    "'notebook', 'saved_query', 'issue', "
    "'workspace'"
    ")"
)

_NEW_KINDS_SQL = (
    "entity_kind IN ("
    "'dp', 'table', 'schema', 'catalog', "
    "'model', 'branch', 'run', 'query', "
    "'notebook', 'saved_query', 'issue', "
    "'workspace', 'agent_memory'"
    ")"
)


def upgrade() -> None:
    """Swap ``ck_social_targets_kind`` to include ``'agent_memory'``."""
    with op.batch_alter_table("social_targets") as batch_op:
        batch_op.drop_constraint("ck_social_targets_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_social_targets_kind",
            sa.text(_NEW_KINDS_SQL),
        )


def downgrade() -> None:
    """Revert the CHECK to the Phase-77a whitelist (drops agent_memory)."""
    with op.batch_alter_table("social_targets") as batch_op:
        batch_op.drop_constraint("ck_social_targets_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_social_targets_kind",
            sa.text(_OLD_KINDS_SQL),
        )
