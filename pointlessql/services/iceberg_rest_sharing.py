"""Iceberg REST connection hints for OpenSharing recipients.

OpenSharing exposes a shared Unity-Catalog dataset to any Iceberg-REST-
catalog-compatible engine (Trino, Spark, Snowflake, Flink, PyIceberg).
Once soyuz-catalog serves the Iceberg REST catalog endpoint, a recipient
points their engine at it with the share as the warehouse.  This module
is the client-facing half: given the catalog URI + share name (+ the
recipient's bearer token), it renders ready-to-paste connection config
for each engine so an operator can hand a recipient exactly what to set.

Pure string assembly — no catalog round-trip; the live REST serving is
soyuz-catalog's job.
"""

from __future__ import annotations

_TOKEN_PLACEHOLDER = "<your-recipient-token>"


def iceberg_rest_connection_hints(
    *,
    catalog_uri: str,
    share: str,
    token: str | None = None,
) -> list[dict[str, str]]:
    """Build per-engine Iceberg REST connection snippets for a share.

    Args:
        catalog_uri: The Iceberg REST catalog root the share is served
            from (e.g. ``https://host/iceberg/v1``).
        share: The share name, used as the Iceberg ``warehouse``.
        token: The recipient's bearer token; a placeholder is rendered
            when omitted so the snippet is still copy-shaped.

    Returns:
        One ``{"engine", "title", "language", "snippet"}`` dict per
        supported client, in a stable order.
    """
    tok = token or _TOKEN_PLACEHOLDER
    return [
        {
            "engine": "trino",
            "title": "Trino — catalog properties",
            "language": "properties",
            "snippet": (
                "connector.name=iceberg\n"
                "iceberg.catalog.type=rest\n"
                f"iceberg.rest-catalog.uri={catalog_uri}\n"
                f"iceberg.rest-catalog.warehouse={share}\n"
                "iceberg.rest-catalog.security=OAUTH2\n"
                f"iceberg.rest-catalog.oauth2.token={tok}"
            ),
        },
        {
            "engine": "spark",
            "title": "Apache Spark — session config",
            "language": "bash",
            "snippet": (
                "spark-sql \\\n"
                "  --conf spark.sql.catalog.share=org.apache.iceberg.spark.SparkCatalog \\\n"
                "  --conf spark.sql.catalog.share.type=rest \\\n"
                f"  --conf spark.sql.catalog.share.uri={catalog_uri} \\\n"
                f"  --conf spark.sql.catalog.share.warehouse={share} \\\n"
                f"  --conf spark.sql.catalog.share.token={tok}"
            ),
        },
        {
            "engine": "pyiceberg",
            "title": "PyIceberg — load_catalog",
            "language": "python",
            "snippet": (
                "from pyiceberg.catalog import load_catalog\n\n"
                "catalog = load_catalog(\n"
                '    "share",\n'
                "    **{\n"
                '        "type": "rest",\n'
                f'        "uri": "{catalog_uri}",\n'
                f'        "warehouse": "{share}",\n'
                f'        "token": "{tok}",\n'
                "    },\n"
                ")"
            ),
        },
        {
            "engine": "flink",
            "title": "Apache Flink — catalog DDL",
            "language": "sql",
            "snippet": (
                "CREATE CATALOG share WITH (\n"
                "  'type' = 'iceberg',\n"
                "  'catalog-type' = 'rest',\n"
                f"  'uri' = '{catalog_uri}',\n"
                f"  'warehouse' = '{share}',\n"
                f"  'token' = '{tok}'\n"
                ");"
            ),
        },
        {
            "engine": "snowflake",
            "title": "Snowflake — catalog integration",
            "language": "sql",
            "snippet": (
                "CREATE CATALOG INTEGRATION share_int\n"
                "  CATALOG_SOURCE = ICEBERG_REST\n"
                f"  REST_CONFIG = (CATALOG_URI = '{catalog_uri}', WAREHOUSE = '{share}')\n"
                f"  REST_AUTHENTICATION = (TYPE = BEARER, BEARER_TOKEN = '{tok}')\n"
                "  ENABLED = TRUE;"
            ),
        },
    ]
