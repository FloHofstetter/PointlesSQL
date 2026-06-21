"""Tests for the Iceberg-v3 / advanced-type catalog-browser classifiers."""

from __future__ import annotations

from pointlessql.services import table_features


def test_column_type_kind_variant_and_geospatial() -> None:
    assert table_features.column_type_kind("variant") == "variant"
    assert table_features.column_type_kind("VARIANT") == "variant"
    assert table_features.column_type_kind("struct<v:variant>") == "variant"
    assert table_features.column_type_kind("geography") == "geospatial"
    assert table_features.column_type_kind("GEOMETRY") == "geospatial"
    assert table_features.column_type_kind("geometrycollection") == "geospatial"


def test_column_type_kind_ordinary_and_empty() -> None:
    assert table_features.column_type_kind("string") is None
    assert table_features.column_type_kind("bigint") is None
    assert table_features.column_type_kind("") is None
    assert table_features.column_type_kind(None) is None


def test_feature_flags_detects_each_signal() -> None:
    flags = table_features.table_feature_flags(
        {
            "delta.enableDeletionVectors": "true",
            "delta.enableRowTracking": "TRUE",
            "delta.universalFormat.enabledFormats": "iceberg",
        }
    )
    assert flags == {
        "deletion_vectors": True,
        "row_tracking": True,
        "uniform_iceberg": True,
    }


def test_feature_flags_uniform_via_iceberg_compat() -> None:
    flags = table_features.table_feature_flags({"delta.enableIcebergCompatV2": "true"})
    assert flags["uniform_iceberg"] is True
    assert flags["deletion_vectors"] is False


def test_feature_flags_absent_and_falsey() -> None:
    assert table_features.table_feature_flags(None) == {
        "deletion_vectors": False,
        "row_tracking": False,
        "uniform_iceberg": False,
    }
    flags = table_features.table_feature_flags({"delta.enableDeletionVectors": "false"})
    assert flags["deletion_vectors"] is False


def test_feature_badges_only_enabled_in_order() -> None:
    badges = table_features.table_feature_badges(
        {
            "delta.enableRowTracking": "true",
            "delta.enableDeletionVectors": "true",
        }
    )
    keys = [b["key"] for b in badges]
    # Stable render order: deletion vectors before row tracking.
    assert keys == ["deletion_vectors", "row_tracking"]
    assert all({"key", "label", "icon", "title"} <= set(b) for b in badges)
    assert table_features.table_feature_badges({}) == []


def test_format_badge_delta_and_iceberg_are_first_class() -> None:
    delta = table_features.format_badge("DELTA")
    iceberg = table_features.format_badge("iceberg")
    assert delta["first_class"] is True
    assert delta["label"] == "Delta"
    assert iceberg["first_class"] is True
    assert iceberg["label"] == "Iceberg"
    # Iceberg is styled distinctly from Delta, not a neutral fallback.
    assert iceberg["css"] != delta["css"]
    assert iceberg["icon"]


def test_format_badge_file_formats_and_unknown() -> None:
    parquet = table_features.format_badge("PARQUET")
    assert parquet["first_class"] is False
    assert parquet["label"] == "Parquet"
    unknown = table_features.format_badge("orc")
    assert unknown["first_class"] is False
    assert unknown["label"] == "orc"


def test_format_badge_empty_is_placeholder() -> None:
    for empty in (None, ""):
        badge = table_features.format_badge(empty)
        assert badge["first_class"] is False
        assert badge["label"] == "—"


def test_column_type_kinds_maps_advanced_only() -> None:
    columns = [
        {"name": "id", "type_text": "bigint"},
        {"name": "payload", "type_text": "variant"},
        {"name": "loc", "type_text": "geography"},
        {"name": "broken"},
        "not-a-dict",
    ]
    assert table_features.column_type_kinds(columns) == {
        "payload": "variant",
        "loc": "geospatial",
    }
    assert table_features.column_type_kinds(None) == {}
