"""HTML page routes for the registered-models browse surface.

Three pages: the metastore-wide ``/models`` index, the per-model
detail page at ``/models/{full_name}``, and the version-compare
view at ``/models/{full_name}/compare``.  All three redirect
anonymous browsers to ``/auth/login`` with a ``next=`` hint so
the deep-link survives the round trip.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from pointlessql.api.dependencies import get_uc_client, get_user
from pointlessql.api.models_routes import annotate_version, fetch_mlflow_context
from pointlessql.exceptions import ResourceNotFoundError, ValidationError
from pointlessql.services import model_promotion
from pointlessql.services._executor import run_sync

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["models"])


@router.get("/models", response_class=HTMLResponse, response_model=None)
async def models_index_page(request: Request) -> HTMLResponse | RedirectResponse:
    """Render the metastore-wide registered-models index."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(url="/auth/login?next=/models", status_code=303)

    client = get_uc_client(request)
    catalogs = await client.list_catalogs()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/models.html",
        {
            "active_page": "models",
            "catalogs": catalogs,
            "is_admin": user["is_admin"],
        },
    )


async def _gather_versions_with_mlflow(
    versions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Annotate each version with the parsed marker + MLflow context.

    The MLflow lookups run via :func:`asyncio.to_thread` so the
    blocking ``MlflowClient.get_run`` call doesn't stall the event
    loop. Failures degrade to ``{"error": ...}`` per version.
    """
    annotated = [annotate_version(v) for v in versions]

    async def _resolve(v: dict[str, Any]) -> dict[str, Any]:
        marker = v.get("link_marker") or {}
        run_id = marker.get("mlflow_run_id") or v.get("run_id")
        mlflow_ctx = await run_sync(fetch_mlflow_context, run_id)
        return {**v, "mlflow": mlflow_ctx}

    if not annotated:
        return []
    capped = annotated[:50]
    return list(await asyncio.gather(*(_resolve(v) for v in capped)))


@router.get("/models/{full_name}", response_class=HTMLResponse, response_model=None)
async def model_detail_page(full_name: str, request: Request) -> HTMLResponse | RedirectResponse:
    """Render the model-detail page with versions + MLflow context."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(url=f"/auth/login?next=/models/{full_name}", status_code=303)

    client = get_uc_client(request)
    model = await client.get_registered_model(full_name)
    if not model:
        raise ResourceNotFoundError(f"Model {full_name!r} not found")

    versions = await client.list_model_versions(full_name=full_name)
    versions_enriched = await _gather_versions_with_mlflow(versions)

    mlflow_running = getattr(request.app.state, "mlflow_subprocess", None) is not None

    # surface the current champion so the Versions tab
    # can render a star-badge and the Promotion tab pre-loads.
    try:
        champion_version = await model_promotion.get_current_champion(client, full_name)
    except Exception:  # noqa: BLE001 — promotion lookup must never block the page
        _logger.warning("get_current_champion failed for %s", full_name, exc_info=True)
        champion_version = None

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/model.html",
        {
            "active_page": "models",
            "model": model,
            "versions": versions_enriched,
            "mlflow_running": mlflow_running,
            "champion_version": champion_version,
            "is_admin": user["id"] != 0 and user["is_admin"],
        },
    )


@router.get(
    "/models/{full_name}/compare",
    response_class=HTMLResponse,
    response_model=None,
)
async def model_compare_page(
    full_name: str, request: Request, v1: int, v2: int
) -> HTMLResponse | RedirectResponse:
    """Render the side-by-side version-compare view."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(
            url=f"/auth/login?next=/models/{full_name}/compare?v1={v1}&v2={v2}",
            status_code=303,
        )
    if v1 == v2:
        raise ValidationError("v1 and v2 must differ")

    # Local imports to avoid circulars at module import time.
    from pointlessql.services.models_compare import (
        compute_metric_diff,
        params_diff,
        tags_diff,
    )

    client = get_uc_client(request)
    v1_info, v2_info = await asyncio.gather(
        client.get_model_version(full_name, v1),
        client.get_model_version(full_name, v2),
    )
    if not v1_info:
        raise ResourceNotFoundError(f"v{v1} not found")
    if not v2_info:
        raise ResourceNotFoundError(f"v{v2} not found")

    v1_annot = annotate_version(v1_info)
    v2_annot = annotate_version(v2_info)

    def _run_id_for(annot: dict[str, Any]) -> str | None:
        marker = annot.get("link_marker") or {}
        return marker.get("mlflow_run_id") or annot.get("run_id")

    v1_mlflow, v2_mlflow = await asyncio.gather(
        run_sync(fetch_mlflow_context, _run_id_for(v1_annot)),
        run_sync(fetch_mlflow_context, _run_id_for(v2_annot)),
    )

    metric_diff = compute_metric_diff(v1_mlflow, v2_mlflow)
    params_diff_data = params_diff(v1_mlflow.get("params") or {}, v2_mlflow.get("params") or {})
    tags_diff_data = tags_diff(v1_mlflow.get("tags") or {}, v2_mlflow.get("tags") or {})

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/model_compare.html",
        {
            "active_page": "models",
            "model_full_name": full_name,
            "v1": v1_annot,
            "v2": v2_annot,
            "v1_mlflow": v1_mlflow,
            "v2_mlflow": v2_mlflow,
            "metric_diff": metric_diff,
            "params_diff": params_diff_data,
            "tags_diff": tags_diff_data,
        },
    )
