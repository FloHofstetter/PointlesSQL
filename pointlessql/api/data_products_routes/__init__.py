"""Data-product browse + diff JSON surface — package facade.

Splits the previous 430-LOC ``data_products_routes.py`` module into
per-axis sub-modules: listing, detail, diff, lineage, reload (plus
the Phase-71 marketplace-polish add-ons that share this surface).
Public surface (the FastAPI router and the cross-module ``load_one``
helper) is re-exported here so existing imports like
``from pointlessql.api.data_products_routes import router`` and
``from pointlessql.api.data_products_routes import load_one``
continue to work unchanged.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.data_products_routes._shared import (
    load_one,
    serialise_product,
)
from pointlessql.api.data_products_routes.active_reviewer import (
    router as _active_reviewer_router,
)
from pointlessql.api.data_products_routes.activity import router as _activity_router
from pointlessql.api.data_products_routes.candidates import (
    router as _candidates_router,
)
from pointlessql.api.data_products_routes.comments import router as _comments_router
from pointlessql.api.data_products_routes.contracts import router as _contracts_router
from pointlessql.api.data_products_routes.detail import router as _detail_router
from pointlessql.api.data_products_routes.diff import router as _diff_router
from pointlessql.api.data_products_routes.endorsements import (
    router as _endorsements_router,
)
from pointlessql.api.data_products_routes.follows import router as _follows_router
from pointlessql.api.data_products_routes.lineage import router as _lineage_router
from pointlessql.api.data_products_routes.listing import router as _listing_router
from pointlessql.api.data_products_routes.passport import router as _passport_router
from pointlessql.api.data_products_routes.proposals import (
    router as _proposals_router,
)
from pointlessql.api.data_products_routes.reactions import router as _reactions_router
from pointlessql.api.data_products_routes.readme import router as _readme_router
from pointlessql.api.data_products_routes.recommendations import (
    router as _recommendations_router,
)
from pointlessql.api.data_products_routes.reload import router as _reload_router
from pointlessql.api.data_products_routes.reviews import router as _reviews_router
from pointlessql.api.data_products_routes.trending import router as _trending_router

router = APIRouter(tags=["data-products"])
router.include_router(_listing_router)
router.include_router(_detail_router)
router.include_router(_diff_router)
router.include_router(_lineage_router)
router.include_router(_reload_router)
router.include_router(_comments_router)
router.include_router(_reviews_router)
router.include_router(_follows_router)
router.include_router(_readme_router)
router.include_router(_activity_router)
router.include_router(_trending_router)
router.include_router(_endorsements_router)
router.include_router(_candidates_router)
router.include_router(_passport_router)
router.include_router(_recommendations_router)
router.include_router(_contracts_router)
router.include_router(_proposals_router)
router.include_router(_active_reviewer_router)
router.include_router(_reactions_router)


# Backwards-compatible aliases — ``_load_one`` was the original
# (private) name; the package-internal callers in
# ``data_products_html_routes`` and a few tests import it by that
# name.  The new public name is ``load_one``.
_load_one = load_one
_serialise_product = serialise_product


__all__ = [
    "_load_one",
    "_serialise_product",
    "load_one",
    "router",
    "serialise_product",
]
