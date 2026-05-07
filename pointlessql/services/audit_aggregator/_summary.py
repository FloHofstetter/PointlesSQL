"""Single-dict cockpit summary across every metric.

Renders the four "is anything exploding right now?" stat-cards on
the audit cockpit.  The flat shape lets the UI render with no
further parsing; ``None`` filters span the full retention window.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from pointlessql.services.audit_aggregator._query_builder import VALID_METRICS, scalar_count

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


def summary(
    factory: sessionmaker[Session],
    *,
    since: datetime.datetime | None = None,
    until: datetime.datetime | None = None,
    principal: str | None = None,
    agent_id: str | None = None,
    table: str | None = None,
    workspace_id: int | None = None,
) -> dict[str, int]:
    """Return a single-dict cockpit summary across every metric.

    The shape is deliberately flat — the cockpit UI renders it as
    stat-cards with no further parsing.  When every filter is
    ``None`` the response covers the full retention window, matching
    "since the beginning of recorded time" semantics.

    Args:
        factory: SQLAlchemy session factory.
        since: Lower bound (inclusive) on each metric's timestamp.
        until: Upper bound (exclusive) on each metric's timestamp.
        principal: ``AgentRun.principal`` filter applied where
            possible (run-attached metrics).
        agent_id: ``AgentRun.agent_id`` filter applied where
            possible.
        table: Target-table filter applied to op/lineage metrics
            (``target_table``) and external writes (``table_fqn``).
        workspace_id: Workspace lens.  ``None`` opts into
            the cross-workspace view (tenant admin only); a concrete id
            restricts results to that workspace.

    Returns:
        Dict with one key per metric in :data:`VALID_METRICS`.
    """
    with factory() as session:
        return {
            metric: scalar_count(
                session,
                metric,  # type: ignore[arg-type]
                since=since,
                until=until,
                principal=principal,
                agent_id=agent_id,
                table=table,
                workspace_id=workspace_id,
            )
            for metric in sorted(VALID_METRICS)
        }
