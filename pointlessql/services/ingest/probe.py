"""DuckDB-driven probe for an ingest source.

Phase 82.1 — the UI "Probe" button posts the in-form config + secrets
to ``POST /api/ingest/probe``; the route calls :func:`probe_source`
to dry-run the configured reader against a throw-away DuckDB
connection and reports the resolved column list.

The probe never persists anything: it spins a fresh in-memory DuckDB
instance, installs the required extensions, applies any S3
``SET``-prelude, runs ``<reader_sql> LIMIT 0``, and returns the
``description`` rows.  On failure it raises :class:`ProbeError` with a
human-readable hint so the form can surface a useful message instead
of a raw driver traceback (which would leak the connection string).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import duckdb

from pointlessql.exceptions import ValidationError
from pointlessql.services.ingest.connectors import (
    ReaderSpec,
    build_reader_spec,
)

logger = logging.getLogger(__name__)

# Lazy-install cache: extensions install + load is idempotent but
# slow on the first probe per extension.  We remember which ones the
# current Python process already loaded into the *throw-away* probe
# pool so subsequent probes skip the install hit.
_INSTALLED_EXTENSIONS: set[str] = set()


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """Successful probe payload.

    Attributes:
        columns: List of ``{"name": str, "type": str}`` dicts, in the
            order DuckDB returned them.
        extension_ms: Wall-clock time spent installing + loading
            DuckDB extensions for this probe.  ``0`` when no
            extensions were needed.
        query_ms: Wall-clock time spent on the ``SELECT ... LIMIT 0``
            itself.
    """

    columns: list[dict[str, str]]
    extension_ms: int
    query_ms: int

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready dict for the API response."""
        return {
            "columns": list(self.columns),
            "extension_ms": int(self.extension_ms),
            "query_ms": int(self.query_ms),
        }


