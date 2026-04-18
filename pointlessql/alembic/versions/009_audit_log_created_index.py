"""Add index on audit_log.created_at for Sprint 41 admin viewer.

Revision ID: 009
Revises: 008
"""

from collections.abc import Sequence

from alembic import op

revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ``ix_audit_log_created`` on ``(created_at)``.

    The existing composite indexes cover user- and target-scoped
    lookups, but the Sprint 41 ``/admin/audit`` viewer lists the
    newest N rows across every user; without this index SQLite
    falls back to a full table scan to satisfy the ORDER BY.
    """
    op.create_index(
        "ix_audit_log_created",
        "audit_log",
        ["created_at"],
    )


def downgrade() -> None:
    """Drop the ``ix_audit_log_created`` index."""
    op.drop_index("ix_audit_log_created", table_name="audit_log")
