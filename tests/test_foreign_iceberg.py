"""Tests for the Iceberg foreign-catalog connector presets."""

from __future__ import annotations

from pointlessql.services import foreign_iceberg


def test_connector_types_cover_the_known_sources() -> None:
    keys = {entry["key"] for entry in foreign_iceberg.iceberg_connector_types()}
    assert keys == {
        "glue",
        "snowflake_horizon",
        "hive_metastore",
        "salesforce_data_cloud",
        "google_cloud_lakehouse",
        "palantir",
    }


def test_each_preset_is_render_ready() -> None:
    for entry in foreign_iceberg.iceberg_connector_types():
        assert {"key", "label", "hint", "options"} <= set(entry)
        assert entry["label"]
        assert isinstance(entry["options"], dict)
        # Every Iceberg source declares a catalog-type so the form is
        # never blank.
        assert entry["options"].get("catalog-type")


def test_helper_returns_isolated_copies() -> None:
    first = foreign_iceberg.iceberg_connector_types()
    first[0]["options"]["warehouse"] = "mutated"
    second = foreign_iceberg.iceberg_connector_types()
    assert second[0]["options"].get("warehouse") != "mutated"
