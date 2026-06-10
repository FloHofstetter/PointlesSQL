# pyright: reportUnusedFunction=false
"""Source-frame + target-location resolution + Arrow coercion."""

from __future__ import annotations

from typing import Any, cast

import httpx
import pyarrow as pa
from soyuz_catalog_client import Client
from soyuz_catalog_client.api.tables import (
    get_table_api_2_1_unity_catalog_tables_full_name_get as _get_table,
)
from soyuz_catalog_client.models.table_info import TableInfo
from soyuz_catalog_client.types import Unset

from pointlessql.exceptions import (
    CatalogNotFoundError,
    CatalogUnavailableError,
    ValidationError,
)
from pointlessql.pql._read import read_table
from pointlessql.pql._types import ArrowTable
from pointlessql.pql.engine import Engine


def _resolve_target_location(client: Client, full_name: str, unreachable_msg: str) -> str:
    """Look up *full_name* in soyuz-catalog and return its storage_location.

    Args:
        client: Configured catalog client.
        full_name: UC ``"catalog.schema.table"`` string.
        unreachable_msg: Pre-rendered "cannot reach catalog" message.

    Returns:
        The Delta table's storage location URI.

    Raises:
        CatalogNotFoundError: Target is unknown or has no location.
        CatalogUnavailableError: When soyuz-catalog is unreachable.
    """
    try:
        response = _get_table.sync(client=client, full_name=full_name)
    except httpx.ConnectError as exc:
        raise CatalogUnavailableError(unreachable_msg) from exc
    if not isinstance(response, TableInfo):
        raise CatalogNotFoundError(
            f"merge target {full_name!r} not found in soyuz-catalog "
            "(merge does not bootstrap tables — write or autoload first)"
        )
    location = response.storage_location
    if isinstance(location, Unset) or not location:
        raise CatalogNotFoundError(f"merge target {full_name!r} has no storage_location")
    return location


def _resolve_source_frame(client: Client, engine: Engine, source: Any, unreachable_msg: str) -> Any:
    """Return *source* as a frame, resolving UC references through the engine.

    Propagates :class:`CatalogNotFoundError` from :func:`read_table`
    when *source* is a UC reference that cannot be resolved, and
    :class:`CatalogUnavailableError` when soyuz-catalog is
    unreachable.

    Args:
        client: Configured catalog client (only used when *source* is a string).
        engine: Engine used to materialise UC references.
        source: Either a frame or a UC ``"catalog.schema.table"`` string.
        unreachable_msg: Pre-rendered "cannot reach catalog" message.

    Returns:
        The source frame in the engine's native type.
    """
    if isinstance(source, str):
        return read_table(
            client=client,
            engine=engine,
            full_name=source,
            unreachable_msg=unreachable_msg,
        )
    return source


def _frame_to_arrow(frame: Any) -> ArrowTable:
    """Coerce a frame into a PyArrow Table for ``DeltaTable.merge``.

    Accepts pandas DataFrames (the default engine output) and any
    object that already exposes an Arrow conversion via
    ``to_arrow`` (Polars / DuckDB relations).  PyArrow Tables pass
    through unchanged.

    Args:
        frame: Source frame in the engine's native type.

    Returns:
        A PyArrow Table backing the merge source side.

    Raises:
        ValidationError: When the frame cannot be converted.
    """
    if isinstance(frame, pa.Table):
        return cast(ArrowTable, frame)
    if hasattr(frame, "to_arrow"):
        return cast(ArrowTable, pa.Table.from_pandas(frame.to_arrow()))
    try:
        return cast(ArrowTable, pa.Table.from_pandas(frame))
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"merge source must be a pandas DataFrame, PyArrow Table, or "
            f"frame with .to_arrow(); got {type(frame).__name__}"
        ) from exc
