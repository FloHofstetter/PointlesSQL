"""add 'notebook_cell' to social_targets.entity_kind CHECK

Mirrors the Phase-90 ``agent_memory`` migration line-by-line — the
``social_targets`` table is the polymorphic anchor for every social
row.  Adding a new ``entity_kind`` requires extending the
``ck_social_targets_kind`` CHECK; ``op.batch_alter_table`` covers
both SQLite (CHECK is table-creation-time, so recreate) and Postgres
(in-place drop+create) dialects.

Revision ID: 0099
Revises: 0098
Create Date: 2026-05-19 14:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0099"
down_revision: str | None = "0098"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_OLD_KINDS_SQL = (
    "entity_kind IN ("
    "'dp', 'table', 'schema', 'catalog', "
    "'model', 'branch', 'run', 'query', "
    "'notebook', 'saved_query', 'issue', "
    "'workspace', 'agent_memory'"
    ")"
)

_NEW_KINDS_SQL = (
    "entity_kind IN ("
    "'dp', 'table', 'schema', 'catalog', "
    "'model', 'branch', 'run', 'query', "
    "'notebook', 'saved_query', 'issue', "
    "'workspace', 'agent_memory', 'notebook_cell'"
    ")"
)


def upgrade() -> None:
    """Swap ``ck_social_targets_kind`` to include ``'notebook_cell'``."""
    with op.batch_alter_table("social_targets") as batch_op:
        batch_op.drop_constraint("ck_social_targets_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_social_targets_kind",
            sa.text(_NEW_KINDS_SQL),
        )


def downgrade() -> None:
    """Revert the CHECK to the Phase-90 whitelist (drops notebook_cell)."""
    with op.batch_alter_table("social_targets") as batch_op:
        batch_op.drop_constraint("ck_social_targets_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_social_targets_kind",
            sa.text(_OLD_KINDS_SQL),
        )
