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
from pointlessql.api.data_products_routes.comments import router as _comments_router
from pointlessql.api.data_products_routes.detail import router as _detail_router
from pointlessql.api.data_products_routes.diff import router as _diff_router
from pointlessql.api.data_products_routes.lineage import router as _lineage_router
from pointlessql.api.data_products_routes.listing import router as _listing_router
from pointlessql.api.data_products_routes.reload import router as _reload_router
from pointlessql.api.data_products_routes.reviews import router as _reviews_router

router = APIRouter(tags=["data-products"])
router.include_router(_listing_router)
router.include_router(_detail_router)
router.include_router(_diff_router)
router.include_router(_lineage_router)
router.include_router(_reload_router)
router.include_router(_comments_router)
router.include_router(_reviews_router)


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
