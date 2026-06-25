"""Idempotent backfill: every user is a member of workspace 1.

The Sprint 28.0 ``workspace_foundation`` migration backfilled
``workspace_members`` from the users table at the time it ran, but
new users registered via :func:`pointlessql.services.auth.register`
between that migration and the auth-service fix landed in this
sprint slipped through without a membership row.  Without that
row the ``X-Workspace`` middleware 403s every HTMX-boosted link,
which makes the entire site unusable for those users.

This migration patches the deployed shape so existing ones stop
hitting the 403; the auth-service fix prevents new ones.

Revision ID: 0049
Revises: 0048
Create Date: 2026-05-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO workspace_members "
            "(workspace_id, user_id, role, created_at) "
            "SELECT 1, u.id, "
            "CASE WHEN u.is_admin THEN 'admin' ELSE 'member' END, "
            "u.created_at "
            "FROM users u "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM workspace_members m "
            "  WHERE m.workspace_id = 1 AND m.user_id = u.id"
            ")"
        )
    )


def downgrade() -> None:
    pass
