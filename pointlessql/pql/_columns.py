"""Map pandas DataFrame columns to Unity Catalog ColumnInfo objects."""

from __future__ import annotations

import json

import pandas as pd
from soyuz_catalog_client.models.column_info import ColumnInfo

# pandas dtype kind → (UC type_name, UC type_text)
# https://numpy.org/doc/stable/reference/generated/numpy.dtype.kind.html
_DTYPE_MAP: dict[str, tuple[str, str]] = {
    "i": ("LONG", "long"),  # signed integer — refined below by itemsize
    "u": ("LONG", "long"),  # unsigned integer
    "f": ("DOUBLE", "double"),  # float — refined below by itemsize
    "b": ("BOOLEAN", "boolean"),
    "M": ("TIMESTAMP", "timestamp"),
    "U": ("STRING", "string"),
    "S": ("BINARY", "binary"),
    "O": ("STRING", "string"),  # object (typically strings)
}

_INT_BY_SIZE: dict[int, tuple[str, str]] = {
    1: ("BYTE", "byte"),
    2: ("SHORT", "short"),
    4: ("INT", "int"),
    8: ("LONG", "long"),
}

_FLOAT_BY_SIZE: dict[int, tuple[str, str]] = {
    4: ("FLOAT", "float"),
    8: ("DOUBLE", "double"),
}


def _resolve_dtype(dtype: object) -> tuple[str, str]:
    """Return ``(type_name, type_text)`` for a single pandas dtype."""
    # Handle pandas nullable extension dtypes (Int8, Int16, …, Float32, …)
    if hasattr(dtype, "numpy_dtype"):
        dtype = dtype.numpy_dtype  # type: ignore[union-attr]

    # Handle string[python] / string[pyarrow] → STRING
    if isinstance(dtype, pd.StringDtype):
        return ("STRING", "string")
    if isinstance(dtype, pd.BooleanDtype):
        return ("BOOLEAN", "boolean")

    kind = getattr(dtype, "kind", None)
    if kind is None:
        return ("STRING", "string")

    if kind in ("i", "u"):
        itemsize = getattr(dtype, "itemsize", 8)
        return _INT_BY_SIZE.get(itemsize, ("LONG", "long"))
    if kind == "f":
        itemsize = getattr(dtype, "itemsize", 8)
        return _FLOAT_BY_SIZE.get(itemsize, ("DOUBLE", "double"))

    return _DTYPE_MAP.get(kind, ("STRING", "string"))


def columns_from_tuples(
    columns: list[tuple[str, str, str, bool]],
) -> list[ColumnInfo]:
    """Build ``ColumnInfo`` objects from engine-provided column metadata.

    Args:
        columns: List of ``(name, type_name, type_text, nullable)`` tuples
            as returned by ``Engine.columns_info()``.

    Returns:
        A list of ``ColumnInfo`` objects ready for a ``CreateTable`` request.
    """
    result: list[ColumnInfo] = []
    for position, (col_name, type_name, type_text, nullable) in enumerate(columns):
        type_json = json.dumps(
            {"name": col_name, "type": type_text, "nullable": nullable, "metadata": {}}
        )
        result.append(
            ColumnInfo(
                name=col_name,
                type_name=type_name,
                type_text=type_text,
                type_json=type_json,
                nullable=nullable,
                position=position,
            )
        )
    return result


def columns_from_dataframe(df: pd.DataFrame) -> list[ColumnInfo]:
    """Derive Unity Catalog ``ColumnInfo`` list from a DataFrame's schema.

    Args:
        df: The source DataFrame.

    Returns:
        A list of ``ColumnInfo`` objects ready for a ``CreateTable`` request.
    """
    tuples = [
        (str(col_name), *_resolve_dtype(dtype), True) for col_name, dtype in df.dtypes.items()
    ]
    return columns_from_tuples(tuples)
