"""Mutation-kill tests for ``_ReadMixin`` read dispatch.

Pins that ``table`` forwards the real client and that
``table_as_of_event_time`` reads the *named* table (not ``None``).

The mixin methods are exercised on a real ``_ReadMixin`` instance built via
``__new__`` (skipping the heavy constructor): under mutmut the trampoline
dispatches through ``getattr(self, "<mangled>")``, which only resolves on a
genuine instance of the owning class, not a bare ``SimpleNamespace``.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from pointlessql.pql import _pql_read
from pointlessql.pql._pql_read import _ReadMixin


def test_table_forwards_the_client(monkeypatch: Any) -> None:
    """``table`` dispatches into read_table with ``self._client``, not None."""
    # kills client=self._client -> client=None
    captured: dict[str, Any] = {}

    def fake_read_table(*, client: Any, engine: Any, full_name: Any, unreachable_msg: Any) -> str:
        captured.update(client=client, full_name=full_name)
        return "FRAME"

    monkeypatch.setattr(_pql_read, "read_table", fake_read_table)
    obj = _ReadMixin.__new__(_ReadMixin)
    obj._client = object()  # type: ignore[misc]
    obj._engine = object()  # type: ignore[assignment]
    obj._branch_remap = lambda n: n  # type: ignore[method-assign,assignment]
    obj._unreachable_msg = lambda: "msg"  # type: ignore[method-assign,assignment]
    assert obj.table("c.s.t") == "FRAME"
    assert captured["client"] is obj._client


def test_table_as_of_event_time_reads_the_named_table() -> None:
    """The business-time read pulls the requested table, not ``None``."""
    # kills frame = self.table(full_name) -> self.table(None)
    seen: dict[str, Any] = {}
    frame = pd.DataFrame({"event_time": [1, 2, 3], "v": [10, 20, 30]})

    def fake_table(full_name: str) -> pd.DataFrame:
        seen["full_name"] = full_name
        return frame

    obj = _ReadMixin.__new__(_ReadMixin)
    obj.table = fake_table  # type: ignore[method-assign]
    out = obj.table_as_of_event_time("c.s.t", when=2, event_column="event_time")
    assert seen["full_name"] == "c.s.t"
    assert list(out["v"]) == [10, 20]
