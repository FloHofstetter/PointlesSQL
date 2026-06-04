"""Unit tests for the post-commit data-product statistics hook.

``record_statistics_after_commit`` persists one ``data_product_statistics``
snapshot keyed on the just-committed op, optionally upgrading the cheap
"light" shape from a cached full profile. Covered: the no-op short-circuit,
a plain insert, the cache-upgrade branch (monkeypatched ``read_cached``),
and the pure ``_shape_from_cache`` distiller.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models.catalog._data_products import DataProductStatistics
from pointlessql.services.agent_runs.operations._statistics import (
    _shape_from_cache,
    record_statistics_after_commit,
)


def _rows(dp_id: int) -> list[DataProductStatistics]:
    factory = app.state.session_factory
    with factory() as session:
        return list(
            session.scalars(
                select(DataProductStatistics).where(
                    DataProductStatistics.data_product_id == dp_id
                )
            ).all()
        )


# --- _shape_from_cache (pure) --------------------------------------------


def test_shape_from_cache_distills_columns() -> None:
    cached = [
        {"column_name": "a", "stats": {"null_count": 0, "distinct_count": 3, "min": 1, "max": 9}},
        {"column_name": "b", "stats": {"null_count": 2, "distinct_count": 1}},
    ]
    shape = _shape_from_cache(cached)
    assert shape["column_count"] == 2
    assert shape["columns"]["a"] == {"null_count": 0, "distinct": 3, "min": 1, "max": 9}
    assert shape["columns"]["b"]["distinct"] == 1


def test_shape_from_cache_skips_malformed_entries() -> None:
    cached = [
        {"column_name": None, "stats": {}},
        {"column_name": "ok", "stats": "not-a-dict"},
        {"column_name": "good", "stats": {"null_count": 1}},
    ]
    shape = _shape_from_cache(cached)
    assert shape["column_count"] == 1
    assert "good" in shape["columns"]


# --- record_statistics_after_commit --------------------------------------


def test_none_pending_is_noop() -> None:
    # Must not raise or insert anything.
    record_statistics_after_commit(
        app.state.session_factory, op_id=1, target_table=None, pending=None
    )


def test_plain_insert_persists_snapshot() -> None:
    pending = (4101, "main.gold.t", None, 5, {"column_count": 1}, "light")
    record_statistics_after_commit(
        app.state.session_factory, op_id=11, target_table=None, pending=pending
    )
    rows = _rows(4101)
    assert len(rows) == 1
    assert rows[0].row_count == 5
    assert rows[0].profile_kind == "light"


def test_cache_upgrade_replaces_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_read_cached(factory: Any, *, full_name: str, delta_log_version: int) -> Any:
        return [{"column_name": "x", "stats": {"null_count": 0, "distinct_count": 2}}]

    monkeypatch.setattr(
        "pointlessql.services.table_stats.read_cached", _fake_read_cached
    )
    pending = (4102, "main.gold.u", 7, 10, {"column_count": 0}, "light")
    record_statistics_after_commit(
        app.state.session_factory, op_id=12, target_table="main.gold.u", pending=pending
    )
    rows = _rows(4102)
    assert len(rows) == 1
    # profile_kind upgraded to "reused", shape distilled from the cache.
    assert rows[0].profile_kind == "reused"
    assert '"x"' in rows[0].shape_json
