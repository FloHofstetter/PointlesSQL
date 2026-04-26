"""Pure-function unit tests for ``infer_column_edges`` (Sprint 15.6.2).

No DB, no soyuz — the helper takes column lists in and returns
:class:`ColumnEdgeSpec` lists out.  These tests pin down the
identity / derived / audit / unknown_origin classification rules
documented in the helper's module docstring.
"""

from __future__ import annotations

from pointlessql.services.column_lineage_diff import infer_column_edges


class TestIdentityVsUnknownOrigin:
    def test_identity_when_source_present(self) -> None:
        edges = infer_column_edges(
            source_columns=["a", "b", "c"],
            target_columns=["a", "b", "c"],
            source_table="main.bronze.t",
            target_table="main.silver.t",
        )
        assert len(edges) == 3
        assert {e.transform_kind for e in edges} == {"identity"}
        assert all(e.source_table == "main.bronze.t" for e in edges)
        assert [(e.source_column, e.target_column) for e in edges] == [
            ("a", "a"),
            ("b", "b"),
            ("c", "c"),
        ]

    def test_target_only_without_derivation_is_unknown_origin(self) -> None:
        edges = infer_column_edges(
            source_columns=["a"],
            target_columns=["a", "b"],
            source_table="main.bronze.t",
            target_table="main.silver.t",
        )
        kinds = {e.target_column: e.transform_kind for e in edges}
        assert kinds == {"a": "identity", "b": "unknown_origin"}
        b_edge = next(e for e in edges if e.target_column == "b")
        assert b_edge.source_table is None
        assert b_edge.source_column is None

    def test_no_source_table_collapses_identity_to_unknown(self) -> None:
        # ``pql.write_table`` without source_table_fqn — the schema
        # diff still runs but every edge becomes unknown_origin.
        edges = infer_column_edges(
            source_columns=["a", "b"],
            target_columns=["a", "b"],
            source_table=None,
            target_table="main.silver.t",
        )
        assert {e.transform_kind for e in edges} == {"unknown_origin"}
        assert all(e.source_table is None for e in edges)


class TestDerivations:
    def test_single_derivation(self) -> None:
        edges = infer_column_edges(
            source_columns=["placed_at"],
            target_columns=["placed_day"],
            source_table="main.silver.t",
            target_table="main.gold.t",
            derivations={"placed_day": ["placed_at"]},
        )
        assert len(edges) == 1
        assert edges[0].transform_kind == "derived"
        assert edges[0].source_column == "placed_at"

    def test_multi_source_derivation(self) -> None:
        edges = infer_column_edges(
            source_columns=["qty", "unit_price"],
            target_columns=["line_revenue"],
            source_table="main.silver.t",
            target_table="main.gold.t",
            derivations={"line_revenue": ["qty", "unit_price"]},
        )
        assert len(edges) == 2
        assert {e.source_column for e in edges} == {"qty", "unit_price"}
        assert {e.transform_kind for e in edges} == {"derived"}

    def test_derivation_referencing_missing_source(self) -> None:
        edges = infer_column_edges(
            source_columns=["qty"],
            target_columns=["foo"],
            source_table="main.silver.t",
            target_table="main.gold.t",
            derivations={"foo": ["nope"]},
        )
        assert len(edges) == 1
        assert edges[0].transform_kind == "unknown_origin"
        assert edges[0].source_table is None
        assert edges[0].transform_detail is not None
        assert "nope" in edges[0].transform_detail


class TestAuditColumns:
    def test_audit_columns_marked_unknown_origin_with_detail(self) -> None:
        edges = infer_column_edges(
            source_columns=["qty"],
            target_columns=["qty", "_ingested_at", "_source_file"],
            source_table="file://volume",
            target_table="main.bronze.t",
            audit_columns={"_ingested_at", "_source_file"},
        )
        kinds = {e.target_column: (e.transform_kind, e.transform_detail) for e in edges}
        assert kinds["qty"] == ("identity", None)
        assert kinds["_ingested_at"] == ("unknown_origin", "audit")
        assert kinds["_source_file"] == ("unknown_origin", "audit")


class TestEdgeCases:
    def test_empty_target_yields_empty(self) -> None:
        assert infer_column_edges(
            source_columns=["a"],
            target_columns=[],
            source_table="main.x.t",
            target_table="main.y.u",
        ) == []

    def test_source_only_columns_are_skipped(self) -> None:
        # ``b`` exists on source but not target — must NOT appear in
        # the output (no "dropped" edges in v1).
        edges = infer_column_edges(
            source_columns=["a", "b"],
            target_columns=["a"],
            source_table="main.bronze.t",
            target_table="main.silver.t",
        )
        assert [e.target_column for e in edges] == ["a"]
        assert all(e.target_column != "b" for e in edges)

    def test_none_source_columns_treated_as_empty(self) -> None:
        edges = infer_column_edges(
            source_columns=None,
            target_columns=["a"],
            source_table="main.bronze.t",
            target_table="main.silver.t",
        )
        assert len(edges) == 1
        assert edges[0].transform_kind == "unknown_origin"
