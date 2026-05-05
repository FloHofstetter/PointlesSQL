"""User scope columns + OIDC groups snapshot (Phase 29.3)

Adds three columns to ``users`` so OIDC-authenticated session users
can carry supervisor / auditor scope without being forced through the
API-key path:

* ``is_supervisor`` — mirrors :class:`ApiKey.supervisor`.  Granted by
  matching an OIDC group in
  :attr:`OIDCSettings.parsed_group_map`.  Re-resolved on every login.
* ``is_auditor`` — mirrors :class:`ApiKey.auditor`.  Same source.
* ``oidc_groups_json`` — JSON-encoded snapshot of the groups claim
  the IdP returned at the most recent login.  Audit-visibility only;
  authz never reads this column at runtime.

The asymmetric privilege ladder pinned in Sprint 19.1 (auditor scope
passes ``require_supervisor`` but supervisor does not pass
``require_auditor``) is preserved on the session-cookie path inside
:func:`pointlessql.api.dependencies.require_supervisor`.

Revision ID: gg7i9k1m3o5q
Revises: ff6h8j0l2n4p
Create Date: 2026-05-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "gg7i9k1m3o5q"
down_revision: str | None = "ff6h8j0l2n4p"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ``users.is_supervisor`` + ``is_auditor`` + ``oidc_groups_json``."""
    op.add_column(
        "users",
        sa.Column(
            "is_supervisor",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "is_auditor",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("oidc_groups_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Drop the three Phase 29.3 user columns."""
    op.drop_column("users", "oidc_groups_json")
    op.drop_column("users", "is_auditor")
    op.drop_column("users", "is_supervisor")
