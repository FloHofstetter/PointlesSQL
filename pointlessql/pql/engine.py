"""Engine protocol and built-in implementations for PQL data I/O.

Each engine reads Delta data into its native frame type and writes
frames back to Delta storage.  The protocol is deliberately untyped
in its frame parameter (``Any``) so that ``PQL`` does not need to be
generic — the concrete engine implementations are strongly typed
internally.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    import duckdb
    import pandas as pd

WriteMode = Literal["error", "append", "overwrite", "ignore"]


@runtime_checkable
class Engine(Protocol):
    """Strategy for reading and writing Delta tables.

    Each engine reads Delta data into its native frame type and writes
    frames back to Delta storage.
    """

    def read(self, storage_location: str) -> Any:
        """Read a Delta table into the engine's native frame type.

        Args:
            storage_location: Filesystem path or URI of the Delta table.

        Returns:
            The table data in the engine's native representation.
        """
        ...

    def write(self, frame: Any, storage_location: str, mode: WriteMode) -> None:
        """Write a frame to a Delta table.

        Args:
            frame: Data in the engine's native frame type.
            storage_location: Filesystem path or URI of the Delta table.
            mode: Write mode (error, append, overwrite, ignore).
        """
        ...

    def columns_info(self, frame: Any) -> list[tuple[str, str, str, bool]]:
        """Extract column metadata from a frame for UC table registration.

        Args:
            frame: Data in the engine's native frame type.

        Returns:
            A list of ``(name, type_name, type_text, nullable)`` tuples,
            one per column, in positional order.
        """
        ...


# ------------------------------------------------------------------
# Pandas engine
# ------------------------------------------------------------------


class PandasEngine:
    """Engine that reads Delta tables as pandas DataFrames.

    This is the default engine, preserving backward compatibility
    with the pre-Sprint-11 behavior.
    """

    def read(self, storage_location: str) -> pd.DataFrame:
        """Read a Delta table as a pandas DataFrame.

        Args:
            storage_location: Filesystem path or URI of the Delta table.

        Returns:
            The table contents as a pandas DataFrame.
        """
        import deltalake

        dt = deltalake.DeltaTable(storage_location)
        return dt.to_pandas()

    def write(self, frame: pd.DataFrame, storage_location: str, mode: WriteMode) -> None:
        """Write a pandas DataFrame to a Delta table.

        Args:
            frame: The DataFrame to write.
            storage_location: Filesystem path or URI of the Delta table.
            mode: Write mode passed to ``deltalake.write_deltalake``.
        """
        import deltalake

        deltalake.write_deltalake(storage_location, frame, mode=mode)

    def columns_info(self, frame: pd.DataFrame) -> list[tuple[str, str, str, bool]]:
        """Extract column metadata from a pandas DataFrame.

        Args:
            frame: The source DataFrame.

        Returns:
            Column metadata tuples for UC registration.
        """
        from pointlessql.pql._columns import _resolve_dtype

        return [
            (str(col_name), *_resolve_dtype(dtype), True)
            for col_name, dtype in frame.dtypes.items()
        ]


# ------------------------------------------------------------------
# DuckDB engine
# ------------------------------------------------------------------

_DUCKDB_TYPE_MAP: dict[str, tuple[str, str]] = {
    "BIGINT": ("LONG", "long"),
    "INTEGER": ("INT", "int"),
    "SMALLINT": ("SHORT", "short"),
    "TINYINT": ("BYTE", "byte"),
    "DOUBLE": ("DOUBLE", "double"),
    "FLOAT": ("FLOAT", "float"),
    "VARCHAR": ("STRING", "string"),
    "BOOLEAN": ("BOOLEAN", "boolean"),
    "DATE": ("DATE", "date"),
    "TIMESTAMP": ("TIMESTAMP", "timestamp"),
    "TIMESTAMP WITH TIME ZONE": ("TIMESTAMP", "timestamp"),
    "BLOB": ("BINARY", "binary"),
    "HUGEINT": ("LONG", "long"),
}


def _duckdb_type_to_uc(duckdb_type: str) -> tuple[str, str]:
    """Map a DuckDB type string to UC ``(type_name, type_text)``.

    Args:
        duckdb_type: The DuckDB type as a string (e.g. ``"BIGINT"``).

    Returns:
        A tuple of UC type_name and type_text.
    """
    return _DUCKDB_TYPE_MAP.get(duckdb_type.upper(), ("STRING", "string"))


class DuckDBEngine:
    """Engine that reads Delta tables as DuckDB relations.

    Uses PyArrow as the bridge: Delta → PyArrow Dataset → DuckDB.
    Requires the ``duckdb`` package.
    """

    def __init__(self) -> None:
        """Initialize with an in-process DuckDB connection."""
        import duckdb

        self._conn = duckdb.connect()

    def read(self, storage_location: str) -> duckdb.DuckDBPyRelation:
        """Read a Delta table as a DuckDB relation.

        Args:
            storage_location: Filesystem path or URI of the Delta table.

        Returns:
            A DuckDB relation backed by the Delta table's Arrow data.
        """
        import deltalake

        dt = deltalake.DeltaTable(storage_location)
        arrow_dataset = dt.to_pyarrow_dataset()
        return self._conn.from_arrow(arrow_dataset)

    def write(
        self, frame: duckdb.DuckDBPyRelation, storage_location: str, mode: WriteMode
    ) -> None:
        """Write a DuckDB relation to a Delta table.

        Converts the relation to a PyArrow table first, then writes
        via ``deltalake.write_deltalake``.

        Args:
            frame: The DuckDB relation to write.
            storage_location: Filesystem path or URI of the Delta table.
            mode: Write mode passed to ``deltalake.write_deltalake``.
        """
        import deltalake

        arrow_table = frame.arrow()
        deltalake.write_deltalake(storage_location, arrow_table, mode=mode)

    def columns_info(
        self, frame: duckdb.DuckDBPyRelation
    ) -> list[tuple[str, str, str, bool]]:
        """Extract column metadata from a DuckDB relation.

        Args:
            frame: The source DuckDB relation.

        Returns:
            Column metadata tuples for UC registration.
        """
        return [
            (col_name, *_duckdb_type_to_uc(str(col_type)), True)
            for col_name, col_type in zip(frame.columns, frame.types)
        ]


# ------------------------------------------------------------------
# Engine factory
# ------------------------------------------------------------------

_ENGINE_REGISTRY: dict[str, type] = {
    "pandas": PandasEngine,
    "duckdb": DuckDBEngine,
}


def make_engine(name: str) -> Engine:
    """Create an engine instance by name.

    Args:
        name: Engine name (``"pandas"``, ``"duckdb"``).

    Returns:
        A configured engine instance.

    Raises:
        ValueError: If the engine name is not recognized.
    """
    cls = _ENGINE_REGISTRY.get(name.lower())
    if cls is None:
        valid = ", ".join(sorted(_ENGINE_REGISTRY))
        msg = f"Unknown engine {name!r}. Valid engines: {valid}"
        raise ValueError(msg)
    return cls()
