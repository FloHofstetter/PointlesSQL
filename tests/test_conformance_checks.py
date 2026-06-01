"""Unit tests for the Medallion-layer conformance checks.

Pure functions over a :class:`ConventionsConfig` — no DB. Cover the
schema-name layer inference and each layer's check (bronze required
audit columns, silver dedup-anchor hint, gold wide-table hint), plus
the None-layer / unknown-layer short-circuits.
"""

from __future__ import annotations

from pointlessql.conventions import ConventionsConfig, LayerConvention
from pointlessql.services.conformance._checks import (
    check_table_against_layer,
    infer_layer_from_full_name,
)

_CONV = ConventionsConfig(
    layers=[
        LayerConvention(
            name="bronze",
            description="raw",
            required_audit_columns=("_ingested_at", "_source_file"),
        ),
        LayerConvention(name="silver", description="cleaned"),
        LayerConvention(name="gold", description="curated"),
    ]
)


# --- layer inference ------------------------------------------------------


def test_infer_layer_matches_schema_name() -> None:
    assert infer_layer_from_full_name("main.bronze.orders", _CONV) == "bronze"
    assert infer_layer_from_full_name("main.silver.orders", _CONV) == "silver"
    assert infer_layer_from_full_name("main.gold.orders", _CONV) == "gold"


def test_infer_layer_unknown_schema_is_none() -> None:
    assert infer_layer_from_full_name("main.staging.orders", _CONV) is None


def test_infer_layer_non_three_part_is_none() -> None:
    assert infer_layer_from_full_name("main.bronze", _CONV) is None
    assert infer_layer_from_full_name("orders", _CONV) is None


# --- short-circuits -------------------------------------------------------


def test_none_layer_yields_no_findings() -> None:
    assert (
        check_table_against_layer(
            table_full_name="main.staging.x",
            layer=None,
            column_names=["a"],
            conventions=_CONV,
        )
        == []
    )


def test_unknown_layer_not_in_conventions_yields_no_findings() -> None:
    assert (
        check_table_against_layer(
            table_full_name="main.platinum.x",
            layer="platinum",
            column_names=["a"],
            conventions=_CONV,
        )
        == []
    )


# --- bronze ---------------------------------------------------------------


def test_bronze_missing_audit_columns_are_errors() -> None:
    findings = check_table_against_layer(
        table_full_name="main.bronze.orders",
        layer="bronze",
        column_names=["id", "_ingested_at"],  # missing _source_file
        conventions=_CONV,
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == "error"
    assert f.code == "bronze.missing_audit_column"
    assert "_source_file" in f.message


def test_bronze_with_all_audit_columns_conforms() -> None:
    findings = check_table_against_layer(
        table_full_name="main.bronze.orders",
        layer="bronze",
        column_names=["id", "_ingested_at", "_source_file"],
        conventions=_CONV,
    )
    assert findings == []


# --- silver ---------------------------------------------------------------


def test_silver_without_anchor_emits_info() -> None:
    findings = check_table_against_layer(
        table_full_name="main.silver.orders",
        layer="silver",
        column_names=["amount", "country"],
        conventions=_CONV,
    )
    assert len(findings) == 1
    assert findings[0].severity == "info"
    assert findings[0].code == "silver.no_dedup_anchor"


def test_silver_with_id_column_conforms() -> None:
    findings = check_table_against_layer(
        table_full_name="main.silver.orders",
        layer="silver",
        column_names=["order_id", "amount"],
        conventions=_CONV,
    )
    assert findings == []


def test_silver_with_scd2_columns_conforms() -> None:
    findings = check_table_against_layer(
        table_full_name="main.silver.orders",
        layer="silver",
        column_names=["amount", "_valid_from", "_valid_to", "_is_current"],
        conventions=_CONV,
    )
    assert findings == []


# --- gold -----------------------------------------------------------------


def test_gold_wide_table_emits_info() -> None:
    findings = check_table_against_layer(
        table_full_name="main.gold.fact",
        layer="gold",
        column_names=[f"c{i}" for i in range(51)],
        conventions=_CONV,
    )
    assert len(findings) == 1
    assert findings[0].code == "gold.wide_table"
    assert "51" in findings[0].message


def test_gold_narrow_table_conforms() -> None:
    findings = check_table_against_layer(
        table_full_name="main.gold.fact",
        layer="gold",
        column_names=[f"c{i}" for i in range(10)],
        conventions=_CONV,
    )
    assert findings == []
