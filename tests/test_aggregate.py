"""Unit tests for the Sprint 15.5.1 aggregate primitive helpers.

The full ``aggregate_table`` end-to-end path needs a live soyuz +
deltalake stack and is exercised by the Sprint 15.5.5 live replay.
These tests cover the pure-Python helpers
(:func:`pointlessql.services.lineage_edges.synth_aggregate_target_row_id`
and :func:`pointlessql.pql._aggregate._build_aggregate_frame`) that
together produce the fan-in lineage payload.
"""

from __future__ import annotations

import pandas as pd
import pytest

from pointlessql.pql._aggregate import _build_aggregate_frame, aggregate_table
from pointlessql.services.lineage_edges import synth_aggregate_target_row_id


class TestSynthAggregateTargetRowID:
    """The deterministic ID-synthesis formula for aggregate output rows."""

    def test_determinism(self) -> None:
        a = synth_aggregate_target_row_id("main.gold.sales", ["2026-04-01", "widget"])
        b = synth_aggregate_target_row_id("main.gold.sales", ["2026-04-01", "widget"])
        assert a == b

    def test_uniqueness_per_group_values(self) -> None:
        a = synth_aggregate_target_row_id("main.gold.sales", ["2026-04-01", "widget"])
        b = synth_aggregate_target_row_id("main.gold.sales", ["2026-04-02", "widget"])
        c = synth_aggregate_target_row_id("main.gold.sales", ["2026-04-01", "gadget"])
        assert len({a, b, c}) == 3

    def test_uniqueness_per_target(self) -> None:
        a = synth_aggregate_target_row_id("main.gold.sales", ["2026-04-01", "widget"])
        b = synth_aggregate_target_row_id("main.gold.revenue", ["2026-04-01", "widget"])
        assert a != b

    def test_hex_digest_shape(self) -> None:
        out = synth_aggregate_target_row_id("main.gold.sales", ["x"])
        assert len(out) == 64
        assert all(c in "0123456789abcdef" for c in out)


class TestBuildAggregateFrame:
    """The pandas-side groupby + lineage-stamping helper."""

    @pytest.fixture
    def src(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "placed_day": ["2026-04-01", "2026-04-01", "2026-04-02", "2026-04-02", "2026-04-01"],
                "product": ["widget", "widget", "gadget", "gadget", "gadget"],
                "qty": [3, 5, 2, 4, 1],
                "_lineage_row_id": ["s1", "s2", "s3", "s4", "s5"],
            }
        )

    def test_emits_one_row_per_group(self, src: pd.DataFrame) -> None:
        result, groups = _build_aggregate_frame(
            source_df=src,
            target="main.gold.sales",
            group_by=["placed_day", "product"],
            aggs={"units_sold": ("qty", "sum")},
        )
        assert len(result) == 3  # 3 distinct (placed_day, product) pairs
        assert len(groups) == 3

    def test_carries_lineage_column(self, src: pd.DataFrame) -> None:
        result, _ = _build_aggregate_frame(
            source_df=src,
            target="main.gold.sales",
            group_by=["placed_day", "product"],
            aggs={"units_sold": ("qty", "sum")},
        )
        assert "_lineage_row_id" in result.columns
        # All target IDs are 64-char hex digests (no empties from missing groups).
        assert all(isinstance(v, str) and len(v) == 64 for v in result["_lineage_row_id"])

    def test_fan_in_mapping(self, src: pd.DataFrame) -> None:
        _, groups = _build_aggregate_frame(
            source_df=src,
            target="main.gold.sales",
            group_by=["placed_day", "product"],
            aggs={"units_sold": ("qty", "sum")},
        )
        # ``(2026-04-01, widget)`` group has source rows s1 + s2.
        widget_group = next(
            (tid, sids) for tid, sids in groups if "s1" in sids
        )
        assert sorted(widget_group[1]) == ["s1", "s2"]
        # ``(2026-04-02, gadget)`` group has s3 + s4.
        gadget_group = next(
            (tid, sids) for tid, sids in groups if "s3" in sids
        )
        assert sorted(gadget_group[1]) == ["s3", "s4"]
        # ``(2026-04-01, gadget)`` is a singleton (s5 only).
        single_group = next(
            (tid, sids) for tid, sids in groups if sids == ["s5"]
        )
        assert single_group[1] == ["s5"]

    def test_aggregation_is_correct(self, src: pd.DataFrame) -> None:
        result, _ = _build_aggregate_frame(
            source_df=src,
            target="main.gold.sales",
            group_by=["placed_day", "product"],
            aggs={"units_sold": ("qty", "sum")},
        )
        widget_2026_04_01 = result[
            (result["placed_day"] == "2026-04-01") & (result["product"] == "widget")
        ]
        assert int(widget_2026_04_01["units_sold"].iloc[0]) == 8  # 3 + 5

    def test_rerun_produces_same_target_ids(self, src: pd.DataFrame) -> None:
        result1, _ = _build_aggregate_frame(
            source_df=src,
            target="main.gold.sales",
            group_by=["placed_day", "product"],
            aggs={"units_sold": ("qty", "sum")},
        )
        result2, _ = _build_aggregate_frame(
            source_df=src.copy(),
            target="main.gold.sales",
            group_by=["placed_day", "product"],
            aggs={"units_sold": ("qty", "sum")},
        )
        # Determinism: same input → same target IDs.
        ids1 = sorted(result1["_lineage_row_id"].tolist())
        ids2 = sorted(result2["_lineage_row_id"].tolist())
        assert ids1 == ids2

    def test_no_lineage_column_yields_empty_groups(self) -> None:
        src = pd.DataFrame({"k": ["a", "a", "b"], "v": [1, 2, 3]})
        result, groups = _build_aggregate_frame(
            source_df=src,
            target="main.gold.t",
            group_by=["k"],
            aggs={"sv": ("v", "sum")},
        )
        # Two groups, each with empty source-id list (no fan-in lineage).
        assert len(result) == 2
        assert all(sids == [] for _, sids in groups)


