"""Postgres → Unity Catalog sync worker.

This module is the Sprint 18 bridge between a live Postgres database
(referenced by a soyuz-catalog Connection) and a foreign UC catalog.
It runs in two passes:

1. :func:`introspect_pg` reads ``information_schema`` and returns a
   normalised :class:`PostgresSnapshot` — list of schemas, tables,
   and typed columns. Pure SQL, no UC calls. Split out so tests can
   stub it.
2. :func:`diff_snapshots` compares that snapshot against the current
   UC state (returned from the soyuz facade) and produces a
   :class:`SyncDiff`. Still pure — no HTTP, no mutation. This is the
   unit that the scheduler (Sprint 19) will call.
3. :func:`apply_diff` walks the diff and drives the facade's
   ``create_schema`` / ``create_table`` / ``delete_table`` methods.
   Wrapped in :func:`run_sync` which also writes the
   :class:`~pointlessql.models.SyncRun` row and updates its status.

The diff intentionally stays at the "which tables exist and what are
their columns" level — we do not try to migrate data, reconcile
primary keys, or propagate tag/comment edits back to Postgres. Those
are out-of-scope concerns that would blur the one-way mirror contract
with the source database.
"""

from __future__ import annotations

import datetime
import logging
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.orm import Session, sessionmaker

from pointlessql.exceptions import CatalogUnavailableError, ValidationError
from pointlessql.models import SyncRun
from pointlessql.services.unitycatalog import UnityCatalogClient

logger = logging.getLogger(__name__)


# Options that look like secrets are never read from the free-form
# connection ``options`` dict — they must come from a bound Credential.
# Case-insensitive: ``password``, ``PASS``, ``api_secret``, ``token``,
# ``access_key`` all match. ``key`` is intentionally broad because
# ``api_key``, ``private_key``, ``license_key`` all legitimately
# classify as secrets.
_SECRET_KEY_RE = re.compile(r"pass|secret|key|token", re.IGNORECASE)


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
_FOREIGN_DATA_SOURCE_FORMAT = "DELTA"


# Table-type value for externally-managed tables (the UC-spec value).
_EXTERNAL_TABLE_TYPE = "EXTERNAL"


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


def diff_snapshots(pg: PostgresSnapshot, uc_tables: Iterable[UcTable]) -> SyncDiff:
    """Return the diff between a live Postgres snapshot and UC state.

    The function is pure — given identical inputs it always returns an
    identical diff — so the unit tests assert on it directly without
    any HTTP mocking. The behavioural contract:

    * A table is **added** when its ``(schema, name)`` appears in
      ``pg`` but not in ``uc_tables``.
    * A table is **dropped** when its ``(schema, name)`` appears in
      ``uc_tables`` but not in ``pg``.
    * A table is **changed** when it appears in both and the column
      names, order, or type names disagree. We normalise both sides
      to a tuple of ``(name, type_name)`` before comparing so a UC
      column with an extra ``comment`` does not register as a diff.

    Args:
        pg: Snapshot from :class:`PostgresIntrospector`.
        uc_tables: Current UC state under the foreign catalog.

    Returns:
        A :class:`SyncDiff`.
    """
    pg_by_key = {(t.schema, t.name): t for t in pg.tables}
    uc_by_key = {(t.schema, t.name): t for t in uc_tables}

    uc_schemas = {t.schema for t in uc_by_key.values()}
    pg_schemas = set(pg.schemas())
    add_schemas = tuple(sorted(pg_schemas - uc_schemas))

    add_tables: list[PgTable] = []
    change_tables: list[PgTable] = []
    for key, pg_tbl in pg_by_key.items():
        uc_tbl = uc_by_key.get(key)
        if uc_tbl is None:
            add_tables.append(pg_tbl)
            continue
        pg_cols = tuple((c.name, map_pg_type_to_uc(c)[0]) for c in pg_tbl.columns)
        uc_cols = tuple((c.name, c.type_name) for c in uc_tbl.columns)
        if pg_cols != uc_cols:
            change_tables.append(pg_tbl)

    drop_tables = tuple(sorted(key for key in uc_by_key if key not in pg_by_key))

    return SyncDiff(
        add_schemas=add_schemas,
        add_tables=tuple(add_tables),
        change_tables=tuple(change_tables),
        drop_tables=drop_tables,
    )


