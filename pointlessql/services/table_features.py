"""Catalog-browser surfacing for Iceberg v3 / advanced table features.

Pure metadata classifiers over the table info soyuz-catalog already
returns — no engine work and no extra round-trip.  :func:`column_type_kind`
tags a column's type string as VARIANT or geospatial so the column list
can badge it, and :func:`table_feature_badges` reads the Delta / UniForm
table properties to surface the Iceberg-v3-era features (deletion
vectors, row tracking / row lineage, and UniForm Iceberg interop) as
table-level badges.

The matching is intentionally case-insensitive and tolerant: property
keys and type strings arrive in whatever case the upstream catalog
recorded, and a feature stays un-badged rather than mislabelled when a
property is absent.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

#: Semantic column-type kinds the column list badges.
KIND_VARIANT = "variant"
KIND_GEOSPATIAL = "geospatial"

_GEOSPATIAL_TOKENS = ("GEOGRAPHY", "GEOMETRY")

#: Per-format badge styling.  Delta and Iceberg are the first-class
#: managed table formats — each gets its own colour + icon so an Iceberg
#: table reads as a peer of Delta rather than an afterthought; the file
#: formats fall back to neutral styling.
_FORMAT_BADGES: dict[str, dict[str, Any]] = {
    "DELTA": {
        "label": "Delta",
        "css": "text-bg-info",
        "icon": "bi-triangle-half",
        "first_class": True,
    },
    "ICEBERG": {
        "label": "Iceberg",
        "css": "text-bg-primary",
        "icon": "bi-snow2",
        "first_class": True,
    },
    "PARQUET": {
        "label": "Parquet",
        "css": "text-bg-secondary",
        "icon": "bi-file-earmark",
        "first_class": False,
    },
    "CSV": {
        "label": "CSV",
        "css": "text-bg-warning text-dark",
        "icon": "bi-filetype-csv",
        "first_class": False,
    },
    "JSON": {
        "label": "JSON",
        "css": "text-bg-warning text-dark",
        "icon": "bi-filetype-json",
        "first_class": False,
    },
}

_FALLBACK_FORMAT_BADGE: dict[str, Any] = {
    "label": "—",
    "css": "text-bg-light text-dark",
    "icon": "",
    "first_class": False,
}


def format_badge(data_source_format: Any) -> dict[str, Any]:
    """Return a render-ready badge descriptor for a table's data format.

    Delta and Iceberg — the first-class managed formats — each resolve to
    a distinct colour + icon so the catalog browser presents an Iceberg
    table as a peer of Delta.  Known file formats get neutral styling; an
    unknown format passes its raw label through; an empty format yields a
    muted placeholder.

    Args:
        data_source_format: The UC ``data_source_format`` value (any
            case), or a falsy value.

    Returns:
        A dict with ``label`` / ``css`` (Bootstrap badge classes) /
        ``icon`` (a ``bi-*`` name or empty) / ``first_class`` (bool).
    """
    if not data_source_format:
        return dict(_FALLBACK_FORMAT_BADGE)
    key = str(data_source_format).strip().upper()
    preset = _FORMAT_BADGES.get(key)
    if preset is not None:
        return dict(preset)
    return {
        "label": str(data_source_format),
        "css": "text-bg-light text-dark border",
        "icon": "",
        "first_class": False,
    }


#: Table-feature badge metadata, keyed by the flag :func:`table_feature_flags`
#: returns.  Insertion order is the render order.
_FEATURE_BADGES: dict[str, dict[str, str]] = {
    "deletion_vectors": {
        "label": "Deletion vectors",
        "icon": "bi-eraser",
        "title": "Delta deletion vectors enabled — deletes mark rows without rewriting files",
    },
    "row_tracking": {
        "label": "Row tracking",
        "icon": "bi-upc-scan",
        "title": "Row tracking (row lineage) enabled — stable per-row ids survive rewrites",
    },
    "uniform_iceberg": {
        "label": "UniForm Iceberg",
        "icon": "bi-snow2",
        "title": "UniForm exposes this Delta table to Iceberg readers without a copy",
    },
}


def column_type_kind(type_text: str | None) -> str | None:
    """Classify a column's type string into a badge-worthy kind.

    Args:
        type_text: The column's ``type_text`` (e.g. ``"variant"`` or
            ``"geography"``), or ``None``.

    Returns:
        :data:`KIND_VARIANT` when the type carries a VARIANT, otherwise
        :data:`KIND_GEOSPATIAL` for a GEOMETRY / GEOGRAPHY type, else
        ``None`` for an ordinary type.
    """
    if not type_text:
        return None
    upper = type_text.upper()
    if "VARIANT" in upper:
        return KIND_VARIANT
    if any(token in upper for token in _GEOSPATIAL_TOKENS):
        return KIND_GEOSPATIAL
    return None


def _truthy(value: Any) -> bool:
    """Return whether a property value reads as enabled."""
    return str(value).strip().lower() in ("true", "1", "yes", "on")


def table_feature_flags(properties: Mapping[str, Any] | None) -> dict[str, bool]:
    """Derive the Iceberg-v3-era feature flags from table properties.

    Args:
        properties: The table's UC property map (case-insensitive keys),
            or ``None``.

    Returns:
        A dict with the boolean ``deletion_vectors`` / ``row_tracking`` /
        ``uniform_iceberg`` flags.
    """
    props = {str(key).lower(): value for key, value in (properties or {}).items()}
    enabled_formats = str(props.get("delta.universalformat.enabledformats", "")).lower()
    uniform_iceberg = "iceberg" in enabled_formats or any(
        _truthy(props.get(key))
        for key in ("delta.enableicebergcompatv2", "delta.enableicebergcompatv1")
    )
    return {
        "deletion_vectors": _truthy(props.get("delta.enabledeletionvectors")),
        "row_tracking": _truthy(props.get("delta.enablerowtracking")),
        "uniform_iceberg": uniform_iceberg,
    }


def table_feature_badges(properties: Mapping[str, Any] | None) -> list[dict[str, str]]:
    """Return the render-ready table-feature badges for *properties*.

    Args:
        properties: The table's UC property map, or ``None``.

    Returns:
        A list of ``{"key", "label", "icon", "title"}`` badge dicts in a
        stable order, holding only the features that are enabled.
    """
    flags = table_feature_flags(properties)
    return [{"key": key, **meta} for key, meta in _FEATURE_BADGES.items() if flags.get(key, False)]


def column_type_kinds(columns: list[Any] | None) -> dict[str, str]:
    """Map each advanced-typed column name to its badge kind.

    Args:
        columns: The table's column dicts (each with ``name`` +
            ``type_text``), or ``None``.  Non-dict entries are skipped
            so a malformed catalog payload cannot raise.

    Returns:
        ``{column_name: kind}`` covering only the VARIANT / geospatial
        columns; ordinary columns are omitted.
    """
    out: dict[str, str] = {}
    for entry in columns or []:
        if not isinstance(entry, dict):
            continue
        column = cast("dict[str, Any]", entry)
        name = column.get("name")
        kind = column_type_kind(column.get("type_text"))
        if name and kind:
            out[str(name)] = kind
    return out
