"""Backfill rich Markdown descriptions for the 5 starter audit queries.

The originals (Phase 32) were plain-prose paragraphs.  Now that the
saved-queries cockpit renders descriptions through the
``render_markdown`` Jinja filter, replace each starter row's
description in place so existing deployments get the same content as
fresh installs without re-running the seed migration.

Idempotent: only updates rows whose ``slug`` matches a known starter
(``is_starter = TRUE``) — user-created rows and any future starters
not in this list are left untouched.

Revision ID: cc2e5g7i9k1m
Revises: bb1d4f6e8a0c
Create Date: 2026-05-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "cc2e5g7i9k1m"
down_revision = "bb1d4f6e8a0c"
branch_labels = None
depends_on = None


_DESCRIPTIONS: list[tuple[str, str]] = [
    (
        "pii-writes-last-90d",
        "Every `lineage_value_changes` row whose `target_column` "
        "contains the substring `pii` over the last 90 days.\n\n"
        "**When to use:**\n\n"
        "- GDPR Art. 30 evidence — show every PII mutation in a "
        "compliance window.\n"
        "- Investigate after a data-protection incident; pivot "
        "into the row-trace UI from any returned `run_id`.\n",
    ),
    (
        "rollbacks-last-quarter",
        "Every `pql.rollback` operation in the last quarter, "
        "with the principal who triggered it and the Delta "
        "version range.\n\n"
        "Patterns of repeated rollbacks against the same "
        "`target_table` are a good signal that an upstream "
        "agent prompt is unstable — flag those for the audit "
        "reviewer.",
    ),
    (
        "cost-gate-denials-this-week",
        "Runs the EXPLAIN cost gate **denied** in the last 7 "
        "days. The `cost_gate_trigger` column carries the "
        "engine's verdict as JSON.\n\n"
        "Pair with the `runs/<id>/operations` tab to see which "
        "specific operation hit the gate.",
    ),
    (
        "unacknowledged-external-writes",
        "Delta-log commits that **no `agent_run_operations` "
        "row claims** — still waiting for admin triage.\n\n"
        "These should be empty in steady state. Non-empty "
        "rows mean either an out-of-band Spark/notebook "
        "write or a missing audit hook on a new write path.",
    ),
    (
        "top-mutating-principals-30d",
        "Sum of `rows_affected` from `merge` and `write_table` "
        "ops, grouped by `principal`, over the last 30 days. "
        "Top 20.\n\n"
        "Mirrors the same panel in the Grafana dashboard, but "
        "in SQL so you can pivot into specific runs without "
        "leaving the cockpit.",
    ),
]


def upgrade() -> None:
    bind = op.get_bind()
    for slug, description in _DESCRIPTIONS:
        bind.execute(
            sa.text(
                "UPDATE saved_audit_queries "
                "SET description = :description "
                "WHERE slug = :slug AND is_starter = :true_val"
            ),
            {"slug": slug, "description": description, "true_val": True},
        )


def downgrade() -> None:
    pass
