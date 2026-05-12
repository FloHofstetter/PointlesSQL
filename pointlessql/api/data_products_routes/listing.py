"""``GET /api/data-products`` — list every cached product in workspace."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import select

from pointlessql.api.data_products_routes._shared import serialise_product
from pointlessql.api.dependencies import current_workspace_id
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_products import DataProduct

router = APIRouter(tags=["data-products"])


@router.get("/api/data-products")
async def list_data_products(request: Request) -> dict[str, Any]:
    """Return every cached data product in the active workspace.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"workspace_id": int, "data_products": [...]}`` ordered by
        catalog/schema name.
    """
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    items: list[dict[str, Any]] = []
    with factory() as session:
        rows = (
            session.execute(
                select(DataProduct)
                .where(DataProduct.workspace_id == workspace_id)
                .order_by(DataProduct.catalog_name, DataProduct.schema_name)
            )
            .scalars()
            .all()
        )
        steward_ids = [r.steward_user_id for r in rows if r.steward_user_id is not None]
        steward_map: dict[int, tuple[str, str]] = {}
        if steward_ids:
            users = (
                session.execute(select(User).where(User.id.in_(steward_ids)))
                .scalars()
                .all()
            )
            steward_map = {u.id: (u.email, u.display_name) for u in users}

        for row in rows:
            email, display = (
                steward_map.get(row.steward_user_id, (None, None))
                if row.steward_user_id is not None
                else (None, None)
            )
            items.append(
                serialise_product(
                    row,
                    steward_email=email,
                    steward_display_name=display,
                )
            )

    return {"workspace_id": workspace_id, "data_products": items}
