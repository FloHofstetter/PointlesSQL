"""Shared engine-side types.

Two unrelated groups live here:

* :class:`SQLResult` — the JSON-encodable result the public
  :meth:`PQL.sql` returns.  Lives here so the SQL execution path
  can re-import it without dragging the full :class:`PQL` class
  import graph along.
* The ``Arrow*`` / ``Duckdb*`` / ``Delta*`` :class:`typing.Protocol`
  classes — Phase 79.1 typing shims for the third-party return
  values the engine touches (pyarrow / duckdb / deltalake all ship
  without ``py.typed`` markers, so every chained access surfaces
  as ``Unknown`` to pyright).  The Protocols describe the *subset*
  PointlesSQL actually uses; cast at the duckdb/pyarrow boundary
  (e.g. ``cast(ArrowTable, cursor.fetch_arrow_table())``) and every
  downstream operation inherits a typed shape.  Runtime objects
  stay unchanged — these Protocols only narrow pyright's view.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class SQLResult:
    """The outcome of a :meth:`PQL.sql` execution.

    All fields are JSON-encodable so the route handler can serialise
    the result straight into a ``JSONResponse`` body.

    Attributes:
        columns: One dict per output column with ``name`` and
            stringified DuckDB ``type``.
        rows: The result rows as a list of lists (column order matches
            :attr:`columns`).
        row_count: Length of :attr:`rows` after any row-cap slicing.
        truncated: ``True`` iff the underlying query produced more
            rows than ``max_rows`` and the excess was dropped.
        duration_ms: Wall-clock execution time on the DuckDB engine.
        executed_sql: The SQL string the caller supplied (unchanged).
        rewritten_sql: What was actually sent to DuckDB after the
            3-part → single-quoted-identifier rewrite.
        referenced_tables: The list of UC ``catalog.schema.table``
            references extracted from the parsed SQL.
    """

    columns: list[dict[str, str]]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    duration_ms: int
    executed_sql: str
    rewritten_sql: str
    referenced_tables: list[str]


class ArrowField(Protocol):
    """One column entry inside an :class:`ArrowSchema`.

    PointlesSQL reads three attributes off these — name, type, and
    nullable flag.  PyArrow's runtime ``DataType`` is opaque; we
    treat ``type`` as ``Any`` because the codebase only ``str()``s
    or string-compares against it.
    """

    name: str
    nullable: bool
    type: Any


class ArrowSchema(Protocol):
    """Subset of ``pyarrow.Schema`` the PQL engine touches."""

    @property
    def names(self) -> list[str]: ...

    def __iter__(self) -> Iterator[ArrowField]: ...

    def get_field_index(self, name: str) -> int: ...


class ArrowArray(Protocol):
    """Placeholder for ``pyarrow.Array`` — opaque payload type.

    PQL never inspects array contents through this Protocol; it
    only hands arrays to ``append_column`` / ``set_column`` (and
    reads back via ``to_pylist`` for the lineage-row-id path).
    """

    def to_pylist(self) -> list[Any]: ...


class ArrowTable(Protocol):
    """Subset of ``pyarrow.Table`` the PQL engine touches.

    Everything the autoload / merge / write paths do with a Table
    reduces to: how many rows? what are the column names? add a
    new column.  This Protocol covers that; downstream
    pandas/arrow interop (``to_pandas``) stays typed as ``Any``.
    """

    @property
    def num_rows(self) -> int: ...

    @property
    def schema(self) -> ArrowSchema: ...

    def append_column(
        self, field_or_name: str, column: ArrowArray
    ) -> ArrowTable: ...

    def column(self, name: str) -> ArrowArray: ...

    def set_column(
        self, index: int, field_or_name: str, column: ArrowArray
    ) -> ArrowTable: ...

    def to_pandas(self) -> Any: ...


class DuckdbCursor(Protocol):
    """Subset of a ``duckdb.DuckDBPyConnection.execute`` result.

    Only the arrow-table accessor we use at the autoload boundary
    is typed here; other duckdb features stay on the raw object.
    """

    def fetch_arrow_table(self) -> ArrowTable: ...


class DeltaField(Protocol):
    """One column entry inside a ``deltalake.Schema``."""

    name: str


class DeltaSchema(Protocol):
    """Subset of ``deltalake.Schema`` returned by ``DeltaTable.schema()``."""

    @property
    def fields(self) -> list[DeltaField]: ...
