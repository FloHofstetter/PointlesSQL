"""ML-context aggregator endpoint (Phase 21.2).

Single route that joins the three audit sources for a given
agent-run into one response: PointlesSQL's ``agent_runs`` row,
the matching MLflow run (params + metrics + tags + artifact uri),
and any soyuz model-versions linked back via the
``_pql_link``-marker convention from
:mod:`pointlessql.services.agent_runs.mlflow_soyuz_link`.

The endpoint is supervisor-scoped — same gate as Sprint 19.1's
audit axes — so reviewers and the audit-reviewer agent can answer
"how was this model trained?" with a single round-trip.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import select

from pointlessql.api.dependencies import require_supervisor
from pointlessql.exceptions import CatalogNotFoundError
from pointlessql.models import AgentRun
from pointlessql.services.agent_runs.mlflow_detector import get_mlflow_module
from pointlessql.services.agent_runs.mlflow_soyuz_link import parse_link_marker
from pointlessql.services.soyuz_client import make_soyuz_client

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["ml"])


def _fetch_mlflow_run(mlflow_run_id: str) -> dict[str, Any]:
    """Fetch a single MLflow run as a JSON-friendly dict.

    Returns an ``{"error": ...}`` dict instead of raising so a
    transient MLflow outage degrades the response gracefully.

    Args:
        mlflow_run_id: The MLflow run id stored on the agent_run row.

    Returns:
        dict[str, Any]: The serialized run, or an error envelope.
    """
    mlflow = get_mlflow_module()
    if mlflow is None:
        return {"error": "MLflow extra not installed"}
    try:
        client = mlflow.MlflowClient()
        run = client.get_run(mlflow_run_id)
    except Exception as exc:  # noqa: BLE001 - never raise into the aggregator
        return {"error": f"MLflow lookup failed: {exc}"}
    info = run.info
    return {
        "run_id": info.run_id,
        "experiment_id": info.experiment_id,
        "status": info.status,
        "artifact_uri": info.artifact_uri,
        "start_time": info.start_time,
        "end_time": info.end_time,
        "params": dict(run.data.params),
        "metrics": dict(run.data.metrics),
        "tags": dict(run.data.tags),
    }


def _fetch_linked_model_versions(agent_run_id: str) -> list[dict[str, Any]]:
    """Scan soyuz for model-versions whose comment carries a marker for this run.

    Best-effort: a soyuz outage reduces the result to an empty list.
    The implementation iterates every registered model under every
    catalog/schema, which is fine at PointlesSQL's scale; future
    optimisation = a real soyuz tag index once tags-on-models lands.

    Args:
        agent_run_id: The run UUID to match against marker payloads.

    Returns:
        list[dict[str, Any]]: One entry per linked model-version.
    """
    try:
        soyuz = make_soyuz_client()
        from soyuz_catalog_client.api.registered_models import (
            list_registered_models_api_2_1_unity_catalog_models_get as _list_rm,
        )
        from soyuz_catalog_client.api.model_versions import (
            list_model_versions_api_2_1_unity_catalog_models_full_name_versions_get as _list_mv,
        )

        # Soyuz allows a metastore-wide list when both catalog/schema are unset.
        rm_page = _list_rm.sync(client=soyuz, max_results=1000)
        registered = getattr(rm_page, "registered_models", None)
        if not registered:
            return []
        results: list[dict[str, Any]] = []
        for rm in registered:
            full_name = getattr(rm, "full_name", None)
            if not full_name:
                continue
            mv_page = _list_mv.sync(client=soyuz, full_name=full_name, max_results=1000)
            versions = getattr(mv_page, "model_versions", None)
            if not versions:
                continue
            for mv in versions:
                marker = parse_link_marker(getattr(mv, "comment", None))
                if marker is None:
                    continue
                if marker.get("agent_run_id") != agent_run_id:
                    continue
                results.append(
                    {
                        "full_name": full_name,
                        "version": getattr(mv, "version", None),
                        "status": getattr(mv, "status", None),
                        "source": getattr(mv, "source", None),
                        "linked_at": marker.get("linked_at"),
                        "mlflow_run_id": marker.get("mlflow_run_id"),
                    }
                )
        return results
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        _logger.warning("ml-context: soyuz scan failed for run %s: %s", agent_run_id, exc)
        return []


@router.get("/api/runs/{run_id}/ml-context")
async def get_ml_context(request: Request, run_id: str) -> dict[str, Any]:
    """Return the three-way join of agent-run + MLflow + soyuz model-versions.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID of the agent run.

    Returns:
        ``{"agent_run", "mlflow", "model_versions"}`` — see module
        docstring for semantics.

    Raises:
        AuthorizationError: When the caller lacks supervisor scope.
        CatalogNotFoundError: When the run id is unknown.
    """
    require_supervisor(request)

    factory = request.app.state.session_factory
    with factory() as session:
        run = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
        if run is None:
            raise CatalogNotFoundError(f"agent run {run_id!r} not found")
        agent_run_payload = {
            "id": run.id,
            "status": run.status,
            "principal": run.principal,
            "agent_id": run.agent_id,
            "notebook_path": run.notebook_path,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "mlflow_run_id": run.mlflow_run_id,
        }
        mlflow_run_id = run.mlflow_run_id

    mlflow_payload: dict[str, Any] = {}
    if mlflow_run_id:
        mlflow_payload = _fetch_mlflow_run(mlflow_run_id)

    model_versions = _fetch_linked_model_versions(run_id)

    return {
        "agent_run": agent_run_payload,
        "mlflow": mlflow_payload,
        "model_versions": model_versions,
    }
