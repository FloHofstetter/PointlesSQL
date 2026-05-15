"""Cross-DP co-occurrence cache refresher + reader (Phase 73.5).

Two callables:

* :func:`refresh_cooccurrence` — walks
  ``agent_run_operations`` for the rolling window, projects
  ``target_table`` → ``data_product_id`` via the
  ``(catalog, schema)`` prefix, builds the per-run set of
  touched DPs, and UPSERTs one row per directed pair
  ``(dp, co_dp)`` per workspace.  Bounded by ``top_n`` per
  source DP.
* :func:`fetch_related` — returns the top-N related DPs for
  one source DP, ordered by ``cooccurrence_count`` desc.
"""

from __future__ import annotations

import datetime
import logging
from collections import defaultdict
from typing import Any

from sqlalchemy import select

from pointlessql.models.agent._audit import AgentRunOperation
from pointlessql.models.catalog._data_product_cooccurrence import (
    DataProductCooccurrence,
)
from pointlessql.models.catalog._data_products import DataProduct

logger = logging.getLogger(__name__)


def _split_fqn_prefix(target: str) -> tuple[str, str] | None:
    """Return ``(catalog, schema)`` for one ``target_table`` or ``None``."""
    parts = target.split(".")
    if len(parts) != 3:
        return None
    if not all(parts):
        return None
    return parts[0], parts[1]


def refresh_cooccurrence(
    session_factory: Any,
    *,
    window_days: int = 7,
    top_n: int = 10,
    now: datetime.datetime | None = None,
) -> int:
    """Recompute the per-workspace co-occurrence cache.

    Args:
        session_factory: SQLAlchemy session factory.
        window_days: Rolling window length.
        top_n: Max related DPs kept per source DP per
            workspace.
        now: Optional "now" override for tests.

    Returns:
        Total UPSERTed row count.
    """
    now = now or datetime.datetime.now(datetime.UTC)
    window_end = now
    window_start = now - datetime.timedelta(days=window_days)
    upserted = 0

    with session_factory() as session:
        dps = session.execute(select(DataProduct)).scalars().all()
        # (workspace_id, catalog, schema) → dp_id
        key_to_dp_id: dict[tuple[int, str, str], int] = {
            (dp.workspace_id, dp.catalog_name, dp.schema_name): dp.id
            for dp in dps
        }
        if not key_to_dp_id:
            return 0

        rows = session.execute(
            select(
                AgentRunOperation.workspace_id,
                AgentRunOperation.agent_run_id,
                AgentRunOperation.target_table,
            ).where(
                AgentRunOperation.target_table.is_not(None),
                AgentRunOperation.started_at >= window_start,
                AgentRunOperation.started_at < window_end,
            )
        ).all()

        # Per (workspace, run) → set[dp_id]
        per_run: dict[tuple[int, str], set[int]] = defaultdict(set)
        for workspace_id, run_id, target_table in rows:
            if not target_table:
                continue
            split = _split_fqn_prefix(target_table)
            if split is None:
                continue
            catalog, schema = split
            dp_id = key_to_dp_id.get((workspace_id, catalog, schema))
            if dp_id is None:
                continue
            per_run[(workspace_id, run_id)].add(dp_id)

        # Per (workspace, dp_id, co_dp_id) → distinct_run_count
        pair_counts: dict[tuple[int, int, int], int] = defaultdict(int)
        for (workspace_id, _run_id), dp_set in per_run.items():
            if len(dp_set) < 2:
                continue
            dp_list = list(dp_set)
            for dp_id in dp_list:
                for co_id in dp_list:
                    if co_id == dp_id:
                        continue
                    pair_counts[(workspace_id, dp_id, co_id)] += 1

        # Cap to top_n per (workspace, dp_id).
        kept_pairs: dict[tuple[int, int, int], int] = {}
        by_source: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
        for (workspace_id, dp_id, co_id), count in pair_counts.items():
            by_source[(workspace_id, dp_id)].append((co_id, count))
        for (workspace_id, dp_id), pairs in by_source.items():
            pairs.sort(key=lambda t: t[1], reverse=True)
            for co_id, count in pairs[:top_n]:
                kept_pairs[(workspace_id, dp_id, co_id)] = count

        existing_rows = session.execute(
            select(DataProductCooccurrence).where(
                DataProductCooccurrence.window_end == window_end
            )
        ).scalars().all()
        existing_keys = {
            (
                row.workspace_id,
                row.data_product_id,
                row.co_data_product_id,
            ): row
            for row in existing_rows
        }

        for (workspace_id, dp_id, co_id), count in kept_pairs.items():
            existing = existing_keys.get((workspace_id, dp_id, co_id))
            if existing is None:
                session.add(
                    DataProductCooccurrence(
                        workspace_id=workspace_id,
                        data_product_id=dp_id,
                        co_data_product_id=co_id,
                        cooccurrence_count=count,
                        window_start=window_start,
                        window_end=window_end,
                        refreshed_at=now,
                    )
                )
                upserted += 1
            else:
                existing.cooccurrence_count = count
                existing.window_start = window_start
                existing.refreshed_at = now
                session.add(existing)
                upserted += 1
        session.commit()
    return upserted


