"""Connector gallery — the point-and-click source catalog for ingest.

The ingest plane has a handful of *working* connector kinds (the ones
:data:`pointlessql.models.ingest.INGEST_SOURCE_KINDS` lists, backed by a
DuckDB reader in :mod:`pointlessql.services.ingest.connectors`).  This
module wraps them — plus the SaaS / database connectors Lakeflow Connect
has announced but PointlesSQL cannot yet read natively — in a categorised
gallery with labels, icons, and an ``available`` / ``coming_soon``
status, so the "new source" page presents a browsable catalog instead of
a flat radio list.

Pure metadata: the ``available`` entries are derived from
``INGEST_SOURCE_KINDS`` so the gallery can never drift out of sync with
the kinds that actually have a reader; the ``coming_soon`` entries are
informational placeholders for the announced connectors.
"""

from __future__ import annotations

from typing import Any

from pointlessql.models.ingest import INGEST_SOURCE_KINDS

#: Per-kind presentation metadata for the working connectors.
_AVAILABLE_META: dict[str, tuple[str, str, str, str]] = {
    "file_upload": (
        "File upload",
        "file",
        "bi-file-earmark-arrow-up",
        "Upload a CSV, Parquet, or JSON file.",
    ),
    "parquet_glob": ("Parquet glob", "file", "bi-files", "Read a glob of Parquet files."),
    "s3": ("Amazon S3", "cloud", "bi-cloud", "Read files from an S3 bucket."),
    "http": ("HTTP / URL", "cloud", "bi-link-45deg", "Read a file from an HTTP(S) URL."),
    "postgres": ("PostgreSQL", "database", "bi-database", "Pull tables from a Postgres database."),
    "mysql": ("MySQL", "database", "bi-database", "Pull tables from a MySQL database."),
    "sqlite": ("SQLite", "database", "bi-database-fill", "Read tables from a SQLite file."),
}

#: Announced connectors with no native reader yet — shown but not
#: pickable.  Each carries a ``maturity`` (``ga`` / ``beta``) mirroring
#: the Lakeflow Connect rollout status.  Tuple shape:
#: ``(kind, label, category, icon, maturity, description)``.
_COMING_SOON: tuple[tuple[str, str, str, str, str, str], ...] = (
    ("sql_server", "SQL Server", "database", "bi-database", "beta", "Microsoft SQL Server."),
    ("salesforce", "Salesforce", "saas", "bi-cloud-haze2", "beta", "Salesforce objects."),
    ("workday", "Workday", "saas", "bi-people", "beta", "Workday reports + HCM data."),
    ("servicenow", "ServiceNow", "saas", "bi-headset", "beta", "ServiceNow tables."),
    ("google_analytics", "Google Analytics", "saas", "bi-graph-up", "beta", "GA reports."),
    ("netsuite", "NetSuite", "saas", "bi-receipt", "beta", "NetSuite records."),
    ("monday", "Monday.com", "saas", "bi-kanban", "beta", "Monday.com work management."),
    ("slack", "Slack", "saas", "bi-slack", "beta", "Slack message + channel logs."),
    ("zoom", "Zoom", "saas", "bi-camera-video", "beta", "Zoom meeting logs."),
    ("pendo", "Pendo", "saas", "bi-graph-up-arrow", "beta", "Pendo product analytics."),
    ("zoho_books", "Zoho Books", "saas", "bi-journal-text", "beta", "Zoho Books accounting."),
    ("rabbitmq", "RabbitMQ", "streaming", "bi-broadcast", "beta", "RabbitMQ streaming ingest."),
    ("jira", "Jira", "knowledge", "bi-kanban-fill", "beta", "Jira issues + projects."),
    ("github", "GitHub", "knowledge", "bi-github", "beta", "GitHub repos + issues."),
    ("confluence", "Confluence", "knowledge", "bi-file-richtext", "ga", "Confluence pages."),
    ("sharepoint", "SharePoint", "knowledge", "bi-folder-symlink", "beta", "SharePoint files."),
    ("google_drive", "Google Drive", "knowledge", "bi-google", "beta", "Google Drive files."),
    ("outlook", "Outlook", "knowledge", "bi-envelope", "beta", "Outlook mail + calendar."),
)

#: Category display order + labels.
_CATEGORY_ORDER: tuple[tuple[str, str], ...] = (
    ("file", "Files"),
    ("database", "Databases"),
    ("cloud", "Cloud storage"),
    ("streaming", "Streaming"),
    ("saas", "SaaS apps"),
    ("knowledge", "Enterprise knowledge"),
)

_FALLBACK_META = ("", "file", "bi-plug", "")


def connector_gallery() -> list[dict[str, Any]]:
    """Return the full connector catalog as flat entries.

    Returns:
        One ``{"kind", "label", "category", "icon", "status",
        "maturity", "description"}`` dict per connector — the working
        kinds first (``status="available"``), then the announced ones
        (``status="coming_soon"`` with a ``maturity`` of ``ga`` /
        ``beta``).  The available set is derived from
        :data:`INGEST_SOURCE_KINDS`, so it cannot drift from the kinds
        that have a reader.
    """
    entries: list[dict[str, Any]] = []
    for kind in INGEST_SOURCE_KINDS:
        label, category, icon, description = _AVAILABLE_META.get(
            kind, (kind.replace("_", " ").title(), *_FALLBACK_META[1:])
        )
        entries.append(
            {
                "kind": kind,
                "label": label,
                "category": category,
                "icon": icon,
                "status": "available",
                "maturity": "available",
                "description": description,
            }
        )
    for kind, label, category, icon, maturity, description in _COMING_SOON:
        entries.append(
            {
                "kind": kind,
                "label": label,
                "category": category,
                "icon": icon,
                "status": "coming_soon",
                "maturity": maturity,
                "description": description,
            }
        )
    return entries


def gallery_groups() -> list[dict[str, Any]]:
    """Return the connector catalog grouped by category, in display order.

    Returns:
        One ``{"category", "label", "connectors": [...]}`` group per
        non-empty category, ordered files → databases → cloud →
        streaming → SaaS → enterprise knowledge.
    """
    entries = connector_gallery()
    groups: list[dict[str, Any]] = []
    for category, label in _CATEGORY_ORDER:
        items = [entry for entry in entries if entry["category"] == category]
        if items:
            groups.append({"category": category, "label": label, "connectors": items})
    return groups
