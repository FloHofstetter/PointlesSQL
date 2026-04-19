"""Concrete :class:`PsycopgIntrospector` for live Postgres."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pointlessql.exceptions import CatalogUnavailableError
from pointlessql.services.pg_sync.types import (
    PgColumn,
    PgTable,
    PostgresSnapshot,
)


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
