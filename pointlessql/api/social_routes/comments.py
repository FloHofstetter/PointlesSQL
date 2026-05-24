"""Polymorphic comments router.

Wraps the polymorphic ``/api/social/{kind}/{ref:path}/comments``
namespace.  For ``kind='dp'`` the call is delegated in-process to
the existing Phase-76 DP comment handlers (zero behavioural drift,
legacy ``data_product:`` audit-prefix preserved per locked
decision #9).  For ``kind='table'`` and ``kind='branch'`` Phase
77.1.5 routes the call through the generic kind-agnostic handlers
in :mod:`_polymorphic_handlers`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from pointlessql.api.data_products_routes.comments import (
    accept_answer,
    delete_data_product_comment,
    list_data_product_comments,
    post_data_product_comment,
)
from pointlessql.api.social_routes._kind_dispatch import (
    parse_dp_ref,
    parse_ref,
)
from pointlessql.api.social_routes._polymorphic_handlers import (
    delete_polymorphic_comment,
    list_polymorphic_comments,
    post_polymorphic_comment,
)

router = APIRouter(tags=["social"])


@router.get("/api/social/{kind}/{ref:path}/comments")
async def list_social_comments(kind: str, ref: str, request: Request) -> dict[str, Any]:
    """Dispatch a list-comments request by entity kind."""
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await list_data_product_comments(catalog, schema, request)
    polymorphic_ref = parse_ref(kind, ref)
    return await list_polymorphic_comments(kind, polymorphic_ref, request)


@router.post("/api/social/{kind}/{ref:path}/comments")
async def post_social_comment(kind: str, ref: str, request: Request) -> dict[str, Any]:
    """Dispatch a comment POST by entity kind.

    Re-extracts ``?as_agent=`` for both the DP path *and* the
    polymorphic path so cell-level review decisions authored by
    ``hermes`` (and any future agent-on-behalf-of flow) carry the
    presentation-layer envelope into the row.  The principal-or-
    admin gate inside :func:`resolve_agent_for_principal` still
    applies — un-authorised callers see a 403.
    """
    as_agent = request.query_params.get("as_agent")
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await post_data_product_comment(catalog, schema, request, as_agent=as_agent)
    polymorphic_ref = parse_ref(kind, ref)
    return await post_polymorphic_comment(kind, polymorphic_ref, request, as_agent=as_agent)


@router.post("/api/social/{kind}/{ref:path}/comments/{comment_id}/accept-answer")
async def accept_social_answer(
    kind: str, ref: str, comment_id: int, request: Request
) -> dict[str, Any]:
    """Dispatch the accept-answer flow by entity kind.

    Only ``kind='dp'`` supports accepted-answers in 77.1.5 (Question
    threads were a DP-discussion feature; not yet generalised to
    table / branch entities).
    """
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await accept_answer(catalog, schema, comment_id, request)
    # bare-http-ok: feature is DP-only this phase.
    raise HTTPException(
        status_code=501,
        detail=(
            f"accept-answer for kind={kind!r} is deferred — "
            "Phase 77.7 (Issues) brings question/answer flow to "
            "polymorphic entities"
        ),
    )


@router.delete("/api/social/{kind}/{ref:path}/comments/{comment_id}")
async def delete_social_comment(
    kind: str, ref: str, comment_id: int, request: Request
) -> dict[str, Any]:
    """Dispatch a comment soft-delete by entity kind."""
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return await delete_data_product_comment(catalog, schema, comment_id, request)
    polymorphic_ref = parse_ref(kind, ref)
    return await delete_polymorphic_comment(kind, polymorphic_ref, comment_id, request)
