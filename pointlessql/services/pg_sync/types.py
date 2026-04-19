"""Shared dataclasses + Postgres → UC type mapping.

Sprint 82 split out of the monolithic ``pg_sync.py``.  Hosts the data
shapes consumed by both halves of the sync pipeline (``snapshot``
introspection produces them; ``diff`` consumes them) so neither side
imports the other's module.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)


# Postgres → Unity Catalog primitive type mapping.
#
# Keys are the ``data_type`` column from ``information_schema.columns``,
# already normalised to lowercase. Values are the UC type names as used
# in ``ColumnInfo.type_name`` and ``type_text`` (see
# ``soyuz-catalog/DIVERGENCES.md`` for the divergence from upstream UC
# which also accepts ``"INT"`` as an alias for ``"INTEGER"``).
#
# Anything not in this table falls through to STRING with a warning
# log so the sync does not hard-fail on an exotic Postgres type. Keep
# this dict exported so tests can parametrise every row at once.
PG_TO_UC_TYPE: dict[str, str] = {
    "smallint": "SHORT",
    "integer": "INT",
    "bigint": "LONG",
    "real": "FLOAT",
    "double precision": "DOUBLE",
    "numeric": "DECIMAL",
    "decimal": "DECIMAL",
    "text": "STRING",
    "character varying": "STRING",
    "varchar": "STRING",
    "character": "STRING",
    "char": "STRING",
    "boolean": "BOOLEAN",
    "date": "DATE",
    "timestamp without time zone": "TIMESTAMP_NTZ",
    "timestamp with time zone": "TIMESTAMP",
    "timestamp": "TIMESTAMP",
    "bytea": "BINARY",
}


# Data-source-format value we emit for foreign-catalog tables.
#
# The UC OpenAPI ``DataSourceFormat`` enum (see
# ``unitycatalog/api/all.yaml``) only lists physical file formats —
# DELTA, CSV, JSON, AVRO, PARQUET, ORC, TEXT — it has no ``UNKNOWN`` or
# ``FOREIGN`` value. soyuz-catalog's Pydantic model relaxes the enum
# to ``str = Field(min_length=1)``, so we can pass a non-spec token
# without triggering a 422. We choose ``DELTA`` because:
#
# * It round-trips every UC client (Databricks, the generated soyuz
#   client, the JVM reference server) without surprises.
# * Downstream consumers that branch on the format (for example a
#   future delta-rs reader in PointlesSQL itself) will still *try*
#   Delta and fail cleanly if the storage_location is a file:// stub,
#   which is the right failure mode for a metadata-only mirror.
#
# A future soyuz sprint may introduce a canonical ``FOREIGN`` value;
# when that lands we flip this constant in one place.
FOREIGN_DATA_SOURCE_FORMAT = "DELTA"


# Table-type value for externally-managed tables (the UC-spec value).
EXTERNAL_TABLE_TYPE = "EXTERNAL"


@dataclass(frozen=True)
class PgColumn:
    """One column as observed in Postgres ``information_schema.columns``.

    Attributes:
        name: Column name.
        data_type: Raw ``data_type`` string (e.g. ``"integer"``,
            ``"numeric"``).
        nullable: Whether the column is nullable.
        numeric_precision: Precision for DECIMAL/NUMERIC (else ``None``).
        numeric_scale: Scale for DECIMAL/NUMERIC (else ``None``).
    """

    name: str
    data_type: str
    nullable: bool
    numeric_precision: int | None = None
    numeric_scale: int | None = None


@dataclass(frozen=True)
class PgTable:
    """A Postgres table and its columns within one schema.

    Attributes:
        schema: Schema name in Postgres.
        name: Table name in Postgres.
        columns: Columns in declaration order.
    """

    schema: str
    name: str
    columns: tuple[PgColumn, ...]


@dataclass(frozen=True)
class PostgresSnapshot:
    """All relevant schemas and tables read from a Postgres instance.

    Attributes:
        tables: Every user table observed, scoped by schema.
    """

    tables: tuple[PgTable, ...]

    def schemas(self) -> list[str]:
        """Return the distinct schema names, sorted."""
        return sorted({t.schema for t in self.tables})


@dataclass(frozen=True)
class UcColumn:
    """A UC column in the shape returned by ``get_table``.

    Only the fields the diff cares about — name and type — are carried.
    ``type_text`` is compared verbatim so a schema change like
    ``varchar(50)`` → ``text`` is detected even though both map to
    ``STRING`` in UC.
    """

    name: str
    type_name: str


@dataclass(frozen=True)
class UcTable:
    """A UC table scoped to one schema."""

    schema: str
    name: str
    columns: tuple[UcColumn, ...]


@dataclass(frozen=True)
class SyncDiff:
    """Three-bucket diff of Postgres vs UC under the same foreign catalog.

    Attributes:
        add_schemas: Schemas present in Postgres but missing in UC.
        add_tables: Tables present in Postgres but missing in UC.
        change_tables: Tables present in both with a different column
            set. The new column definition wins — soyuz rejects
            ``PATCH /tables`` (see DIVERGENCES), so applying a change
            is drop-then-create.
        drop_tables: Tables present in UC but missing in Postgres.
            We include the full three-part identifier so the delete
            call can be issued without another lookup.
    """

    add_schemas: tuple[str, ...] = field(default_factory=tuple)
    add_tables: tuple[PgTable, ...] = field(default_factory=tuple)
    change_tables: tuple[PgTable, ...] = field(default_factory=tuple)
    drop_tables: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def is_empty(self) -> bool:
        """Return True when no mutation is required."""
        return not (self.add_schemas or self.add_tables or self.change_tables or self.drop_tables)


class PostgresIntrospector(Protocol):
    """Pluggable Postgres introspection surface.

    Implementations connect to a live Postgres, read
    ``information_schema``, and return a snapshot. The protocol keeps
    the sync logic synchronous and independent of ``psycopg`` so unit
    tests can swap in a fixture.
    """

    def snapshot(self, dsn: str, schema_filter: Sequence[str] | None = None) -> PostgresSnapshot:
        """Return a snapshot of *dsn*.

        Args:
            dsn: libpq-style connection string.
            schema_filter: Optional list of schema names to include;
                when ``None`` every non-system schema is returned.

        Returns:
            A :class:`PostgresSnapshot`.
        """
        ...


def map_pg_type_to_uc(column: PgColumn) -> tuple[str, str]:
    """Translate a Postgres column to a UC ``(type_name, type_text)``.

    Returns a two-tuple because UC's ``ColumnInfo`` carries both a
    canonical ``type_name`` ("DECIMAL") and a free-form ``type_text``
    ("decimal(10,2)") — the latter is what shows in the UI.

    Args:
        column: The Postgres column to map.

    Returns:
        ``(type_name, type_text)`` ready to drop into a
        ``ColumnInfo`` payload.
    """
    raw = column.data_type.strip().lower()
    # Collapse ``character varying(n)`` / ``numeric(p,s)`` spellings
    # that ``information_schema`` never emits but that users sometimes
    # hand-craft in fixtures.
    base = raw.split("(", 1)[0].strip()
    mapped = PG_TO_UC_TYPE.get(base) or PG_TO_UC_TYPE.get(raw)
    if mapped is None:
        logger.warning(
            "pg_sync: unknown Postgres type %r for column %r — falling back to STRING",
            column.data_type,
            column.name,
        )
        return ("STRING", "string")

    if mapped == "DECIMAL" and column.numeric_precision is not None:
        scale = column.numeric_scale or 0
        text = f"decimal({column.numeric_precision},{scale})"
        return (mapped, text)

    # Otherwise the canonical type name (lowercased) doubles as
    # type_text; the UI is happy to show "int", "string", "timestamp".
    return (mapped, mapped.lower())
