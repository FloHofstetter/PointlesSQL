"""Periodic scanner: emit ``sla_violated`` events for stale products.

For every cached :class:`DataProduct` row whose ``sla_minutes`` is
set, the scanner walks the product's UC tables, finds the most-
recent write timestamp via ``DeltaTable.history()``, and compares
the age against ``sla_minutes``.  If stale, one
``pointlessql.data_product.sla_violated`` CloudEvent fires; the
row's ``last_alerted_at`` is stamped to suppress re-alerts within
the configured suppression window (default 60 minutes).

Pattern mirrors :mod:`pointlessql.services.external_write_scanner`:
opt-in via ``POINTLESSQL_DATA_PRODUCTS_SCAN_INTERVAL_SECONDS`` (≥60
to enable; default 0 = dormant) and ``scan_all`` is the one entry
point the periodic loop calls per tick.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING

from sqlalchemy import select

from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_DATA_PRODUCT_SLA_VIOLATED,
    emit_governance_event,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

    from pointlessql.services.unitycatalog import UnityCatalogClient

logger = logging.getLogger(__name__)

DEFAULT_RE_ALERT_SUPPRESS_MINUTES = 60


def _latest_write_for_table(storage_location: str) -> datetime.datetime | None:
    """Return the wall-clock of the most recent commit on a Delta table.

    Reads ``DeltaTable.history(limit=1)``; returns ``None`` when the
    table is unreadable / empty / has an unparseable timestamp.  The
    scanner treats ``None`` as "no observation" — products whose
    every table reads ``None`` are skipped (no false-positive alerts
    just because the storage backend is unreachable).
    """
    try:
        import deltalake

        table = deltalake.DeltaTable(storage_location)
        history = table.history(limit=1)
    except Exception:  # noqa: BLE001 — Delta absent / permission / corrupt
        # bare-broad-ok: scanner observation is best-effort; an
        # unreadable table degrades to "no observation" so the
        # caller skips this product rather than alerting falsely.
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


async def _resolve_storage_locations(
    uc: UnityCatalogClient,
    catalog: str,
    schema: str,
) -> list[str]:
    """Return the storage locations of every UC table in the schema.

    Tables without a ``storage_location`` (views, foreign tables) are
    skipped; the scanner can't observe their freshness through the
    Delta-history shortcut.
    """
    try:
        tables = await uc.list_tables(catalog, schema)
    except Exception:  # noqa: BLE001 — skip per-schema failures
        logger.exception(
            "data_product_freshness: list_tables failed for %s.%s",
            catalog,
            schema,
        )
        return []
    locations: list[str] = []
    for table in tables:
        if not isinstance(table, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
            continue
        storage = table.get("storage_location")
        if isinstance(storage, str) and storage:
            locations.append(storage)
    return locations


async def scan_all(
    factory: sessionmaker[Session],
    uc: UnityCatalogClient,
    *,
    now: datetime.datetime | None = None,
    re_alert_suppress_minutes: int = DEFAULT_RE_ALERT_SUPPRESS_MINUTES,
) -> int:
    """Walk every SLA-bearing product and emit alerts when stale.

    Args:
        factory: SQLAlchemy session factory.
        uc: ``UnityCatalogClient`` used to enumerate the tables of
            each product.
        now: Override for the wall-clock comparison anchor (testing
            hook).  ``None`` uses ``datetime.now(UTC)``.
        re_alert_suppress_minutes: Minimum gap between alerts on the
            same product.  When the row's ``last_alerted_at`` is
            within this window, the scanner skips the alert (the
            CloudEvent storm is the failure mode we want to avoid).

    Returns:
        Number of alerts emitted in this tick.
    """
    import asyncio

    timestamp = now or datetime.datetime.now(datetime.UTC)
    alerts_emitted = 0

    with factory() as session:
        rows = (
            session.execute(select(DataProduct).where(DataProduct.sla_minutes.is_not(None)))
            .scalars()
            .all()
        )
        product_specs = [
            (
                row.id,
                row.workspace_id,
                row.catalog_name,
                row.schema_name,
                row.version,
                row.sla_minutes,
                row.last_alerted_at,
            )
            for row in rows
        ]

    for (
        product_id,
        workspace_id,
        catalog,
        schema,
        version,
        sla_minutes,
        last_alerted_at,
    ) in product_specs:
        if sla_minutes is None:
            continue

        if last_alerted_at is not None:
            # SQLite stores naive UTC; Postgres stores tz-aware.  Normalise
            # to UTC-aware so the subtraction below works on both backends.
            if last_alerted_at.tzinfo is None:
                last_alerted_at = last_alerted_at.replace(tzinfo=datetime.UTC)
            age_alert = timestamp - last_alerted_at
            if age_alert < datetime.timedelta(minutes=re_alert_suppress_minutes):
                continue

        locations = await _resolve_storage_locations(uc, catalog, schema)
        latest = None
        for location in locations:
            ts = await asyncio.to_thread(_latest_write_for_table, location)
            if ts is None:
                continue
            if latest is None or ts > latest:
                latest = ts

        if latest is None:
            # No observable history; treat as "scanner can't decide"
            # and skip rather than alert spuriously.
            continue

        age = timestamp - latest
        if age <= datetime.timedelta(minutes=sla_minutes):
            continue

        payload = {
            "workspace_id": workspace_id,
            "catalog": catalog,
            "schema": schema,
            "version": version,
            "sla_minutes": sla_minutes,
            "last_write_at_iso": latest.isoformat(),
            "age_minutes": int(age.total_seconds() // 60),
        }
        try:
            await emit_governance_event(
                EVENT_TYPE_DATA_PRODUCT_SLA_VIOLATED,
                payload,
                fired_at=timestamp,
                session_factory=factory,
                workspace_id=workspace_id,
            )
        except Exception:  # noqa: BLE001 — emit must never raise
            logger.exception(
                "data_product_freshness: emit failed for product_id=%s",
                product_id,
            )
            continue

        with factory() as session:
            row = session.get(DataProduct, product_id)
            if row is not None:
                row.last_alerted_at = timestamp
                session.commit()

        alerts_emitted += 1

    return alerts_emitted
