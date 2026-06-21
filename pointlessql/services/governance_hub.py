"""Governance hub — unified posture + remediation rollup.

The individual governance signals already exist across PointlesSQL
(the compliance scanner logs ``policy.compliance_violation`` audit rows,
the audit cockpit caches per-run anomaly verdicts on ``agent_runs``).
What is missing is a single aggregating view: this module rolls those
findings up into one workspace posture score and a severity-ranked
remediation queue so a steward sees the whole governance surface — and
what to fix first — without visiting each console.

Read-only: every number is derived from rows other subsystems already
wrote, and nothing here mutates a finding.
"""

from __future__ import annotations

import datetime
import json
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.models import AuditLog
from pointlessql.models.agent._runs import AgentRun

#: Audit action the compliance scanner logs one row per finding under.
COMPLIANCE_VIOLATION_ACTION = "policy.compliance_violation"

#: Severities that count toward the posture penalty, worst first.
_ACTIONABLE_SEVERITIES = ("critical", "warn")

#: Posture penalty weights per severity; the score is 100 minus the
#: capped sum so a healthy workspace sits at 100 and a flooded one
#: bottoms out at 0 rather than going negative.
_SEVERITY_WEIGHT = {"critical": 12, "warn": 4}

#: How many findings the remediation queue surfaces.
_QUEUE_LIMIT = 50


def _grade(score: int) -> str:
    """Map a 0–100 posture score to a letter grade."""
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def _normalize_severity(value: Any) -> str:
    """Coerce a raw severity into ``critical`` / ``warn`` / ``info``."""
    text = str(value or "").strip().lower()
    if text in ("critical", "high", "error"):
        return "critical"
    if text in ("warn", "warning", "medium"):
        return "warn"
    return "info"


def _compliance_findings(
    session: Session, *, workspace_id: int, since: datetime.datetime | None
) -> list[dict[str, Any]]:
    """Return the current compliance findings, de-duplicated.

    The scanner appends one audit row per finding on every run, so the
    same open issue recurs across scans.  Rows are read newest-first and
    collapsed on a stable key (target + kind + table/column) so each
    open finding is counted once, at its most recent observation.

    Args:
        session: Active DB session.
        workspace_id: Workspace to scope to.
        since: Lower bound on ``created_at``, or ``None`` for all time.

    Returns:
        One remediation-queue dict per distinct finding.
    """
    stmt = (
        select(AuditLog)
        .where(
            AuditLog.workspace_id == workspace_id,
            AuditLog.action == COMPLIANCE_VIOLATION_ACTION,
        )
        .order_by(AuditLog.created_at.desc())
    )
    if since is not None:
        stmt = stmt.where(AuditLog.created_at >= since)

    seen: set[tuple[str, str, str]] = set()
    findings: list[dict[str, Any]] = []
    for row in session.scalars(stmt).all():
        try:
            detail = json.loads(row.detail) if row.detail else {}
        except TypeError, ValueError:
            detail = {}
        detail_map: dict[str, Any] = (
            cast("dict[str, Any]", detail) if isinstance(detail, dict) else {}
        )
        kind = str(detail_map.get("kind") or "compliance")
        locus = str(detail_map.get("column") or detail_map.get("table") or "")
        key = (row.target, kind, locus)
        if key in seen:
            continue
        seen.add(key)
        findings.append(
            {
                "source": "compliance",
                "kind": kind,
                "severity": _normalize_severity(detail_map.get("severity")),
                "ref": detail_map.get("table") or detail_map.get("column") or row.target,
                "message": str(detail_map.get("message") or kind),
                "observed_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return findings


def _anomaly_findings(
    session: Session, *, workspace_id: int, since: datetime.datetime | None
) -> list[dict[str, Any]]:
    """Return one finding per agent run carrying an anomaly verdict.

    Args:
        session: Active DB session.
        workspace_id: Workspace to scope to.
        since: Lower bound on ``started_at``, or ``None`` for all time.

    Returns:
        One remediation-queue dict per anomalous run.
    """
    stmt = (
        select(AgentRun)
        .where(
            AgentRun.workspace_id == workspace_id,
            AgentRun.anomaly_severity.in_(_ACTIONABLE_SEVERITIES),
        )
        .order_by(AgentRun.started_at.desc())
    )
    if since is not None:
        stmt = stmt.where(AgentRun.started_at >= since)

    findings: list[dict[str, Any]] = []
    for row in session.scalars(stmt).all():
        findings.append(
            {
                "source": "anomaly",
                "kind": f"run_anomaly:{row.anomaly_metric or 'unknown'}",
                "severity": _normalize_severity(row.anomaly_severity),
                "ref": row.id,
                "message": (
                    f"Agent run flagged {row.anomaly_severity} on "
                    f"{row.anomaly_metric or 'a metric'}"
                ),
                "observed_at": row.started_at.isoformat() if row.started_at else None,
            }
        )
    return findings


def governance_posture(
    session_factory: sessionmaker[Session],
    *,
    workspace_id: int,
    since: datetime.datetime | None = None,
) -> dict[str, Any]:
    """Roll the workspace's governance findings into one posture view.

    Collects the de-duplicated compliance findings and the anomalous
    agent runs, scores the workspace's posture from their weighted
    severities, and returns a severity-ranked remediation queue.

    Args:
        session_factory: Sessionmaker callable for the metadata DB.
        workspace_id: Workspace whose posture to compute.
        since: Lower bound on a finding's timestamp; ``None`` spans all.

    Returns:
        A JSON-safe dict with the ``posture_score`` (0–100), letter
        ``grade``, ``totals`` (per-severity + per-source counts), and a
        capped, critical-first ``remediation_queue``.
    """
    with session_factory() as session:
        findings = _compliance_findings(
            session, workspace_id=workspace_id, since=since
        ) + _anomaly_findings(session, workspace_id=workspace_id, since=since)

    by_severity: dict[str, int] = {"critical": 0, "warn": 0, "info": 0}
    by_source: dict[str, int] = {"compliance": 0, "anomaly": 0}
    for finding in findings:
        by_severity[finding["severity"]] = by_severity.get(finding["severity"], 0) + 1
        by_source[finding["source"]] = by_source.get(finding["source"], 0) + 1

    penalty = min(
        100,
        sum(_SEVERITY_WEIGHT.get(sev, 0) * count for sev, count in by_severity.items()),
    )
    score = 100 - penalty

    severity_rank = {"critical": 0, "warn": 1, "info": 2}
    queue = sorted(findings, key=lambda f: (severity_rank.get(f["severity"], 3), f["source"]))

    return {
        "posture_score": score,
        "grade": _grade(score),
        "totals": {
            "findings": len(findings),
            "critical": by_severity["critical"],
            "warn": by_severity["warn"],
            "info": by_severity["info"],
            "compliance": by_source["compliance"],
            "anomaly": by_source["anomaly"],
        },
        "remediation_queue": queue[:_QUEUE_LIMIT],
    }
