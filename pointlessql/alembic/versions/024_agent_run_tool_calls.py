"""Sprint 13.7.4: agent_run_tool_calls table.

Revision ID: 024
Revises: 023

Sprint 13.7.4 adds a fourth orthogonal level alongside cells /
operations / queries: **tool calls** as the LLM invocation
record. The Hermes plugin's ``post_tool_call`` hook posts every
``pql_*`` invocation here so a human reading ``/runs/{id}`` can
reconstruct the LLM's reasoning trace. This is intentionally
distinct from ``agent_run_operations`` (PQL primitive writes) and
``agent_run_events`` (CloudEvent dispatch outcome).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "024"
down_revision: str | None = "023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``agent_run_tool_calls`` with its FK + composite index."""
    op.create_table(
        "agent_run_tool_calls",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "agent_run_id",
            sa.String(length=36),
            sa.ForeignKey("agent_runs.id"),
            nullable=False,
        ),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("args_json", sa.Text, nullable=False),
        sa.Column("result_summary", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("called_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_agent_run_tool_calls_run",
        "agent_run_tool_calls",
        ["agent_run_id", "called_at"],
    )


def downgrade() -> None:
    """Drop the table + its index."""
    op.drop_index("ix_agent_run_tool_calls_run", table_name="agent_run_tool_calls")
    op.drop_table("agent_run_tool_calls")
