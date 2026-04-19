"""Pure diff + UC-mutation appliers.

Bridges :class:`PostgresSnapshot` (Postgres truth) and the live UC
catalog state. ``diff_snapshots`` is pure; ``apply_diff`` walks the
diff and drives the soyuz facade.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pointlessql.services.pg_sync.types import (
    EXTERNAL_TABLE_TYPE,
    FOREIGN_DATA_SOURCE_FORMAT,
    PgTable,
    PostgresSnapshot,
    SyncDiff,
    UcColumn,
    UcTable,
    map_pg_type_to_uc,
)
from pointlessql.services.unitycatalog import UnityCatalogClient


def diff_snapshots(
    pg: PostgresSnapshot, uc_tables: Iterable[UcTable]
) -> SyncDiff:
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


async def collect_uc_tables(uc: UnityCatalogClient, catalog_name: str) -> list[UcTable]:
    """Return every table currently mirrored under *catalog_name*.

    Walks schemas → tables → columns. Used by ``run_sync`` to build
    the "current UC state" half of the diff. Missing catalog yields
    an empty list (soyuz returns an empty list for ``list_schemas``
    when the catalog has none).

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
                "table_type": EXTERNAL_TABLE_TYPE,
                "data_source_format": FOREIGN_DATA_SOURCE_FORMAT,
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
                "table_type": EXTERNAL_TABLE_TYPE,
                "data_source_format": FOREIGN_DATA_SOURCE_FORMAT,
                "columns": _columns_payload(tbl),
                "storage_location": _storage_location_stub(catalog_name, tbl.schema, tbl.name),
            }
        )
        changed += 1

    for schema_name, table_name in diff.drop_tables:
        await uc.delete_table(catalog_name, schema_name, table_name)
        dropped += 1

    return (added, changed, dropped)
