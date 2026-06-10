"""Scheduler-driven pump for one event subscription.

Each tick:

1. Look up the durable subscription row.
2. Skip when it isn't ``active``.
3. Resolve the Delta storage location for the source table.
4. Read CDF rows from ``position.version`` up to a bounded window.
5. Broadcast each row to the in-memory hub.
6. Advance the cursor + record a delivery ledger row.

The scheduler executor wraps this per subscription so transient
failures on one stream don't stall the others.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from pointlessql.models import DataProduct, DataProductEventSubscription
from pointlessql.services.event_port import _ws_hub
from pointlessql.services.event_port._cdf_reader import ChangeRow, read_changes
from pointlessql.services.event_port._subscription_crud import (
    advance_position,
    record_delivery,
)
from pointlessql.types import SessionFactory

_LOG = logging.getLogger(__name__)


ReaderFn = Callable[[str, int, int], list[ChangeRow]]


def _default_reader(location: str, since_version: int, max_versions: int) -> list[ChangeRow]:
    """Bridge :func:`read_changes` into the :data:`ReaderFn` signature."""
    return read_changes(location, since_version=since_version, max_versions=max_versions)


def _resolve_location(factory: SessionFactory, *, subscription: dict[str, Any]) -> str | None:
    """Look up the Delta storage location for the subscription's source.

    Returns ``None`` when the parent product or the storage location
    can't be resolved — the pump treats this as a soft skip.
    """
    with factory() as session:
        product = session.get(DataProduct, subscription["data_product_id"])
        if product is None:
            return None
        catalog = product.catalog_name
        schema = product.schema_name
        del session
    table = subscription["table_name"]
    full = f"{catalog}.{schema}.{table}"
    try:
        # Background-job context — no per-request principal exists, so the
        # generated client is the practical surface for a storage-location
        # lookup that never returns row data.
        from soyuz_catalog_client.api.tables import (  # noqa: TID251 — see comment above
            get_table_api_2_1_unity_catalog_tables_full_name_get as _get_table,
        )

        from pointlessql.config import get_settings
        from pointlessql.services.soyuz_client import make_soyuz_client

        client = make_soyuz_client(get_settings())
        info = _get_table.sync(client=client, full_name=full)
    # bare-broad-ok: unknown table is a soft skip; pump must not raise
    except Exception:  # noqa: BLE001
        _LOG.debug("event_port pump: cannot resolve location for %s", full)
        return None
    if info is None:
        return None
    storage = getattr(info, "storage_location", None)
    if not storage:
        return None
    return str(storage)


async def pump_subscription(
    factory: SessionFactory,
    *,
    subscription_id: int,
    max_versions: int,
    reader: ReaderFn | None = None,
) -> dict[str, Any]:
    """Pump one subscription forward by at most *max_versions* commits.

    Args:
        factory: Sessionmaker callable.
        subscription_id: Subscription PK to pump.
        max_versions: Cap on commit versions read in one tick.
        reader: Override CDF reader (test seam).  Defaults to
            :func:`read_changes` against the resolved Delta location.

    Returns:
        Summary dict with ``status`` (``ok``/``empty``/``skipped``/
        ``error``), ``row_count``, ``version_from``, ``version_to``.
    """
    use_reader: ReaderFn = reader if reader is not None else _default_reader
    with factory() as session:
        row = session.get(DataProductEventSubscription, subscription_id)
        if row is None:
            return {"status": "skipped", "reason": "subscription not found"}
        if row.status != "active":
            return {"status": "skipped", "reason": f"status={row.status!r}"}
        subscription = {
            "id": row.id,
            "data_product_id": row.data_product_id,
            "output_port_id": row.output_port_id,
            "table_name": row.table_name,
            "consumer_label": row.consumer_label,
            "position_marker_json": row.position_marker_json,
        }
    from pointlessql.services.event_port._subscription_crud import decode_position

    position = decode_position(subscription["position_marker_json"])
    since = int(position["version"])

    if reader is None:
        location = _resolve_location(factory, subscription=subscription)
        if location is None:
            return {
                "status": "skipped",
                "reason": "location unresolved",
                "version_from": since,
                "version_to": since,
                "row_count": 0,
            }
    else:
        location = ""

    rows = await asyncio.to_thread(use_reader, location, since, max_versions)
    if not rows:
        record_delivery(
            factory,
            subscription_id=subscription_id,
            version_from=since,
            version_to=since,
            row_count=0,
            status="empty",
        )
        return {
            "status": "empty",
            "version_from": since,
            "version_to": since,
            "row_count": 0,
        }

    # Broadcast.
    product_full = await _product_full_name(factory, subscription["data_product_id"])
    if product_full is not None:
        hub = await _ws_hub.get_or_create_hub(product_full, subscription["table_name"])
        for change in rows:
            await _ws_hub.broadcast(
                hub,
                {
                    "subscription_id": subscription_id,
                    "version": change.version,
                    "commit_timestamp": change.commit_timestamp,
                    "change_type": change.change_type,
                    "data": change.data,
                },
            )

    last_version = max(row.version for row in rows)
    advance_position(
        factory,
        subscription_id=subscription_id,
        to_version=last_version + 1,
        row_offset=0,
    )
    record_delivery(
        factory,
        subscription_id=subscription_id,
        version_from=since,
        version_to=last_version + 1,
        row_count=len(rows),
        status="ok",
    )
    return {
        "status": "ok",
        "version_from": since,
        "version_to": last_version + 1,
        "row_count": len(rows),
    }


async def _product_full_name(factory: SessionFactory, data_product_id: int) -> str | None:
    """Return ``catalog.schema`` of the data product, or ``None``."""
    with factory() as session:
        product = session.get(DataProduct, data_product_id)
        if product is None:
            return None
        return f"{product.catalog_name}.{product.schema_name}"


async def pump_all_active(
    factory: SessionFactory,
    *,
    max_versions: int,
    reader: ReaderFn | None = None,
) -> dict[str, Any]:
    """Pump every active subscription once.  Used by the scheduler executor."""
    from sqlalchemy import select

    with factory() as session:
        ids = [
            row.id
            for row in session.scalars(
                select(DataProductEventSubscription).where(
                    DataProductEventSubscription.status == "active"
                )
            ).all()
        ]

    summary = {"pumped": 0, "ok": 0, "empty": 0, "skipped": 0, "errors": 0}
    for sid in ids:
        summary["pumped"] += 1
        try:
            result = await pump_subscription(
                factory,
                subscription_id=sid,
                max_versions=max_versions,
                reader=reader,
            )
        except Exception:  # noqa: BLE001 — one stream's failure must not stop others
            summary["errors"] += 1
            _LOG.exception("event_port pump: subscription %s failed", sid)
            continue
        status = result.get("status")
        if status == "ok":
            summary["ok"] += 1
        elif status == "empty":
            summary["empty"] += 1
        else:
            summary["skipped"] += 1
    return summary


_PumpFuture = Callable[[], Awaitable[None]]
