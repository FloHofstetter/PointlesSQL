"""Per-user CloudEvent webhook delivery.

Hooks into :func:`pointlessql.services.audit.sinks.dispatch_to_sinks`
*after* install-global sinks have fanned out.  Scans
``user_webhook_subscriptions`` for rows whose ``event_type_filter``
matches the envelope's ``type`` and whose ``dp_ref_filter`` (if
set) matches the envelope's ``data.data_product_ref``, then
delivers via the existing HMAC signer
(:func:`pointlessql.services.alert_dispatcher.sign_body`).

Failure path: per-row HTTP error stamps ``last_error`` +
``last_delivered_at``.  Successes clear ``last_error`` and set
``last_delivered_at``.  One bad subscription never breaks
another.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

import httpx
from sqlalchemy import or_, select

from pointlessql.models.notifications import UserWebhookSubscription
from pointlessql.services.alert_dispatcher import sign_body
from pointlessql.services.egress_guard import assert_public_http_url

logger = logging.getLogger(__name__)


def _matches_dp_ref(filt: str | None, payload: dict[str, Any]) -> bool:
    """``filt`` matches the payload's ``data_product_ref`` (or ``None`` matches all)."""
    if filt is None:
        return True
    raw = payload.get("data_product_ref")
    if not isinstance(raw, str):
        raw = payload.get("ref")
    return isinstance(raw, str) and raw == filt


async def deliver_to_user_subscriptions(
    session_factory: Any,
    envelope: dict[str, Any],
    *,
    workspace_id: int | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Fan *envelope* out to matching user webhook subscriptions.

    Args:
        session_factory: SQLAlchemy session factory.
        envelope: CloudEvents 1.0 dict.
        workspace_id: Optional filter — when supplied, only
            subscriptions whose ``workspace_id`` matches are
            considered.
        client: Optional pre-built ``httpx.AsyncClient`` (reused by
            tests).

    Returns:
        Per-subscription log entries with ``sub_id``, ``user_id``,
        ``delivered_at``, ``ok``.
    """
    event_type = str(envelope.get("type", ""))
    if not event_type.startswith("pointlessql.data_product."):
        return []
    payload: dict[str, Any] = {}
    raw_data: Any = envelope.get("data", {})
    if isinstance(raw_data, dict):
        # Narrow the dict to ``dict[str, Any]`` for pyright; the
        # CloudEvents `data` payload is producer-defined so we can't
        # claim sharper typing here without a generic schema.
        for k, v in raw_data.items():  # pyright: ignore[reportUnknownVariableType]
            payload[str(k)] = v

    log: list[dict[str, Any]] = []
    with session_factory() as session:
        stmt = select(UserWebhookSubscription).where(
            UserWebhookSubscription.is_active == 1,
            or_(
                UserWebhookSubscription.event_type_filter == event_type,
                UserWebhookSubscription.event_type_filter == "*",
            ),
        )
        if workspace_id is not None:
            stmt = stmt.where(UserWebhookSubscription.workspace_id == workspace_id)
        subs = list(session.execute(stmt).scalars())

    if not subs:
        return []

    body = json.dumps(envelope, sort_keys=True).encode("utf-8")
    own_client = client is None
    actual_client = client or httpx.AsyncClient(timeout=10.0)
    try:
        for sub in subs:
            if not _matches_dp_ref(sub.dp_ref_filter, payload):
                continue
            ok = False
            error: str | None = None
            try:
                # Re-check at send time so a DNS rebind to an internal
                # address since the subscription was saved is rejected.
                assert_public_http_url(sub.webhook_url)
                resp = await actual_client.post(
                    sub.webhook_url,
                    content=body,
                    headers={
                        "Content-Type": "application/cloudevents+json",
                        "X-PointlesSQL-Signature": f"sha256={sign_body(body, sub.hmac_secret)}",
                    },
                )
                ok = resp.is_success
                if not ok:
                    error = f"HTTP {resp.status_code}"
            except Exception as exc:  # noqa: BLE001 — never break the loop
                # bare-broad-ok: per-subscription delivery is
                # best-effort — record + move on.
                error = repr(exc)

            # Stamp delivery state on the subscription row.
            with session_factory() as session2:
                row = session2.get(UserWebhookSubscription, sub.id)
                if row is not None:
                    row.last_delivered_at = datetime.datetime.now(datetime.UTC)
                    row.last_error = None if ok else error
                    session2.add(row)
                    session2.commit()

            log.append(
                {
                    "sub_id": sub.id,
                    "user_id": sub.user_id,
                    "delivered_at": datetime.datetime.now(datetime.UTC).isoformat(),
                    "ok": ok,
                    "error": error,
                }
            )
    finally:
        if own_client:
            await actual_client.aclose()
    return log
