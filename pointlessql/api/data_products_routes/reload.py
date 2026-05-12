"""``POST /api/data-products/reload`` — admin trigger to re-load every yaml."""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from pointlessql.api.dependencies import current_workspace_id, require_admin
from pointlessql.config import Settings
from pointlessql.data_products import load_contracts_for_workspace
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_DATA_PRODUCT_SCHEMA_CHANGED,
    emit_governance_event,
)

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

    # Phase 71 follow-up B.1: snapshot the pre-reload
    # ``contract_yaml_hash`` for every existing product in the
    # workspace.  After the reload, compare per-product against
    # the post-reload hash; emit
    # ``pointlessql.data_product.schema_changed`` for any that
    # actually changed.  First-load (no prior hash) does *not*
    # emit — that is a creation event, not a schema change.
    with factory() as session:
        pre_hashes: dict[tuple[str, str], str] = {
            (r.catalog_name, r.schema_name): r.contract_yaml_hash
            for r in session.execute(
                select(DataProduct).where(DataProduct.workspace_id == workspace_id)
            ).scalars()
        }

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

    # Phase 71 follow-up B.1: per-product schema-change detection.
    if contracts:
        keys = [(c.catalog, c.schema_name) for c in contracts]
        with factory() as session:
            post_rows = {
                (r.catalog_name, r.schema_name): r
                for r in session.execute(
                    select(DataProduct).where(
                        DataProduct.workspace_id == workspace_id,
                        DataProduct.catalog_name.in_([k[0] for k in keys]),
                        DataProduct.schema_name.in_([k[1] for k in keys]),
                    )
                ).scalars()
            }
        emitted = 0
        for c in contracts:
            key = (c.catalog, c.schema_name)
            row = post_rows.get(key)
            if row is None:
                continue
            new_hash = row.contract_yaml_hash
            old_hash = pre_hashes.get(key)
            if old_hash is None or old_hash == new_hash:
                continue
            await emit_governance_event(
                EVENT_TYPE_DATA_PRODUCT_SCHEMA_CHANGED,
                {
                    "data_product_id": row.id,
                    "data_product_ref": f"{c.catalog}.{c.schema_name}",
                    "previous_hash": old_hash,
                    "new_hash": new_hash,
                },
                settings=settings,
                session_factory=factory,
                workspace_id=workspace_id,
            )
            emitted += 1

    return {
        "loaded": len(contracts),
        "env_paths": [str(p) for p in env_paths],
    }
