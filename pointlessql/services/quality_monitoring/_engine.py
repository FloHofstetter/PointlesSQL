"""Synchronous quality-scan engine — profiles tables, derives anomalies.

One scan profiles every monitored table (row count + per-column
metrics via the shared table-stats profiler), persists a
:class:`~pointlessql.models.quality_monitoring.TableProfileSnapshot`,
and evaluates the anomaly rules against the table's previous
snapshot:

* ``volume_drop`` — the row count fell below 80 % (warn) / 50 %
  (critical) of the previous snapshot, provided the previous
  snapshot had at least :data:`VOLUME_DROP_MIN_PREVIOUS_ROWS` rows
  (tiny tables fluctuate too much to alert on).
* ``null_spike`` — a column's null fraction rose by more than
  :data:`NULL_SPIKE_WARN_DELTA` (warn) /
  :data:`NULL_SPIKE_CRITICAL_DELTA` (critical) absolute.
* ``schema_change`` — columns appeared or disappeared (warn).
* ``freshness`` — the last Delta commit is older than
  :data:`FRESHNESS_MAX_AGE_HOURS` hours (warn).

An open anomaly with the same ``(table, column, kind)`` identity is
never duplicated; when the rule stops tripping, the open row gets
its ``resolved_at`` stamped instead.

Everything here is synchronous (DuckDB + deltalake + SQLAlchemy) —
the executor dispatches it through ``asyncio.to_thread``.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import desc, select

from pointlessql.models.quality_monitoring import QualityAnomaly, TableProfileSnapshot
from pointlessql.services.quality_monitoring._crud import serialize_anomaly
from pointlessql.services.table_stats import compute_stats

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

FRESHNESS_MAX_AGE_HOURS = 24
"""A table whose last Delta commit is older than this warns.

