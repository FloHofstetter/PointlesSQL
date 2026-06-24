"""Mutation-kill tests for the catalog-listing client forwarding.

Covers ``pointlessql.pql._list.list_catalogs`` (the low-level helper) and
``pointlessql.pql._pql_list._ListMixin.list_catalogs`` (the façade method
that dispatches into it) — both must forward the *real* client, not None.
"""

from __future__ import annotations

import types
from typing import Any

from pointlessql.pql import _list
from pointlessql.pql._pql_list import _ListMixin


def test_list_catalogs_forwards_the_client(monkeypatch: Any) -> None:
    """The helper passes the caller's client into the generated sync call."""
    # kills _list_catalogs.sync(client=client) -> sync(client=None)
    captured: dict[str, Any] = {}

    def fake_sync(*, client: Any) -> None:
        captured["client"] = client
        return None  # not a ListCatalogsResponse -> helper returns []

    monkeypatch.setattr(_list, "_list_catalogs", types.SimpleNamespace(sync=fake_sync))
    sentinel = object()
    assert _list.list_catalogs(sentinel) == []  # type: ignore[arg-type]
    assert captured["client"] is sentinel


def test_listmixin_list_catalogs_forwards_its_client(monkeypatch: Any) -> None:
    """The mixin method dispatches with ``self._client``, not None."""
    # kills list_catalogs(self._client) -> list_catalogs(None)
    captured: dict[str, Any] = {}

    def fake_list_catalogs(client: Any) -> list[Any]:
        captured["client"] = client
        return []

    monkeypatch.setattr("pointlessql.pql._pql_list.list_catalogs", fake_list_catalogs)
    # Real instance (via __new__) so the mutmut trampoline's getattr(self, ...)
    # dispatch resolves on the owning class.
    obj = _ListMixin.__new__(_ListMixin)
    obj._client = object()  # type: ignore[misc]
    obj.list_catalogs()
    assert captured["client"] is obj._client
