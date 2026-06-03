"""Per-block behaviour tests for the dp_canvas registry."""

from __future__ import annotations

from pointlessql.services.dp_canvas._blocks import (
    BLOCK_REGISTRY,
    compile_block,
    infer_block,
)
from pointlessql.services.dp_canvas._types import ColumnSpec, PinSchema


def _seed_schema(*cols: tuple[str, str]) -> PinSchema:
    return PinSchema(
        kind="table",
        columns=[ColumnSpec(name=n, duckdb_type=t, nullable=True) for n, t in cols],
    )


class TestInputPort:
    def test_compile_emits_unquoted_three_part(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="InputPort",
            node_id="n1",
            inputs={},
            output_schema=_seed_schema(("id", "BIGINT")),
            cfg={"table_fqn": "main.sales.orders"},
            errors=errors,
        )
        assert out is not None
        assert "SELECT * FROM main.sales.orders" == out.sql
        assert errors == []

    def test_compile_rejects_bad_fqn(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="InputPort",
            node_id="n1",
            inputs={},
            output_schema=_seed_schema(),
            cfg={"table_fqn": "only.two"},
            errors=errors,
        )
        assert out is None
        assert errors and errors[0].kind == "bad_config"


class TestFilter:
    def test_compile_emits_where(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="Filter",
            node_id="f1",
            inputs={"in": "upstream_cte"},
            output_schema=_seed_schema(("a", "BIGINT")),
            cfg={"predicate": "a > 0"},
            errors=errors,
        )
        assert out is not None
        assert out.sql == "SELECT * FROM upstream_cte WHERE a > 0"


class TestProject:
    def test_infer_subsets_columns(self) -> None:
        errors: list = []
        inferred = infer_block(
            block_type="Project",
            node_id="p1",
            input_schemas={"in": _seed_schema(("a", "BIGINT"), ("b", "VARCHAR"))},
            cfg={"columns": ["a"]},
            errors=errors,
        )
        assert [c.name for c in inferred.columns] == ["a"]
        assert errors == []

    def test_infer_flags_unknown_column(self) -> None:
        errors: list = []
        infer_block(
            block_type="Project",
            node_id="p1",
            input_schemas={"in": _seed_schema(("a", "BIGINT"))},
            cfg={"columns": ["missing"]},
            errors=errors,
        )
        assert any(e.kind == "type_mismatch" for e in errors)


class TestJoin:
    def test_compile_with_keys(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="Join",
            node_id="j1",
            inputs={"left": "left_cte", "right": "right_cte"},
            output_schema=_seed_schema(),
            cfg={"keys": ["id"], "how": "left"},
            errors=errors,
        )
        assert out is not None
        assert "LEFT JOIN" in out.sql
        assert 'USING ("id")' in out.sql

    def test_compile_rejects_bad_how(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="Join",
            node_id="j1",
            inputs={"left": "l", "right": "r"},
            output_schema=_seed_schema(),
            cfg={"keys": ["k"], "how": "weird"},
            errors=errors,
        )
        assert out is None
        assert any("how" in e.message for e in errors)


class TestGroupBy:
    def test_compile_emits_aggregates(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="GroupBy",
            node_id="g1",
            inputs={"in": "src"},
            output_schema=_seed_schema(),
            cfg={
                "keys": ["country"],
                "aggregations": [
                    {"column": "amount", "fn": "sum", "alias": "total"},
                    {"column": None, "fn": "count", "alias": "n"},
                ],
            },
            errors=errors,
        )
        assert out is not None
        assert 'SUM("amount") AS "total"' in out.sql
        assert 'COUNT(*) AS "n"' in out.sql
        assert 'GROUP BY "country"' in out.sql


class TestLimit:
    def test_compile_emits_limit(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="Limit",
            node_id="l1",
            inputs={"in": "src"},
            output_schema=_seed_schema(),
            cfg={"n": 100},
            errors=errors,
        )
        assert out is not None
        assert out.sql.endswith("LIMIT 100")

    def test_compile_rejects_negative(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="Limit",
            node_id="l1",
            inputs={"in": "src"},
            output_schema=_seed_schema(),
            cfg={"n": -1},
            errors=errors,
        )
        assert out is None
        assert errors[0].kind == "bad_config"


