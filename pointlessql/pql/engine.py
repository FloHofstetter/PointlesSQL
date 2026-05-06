"""Engine protocol and built-in implementations for PQL data I/O.

Each engine reads Delta data into its native frame type and writes
frames back to Delta storage.  The protocol is deliberately untyped
in its frame parameter (``Any``) so that ``PQL`` does not need to be
generic — the concrete engine implementations are strongly typed
internally.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

import deltalake

if TYPE_CHECKING:
    import duckdb
    import pandas as pd
    import polars as pl

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

    This is the default engine.
    """

    def read(self, storage_location: str) -> pd.DataFrame:
        """Read a Delta table as a pandas DataFrame.

        Args:
            storage_location: Filesystem path or URI of the Delta table.

        Returns:
            The table contents as a pandas DataFrame.
        """
        dt = deltalake.DeltaTable(storage_location)
        return dt.to_pandas()

    def write(self, frame: pd.DataFrame, storage_location: str, mode: WriteMode) -> None:
        """Write a pandas DataFrame to a Delta table.

        ``mode="overwrite"`` is interpreted strictly: the new frame
        replaces the prior table contents *and* its schema.  Without
        ``schema_mode="overwrite"`` deltalake refuses any column-set
        change with ``SchemaMismatchError("Cannot cast schema, number
        of fields does not match")``, which breaks the common pattern
        of an agent rebuilding a silver table with a slightly
        different projection.  Append-mode keeps the merge-with-
        existing semantics; the schema must still match on append,
        that's the point of append.

        Args:
            frame: The DataFrame to write.
            storage_location: Filesystem path or URI of the Delta table.
            mode: Write mode passed to ``deltalake.write_deltalake``.
        """
        if mode == "overwrite":
            deltalake.write_deltalake(storage_location, frame, mode=mode, schema_mode="overwrite")
        else:
            deltalake.write_deltalake(storage_location, frame, mode=mode)

    def columns_info(self, frame: pd.DataFrame) -> list[tuple[str, str, str, bool]]:
        """Extract column metadata from a pandas DataFrame.

        Args:
            frame: The source DataFrame.

        Returns:
            Column metadata tuples for UC registration.
        """
        from pointlessql.pql._columns import _resolve_dtype  # pyright: ignore[reportPrivateUsage]

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


def register_delta_view(
    conn: duckdb.DuckDBPyConnection,
    full_name: str,
    storage_location: str,
) -> None:
    """Register a Delta table as a DuckDB view named after its UC path.

    Reuses the :class:`DuckDBEngine` bridge (Delta → PyArrow Dataset →
    DuckDB).  The view is created at the dotted catalog name so the
    user's verbatim SQL (``SELECT * FROM main.sales.orders``) binds
    to this registration without rewriting.  We use ``register`` with
    the 3-part name verbatim so the view is scoped to the connection
    and disappears when the connection closes.

    Args:
        conn: A live DuckDB connection.
        full_name: The UC ``catalog.schema.table`` three-part name,
            used verbatim as the view identifier.
        storage_location: Filesystem path or URI of the Delta table.
    """
    dt = deltalake.DeltaTable(storage_location)
    arrow_dataset = dt.to_pyarrow_dataset()
    conn.register(full_name, arrow_dataset)


class DuckDBEngine:
    """Engine that reads Delta tables as DuckDB relations.

    Uses PyArrow as the bridge: Delta → PyArrow Dataset → DuckDB.
    Requires the ``duckdb`` package.  Creates an in-process DuckDB
    connection on instantiation.
    """

    def __init__(self) -> None:
        import duckdb

        self._conn = duckdb.connect()

    def read(self, storage_location: str) -> duckdb.DuckDBPyRelation:
        """Read a Delta table as a DuckDB relation.

        Args:
            storage_location: Filesystem path or URI of the Delta table.

        Returns:
            A DuckDB relation backed by the Delta table's Arrow data.
        """
        dt = deltalake.DeltaTable(storage_location)
        arrow_dataset = dt.to_pyarrow_dataset()
        return self._conn.from_arrow(arrow_dataset)

    def write(self, frame: duckdb.DuckDBPyRelation, storage_location: str, mode: WriteMode) -> None:
        """Write a DuckDB relation to a Delta table.

        Converts the relation to a PyArrow table first, then writes
        via ``deltalake.write_deltalake``.

        Args:
            frame: The DuckDB relation to write.
            storage_location: Filesystem path or URI of the Delta table.
            mode: Write mode passed to ``deltalake.write_deltalake``.
        """
        arrow_table = frame.arrow()
        if mode == "overwrite":
            deltalake.write_deltalake(
                storage_location, arrow_table, mode=mode, schema_mode="overwrite"
            )
        else:
            deltalake.write_deltalake(storage_location, arrow_table, mode=mode)

    def columns_info(self, frame: duckdb.DuckDBPyRelation) -> list[tuple[str, str, str, bool]]:
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
# Polars engine
# ------------------------------------------------------------------