A fixed wall-clock budget (rather than a multiple of the scan
interval) keeps the rule independent of the monitor's cron cadence
and predictable for operators.
"""

VOLUME_DROP_WARN_RATIO = 0.8
"""Row count below this fraction of the previous snapshot warns."""

VOLUME_DROP_CRITICAL_RATIO = 0.5
"""Row count below this fraction of the previous snapshot is critical."""

VOLUME_DROP_MIN_PREVIOUS_ROWS = 100
"""Volume rule only fires when the previous snapshot had this many rows."""

NULL_SPIKE_WARN_DELTA = 0.2
"""Absolute null-fraction increase that warns."""

NULL_SPIKE_CRITICAL_DELTA = 0.5
"""Absolute null-fraction increase that is critical."""

_METRIC_KEYS = ("null_count", "distinct_count", "min", "max", "mean")


def _duckdb_type(arrow_type: Any) -> str:
    """Map a PyArrow type to the DuckDB type string the profiler expects.

    Only the numeric / non-numeric split matters (it decides whether
    the profiler computes a mean), so unknown types collapse to
    ``VARCHAR``.

    Args:
        arrow_type: A ``pyarrow.DataType``.

    Returns:
        A DuckDB type name.
    """
    import pyarrow.types as _pyarrow_types

    # The shipped pyarrow stubs leave the ``is_*`` predicates partially
    # unknown; the explicit ``Any`` keeps this seam warning-free.
    pat = cast("Any", _pyarrow_types)
    if pat.is_boolean(arrow_type):
        return "BOOLEAN"
    if pat.is_integer(arrow_type):
        return "BIGINT"
    if pat.is_floating(arrow_type):
        return "DOUBLE"
    if pat.is_decimal(arrow_type):
        return "DECIMAL"
    if pat.is_timestamp(arrow_type):
        return "TIMESTAMP"
    if pat.is_date(arrow_type):
        return "DATE"
    return "VARCHAR"


def _last_write_at(storage_location: str) -> datetime.datetime | None:
    """Return the wall-clock of the most recent commit on a Delta table.

    Reads ``DeltaTable.history(limit=1)``; returns ``None`` when the
    table is unreadable or the timestamp cannot be parsed, which the
    freshness rule treats as "no observation" (no false alerts on an
    unreachable storage backend).

    Args:
        storage_location: Filesystem path or URI of the Delta table.

    Returns:
        The last commit's timestamp, or ``None``.
    """
    try:
        import deltalake

        history = deltalake.DeltaTable(storage_location).history(limit=1)
    except Exception:  # noqa: BLE001 — Delta absent / permission / corrupt
        # bare-broad-ok: freshness observation is best-effort; an
        # unreadable history degrades to "no observation".
        return None
    if not history:
        return None
    raw = history[0].get("timestamp")
    if isinstance(raw, int | float):
        try:
            return datetime.datetime.fromtimestamp(raw / 1000.0, tz=datetime.UTC)
        except OverflowError, OSError, ValueError:
            return None
    if isinstance(raw, str):
        try:
            return datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _profile_table(
    table_fqn: str, storage_location: str
) -> tuple[int | None, int, dict[str, dict[str, Any]]]:
    """Profile one Delta table into snapshot-shaped metrics.

    Args:
        table_fqn: The table's three-part name (used as the DuckDB
            view identifier).
        storage_location: Filesystem path or URI of the Delta table.

    Returns:
        ``(delta_version, row_count, column_metrics)`` where
        ``column_metrics`` maps every column name to its
        ``null_count`` / ``distinct_count`` / ``min`` / ``max`` /
        ``mean`` dict (values ``None`` when that column's profile
        failed).
    """
    import deltalake

    table = deltalake.DeltaTable(storage_location)
    version = int(table.version())
    # ``to_pyarrow_dataset`` is partially unknown in the deltalake
    # stubs; the explicit ``Any`` cast keeps this seam warning-free.
    schema = cast("Any", table.to_pyarrow_dataset()).schema  # pyright: ignore[reportUnknownMemberType]
    columns: list[dict[str, str]] = [
        {"name": str(name), "type": _duckdb_type(schema.field(name).type)} for name in schema.names
    ]
    stats = compute_stats(table_fqn, storage_location, columns)
    row_count = 0
    column_metrics: dict[str, dict[str, Any]] = {}
    for name, column_stats in stats.items():
        row_count = max(row_count, int(column_stats.get("count") or 0))
        column_metrics[name] = {key: column_stats.get(key) for key in _METRIC_KEYS}
    return version, row_count, column_metrics


def _null_fraction(metrics: dict[str, Any], row_count: int) -> float | None:
    """Return a column's null fraction, or ``None`` when undefined.

    Args:
        metrics: One column's metric dict.
        row_count: The snapshot's row count.

    Returns:
        ``null_count / row_count``, or ``None`` when the count is
        missing or the table was empty.
    """
    null_count = metrics.get("null_count")
    if null_count is None or row_count <= 0:
        return None
    return float(null_count) / float(row_count)


def _volume_anomaly(table_fqn: str, previous_rows: int, current_rows: int) -> dict[str, Any] | None:
    """Evaluate the volume-drop rule for one table.

    Args:
        table_fqn: The table under scan.
        previous_rows: The previous snapshot's row count.
        current_rows: The fresh snapshot's row count.

    Returns:
        A firing-anomaly dict, or ``None``.
    """
    if previous_rows < VOLUME_DROP_MIN_PREVIOUS_ROWS:
        return None
    ratio = current_rows / previous_rows
    if ratio >= VOLUME_DROP_WARN_RATIO:
        return None
    severity = "critical" if ratio < VOLUME_DROP_CRITICAL_RATIO else "warn"
    return {
        "table_fqn": table_fqn,
        "column_name": None,
        "kind": "volume_drop",
        "severity": severity,
        "observed": f"{current_rows} rows",
        "expected": f"at least {int(previous_rows * VOLUME_DROP_WARN_RATIO)} rows "
        f"(80% of previous {previous_rows})",
        "detail": f"row count fell to {ratio:.0%} of the previous snapshot",
    }


def _null_spike_anomalies(
    table_fqn: str,
    previous: TableProfileSnapshot,
    current_rows: int,
    current_metrics: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Evaluate the null-spike rule per column shared with the predecessor.

    Args:
        table_fqn: The table under scan.
        previous: The previous snapshot row.
        current_rows: The fresh snapshot's row count.
        current_metrics: The fresh snapshot's column metrics.

    Returns:
        Firing-anomaly dicts (possibly empty).
    """
    firing: list[dict[str, Any]] = []
    previous_metrics: dict[str, dict[str, Any]] = json.loads(previous.column_metrics or "{}")
    for column, metrics in current_metrics.items():
        prior = previous_metrics.get(column)
        if prior is None:
            continue
        previous_fraction = _null_fraction(prior, previous.row_count)
        current_fraction = _null_fraction(metrics, current_rows)
        if previous_fraction is None or current_fraction is None:
            continue
        delta = current_fraction - previous_fraction
        if delta <= NULL_SPIKE_WARN_DELTA:
            continue
        severity = "critical" if delta > NULL_SPIKE_CRITICAL_DELTA else "warn"
        firing.append(
            {
                "table_fqn": table_fqn,
                "column_name": column,
                "kind": "null_spike",
                "severity": severity,
                "observed": f"null fraction {current_fraction:.2f}",
                "expected": f"at most {previous_fraction + NULL_SPIKE_WARN_DELTA:.2f} "
                f"(previous {previous_fraction:.2f} + {NULL_SPIKE_WARN_DELTA})",
                "detail": f"null fraction rose by {delta:.2f} absolute",
            }
        )
    return firing