class TestSQL:
    def test_placeholder_substitution(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="SQL",
            node_id="s1",
            inputs={"in": "n0_inputport"},
            output_schema=_seed_schema(),
            cfg={"query": "SELECT * FROM {{in}} WHERE 1=1"},
            errors=errors,
        )
        assert out is not None
        assert "n0_inputport" in out.sql
        assert "{{in}}" not in out.sql


class TestOutputPort:
    def test_compile_validates_target_fqn(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="OutputPort",
            node_id="o1",
            inputs={"in": "src"},
            output_schema=_seed_schema(),
            cfg={
                "port_name": "p",
                "materialized_table": "not_three_part",
                "mode": "overwrite",
            },
            errors=errors,
        )
        assert out is None
        assert any("three-part" in e.message for e in errors)

    def test_merge_mode_requires_keys(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="OutputPort",
            node_id="o1",
            inputs={"in": "src"},
            output_schema=_seed_schema(),
            cfg={
                "port_name": "p",
                "materialized_table": "cat.sch.tbl",
                "mode": "merge",
            },
            errors=errors,
        )
        assert out is None
        assert any("merge_on" in e.message for e in errors)


class TestDataProduct:
    def test_compile_emits_select_from_resolved_fqn(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="DataProduct",
            node_id="dp1",
            inputs={},
            output_schema=_seed_schema(("id", "BIGINT")),
            cfg={
                "dp_id": 7,
                "port_name": "primary",
                "materialized_table": "main.gold.orders_summary",
            },
            errors=errors,
        )
        assert out is not None
        assert out.sql == "SELECT * FROM main.gold.orders_summary"
        assert errors == []

    def test_compile_rejects_missing_resolved_fqn(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="DataProduct",
            node_id="dp1",
            inputs={},
            output_schema=_seed_schema(),
            cfg={"dp_id": 7, "port_name": "primary"},
            errors=errors,
        )
        assert out is None
        assert errors and errors[0].kind == "bad_config"

    def test_infer_uses_seed_when_provided(self) -> None:
        errors: list = []
        seed = _seed_schema(("id", "BIGINT"), ("name", "VARCHAR"))
        inferred = infer_block(
            block_type="DataProduct",
            node_id="dp1",
            input_schemas={},
            cfg={
                "dp_id": 7,
                "port_name": "primary",
                "materialized_table": "main.gold.orders_summary",
            },
            errors=errors,
            seed=seed,
        )
        assert inferred == seed
        assert errors == []


class TestWindow:
    def test_compile_row_number(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="Window",
            node_id="w1",
            inputs={"in": "upstream"},
            output_schema=_seed_schema(),
            cfg={
                "function": "row_number",
                "target_alias": "rn",
                "partition_by": ["country"],
                "order_by": ["ts"],
            },
            errors=errors,
        )
        assert out is not None
        assert "ROW_NUMBER()" in out.sql
        assert "PARTITION BY" in out.sql
        assert 'AS "rn"' in out.sql

    def test_compile_rejects_unknown_fn(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="Window",
            node_id="w1",
            inputs={"in": "u"},
            output_schema=_seed_schema(),
            cfg={"function": "wat", "target_alias": "x"},
            errors=errors,
        )
        assert out is None
        assert errors and errors[0].kind == "bad_config"


class TestPivotUnpivot:
    def test_compile_pivot(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="Pivot",
            node_id="p1",
            inputs={"in": "u"},
            output_schema=_seed_schema(),
            cfg={"on_column": "month", "value_column": "amt", "aggregate": "sum"},
            errors=errors,
        )
        assert out is not None
        assert "PIVOT u" in out.sql
        assert 'ON "month"' in out.sql

    def test_compile_unpivot(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="Unpivot",
            node_id="u1",
            inputs={"in": "u"},
            output_schema=_seed_schema(),
            cfg={"value_columns": ["jan", "feb"], "name_label": "m", "value_label": "v"},
            errors=errors,
        )
        assert out is not None
        assert "UNPIVOT u" in out.sql
        assert '"jan", "feb"' in out.sql


