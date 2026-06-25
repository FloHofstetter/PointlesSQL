"""workspace foundation: workspaces + members + pins + bootstrap seed

Phase-28 Sprint-28.0 foundation.  Adds three new tables plus the
two cross-cutting FK columns the rest of Phase 28 hangs off.  The
migration is **safe on a populated install**: every existing user
becomes a member of a freshly-seeded ``default`` workspace
(``id=1``, ``slug='default'``) and every existing API key pins to
the same workspace, so single-tenant deployments stay
behaviour-identical until an admin creates a second workspace.

Backfill order matters because of FK dependencies:

1. ``workspaces`` table created.
2. ``default`` workspace row inserted (id=1).
3. ``workspace_members`` table created.  Every existing
   ``users`` row backfills as a member with role mirroring
   ``is_admin`` (admins → role=admin, others → role=member).
4. ``workspace_catalog_pins`` table created (intentionally
   empty — Sprint 28.3 wires it in).
5. ``users.default_workspace_id`` added nullable; all existing
   rows backfilled to 1.  Stays nullable in 28.0 so the FK
   column can co-exist with the legacy code-path; flipped to
   NOT NULL in Sprint 28.6.
6. ``api_keys.workspace_id`` added NOT NULL with
   ``server_default='1'`` so existing rows auto-pin to the
   default workspace.  Carved out of the original Sprint-28.5
   plan-shape into 28.0 to eliminate the cross-sprint hazard
   where Sprint 28.3's catalog filter would trip Bearer-auth
   before the column existed.

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-05 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create workspace tables, seed default workspace, backfill FKs."""
    bind = op.get_bind()

    # 1. workspaces ----------------------------------------------------------
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_workspaces_slug", "workspaces", ["slug"], unique=True)

    # 2. seed default workspace (id=1) --------------------------------------
    bind.execute(
        sa.text(
            "INSERT INTO workspaces (id, slug, name, description, created_at) "
            "VALUES (1, 'default', 'Default workspace', "
            "'Auto-created by Sprint 28.0 bootstrap.  Holds every audit row, "
            "job, dashboard, saved query, recent table, and alert that pre-dates "
            "Phase 28''s workspace isolation.', :now)"
        ),
        {"now": _now_iso()},
    )

    # 3. workspace_members + backfill from existing users -------------------
    op.create_table(
        "workspace_members",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_identity"),
    )
    op.create_index("ix_workspace_members_user", "workspace_members", ["user_id"])

    # Backfill: every existing user joins the default workspace.  The role
    # mirrors users.is_admin so a tenant admin keeps workspace-local admin
    # rights from day one.  Both dialects accept the CASE expression.
    bind.execute(
        sa.text(
            "INSERT INTO workspace_members (workspace_id, user_id, role, created_at) "
            "SELECT 1, id, "
            "CASE WHEN is_admin THEN 'admin' ELSE 'member' END, "
            ":now FROM users"
        ),
        {"now": _now_iso()},
    )

    # 4. workspace_catalog_pins (intentionally empty in 28.0) ---------------
    op.create_table(
        "workspace_catalog_pins",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("catalog_name", sa.String(length=255), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "workspace_id", "catalog_name", name="uq_workspace_catalog_pins_identity"
        ),
    )

    # 5. users.default_workspace_id (nullable in 28.0, NOT NULL in 28.6) ----
    # SQLite cannot ALTER constraints in place — both column adds use
    # batch mode so the underlying copy-and-move strategy carries the
    # FK declaration onto the new table.  Postgres ignores batch mode
    # and runs the equivalent ALTER directly.
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "default_workspace_id",
                sa.Integer(),
                sa.ForeignKey("workspaces.id", name="fk_users_default_workspace_id"),
                nullable=True,
            )
        )
    bind.execute(sa.text("UPDATE users SET default_workspace_id = 1"))

    # 6. api_keys.workspace_id (NOT NULL with server_default='1') -----------
    # The server_default lets SQLite ADD COLUMN succeed on an existing
    # populated table — every existing row gets workspace_id=1
    # transparently, then the constraint stays in place for inserts.
    with op.batch_alter_table("api_keys", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "workspace_id",
                sa.Integer(),
                sa.ForeignKey("workspaces.id", name="fk_api_keys_workspace_id"),
                nullable=False,
                server_default="1",
            )
        )
    # Belt-and-braces: explicit UPDATE in case any historical row had a
    # NULL slip through (e.g. a manually crafted dev DB).
    bind.execute(sa.text("UPDATE api_keys SET workspace_id = 1 WHERE workspace_id IS NULL"))


def downgrade() -> None:
    """Drop workspace_id / default_workspace_id columns + the three tables."""
    # api_keys.workspace_id removal needs batch mode on SQLite.
    with op.batch_alter_table("api_keys") as batch_op:
        batch_op.drop_column("workspace_id")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("default_workspace_id")
    op.drop_table("workspace_catalog_pins")
    op.drop_index("ix_workspace_members_user", table_name="workspace_members")
    op.drop_table("workspace_members")
    op.drop_index("ix_workspaces_slug", table_name="workspaces")
    op.drop_table("workspaces")


def _now_iso() -> str:
    """Return an ISO-8601 UTC timestamp the migration can pass as a parameter.

    Avoids dialect-specific ``CURRENT_TIMESTAMP`` semantics (SQLite
    returns naive UTC, Postgres returns timezone-aware local) by
    materialising the value Python-side before the INSERT.
    """
    import datetime

    return datetime.datetime.now(datetime.UTC).isoformat()
