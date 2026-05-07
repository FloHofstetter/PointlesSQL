"""Worker-side service for the Phase 40.5 CDF tail subscriptions.

Counterpart to :mod:`pointlessql.services.external_write_scanner`: where
the external-writes scanner walks ``DeltaTable.history()`` and flags
*unattributed* commits, the CDF tail walks ``DeltaTable.load_cdf()``
on a *subscribed* foreign table and INSERT-OR-IGNOREs every CDF row
into :class:`CdfTailEvent`.

Two public entry points:

* :func:`tail_subscription` — sync, scoped to one
  :class:`CdfTailSubscription`.  Pure helper around
  ``deltalake.DeltaTable.load_cdf``; used by the periodic worker
  loop and by tests directly.
* :func:`tail_all` — async wrapper that walks every active
  subscription (per workspace).  Reuses :func:`tail_subscription`
  via ``asyncio.to_thread``.

The worker is **opt-in per table** — there's no implicit
auto-discovery — and it reuses whatever credentials soyuz's
``storage_location`` already exposes.  Tables behind cloud
credentials we don't have stay un-tail-able and the worker logs
a warning rather than failing the whole tick.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from pointlessql.models import CdfTailEvent, CdfTailSubscription

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

    from pointlessql.services.unitycatalog import UnityCatalogClient

logger = logging.getLogger(__name__)

DEFAULT_HISTORY_LIMIT = 200

CDF_META_CHANGE_TYPE = "_change_type"
CDF_META_VERSION = "_commit_version"
CDF_META_TIMESTAMP = "_commit_timestamp"

VALID_CHANGE_TYPES = frozenset(
    {"insert", "update_preimage", "update_postimage", "delete"}
)


def fetch_events_for_row(
    session_factory: sessionmaker[Session],
    *,
    workspace_id: int,
    table_full_name: str,
    row_id: str,
    limit: int = 50,
) -> list[CdfTailEvent]:
    """Return captured CDF events for one ``(table, row_id)`` pair.

    Used by the row-trace UI to fold CDF captures into the existing
    walkback steps as contextual metadata, alongside the
    ``lineage_value_changes`` per-cell history.  Workspace-scoped so
    two installs that happen to share a row identifier never see
    each other's events.

    Args:
        session_factory: SQLAlchemy session factory.
        workspace_id: Active workspace; only events captured for this
            workspace are returned.
        table_full_name: Three-part UC name; matched verbatim against
            :attr:`CdfTailEvent.table_full_name`.
        row_id: Stringified row identifier (the value the
            subscription's ``row_id_column`` produced at capture).
        limit: Defensive bound on the per-row event count.  Defaults
            to 50 so a runaway producer can't blow up the row-trace
            page.

    Returns:
        Matching events ordered ``(delta_version, created_at)``
        ascending so the row-trace pane renders insert→update→delete
        in commit order.  Empty list when no events match.
    """
    with session_factory() as session:
        stmt = (
            select(CdfTailEvent)
            .where(
                CdfTailEvent.workspace_id == workspace_id,
                CdfTailEvent.table_full_name == table_full_name,
                CdfTailEvent.row_id == row_id,
            )
            .order_by(
                CdfTailEvent.delta_version.asc(),
                CdfTailEvent.created_at.asc(),
            )
            .limit(limit)
        )
        return list(session.scalars(stmt))


def _coerce_timestamp(value: Any) -> datetime.datetime | None:
    """Parse a Delta CDF ``_commit_timestamp`` cell into UTC.

    Delta returns commit timestamps as either pyarrow timestamp
    objects (decoded by ``to_pydict()`` to ``datetime.datetime``)
    or epoch milliseconds (older Python deltalake bindings).  Tolerate
    both shapes; an unrecognised value just becomes ``None``.

    Args:
        value: One pyarrow-decoded cell value.

    Returns:
        Timezone-aware UTC ``datetime`` or ``None``.
    """
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=datetime.UTC)
        return value
    if isinstance(value, int | float):
        try:
            return datetime.datetime.fromtimestamp(value / 1000.0, tz=datetime.UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _read_cdf_rows(
    storage_location: str,
    *,
    starting_version: int,
    history_limit: int,
) -> list[dict[str, Any]]:
    """Read CDF rows from one Delta table.

    Caps the per-tick read at ``starting_version + history_limit``
    so a long-idle subscription doesn't spike memory on its first
    catch-up tick.

    Args:
        storage_location: Filesystem path or URI of the Delta table.
        starting_version: First Delta version to read (inclusive).
        history_limit: Max commit-version range to walk in one
            tick.  Bounds the per-call cost.

    Returns:
        One dict per CDF row with ``_change_type`` /
        ``_commit_version`` / ``_commit_timestamp`` plus all the
        table's column values.  Empty when CDF is unavailable, the
        range is empty, or anything reading-side raised.
    """
    try:
        import deltalake
        import pyarrow as pa
    except ImportError:
        logger.warning("cdf_tail: deltalake/pyarrow not installed; skipping read")
        return []

    try:
        dt = deltalake.DeltaTable(storage_location)
    except Exception as exc:  # noqa: BLE001 — Delta absent / permission denied / corrupt
        logger.warning(
            "cdf_tail: could not open Delta table at %r: %s",
            storage_location,
            exc,
        )
        return []

    try:
        latest_version = int(dt.version())
    except Exception as exc:  # noqa: BLE001 — Delta runtime error
        logger.warning("cdf_tail: dt.version() failed for %r: %s", storage_location, exc)
        return []

    if latest_version < starting_version:
        return []

    ending_version = min(latest_version, starting_version + max(1, history_limit) - 1)

    try:
        cdf_reader = dt.load_cdf(
            starting_version=starting_version,
            ending_version=ending_version,
        )
        cdf_arrow: pa.Table = pa.table(cdf_reader.read_all())  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
    except Exception as exc:  # noqa: BLE001 — CDF disabled / range invalid / read error
        logger.warning(
            "cdf_tail: load_cdf failed for %r [%d..%d]: %s",
            storage_location,
            starting_version,
            ending_version,
            exc,
        )
        return []

    num_rows = int(cdf_arrow.num_rows)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
    if num_rows == 0:
        return []

    schema_names: list[str] = list(cdf_arrow.schema.names)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
    columns: set[str] = set(schema_names)
    if CDF_META_CHANGE_TYPE not in columns or CDF_META_VERSION not in columns:
        logger.warning(
            "cdf_tail: missing CDF metadata columns at %r; got %s",
            storage_location,
            sorted(columns),
        )
        return []

    rows: list[dict[str, Any]] = list(
        cdf_arrow.to_pylist()  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
    )
    return rows


def tail_subscription(
    factory: sessionmaker[Session],
    sub_id: int,
    *,
    history_limit: int = DEFAULT_HISTORY_LIMIT,
    storage_location: str,
    now: datetime.datetime | None = None,
) -> int:
    """Tail one subscription, persisting new CDF events.

    Reads CDF rows in ``[last_version_processed + 1 ..
    last_version_processed + history_limit]`` (or
    ``[0 .. history_limit - 1]`` when the subscription is fresh)
    and INSERT-OR-IGNOREs them into ``cdf_tail_events``.  Advances
    ``last_version_processed`` to the highest version actually read.

    Idempotent on re-tail thanks to UNIQUE
    ``(table_full_name, delta_version, row_id, change_type)``.

    Args:
        factory: SQLAlchemy session factory.
        sub_id: Primary key of the :class:`CdfTailSubscription` to
            tail.  Looked up in a fresh session so the caller doesn't
            need to share ORM state.
        history_limit: Max commit-version range to read this tick.
        storage_location: Resolved Delta storage URI / path for the
            subscription's table.  Caller is responsible for the
            UC lookup so this helper stays sync-safe (no async UC
            client call from within ``asyncio.to_thread``).
        now: Override for the ``created_at`` / ``last_tailed_at``
            timestamp (testing hook).  ``None`` uses
            ``datetime.now(UTC)``.

    Returns:
        The number of newly-persisted ``cdf_tail_events`` rows.
        Empty re-tails return ``0``.
    """
    detected_at = now or datetime.datetime.now(datetime.UTC)
    with factory() as session:
        sub = session.get(CdfTailSubscription, sub_id)
        if sub is None or not sub.is_active:
            return 0
        starting_version = (sub.last_version_processed or -1) + 1

    rows = _read_cdf_rows(
        storage_location,
        starting_version=starting_version,
        history_limit=history_limit,
    )
    if not rows:
        with factory() as session:
            sub = session.get(CdfTailSubscription, sub_id)
            if sub is None:
                return 0
            sub.last_tailed_at = detected_at
            sub.last_error = None
            session.commit()
        return 0

    inserted = 0
    max_version_seen = starting_version - 1
    with factory() as session:
        sub = session.get(CdfTailSubscription, sub_id)
        if sub is None:
            return 0
        row_id_column = sub.row_id_column
        producer_label = sub.producer_label
        table_full_name = sub.table_full_name
        workspace_id = sub.workspace_id

        for entry in rows:
            change_type = entry.get(CDF_META_CHANGE_TYPE)
            version = entry.get(CDF_META_VERSION)
            if not isinstance(change_type, str) or change_type not in VALID_CHANGE_TYPES:
                continue
            if not isinstance(version, int):
                continue
            row_id_value = entry.get(row_id_column)
            if row_id_value is None:
                continue
            row_id = str(row_id_value)
            if not row_id:
                continue
            event = CdfTailEvent(
                workspace_id=workspace_id,
                subscription_id=sub_id,
                table_full_name=table_full_name,
                delta_version=version,
                row_id=row_id,
                change_type=change_type,
                producer_label=producer_label,
                commit_timestamp=_coerce_timestamp(entry.get(CDF_META_TIMESTAMP)),
                created_at=detected_at,
            )
            session.add(event)
            try:
                session.flush()
            except IntegrityError:
                # Re-tail of an already-captured row; UNIQUE makes
                # this safe and explicit.
                session.rollback()
                continue
            inserted += 1
            if version > max_version_seen:
                max_version_seen = version

        sub.last_tailed_at = detected_at
        sub.last_error = None
        if max_version_seen >= (sub.last_version_processed or -1) + 1:
            sub.last_version_processed = max_version_seen
        session.commit()
    return inserted


async def tail_all(
    factory: sessionmaker[Session],
    uc: UnityCatalogClient,
    *,
    history_limit: int = DEFAULT_HISTORY_LIMIT,
) -> int:
    """Walk every active subscription and tail each one.

    Per-subscription failures (UC lookup error, Delta read error,
    DB transient) are logged and the loop continues — one bad
    subscription should not block the rest.  The error message is
    persisted on the subscription's ``last_error`` so admins can
    diagnose without scraping the application log.

    Args:
        factory: SQLAlchemy session factory.
        uc: Async UC facade used to resolve each subscription's
            ``storage_location`` per tick.
        history_limit: Forwarded to :func:`tail_subscription`.

    Returns:
        Sum of newly-persisted ``cdf_tail_events`` rows across
        every subscription.
    """
    import asyncio

    total = 0
    with factory() as session:
        active_ids = list(
            session.scalars(
                select(CdfTailSubscription.id).where(
                    CdfTailSubscription.is_active.is_(True)
                )
            ).all()
        )

    for sub_id in active_ids:
        with factory() as session:
            sub = session.get(CdfTailSubscription, sub_id)
            if sub is None or not sub.is_active:
                continue
            table_full_name = sub.table_full_name

        parts = table_full_name.split(".")
        if len(parts) != 3:
            _stamp_error(factory, sub_id, f"invalid three-part name: {table_full_name!r}")
            continue
        catalog, schema, table = parts
        try:
            table_info = await uc.get_table(catalog, schema, table)
        except Exception as exc:  # noqa: BLE001 — UC lookup is best-effort
            _stamp_error(factory, sub_id, f"uc.get_table failed: {exc}")
            continue
        storage_location = table_info.get("storage_location") if table_info else None
        if not isinstance(storage_location, str) or not storage_location:
            _stamp_error(factory, sub_id, "table has no storage_location")
            continue

        try:
            inserted = await asyncio.to_thread(
                tail_subscription,
                factory,
                sub_id,
                history_limit=history_limit,
                storage_location=storage_location,
            )
        except Exception as exc:  # noqa: BLE001 — never let one bad sub kill the loop
            logger.exception("cdf_tail: tail_subscription raised for sub_id=%s", sub_id)
            _stamp_error(factory, sub_id, f"tail_subscription raised: {exc}")
            continue
        total += inserted
    return total


def _stamp_error(
    factory: sessionmaker[Session],
    sub_id: int,
    message: str,
) -> None:
    """Persist a truncated error message onto a subscription row.

    Best-effort: a DB hiccup writing the error itself is logged but
    never propagated — the worker loop must survive.

    Args:
        factory: SQLAlchemy session factory.
        sub_id: Subscription primary key.
        message: Human-readable error string; truncated to fit the
            ``last_error`` VARCHAR(500) column.
    """
    try:
        with factory() as session:
            sub = session.get(CdfTailSubscription, sub_id)
            if sub is None:
                return
            sub.last_error = message[:500]
            sub.last_tailed_at = datetime.datetime.now(datetime.UTC)
            session.commit()
    except Exception:  # noqa: BLE001 — never let error-stamping break the loop
        logger.exception("cdf_tail: failed to stamp error onto sub_id=%s", sub_id)


__all__ = ["DEFAULT_HISTORY_LIMIT", "tail_all", "tail_subscription"]