def _schema_change_anomaly(
    table_fqn: str,
    previous: TableProfileSnapshot,
    current_metrics: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Evaluate the schema-change rule for one table.

    Args:
        table_fqn: The table under scan.
        previous: The previous snapshot row.
        current_metrics: The fresh snapshot's column metrics.

    Returns:
        A firing-anomaly dict, or ``None``.
    """
    previous_metrics: dict[str, dict[str, Any]] = json.loads(previous.column_metrics or "{}")
    previous_columns = set(previous_metrics)
    current_columns = set(current_metrics)
    if previous_columns == current_columns:
        return None
    added = sorted(current_columns - previous_columns)
    removed = sorted(previous_columns - current_columns)
    parts: list[str] = []
    if added:
        parts.append("added: " + ", ".join(added))
    if removed:
        parts.append("removed: " + ", ".join(removed))
    return {
        "table_fqn": table_fqn,
        "column_name": None,
        "kind": "schema_change",
        "severity": "warn",
        "observed": f"{len(current_columns)} columns",
        "expected": f"{len(previous_columns)} columns",
        "detail": "; ".join(parts),
    }


def _freshness_anomaly(
    table_fqn: str, storage_location: str, now: datetime.datetime
) -> dict[str, Any] | None:
    """Evaluate the freshness rule for one table.

    Args:
        table_fqn: The table under scan.
        storage_location: Filesystem path or URI of the Delta table.
        now: The scan's wall-clock.

    Returns:
        A firing-anomaly dict, or ``None``.
    """
    last_write = _last_write_at(storage_location)
    if last_write is None:
        return None
    age = now - last_write
    if age <= datetime.timedelta(hours=FRESHNESS_MAX_AGE_HOURS):
        return None
    return {
        "table_fqn": table_fqn,
        "column_name": None,
        "kind": "freshness",
        "severity": "warn",
        "observed": f"last write {last_write.isoformat()}",
        "expected": f"a write within the last {FRESHNESS_MAX_AGE_HOURS}h",
        "detail": f"table is {age.total_seconds() / 3600.0:.1f}h stale",
    }


def _apply_anomalies(
    session: Session,
    *,
    monitor_id: int,
    table_fqn: str,
    firing: list[dict[str, Any]],
    now: datetime.datetime,
) -> tuple[list[QualityAnomaly], int]:
    """Reconcile firing rules against the table's open anomalies.

    A firing rule whose ``(column, kind)`` identity already has an
    open anomaly is skipped (no duplicates); an open anomaly whose
    rule stopped firing gets ``resolved_at`` stamped.

    Args:
        session: Active SQLAlchemy session (caller commits).
        monitor_id: Owning monitor.
        table_fqn: The table just scanned.
        firing: Firing-anomaly dicts from the rule evaluation.
        now: The scan's wall-clock.

    Returns:
        ``(newly inserted rows, resolved count)``.
    """
    open_rows = list(
        session.scalars(
            select(QualityAnomaly).where(
                QualityAnomaly.monitor_id == monitor_id,
                QualityAnomaly.table_fqn == table_fqn,
                QualityAnomaly.resolved_at.is_(None),
            )
        )
    )
    firing_keys = {(item["column_name"], item["kind"]) for item in firing}
    resolved = 0
    for row in open_rows:
        if (row.column_name, row.kind) not in firing_keys:
            row.resolved_at = now
            resolved += 1
    open_keys = {(row.column_name, row.kind) for row in open_rows}
    created: list[QualityAnomaly] = []
    for item in firing:
        if (item["column_name"], item["kind"]) in open_keys:
            continue
        anomaly = QualityAnomaly(
            monitor_id=monitor_id,
            table_fqn=table_fqn,
            column_name=item["column_name"],
            kind=item["kind"],
            severity=item["severity"],
            observed=item["observed"],
            expected=item["expected"],
            detail=item["detail"],
            detected_at=now,
        )
        session.add(anomaly)
        created.append(anomaly)
    return created, resolved


def scan_monitor_sync(
    factory: sessionmaker[Session],
    *,
    monitor_id: int,
    tables: dict[str, str],
) -> dict[str, Any]:
    """Scan every table of one monitor and persist snapshots + anomalies.

    Tables that cannot be profiled (storage gone, corrupt log) are
    skipped — the scan is an observation pass and one broken table
    must not block the rest of the schema.

    Args:
        factory: SQLAlchemy session factory.
        monitor_id: The monitor being scanned.
        tables: Mapping ``table FQN → storage location`` resolved by
            the executor through Unity Catalog.

    Returns:
        Summary dict with ``tables_scanned``, ``tables_skipped``
        (FQNs), ``new_anomalies`` (serialised), and
        ``resolved_count``.
    """
    now = datetime.datetime.now(datetime.UTC)
    scanned = 0
    skipped: list[str] = []
    new_anomalies: list[dict[str, Any]] = []
    resolved_count = 0
    for table_fqn, storage_location in sorted(tables.items()):
        try:
            delta_version, row_count, column_metrics = _profile_table(table_fqn, storage_location)
        except Exception:  # noqa: BLE001 — per-table isolation
            logger.exception(
                "quality monitor %s: profiling %s failed; skipping",
                monitor_id,
                table_fqn,
            )
            skipped.append(table_fqn)
            continue
        with factory() as session:
            previous = session.scalar(
                select(TableProfileSnapshot)
                .where(
                    TableProfileSnapshot.monitor_id == monitor_id,
                    TableProfileSnapshot.table_fqn == table_fqn,
                )
                .order_by(desc(TableProfileSnapshot.captured_at), desc(TableProfileSnapshot.id))
                .limit(1)
            )
            session.add(
                TableProfileSnapshot(
                    monitor_id=monitor_id,
                    table_fqn=table_fqn,
                    delta_version=delta_version,
                    row_count=row_count,
                    column_metrics=json.dumps(column_metrics, default=str),
                    captured_at=now,
                )
            )
            firing: list[dict[str, Any]] = []
            if previous is not None:
                volume = _volume_anomaly(table_fqn, previous.row_count, row_count)
                if volume is not None:
                    firing.append(volume)
                firing.extend(_null_spike_anomalies(table_fqn, previous, row_count, column_metrics))
                schema_change = _schema_change_anomaly(table_fqn, previous, column_metrics)
                if schema_change is not None:
                    firing.append(schema_change)
            freshness = _freshness_anomaly(table_fqn, storage_location, now)
            if freshness is not None:
                firing.append(freshness)
            created, resolved = _apply_anomalies(
                session,
                monitor_id=monitor_id,
                table_fqn=table_fqn,
                firing=firing,
                now=now,
            )
            session.flush()
            new_anomalies.extend(serialize_anomaly(row) for row in created)
            resolved_count += resolved
            session.commit()
        scanned += 1
    return {
        "monitor_id": monitor_id,
        "tables_scanned": scanned,
        "tables_skipped": skipped,
        "new_anomalies": new_anomalies,
        "resolved_count": resolved_count,
    }