class TestAggregateTableValidation:
    """Argument validation that must surface as ``ValidationError``.

    These tests don't exercise the soyuz hop — they hit the
    pre-flight checks at the top of :func:`aggregate_table`.
    """

    def test_empty_group_by_rejected(self) -> None:
        from pointlessql.exceptions import ValidationError

        with pytest.raises(ValidationError, match="group_by"):
            aggregate_table(
                client=None,  # type: ignore[arg-type] — fail-fast checks come first
                engine=None,  # type: ignore[arg-type]
                source_df=pd.DataFrame({"k": [1]}),
                target="main.gold.t",
                group_by=[],
                aggs={"v": ("k", "sum")},
                source_table_fqn="main.silver.t",
                unreachable_msg="",
            )

    def test_missing_source_table_fqn_rejected(self) -> None:
        from pointlessql.exceptions import ValidationError

        with pytest.raises(ValidationError, match="source_table_fqn"):
            aggregate_table(
                client=None,  # type: ignore[arg-type]
                engine=None,  # type: ignore[arg-type]
                source_df=pd.DataFrame({"k": [1]}),
                target="main.gold.t",
                group_by=["k"],
                aggs={"v": ("k", "sum")},
                source_table_fqn="",
                unreachable_msg="",
            )

    def test_empty_aggs_rejected(self) -> None:
        from pointlessql.exceptions import ValidationError

        with pytest.raises(ValidationError, match="aggs"):
            aggregate_table(
                client=None,  # type: ignore[arg-type]
                engine=None,  # type: ignore[arg-type]
                source_df=pd.DataFrame({"k": [1]}),
                target="main.gold.t",
                group_by=["k"],
                aggs={},
                source_table_fqn="main.silver.t",
                unreachable_msg="",
            )

    def test_missing_group_by_column_rejected(self) -> None:
        from pointlessql.exceptions import ValidationError

        with pytest.raises(ValidationError, match="not present"):
            aggregate_table(
                client=None,  # type: ignore[arg-type]
                engine=None,  # type: ignore[arg-type]
                source_df=pd.DataFrame({"k": [1]}),
                target="main.gold.t",
                group_by=["does_not_exist"],
                aggs={"v": ("k", "sum")},
                source_table_fqn="main.silver.t",
                unreachable_msg="",
            )
