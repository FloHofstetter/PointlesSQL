"""Webhook dispatch for fired Sprint-55 alerts.

Pure async helper: the scheduler's ``_alert_check_executor`` builds
the CloudEvents envelope, inserts an :class:`AlertEvent` row, and
then calls :func:`dispatch_webhook` for every enabled webhook
destination.  The function serialises the envelope deterministically,
optionally signs it with HMAC-SHA256, and POSTs with a 5s connect /
10s total timeout + two retries with exponential backoff.

No queue, no dedup, no idempotence token — those are alerting-
platform concerns and PointlesSQL stays a portable event emitter.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# Stubbed in tests so retry backoff does not actually sleep.
_sleep = asyncio.sleep


def canonicalise_envelope(envelope: dict[str, Any]) -> bytes:
    """Return the HMAC-input serialisation of *envelope*.

    Uses sorted keys + compact separators so receivers can re-serialise
    the decoded JSON and reproduce the exact bytes to verify the
    signature.  Deliberately *not* the request body itself — httpx
    round-trips the dict through its own JSON encoder — but the
    receiver is expected to re-serialise after parsing, so shipping
    the canonical body is the simplest contract.

    Args:
        envelope: The CloudEvents dict.

    Returns:
        UTF-8 encoded JSON bytes.
    """
    return json.dumps(
        envelope, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def sign_body(body: bytes, secret: str) -> str:
    """Return the hex-encoded HMAC-SHA256 of *body* using *secret*.

    Args:
        body: Raw request body bytes.
        secret: Pre-shared secret string.

    Returns:
        Hex digest, suitable for the ``sha256=<hex>`` header value.
    """
    return hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()


async def dispatch_webhook(
    url: str,
    envelope: dict[str, Any],
    *,
    hmac_secret: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> bool:
    """POST the CloudEvents *envelope* to *url*, returning success.

    Args:
        url: Destination URL.
        envelope: CloudEvents 1.0 dict.
        hmac_secret: Optional secret; when set, sign the canonical body
            and attach ``X-PointlesSQL-Signature: sha256=<hex>``.
        client: Optional pre-configured client.  When ``None`` a
            transient client with the Sprint-55 timeouts is created
            and closed within this call.

    Returns:
        ``True`` when a 2xx response arrived within the retry budget.
    """
    body = canonicalise_envelope(envelope)
    headers = {"Content-Type": "application/cloudevents+json"}
    if hmac_secret:
        headers["X-PointlesSQL-Signature"] = f"sha256={sign_body(body, hmac_secret)}"
    should_close = False
    if client is None:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=10.0)
        )
        should_close = True
    try:
        delay = 1.0
        last_error: Exception | None = None
        for attempt in range(3):  # initial + 2 retries
            try:
                response = await client.post(url, content=body, headers=headers)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_error = exc
                logger.warning(
                    "alert webhook transport error attempt=%d url=%s: %s",
                    attempt + 1, url, exc,
                )
            else:
                if 200 <= response.status_code < 300:
                    return True
                logger.warning(
                    "alert webhook %s returned HTTP %d",
                    url, response.status_code,
                )
                if response.status_code < 500:
                    # 4xx is a permanent failure; don't retry.
                    return False
            if attempt < 2:
                await _sleep(delay)
                delay *= 2
        if last_error is not None:
            logger.error(
                "alert webhook %s exhausted retries: %s", url, last_error
            )
        return False
    finally:
        if should_close:
            await client.aclose()
