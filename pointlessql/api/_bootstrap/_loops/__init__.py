# pyright: reportPrivateUsage=false
# This package's __init__ re-exports the package-private ``_*_loop``
# coroutines from the per-domain sub-modules so the lifespan can keep
# importing them from one path — the cross-module access is intentional.
"""Background-task coroutines started by the lifespan.

Each coroutine is a long-running ``while True`` loop that performs
one bookkeeping pass per cadence and survives transient failures.
The lifespan in ``api.main`` schedules them as ``asyncio.Task``
instances at startup and cancels them at shutdown.

All loops share the same shape:

1. Snapshot the relevant settings sub-tree at start.
2. Loop forever; per tick: do work guarded by a broad ``except``,
   then sleep for the interval, then bail cleanly on
   ``asyncio.CancelledError``.

This module is private (``_bootstrap`` package).  ``main.py``
imports the loop functions directly; nothing else should call them.
The coroutines live in per-domain sub-modules and are re-exported
here so the historical import path keeps resolving.
"""

from __future__ import annotations

from pointlessql.api._bootstrap._loops._api_keys import (
    _api_key_lifecycle_sweep_loop,
    _api_key_usage_flush_loop,
    _api_key_usage_retention_loop,
)
from pointlessql.api._bootstrap._loops._data_products import (
    _active_reviewer_loop,
    _data_product_cooccurrence_loop,
    _data_product_freshness_loop,
    _data_product_passport_loop,
    _data_product_promotion_loop,
    _data_product_trending_loop,
)
from pointlessql.api._bootstrap._loops._lineage import (
    _branch_cleanup_loop,
    _cdf_tail_loop,
    _external_writes_loop,
    _lineage_pruner_loop,
)
from pointlessql.api._bootstrap._loops._platform import (
    _audit_retention_loop,
    _event_retention_loop,
    _user_badges_loop,
    _user_notification_digest_loop,
    _workspace_repos_sync_loop,
)

__all__ = [
    "_active_reviewer_loop",
    "_api_key_lifecycle_sweep_loop",
    "_api_key_usage_flush_loop",
    "_api_key_usage_retention_loop",
    "_audit_retention_loop",
    "_branch_cleanup_loop",
    "_cdf_tail_loop",
    "_event_retention_loop",
    "_data_product_cooccurrence_loop",
    "_data_product_freshness_loop",
    "_data_product_passport_loop",
    "_data_product_promotion_loop",
    "_data_product_trending_loop",
    "_external_writes_loop",
    "_lineage_pruner_loop",
    "_user_badges_loop",
    "_user_notification_digest_loop",
    "_workspace_repos_sync_loop",
]
