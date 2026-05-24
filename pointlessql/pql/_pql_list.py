# pyright: reportUnusedClass=false
"""Catalog / schema / table listing for the PQL façade.

The module name carries the ``_pql_`` prefix to avoid collision
with :mod:`pointlessql.pql._list` (the lower-level helper this
mixin dispatches into).
"""

from __future__ import annotations

from typing import Any

from pointlessql.pql._list import list_catalogs, list_schemas, list_tables
from pointlessql.pql._pql_base import PQLBase as _PQLBase


class _ListMixin(_PQLBase):
    """List catalogs, schemas, and tables visible to the caller."""

    def list_catalogs(self) -> list[dict[str, Any]]:
        """Return all catalogs visible to the caller.

        Returns:
            A list of catalog dicts with at least a ``"name"`` key.
        """
        return list_catalogs(self._client)

    def list_schemas(self, catalog: str) -> list[dict[str, Any]]:
        """Return all schemas inside a catalog.

        Args:
            catalog: Name of the parent catalog.

        Returns:
            A list of schema dicts.
        """
        return list_schemas(self._client, catalog)

    def list_tables(self, catalog: str, schema: str) -> list[dict[str, Any]]:
        """Return all tables inside a schema.

        Args:
            catalog: Name of the parent catalog.
            schema: Name of the parent schema.

        Returns:
            A list of table identifier dicts.
        """
        return list_tables(self._client, catalog, schema)
