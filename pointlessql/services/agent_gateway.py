"""Agent gateway — read-only governance overlay over agent runs.

PointlesSQL registers agent runs from external runtimes (the
``agent_runs`` table); this module is the AI-Gateway-style governance
*lens* on that registry.  It rolls the supervised runs up by their
harness (the agent framework / meta-harness that produced them) and by
principal, sums the per-run cost estimates into a spend-telemetry view,
and — when the caller supplies a budget amount — evaluates the accrued
spend against warn / block thresholds with the shared cost-budget
evaluator.

The overlay is deliberately read-side only: every number is derived
from rows a runtime already POSTed, and nothing here mutates a run.
Live policy enforcement — routing a call only to an approved harness,
or blocking a run mid-flight once a budget is exhausted — is the
runtime's job and is intentionally outside this read model.
"""

from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from pointlessql.models.agent._runs import (
    STATUS_DENIED,
    STATUS_FAILED,
    STATUS_SUCCEEDED,
    TERMINAL_STATUSES,
    AgentRun,
)
from pointlessql.services.cost import evaluate_budget
from pointlessql.types import SessionFactory

#: Placeholder bucket key for runs that did not report a harness, so the
#: rollup never silently drops their spend.
UNSPECIFIED_HARNESS = "(unspecified)"

#: Placeholder bucket key for runs that did not report a principal.
UNSPECIFIED_PRINCIPAL = "(unattributed)"

#: Cap on the recent-runs detail list returned alongside the rollups.
_RECENT_RUNS_LIMIT = 50


@dataclasses.dataclass
class _Bucket:
    """Mutable accumulator for one harness or principal group.

    Attributes:
        key: The harness name or principal the bucket aggregates.
        run_count: Total runs that fell into the bucket.
        active: Runs in a non-terminal state.
        succeeded: Runs that terminated successfully.
        failed: Runs that terminated as failed.
        denied: Runs that terminated as denied.
        total_cost: Sum of ``cost_est`` over runs that carried one.
        costed_runs: How many runs contributed to ``total_cost``.
        members: Distinct values of the *other* dimension seen (the
            principal set for a harness bucket, and vice versa).
    """

    key: str
    run_count: int = 0
    active: int = 0
    succeeded: int = 0
    failed: int = 0
    denied: int = 0
    total_cost: Decimal = Decimal("0")
    costed_runs: int = 0
    members: set[str] = dataclasses.field(default_factory=set[str])

    def add(self, *, status: str, cost: Decimal | None, member: str | None) -> None:
        """Fold one run into the bucket's running totals.

        Args:
            status: The run's lifecycle status.
            cost: The run's ``cost_est`` (``None`` when unset).
            member: The cross-dimension value (principal for a harness
                bucket, harness for a principal bucket) to count as
                distinct, or ``None`` to skip.
        """
        self.run_count += 1
        if status == STATUS_SUCCEEDED:
            self.succeeded += 1
        elif status == STATUS_FAILED:
            self.failed += 1
        elif status == STATUS_DENIED:
            self.denied += 1
        if status not in TERMINAL_STATUSES:
            self.active += 1
        if cost is not None:
            self.total_cost += cost
            self.costed_runs += 1
        if member:
            self.members.add(member)


def _bucket_dict(bucket: _Bucket, *, member_key: str) -> dict[str, Any]:
    """Serialize a bucket into a JSON-safe rollup row.

    Args:
        bucket: The accumulated bucket.
        member_key: Output key for the distinct-member count
            (``distinct_principals`` or ``distinct_harnesses``).

    Returns:
        A plain dict with the run/status counts, spend totals, an
        average over the costed runs, and the distinct-member count.
    """
    avg_cost = float(bucket.total_cost / bucket.costed_runs) if bucket.costed_runs else None
    return {
        "key": bucket.key,
        "run_count": bucket.run_count,
        "active": bucket.active,
        "succeeded": bucket.succeeded,
        "failed": bucket.failed,
        "denied": bucket.denied,
        "total_cost": float(bucket.total_cost),
        "avg_cost": avg_cost,
        member_key: len(bucket.members),
    }


