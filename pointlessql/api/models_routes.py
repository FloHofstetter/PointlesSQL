"""JSON aggregator endpoints for the registered-models browse surface.

Five endpoints back the ``/models`` index, model-detail page, and
version-compare view:

- ``GET /api/models?catalog_name=&schema_name=`` lists registered
  models, optionally enriched with the latest-version status snapshot.
- ``GET /api/models/{full_name}`` returns the registered model + its
  versions (each annotated with the parsed ``_pql_link`` marker, when
  present).
- ``GET /api/models/{full_name}/versions/{version}`` returns one
  version with the matching MLflow context (params + metrics + tags).
- ``GET /api/models/{full_name}/runs`` returns the unique
  agent-run-ids referenced by any version's ``_pql_link`` marker.
- ``GET /api/models/{full_name}/lineage`` builds the focused model
  lineage DAG (added).

Two write endpoints landed to support champion/
challenger promotion:

- ``GET /api/models/{full_name}/promotion`` returns the current
  champion + history.
- ``POST /api/models/{full_name}/promote`` swaps the champion;
  supervisor scope required.

All read endpoints require an authenticated user; supervisor scope
is *not* required because the browse experience is read-only. The
sensitive surface (cross-link marker payloads) only echoes
metadata that already lives on the soyuz row.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from pointlessql.api.dependencies import (
    effective_principal,
    get_uc_client,
    get_user,
    require_supervisor,
)
from pointlessql.exceptions import CatalogNotFoundError
from pointlessql.services import model_promotion
from pointlessql.services.agent_runs.mlflow_detector import get_mlflow_module
from pointlessql.services.agent_runs.mlflow_soyuz_link import parse_link_marker
from pointlessql.services.models_lineage import (
    aggregate_prediction_tables_for_model,
    build_model_lineage_graph,
)

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["models"])


def _parse_marker(comment: str | None) -> dict[str, Any] | None:
    """Return the ``_pql_link`` marker dict for a comment, or ``None``."""
    return parse_link_marker(comment)


def annotate_version(version: dict[str, Any]) -> dict[str, Any]:
    """Add ``link_marker`` to a model-version dict, preserving the rest."""
    marker = _parse_marker(version.get("comment"))
    return {**version, "link_marker": marker}


def fetch_mlflow_context(run_id: str | None) -> dict[str, Any]:
    """Best-effort MLflow run lookup, never raises.

    Args:
        run_id: MLflow run-id from the soyuz model-version row, or
            from a parsed ``_pql_link`` marker.

    Returns:
        dict: Empty dict when no run id; ``{"error": ...}`` when
            MLflow is unreachable or the run is unknown; otherwise
            ``{"params", "metrics", "tags", "status", "artifact_uri",
            "experiment_id", "start_time", "end_time"}``.
    """
    if not run_id:
        return {}
    mlflow = get_mlflow_module()
    if mlflow is None:
        return {"error": "MLflow extra not installed"}
    try:
        client = mlflow.MlflowClient()
        run = client.get_run(run_id)
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
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


def _require_auth(request: Request) -> None:
    """Reject anonymous callers with 401.

    The page-level routes redirect unauthenticated browsers to
    ``/auth/login`` themselves; the JSON endpoints answer 401 so
    fetch() callers don't follow redirects into an HTML form.
    """
    user = get_user(request)
    if user["id"] == 0:
        raise HTTPException(status_code=401, detail="Authentication required")


@router.get("/api/models")
async def api_list_models(
    request: Request,
    catalog_name: str | None = None,
    schema_name: str | None = None,
    enrich_latest: bool = False,
) -> dict[str, Any]:
    """List registered models, optionally enriched with latest-version status.

    Args:
        request: FastAPI request.
        catalog_name: Optional parent catalog filter.
        schema_name: Optional parent schema filter (requires
            ``catalog_name`` per UC-OSS spec).
        enrich_latest: When ``True``, fetch each model's versions to
            populate ``latest_version`` + ``latest_status``.

    Returns:
        ``{"models": [...]}`` — each entry mirrors
        ``RegisteredModelInfo`` plus the optional enrichment fields.
    """
    _require_auth(request)
    client = get_uc_client(request)
    models = await client.list_registered_models(catalog_name=catalog_name, schema_name=schema_name)
    if enrich_latest:
        enriched: list[dict[str, Any]] = []
        for model in models:
            full_name = model.get("full_name")
            latest_version: int | None = None
            latest_status: str | None = None
            linked_run_count = 0
            if full_name:
                try:
                    versions = await client.list_model_versions(full_name=full_name)
                except CatalogNotFoundError:
                    versions = []
                for v in versions:
                    ver = v.get("version")
                    if isinstance(ver, int) and (latest_version is None or ver > latest_version):
                        latest_version = ver
                        latest_status = v.get("status")
                    if _parse_marker(v.get("comment")) is not None:
                        linked_run_count += 1
            enriched.append(
                {
                    **model,
                    "latest_version": latest_version,
                    "latest_status": latest_status,
                    "linked_run_count": linked_run_count,
                }
            )
        return {"models": enriched}
    return {"models": models}


@router.get("/api/models/{full_name}")
async def api_get_model(request: Request, full_name: str) -> dict[str, Any]:
    """Return a single registered model with all versions + parsed markers."""
    _require_auth(request)
    client = get_uc_client(request)
    model = await client.get_registered_model(full_name)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model {full_name!r} not found")
    versions = await client.list_model_versions(full_name=full_name)
    annotated = [annotate_version(v) for v in versions]
    return {"model": model, "versions": annotated}


@router.get("/api/models/{full_name}/versions/{version}")
async def api_get_model_version(request: Request, full_name: str, version: int) -> dict[str, Any]:
    """Return one model version with the matching MLflow context."""
    _require_auth(request)
    client = get_uc_client(request)
    info = await client.get_model_version(full_name, version)
    if not info:
        raise HTTPException(
            status_code=404,
            detail=f"Version {version} of {full_name!r} not found",
        )
    annotated = annotate_version(info)
    marker = annotated.get("link_marker") or {}
    mlflow_run_id = marker.get("mlflow_run_id") or info.get("run_id")
    mlflow_ctx = fetch_mlflow_context(mlflow_run_id)
    return {"version": annotated, "mlflow": mlflow_ctx}


@router.get("/api/models/{full_name}/lineage")
async def api_model_lineage(request: Request, full_name: str) -> dict[str, Any]:
    """Build the bidirectional model-lineage DAG ( + 21.7).

    Walks the model's versions to collect the linked agent-run ids
    from the ``_pql_link`` markers, then aggregates the distinct
    source tables consumed by those runs from
    :class:`pointlessql.models.LineageRowEdge`.   adds
    the downstream half: every row-edge whose ``source_model_uri``
    matches the model FQN contributes a prediction-table successor.
    Returns just the centre model node when no runs are linked
    and no inference edges exist yet.

    Args:
        request: FastAPI request.
        full_name: Three-level FQN ``catalog.schema.model``.

    Returns:
        ``{"model_full_name", "nodes", "edges"}``.
    """
    _require_auth(request)
    client = get_uc_client(request)
    versions = await client.list_model_versions(full_name=full_name)
    agent_run_ids: list[str] = []
    for v in versions:
        marker = _parse_marker(v.get("comment"))
        if marker is None:
            continue
        rid = marker.get("agent_run_id")
        if isinstance(rid, str) and rid:
            agent_run_ids.append(rid)

    factory = request.app.state.session_factory
    return build_model_lineage_graph(
        factory,
        model_full_name=full_name,
        agent_run_ids=agent_run_ids,
    )


@router.get("/api/models/{full_name}/predictions")
async def api_model_predictions(request: Request, full_name: str) -> dict[str, Any]:
    """Return distinct prediction-tables this model has written into.

    backs the "Predictions" sub-card on the
    model-detail Lineage tab.  Reads ``lineage_row_edges`` directly
    (no soyuz round-trip) so cost is O(R · E) rather than the
    O(C · M · V) full-scan of the upstream side.

    Args:
        request: FastAPI request.
        full_name: Three-level FQN ``catalog.schema.model``.

    Returns:
        ``{"predictions": [{"target_table", "edge_count"}, ...]}``.
    """
    _require_auth(request)
    factory = request.app.state.session_factory
    rows = aggregate_prediction_tables_for_model(factory, full_name)
    return {"predictions": rows}


@router.get("/api/models/{full_name}/runs")
async def api_model_linked_runs(request: Request, full_name: str) -> dict[str, Any]:
    """Return the agent-run + MLflow-run ids linked to any version of this model.

    Args:
        request: FastAPI request.
        full_name: Three-level FQN ``catalog.schema.model``.

    Returns:
        ``{"runs": [{"agent_run_id", "mlflow_run_id", "version",
        "linked_at"}, ...]}``.
    """
    _require_auth(request)
    client = get_uc_client(request)
    versions = await client.list_model_versions(full_name=full_name)
    runs: list[dict[str, Any]] = []
    for v in versions:
        marker = _parse_marker(v.get("comment"))
        if marker is None:
            continue
        runs.append(
            {
                "agent_run_id": marker.get("agent_run_id"),
                "mlflow_run_id": marker.get("mlflow_run_id"),
                "mlflow_experiment_id": marker.get("mlflow_experiment_id"),
                "linked_at": marker.get("linked_at"),
                "version": v.get("version"),
            }
        )
    return {"runs": runs}


class PromoteRequest(BaseModel):
    """Body for ``POST /api/models/{full_name}/promote``."""

    target_version: int = Field(..., ge=1, description="Version to crown.")
    reason: str = Field(..., min_length=1, max_length=4000, description="Justification.")


@router.get("/api/models/{full_name}/promotion")
async def api_get_promotion(request: Request, full_name: str) -> dict[str, Any]:
    """Return the current champion + chronological promotion history.

    Args:
        request: FastAPI request.
        full_name: Three-level FQN ``catalog.schema.model``.

    Returns:
        ``{"champion_version", "history": [...]}``.  ``champion_version``
        is ``None`` when the model has no READY versions yet.
    """
    _require_auth(request)
    client = get_uc_client(request)
    champion = await model_promotion.get_current_champion(client, full_name)
    factory = request.app.state.session_factory
    history = await model_promotion.list_promotion_history(factory, full_name)
    return {"champion_version": champion, "history": history}


@router.post("/api/models/{full_name}/promote")
async def api_promote_model(
    request: Request, full_name: str, body: PromoteRequest
) -> dict[str, Any]:
    """Promote a challenger version to champion.

    Requires supervisor scope.  Writes a ``_pql_promotion`` marker
    into the registered-model's ``comment``, persists an
    ``AgentReview`` row with ``kind="model_promotion"``, and emits
    a ``pointlessql.model.promoted`` CloudEvents envelope (returned
    in the response so the caller can inspect or fan out).

    Args:
        request: FastAPI request.
        full_name: Three-level FQN ``catalog.schema.model``.
        body: Validated promotion request.

    Returns:
        ``{"champion_version", "previous_champion", "promoted_at",
        "review_id", "event"}`` on success.

    Raises:
        HTTPException: 400 when validation fails (version not READY,
            already champion, missing reason); 502 when soyuz rejects
            the comment PATCH.
    """
    require_supervisor(request)
    user = get_user(request)
    actor = effective_principal(request) or user.get("email") or "unknown"

    client = get_uc_client(request)
    factory = request.app.state.session_factory
    try:
        result = await model_promotion.promote_version(
            factory,
            client,
            full_name,
            target_version=body.target_version,
            promoted_by=actor,
            reason=body.reason,
        )
    except model_promotion.PromotionError as exc:
        message = str(exc)
        status = 502 if "soyuz" in message.lower() else 400
        raise HTTPException(status_code=status, detail=message) from exc
    return result