_POLARS_TYPE_MAP: dict[str, tuple[str, str]] = {
    "Int8": ("BYTE", "byte"),
    "Int16": ("SHORT", "short"),
    "Int32": ("INT", "int"),
    "Int64": ("LONG", "long"),
    "UInt8": ("SHORT", "short"),
    "UInt16": ("INT", "int"),
    "UInt32": ("LONG", "long"),
    "UInt64": ("LONG", "long"),
    "Float32": ("FLOAT", "float"),
    "Float64": ("DOUBLE", "double"),
    "Boolean": ("BOOLEAN", "boolean"),
    "String": ("STRING", "string"),
    "Utf8": ("STRING", "string"),
    "Date": ("DATE", "date"),
    "Datetime": ("TIMESTAMP", "timestamp"),
    "Binary": ("BINARY", "binary"),
    "LargeString": ("STRING", "string"),
}


def _polars_type_to_uc(polars_type: str) -> tuple[str, str]:
    """Map a Polars dtype string to UC ``(type_name, type_text)``.

    Args:
        polars_type: The Polars dtype base name (e.g. ``"Int64"``).

    Returns:
        A tuple of UC type_name and type_text.
    """
    return _POLARS_TYPE_MAP.get(polars_type, ("STRING", "string"))


class PolarsEngine:
    """Engine that reads Delta tables as Polars DataFrames.

    Uses PyArrow as the bridge: Delta → PyArrow Table → Polars.
    Requires the ``polars`` package.
    """

    def read(self, storage_location: str) -> pl.DataFrame:
        """Read a Delta table as a Polars DataFrame.

        Args:
            storage_location: Filesystem path or URI of the Delta table.

        Returns:
            The table contents as a Polars DataFrame.
        """
        import polars as pl

        dt = deltalake.DeltaTable(storage_location)
        result = pl.from_arrow(dt.to_pyarrow_table())
        assert isinstance(result, pl.DataFrame)  # noqa: S101 — pyarrow Table always yields DataFrame
        return result

    def write(self, frame: pl.DataFrame, storage_location: str, mode: WriteMode) -> None:
        """Write a Polars DataFrame to a Delta table.

        Converts the frame to a PyArrow table first, then writes
        via ``deltalake.write_deltalake``.

        Args:
            frame: The Polars DataFrame to write.
            storage_location: Filesystem path or URI of the Delta table.
            mode: Write mode passed to ``deltalake.write_deltalake``.
        """
        if mode == "overwrite":
            deltalake.write_deltalake(
                storage_location, frame.to_arrow(), mode=mode, schema_mode="overwrite"
            )
        else:
            deltalake.write_deltalake(storage_location, frame.to_arrow(), mode=mode)

    def columns_info(self, frame: pl.DataFrame) -> list[tuple[str, str, str, bool]]:
        """Extract column metadata from a Polars DataFrame.

        Args:
            frame: The source Polars DataFrame.

        Returns:
            Column metadata tuples for UC registration.
        """
        return [
            (name, *_polars_type_to_uc(str(dtype.base_type())), True)
            for name, dtype in zip(frame.columns, frame.dtypes)
        ]


# ------------------------------------------------------------------
# Engine factory
# ------------------------------------------------------------------

_ENGINE_REGISTRY: dict[str, type] = {
    "pandas": PandasEngine,
    "duckdb": DuckDBEngine,
    "polars": PolarsEngine,
}


def make_engine(name: str) -> Engine:
    """Create an engine instance by name.

    Args:
        name: Engine name (``"pandas"``, ``"duckdb"``, ``"polars"``).

    Returns:
        A configured engine instance.

    Raises:
        ValidationError: If the engine name is not recognized.
    """
    from pointlessql.exceptions import ValidationError

    cls = _ENGINE_REGISTRY.get(name.lower())
    if cls is None:
        valid = ", ".join(sorted(_ENGINE_REGISTRY))
        msg = f"Unknown engine {name!r}. Valid engines: {valid}"
        raise ValidationError(msg)
    return cls()