class ProbeError(Exception):
    """Structured probe failure with a user-actionable hint.

    The route layer turns this into a 400-response with
    ``{"error": reason, "hint": hint}`` — driver-level tracebacks are
    swallowed so the connection string never leaks into a HTTP body.

    Args:
        reason: Short message describing what failed.
        hint: Optional follow-up instruction for the user.
    """

    def __init__(self, reason: str, hint: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.hint = hint

    def to_dict(self) -> dict[str, str | None]:
        """Return a JSON-ready dict for the API error body."""
        return {"reason": self.reason, "hint": self.hint}


def install_extensions(
    cursor: duckdb.DuckDBPyConnection, extensions: tuple[str, ...]
) -> int:
    """Install + load each extension on the throw-away connection.

    Args:
        cursor: A DuckDB connection cursor.
        extensions: Tuple of extension names.

    Returns:
        Wall-clock milliseconds spent in the install/load calls.

    Raises:
        ProbeError: When an extension cannot be installed (offline
            CI, blocked egress, unsupported architecture).
    """
    if not extensions:
        return 0
    started = time.perf_counter()
    for ext in extensions:
        try:
            if ext not in _INSTALLED_EXTENSIONS:
                cursor.execute(f"INSTALL {ext};")
                _INSTALLED_EXTENSIONS.add(ext)
            cursor.execute(f"LOAD {ext};")
        except duckdb.Error as exc:
            raise ProbeError(
                reason=f"DuckDB extension {ext!r} could not be loaded.",
                hint=(
                    f"Install it locally and retry, or use a different "
                    f"connector kind.  Underlying error: {type(exc).__name__}."
                ),
            ) from exc
    return int((time.perf_counter() - started) * 1000)


def apply_s3_credentials(
    cursor: duckdb.DuckDBPyConnection, secrets: dict[str, Any]
) -> None:
    """Apply S3 credentials (if any) via DuckDB ``SET`` statements.

    Only fires when ``access_key`` is present in *secrets* — the
    HTTP / public-bucket case skips the prelude entirely so probes
    against public S3 URLs work without credentials.
    """
    access_key = secrets.get("access_key")
    if not access_key:
        return
    secret_key = secrets.get("secret_key") or ""
    region = secrets.get("region") or "us-east-1"
    # ``SET`` quoting: DuckDB accepts the string form for these settings.
    cursor.execute(f"SET s3_access_key_id={_q(str(access_key))};")
    cursor.execute(f"SET s3_secret_access_key={_q(str(secret_key))};")
    cursor.execute(f"SET s3_region={_q(str(region))};")


def _q(value: str) -> str:
    """Quote *value* as a DuckDB single-quoted string literal."""
    return "'" + value.replace("'", "''") + "'"


def _run_listing_or_probe(
    cursor: duckdb.DuckDBPyConnection, spec: ReaderSpec
) -> tuple[list[dict[str, str]], int]:
    """Execute the spec's SQL with ``LIMIT 0`` and return resolved columns.

    For multi-statement listing specs (Postgres/MySQL/SQLite ATTACH +
    SELECT + DETACH) we execute each ``;``-separated chunk so the
    SELECT runs in the same session as the ATTACH.

    Args:
        cursor: A DuckDB connection cursor with extensions already loaded.
        spec: The :class:`ReaderSpec` whose ``sql`` should be probed.

    Returns:
        ``(columns, query_ms)`` — columns is a list of name/type dicts
        in cursor order; query_ms is the SELECT's wall-clock cost.

    Raises:
        ProbeError: When the spec contains no SELECT or the DuckDB
            cursor fails to describe the resolved schema.
    """
    started = time.perf_counter()
    # Multi-statement specs already terminate every statement with
    # a ``;``; split + run individually so the last SELECT is the one
    # whose description we read.
    statements = [s.strip() for s in spec.sql.split(";") if s.strip()]
    if not statements:
        raise ProbeError(reason="Empty reader SQL.")
    last_select_idx = max(
        (i for i, stmt in enumerate(statements) if stmt.lower().startswith("select")),
        default=-1,
    )
    if last_select_idx < 0:
        raise ProbeError(reason="Reader SQL contains no SELECT statement.")
    for idx, stmt in enumerate(statements):
        if idx == last_select_idx:
            # Wrap the final SELECT with LIMIT 0 so we get the schema
            # without materialising rows.  Wrapping with a sub-SELECT
            # works uniformly regardless of any embedded LIMIT/ORDER.
            cursor.execute(f"SELECT * FROM ({stmt}) AS _pql_probe LIMIT 0;")
        else:
            cursor.execute(stmt + ";")
    columns: list[dict[str, str]] = []
    description = cursor.description or []
    for col in description:
        # PEP 249 description: (name, type_code, ...).  DuckDB exposes
        # the SQL-level type name in ``col[1]`` for our purposes.
        col_name = str(col[0])
        col_type = str(col[1]) if len(col) > 1 else ""
        columns.append({"name": col_name, "type": col_type})
    query_ms = int((time.perf_counter() - started) * 1000)
    return columns, query_ms


def probe_source(
    kind: str,
    config: dict[str, Any],
    secrets: dict[str, Any] | None = None,
    source_table: str | None = None,
) -> ProbeResult:
    """Dry-run the configured reader and report resolved columns.

    Spins a fresh in-memory DuckDB connection (so the probe never
    pollutes any shared state), installs the required extensions,
    applies any S3 prelude, and executes the reader SQL wrapped in
    ``LIMIT 0``.

    Args:
        kind: Connector kind.
        config: Non-secret connection parameters.
        secrets: Plaintext credentials (``None`` when the kind doesn't
            need any).
        source_table: For SQL connectors, the source-side table name.

    Returns:
        A :class:`ProbeResult` carrying columns + timing.

    Raises:
        ProbeError: When the probe fails for any reason — the public
            API surface only ever shows this class to callers, never
            raw driver errors.
    """
    secrets_dict: dict[str, Any] = secrets or {}
    try:
        spec = build_reader_spec(kind, config, secrets_dict, source_table=source_table)
    except ValidationError as exc:
        raise ProbeError(reason=str(exc)) from exc

    conn = duckdb.connect(":memory:")
    try:
        cursor = conn.cursor()
        extension_ms = install_extensions(cursor, spec.install)
        if kind == "s3":
            apply_s3_credentials(cursor, secrets_dict)
        try:
            columns, query_ms = _run_listing_or_probe(cursor, spec)
        except ProbeError:
            raise
        except duckdb.Error as exc:
            # Swallow the driver detail so credentials never end up
            # in an HTTP body.  Log the full exception locally for
            # operators.
            logger.warning(
                "ingest probe failed for kind=%s: %s",
                kind,
                exc,
                exc_info=True,
            )
            raise ProbeError(
                reason=f"DuckDB reader failed to resolve schema for {kind!r}.",
                hint=(
                    "Double-check the connection parameters and that the "
                    "source is reachable from this server."
                ),
            ) from exc
        except Exception as exc:  # noqa: BLE001 — also paranoid against driver leaks
            logger.exception("unexpected probe failure")
            raise ProbeError(
                reason=f"Probe failed for {kind!r}.",
                hint="See server logs for the underlying error.",
            ) from exc
    finally:
        conn.close()

    return ProbeResult(
        columns=columns, extension_ms=extension_ms, query_ms=query_ms
    )


def list_tables(
    kind: str,
    config: dict[str, Any],
    secrets: dict[str, Any] | None = None,
) -> list[str]:
    """List the source's available tables.

    File-based connectors short-circuit to a single-element list
    derived from the file path.  SQL connectors actually hit the
    source's information schema.

    Args:
        kind: Connector kind.
        config: Non-secret connection parameters.
        secrets: Plaintext credentials.

    Returns:
        List of table names (``"schema.table"`` for SQL connectors,
        bare basename for file-based).

    Raises:
        ProbeError: On listing failure.
    """
    from pointlessql.services.ingest.connectors import build_table_listing_spec

    secrets_dict: dict[str, Any] = secrets or {}
    try:
        spec = build_table_listing_spec(kind, config, secrets_dict)
    except ValidationError as exc:
        raise ProbeError(reason=str(exc)) from exc
    if spec.single_table_name is not None:
        return [spec.single_table_name]

    conn = duckdb.connect(":memory:")
    try:
        cursor = conn.cursor()
        install_extensions(cursor, spec.install)
        try:
            # Multi-statement spec: run them in order; the SELECT's
            # rows are the listing.
            statements = [s.strip() for s in spec.sql.split(";") if s.strip()]
            rows: list[tuple[Any, ...]] = []
            for stmt in statements:
                cursor.execute(stmt + ";")
                if stmt.lower().startswith("select"):
                    rows = cursor.fetchall()
            return [str(r[0]) for r in rows]
        except duckdb.Error as exc:
            logger.warning(
                "ingest table-listing failed for kind=%s: %s", kind, exc
            )
            raise ProbeError(
                reason=f"DuckDB could not list tables on {kind!r} source.",
                hint="Double-check connection parameters and reachability.",
            ) from exc
    finally:
        conn.close()
