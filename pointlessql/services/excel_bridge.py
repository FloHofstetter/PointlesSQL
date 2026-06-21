"""Excel add-in bridge — OData feed shaping + Office.js manifest.

The Excel add-in pulls governed lakehouse data and Unity-Catalog metric
views into a worksheet without a per-user ODBC driver.  The data side
already exists (grant-enforced SELECT reads, the metric-view query path,
and the PQL write-back path); this module supplies the thin client
adapter — the OData-v4 JSON envelope Excel's "From OData Feed" consumes,
plus the Office.js add-in manifest XML that points Excel at this server.

Pure string / dict assembly — no catalog round-trip and no engine work.
"""

from __future__ import annotations

from typing import Any, cast
from xml.sax.saxutils import escape, quoteattr


def _col_name(col: Any) -> str:
    """Return a column's display name, tolerating dict or string shapes."""
    if isinstance(col, dict):
        column = cast("dict[str, Any]", col)
        return str(column.get("name") or column.get("column") or "")
    return str(col)


def to_odata_feed(
    entity: str,
    columns: list[Any],
    rows: list[list[Any]],
    *,
    context: str | None = None,
) -> dict[str, Any]:
    """Shape a tabular result into an OData-v4 feed envelope for Excel.

    Args:
        entity: The entity-set name (e.g. the table or metric-view name)
            Excel labels the query with.
        columns: The result columns (names, dict-or-string shaped).
        rows: The result rows, each a list aligned to *columns*.
        context: Optional ``@odata.context`` value; defaults to
            ``$metadata#<entity>``.

    Returns:
        ``{"@odata.context", "value": [{col: val, ...}, ...]}`` — the
        JSON shape Excel's OData connector reads.
    """
    names = [_col_name(col) for col in columns]
    value = [dict(zip(names, row, strict=False)) for row in rows]
    return {
        "@odata.context": context or f"$metadata#{entity}",
        "value": value,
    }


def odata_service_document(base_url: str, entity_sets: list[str]) -> dict[str, Any]:
    """Build the OData service document listing the available feeds.

    Args:
        base_url: The bridge's OData root URL.
        entity_sets: Names of the entity sets (metric views / tables)
            the add-in may pull.

    Returns:
        ``{"@odata.context", "value": [{"name", "kind", "url"}, ...]}``.
    """
    root = base_url.rstrip("/")
    return {
        "@odata.context": f"{root}/$metadata",
        "value": [
            {"name": name, "kind": "EntitySet", "url": f"{root}/{name}"} for name in entity_sets
        ],
    }


def office_manifest(
    *,
    base_url: str,
    add_in_id: str = "8f2c0a1e-3b4d-4c5e-9a6f-1b2c3d4e5f60",
    display_name: str = "PointlesSQL",
    description: str = "Pull governed lakehouse data and metric views into Excel.",
) -> str:
    """Render the Office.js task-pane add-in manifest XML.

    Args:
        base_url: HTTPS base URL Excel loads the add-in assets from.
        add_in_id: Stable GUID identifying the add-in.
        display_name: Add-in name shown in Excel.
        description: Add-in description.

    Returns:
        A well-formed Office Add-in manifest XML string.
    """
    root = escape(base_url.rstrip("/"))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<OfficeApp xmlns="http://schemas.microsoft.com/office/appforoffice/1.1" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns:bt="http://schemas.microsoft.com/office/officeappbasictypes/1.0" '
        'xsi:type="TaskPaneApp">\n'
        f"  <Id>{escape(add_in_id)}</Id>\n"
        "  <Version>1.0.0.0</Version>\n"
        "  <ProviderName>PointlesSQL</ProviderName>\n"
        "  <DefaultLocale>en-US</DefaultLocale>\n"
        f"  <DisplayName DefaultValue={quoteattr(display_name)} />\n"
        f"  <Description DefaultValue={quoteattr(description)} />\n"
        f'  <IconUrl DefaultValue="{root}/static/img/excel-icon-32.png" />\n'
        "  <Hosts>\n"
        '    <Host Name="Workbook" />\n'
        "  </Hosts>\n"
        "  <DefaultSettings>\n"
        f'    <SourceLocation DefaultValue="{root}/excel/taskpane.html" />\n'
        "  </DefaultSettings>\n"
        "  <Permissions>ReadWriteDocument</Permissions>\n"
        "</OfficeApp>\n"
    )
