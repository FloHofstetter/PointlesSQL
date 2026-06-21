"""Iceberg foreign-catalog connector presets for the federation UI.

Unity Catalog can register and govern Apache Iceberg tables from
external catalogs (AWS Glue, Snowflake Horizon, Hive Metastore,
Salesforce Data Cloud, Google Cloud Lakehouse, Palantir) without moving
the data.  This module is the static catalog of those Iceberg source
types the "New Foreign Catalog" flow offers, each with the option keys
that source expects pre-filled so an admin starts from a shaped form
instead of a blank key/value grid.

Pure data plus a render helper — the actual foreign-catalog creation
still flows through the generated client's ``POST /api/catalogs`` path.
"""

from __future__ import annotations

from typing import Any

#: The Iceberg source presets, in display order.  ``options`` holds the
#: option keys the source expects, pre-seeded with sensible defaults (or
#: an empty string for values the admin must supply).
ICEBERG_CONNECTOR_TYPES: tuple[dict[str, Any], ...] = (
    {
        "key": "glue",
        "label": "AWS Glue",
        "hint": "Iceberg tables catalogued in the AWS Glue Data Catalog.",
        "options": {"catalog-type": "glue", "warehouse": "", "region": ""},
    },
    {
        "key": "snowflake_horizon",
        "label": "Snowflake Horizon",
        "hint": "Iceberg REST endpoint exposed by Snowflake Horizon.",
        "options": {"catalog-type": "rest", "uri": "", "warehouse": ""},
    },
    {
        "key": "hive_metastore",
        "label": "Hive Metastore",
        "hint": "Iceberg tables tracked by a Hive Metastore (thrift URI).",
        "options": {"catalog-type": "hive", "uri": "thrift://", "warehouse": ""},
    },
    {
        "key": "salesforce_data_cloud",
        "label": "Salesforce Data Cloud",
        "hint": "Iceberg REST catalog vended by Salesforce Data Cloud.",
        "options": {"catalog-type": "rest", "uri": "", "warehouse": ""},
    },
    {
        "key": "google_cloud_lakehouse",
        "label": "Google Cloud Lakehouse",
        "hint": "Iceberg REST catalog from Google Cloud's lakehouse.",
        "options": {"catalog-type": "rest", "uri": "", "warehouse": ""},
    },
    {
        "key": "palantir",
        "label": "Palantir",
        "hint": "Iceberg REST catalog exposed by Palantir Foundry.",
        "options": {"catalog-type": "rest", "uri": "", "warehouse": ""},
    },
)


def iceberg_connector_types() -> list[dict[str, Any]]:
    """Return the Iceberg connector presets as a render-ready list.

    Each entry is deep-copied at the one level that matters (the
    ``options`` dict) so a caller — or the JSON serializer — cannot
    mutate the module-level constant.

    Returns:
        A list of ``{"key", "label", "hint", "options"}`` dicts in
        display order.
    """
    return [dict(entry, options=dict(entry["options"])) for entry in ICEBERG_CONNECTOR_TYPES]