def _effective_options(
    connection: dict[str, Any], credential: dict[str, Any] | None
) -> dict[str, Any]:
    """Merge connection options with secrets read from a Credential.

    The sprint contract: options with keys matching
    ``(?i)pass|secret|key|token`` are read from the bound Credential's
    ``additional_properties`` (the generated client's catch-all for
    non-spec fields — see ADR-0013 in soyuz-catalog). Non-secret
    options stay on the Connection's ``options`` dict. Missing
    Credential falls back to ``options`` so a local dev Postgres can
    skip the ceremony entirely.

    Args:
        connection: Raw ``ConnectionInfo.to_dict()`` payload.
        credential: Raw ``CredentialInfo.to_dict()`` payload or
            ``None`` when no credential is bound.

    Returns:
        The merged options dict, with secret keys overridden by the
        Credential when one is present.
    """
    options: dict[str, Any] = dict(connection.get("options") or {})
    if credential is None:
        return options
    # additional_properties is where soyuz stashes non-spec fields
    # like postgres-flavour secrets.
    cred_extras: dict[str, Any] = dict(credential.get("additional_properties") or {})
    for key, value in cred_extras.items():
        if _SECRET_KEY_RE.search(key):
            options[key] = value
    return options


def build_dsn(options: dict[str, Any]) -> str:
    """Translate a connection options dict to a libpq DSN string.

    Accepts the Databricks-style UC keys (``host``, ``port``,
    ``database``, ``user``, ``password``) as well as the raw libpq
    ``dbname``. Missing ``host`` is fatal because we would silently
    connect to localhost — better to fail fast with a clear error.

    Args:
        options: Merged connection options (see
            :func:`_effective_options`).

    Returns:
        A space-separated ``key=value`` libpq DSN.

    Raises:
        ValidationError: When a required key (``host``) is missing.
    """
    host = options.get("host")
    if not host:
        raise ValidationError("Postgres connection options missing required key 'host'")
    pairs: list[str] = [f"host={host}"]
    port = options.get("port")
    if port:
        pairs.append(f"port={port}")
    database = options.get("database") or options.get("dbname")
    if database:
        pairs.append(f"dbname={database}")
    user = options.get("user")
    if user:
        pairs.append(f"user={user}")
    password = options.get("password")
    if password:
        pairs.append(f"password={password}")
    return " ".join(pairs)


class PsycopgIntrospector:
    """Default :class:`PostgresIntrospector` backed by ``psycopg``.

    Kept as a concrete class (not a module-level function) so the
    protocol contract is explicit: tests substitute any object that
    implements :meth:`snapshot`, no monkeypatching required.
    """

    def snapshot(self, dsn: str, schema_filter: Sequence[str] | None = None) -> PostgresSnapshot:
        """Read ``information_schema`` from *dsn*.

        Args:
            dsn: libpq connection string.
            schema_filter: Optional list of schema names to include;
                when ``None`` every schema except ``pg_catalog`` and
                ``information_schema`` is returned.

        Returns:
            A :class:`PostgresSnapshot`.

        Raises:
            CatalogUnavailableError: When the database cannot be
                reached or the introspection query fails.
        """
        # Imported lazily so unit tests that never call snapshot()
        # can run on machines without libpq.
        import psycopg
        from psycopg import sql

        exclude = ("pg_catalog", "information_schema")
        base_query = sql.SQL(
            """
            SELECT
                c.table_schema,
                c.table_name,
                c.column_name,
                c.data_type,
                c.is_nullable,
                c.numeric_precision,
                c.numeric_scale,
                c.ordinal_position
            FROM information_schema.columns c
            JOIN information_schema.tables t
              ON c.table_schema = t.table_schema
             AND c.table_name = t.table_name
            WHERE t.table_type = 'BASE TABLE'
              AND c.table_schema NOT IN ({excl1}, {excl2})
            """
        ).format(
            excl1=sql.Placeholder(),
            excl2=sql.Placeholder(),
        )
        params: list[Any] = [exclude[0], exclude[1]]
        query: sql.Composable = base_query
        if schema_filter:
            placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in schema_filter)
            query = query + sql.SQL(" AND c.table_schema IN ({f})").format(f=placeholders)
            params.extend(schema_filter)
        query = query + sql.SQL(" ORDER BY c.table_schema, c.table_name, c.ordinal_position")

        try:
            with psycopg.connect(dsn) as conn, conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
        except psycopg.Error as exc:
            raise CatalogUnavailableError(f"Postgres introspection failed: {exc}") from exc

        tables: dict[tuple[str, str], list[PgColumn]] = {}
        for row in rows:
            schema, name, col, dtype, nullable, precision, scale, _pos = row
            tables.setdefault((schema, name), []).append(
                PgColumn(
                    name=col,
                    data_type=dtype,
                    nullable=(nullable == "YES"),
                    numeric_precision=precision,
                    numeric_scale=scale,
                )
            )
        return PostgresSnapshot(
            tables=tuple(
                PgTable(schema=k[0], name=k[1], columns=tuple(cols)) for k, cols in tables.items()
            )
        )


