"""ORM models for catalog metadata: queries, dashboards, recents, autoload, data products.

Four flat sibling modules consolidated into one
``pointlessql.models.catalog`` package whose ``__init__.py``
re-exports the 10 public symbols.

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
"""

from __future__ import annotations

from pointlessql.models.catalog._autoload import AutoloadCheckpoint
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

__all__ = [
    "CONTRACT_EVENT_OUTCOMES",
    "AutoloadCheckpoint",
    "Dashboard",
    "DataProduct",
    "DataProductContractEvent",
    "QueryHistory",
    "QueryHistoryTable",
    "RateLimitEvent",
    "RecentTable",
    "SavedQuery",
    "TableStats",
]
