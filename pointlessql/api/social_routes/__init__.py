"""Polymorphic social router package (Phase 77.0.F.2).

Exposes ``/api/social/{kind}/{ref:path}/...`` as the canonical
namespace for every social affordance.  Phase 77.0 wires only
``kind='dp'`` (delegates to the existing DP-scoped handlers in
:mod:`pointlessql.api.data_products_routes`).  Other kinds raise
501 until 77.1+ extends the registry.

The legacy ``/api/data-products/{catalog}/{schema}/...`` routes
stay live as aliases so hermes-plugin-pointlessql and any external
caller keeps working unchanged.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.social_routes import (
    comments,
    endorsements,
    follows,
    issues,
    reactions,
    readme,
    reviews,
    stars,
)

router = APIRouter()
router.include_router(comments.router)
router.include_router(reviews.router)
router.include_router(endorsements.router)
router.include_router(follows.router)
router.include_router(reactions.router)
router.include_router(readme.router)
router.include_router(stars.router)
router.include_router(issues.router)


__all__: list[str] = ["router"]
