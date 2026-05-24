"""column-stats reduction + LRU cache.

Pure unit tests against the pandas reduction in
``services.column_stats``.  The Delta-read path is monkeypatched
out; we only exercise the summarisation + cache invariants here.
End-to-end tests against a real Delta table live in
``test_catalog_stats_route.py``.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from pointlessql.services.column_stats import (
    compute_table_stats,
    invalidate_table_stats,
)
from pointlessql.services.column_stats._compute import _summarise_frame
from pointlessql.types import TableFqn

_FQN = TableFqn.from_parts("c1", "s1", "t1")


def setup_function() -> None:
    """Clear the LRU cache between tests."""
    invalidate_table_stats()


def _make_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5, None],
            "country": ["DE", "DE", "DE", "FR", "US", "FR"],
            "amount": [10.5, 20.0, 30.25, None, 40.0, 50.0],
            "all_null": [None, None, None, None, None, None],
        }
    )


def test_summarise_frame_row_count_and_columns() -> None:
    """Row count includes nulls; column list preserves order."""
    df = _make_df()
    result = _summarise_frame(df)
    assert result["row_count"] == 6
    column_names = [c["name"] for c in result["columns"]]
    assert column_names == ["id", "country", "amount", "all_null"]


def test_summarise_frame_numeric_extremes() -> None:
    """Numeric columns carry min + max; integer dtype handled."""
    result = _summarise_frame(_make_df())
    id_col = next(c for c in result["columns"] if c["name"] == "id")
    assert id_col["min"] == 1
    assert id_col["max"] == 5
    assert id_col["n_distinct"] == 5
    assert id_col["nullability_pct"] == pytest.approx(16.67, abs=0.05)
    assert "top_values" not in id_col


def test_summarise_frame_float_extremes() -> None:
    """Float columns produce float min/max, not numpy scalars."""
    result = _summarise_frame(_make_df())
    amount_col = next(c for c in result["columns"] if c["name"] == "amount")
    assert isinstance(amount_col["min"], float)
    assert amount_col["min"] == pytest.approx(10.5)
    assert amount_col["max"] == pytest.approx(50.0)


def test_summarise_frame_string_top_values() -> None:
    """Non-numeric columns carry top-5 value counts, descending."""
    result = _summarise_frame(_make_df())
    country_col = next(c for c in result["columns"] if c["name"] == "country")
    assert country_col["n_distinct"] == 3
    assert "min" not in country_col
    top_values = country_col["top_values"]
    assert top_values[0] == {"value": "DE", "count": 3}
    assert top_values[1] == {"value": "FR", "count": 2}
    assert top_values[2] == {"value": "US", "count": 1}


def test_summarise_frame_all_null_column() -> None:
    """Numeric / non-numeric columns where every value is NULL stay safe."""
    result = _summarise_frame(_make_df())
    all_null = next(c for c in result["columns"] if c["name"] == "all_null")
    assert all_null["nullability_pct"] == 100.0
    assert all_null["n_distinct"] == 0
    assert all_null["top_values"] == []


def test_summarise_frame_empty_frame() -> None:
    """Empty frames return ``row_count=0`` and ``columns=[]``."""
    result = _summarise_frame(pd.DataFrame())
    assert result == {"row_count": 0, "columns": []}


def test_compute_table_stats_caches_same_principal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Second call hits the LRU, doesn't re-scan."""
    call_count = {"n": 0}

    def fake_reader(*args: Any, **kwargs: Any) -> dict[str, Any]:
        call_count["n"] += 1
        return {"row_count": 42, "columns": []}

    monkeypatch.setattr(
        "pointlessql.services.column_stats._compute._read_and_summarise",
        fake_reader,
    )
    first = compute_table_stats(settings=None, principal="alice", full_name=_FQN)  # type: ignore[arg-type]
    second = compute_table_stats(settings=None, principal="alice", full_name=_FQN)  # type: ignore[arg-type]
    assert first == second
    assert call_count["n"] == 1


def test_compute_table_stats_per_principal_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two principals see independent cache entries."""
    call_count = {"n": 0}

    def fake_reader(*args: Any, **kwargs: Any) -> dict[str, Any]:
        call_count["n"] += 1
        return {"row_count": call_count["n"], "columns": []}

    monkeypatch.setattr(
        "pointlessql.services.column_stats._compute._read_and_summarise",
        fake_reader,
    )
    alice = compute_table_stats(settings=None, principal="alice", full_name=_FQN)  # type: ignore[arg-type]
    bob = compute_table_stats(settings=None, principal="bob", full_name=_FQN)  # type: ignore[arg-type]
    assert alice != bob
    assert call_count["n"] == 2


def test_invalidate_table_stats_per_fqn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalidating one FQN clears every principal's entry for it."""
    call_count = {"n": 0}
    other = TableFqn.from_parts("c1", "s1", "other")

    def fake_reader(*args: Any, **kwargs: Any) -> dict[str, Any]:
        call_count["n"] += 1
        return {"row_count": call_count["n"], "columns": []}

    monkeypatch.setattr(
        "pointlessql.services.column_stats._compute._read_and_summarise",
        fake_reader,
    )
    compute_table_stats(settings=None, principal="alice", full_name=_FQN)  # type: ignore[arg-type]
    compute_table_stats(settings=None, principal="alice", full_name=other)  # type: ignore[arg-type]
    assert call_count["n"] == 2

    invalidate_table_stats(_FQN)
    compute_table_stats(settings=None, principal="alice", full_name=_FQN)  # type: ignore[arg-type]
    # Other FQN still cached, only the targeted one was re-scanned.
    compute_table_stats(settings=None, principal="alice", full_name=other)  # type: ignore[arg-type]
    assert call_count["n"] == 3