class TestUnion:
    def test_compile_union_all(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="Union",
            node_id="u1",
            inputs={"left": "a", "right": "b"},
            output_schema=_seed_schema(),
            cfg={"all": True},
            errors=errors,
        )
        assert out is not None
        assert "UNION ALL" in out.sql

    def test_infer_schema_mismatch_emits_error(self) -> None:
        from pointlessql.services.dp_canvas._blocks import infer_block

        errors: list = []
        left = _seed_schema(("a", "BIGINT"))
        right = _seed_schema(("b", "BIGINT"))
        inferred = infer_block(
            block_type="Union",
            node_id="u1",
            input_schemas={"left": left, "right": right},
            cfg={},
            errors=errors,
        )
        assert inferred.unknown is True
        assert any(e.kind == "type_mismatch" for e in errors)


class TestSortSampleDistinct:
    def test_compile_distinct_all(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="Distinct",
            node_id="d1",
            inputs={"in": "u"},
            output_schema=_seed_schema(),
            cfg={},
            errors=errors,
        )
        assert out is not None
        assert "SELECT DISTINCT *" in out.sql

    def test_compile_sort(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="Sort",
            node_id="s1",
            inputs={"in": "u"},
            output_schema=_seed_schema(),
            cfg={"order_by": ["a", {"column": "b", "direction": "desc"}]},
            errors=errors,
        )
        assert out is not None
        assert 'ORDER BY "a" ASC, "b" DESC' in out.sql

    def test_compile_sample_percent(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="Sample",
            node_id="sm1",
            inputs={"in": "u"},
            output_schema=_seed_schema(),
            cfg={"kind": "percent", "value": 10},
            errors=errors,
        )
        assert out is not None
        assert "USING SAMPLE 10.0 PERCENT" in out.sql


class TestCastRenameCalc:
    def test_compile_cast(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="Cast",
            node_id="c1",
            inputs={"in": "u"},
            output_schema=_seed_schema(),
            cfg={"casts": [{"column": "amt", "target_type": "INTEGER"}]},
            errors=errors,
        )
        assert out is not None
        assert '"amt"::INTEGER AS "amt"' in out.sql

    def test_compile_rename(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="Rename",
            node_id="r1",
            inputs={"in": "u"},
            output_schema=_seed_schema(),
            cfg={"renames": {"a": "alpha"}},
            errors=errors,
        )
        assert out is not None
        assert '"a" AS "alpha"' in out.sql

    def test_compile_calc_column(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="CalcColumn",
            node_id="cc1",
            inputs={"in": "u"},
            output_schema=_seed_schema(),
            cfg={"expression": "amt * 1.1", "target_alias": "amt_x"},
            errors=errors,
        )
        assert out is not None
        assert '(amt * 1.1) AS "amt_x"' in out.sql


class TestSemiAntiJoin:
    def test_semi_join_compiles_exists(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="SemiJoin",
            node_id="s1",
            inputs={"left": "l", "right": "r"},
            output_schema=_seed_schema(),
            cfg={"keys": ["id", "region"]},
            errors=errors,
        )
        assert out is not None and errors == []
        assert out.sql == (
            'SELECT l.* FROM l l WHERE EXISTS '
            '(SELECT 1 FROM r r WHERE l."id" = r."id" AND l."region" = r."region")'
        )

    def test_anti_join_compiles_not_exists(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="AntiJoin",
            node_id="a1",
            inputs={"left": "l", "right": "r"},
            output_schema=_seed_schema(),
            cfg={"keys": ["id"]},
            errors=errors,
        )
        assert out is not None
        assert "WHERE NOT EXISTS" in out.sql

    def test_semi_join_missing_input(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="SemiJoin",
            node_id="s1",
            inputs={"left": "l"},
            output_schema=_seed_schema(),
            cfg={"keys": ["id"]},
            errors=errors,
        )
        assert out is None
        assert any(e.kind == "missing_input" and e.pin == "right" for e in errors)

    def test_semi_join_requires_keys(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="SemiJoin",
            node_id="s1",
            inputs={"left": "l", "right": "r"},
            output_schema=_seed_schema(),
            cfg={"keys": []},
            errors=errors,
        )
        assert out is None
        assert any("keys is required" in e.message for e in errors)

    def test_semi_join_infer_returns_left_and_flags_missing_key(self) -> None:
        errors: list = []
        inferred = infer_block(
            block_type="SemiJoin",
            node_id="s1",
            input_schemas={
                "left": _seed_schema(("id", "BIGINT"), ("name", "VARCHAR")),
                "right": _seed_schema(("other", "BIGINT")),
            },
            cfg={"keys": ["id"]},
            errors=errors,
        )
        assert [c.name for c in inferred.columns] == ["id", "name"]
        assert any(e.kind == "type_mismatch" and e.pin == "right" for e in errors)


