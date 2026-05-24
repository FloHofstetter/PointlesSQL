"""Auto-generated data-product passport renderer.

Two callables:

* :func:`render_passport` — pure-function: takes a session + DP,
  returns ``(body_md, stats)`` where ``stats`` carries the
  upstream / downstream snapshot the passport row stores.
* :func:`refresh_passport_for_dp` — UPSERTs a new
  :class:`DataProductPassport` row with monotonic
  ``version_int`` per ``(workspace, dp)``.

The renderer reads:

* :class:`LineageColumnMap` for source + downstream table sets.
* :class:`DataProductContractEvent` (last 30d) for the
  freshness profile.
* :func:`fetch_activity_for_dp` for the recent-activity
  bullet list (5 most-recent rows).
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

from sqlalchemy import func, select

from pointlessql.models.catalog._data_product_passport import DataProductPassport
from pointlessql.models.catalog._data_products import (
    DataProduct,
    DataProductContractEvent,
)
from pointlessql.models.lineage._core import LineageColumnMap
from pointlessql.services.data_products.activity import fetch_activity_for_dp

logger = logging.getLogger(__name__)


def _collect_lineage_tables(
    session: Any,
    *,
    workspace_id: int,
    dp_prefix: str,
) -> tuple[list[str], list[str], int]:
    """Return (sources, downstream, edge_count) for one DP's tables.

    Args:
        session: Live SQLAlchemy session.
        workspace_id: Tenant scope.
        dp_prefix: ``"catalog.schema."`` prefix to match
            ``target_table`` / ``source_table`` against.

    Returns:
        ``(sorted_unique_sources, sorted_unique_downstream,
        total_edge_count)``.
    """
    src_rows = (
        session.execute(
            select(LineageColumnMap.source_table).where(
                LineageColumnMap.workspace_id == workspace_id,
                LineageColumnMap.target_table.like(f"{dp_prefix}%"),
                LineageColumnMap.source_table.is_not(None),
            )
        )
        .scalars()
        .all()
    )
    sources = sorted({s for s in src_rows if s and not s.startswith(dp_prefix)})

    down_rows = (
        session.execute(
            select(LineageColumnMap.target_table).where(
                LineageColumnMap.workspace_id == workspace_id,
                LineageColumnMap.source_table.like(f"{dp_prefix}%"),
                LineageColumnMap.target_table.is_not(None),
            )
        )
        .scalars()
        .all()
    )
    downstream = sorted({t for t in down_rows if t and not t.startswith(dp_prefix)})

    total_edges = int(
        session.execute(
            select(func.count(LineageColumnMap.id)).where(
                LineageColumnMap.workspace_id == workspace_id,
                LineageColumnMap.target_table.like(f"{dp_prefix}%"),
            )
        ).scalar_one()
        or 0
    )
    return sources, downstream, total_edges


def _freshness_summary(
    session: Any,
    *,
    workspace_id: int,
    dp_id: int,
    now: datetime.datetime,
) -> tuple[int, int]:
    """Return ``(compliant_count, total_count)`` for the last 30d.

    The contract-event row is scoped to the DP id, which is
    itself scoped to ``workspace_id`` via the
    :class:`DataProduct` row.  We don't need an explicit
    workspace filter on the event row.

    Args:
        session: Live SQLAlchemy session.
        workspace_id: Active workspace (kept for symmetry).
        dp_id: Data-product id.
        now: Wall-clock anchor for the rolling window.

    Returns:
        ``(compliant_count, total_count)``.
    """
    del workspace_id
    cutoff = now - datetime.timedelta(days=30)
    total = int(
        session.execute(
            select(func.count(DataProductContractEvent.id)).where(
                DataProductContractEvent.data_product_id == dp_id,
                DataProductContractEvent.created_at >= cutoff,
            )
        ).scalar_one()
        or 0
    )
    compliant = int(
        session.execute(
            select(func.count(DataProductContractEvent.id)).where(
                DataProductContractEvent.data_product_id == dp_id,
                DataProductContractEvent.created_at >= cutoff,
                DataProductContractEvent.outcome == "compliant",
            )
        ).scalar_one()
        or 0
    )
    return compliant, total


def render_passport(
    session: Any,
    *,
    workspace_id: int,
    data_product: DataProduct,
    now: datetime.datetime | None = None,
) -> tuple[str, dict[str, Any]]:
    """Render one passport's markdown body + the cached stats.

    Args:
        session: Live SQLAlchemy session.
        workspace_id: Tenant scope.
        data_product: The DP row.
        now: Optional "now" override for tests.

    Returns:
        ``(body_md, stats_dict)``.  Stats keys: ``source_tables``
        (list[str]), ``downstream_tables`` (list[str]),
        ``column_count`` (int), ``edge_count`` (int).
    """
    now = now or datetime.datetime.now(datetime.UTC)
    prefix = f"{data_product.catalog_name}.{data_product.schema_name}."
    sources, downstream, edge_count = _collect_lineage_tables(
        session, workspace_id=workspace_id, dp_prefix=prefix
    )
    distinct_columns = (
        session.execute(
            select(func.count(func.distinct(LineageColumnMap.target_column))).where(
                LineageColumnMap.workspace_id == workspace_id,
                LineageColumnMap.target_table.like(f"{prefix}%"),
            )
        ).scalar_one()
        or 0
    )
    column_count = int(distinct_columns)

    compliant, total = _freshness_summary(
        session,
        workspace_id=workspace_id,
        dp_id=data_product.id,
        now=now,
    )
    pct = (compliant / total * 100.0) if total > 0 else None

    recent_activity = fetch_activity_for_dp(
        session,
        workspace_id=workspace_id,
        dp=data_product,
        limit=5,
        offset=0,
    )

    parts: list[str] = []
    parts.append("## What this product holds")
    parts.append("")
    parts.append(
        (data_product.description or "").strip() or "_No description in the contract yaml._"
    )
    parts.append("")

    parts.append("## Where the data comes from")
    parts.append("")
    if sources:
        for s in sources:
            parts.append(f"- `{s}`")
    else:
        parts.append("_No upstream tables observed yet._")
    parts.append("")

    parts.append("## Who consumes it")
    parts.append("")
    if downstream:
        for d in downstream:
            parts.append(f"- `{d}`")
    else:
        parts.append("_No downstream consumers observed yet._")
    parts.append("")

    parts.append("## Freshness profile (last 30d)")
    parts.append("")
    if total > 0 and pct is not None:
        parts.append(f"- Compliant: **{pct:.1f}%** ({compliant} of {total} contract events)")
    else:
        parts.append("_No contract events in the last 30 days._")
    parts.append("")

    parts.append("## Recent activity (last 7d)")
    parts.append("")
    if recent_activity:
        for entry in recent_activity[:5]:
            summary = entry.summary or entry.kind
            parts.append(f"- `{entry.ts}` — {summary}")
    else:
        parts.append("_No activity in the last 7 days._")
    parts.append("")

    body_md = "\n".join(parts).rstrip() + "\n"
    stats: dict[str, Any] = {
        "source_tables": sources,
        "downstream_tables": downstream,
        "column_count": column_count,
        "edge_count": edge_count,
    }
    return body_md, stats


def refresh_passport_for_dp(
    session_factory: Any,
    *,
    workspace_id: int,
    data_product_id: int,
    trigger: str = "manual",
    now: datetime.datetime | None = None,
) -> int:
    """Insert a fresh :class:`DataProductPassport` row.

    Args:
        session_factory: SQLAlchemy session factory.
        workspace_id: Tenant scope.
        data_product_id: The DP row id to refresh against.
        trigger: One of :data:`PASSPORT_TRIGGERS`.
        now: Optional "now" override for tests.

    Returns:
        The new row's ``version_int``.
    """
    now = now or datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        dp = session.get(DataProduct, data_product_id)
        if dp is None or dp.workspace_id != workspace_id:
            return 0
        body_md, stats = render_passport(
            session,
            workspace_id=workspace_id,
            data_product=dp,
            now=now,
        )
        latest = int(
            session.execute(
                select(func.coalesce(func.max(DataProductPassport.version_int), 0)).where(
                    DataProductPassport.workspace_id == workspace_id,
                    DataProductPassport.data_product_id == data_product_id,
                )
            ).scalar_one()
            or 0
        )
        version_int = latest + 1
        session.add(
            DataProductPassport(
                workspace_id=workspace_id,
                data_product_id=data_product_id,
                version_int=version_int,
                body_md=body_md,
                source_tables_json=json.dumps(stats["source_tables"]),
                downstream_tables_json=json.dumps(stats["downstream_tables"]),
                column_count=int(stats["column_count"]),
                edge_count=int(stats["edge_count"]),
                refreshed_at=now,
                refresh_trigger=trigger,
            )
        )
        session.commit()
    return version_int


def refresh_stale_passports(
    session_factory: Any,
    *,
    stale_threshold_seconds: int = 86_400,
    now: datetime.datetime | None = None,
) -> int:
    """Refresh every DP whose latest passport is older than the threshold.

    Args:
        session_factory: SQLAlchemy session factory.
        stale_threshold_seconds: Passport rows refreshed later
            than this many seconds ago are skipped.
        now: Optional "now" override for tests.

    Returns:
        Number of refreshed passports.
    """
    now = now or datetime.datetime.now(datetime.UTC)
    cutoff = now - datetime.timedelta(seconds=stale_threshold_seconds)
    refreshed = 0
    with session_factory() as session:
        dps = session.execute(select(DataProduct)).scalars().all()
        latest_per_dp: dict[int, datetime.datetime] = {}
        rows = (
            session.execute(
                select(
                    DataProductPassport.data_product_id,
                    func.max(DataProductPassport.refreshed_at),
                ).group_by(DataProductPassport.data_product_id)
            )
        ).all()
        for dp_id, refreshed_at in rows:
            if refreshed_at is not None:
                if refreshed_at.tzinfo is None:
                    refreshed_at = refreshed_at.replace(tzinfo=datetime.UTC)
                latest_per_dp[int(dp_id)] = refreshed_at
        to_refresh: list[DataProduct] = []
        for dp in dps:
            last = latest_per_dp.get(dp.id)
            if last is None or last < cutoff:
                to_refresh.append(dp)

    for dp in to_refresh:
        refresh_passport_for_dp(
            session_factory,
            workspace_id=dp.workspace_id,
            data_product_id=dp.id,
            trigger="periodic",
            now=now,
        )
        refreshed += 1
    return refreshed