def _sort_key(row: dict[str, Any]) -> tuple[float, int]:
    """Rank rollup rows by spend then run volume, both descending."""
    return (row["total_cost"], row["run_count"])


def gateway_overview(
    session_factory: SessionFactory,
    *,
    workspace_id: int,
    since: datetime.datetime | None = None,
    budget: Decimal | None = None,
) -> dict[str, Any]:
    """Build the governance overlay for one workspace's agent runs.

    Loads every run in the workspace (optionally only those started at
    or after *since*), rolls the runs up by harness and by principal,
    and — when *budget* is given — evaluates the total accrued spend
    against the budget's warn / block thresholds.

    Args:
        session_factory: Sessionmaker callable for the metadata DB.
        workspace_id: Workspace whose runs form the overlay.
        since: Lower bound on ``started_at``; ``None`` spans all runs.
        budget: Spend ceiling to evaluate the accrued cost against, or
            ``None`` to skip the budget verdict.

    Returns:
        A JSON-safe dict with ``totals`` (run/active counts, spend, and
        distinct harness/principal counts), ``by_harness`` and
        ``by_principal`` rollup lists sorted by spend, a capped
        ``recent_runs`` detail list, and ``budget`` (the
        :func:`evaluate_budget` verdict, or ``None`` when no budget was
        supplied).
    """
    harness_buckets: dict[str, _Bucket] = {}
    principal_buckets: dict[str, _Bucket] = {}
    recent_runs: list[dict[str, Any]] = []
    total_cost = Decimal("0")
    run_count = 0
    active_count = 0

    with session_factory() as session:
        stmt = (
            select(AgentRun)
            .where(AgentRun.workspace_id == workspace_id)
            .order_by(AgentRun.started_at.desc())
        )
        if since is not None:
            stmt = stmt.where(AgentRun.started_at >= since)
        for row in session.scalars(stmt).all():
            harness = (row.harness or "").strip() or UNSPECIFIED_HARNESS
            principal = (row.principal or "").strip() or UNSPECIFIED_PRINCIPAL
            cost = row.cost_est
            run_count += 1
            if row.status not in TERMINAL_STATUSES:
                active_count += 1
            if cost is not None:
                total_cost += cost

            harness_buckets.setdefault(harness, _Bucket(harness)).add(
                status=row.status, cost=cost, member=principal
            )
            principal_buckets.setdefault(principal, _Bucket(principal)).add(
                status=row.status, cost=cost, member=harness
            )
            if len(recent_runs) < _RECENT_RUNS_LIMIT:
                recent_runs.append(
                    {
                        "id": row.id,
                        "harness": row.harness,
                        "principal": row.principal,
                        "agent_id": row.agent_id,
                        "status": row.status,
                        "cost_est": float(cost) if cost is not None else None,
                        "started_at": row.started_at.isoformat() if row.started_at else None,
                    }
                )

    by_harness = sorted(
        (_bucket_dict(b, member_key="distinct_principals") for b in harness_buckets.values()),
        key=_sort_key,
        reverse=True,
    )
    by_principal = sorted(
        (_bucket_dict(b, member_key="distinct_harnesses") for b in principal_buckets.values()),
        key=_sort_key,
        reverse=True,
    )

    budget_block: dict[str, Any] | None = None
    if budget is not None:
        verdict = evaluate_budget(total_cost, budget)
        budget_block = {
            "amount": float(budget),
            "accrued": float(total_cost),
            "status": verdict.status,
            "percent_used": round(verdict.percent_used, 2),
            "signal_kind": verdict.signal_kind,
        }

    return {
        "totals": {
            "run_count": run_count,
            "active": active_count,
            "total_cost": float(total_cost),
            "distinct_harnesses": len(harness_buckets),
            "distinct_principals": len(principal_buckets),
        },
        "by_harness": by_harness,
        "by_principal": by_principal,
        "recent_runs": recent_runs,
        "budget": budget_block,
    }
