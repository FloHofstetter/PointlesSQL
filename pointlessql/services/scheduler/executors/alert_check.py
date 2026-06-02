# pyright: reportUnusedFunction=false
"""``alert_check`` job kind — evaluate a query alert and fan out dispatches."""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from typing import Any

from sqlalchemy import select

from pointlessql.exceptions import ValidationError
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo

logger = logging.getLogger(__name__)


async def _alert_check_executor(
    job_run_id: int,
    user_info: UserInfo,
    config: dict[str, Any],
    uc_client: UnityCatalogClient,
) -> None:
    """Evaluate a query alert's condition and dispatch events.

    Config shape:

    .. code-block:: json

        {"alert_id": 42}

    Runs the alert's saved query via :class:`~pointlessql.pql.pql.PQL`
    under the owner's UC identity (the scheduler already threaded
    ``uc_client`` with the right principal).  On condition match it
    records one :class:`~pointlessql.models.AlertEvent` row, then fans
    out dispatch for every enabled destination.  Webhook delivery
    failures flip the event's ``outcome`` to ``delivery_failed``
    without raising — the alert check itself is considered successful
    as long as the condition was evaluated.

    Args:
        job_run_id: Current run id (unused; the alert's own
            ``AlertEvent`` row carries the history).
        user_info: The run-as user's :class:`UserInfo`.
        config: Must carry ``alert_id``.
        uc_client: Principal-forwarded facade.

    Raises:
        ValidationError: When ``alert_id`` is missing from config.
    """
    del job_run_id  # unused; the AlertEvent row carries the history
    alert_id = config.get("alert_id")
    if not isinstance(alert_id, int):
        raise ValidationError("alert_check job config missing integer 'alert_id'")

    from uuid import uuid4

    import duckdb

    from pointlessql.db import get_session_factory
    from pointlessql.models import Alert, AlertDestination, SavedQuery
    from pointlessql.pql import PQL, SQLParseError, prepare_sql
    from pointlessql.services import alerts as alerts_service
    from pointlessql.services.alert_dispatcher import dispatch_webhook
    from pointlessql.services.authorization import SELECT, check_privilege

    factory = get_session_factory()
    with factory() as session:
        alert = session.get(Alert, alert_id)
        if alert is None or not alert.is_active:
            return
        saved = session.get(SavedQuery, alert.saved_query_id)
        if saved is None:
            return
        sql_text = saved.sql_text
        alert_slug = alert.slug
        saved_query_slug = saved.slug
        condition_op = alert.condition_op
        threshold = alert.threshold
        workspace_id = int(alert.workspace_id)

    from pointlessql.services.signals import emit_signal, resolve_signal

    try:
        prepared = prepare_sql(sql_text)
    except SQLParseError as exc:
        logger.warning("alert %s: SQL parse failed: %s", alert_slug, exc)
        return

    approved: dict[str, str] = {}
    for full_name in prepared.refs:
        parts = full_name.split(".")
        if len(parts) != 3:
            logger.warning("alert %s: unexpected ref shape %r", alert_slug, full_name)
            return
        table_info = await uc_client.get_table(parts[0], parts[1], parts[2])
        if not table_info:
            logger.warning(
                "alert %s: referenced table %s not found",
                alert_slug,
                full_name,
            )
            return
        storage_location = table_info.get("storage_location")
        if not isinstance(storage_location, str) or not storage_location:
            logger.warning(
                "alert %s: table %s has no storage_location",
                alert_slug,
                full_name,
            )
            return
        await check_privilege(
            uc_client,
            user_info["email"],
            bool(user_info["is_admin"]),
            "table",
            full_name,
            SELECT,
        )
        approved[full_name] = storage_location

    conn = duckdb.connect()
    try:
        result = await asyncio.to_thread(
            PQL.sql,
            sql_text,
            approved_tables=approved,
            max_rows=100_000,
            conn=conn,
            explain=False,
        )
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001 — diagnostic only
            logger.debug("alert %s: conn.close raised", alert_slug, exc_info=True)

    if not alerts_service.evaluate_condition(result.row_count, condition_op, threshold):
        # Condition no longer met — clear any open data-health card so
        # the feed self-heals when the alert stops firing.
        resolve_signal(
            factory,
            signal_kind="alert_firing",
            workspace_id=workspace_id,
            entity_kind="alert",
            entity_ref=str(alert_id),
        )
        return

    now = datetime.datetime.now(datetime.UTC)
    envelope = alerts_service.build_cloudevent(
        event_id=uuid4().hex,
        alert_slug=alert_slug,
        saved_query_slug=saved_query_slug,
        condition_op=condition_op,
        threshold=threshold,
        row_count=result.row_count,
        duration_ms=result.duration_ms,
        referenced_tables=result.referenced_tables,
        fired_at=now,
    )
    payload_json = json.dumps(envelope, sort_keys=True)
    alerts_service.record_event(
        factory,
        alert_id=alert_id,
        event_id=envelope["id"],
        fired_at=now,
        row_count=result.row_count,
        outcome="fired",
        payload_json=payload_json,
    )

    # Open a data-health card (or keep one open) so the firing alert
    # surfaces in the feed.  The ledger's dedupe guard means a still-
    # firing alert produces one card, not one per tick.
    emit_signal(
        factory,
        signal_kind="alert_firing",
        workspace_id=workspace_id,
        entity_kind="alert",
        entity_ref=str(alert_id),
        summary_md=(
            f"Alert '{alert_slug}' fired — {result.row_count} rows {condition_op} {threshold}"
        ),
        source_url=f"/alerts/{alert_slug}",
    )

    # Fan out webhook dispatches.
    with factory() as session:
        dests = list(
            session.scalars(
                select(AlertDestination).where(
                    AlertDestination.alert_id == alert_id,
                    AlertDestination.is_active.is_(True),
                )
            ).all()
        )
    delivery_failed = False
    for dest in dests:
        if dest.kind != "webhook" or not dest.webhook_url:
            continue
        ok = await dispatch_webhook(
            dest.webhook_url,
            envelope,
            hmac_secret=dest.hmac_secret,
        )
        if not ok:
            delivery_failed = True
    if delivery_failed:
        alerts_service.set_event_outcome(factory, envelope["id"], "delivery_failed")