async def collect_uc_tables(uc: UnityCatalogClient, catalog_name: str) -> list[UcTable]:
    """Return every table currently mirrored under *catalog_name*.

    Walks schemas → tables → columns. Used by :func:`run_sync` to
    build the "current UC state" half of the diff. Missing catalog
    yields an empty list (soyuz returns an empty list for
    ``list_schemas`` when the catalog has none).

    Args:
        uc: Configured UnityCatalog facade.
        catalog_name: Target catalog.

    Returns:
        List of :class:`UcTable` objects, ordered by ``(schema, name)``.
    """
    schemas = await uc.list_schemas(catalog_name)
    out: list[UcTable] = []
    for schema in schemas:
        schema_name = schema.get("name")
        if not schema_name:
            continue
        tables = await uc.list_tables(catalog_name, schema_name)
        for tbl in tables:
            cols_raw = tbl.get("columns") or []
            cols: list[UcColumn] = []
            for c in cols_raw:
                cname = c.get("name")
                ctype = c.get("type_name") or ""
                if cname:
                    cols.append(UcColumn(name=str(cname), type_name=str(ctype)))
            name = tbl.get("name")
            if name:
                out.append(
                    UcTable(
                        schema=str(schema_name),
                        name=str(name),
                        columns=tuple(cols),
                    )
                )
    return sorted(out, key=lambda t: (t.schema, t.name))


def _columns_payload(pg_tbl: PgTable) -> list[dict[str, Any]]:
    """Build the ``ColumnInfo`` list for a UC create request.

    ``type_json`` is a minimal JSON shape — name, type, nullable,
    empty metadata — because soyuz stores it verbatim on write and
    round-trips it on read (ADR-0009). Keeping the JSON compact
    avoids surprising anyone grepping the UC table for column
    annotations.
    """
    import json as _json

    cols: list[dict[str, Any]] = []
    for i, col in enumerate(pg_tbl.columns):
        type_name, type_text = map_pg_type_to_uc(col)
        type_json = _json.dumps(
            {
                "name": col.name,
                "type": type_text,
                "nullable": col.nullable,
                "metadata": {},
            }
        )
        payload: dict[str, Any] = {
            "name": col.name,
            "type_name": type_name,
            "type_text": type_text,
            "type_json": type_json,
            "position": i,
            "nullable": col.nullable,
        }
        if type_name == "DECIMAL":
            payload["type_precision"] = col.numeric_precision
            payload["type_scale"] = col.numeric_scale or 0
        cols.append(payload)
    return cols


def _storage_location_stub(catalog: str, schema: str, table: str) -> str:
    """Return a placeholder ``file://`` storage_location for a foreign table.

    soyuz-catalog's :func:`parse_storage_uri` rejects schemes outside
    ``{file, s3, s3a, abfss, gs}``. A Postgres-backed table has no
    filesystem storage, so we emit a deterministic ``file:///foreign/...``
    path — the location is never read, only stored so the UC row
    remains addressable. The path includes the full three-part name
    to keep every stub unique.
    """
    return f"file:///foreign/{catalog}/{schema}/{table}"


async def apply_diff(
    uc: UnityCatalogClient, catalog_name: str, diff: SyncDiff
) -> tuple[int, int, int]:
    """Apply a :class:`SyncDiff` against soyuz-catalog.

    Returns the ``(added, changed, dropped)`` counts so the caller can
    persist them on the :class:`~pointlessql.models.SyncRun` row. The
    function is resilient: if creating one table fails, the others
    are still attempted so a single bad column type does not stall
    the whole sync. Failures surface as :class:`CatalogUnavailableError`
    raised by the facade, re-raised to the caller so they land on the
    run's ``error`` field.

    Args:
        uc: Configured UnityCatalog facade.
        catalog_name: Target foreign catalog.
        diff: Work to apply.

    Returns:
        ``(added_count, changed_count, dropped_count)``.
    """
    added = 0
    changed = 0
    dropped = 0

    for schema_name in diff.add_schemas:
        await uc.create_schema({"catalog_name": catalog_name, "name": schema_name})
        added += 1

    for tbl in diff.add_tables:
        await uc.create_table(
            {
                "catalog_name": catalog_name,
                "schema_name": tbl.schema,
                "name": tbl.name,
                "table_type": _EXTERNAL_TABLE_TYPE,
                "data_source_format": _FOREIGN_DATA_SOURCE_FORMAT,
                "columns": _columns_payload(tbl),
                "storage_location": _storage_location_stub(catalog_name, tbl.schema, tbl.name),
            }
        )
        added += 1

    for tbl in diff.change_tables:
        # soyuz rejects PATCH /tables; drop-then-create is the only
        # path to "change" columns.
        await uc.delete_table(catalog_name, tbl.schema, tbl.name)
        await uc.create_table(
            {
                "catalog_name": catalog_name,
                "schema_name": tbl.schema,
                "name": tbl.name,
                "table_type": _EXTERNAL_TABLE_TYPE,
                "data_source_format": _FOREIGN_DATA_SOURCE_FORMAT,
                "columns": _columns_payload(tbl),
                "storage_location": _storage_location_stub(catalog_name, tbl.schema, tbl.name),
            }
        )
        changed += 1

    for schema_name, table_name in diff.drop_tables:
        await uc.delete_table(catalog_name, schema_name, table_name)
        dropped += 1

    return (added, changed, dropped)


