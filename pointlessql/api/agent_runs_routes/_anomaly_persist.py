"""Run-finish hook: persist the anomaly verdict onto ``agent_runs``.

Caches the per-run day-bin anomaly severity onto two columns on
:class:`AgentRun` so the runs-list page can paint its badge
without re-running :func:`audit_aggregator.anomalies` per render.
The hook runs after every terminal status transition (both the
runtime-driven ``/api/agent-runs/{run_id}/finish`` and the
admin-driven ``/api/agent-runs/{run_id}/deny``), in its own
session so a verdict-compute failure cannot roll back the status
transition itself.
"""

from __future__ import annotations

import logging

from fastapi import Request
from sqlalchemy import select

from pointlessql.models.agent._runs import AgentRun
from pointlessql.services import audit_aggregator as agg

logger = logging.getLogger(__name__)


def persist_run_anomaly(request: Request, run_id: str) -> None:
    """Compute + persist the run's anomaly verdict, fail-soft.

    Loads the freshly-finished :class:`AgentRun`, calls
    :func:`audit_aggregator.compute_run_anomaly` against the
    run's day-bin, and updates the cached severity + metric
    columns.  Any failure logs and returns silently — the badge
    can stay ``NULL`` without breaking the run-finish path.

    Args:
        request: FastAPI request — used to reach app state.
        run_id: The terminal run's UUID.
    """
    try:
        settings = request.app.state.settings
        factory = request.app.state.session_factory
        with factory() as session:
            row = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
            if row is None:
                return
            verdict = agg.compute_run_anomaly(
                factory,
                row,
                window_days=settings.audit.anomaly_baseline_window_days,
                sigma=settings.audit.anomaly_threshold_sigma,
            )
            if verdict is None:
                row.anomaly_severity = "ok"
                row.anomaly_metric = None
            else:
                row.anomaly_severity = verdict["severity"]
                row.anomaly_metric = verdict["metric"]
            session.commit()
    except Exception:  # noqa: BLE001 — anomaly persist is best-effort
        logger.exception("persist_run_anomaly failed for run %s", run_id)
