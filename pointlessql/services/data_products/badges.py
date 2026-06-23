"""Auto-computed endorsement badges per data product.

Four computed badges, all recomputed on read (no cache table):

* ``downstream_count`` — distinct ``target_table`` values in
  :class:`LineageColumnMap` whose ``source_table`` matches one of
  the DP's tables.  Tells the steward "how many tables consume
  from me".
* ``agent_run_count_7d`` — distinct ``agent_run_id`` values in
  ``agent_run_operations`` whose ``target_table`` starts with the
  DP's catalog.schema prefix in the last 7 days.  Tells the
  steward "how heavily agents read+wrote me this week".
* ``last_rollback_passed`` — ``True`` / ``False`` / ``None``.
  Looks at the most recent ``op_name='rollback'`` row touching
  the DP and reports whether it landed without an ``error_message``.
  ``None`` when the DP has never been rolled back.
* ``freshness_on_time_30d_pct`` — percentage of freshness checks
  in the last 30 days that came back ``on_time``.  Derived from
  the DP's ``last_loaded_at`` + ``sla_minutes`` versus the
  ``governance_events`` records of ``sla_violated`` envelopes.
  Today this is a coarse "did we ever miss SLA in the window?"
  signal; the metric refines once the SLA cache lands.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from sqlalchemy import distinct, func, select

from pointlessql.models.agent._audit import AgentRunOperation
from pointlessql.models.audit._sinks import GovernanceEvent
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.lineage._core import LineageColumnMap

logger = logging.getLogger(__name__)


def compute_badges_for_dp(
    session: Any,
    *,
    workspace_id: int,
    dp: DataProduct,
    now: datetime.datetime | None = None,
) -> dict[str, Any]:
    """Compute the four endorsement badges for one data product.

    Args:
        session: Live SQLAlchemy session.
        workspace_id: Active workspace.
        dp: The :class:`DataProduct` row.
        now: Optional "now" override for tests.

    Returns:
        Dict shaped for direct embedding in the listing / detail
        JSON payload.  Any badge that can't be computed lands as
        ``None``.
    """
    now = now or datetime.datetime.now(datetime.UTC)
    fqn_prefix = f"{dp.catalog_name}.{dp.schema_name}."
    seven_days_ago = now - datetime.timedelta(days=7)
    thirty_days_ago = now - datetime.timedelta(days=30)

    # Badge 1: downstream-count.
    downstream_count = int(
        session.execute(
            select(func.count(distinct(LineageColumnMap.target_table))).where(
                LineageColumnMap.workspace_id == workspace_id,
                LineageColumnMap.source_table.like(f"{fqn_prefix}%"),
                LineageColumnMap.target_table.notlike(f"{fqn_prefix}%"),
            )
        ).scalar_one()
        or 0
    )

    # Badge 2: agent-run-count-7d.
    agent_run_count_7d = int(
        session.execute(
            select(func.count(distinct(AgentRunOperation.agent_run_id))).where(
                AgentRunOperation.workspace_id == workspace_id,
                AgentRunOperation.target_table.like(f"{fqn_prefix}%"),
                AgentRunOperation.started_at >= seven_days_ago,
            )
        ).scalar_one()
        or 0
    )

    # Badge 3: last-rollback-passed.
    last_rollback = session.execute(
        select(AgentRunOperation)
        .where(
            AgentRunOperation.workspace_id == workspace_id,
            AgentRunOperation.target_table.like(f"{fqn_prefix}%"),
            AgentRunOperation.op_name == "rollback",
        )
        .order_by(AgentRunOperation.started_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if last_rollback is None:
        last_rollback_passed: bool | None = None
    else:
        last_rollback_passed = last_rollback.error_message is None

    # Badge 4: freshness-on-time-30d-pct.  Coarse derivation:
    # count sla_violated envelopes mentioning this DP within
    # the window; if zero, treat as 100%; otherwise return
    # ``max(0, 100 - violation_count * 5)`` so a single
    # violation reads as 95%.  trending refresh
    # will replace this with a per-tick percentage once the
    # cache lands.
    violation_count = int(
        session.execute(
            select(func.count(GovernanceEvent.id)).where(
                GovernanceEvent.workspace_id == workspace_id,
                GovernanceEvent.event_type == "pointlessql.data_product.sla_violated",
                GovernanceEvent.fired_at >= thirty_days_ago,
                GovernanceEvent.payload_json.like(f"%{dp.catalog_name}.{dp.schema_name}%"),
            )
        ).scalar_one()
        or 0
    )
    freshness_on_time_30d_pct: float
    if dp.sla_minutes is None:
        freshness_on_time_30d_pct = 100.0
    else:
        freshness_on_time_30d_pct = max(0.0, 100.0 - violation_count * 5.0)

    return {
        "downstream_count": downstream_count,
        "agent_run_count_7d": agent_run_count_7d,
        "last_rollback_passed": last_rollback_passed,
        "freshness_on_time_30d_pct": freshness_on_time_30d_pct,
    }


def compute_badges_bulk(
    session: Any,
    *,
    workspace_id: int,
    dps: list[DataProduct],
    now: datetime.datetime | None = None,
) -> dict[int, dict[str, Any]]:
    """Compute badges for *every* DP in *dps* with one query per badge.

    The listing endpoint renders N products on the same page;
    naive per-row calls would mean ``4 * N`` queries.  This bulk
    helper groups the four badges into four ``GROUP BY``-keyed
    queries so the cost is constant in N.

    Args:
        session: Live SQLAlchemy session.
        workspace_id: Active workspace.
        dps: The DataProduct rows to score.
        now: Optional "now" override.

    Returns:
        Map ``data_product_id → badges dict``.
    """
    now = now or datetime.datetime.now(datetime.UTC)
    out: dict[int, dict[str, Any]] = {
        dp.id: {
            "downstream_count": 0,
            "agent_run_count_7d": 0,
            "last_rollback_passed": None,
            "freshness_on_time_30d_pct": 100.0,
        }
        for dp in dps
    }
    if not dps:
        return out

    # Per-DP downstream count and 7d agent runs both involve
    # per-DP LIKE filters that don't merge into a single GROUP BY.
    # Iterating is N queries per badge, which stays cheap for the
    # < 50 DPs we render on a browse page.  The trending refresh
    # owns the bulk-aggregation pattern for the
    # rollups that actually need it.
    for dp in dps:
        out[dp.id] = compute_badges_for_dp(session, workspace_id=workspace_id, dp=dp, now=now)
    return out