def _start_run(session: Session, catalog_name: str) -> SyncRun:
    """Insert the initial ``running`` :class:`SyncRun` row."""
    run = SyncRun(
        catalog_name=catalog_name,
        started_at=datetime.datetime.now(datetime.UTC),
        status="running",
        added_count=0,
        changed_count=0,
        dropped_count=0,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _finish_run(
    session: Session,
    run_id: int,
    status: str,
    added: int,
    changed: int,
    dropped: int,
    error: str | None,
) -> None:
    """Flip a :class:`SyncRun` from ``running`` to its terminal status."""
    run = session.get(SyncRun, run_id)
    if run is None:  # pragma: no cover — row was just inserted
        return
    run.status = status
    run.finished_at = datetime.datetime.now(datetime.UTC)
    run.added_count = added
    run.changed_count = changed
    run.dropped_count = dropped
    run.error = error
    session.commit()


async def run_sync(
    uc: UnityCatalogClient,
    factory: sessionmaker[Session],
    catalog_name: str,
    introspector: PostgresIntrospector,
    connection: dict[str, Any],
    credential: dict[str, Any] | None,
    schema_filter: Sequence[str] | None = None,
) -> SyncRun:
    """End-to-end: introspect Postgres, diff, apply, record.

    The high-level orchestration glue: wire the passed introspector
    into the same ``SyncRun`` bookkeeping the API route and the
    future scheduler both depend on. Always writes exactly one row
    — the ``running`` placeholder is updated in place so the history
    card never shows half-formed entries.

    Args:
        uc: UnityCatalog facade to drive.
        factory: SQLAlchemy session factory (our own metadata DB).
        catalog_name: Foreign catalog to sync.
        introspector: Source of the Postgres snapshot.
        connection: ``ConnectionInfo.to_dict()`` payload for the
            catalog's bound connection.
        credential: Optional ``CredentialInfo.to_dict()`` payload that
            supplies secrets the connection options do not carry.
        schema_filter: Optional list of Postgres schema names to sync;
            ``None`` means every non-system schema.

    Returns:
        The final :class:`SyncRun` row (post-commit).
    """
    with factory() as session:
        run = _start_run(session, catalog_name)
        run_id = run.id

    added = 0
    changed = 0
    dropped = 0
    error: str | None = None

    try:
        options = _effective_options(connection, credential)
        dsn = build_dsn(options)
        snapshot = introspector.snapshot(dsn, schema_filter)
        uc_tables = await collect_uc_tables(uc, catalog_name)
        diff = diff_snapshots(snapshot, uc_tables)
        logger.info(
            "pg_sync: catalog=%s add_schemas=%d add_tables=%d change_tables=%d drop_tables=%d",
            catalog_name,
            len(diff.add_schemas),
            len(diff.add_tables),
            len(diff.change_tables),
            len(diff.drop_tables),
        )
        added, changed, dropped = await apply_diff(uc, catalog_name, diff)
        status = "succeeded"
    except Exception as exc:
        error = str(exc)
        status = "failed"
        logger.exception("pg_sync: sync failed for catalog=%s", catalog_name)

    with factory() as session:
        _finish_run(session, run_id, status, added, changed, dropped, error)
        final = session.get(SyncRun, run_id)
        assert final is not None  # just written
        # Detach so the caller can read attributes after the session closes.
        session.expunge(final)
        return final


def list_recent_runs(
    factory: sessionmaker[Session], catalog_name: str, limit: int = 20
) -> list[SyncRun]:
    """Return the last *limit* :class:`SyncRun` rows for *catalog_name*.

    Ordered newest-first. Powers the sync-history card on the
    foreign-catalog detail page.

    Args:
        factory: SQLAlchemy session factory.
        catalog_name: Target catalog.
        limit: Maximum number of rows to return.

    Returns:
        A list of :class:`SyncRun` objects, most recent first.
    """
    from sqlalchemy import select

    with factory() as session:
        rows = session.scalars(
            select(SyncRun)
            .where(SyncRun.catalog_name == catalog_name)
            .order_by(SyncRun.started_at.desc())
            .limit(limit)
        ).all()
        # Detach so the caller renders attributes outside the session.
        for r in rows:
            session.expunge(r)
        return list(rows)
