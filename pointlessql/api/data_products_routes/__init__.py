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
from pointlessql.api.data_products_routes.apply import router as _apply_router
from pointlessql.api.data_products_routes.active_reviewer import (
    router as _active_reviewer_router,
)
from pointlessql.api.data_products_routes.activity import router as _activity_router
from pointlessql.api.data_products_routes.bitemporal_policy import (
    router as _bitemporal_policy_router,
)
from pointlessql.api.data_products_routes.candidates import (
    router as _candidates_router,
)
from pointlessql.api.data_products_routes.comments import router as _comments_router
from pointlessql.api.data_products_routes.consumer_voice import (
    router as _consumer_voice_router,
)
from pointlessql.api.data_products_routes.consumption_events import (
    router as _consumption_events_router,
)
from pointlessql.api.data_products_routes.contract_tests import (
    router as _contract_tests_router,
)
from pointlessql.api.data_products_routes.contracts import router as _contracts_router
from pointlessql.api.data_products_routes.detail import router as _detail_router
from pointlessql.api.data_products_routes.diff import router as _diff_router
from pointlessql.api.data_products_routes.discovery import router as _discovery_router
from pointlessql.api.data_products_routes.domain import router as _domain_router
from pointlessql.api.data_products_routes.endorsements import (
    router as _endorsements_router,
)
from pointlessql.api.data_products_routes.entities import (
    router as _entities_router,
)
from pointlessql.api.data_products_routes.event_port import (
    router as _event_port_router,
)
from pointlessql.api.data_products_routes.export import router as _export_router
from pointlessql.api.data_products_routes.follows import router as _follows_router
from pointlessql.api.data_products_routes.forks import router as _forks_router
from pointlessql.api.data_products_routes.governance import router as _governance_router
from pointlessql.api.data_products_routes.heatmap import router as _heatmap_router
from pointlessql.api.data_products_routes.infrastructure import (
    router as _infrastructure_router,
)
from pointlessql.api.data_products_routes.ingest_status import (
    router as _ingest_status_router,
)
from pointlessql.api.data_products_routes.interop import router as _interop_router
from pointlessql.api.data_products_routes.lifecycle import router as _lifecycle_router
from pointlessql.api.data_products_routes.lineage import router as _lineage_router
from pointlessql.api.data_products_routes.listing import router as _listing_router
from pointlessql.api.data_products_routes.passport import router as _passport_router
from pointlessql.api.data_products_routes.ports import router as _ports_router
from pointlessql.api.data_products_routes.proposals import (
    router as _proposals_router,
)
from pointlessql.api.data_products_routes.reactions import router as _reactions_router
from pointlessql.api.data_products_routes.readme import router as _readme_router
from pointlessql.api.data_products_routes.recommendations import (
    router as _recommendations_router,
)
from pointlessql.api.data_products_routes.releases import router as _releases_router
from pointlessql.api.data_products_routes.reload import router as _reload_router
from pointlessql.api.data_products_routes.reviews import router as _reviews_router
from pointlessql.api.data_products_routes.semantic import router as _semantic_router
from pointlessql.api.data_products_routes.slo import router as _slo_router
from pointlessql.api.data_products_routes.statistics import router as _statistics_router
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
router.include_router(_ingest_status_router)
router.include_router(_forks_router)
router.include_router(_heatmap_router)
router.include_router(_releases_router)
router.include_router(_domain_router)
router.include_router(_discovery_router)
router.include_router(_ports_router)
router.include_router(_semantic_router)
router.include_router(_statistics_router)
router.include_router(_export_router)
router.include_router(_governance_router)
router.include_router(_interop_router)
router.include_router(_slo_router)
router.include_router(_lifecycle_router)
router.include_router(_event_port_router)
router.include_router(_infrastructure_router)
router.include_router(_consumer_voice_router)
router.include_router(_consumption_events_router)
router.include_router(_bitemporal_policy_router)
router.include_router(_entities_router)
router.include_router(_contract_tests_router)
router.include_router(_apply_router)


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
