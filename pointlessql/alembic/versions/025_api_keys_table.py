"""Sprint 13.11.4a: api_keys table — DB-backed Bearer-token store.

Revision ID: 025
Revises: 024

Sprint 13.7.0.5 introduced the env-var POINTLESSQL_API_KEYS gate
as a front-loaded shoreguard for the Hermes plugin's Bearer client.
Sprint 13.11.4a promotes that store to a real DB table so:

* admins can create + revoke keys without a process restart;
* keys carry a ``supervisor`` scope that the new Family-B
  Sprint-13.11.4 routes (run summary, diff, by-principal, by-agent)
  use to gate cross-run reads — supervision telemetry should not be
  walkable by every working agent;
* ``last_used_at`` makes stale-key cleanup straightforward.

The env var stays valid as a *bootstrap* path: a process-startup
hook (``services.api_keys.bootstrap_from_env``) idempotently spills
``name:secret[:supervisor]`` pairs into this table, so clean-machine
docker-compose deployments with no admin UI mounted still work.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "025"
down_revision: str | None = "024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``api_keys`` with a unique name index + secret-hash index."""
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=64), nullable=False, unique=True),
        sa.Column("secret_hash", sa.String(length=128), nullable=False),
        sa.Column("secret_prefix", sa.String(length=8), nullable=False),
        sa.Column(
            "supervisor",
            sa.Boolean,
            nullable=False,
            default=False,
            server_default=sa.text("0"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Integer,
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Hot-path lookup: middleware hashes the presented secret then
    # compares against this column, so an index is mandatory.
    op.create_index("ix_api_keys_secret_hash", "api_keys", ["secret_hash"])


def downgrade() -> None:
    """Drop the table + its hash index."""
    op.drop_index("ix_api_keys_secret_hash", table_name="api_keys")
    op.drop_table("api_keys")
