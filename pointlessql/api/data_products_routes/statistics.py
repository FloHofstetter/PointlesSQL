"""Self-generated statistics endpoint for a data product.

Read-only — the rows are stamped at write time by the operation
lifecycle hook, not edited here.  Returns the latest snapshot per
table, with the freshness lag computed at read time.

* ``GET .../{catalog}/{schema}/statistics``
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.dependencies import current_workspace_id, require_user
from pointlessql.services.data_product_stats import read_latest_statistics

router = APIRouter(tags=["data-products"])


@router.get("/api/data-products/{catalog}/{schema}/statistics")
async def get_statistics(catalog: str, schema: str, request: Request) -> dict[str, Any]:
    """Return the latest self-generated statistics snapshot per table."""
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    stats = read_latest_statistics(factory, data_product_id=dp_row.id)
    return {"statistics": stats}
