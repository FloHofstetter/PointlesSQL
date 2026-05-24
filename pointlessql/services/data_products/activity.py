"""Activity-feed aggregator per data product.

Merges four source streams into one chronologically-sorted feed:

1. ``agent_run_operations`` rows whose ``target_table`` starts with
   ``{dp.catalog_name}.{dp.schema_name}.``  — *authoritative* write
   stream (every pql.write / pql.merge etc.).
2. ``audit_log`` rows whose ``target`` contains the DP catalog or
   schema reference — best-effort, free-form text match.
3. ``data_product_contract_events`` rows where
   ``data_product_id = dp.id`` — Phase 50 contract validations.
4. ``governance_events`` rows of type
   ``pointlessql.data_product.sla_violated`` whose payload's
   ``data_product_ref`` matches the DP — Phase 50.4 freshness.

Heuristics:

* AuditLog matching is a substring scan on ``target`` (the column
  is free-form, e.g. ``"catalog:my_cat"``).  Not 100% precise; the
  agent-run-ops stream is the reliable one.
* Each ``ActivityRow.source_url`` deep-links back into the
  corresponding feature page so the Activity tab acts as a
  navigation hub.
"""

from __future__ import annotations

import datetime
import json
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select

from pointlessql.models.agent._audit import AgentRunOperation
from pointlessql.models.audit._log import AuditLog
from pointlessql.models.audit._sinks import GovernanceEvent
from pointlessql.models.catalog._data_products import (
    DataProduct,
    DataProductContractEvent,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActivityRow:
    """One row in the merged Activity feed.

    Attributes:
        kind: Source stream label — ``"agent_op"`` /
            ``"audit"`` / ``"contract"`` / ``"freshness"``.
        ts: ISO-8601 timestamp.
        summary: Short single-line markdown for the inbox row.
        source_id: Source-table primary key (so the UI can stamp
            a unique ``data-activity-id`` attribute).
        source_url: Click-through URL.
    """

    kind: str
    ts: str
    summary: str
    source_id: int
    source_url: str


def _ts(value: datetime.datetime) -> str:
    """Render a datetime as ISO-8601 UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.UTC)
    return value.astimezone(datetime.UTC).isoformat()


def fetch_activity_for_dp(
    session: Any,
    *,
    workspace_id: int,
    dp: DataProduct,
    limit: int = 50,
    offset: int = 0,
) -> list[ActivityRow]:
    """Return up to *limit* rows of merged activity for *dp*, newest first.

    Pagination is post-merge (the four streams are fetched with
    their own per-stream ``limit + offset`` headroom + a hard cap
    of 200 rows per stream so a single high-traffic stream can't
    starve the others).

    Args:
        session: Live SQLAlchemy session bound to the metadata DB.
        workspace_id: Active workspace.
        dp: The :class:`DataProduct` we're fetching activity for.
        limit: Max rows to return.
        offset: Number of merged rows to skip (post-sort).

    Returns:
        Sorted list of :class:`ActivityRow`.
    """
    fqn_prefix = f"{dp.catalog_name}.{dp.schema_name}."
    per_stream_cap = max(50, limit * 2)

    rows: list[ActivityRow] = []

    # Stream 1: agent_run_operations.
    op_rows = session.execute(
        select(AgentRunOperation)
        .where(
            AgentRunOperation.workspace_id == workspace_id,
            AgentRunOperation.target_table.like(f"{fqn_prefix}%"),
        )
        .order_by(AgentRunOperation.started_at.desc())
        .limit(per_stream_cap)
    ).scalars().all()
    for op in op_rows:
        rows.append(
            ActivityRow(
                kind="agent_op",
                ts=_ts(op.started_at),
                summary=(
                    f"`{op.op_name}` on `{op.target_table}` "
                    f"({op.rows_affected or 0} rows)"
                ),
                source_id=op.id,
                source_url=f"/runs/{op.agent_run_id}#op-{op.id}",
            )
        )

    # Stream 2: audit_log (free-form ``target`` column).  We match
    # any row whose target contains the DP catalog or schema name;
    # the heuristic is documented at module level.
    audit_rows = session.execute(
        select(AuditLog)
        .where(
            AuditLog.workspace_id == workspace_id,
            or_(
                AuditLog.target.like(f"%{dp.catalog_name}%"),
                AuditLog.target.like(f"%{dp.schema_name}%"),
            ),
        )
        .order_by(AuditLog.created_at.desc())
        .limit(per_stream_cap)
    ).scalars().all()
    for a in audit_rows:
        rows.append(
            ActivityRow(
                kind="audit",
                ts=_ts(a.created_at),
                summary=(
                    f"`{a.action}` on `{a.target}` by "
                    f"{a.user_email or 'system'}"
                ),
                source_id=a.id,
                source_url=f"/audit/log?id={a.id}",
            )
        )

    # Stream 3: data_product_contract_events.
    contract_rows = session.execute(
        select(DataProductContractEvent)
        .where(DataProductContractEvent.data_product_id == dp.id)
        .order_by(DataProductContractEvent.created_at.desc())
        .limit(per_stream_cap)
    ).scalars().all()
    for ev in contract_rows:
        rows.append(
            ActivityRow(
                kind="contract",
                ts=_ts(ev.created_at),
                summary=f"contract outcome: **{ev.outcome}**",
                source_id=ev.id,
                source_url=(
                    f"/runs?op={ev.agent_run_operation_id}"
                    if ev.agent_run_operation_id is not None
                    else f"/data-products/{dp.catalog_name}/{dp.schema_name}#tab-compliance"
                ),
            )
        )

    # Stream 4: governance_events (sla_violated).
    gov_rows = session.execute(
        select(GovernanceEvent)
        .where(
            GovernanceEvent.workspace_id == workspace_id,
            GovernanceEvent.event_type == "pointlessql.data_product.sla_violated",
        )
        .order_by(GovernanceEvent.fired_at.desc())
        .limit(per_stream_cap)
    ).scalars().all()
    for gv in gov_rows:
        payload: dict[str, Any] = {}
        try:
            envelope: dict[str, Any] = json.loads(gv.payload_json or "{}")
            raw = envelope.get("data", {})
            if isinstance(raw, dict):
                payload = raw
        except (ValueError, TypeError):
            payload = {}
        ref_value: Any = payload.get("data_product_ref") or payload.get("ref")
        ref: str | None = ref_value if isinstance(ref_value, str) else None
        if ref is not None and ref != f"{dp.catalog_name}.{dp.schema_name}":
            continue
        age_minutes: Any = payload.get("age_minutes", "?")
        rows.append(
            ActivityRow(
                kind="freshness",
                ts=_ts(gv.fired_at),
                summary=f"SLA violated (age `{age_minutes}` min)",
                source_id=gv.id,
                source_url=(
                    f"/data-products/{dp.catalog_name}/{dp.schema_name}#tab-compliance"
                ),
            )
        )

    rows.sort(key=lambda r: r.ts, reverse=True)
    return rows[offset : offset + limit]
