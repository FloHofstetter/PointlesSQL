"""Canonical specs for the audit cockpit's built-in saved queries.

The audit cockpit ships five starter saved queries (``is_starter=True``,
``owner_id=NULL``) that survive any user deletion. This module is the single
source of truth for their specs so both the seeding migration and the runtime
idempotent re-seed
(:func:`pointlessql.services.audit.saved_queries.bootstrap_starter_rows`) build
identical rows. The SQL fragments are raw strings the runtime executes via
``text()`` without dialect translation, so the date arithmetic is rendered
per-dialect here rather than left to SQLAlchemy.
"""

from __future__ import annotations


def _date_minus(days: int, dialect_name: str) -> str:
    """Return a dialect-correct "now minus N days" SQL fragment.

    SQLite ships ``datetime('now', '-N days')``; Postgres needs
    ``NOW() - INTERVAL 'N days'``. The starter rows below ship as raw SQL
    strings the runtime executes via ``text()`` without dialect translation,
    so the fragment must already be correct for the target backend.

    Args:
        days: Number of days to subtract from the current timestamp.
        dialect_name: SQLAlchemy dialect name (e.g. ``"postgresql"``).

    Returns:
        A SQL expression string evaluating to "now minus *days* days".
    """
    if dialect_name == "postgresql":
        return f"NOW() - INTERVAL '{days} days'"
    return f"datetime('now', '-{days} days')"


def starter_rows(dialect_name: str) -> list[dict[str, object]]:
    """Build the five starter saved-query specs with dialect-correct dates.

    Args:
        dialect_name: SQLAlchemy dialect name, used to render the date
            arithmetic embedded in each query's SQL.

    Returns:
        One dict per starter query, each carrying ``slug``, ``title``,
        ``description``, and ``sql_text`` keys.
    """
    d90 = _date_minus(90, dialect_name)
    d30 = _date_minus(30, dialect_name)
    d7 = _date_minus(7, dialect_name)
    return [
        {
            "slug": "pii-writes-last-90d",
            "title": "PII writes — last 90 days",
            "description": (
                "Every `lineage_value_changes` row whose `target_column` "
                "contains the substring `pii` over the last 90 days.\n\n"
                "**When to use:**\n\n"
                "- GDPR Art. 30 evidence — show every PII mutation in a "
                "compliance window.\n"
                "- Investigate after a data-protection incident; pivot "
                "into the row-trace UI from any returned `run_id`.\n"
            ),
            "sql_text": (
                "SELECT vc.run_id, vc.op_id, vc.target_table, vc.target_column,"
                " vc.target_row_id, vc.old_value, vc.new_value, vc.created_at\n"
                "FROM lineage_value_changes vc\n"
                "WHERE LOWER(vc.target_column) LIKE '%pii%'\n"
                f"  AND vc.created_at >= {d90}\n"
                "ORDER BY vc.created_at DESC\n"
                "LIMIT 1000"
            ),
        },
        {
            "slug": "rollbacks-last-quarter",
            "title": "Rollbacks — last 90 days",
            "description": (
                "Every `pql.rollback` operation in the last quarter, "
                "with the principal who triggered it and the Delta "
                "version range.\n\n"
                "Patterns of repeated rollbacks against the same "
                "`target_table` are a good signal that an upstream "
                "agent prompt is unstable — flag those for the audit "
                "reviewer."
            ),
            "sql_text": (
                "SELECT r.id AS run_id, r.principal, r.agent_id,"
                " o.target_table, o.delta_version_before, o.delta_version_after,"
                " o.started_at\n"
                "FROM agent_run_operations o\n"
                "JOIN agent_runs r ON r.id = o.agent_run_id\n"
                "WHERE o.op_name = 'rollback'\n"
                f"  AND o.started_at >= {d90}\n"
                "ORDER BY o.started_at DESC"
            ),
        },
        {
            "slug": "cost-gate-denials-this-week",
            "title": "Cost-gate denials — this week",
            "description": (
                "Runs the EXPLAIN cost gate **denied** in the last 7 "
                "days. The `cost_gate_trigger` column carries the "
                "engine's verdict as JSON.\n\n"
                "Pair with the `runs/<id>/operations` tab to see which "
                "specific operation hit the gate."
            ),
            "sql_text": (
                "SELECT id, principal, agent_id, notebook_path, status,"
                " cost_gate_trigger, started_at\n"
                "FROM agent_runs\n"
                "WHERE status = 'denied'\n"
                "  AND cost_gate_trigger IS NOT NULL\n"
                f"  AND started_at >= {d7}\n"
                "ORDER BY started_at DESC"
            ),
        },
        {
            "slug": "unacknowledged-external-writes",
            "title": "Unacknowledged external writes",
            "description": (
                "Delta-log commits that **no `agent_run_operations` "
                "row claims** — still waiting for admin triage.\n\n"
                "These should be empty in steady state. Non-empty "
                "rows mean either an out-of-band Spark/notebook "
                "write or a missing audit hook on a new write path."
            ),
            "sql_text": (
                "SELECT id, table_fqn, delta_version, commit_timestamp, detected_at\n"
                "FROM unattributed_writes\n"
                "WHERE acknowledged_at IS NULL\n"
                "ORDER BY detected_at DESC"
            ),
        },
        {
            "slug": "top-mutating-principals-30d",
            "title": "Top mutating principals — last 30 days",
            "description": (
                "Sum of `rows_affected` from `merge` and `write_table` "
                "ops, grouped by `principal`, over the last 30 days. "
                "Top 20.\n\n"
                "Mirrors the same panel in the Grafana dashboard, but "
                "in SQL so you can pivot into specific runs without "
                "leaving the cockpit."
            ),
            "sql_text": (
                "SELECT COALESCE(r.principal, '<unknown>') AS principal,"
                " COALESCE(SUM(o.rows_affected), 0) AS rows_written\n"
                "FROM agent_runs r\n"
                "JOIN agent_run_operations o ON o.agent_run_id = r.id\n"
                "WHERE o.op_name IN ('merge', 'write_table')\n"
                f"  AND r.started_at >= {d30}\n"
                "GROUP BY r.principal\n"
                "ORDER BY rows_written DESC\n"
                "LIMIT 20"
            ),
        },
    ]
