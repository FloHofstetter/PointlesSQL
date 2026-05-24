"""ingest service package.

Wraps DuckDB readers (``read_csv``, ``read_parquet``, ``read_json``,
``postgres_scan``, ``mysql_scan``, ``sqlite_scan``, plus ``httpfs``
for S3/HTTP) behind one stable shape so the API / form / scheduled
executor share a single source of truth.

The seven first-party connector kinds shipped in Phase 82 each have:

* A **reader builder** in :mod:`.connectors` that turns ``(config,
  secrets, source_table?)`` into a :class:`ReaderSpec`
  (DuckDB SQL + required extensions + a discovery query for listing
  tables).
* A **probe path** in :mod:`.probe` that runs ``<reader_sql> LIMIT 0``
  on a throw-away DuckDB connection and reports resolved columns.
* A **pull path** in :mod:`.pull` that materialises rows into a pandas
  frame and hands them to ``pql.write_table()`` / ``pql.merge()``.

The scheduled-pull executor in :mod:`.executor` wires the pull path
into the Phase-8 scheduler under job kind ``"ingest_pull"``.
"""

from __future__ import annotations

from pointlessql.services.ingest.connectors import (
    ReaderSpec,
    build_reader_spec,
    build_table_listing_spec,
)
from pointlessql.services.ingest.probe import ProbeError, ProbeResult, probe_source

__all__ = [
    "ProbeError",
    "ProbeResult",
    "ReaderSpec",
    "build_reader_spec",
    "build_table_listing_spec",
    "probe_source",
]
