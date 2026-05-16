"""``/audit/*`` and ``/api/audit/*`` route surface, split per axis.

This package consolidates the audit route surface that used to live
in flat sibling modules at ``pointlessql/api/`` root.  The combined
router is mounted by ``api.main`` exactly once via
``router = APIRouter(); router.include_router(...)`` in this
``__init__.py`` — callers no longer juggle individual router
references.

Layout:

* ``_helpers``        — shared workspace-lens, ISO-8601 parser,
                        audit-of-audit self-tracking.
* ``_metrics``        — ``/api/audit/{summary,timeseries,anomalies}``.
* ``_principal``      — ``/api/audit/principal-summary``.
* ``_pii``            — ``/api/audit/pii/reveal`` (admin-only).
* ``_history``        — ``/api/audit/history`` paginated trail.
* ``_cdf``            — ``/api/audit/cdf-{subscriptions,events}``.
* ``_anomaly_inbox``  — ``/api/audit/inbox`` + ``anomaly-acks`` CRUD.
* ``inbox``           — HTML cockpit at ``/audit/inbox`` (server-side
                        template; sibling to the JSON ``_anomaly_inbox``).
* ``sinks``           — admin CRUD for audit-stream destinations.
* ``search``          — the FTS-backed full-text audit-event search.
* ``by_table``        — per-table audit-event reverse index.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.audit._anomaly_inbox import router as _anomaly_inbox_router
from pointlessql.api.audit._cdf import router as _cdf_router
from pointlessql.api.audit._history import router as _history_router
from pointlessql.api.audit._metrics import router as _metrics_router
from pointlessql.api.audit._pii import router as _pii_router
from pointlessql.api.audit._principal import router as _principal_router
from pointlessql.api.audit.by_table import router as _by_table_router
from pointlessql.api.audit.inbox import router as _inbox_router
from pointlessql.api.audit.search import router as _search_router
from pointlessql.api.audit.sinks import router as _sinks_router

router = APIRouter()
router.include_router(_metrics_router)
router.include_router(_principal_router)
router.include_router(_pii_router)
router.include_router(_history_router)
router.include_router(_cdf_router)
router.include_router(_anomaly_inbox_router)
router.include_router(_inbox_router)
router.include_router(_sinks_router)
router.include_router(_search_router)
router.include_router(_by_table_router)

__all__ = ["router"]
