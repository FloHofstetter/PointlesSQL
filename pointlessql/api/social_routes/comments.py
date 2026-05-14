"""Polymorphic comments router (Phase 77.0.F.2).

Wraps the DP-scoped comment routes at
``/api/social/{kind}/{ref:path}/comments`` so future kinds (table /
model / branch / run / ...) can plug into the same path shape.  In
77.0 only ``kind='dp'`` is wired; other kinds raise 501.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from pointlessql.api.data_products_routes.comments import (
    accept_answer,
    delete_data_product_comment,
    list_data_product_comments,
    post_data_product_comment,
)
from pointlessql.api.social_routes._kind_dispatch import parse_dp_ref

router = APIRouter(tags=["social"])


@router.get("/api/social/{kind}/{ref:path}/comments")
async def list_social_comments(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Delegate to the DP comment list handler for ``kind='dp'``."""
    catalog, schema = parse_dp_ref(kind, ref)
    return await list_data_product_comments(catalog, schema, request)


@router.post("/api/social/{kind}/{ref:path}/comments")
async def post_social_comment(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Delegate to the DP comment POST handler for ``kind='dp'``.

    Re-extracts ``?as_agent=`` so the speak-as-agent path survives
    the indirection.
    """
    catalog, schema = parse_dp_ref(kind, ref)
    as_agent = request.query_params.get("as_agent")
    return await post_data_product_comment(
        catalog, schema, request, as_agent=as_agent
    )


@router.post(
    "/api/social/{kind}/{ref:path}/comments/{comment_id}/accept-answer"
)
async def accept_social_answer(
    kind: str, ref: str, comment_id: int, request: Request
) -> dict[str, Any]:
    """Delegate to the DP accept-answer handler for ``kind='dp'``."""
    catalog, schema = parse_dp_ref(kind, ref)
    return await accept_answer(catalog, schema, comment_id, request)


@router.delete("/api/social/{kind}/{ref:path}/comments/{comment_id}")
async def delete_social_comment(
    kind: str, ref: str, comment_id: int, request: Request
) -> dict[str, Any]:
    """Delegate to the DP comment soft-delete handler."""
    catalog, schema = parse_dp_ref(kind, ref)
    return await delete_data_product_comment(
        catalog, schema, comment_id, request
    )
