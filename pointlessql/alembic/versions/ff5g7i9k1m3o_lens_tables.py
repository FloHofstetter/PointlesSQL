"""lens tables + api_keys.analyst column (Phase 65.0)

Adds the four Lens tables (sessions, messages, pinned_answers,
provider_creds) and the ``analyst`` boolean column on
``api_keys`` that gates the new read-only Q&A surface.

The Lens tables are workspace-scoped on every read path; the FK to
``workspaces.id`` is NOT NULL on every body row.  ``lens_messages``
cascades on ``lens_sessions`` delete so admins purging a session do
not leave orphan tool-call audit rows.

The ``api_keys.analyst`` column carries ``server_default='false'`` so
existing rows backfill cleanly to "no Lens access" — admins explicitly
flip it on per key via the admin CRUD.

Revision ID: ff5g7i9k1m3o
Revises: ee3f6h8j0l2n
Create Date: 2026-05-10 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ff5g7i9k1m3o"
down_revision: str | None = "ee3f6h8j0l2n"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the four Lens tables + ``api_keys.analyst`` column."""
    # 1. lens_sessions ---------------------------------------------------
    op.create_table(
        "lens_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("llm_provider", sa.String(length=32), nullable=False),
        sa.Column("llm_model", sa.String(length=128), nullable=False),
        sa.Column(
            "total_cost_estimate",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "llm_provider IN ('openai', 'anthropic')",
            name="ck_lens_sessions_provider",
        ),
    )
    op.create_index(
        "ix_lens_sessions_workspace_owner",
        "lens_sessions",
        ["workspace_id", "owner_id"],
    )
    op.create_index(
        "ix_lens_sessions_last_message",
        "lens_sessions",
        ["workspace_id", "last_message_at"],
    )

    # 2. lens_messages ---------------------------------------------------
    op.create_table(
        "lens_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("lens_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("tool_name", sa.String(length=64), nullable=True),
        sa.Column("tool_args", sa.JSON(), nullable=True),
        sa.Column("tool_result", sa.JSON(), nullable=True),
        sa.Column("tool_status", sa.String(length=32), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "cost_estimate",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'tool')",
            name="ck_lens_messages_role",
        ),
    )
    op.create_index(
        "ix_lens_messages_session_created",
        "lens_messages",
        ["session_id", "created_at"],
    )

    # 3. lens_pinned_answers --------------------------------------------
    op.create_table(
        "lens_pinned_answers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "source_message_id",
            sa.Integer(),
            sa.ForeignKey("lens_messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("content_snapshot", sa.Text(), nullable=False),
        sa.Column("sql_text", sa.Text(), nullable=True),
        sa.Column("result_preview", sa.JSON(), nullable=True),
        sa.Column(
            "is_shared",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "workspace_id",
            "slug",
            name="uq_lens_pinned_workspace_slug",
        ),
    )
    op.create_index(
        "ix_lens_pinned_workspace_owner",
        "lens_pinned_answers",
        ["workspace_id", "owner_id"],
    )

    # 4. lens_provider_creds --------------------------------------------
    op.create_table(
        "lens_provider_creds",
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            primary_key=True,
        ),
        sa.Column("provider", sa.String(length=32), primary_key=True),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column("default_model", sa.String(length=128), nullable=True),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provider IN ('openai', 'anthropic')",
            name="ck_lens_provider_creds_provider",
        ),
    )

    # 5. api_keys.analyst -----------------------------------------------
    op.add_column(
        "api_keys",
        sa.Column(
            "analyst",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    """Drop the Lens tables + the analyst column."""
    op.drop_column("api_keys", "analyst")
    op.drop_table("lens_provider_creds")
    op.drop_index(
        "ix_lens_pinned_workspace_owner",
        table_name="lens_pinned_answers",
    )
    op.drop_table("lens_pinned_answers")
    op.drop_index(
        "ix_lens_messages_session_created",
        table_name="lens_messages",
    )
    op.drop_table("lens_messages")
    op.drop_index(
        "ix_lens_sessions_last_message",
        table_name="lens_sessions",
    )
    op.drop_index(
        "ix_lens_sessions_workspace_owner",
        table_name="lens_sessions",
    )
    op.drop_table("lens_sessions")
