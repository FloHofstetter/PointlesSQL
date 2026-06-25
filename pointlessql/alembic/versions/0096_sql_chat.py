"""SQL-editor chat sessions + proposals

Adds two tables that back the NL→SQL chat panel in the SQL editor:

* ``editor_chat_sessions`` — one row per (editor-tab, user) pair;
  carries the ``hermes_agent`` conversation history JSON and the
  1:1 link to the ``agent_run`` that owns every plugin tool-call
  in the session.
* ``chat_proposals`` — one row per DML/DDL draft the LLM hands
  back to the human via ``pql_propose_sql``; status transitions
  ``pending`` → ``accepted`` | ``discarded`` | ``expired``.

Both tables denormalise ``workspace_id`` from their parent rows so
workspace-scoped audit reads stay JOIN-free.

Revision ID: 0096
Revises: 0095
Create Date: 2026-05-19 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0096"
down_revision: str | None = "0095"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``editor_chat_sessions`` + ``chat_proposals``."""
    op.create_table(
        "editor_chat_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "editor_session_id",
            sa.String(length=36),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "agent_run_id",
            sa.String(length=36),
            sa.ForeignKey("agent_runs.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "conversation_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "turn_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "current_turn_id",
            sa.String(length=36),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_editor_chat_sessions_user_active",
        "editor_chat_sessions",
        ["user_id", "last_active_at"],
    )
    op.create_index(
        "ix_editor_chat_sessions_workspace_active",
        "editor_chat_sessions",
        ["workspace_id", "last_active_at"],
    )

    op.create_table(
        "chat_proposals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "proposal_id",
            sa.String(length=36),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "chat_session_id",
            sa.Integer(),
            sa.ForeignKey("editor_chat_sessions.id"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column("sql_text", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=12),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "accepted_run_id",
            sa.String(length=36),
            sa.ForeignKey("agent_runs.id"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "kind IN ('dml', 'ddl')",
            name="ck_chat_proposals_kind",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'discarded', 'expired')",
            name="ck_chat_proposals_status",
        ),
    )
    op.create_index(
        "ix_chat_proposals_session",
        "chat_proposals",
        ["chat_session_id", "created_at"],
    )
    op.create_index(
        "ix_chat_proposals_workspace_status",
        "chat_proposals",
        ["workspace_id", "status"],
    )


def downgrade() -> None:
    """Drop both tables (proposals first to respect the FK)."""
    op.drop_index("ix_chat_proposals_workspace_status", table_name="chat_proposals")
    op.drop_index("ix_chat_proposals_session", table_name="chat_proposals")
    op.drop_table("chat_proposals")
    op.drop_index(
        "ix_editor_chat_sessions_workspace_active",
        table_name="editor_chat_sessions",
    )
    op.drop_index(
        "ix_editor_chat_sessions_user_active",
        table_name="editor_chat_sessions",
    )
    op.drop_table("editor_chat_sessions")
