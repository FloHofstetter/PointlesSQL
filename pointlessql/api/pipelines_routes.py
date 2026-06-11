"""Declarative-pipeline routes — CRUD, runs, and the two HTML pages.

The run endpoint does the async groundwork (SELECT enforcement +
policy collection on every external reference, as the caller) and
then dispatches the synchronous engine through ``run_sync``;
targets are written through PQL with a principal-bound client so
creation, lineage, and audit follow the normal write path.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_templates,
    get_uc_client,
    get_user,
)
from pointlessql.exceptions import (
    CatalogNotFoundError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationError,
)
from pointlessql.models.pipelines import Pipeline, PipelineRun
from pointlessql.pql._policies import extract_table_policy
from pointlessql.services import pipelines as pipelines_service
from pointlessql.services._executor import run_sync
from pointlessql.services.authorization import SELECT, check_privilege
from pointlessql.services.pipelines import PipelineValidationError

router = APIRouter(tags=["pipelines"])


def _serialize_pipeline(row: Pipeline) -> dict[str, Any]:
    """Project a pipeline row to a JSON-safe dict."""
    return {
        "id": row.id,
        "slug": row.slug,
        "title": row.title,
        "description": row.description,
        "owner_id": row.owner_id,
        "datasets": json.loads(row.datasets or "[]"),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _serialize_run(row: PipelineRun) -> dict[str, Any]:
    """Project a run row to a JSON-safe dict."""
    return {
        "id": row.id,
        "status": row.status,
        "triggered_by": row.triggered_by,
        "metrics": json.loads(row.metrics or "[]"),
        "error": row.error,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


def _ensure_pipeline(request: Request, slug: str) -> Pipeline:
    """Return the active workspace's pipeline or raise a 404.

    Args:
        request: Incoming FastAPI request.
        slug: Pipeline slug from the URL.

    Returns:
        The detached pipeline row.

    Raises:
        ResourceNotFoundError: When no pipeline with *slug* exists in
            the active workspace.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    row = pipelines_service.get_pipeline(factory, workspace_id=workspace_id, slug=slug)
    if row is None:
        raise ResourceNotFoundError(f"Pipeline '{slug}' not found.")
    return row


def _ensure_can_edit(request: Request, pipeline: Pipeline) -> None:
    """Gate mutations to the owner + admins.

    Args:
        request: Incoming FastAPI request.
        pipeline: The pipeline being mutated.

    Raises:
        PermissionDeniedError: When the caller is neither the owner
            nor an admin.
    """
    user = get_user(request)
    if not user["is_admin"] and int(user["id"]) != pipeline.owner_id:
        raise PermissionDeniedError("only the pipeline owner or an admin can modify it")


@router.get("/api/pipelines")
async def api_list_pipelines(request: Request) -> dict[str, Any]:
    """List the active workspace's pipelines."""
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    rows = await run_sync(pipelines_service.list_pipelines, factory, workspace_id=workspace_id)
    return {"pipelines": [_serialize_pipeline(row) for row in rows]}


