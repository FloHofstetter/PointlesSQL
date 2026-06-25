"""query_history.read_kind for read-audit

Extends ``query_history`` with a ``read_kind`` discriminator so
direct-Delta reads via ``pql.table()`` and engine-direct paths can
land in the same table as ``/api/sql/execute`` rows.  Existing rows
default to ``sql_execute`` — they all came from the SQL editor
route which has been the only writer until this sprint.

Validation of the enum lives in
``pointlessql.services.query_history.record_query`` (no DB CHECK,
matching the existing schema's app-level pattern; see Alembic
``b55f1020b8a4`` where ``status``/``actor_role`` follow the same
convention).

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-26 19:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("query_history", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "read_kind",
                sa.String(length=20),
                server_default="sql_execute",
                nullable=False,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("query_history", schema=None) as batch_op:
        batch_op.drop_column("read_kind")
