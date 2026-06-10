"""Soyuz Unity Catalog table lookups shared across the canvas pipeline.

The compiler-adjacent layers all need the same thing from soyuz: given a
table FQN, fetch its ``TableInfo`` and turn the HTTP edge cases (catalog
unreachable, table missing, no storage location) into the project's typed
errors.  The executor (base-table reads + target existence checks), the
per-node preview, and the route layer's schema seeding each used to carry
their own copy of that soyuz call plus error mapping; they share this
module instead.

Write-path concerns specific to materialisation — deriving a target
schema's storage root and creating the UC table row — stay in the
executor.  This module is read-only lookups.
"""

from __future__ import annotations

from typing import Literal, overload

import httpx
from soyuz_catalog_client import Client
from soyuz_catalog_client.api.tables import (
    get_table_api_2_1_unity_catalog_tables_full_name_get as _get_table,
)
from soyuz_catalog_client.errors import UnexpectedStatus
from soyuz_catalog_client.models.table_info import TableInfo
from soyuz_catalog_client.types import Unset

from pointlessql.exceptions import CatalogUnavailableError, ValidationError
from pointlessql.services.dp_canvas._types import ColumnSpec, PinSchema

_CATALOG_UNREACHABLE_MSG = (
    "soyuz-catalog could not be reached while resolving a canvas table "
    "reference.  Check that the catalog service is running and try again."
)


def fetch_table_info(client: Client, fqn: str) -> TableInfo | None:
    """Fetch the soyuz ``TableInfo`` for *fqn*.

    Centralises the one soyuz call every canvas table lookup makes, so
    the catalog-down and table-missing cases map to the same outcomes
    everywhere.

    Args:
        client: Configured soyuz client.
        fqn: Three-part table name.

    Returns:
        The ``TableInfo``, or ``None`` when the table is unknown to UC (a
        404 or a non-table response).

    Raises:
        CatalogUnavailableError: soyuz could not be reached.
        UnexpectedStatus: soyuz answered with a non-404 error
            response; re-raised untouched so the caller sees the
            real status code.
    """
    try:
        response = _get_table.sync(client=client, full_name=fqn)
    except httpx.ConnectError as exc:
        raise CatalogUnavailableError(_CATALOG_UNREACHABLE_MSG) from exc
    except UnexpectedStatus as exc:
        if exc.status_code == 404:
            return None
        raise
    if not isinstance(response, TableInfo):
        return None
    return response


@overload
def resolve_storage_location(client: Client, fqn: str, *, required: Literal[True]) -> str: ...


@overload
def resolve_storage_location(
    client: Client, fqn: str, *, required: Literal[False]
) -> str | None: ...


def resolve_storage_location(client: Client, fqn: str, *, required: bool) -> str | None:
    """Read the Delta storage location of *fqn* from UC.

    Propagates :class:`CatalogUnavailableError` raised by
    :func:`fetch_table_info` when soyuz could not be reached.

    Args:
        client: Configured soyuz client.
        fqn: Three-part table name.
        required: When True (the materialise path) a missing table or an
            empty storage location raises :class:`ValidationError`; when
            False (the preview path) those cases return ``None`` so the
            caller can fall back gracefully.

    Returns:
        The storage location, or ``None`` when ``required`` is False and
        the table is unknown or carries no location.

    Raises:
        ValidationError: ``required`` is True and the table is unknown or
            has no storage location.
    """
    info = fetch_table_info(client, fqn)
    if info is None:
        if required:
            raise ValidationError(f"Table {fqn!r} is not registered in UC.")
        return None
    location = info.storage_location
    if isinstance(location, Unset) or not location:
        if required:
            raise ValidationError(
                f"Table {fqn!r} has no storage_location in UC; cannot register as a view."
            )
        return None
    return location


def table_info_to_pin_schema(info: TableInfo) -> PinSchema:
    """Project a soyuz ``TableInfo`` onto the canvas's ``PinSchema``."""
    raw_columns = info.columns if not isinstance(info.columns, Unset) else None
    specs: list[ColumnSpec] = []
    for col in raw_columns or []:
        name = col.name if not isinstance(col.name, Unset) else None
        if not name:
            continue
        type_text = col.type_text if not isinstance(col.type_text, Unset) else None
        if not type_text:
            type_name = col.type_name if not isinstance(col.type_name, Unset) else None
            type_text = type_name or "VARCHAR"
        nullable_raw = col.nullable if not isinstance(col.nullable, Unset) else None
        nullable = True if nullable_raw is None else bool(nullable_raw)
        specs.append(ColumnSpec(name=str(name), duckdb_type=str(type_text), nullable=nullable))
    return PinSchema(kind="table", columns=specs, unknown=False)


def resolve_table_schema(client: Client, fqn: str) -> PinSchema | None:
    """Fetch *fqn* and project it to a ``PinSchema``; ``None`` on miss.

    Propagates :class:`CatalogUnavailableError` raised by
    :func:`fetch_table_info` when soyuz could not be reached.

    Args:
        client: Configured soyuz client.
        fqn: Three-part table name.

    Returns:
        The table's column layout as a ``PinSchema``, or ``None``
        when the table is unknown to UC.
    """
    info = fetch_table_info(client, fqn)
    if info is None:
        return None
    return table_info_to_pin_schema(info)


__all__ = [
    "fetch_table_info",
    "resolve_storage_location",
    "resolve_table_schema",
    "table_info_to_pin_schema",
]