def fetch_related(
    session: Any,
    *,
    workspace_id: int,
    data_product_id: int,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return the top-N related DPs for one source DP.

    Args:
        session: Live SQLAlchemy session.
        workspace_id: Tenant scope.
        data_product_id: Source DP id.
        limit: Max rows.

    Returns:
        List of ``{data_product_id, data_product_ref, version,
        cooccurrence_count, window_end}`` dicts.
    """
    stmt = (
        select(DataProductCooccurrence, DataProduct)
        .join(
            DataProduct,
            DataProduct.id == DataProductCooccurrence.co_data_product_id,
        )
        .where(
            DataProductCooccurrence.workspace_id == workspace_id,
            DataProductCooccurrence.data_product_id == data_product_id,
        )
        .order_by(
            DataProductCooccurrence.window_end.desc(),
            DataProductCooccurrence.cooccurrence_count.desc(),
        )
        .limit(limit)
    )
    rows = session.execute(stmt).all()
    return [
        {
            "data_product_id": dp.id,
            "data_product_ref": f"{dp.catalog_name}.{dp.schema_name}",
            "version": dp.version,
            "cooccurrence_count": pair.cooccurrence_count,
            "window_end": pair.window_end.isoformat(),
        }
        for pair, dp in rows
    ]


def fetch_recommendations_for_user(
    session: Any,
    *,
    workspace_id: int,
    user_id: int,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return per-user "Recommended for you" entries.

    Reads the caller's followed-DP set, unions every co-DP
    pair anchored to one of those DPs, removes the DPs the
    caller already follows, and returns the top-N by
    cooccurrence count.

    Args:
        session: Live SQLAlchemy session.
        workspace_id: Tenant scope.
        user_id: Caller user id.
        limit: Max rows.

    Returns:
        List of ``{data_product_id, data_product_ref, version,
        cooccurrence_count}`` dicts.
    """
    from pointlessql.models.social._social_follow import SocialFollow
    from pointlessql.models.social._social_target import SocialTarget

    followed_rows = session.execute(
        select(SocialTarget.data_product_id)
        .join(SocialFollow, SocialFollow.social_target_id == SocialTarget.id)
        .where(
            SocialFollow.workspace_id == workspace_id,
            SocialFollow.user_id == user_id,
            SocialTarget.entity_kind == "dp",
            SocialTarget.data_product_id.is_not(None),
        )
    ).all()
    followed_ids: set[int] = {row[0] for row in followed_rows if row[0] is not None}
    if not followed_ids:
        return []

    rows = session.execute(
        select(DataProductCooccurrence, DataProduct)
        .join(
            DataProduct,
            DataProduct.id == DataProductCooccurrence.co_data_product_id,
        )
        .where(
            DataProductCooccurrence.workspace_id == workspace_id,
            DataProductCooccurrence.data_product_id.in_(followed_ids),
            DataProductCooccurrence.co_data_product_id.notin_(followed_ids),
        )
        .order_by(DataProductCooccurrence.cooccurrence_count.desc())
    ).all()

    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for pair, dp in rows:
        if dp.id in seen:
            continue
        seen.add(dp.id)
        out.append(
            {
                "data_product_id": dp.id,
                "data_product_ref": f"{dp.catalog_name}.{dp.schema_name}",
                "version": dp.version,
                "cooccurrence_count": pair.cooccurrence_count,
            }
        )
        if len(out) >= limit:
            break
    return out
