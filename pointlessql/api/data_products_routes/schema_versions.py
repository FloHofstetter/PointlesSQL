"""Output-port schema-version history + bump + diff routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.exceptions import AuthorizationError, BadRequestError
from pointlessql.services import schema_versioning as sv_service

router = APIRouter(tags=["data-products"])


def _require_steward_or_admin(request: Request, catalog: str, schema: str) -> None:
    """Raise 403 unless the caller is admin or the product's steward."""
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    dp_row, _, _, _ = load_one(factory, workspace_id, catalog, schema)
    user = get_user(request)
    if user.get("is_admin"):
        return
    if dp_row.steward_user_id is not None and dp_row.steward_user_id == user["id"]:
        return
    raise AuthorizationError(
        principal=user.get("email", ""),
        privilege="steward",
        securable_type="data_product",
        full_name=f"{catalog}.{schema}",
    )


@router.get("/api/data-products/{catalog}/{schema}/output-ports/{port_id}/versions")
async def list_port_versions(
    catalog: str, schema: str, port_id: int, request: Request
) -> dict[str, Any]:
    """Return the schema-version history for one output port (any-user)."""
    require_user(request)
    factory = request.app.state.session_factory
    return {"versions": sv_service.list_versions(factory, output_port_id=port_id)}


@router.post("/api/data-products/{catalog}/{schema}/output-ports/{port_id}/bump")
async def bump_port_schema(
    catalog: str,
    schema: str,
    port_id: int,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Persist a new schema version for the port (steward/admin)."""
    require_user(request)
    _require_steward_or_admin(request, catalog, schema)
    factory = request.app.state.session_factory
    user = get_user(request)
    new_schema = body.get("schema")
    if not isinstance(new_schema, dict):
        raise BadRequestError("schema body is required as an object")
    try:
        row, diff = sv_service.bump_port_version(
            factory,
            output_port_id=port_id,
            new_schema=new_schema,
            change_summary=body.get("change_summary"),
            bumped_by_user_id=int(user.get("id", 0) or 0) or None,
        )
    except LookupError as exc:
        # bare-http-ok: 404 for unknown port; no domain exception.
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "version": row,
        "diff": {
            "change_kind": diff.change_kind,
            "columns_removed": diff.columns_removed,
            "columns_added": [list(t) for t in diff.columns_added],
            "columns_type_changed": [list(t) for t in diff.columns_type_changed],
            "columns_nullable_tightened": diff.columns_nullable_tightened,
            "columns_description_changed": diff.columns_description_changed,
        },
    }


@router.get("/api/data-products/{catalog}/{schema}/output-ports/{port_id}/diff")
async def diff_port_versions(
    catalog: str,
    schema: str,
    port_id: int,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Compute the diff between two registered schema_json snapshots."""
    require_user(request)
    factory = request.app.state.session_factory
    history = sv_service.list_versions(factory, output_port_id=port_id)
    if not history:
        return {"diff": None}
    from_version = body.get("from_version")
    to_version = body.get("to_version") or history[0]["version_semver"]
    by_version = {row["version_semver"]: row for row in history}
    older = by_version.get(from_version) if from_version else None
    newer = by_version.get(to_version)
    if newer is None:
        # bare-http-ok: 404 for unknown semver target.
        raise HTTPException(status_code=404, detail="version not found")
    diff = sv_service.compute_diff(
        older["schema"] if older else None,
        newer["schema"],
    )
    return {
        "from_version": older["version_semver"] if older else None,
        "to_version": newer["version_semver"],
        "diff": {
            "change_kind": diff.change_kind,
            "columns_removed": diff.columns_removed,
            "columns_added": [list(t) for t in diff.columns_added],
            "columns_type_changed": [list(t) for t in diff.columns_type_changed],
            "columns_nullable_tightened": diff.columns_nullable_tightened,
            "columns_description_changed": diff.columns_description_changed,
        },
    }
