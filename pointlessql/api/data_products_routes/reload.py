"""``POST /api/data-products/reload`` — admin trigger to re-load every yaml."""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from pointlessql.api.dependencies import current_workspace_id, require_admin
from pointlessql.config import Settings
from pointlessql.data_products import load_contracts_for_workspace

router = APIRouter(tags=["data-products"])


@router.post("/api/data-products/reload")
async def reload_data_products(request: Request) -> dict[str, Any]:
    """Reload every yaml under ``Settings.data_products.yaml_search_paths``.

    Admin-gated.  Re-runs :func:`load_contracts_from_paths` for the
    current workspace; failures on individual yamls propagate as
    ``DataProductYamlInvalid`` and surface as a 400 response.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"loaded": int, "paths": [...]}`` with the count of
        contracts UPSERTed and the resolved yaml paths.

    Raises:
        HTTPException: When ``yaml_search_paths`` is empty
            (admins must configure the search roots before calling
            this endpoint).
    """
    require_admin(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    settings: Settings = request.app.state.settings
    contracts = load_contracts_for_workspace(
        factory,
        workspace_id=workspace_id,
        settings=settings,
        now=datetime.datetime.now(datetime.UTC),
    )
    env_paths = list(settings.data_products.yaml_search_paths)
    if not contracts and not env_paths:
        # bare-http-ok: nothing was discoverable; surface a config hint
        # rather than a silent empty success so the admin learns to
        # either populate the env path or sync at least one repo.
        raise HTTPException(
            status_code=400,
            detail=(
                "no data-product yaml found.  Either set "
                "data_products.yaml_search_paths "
                "(POINTLESSQL_DATA_PRODUCTS_YAML_SEARCH_PATHS) to a "
                "directory or yaml file, or register and sync a "
                "workspace_repo whose tree contains pointlessql.yaml."
            ),
        )
    return {
        "loaded": len(contracts),
        "env_paths": [str(p) for p in env_paths],
    }
