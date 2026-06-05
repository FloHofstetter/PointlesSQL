"""Materialise rows from a configured source into a Delta target.

the scheduled-pull executor calls :func:`pull_mapping`
once per ``(source, mapping_index)`` pair.  This module is the bridge
between the DuckDB reader plane and PQL's write plane.

* Build the reader spec via :mod:`.connectors`.
* Open a throw-away DuckDB connection; install extensions; apply
  any S3 prelude.
* For incremental pulls, wrap the SELECT with a ``WHERE high_water_col
  > <last_value>`` filter and a ``MAX(high_water_col)`` post-query.
* Materialise the rows into pandas.
* Hand the frame to ``pql.write_table()`` (full refresh) or
  ``pql.merge()`` (incremental upsert).

The function returns a :class:`PullResult` carrying row count, the new
high-water value (incremental mode), and duration timings.  Failure
raises :class:`PullError` — the executor catches it, persists the
failure on the JobRun, and emits a ``pointlessql.ingest.failed``
fanout event.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import duckdb

from pointlessql.exceptions import ValidationError
from pointlessql.services.ingest._pull_logic import (
    coerce_mapping,
    compute_new_high_water,
    max_high_water_sql,
    prepare_select_sql,
    safe_row_count,
    select_write_strategy,
)
from pointlessql.services.ingest.connectors import build_reader_spec
from pointlessql.services.ingest.probe import (
    ProbeError,
    apply_s3_credentials,
    install_extensions,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PullResult:
    """Outcome of a single mapping pull.

    Attributes:
        target_fqn: The Delta table that was written to.
        rows_written: Number of rows that landed (pandas frame size).
        duration_ms: Wall-clock pull duration, including DuckDB read
            and Delta write.
        new_high_water_value: The new high-water value to persist on
            the mapping.  ``None`` for full-refresh pulls.
        mode: ``"full"`` or ``"incremental"`` — echoed back so the
            executor doesn't need to re-read the mapping.
    """

    target_fqn: str
    rows_written: int
    duration_ms: int
    new_high_water_value: str | None
    mode: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready dict for the API response."""
        return {
            "target_fqn": self.target_fqn,
            "rows_written": int(self.rows_written),
            "duration_ms": int(self.duration_ms),
            "new_high_water_value": self.new_high_water_value,
            "mode": self.mode,
        }


class PullError(Exception):
    """Pull failure with a user-actionable message.

    Args:
        reason: Short error description, safe to surface in HTTP and
            audit log.
        hint: Optional follow-up instruction.
    """

    def __init__(self, reason: str, hint: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.hint = hint


def pull_mapping(
    *,
    kind: str,
    config: dict[str, Any],
    secrets: dict[str, Any],
    mapping: dict[str, Any],
    pql_instance: Any,
) -> PullResult:
    """Execute a single mapping pull end-to-end.

    Args:
        kind: Connector kind.
        config: Non-secret connection parameters.
        secrets: Plaintext credentials.
        mapping: One entry from ``IngestSource.table_mappings``
            (already JSON-decoded).
        pql_instance: A :class:`pointlessql.pql.pql.PQL` instance
            with the appropriate principal / settings — the caller
            owns construction so tests can inject a fixture.

    Returns:
        A :class:`PullResult`.

    Raises:
        PullError: On any user-visible failure.  The executor catches
            this and writes it to ``JobRun.error``.
    """
    started = time.perf_counter()
    try:
        coerced = coerce_mapping(mapping)
    except ValidationError as exc:
        raise PullError(reason=str(exc)) from exc

    target_fqn = coerced["target_fqn"]
    mode = coerced["mode"]
    high_water_col = coerced["high_water_col"]
    last_value = coerced["last_high_water_value"]

    try:
        spec = build_reader_spec(
            kind, config, secrets, source_table=coerced["source_table"] or None
        )
    except ValidationError as exc:
        raise PullError(reason=str(exc)) from exc

    conn = duckdb.connect(":memory:")
    try:
        cursor = conn.cursor()
        try:
            install_extensions(cursor, spec.install)
        except ProbeError as exc:
            raise PullError(reason=exc.reason, hint=exc.hint) from exc
        if kind == "s3":
            apply_s3_credentials(cursor, secrets)

        new_high_water: str | None = None
        if mode == "incremental":
            assert isinstance(high_water_col, str)
            # Run the MAX query first against the pre-cutoff window
            # so we capture the watermark even if the SELECT returns
            # zero rows.
            try:
                cursor.execute(max_high_water_sql(spec, high_water_col, last_value))
                row = cursor.fetchone()
            except duckdb.Error as exc:
                logger.warning("ingest pull MAX failed: %s", exc)
                raise PullError(
                    reason="Could not compute high-water mark on source.",
                    hint="Verify the column name and that the source is reachable.",
                ) from exc
            new_high_water = compute_new_high_water(row, last_value)

        select_sql = prepare_select_sql(spec, mode, high_water_col, last_value)
        try:
            df = cursor.execute(select_sql).fetch_df()
        except duckdb.Error as exc:
            logger.warning("ingest pull SELECT failed: %s", exc)
            raise PullError(
                reason="DuckDB SELECT failed against the source.",
                hint="See server logs for the underlying error.",
            ) from exc
    finally:
        conn.close()

    rows_written = safe_row_count(df)

    # Incremental's first pull bootstraps the table via write_table —
    # pql.merge() can't create a missing target, so the strategy switch
    # only upserts once a watermark exists.
    operation, write_kwargs = select_write_strategy(mode, last_value, high_water_col)
    try:
        if operation == "merge":
            pql_instance.merge(df, target_fqn, **write_kwargs)
        else:
            pql_instance.write_table(df, target_fqn, **write_kwargs)
    except Exception as exc:  # noqa: BLE001 — surface as PullError
        logger.exception("ingest pull write failed")
        raise PullError(
            reason=f"Write to {target_fqn} failed: {type(exc).__name__}.",
            hint="See server logs for the underlying error.",
        ) from exc

    duration_ms = int((time.perf_counter() - started) * 1000)
    return PullResult(
        target_fqn=target_fqn,
        rows_written=rows_written,
        duration_ms=duration_ms,
        new_high_water_value=new_high_water,
        mode=mode,
    )


def load_mappings(table_mappings_json: str) -> list[dict[str, Any]]:
    """Decode the JSON column safely; empty list on malformed input."""
    if not table_mappings_json:
        return []
    try:
        data = json.loads(table_mappings_json)
    except ValueError, TypeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:  # type: ignore[reportUnknownVariableType]
        if isinstance(item, dict):
            out.append(item)  # type: ignore[reportUnknownArgumentType]
    return out


def dump_mappings(mappings: list[dict[str, Any]]) -> str:
    """Encode the list back to the JSON column."""
    return json.dumps(mappings, default=str)
