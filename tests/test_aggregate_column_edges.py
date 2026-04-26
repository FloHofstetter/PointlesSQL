"""Unit tests for the column-edge builder on ``pql.aggregate`` (Sprint 15.6.2).

The end-to-end aggregate path needs soyuz + deltalake; this file
covers only the pure-Python ``_build_aggregate_column_edges`` helper
that translates ``aggs`` + ``group_by`` + ``derivations`` into
:class:`ColumnEdgeSpec` lists.
"""

from __future__ import annotations

import pandas as pd

from pointlessql.pql._aggregate import _build_aggregate_column_edges


class TestAggregateColumnEdges:
    def test_group_by_emits_identity_edges(self) -> None:
        src = pd.DataFrame({"placed_day": ["d1"], "product": ["p1"], "qty": [1]})
        edges = _build_aggregate_column_edges(
            source_df=src,
            source_table_fqn="main.silver.t",
            target="main.gold.t",
            group_by=["placed_day", "product"],
            aggs={"units_sold": ("qty", "sum")},
            derivations=None,
        )
        kinds = {e.target_column: e.transform_kind for e in edges}
        assert kinds["placed_day"] == "identity"
        assert kinds["product"] == "identity"
        assert kinds["units_sold"] == "aggregate"

    def test_aggs_emit_aggregate_edges_with_fn_detail(self) -> None:
        src = pd.DataFrame({"day": ["d1"], "qty": [1]})
        edges = _build_aggregate_column_edges(
            source_df=src,
            source_table_fqn="main.silver.t",
            target="main.gold.t",
            group_by=["day"],
            aggs={"units_sold": ("qty", "sum"), "max_qty": ("qty", "max")},
            derivations=None,
        )
        agg = {e.target_column: e for e in edges if e.transform_kind == "aggregate"}
        assert agg["units_sold"].transform_detail == "sum"
        assert agg["max_qty"].transform_detail == "max"
        assert agg["units_sold"].source_column == "qty"

    def test_derivation_replaces_aggregate_with_derived_chain(self) -> None:
        # qty * unit_price -> line_revenue (derived) -> revenue (aggregate sum)
        src = pd.DataFrame(
            {
                "day": ["d1"],
                "qty": [1],
                "unit_price": [10.0],
                "line_revenue": [10.0],
            }
        )
        edges = _build_aggregate_column_edges(
            source_df=src,
            source_table_fqn="main.silver.t",
            target="main.gold.t",
            group_by=["day"],
            aggs={"revenue": ("line_revenue", "sum")},
            derivations={"line_revenue": ["qty", "unit_price"]},
        )
        revenue_edges = [e for e in edges if e.target_column == "revenue"]
        # Two edges (one per upstream column), both 'derived' kind.
        assert {e.source_column for e in revenue_edges} == {"qty", "unit_price"}
        assert {e.transform_kind for e in revenue_edges} == {"derived"}
        # Detail describes the chain.
        for e in revenue_edges:
            assert "via" in (e.transform_detail or "")
            assert "line_revenue" in (e.transform_detail or "")

    def test_group_by_derived_column(self) -> None:
        # placed_at -> placed_day (derived) used as group-by key
        src = pd.DataFrame(
            {
                "placed_at": [None],
                "placed_day": ["d1"],
                "qty": [1],
            }
        )
        edges = _build_aggregate_column_edges(
            source_df=src,
            source_table_fqn="main.silver.t",
            target="main.gold.t",
            group_by=["placed_day"],
            aggs={"units_sold": ("qty", "sum")},
            derivations={"placed_day": ["placed_at"]},
        )
        derived = [e for e in edges if e.target_column == "placed_day"]
        assert len(derived) == 1
        assert derived[0].transform_kind == "derived"
        assert derived[0].source_column == "placed_at"

    def test_lineage_row_id_synth_edge(self) -> None:
        src = pd.DataFrame({"day": ["d1"], "qty": [1], "_lineage_row_id": ["s1"]})
        edges = _build_aggregate_column_edges(
            source_df=src,
            source_table_fqn="main.silver.t",
            target="main.gold.t",
            group_by=["day"],
            aggs={"units_sold": ("qty", "sum")},
            derivations=None,
        )
        synth = [e for e in edges if e.target_column == "_lineage_row_id"]
        assert len(synth) == 1
        assert synth[0].transform_kind == "derived"
        assert synth[0].transform_detail == "synth_target_row_id"

    def test_no_lineage_column_means_no_synth_edge(self) -> None:
        src = pd.DataFrame({"day": ["d1"], "qty": [1]})
        edges = _build_aggregate_column_edges(
            source_df=src,
            source_table_fqn="main.silver.t",
            target="main.gold.t",
            group_by=["day"],
            aggs={"units_sold": ("qty", "sum")},
            derivations=None,
        )
        assert all(e.target_column != "_lineage_row_id" for e in edges)
