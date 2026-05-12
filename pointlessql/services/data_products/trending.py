"""Trending-rank refresh + read helpers (Phase 72.3).

Two callables:

* :func:`refresh_trending` — compute the top-N
  ``DataProductTrending`` rows per workspace for the rolling
  ``trending_window_days`` window and UPSERT them.  Called from
  the ``_data_product_trending_loop`` coroutine.
* :func:`fetch_trending` — read the cached rows for a given
  workspace (or all workspaces when ``workspace_scope='all'``,
  reserved for auditor+admin).

The refresh walks every ``DataProduct`` in every workspace +
counts the matching ``agent_run_operations`` rows.  For a single
workspace with < 10⁴ ops/week the join stays under 1s on SQLite
(verified via pytest); production deployments should still
enable the loop via
``POINTLESSQL_DATA_PRODUCTS_TRENDING_REFRESH_INTERVAL_SECONDS=900``
(15 min) rather than per-request inline computation.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from sqlalchemy import distinct, func, select

from pointlessql.models.agent._audit import AgentRunOperation
from pointlessql.models.catalog._data_product_trending import DataProductTrending
from pointlessql.models.catalog._data_products import DataProduct

logger = logging.getLogger(__name__)


def refresh_trending(
    session_factory: Any,
    *,
    window_days: int = 7,
    top_n: int = 10,
    now: datetime.datetime | None = None,
) -> int:
    """Recompute the trending-rank table for every workspace.

    Args:
        session_factory: SQLAlchemy session factory.
        window_days: Rolling window length.
        top_n: Number of top rows kept per workspace.
        now: Optional "now" override for tests.

    Returns:
        Total UPSERTed row count (sum across workspaces).
    """
    now = now or datetime.datetime.now(datetime.UTC)
    window_end = now
    window_start = window_end - datetime.timedelta(days=window_days)
    inserted = 0

    with session_factory() as session:
        all_dps = (
            session.execute(select(DataProduct))
            .scalars()
            .all()
        )

        # Group DPs by workspace so the ranking is per-tenant.
        by_workspace: dict[int, list[DataProduct]] = {}
        for dp in all_dps:
            by_workspace.setdefault(dp.workspace_id, []).append(dp)

        for workspace_id, dps in by_workspace.items():
            # Compute per-DP (agent_run_count, write_count) for the window.
            scored: list[tuple[DataProduct, int, int]] = []
            for dp in dps:
                fqn_prefix = f"{dp.catalog_name}.{dp.schema_name}."
                agent_run_count = int(
                    session.execute(
                        select(
                            func.count(distinct(AgentRunOperation.agent_run_id))
                        ).where(
                            AgentRunOperation.workspace_id == workspace_id,
                            AgentRunOperation.target_table.like(f"{fqn_prefix}%"),
                            AgentRunOperation.started_at >= window_start,
                            AgentRunOperation.started_at < window_end,
                        )
                    ).scalar_one()
                    or 0
                )
                write_count = int(
                    session.execute(
                        select(func.count(AgentRunOperation.id)).where(
                            AgentRunOperation.workspace_id == workspace_id,
                            AgentRunOperation.target_table.like(f"{fqn_prefix}%"),
                            AgentRunOperation.started_at >= window_start,
                            AgentRunOperation.started_at < window_end,
                        )
                    ).scalar_one()
                    or 0
                )
                if agent_run_count == 0 and write_count == 0:
                    continue
                scored.append((dp, agent_run_count, write_count))

            scored.sort(key=lambda t: (t[1], t[2]), reverse=True)
            scored = scored[:top_n]

            for rank, (dp, agent_run_count, write_count) in enumerate(
                scored, start=1
            ):
                existing = session.execute(
                    select(DataProductTrending).where(
                        DataProductTrending.workspace_id == workspace_id,
                        DataProductTrending.data_product_id == dp.id,
                        DataProductTrending.window_end == window_end,
                    )
                ).scalar_one_or_none()
                if existing is None:
                    session.add(
                        DataProductTrending(
                            workspace_id=workspace_id,
                            data_product_id=dp.id,
                            window_start=window_start,
                            window_end=window_end,
                            agent_run_count=agent_run_count,
                            write_count=write_count,
                            rank=rank,
                            refreshed_at=now,
                        )
                    )
                else:
                    existing.window_start = window_start
                    existing.agent_run_count = agent_run_count
                    existing.write_count = write_count
                    existing.rank = rank
                    existing.refreshed_at = now
                    session.add(existing)
                inserted += 1

        session.commit()
    return inserted


def fetch_trending(
    session: Any,
    *,
    workspace_id: int,
    workspace_scope: str = "current",
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Read the latest cached trending rows.

    Args:
        session: Live SQLAlchemy session.
        workspace_id: Active workspace.  Ignored when
            ``workspace_scope='all'``.
        workspace_scope: ``"current"`` (default, filter to
            *workspace_id*) or ``"all"`` (cross-workspace,
            auditor+admin only — the route is responsible for the
            gate).
        limit: Cap on rows returned.

    Returns:
        List of dicts shaped for direct JSON return.
    """
    stmt = (
        select(DataProductTrending, DataProduct)
        .join(
            DataProduct, DataProduct.id == DataProductTrending.data_product_id
        )
    )
    if workspace_scope != "all":
        stmt = stmt.where(DataProductTrending.workspace_id == workspace_id)
    # Pick the freshest window per DP.
    stmt = stmt.order_by(
        DataProductTrending.window_end.desc(),
        DataProductTrending.rank.asc(),
    ).limit(limit)
    rows = session.execute(stmt).all()
    return [
        {
            "data_product_id": dp.id,
            "data_product_ref": f"{dp.catalog_name}.{dp.schema_name}",
            "version": dp.version,
            "rank": trend.rank,
            "agent_run_count": trend.agent_run_count,
            "write_count": trend.write_count,
            "window_start": trend.window_start.isoformat(),
            "window_end": trend.window_end.isoformat(),
            "refreshed_at": trend.refreshed_at.isoformat(),
            "workspace_id": trend.workspace_id,
        }
        for trend, dp in rows
    ]
