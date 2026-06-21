"""Lakebase ops — autonomous health assessment over synced/online tables.

PointlesSQL already runs a "Lakebase-lite": reverse-ETL of Delta tables
into a low-latency serving target (:class:`SyncedTable`), with a sync
lifecycle (idle / syncing / ok / failed) and a Delta-version cursor.
The autonomous-database-operations idea is a governance surface on top:
agents watch table health, flag slowdowns / failures, and *propose*
fixes (resync, set keys, add a serving index) for a human to approve.

This module is that read-only health + recommendation engine.  It
derives a per-table health verdict and a list of advisory
recommendations from the synced-table state — it never executes a fix;
applying an index or recovery in the serving Postgres stays engine-side.
The recommendations are the propose-half of a propose-and-approve flow.
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from pointlessql.models.synced_tables import SyncedTable
from pointlessql.services.synced_tables import list_synced_tables, parse_primary_keys

#: Minutes after a successful sync before the data is considered stale.
_DEFAULT_STALE_AFTER_MINUTES = 60


def _recommendation(action: str, severity: str, title: str, detail: str) -> dict[str, str]:
    """Build one advisory recommendation row."""
    return {"action": action, "severity": severity, "title": title, "detail": detail}


def _sync_age_minutes(
    last_synced_at: datetime.datetime | None, now: datetime.datetime
) -> float | None:
    """Return minutes since the last successful sync, or ``None``.

    Args:
        last_synced_at: Timestamp of the last sync (may be tz-naive from
            a SQLite round-trip — assumed UTC).
        now: The timezone-aware reference clock.

    Returns:
        Age in minutes, or ``None`` when never synced.
    """
    if last_synced_at is None:
        return None
    stamp = last_synced_at
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=datetime.UTC)
    return (now - stamp).total_seconds() / 60.0


def assess_synced_table(
    row: SyncedTable,
    *,
    now: datetime.datetime,
    stale_after_minutes: int = _DEFAULT_STALE_AFTER_MINUTES,
) -> dict[str, Any]:
    """Assess one synced table's health + advisory recommendations.

    Args:
        row: The synced-table row to assess.
        now: Timezone-aware reference clock for staleness.
        stale_after_minutes: Age past which an ``ok`` table is flagged
            stale.

    Returns:
        A JSON-safe dict with the table identity, ``health`` (one of
        ``healthy`` / ``syncing`` / ``degraded`` / ``critical``), the
        sync age, and a severity-tagged ``recommendations`` list.
    """
    age = _sync_age_minutes(row.last_synced_at, now)
    pks = parse_primary_keys(row.primary_keys)
    recommendations: list[dict[str, str]] = []

    if row.status == "failed":
        recommendations.append(
            _recommendation(
                "investigate_failure",
                "critical",
                "Recover from the last sync failure",
                row.last_error or "The most recent sync failed; review and re-run it.",
            )
        )
    if row.status == "idle" and row.last_synced_at is None:
        recommendations.append(
            _recommendation(
                "initial_sync",
                "warn",
                "Run the first sync",
                "This online table has never been populated from its source.",
            )
        )
    elif row.status == "ok" and age is not None and age > stale_after_minutes:
        recommendations.append(
            _recommendation(
                "resync",
                "warn",
                "Refresh stale serving data",
                f"Last synced {int(age)} minutes ago (threshold {stale_after_minutes}).",
            )
        )
    if row.mode == "cdf" and not pks:
        recommendations.append(
            _recommendation(
                "set_primary_keys",
                "warn",
                "Set primary keys for incremental sync",
                "CDF mode needs primary keys to apply upserts and deletes.",
            )
        )
    if pks and row.status == "ok":
        recommendations.append(
            _recommendation(
                "add_serving_index",
                "info",
                "Consider a serving index",
                f"Index {row.target_table}({', '.join(pks)}) to speed point lookups.",
            )
        )

    severities = {rec["severity"] for rec in recommendations}
    if "critical" in severities:
        health = "critical"
    elif row.status == "syncing":
        health = "syncing"
    elif "warn" in severities:
        health = "degraded"
    else:
        health = "healthy"

    return {
        "name": row.name,
        "source_fqn": row.source_fqn,
        "target_table": row.target_table,
        "mode": row.mode,
        "status": row.status,
        "health": health,
        "last_synced_at": row.last_synced_at.isoformat() if row.last_synced_at else None,
        "sync_age_minutes": round(age, 1) if age is not None else None,
        "last_error": row.last_error,
        "recommendations": recommendations,
    }


def ops_overview(
    session_factory: sessionmaker[Session],
    *,
    workspace_id: int,
    now: datetime.datetime,
    stale_after_minutes: int = _DEFAULT_STALE_AFTER_MINUTES,
) -> dict[str, Any]:
    """Assess every synced table in a workspace into one ops view.

    Args:
        session_factory: Sessionmaker callable for the metadata DB.
        workspace_id: Workspace whose synced tables to assess.
        now: Timezone-aware reference clock.
        stale_after_minutes: Staleness threshold passed to each
            assessment.

    Returns:
        A JSON-safe dict with a ``tables`` list (worst health first), a
        ``summary`` count per health, and the total ``open_recommendations``.
    """
    rows = list_synced_tables(session_factory, workspace_id=workspace_id)
    tables = [
        assess_synced_table(row, now=now, stale_after_minutes=stale_after_minutes) for row in rows
    ]

    summary = {"healthy": 0, "syncing": 0, "degraded": 0, "critical": 0}
    open_recommendations = 0
    for table in tables:
        summary[table["health"]] = summary.get(table["health"], 0) + 1
        open_recommendations += len(table["recommendations"])

    rank = {"critical": 0, "degraded": 1, "syncing": 2, "healthy": 3}
    tables.sort(key=lambda t: (rank.get(t["health"], 4), t["name"]))

    return {
        "tables": tables,
        "summary": summary,
        "total": len(tables),
        "open_recommendations": open_recommendations,
    }