def test_registry_has_full_block_set() -> None:
    assert set(BLOCK_REGISTRY) == {
        "InputPort",
        "DataProduct",
        "FileInput",
        "Filter",
        "Project",
        "Join",
        "SemiJoin",
        "AntiJoin",
        "GroupBy",
        "Limit",
        "SQL",
        "Window",
        "Pivot",
        "Unpivot",
        "Union",
        "Except",
        "Intersect",
        "Distinct",
        "Sort",
        "Sample",
        "Cast",
        "Rename",
        "CalcColumn",
        "Unnest",
        "OutputPort",
        "FileOutput",
    }


class TestFileBlocks:
    def test_file_input_emits_sentinel_and_reader(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="FileInput",
            node_id="fi",
            inputs={},
            output_schema=_seed_schema(),
            cfg={"path": "bronze/events.csv", "format": "csv"},
            errors=errors,
        )
        assert out is not None and errors == []
        assert out.sql == "SELECT * FROM read_csv_auto('@@CANVAS_FILE:bronze/events.csv@@')"

    def test_file_input_auto_format_picks_reader_by_extension(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="FileInput",
            node_id="fi",
            inputs={},
            output_schema=_seed_schema(),
            cfg={"path": "a/b.parquet", "format": "auto"},
            errors=errors,
        )
        assert "read_parquet(" in out.sql

    def test_file_input_infer_is_unknown_at_edit_time(self) -> None:
        errors: list = []
        inferred = infer_block(
            block_type="FileInput",
            node_id="fi",
            input_schemas={},
            cfg={"path": "ok/file.csv", "format": "csv"},
            errors=errors,
        )
        assert inferred.unknown and errors == []

    def test_file_output_passthrough_and_missing_input(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="FileOutput",
            node_id="fo",
            inputs={"in": "src"},
            output_schema=_seed_schema(),
            cfg={"path": "exports/o.parquet", "format": "parquet"},
            errors=errors,
        )
        assert out is not None and out.sql == "SELECT * FROM src"

        errors2: list = []
        missing = compile_block(
            block_type="FileOutput",
            node_id="fo",
            inputs={},
            output_schema=_seed_schema(),
            cfg={"path": "exports/o.parquet"},
            errors=errors2,
        )
        assert missing is None
        assert any(e.kind == "missing_input" and e.pin == "in" for e in errors2)

    def test_file_output_rejects_bad_format(self) -> None:
        errors: list = []
        out = compile_block(
            block_type="FileOutput",
            node_id="fo",
            inputs={"in": "src"},
            output_schema=_seed_schema(),
            cfg={"path": "exports/o.txt", "format": "txt"},
            errors=errors,
        )
        assert out is None
        assert any("FileOutput.format" in e.message for e in errors)

    def test_safe_relative_path_rejects_traversal_and_injection(self) -> None:
        from pointlessql.services.dp_canvas._blocks._files import _safe_relative_path

        for bad in [
            "/etc/passwd",
            "../../etc/passwd",
            "a/../../x",
            "a/./b",
            "a//b",
            "x'y.csv",
            "a b.csv",
            "a\\b.csv",
            "",
            ".",
            "..",
        ]:
            errs: list = []
            assert _safe_relative_path("n", bad, errs) is None, bad
            assert errs and errs[0].column == "path"
        for ok in ["bronze/events.csv", "a.parquet", "sub/dir/f-1_2.json"]:
            errs2: list = []
            assert _safe_relative_path("n", ok, errs2) == ok
            assert errs2 == []
