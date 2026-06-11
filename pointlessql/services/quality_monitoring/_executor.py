"""Scheduler executor for the ``"quality_monitor"`` job kind."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pointlessql.exceptions import CatalogNotFoundError, ValidationError
from pointlessql.models.quality_monitoring import QualityMonitor
from pointlessql.services.quality_monitoring._engine import scan_monitor_sync
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)


async def _resolve_tables(uc_client: UnityCatalogClient, target: str) -> dict[str, str]:
    """Resolve a monitor target to ``{table FQN → storage location}``.

    A three-part target resolves to exactly one table; a two-part
    target lists the schema and keeps every table that exposes a
    ``storage_location`` (views and foreign tables cannot be profiled
    through the Delta shortcut and are skipped).

    Args:
        uc_client: Principal-forwarded Unity Catalog facade.
        target: ``cat.sch.tbl`` or ``cat.sch``.

    Returns:
        Mapping of resolvable tables (possibly empty for a schema
        target with no Delta tables).

    Raises:
        CatalogNotFoundError: When a table target is unknown or has
            no storage location.
        ValidationError: When the stored target is malformed.
    """
    parts = target.split(".")
    if len(parts) == 3:
        info = await uc_client.get_table(parts[0], parts[1], parts[2])
        if not info:
            raise CatalogNotFoundError(f"Table not found: {target!r}")
        storage = info.get("storage_location")
        if not isinstance(storage, str) or not storage:
            raise CatalogNotFoundError(f"Table {target!r} has no storage_location.")
        return {target: storage}
    if len(parts) == 2:
        tables: dict[str, str] = {}
        for info in await uc_client.list_tables(parts[0], parts[1]):
            name = info.get("name")
            storage = info.get("storage_location")
            if isinstance(name, str) and name and isinstance(storage, str) and storage:
                tables[f"{parts[0]}.{parts[1]}.{name}"] = storage
        return tables
    raise ValidationError(f"monitor target must have 2 or 3 parts, got {target!r}")


def _notify_anomalies(
    factory: Any,
    monitor: QualityMonitor,
    anomalies: list[dict[str, Any]],
) -> None:
    """Fan new anomalies out to the monitor's creator, one event per table.

    Best-effort — a notification failure never fails the scan run.

    Args:
        factory: SQLAlchemy session factory.
        monitor: The (detached) monitor that was scanned.
        anomalies: Serialised anomaly dicts fresh from the scan.
    """
    from pointlessql.services.notifications.fanout import fanout_event

    by_table: dict[str, list[dict[str, Any]]] = {}
    for anomaly in anomalies:
        by_table.setdefault(str(anomaly["table_fqn"]), []).append(anomaly)
    for table_fqn, items in sorted(by_table.items()):
        lines = ", ".join(
            f"{item['kind']} ({item['severity']}): {item['observed']}" for item in items
        )
        summary_md = f"Quality monitor found {len(items)} anomalies on `{table_fqn}` — {lines}"
        try:
            fanout_event(
                factory,
                event_type="pointlessql.quality.anomaly_detected",
                entity_kind="table",
                entity_ref=table_fqn,
                workspace_id=monitor.workspace_id,
                actor_user_id=None,
                source_url="/quality",
                summary_md=summary_md,
                extra_recipients=[monitor.created_by_user_id],
            )
        except Exception:  # noqa: BLE001 — fanout is best-effort
            logger.exception(
                "quality monitor %s: anomaly fanout failed for %s",
                monitor.id,
                table_fqn,
            )


async def quality_monitor_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Run one quality scan from the scheduler (as the job's run-as user).

    Resolves the monitor's target through Unity Catalog (one table
    for an FQN target, the whole schema for a prefix target),
    dispatches the synchronous scan engine in a worker thread, and
    fans freshly detected anomalies out to the monitor's creator.

    Args:
        job_run_id: Current ``JobRun.id`` (unused — snapshots and
            anomalies carry their own history).
        user_info: The run-as user (unused — the scan is a metadata
            observation; UC reads happen through *uc_client* which
            is already principal-bound).
        config: Must carry ``monitor_id``.
        uc_client: Principal-forwarded facade for the target
            resolution hops.

    A table target that cannot be resolved bubbles the
    ``CatalogNotFoundError`` raised by the target-resolution helper.

    Raises:
        ValidationError: When ``monitor_id`` is missing / unknown.
    """
    del job_run_id, user_info
    from pointlessql.db import get_session_factory

    monitor_id = config.get("monitor_id")
    if not isinstance(monitor_id, int):
        raise ValidationError("quality_monitor jobs need an integer monitor_id in config")
    factory = get_session_factory()
    with factory() as session:
        monitor = session.get(QualityMonitor, monitor_id)
        if monitor is None:
            raise ValidationError(f"quality monitor id={monitor_id} not found")
        session.expunge(monitor)

    tables = await _resolve_tables(uc_client, monitor.target)
    if not tables:
        logger.info(
            "quality monitor %s: target %s resolved to no profileable tables",
            monitor_id,
            monitor.target,
        )
        return
    result = await asyncio.to_thread(
        scan_monitor_sync,
        factory,
        monitor_id=monitor_id,
        tables=tables,
    )
    new_anomalies = list(result.get("new_anomalies") or [])
    if new_anomalies:
        await asyncio.to_thread(_notify_anomalies, factory, monitor, new_anomalies)
