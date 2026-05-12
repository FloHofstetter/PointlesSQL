"""ORM models for catalog metadata: queries, dashboards, recents, autoload, data products, sync.

Five flat sibling modules consolidated into one
``pointlessql.models.catalog`` package whose ``__init__.py``
re-exports the 11 public symbols.

Layout:

* ``_metadata``       — :class:`Dashboard`, :class:`QueryHistory`,
                        :class:`QueryHistoryTable`, :class:`RateLimitEvent`,
                        :class:`SavedQuery`, :class:`TableStats`.
* ``_recents``        — :class:`RecentTable` (per-user catalog-tree
                        recently-visited bookmarks).
* ``_autoload``       — :class:`AutoloadCheckpoint` (autoload
                        per-target-table progress checkpoint).
* ``_data_products``  — :class:`DataProduct`,
                        :class:`DataProductContractEvent`
                        + ``CONTRACT_EVENT_OUTCOMES`` constant.
* ``_data_product_comments`` — :class:`DataProductComment`
                        (Phase 71.1, threaded discussion rows).
* ``_data_product_reviews``  — :class:`DataProductReview`
                        (Phase 71.2, one-per-user star + body row).
* ``_data_product_follows``  — :class:`DataProductFollow`
                        (Phase 71.3, composite-PK follow link).
* ``_data_product_readme``   — :class:`DataProductReadme`
                        (Phase 71.5, versioned per-DP wiki).
* ``_sync``           — :class:`SyncRun` (foreign-catalog sync run
                        history).
"""

from __future__ import annotations

from pointlessql.models.catalog._autoload import AutoloadCheckpoint
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.models.catalog._data_product_follows import DataProductFollow
from pointlessql.models.catalog._data_product_readme import DataProductReadme
from pointlessql.models.catalog._data_product_reviews import DataProductReview
from pointlessql.models.catalog._data_products import (
    CONTRACT_EVENT_OUTCOMES,
    DataProduct,
    DataProductContractEvent,
)
from pointlessql.models.catalog._metadata import (
    Dashboard,
    QueryHistory,
    QueryHistoryTable,
    RateLimitEvent,
    SavedQuery,
    TableStats,
)
from pointlessql.models.catalog._recents import RecentTable
from pointlessql.models.catalog._sync import SyncRun

__all__ = [
    "CONTRACT_EVENT_OUTCOMES",
    "AutoloadCheckpoint",
    "Dashboard",
    "DataProduct",
    "DataProductComment",
    "DataProductContractEvent",
    "DataProductFollow",
    "DataProductReadme",
    "DataProductReview",
    "QueryHistory",
    "QueryHistoryTable",
    "RateLimitEvent",
    "RecentTable",
    "SavedQuery",
    "SyncRun",
    "TableStats",
]
