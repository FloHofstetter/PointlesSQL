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


def test_registry_has_nine_atom_blocks() -> None:
    assert set(BLOCK_REGISTRY) == {
        "InputPort",
        "DataProduct",
        "Filter",
        "Project",
        "Join",
        "GroupBy",
        "Limit",
        "SQL",
        "OutputPort",
    }
