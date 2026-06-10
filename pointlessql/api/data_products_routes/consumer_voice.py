"""Consumer-contributed metadata routes (C).

Use cases + ratings — the consumer-side discovery surface.  Any-user
POST for use-cases / votes / own-rating; steward / admin may delete a
use case.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query, Request
from sqlalchemy import select

from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.exceptions import AuthorizationError, BadRequestError, ResourceNotFoundError
from pointlessql.models import DataProductRating
from pointlessql.services import consumer_voice as consumer_voice_service

router = APIRouter(tags=["data-products"])


def _require_steward_or_admin(request: Request, dp_row: Any) -> None:
    user = get_user(request)
    if user.get("is_admin"):
        return
    if dp_row.steward_user_id is not None and dp_row.steward_user_id == user["id"]:
        return
    raise AuthorizationError(
        principal=user.get("email", ""),
        privilege="steward",
        securable_type="data_product",
        full_name=f"{dp_row.catalog_name}.{dp_row.schema_name}",
    )


@router.get("/api/data-products/{catalog}/{schema}/use-cases")
async def list_use_cases(
    catalog: str,
    schema: str,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """Return the product's use cases ordered by votes."""
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    dp_row, _, _, _ = load_one(factory, workspace_id, catalog, schema)
    return {
        "use_cases": consumer_voice_service.list_use_cases(
            factory, data_product_id=int(dp_row.id), limit=limit
        )
    }


@router.post("/api/data-products/{catalog}/{schema}/use-cases")
async def add_use_case(
    catalog: str,
    schema: str,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Share a use case (any authenticated user)."""
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    dp_row, _, _, _ = load_one(factory, workspace_id, catalog, schema)
    user = get_user(request)
    try:
        result = consumer_voice_service.add_use_case(
            factory,
            data_product_id=int(dp_row.id),
            title=str(body.get("title", "")),
            body=str(body.get("body", "")),
            author_user_id=int(user.get("id", 0) or 0) or None,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
    return result


@router.delete("/api/data-products/{catalog}/{schema}/use-cases/{use_case_id}")
async def delete_use_case(
    catalog: str, schema: str, use_case_id: int, request: Request
) -> dict[str, Any]:
    """Delete a use case (steward / admin)."""
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    dp_row, _, _, _ = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(request, dp_row)
    removed = consumer_voice_service.delete_use_case(
        factory, data_product_id=int(dp_row.id), use_case_id=use_case_id
    )
    if not removed:
        raise ResourceNotFoundError(f"use case {use_case_id} not found")
    return {"deleted": True}


@router.post("/api/data-products/{catalog}/{schema}/use-cases/{use_case_id}/vote")
async def vote_use_case(
    catalog: str, schema: str, use_case_id: int, request: Request
) -> dict[str, Any]:
    """Toggle the caller's vote on one use case."""
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    dp_row, _, _, _ = load_one(factory, workspace_id, catalog, schema)
    del dp_row  # the use-case belongs to this product by URL contract
    user = get_user(request)
    return consumer_voice_service.vote_use_case(
        factory,
        use_case_id=use_case_id,
        user_id=int(user.get("id", 0) or 0),
        upvote=True,
    )


@router.get("/api/data-products/{catalog}/{schema}/rating")
async def get_rating(catalog: str, schema: str, request: Request) -> dict[str, Any]:
    """Return the product's rating summary + caller's own row."""
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    dp_row, _, _, _ = load_one(factory, workspace_id, catalog, schema)
    summary = consumer_voice_service.list_rating_summary(factory, data_product_id=int(dp_row.id))
    user = get_user(request)
    own: dict[str, Any] | None = None
    if user.get("id"):
        with factory() as session:
            row = session.scalar(
                select(DataProductRating).where(
                    DataProductRating.data_product_id == int(dp_row.id),
                    DataProductRating.user_id == int(user["id"]),
                )
            )
            if row is not None:
                own = {"score": row.score, "comment": row.comment}
    return {"avg": summary["avg"], "count": summary["count"], "own": own}


@router.put("/api/data-products/{catalog}/{schema}/rating")
async def upsert_rating(
    catalog: str,
    schema: str,
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Upsert the caller's own rating (any authenticated user)."""
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    dp_row, _, _, _ = load_one(factory, workspace_id, catalog, schema)
    user = get_user(request)
    try:
        result = consumer_voice_service.upsert_rating(
            factory,
            data_product_id=int(dp_row.id),
            user_id=int(user.get("id", 0) or 0),
            score=int(body.get("score", 0)),
            comment=body.get("comment"),
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
    return result
