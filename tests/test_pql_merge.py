"""Unit tests for the PQL merge strategies + audit-stats massagers.

``_stats.py`` is pure (row-count rollups + JSON-safe coercion).
``_strategies.py`` is exercised both purely (``_augment_for_scd2`` column
shaping) and against a real temp Delta table for the upsert / SCD-2 merge
round-trips — ``deltalake`` is a first-class dependency, so a tmp-path
table is the honest way to cover the actual merge path.
"""

from __future__ import annotations

import deltalake
import pyarrow as pa

from pointlessql.pql._merge._stats import _merge_rows_affected, _stats_for_audit
from pointlessql.pql._merge._strategies import _augment_for_scd2, _do_scd2, _do_upsert


# --- _merge_rows_affected (pure) -----------------------------------------


def test_rows_affected_upsert_sums_inserted_and_updated() -> None:
    stats = {
        "strategy": "upsert",
        "num_target_rows_inserted": 3,
        "num_target_rows_updated": 2,
    }
    assert _merge_rows_affected(stats) == 5


def test_rows_affected_scd2_sums_appended_and_closed() -> None:
    stats = {
        "strategy": "scd2",
        "rows_appended": 4,
        "close_stats": {"num_target_rows_updated": 1},
    }
    assert _merge_rows_affected(stats) == 5


def test_rows_affected_unknown_strategy_is_none() -> None:
    assert _merge_rows_affected({"strategy": "other"}) is None


def test_rows_affected_missing_keys_default_zero() -> None:
    assert _merge_rows_affected({"strategy": "upsert"}) == 0


# --- _stats_for_audit (pure) ---------------------------------------------


def test_stats_for_audit_passes_scalars_through() -> None:
    out = _stats_for_audit({"a": 1, "b": "x", "c": True, "d": None, "e": 1.5})
    assert out == {"a": 1, "b": "x", "c": True, "d": None, "e": 1.5}


def test_stats_for_audit_recurses_into_dicts() -> None:
    out = _stats_for_audit({"nested": {"k": 1, "obj": object()}})
    assert out["nested"]["k"] == 1
    assert isinstance(out["nested"]["obj"], str)


def test_stats_for_audit_stringifies_non_scalar_list_items() -> None:
    out = _stats_for_audit({"items": [1, "x", object()]})
    assert out["items"][0] == 1
    assert out["items"][1] == "x"
    assert isinstance(out["items"][2], str)


def test_stats_for_audit_stringifies_other_values() -> None:
    out = _stats_for_audit({"weird": object()})
    assert isinstance(out["weird"], str)


# --- _augment_for_scd2 (pure) --------------------------------------------


def test_augment_appends_three_scd2_columns() -> None:
    import datetime as _dt

    source = pa.table({"id": [1, 2], "v": ["a", "b"]})
    now = _dt.datetime(2026, 1, 1, tzinfo=_dt.UTC)
    out = _augment_for_scd2(source, now)
    assert out.column_names == ["id", "v", "_valid_from", "_valid_to", "_is_current"]
    assert out.num_rows == 2
    assert out.column("_is_current").to_pylist() == [True, True]
    assert out.column("_valid_to").to_pylist() == [None, None]


# --- _do_upsert (real temp Delta table) ----------------------------------


def test_do_upsert_updates_and_inserts(tmp_path) -> None:
    loc = str(tmp_path / "upsert_tbl")
    deltalake.write_deltalake(loc, pa.table({"id": [1, 2], "v": ["a", "b"]}))
    source = pa.table({"id": [2, 3], "v": ["B", "C"]})

    result = _do_upsert(loc, source, ["id"])
    assert result["strategy"] == "upsert"
    assert _merge_rows_affected(result) == 2  # 1 updated (id=2) + 1 inserted (id=3)

    final = deltalake.DeltaTable(loc).to_pyarrow_table().to_pydict()
    rows = dict(zip(final["id"], final["v"], strict=True))
    assert rows == {1: "a", 2: "B", 3: "C"}


# --- _do_scd2 (real temp Delta table) ------------------------------------


def test_do_scd2_closes_open_row_and_appends(tmp_path) -> None:
    import datetime as _dt

    loc = str(tmp_path / "scd2_tbl")
    # Seed the target with one open (current) version of id=1.
    seed = _augment_for_scd2(
        pa.table({"id": [1], "v": ["old"]}), _dt.datetime(2025, 1, 1, tzinfo=_dt.UTC)
    )
    deltalake.write_deltalake(loc, seed)

    result = _do_scd2(loc, pa.table({"id": [1], "v": ["new"]}), ["id"])
    assert result["strategy"] == "scd2"
    assert result["rows_appended"] == 1

    final = deltalake.DeltaTable(loc).to_pyarrow_table().to_pydict()
    # Two physical rows now: the closed old one and the new current one.
    current_flags = final["_is_current"]
    assert current_flags.count(True) == 1
    assert current_flags.count(False) == 1