@router.post("/api/pipelines")
async def api_create_pipeline(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Create a pipeline from a dataset document.

    Args:
        request: Incoming FastAPI request.
        body: ``{"title", "description"?, "datasets": [...]}``.

    Returns:
        The serialized pipeline.

    Raises:
        ValidationError: When the dataset document does not compile
            into a DAG.
        PermissionDeniedError: When the caller is unauthenticated.
    """
    user = get_user(request)
    if user["id"] <= 0:
        raise PermissionDeniedError("authentication required to create pipelines")
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    try:
        row = await run_sync(
            pipelines_service.create_pipeline,
            factory,
            workspace_id=workspace_id,
            title=str(body.get("title", "")),
            description=body.get("description")
            if isinstance(body.get("description"), str)
            else None,
            owner_id=int(user["id"]),
            datasets=body.get("datasets"),
        )
    except PipelineValidationError as exc:
        raise ValidationError(str(exc)) from exc
    await audit(
        request,
        "pipeline.created",
        f"pipeline:{row.slug}",
        {"datasets": len(json.loads(row.datasets))},
    )
    return _serialize_pipeline(row)


@router.get("/api/pipelines/{slug}")
async def api_get_pipeline(request: Request, slug: str) -> dict[str, Any]:
    """Return one pipeline with its recent runs."""
    row = _ensure_pipeline(request, slug)
    factory = request.app.state.session_factory
    runs = await run_sync(pipelines_service.list_runs, factory, pipeline_id=row.id)
    body = _serialize_pipeline(row)
    body["runs"] = [_serialize_run(run) for run in runs]
    return body


@router.patch("/api/pipelines/{slug}")
async def api_update_pipeline(
    request: Request,
    slug: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Patch title / description / datasets (owner or admin).

    Args:
        request: Incoming FastAPI request.
        slug: Pipeline slug.
        body: Any of ``{"title", "description", "datasets"}``.

    Returns:
        The serialized refreshed pipeline.

    Raises:
        ValidationError: When the new dataset document is invalid.
    """
    row = _ensure_pipeline(request, slug)
    _ensure_can_edit(request, row)
    factory = request.app.state.session_factory
    try:
        updated = await run_sync(
            pipelines_service.update_pipeline,
            factory,
            pipeline_id=row.id,
            title=body.get("title") if isinstance(body.get("title"), str) else None,
            description=body.get("description")
            if isinstance(body.get("description"), str)
            else None,
            datasets=body.get("datasets"),
        )
    except PipelineValidationError as exc:
        raise ValidationError(str(exc)) from exc
    assert updated is not None  # ensured above  # noqa: S101
    await audit(request, "pipeline.updated", f"pipeline:{slug}", {"fields": sorted(body)})
    return _serialize_pipeline(updated)


@router.delete("/api/pipelines/{slug}")
async def api_delete_pipeline(request: Request, slug: str) -> dict[str, Any]:
    """Delete a pipeline with its runs and cursors (owner or admin)."""
    row = _ensure_pipeline(request, slug)
    _ensure_can_edit(request, row)
    factory = request.app.state.session_factory
    deleted = await run_sync(pipelines_service.delete_pipeline, factory, pipeline_id=row.id)
    if deleted:
        await audit(request, "pipeline.deleted", f"pipeline:{slug}", {"id": row.id})
    return {"deleted": deleted}


async def _resolve_externals(
    request: Request, refs: list[str]
) -> tuple[dict[str, str], dict[str, Any]]:
    """Enforce SELECT and collect policies for external references.

    Args:
        request: Incoming FastAPI request (caller = principal).
        refs: External 3-part references of the pipeline.

    Returns:
        ``(storage map, policy map)`` for the engine.

    Raises:
        CatalogNotFoundError: When a reference is unknown or has no
            storage location.
        ValidationError: When a stored read policy is malformed.
    """
    uc_client = get_uc_client(request)
    user = get_user(request)
    external: dict[str, str] = {}
    policies: dict[str, Any] = {}
    for fqn in refs:
        parts = fqn.split(".")
        info = await uc_client.get_table(parts[0], parts[1], parts[2])
        if not info:
            raise CatalogNotFoundError(f"Table not found: {fqn!r}")
        storage = info.get("storage_location")
        if not isinstance(storage, str) or not storage:
            raise CatalogNotFoundError(f"Table {fqn!r} has no storage_location.")
        await check_privilege(
            uc_client, user["email"], bool(user["is_admin"]), "table", fqn, SELECT
        )
        external[fqn] = storage
        is_owner = bool(user["email"]) and info.get("owner") == user["email"]
        if not user["is_admin"] and not is_owner:
            try:
                policy = extract_table_policy(info, principal=user["email"])
            except ValueError as exc:
                raise ValidationError(
                    f"table {fqn!r} carries a malformed read policy: {exc}"
                ) from exc
            if policy is not None:
                policies[fqn] = policy
    return external, policies


@router.post("/api/pipelines/{slug}/run")
async def api_run_pipeline(request: Request, slug: str) -> dict[str, Any]:
    """Run a pipeline now (as the caller) and return the run record.

    Args:
        request: Incoming FastAPI request.
        slug: Pipeline slug.

    Returns:
        The serialized run (terminal state — the engine runs to
        completion within the request).

    Raises:
        ValidationError: When the stored definition no longer
            validates.
        ResourceNotFoundError: When the run row vanished between
            dispatch and readback (defence in depth).
    """
    row = _ensure_pipeline(request, slug)
    factory = request.app.state.session_factory
    user = get_user(request)
    try:
        datasets = pipelines_service.parse_datasets(row)
    except PipelineValidationError as exc:
        raise ValidationError(str(exc)) from exc
    dataset_names = {d["name"] for d in datasets}
    external_refs = sorted({ref for d in datasets for ref in d["refs"] if ref not in dataset_names})
    external, policies = await _resolve_externals(request, external_refs)

    from pointlessql.services.soyuz_client import make_principal_client

    client = make_principal_client(request.app.state.settings, user["email"])
    run_id = await run_sync(
        pipelines_service.run_pipeline_sync,
        factory,
        pipeline_id=row.id,
        triggered_by=user["email"],
        external=external,
        external_policies=policies,
        client=client,
    )
    runs = await run_sync(pipelines_service.list_runs, factory, pipeline_id=row.id, limit=1)
    run = next((r for r in runs if r.id == run_id), runs[0] if runs else None)
    await audit(
        request,
        "pipeline.ran",
        f"pipeline:{slug}",
        {"run_id": run_id, "status": run.status if run else "unknown"},
    )
    if run is None:
        raise ResourceNotFoundError(f"Run {run_id} not found.")
    return _serialize_run(run)


@router.get("/api/pipelines/{slug}/runs")
async def api_list_runs(request: Request, slug: str) -> dict[str, Any]:
    """List a pipeline's recent runs."""
    row = _ensure_pipeline(request, slug)
    factory = request.app.state.session_factory
    runs = await run_sync(pipelines_service.list_runs, factory, pipeline_id=row.id)
    return {"runs": [_serialize_run(run) for run in runs]}


@router.get("/pipelines", response_class=HTMLResponse)
async def pipelines_page(request: Request):
    """Render the pipelines list page."""
    return get_templates(request).TemplateResponse(
        request,
        "pages/pipelines.html",
        {"active_page": "pipelines"},
    )


@router.get("/pipelines/{slug}", response_class=HTMLResponse)
async def pipeline_detail_page(request: Request, slug: str):
    """Render one pipeline's editor + run history page."""
    row = _ensure_pipeline(request, slug)
    user = get_user(request)
    can_edit = bool(user["is_admin"]) or int(user["id"]) == row.owner_id
    return get_templates(request).TemplateResponse(
        request,
        "pages/pipeline_detail.html",
        {
            "active_page": "pipelines",
            "pipeline": _serialize_pipeline(row),
            "can_edit": can_edit,
        },
    )
