"""Audit-stream sink dispatchers.

Three sink types ship in the first cut:

* ``webhook`` — reuses :func:`pointlessql.services.alert_dispatcher.dispatch_webhook`
  (HMAC-SHA256 signing + 3-attempt retry) so existing receivers
  decode the envelope unchanged.
* ``s3`` — PUTs one JSON object per envelope under
  ``<prefix>/<event_type>/<yyyy>/<mm>/<dd>/<event_id>.json``.
  Works against any S3-compatible store (real AWS, MinIO,
  Cloudflare R2) by setting ``endpoint_url``.
* ``aws_cloudtrail`` — POSTs to the CloudTrail Data Service
  ``PutAuditEvents`` endpoint.  Each envelope becomes one
  ``AuditEvent`` whose ``EventData`` is the canonical CloudEvents
  JSON.

The dispatcher is intentionally narrow: each sink type returns
``True``/``False`` for delivered/not-delivered.  No queue, no DLQ —
the persistence row in ``governance_events`` (or
``agent_run_events``) keeps the trail durable across webhook
outages, and a follow-up replay job can re-fan failed deliveries
when one is needed.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.models.audit._sinks import AuditSink
from pointlessql.services.alert_dispatcher import dispatch_webhook
from pointlessql.services.aws_sigv4 import sign_request
from pointlessql.types import AuditSinkType, SessionFactory

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=10.0)



def _decode_config(sink: AuditSink) -> dict[str, Any]:
    """Decode ``sink.config_json`` into a dict, raising :class:`ValueError` on bad JSON.

    Args:
        sink: ORM row to read.

    Returns:
        Decoded config dict.

    Raises:
        ValueError: When ``config_json`` is not a JSON object.
    """
    cfg = json.loads(sink.config_json or "{}")
    if not isinstance(cfg, dict):
        raise ValueError(f"audit_sinks[{sink.id}].config_json is not a JSON object")
    return cfg


def _decode_event_filter(sink: AuditSink) -> set[str] | None:
    """Decode the optional event-type allow-list.

    Args:
        sink: ORM row to read.

    Returns:
        ``None`` when every event is allowed, else a set of allowed
        ``event_type`` strings.  An empty list / null column maps to
        ``None`` ("everything").
    """
    raw = sink.event_types_json
    if not raw:
        return None
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            "audit_sinks[%s].event_types_json is not valid JSON; allowing all events",
            sink.id,
        )
        return None
    if not isinstance(decoded, list) or not decoded:
        return None
    return {str(item) for item in decoded}


def _decode_workspace_filter(sink: AuditSink) -> set[int] | None:
    """Decode the optional workspace-id allow-list.

    Args:
        sink: ORM row to read.

    Returns:
        ``None`` when every workspace's events fire the sink (the
        install-global default), else a set of allowed
        ``workspace_id`` ints.  An empty list, malformed JSON, or
        null column all map to ``None`` so an admin's typo never
        silently blackholes events — fail-open for routing, fail-loud
        only for delivery.
    """
    raw = sink.workspace_filter
    if not raw:
        return None
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            "audit_sinks[%s].workspace_filter is not valid JSON; allowing all workspaces",
            sink.id,
        )
        return None
    if not isinstance(decoded, list) or not decoded:
        return None
    out: set[int] = set()
    for item in decoded:
        try:
            out.add(int(item))
        except TypeError, ValueError:
            logger.warning(
                "audit_sinks[%s].workspace_filter entry %r is not an int; ignoring",
                sink.id,
                item,
            )
    return out or None


async def _dispatch_webhook(
    sink: AuditSink,
    envelope: dict[str, Any],
) -> bool:
    """Dispatch *envelope* to a webhook sink, returning success.

    Args:
        sink: The webhook sink ORM row.
        envelope: CloudEvents 1.0 dict.

    Returns:
        ``True`` on a 2xx response within the retry budget.
    """
    cfg = _decode_config(sink)
    url = cfg.get("url")
    if not isinstance(url, str) or not url:
        logger.warning("audit_sinks[%s] webhook missing 'url' in config", sink.id)
        return False
    raw_secret = cfg.get("hmac_secret")
    secret = raw_secret if isinstance(raw_secret, str) and raw_secret else None
    return await dispatch_webhook(url, envelope, hmac_secret=secret)


async def _dispatch_s3(
    sink: AuditSink,
    envelope: dict[str, Any],
    *,
    client: httpx.AsyncClient | None = None,
) -> bool:
    """PUT one JSON object per envelope under ``<prefix>/...`` in S3.

    Args:
        sink: The S3 sink ORM row.
        envelope: CloudEvents 1.0 dict.
        client: Optional httpx client override (used by tests).

    Returns:
        ``True`` on a 2xx response.
    """
    cfg = _decode_config(sink)
    bucket = cfg.get("bucket")
    region = cfg.get("region", "us-east-1")
    access_key_id = cfg.get("access_key_id")
    secret_access_key = cfg.get("secret_access_key")
    prefix = (cfg.get("prefix") or "").strip("/")
    endpoint_url = cfg.get("endpoint_url")
    if not all(isinstance(v, str) and v for v in (bucket, access_key_id, secret_access_key)):
        logger.warning("audit_sinks[%s] s3 config missing bucket / credentials", sink.id)
        return False

    fired_at = envelope.get("time", datetime.datetime.now(datetime.UTC).isoformat())
    try:
        when = datetime.datetime.fromisoformat(fired_at)
    except TypeError, ValueError:
        when = datetime.datetime.now(datetime.UTC)
    event_type = envelope.get("type", "unknown")
    event_id = envelope.get("id", "no-id")
    key_parts = [
        p
        for p in (
            prefix,
            event_type,
            f"{when:%Y}",
            f"{when:%m}",
            f"{when:%d}",
            f"{event_id}.json",
        )
        if p
    ]
    object_key = "/".join(key_parts)

    body = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    extra = {"Content-Type": "application/cloudevents+json"}

    if endpoint_url:
        url = f"{endpoint_url.rstrip('/')}/{bucket}/{object_key}"
    else:
        url = f"https://{bucket}.s3.{region}.amazonaws.com/{object_key}"

    headers = sign_request(
        method="PUT",
        url=url,
        region=region,
        service="s3",
        access_key_id=access_key_id,  # type: ignore[arg-type]
        secret_access_key=secret_access_key,  # type: ignore[arg-type]
        body=body,
        extra_headers=extra,
    )

    should_close = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
    try:
        try:
            response = await client.put(url, content=body, headers=headers)
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            logger.warning("audit_sinks[%s] s3 transport error: %s", sink.id, exc)
            return False
        if 200 <= response.status_code < 300:
            return True
        logger.warning(
            "audit_sinks[%s] s3 returned HTTP %d for %s",
            sink.id,
            response.status_code,
            object_key,
        )
        return False
    finally:
        if should_close:
            await client.aclose()


async def _dispatch_cloudtrail(
    sink: AuditSink,
    envelope: dict[str, Any],
    *,
    client: httpx.AsyncClient | None = None,
) -> bool:
    """POST one envelope to the CloudTrail Data Service PutAuditEvents endpoint.

    Args:
        sink: The aws_cloudtrail sink ORM row.
        envelope: CloudEvents 1.0 dict.
        client: Optional httpx client override (used by tests).

    Returns:
        ``True`` on a 2xx response.
    """
    cfg = _decode_config(sink)
    region = cfg.get("region", "us-east-1")
    event_source = cfg.get("event_source", "pointlessql.audit")
    channel_arn = cfg.get("channel_arn")
    access_key_id = cfg.get("access_key_id")
    secret_access_key = cfg.get("secret_access_key")
    if not all(isinstance(v, str) and v for v in (channel_arn, access_key_id, secret_access_key)):
        logger.warning(
            "audit_sinks[%s] cloudtrail config missing channel_arn / credentials",
            sink.id,
        )
        return False

    audit_event = {
        "id": envelope.get("id"),
        "eventData": json.dumps(envelope, sort_keys=True, separators=(",", ":")),
    }
    body_dict = {
        "auditEvents": [audit_event],
        "channelArn": channel_arn,
        "externalId": event_source,
    }
    body = json.dumps(body_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
    extra = {"Content-Type": "application/json"}

    url = f"https://cloudtrail-data.{region}.amazonaws.com/PutAuditEvents"

    headers = sign_request(
        method="POST",
        url=url,
        region=region,
        service="cloudtrail-data",
        access_key_id=access_key_id,  # type: ignore[arg-type]
        secret_access_key=secret_access_key,  # type: ignore[arg-type]
        body=body,
        extra_headers=extra,
    )

    should_close = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
    try:
        try:
            response = await client.post(url, content=body, headers=headers)
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            logger.warning("audit_sinks[%s] cloudtrail transport error: %s", sink.id, exc)
            return False
        if 200 <= response.status_code < 300:
            return True
        logger.warning(
            "audit_sinks[%s] cloudtrail returned HTTP %d",
            sink.id,
            response.status_code,
        )
        return False
    finally:
        if should_close:
            await client.aclose()


async def dispatch_one(
    sink: AuditSink,
    envelope: dict[str, Any],
    *,
    client: httpx.AsyncClient | None = None,
) -> bool:
    """Route the envelope to the right per-type dispatcher.

    Unknown sink types are logged-and-skipped — adding a new type is
    a controlled migration, never an exception in the hot path.

    Args:
        sink: ORM row.
        envelope: CloudEvents dict.
        client: Optional pre-built httpx client (S3 / CloudTrail).

    Returns:
        ``True`` when the dispatcher reports success.
    """
    if sink.type == AuditSinkType.WEBHOOK:
        return await _dispatch_webhook(sink, envelope)
    if sink.type == AuditSinkType.S3:
        return await _dispatch_s3(sink, envelope, client=client)
    if sink.type == AuditSinkType.AWS_CLOUDTRAIL:
        return await _dispatch_cloudtrail(sink, envelope, client=client)
    if sink.type == AuditSinkType.STDOUT_JSON:
        return _dispatch_stdout_json(sink, envelope)
    if sink.type == AuditSinkType.SYSLOG:
        return _dispatch_syslog(sink, envelope)
    logger.warning("audit_sinks[%s] unknown type=%r — skipping", sink.id, sink.type)
    return False


def _dispatch_stdout_json(sink: AuditSink, envelope: dict[str, Any]) -> bool:
    """Write the envelope as a single line of JSON to stdout.

    Aimed at container-log harvesters (Loki, Fluent Bit,
    Vector) that index stdout/stderr.  Delivery is sync — there is no
    network round-trip — so we never see retries; OSError on write is
    swallowed (the audit_log row stays authoritative).

    Args:
        sink: ORM row.  ``config_json`` may carry an optional
            ``stream`` field (``'stdout'`` default, ``'stderr'``
            alt); any other value falls back to stdout.
        envelope: CloudEvents 1.0 dict.

    Returns:
        ``True`` on a successful write.
    """
    import sys

    try:
        cfg = _decode_config(sink)
    except ValueError:
        logger.exception("audit_sinks[%s] bad config_json", sink.id)
        return False
    stream_name = str(cfg.get("stream") or "stdout").lower()
    stream = sys.stderr if stream_name == "stderr" else sys.stdout
    try:
        line = json.dumps(envelope, separators=(",", ":"), sort_keys=True)
        stream.write(line + "\n")
        stream.flush()
    except OSError:
        logger.exception("audit_sinks[%s] stdout_json write failed", sink.id)
        return False
    return True


def _dispatch_syslog(sink: AuditSink, envelope: dict[str, Any]) -> bool:
    """Send the envelope to a syslog endpoint via :mod:`logging.handlers`.

    "host:port",
    protocol: "udp" | "tcp", facility: int (default 1), severity: int
    (default 6)}``.  The envelope is JSON-encoded and shipped as the
    message body — receivers parse it with their existing JSON
    pipeline.  TLS is intentionally NOT supported here; if you need
    encrypted syslog, terminate TLS at a local sidecar (rsyslog /
    syslog-ng) and point this sink at the sidecar.

    Args:
        sink: ORM row.
        envelope: CloudEvents 1.0 dict.

    Returns:
        ``True`` on a successful emit.  Network errors are caught and
        logged — the primary DB write is never blocked by sink failure.
    """
    import logging.handlers as _handlers
    import socket

    try:
        cfg = _decode_config(sink)
    except ValueError:
        logger.exception("audit_sinks[%s] bad config_json", sink.id)
        return False
    address_raw = cfg.get("address")
    if not isinstance(address_raw, str) or ":" not in address_raw:
        logger.warning("audit_sinks[%s] syslog address must be 'host:port'", sink.id)
        return False
    host, port_str = address_raw.rsplit(":", 1)
    try:
        port = int(port_str)
    except ValueError:
        logger.warning(
            "audit_sinks[%s] syslog port %r is not an integer",
            sink.id,
            port_str,
        )
        return False
    protocol = str(cfg.get("protocol") or "udp").lower()
    sock_type = socket.SOCK_STREAM if protocol == "tcp" else socket.SOCK_DGRAM
    facility = int(cfg.get("facility", 1))
    severity = int(cfg.get("severity", 6))

    syslog_logger_name = f"pointlessql.audit_sink.{sink.id}"
    syslog_logger = logging.getLogger(syslog_logger_name)
    syslog_logger.setLevel(logging.DEBUG)
    syslog_logger.propagate = False
    handler: _handlers.SysLogHandler | None = None
    try:
        handler = _handlers.SysLogHandler(
            address=(host, port),
            facility=facility,
            socktype=sock_type,
        )
        # SysLogHandler levels: PRI = facility * 8 + severity.  We
        # don't override its severity-from-record mapping — the
        # downstream collector sees the configured severity through
        # the LogRecord level set below.
        del severity  # kept for future per-record override use
        handler.setFormatter(logging.Formatter("%(message)s"))
        syslog_logger.addHandler(handler)
        payload = json.dumps(envelope, separators=(",", ":"), sort_keys=True)
        syslog_logger.info(payload)
        return True
    except OSError:
        logger.exception("audit_sinks[%s] syslog emit failed", sink.id)
        return False
    finally:
        if handler is not None:
            handler.close()
            syslog_logger.removeHandler(handler)


def _select_active_sinks(
    session: Session,
    *,
    event_type: str,
    workspace_id: int | None = None,
) -> list[AuditSink]:
    """Return active sinks whose event-type + workspace filter passes.

    Args:
        session: Open SQLAlchemy session.
        event_type: CloudEvents ``type`` of the envelope being fanned out.
        workspace_id: Workspace the originating event belongs to.
            ``None`` skips workspace filtering entirely (used by the
            synthetic ``/api/admin/audit-sinks/{id}/test`` flow which
            bypasses both filters).

    Returns:
        Detached sink rows in primary-key order.
    """
    rows = list(
        session.scalars(
            select(AuditSink).where(AuditSink.is_active.is_(True)).order_by(AuditSink.id.asc())
        ).all()
    )
    out: list[AuditSink] = []
    for row in rows:
        allow_event = _decode_event_filter(row)
        if allow_event is not None and event_type not in allow_event:
            continue
        if workspace_id is not None:
            allow_ws = _decode_workspace_filter(row)
            if allow_ws is not None and workspace_id not in allow_ws:
                continue
        out.append(row)
    for row in out:
        session.expunge(row)
    return out


async def dispatch_to_sinks(
    session_factory: SessionFactory | sessionmaker[Session],
    envelope: dict[str, Any],
    *,
    workspace_id: int | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Fan *envelope* out to every active sink that allows it.

    Args:
        session_factory: Sessionmaker callable.
        envelope: CloudEvents 1.0 dict.  Must include ``type`` and
            ``id``.
        workspace_id: Workspace the originating event belongs to.
            When supplied, sinks with a non-null ``workspace_filter``
            that excludes this id are skipped.  ``None`` disables
            workspace filtering — used by callers that already speak
            install-global semantics (notably the synthetic test
            envelope endpoint).
        client: Optional pre-built httpx client (used by tests; the
            S3 / CloudTrail dispatchers reuse it for SigV4 PUT/POST).

    Returns:
        Per-sink fan-out log: ``[{sink_id, name, type, delivered_at,
        ok}, ...]``.  Empty list when no matching active sinks
        existed at fire time.
    """
    event_type = str(envelope.get("type", ""))
    with session_factory() as session:
        sinks = _select_active_sinks(session, event_type=event_type, workspace_id=workspace_id)
    log: list[dict[str, Any]] = []
    for sink in sinks:
        ok = False
        try:
            ok = await dispatch_one(sink, envelope, client=client)
        except Exception:  # noqa: BLE001 — emitter must never raise
            logger.exception(
                "audit_sinks[%s] dispatcher raised for event_id=%s",
                sink.id,
                envelope.get("id"),
            )
        log.append(
            {
                "sink_id": sink.id,
                "name": sink.name,
                "type": sink.type,
                "delivered_at": datetime.datetime.now(datetime.UTC).isoformat(),
                "ok": ok,
            }
        )

    # also fan out to per-user webhook subscriptions
    # for the data-product event family.  Best-effort; failures are
    # stamped per-subscription, not surfaced to the emitter.
    if event_type.startswith("pointlessql.data_product."):
        try:
            from pointlessql.services.notifications import (
                deliver_to_user_subscriptions,
            )

            user_log = await deliver_to_user_subscriptions(
                session_factory,
                envelope,
                workspace_id=workspace_id,
                client=client,
            )
            for entry in user_log:
                log.append(
                    {
                        "sub_id": entry["sub_id"],
                        "name": f"user_webhook[{entry['user_id']}]",
                        "type": "user_webhook",
                        "delivered_at": entry["delivered_at"],
                        "ok": entry["ok"],
                    }
                )
        except Exception:  # noqa: BLE001 — emitter must never raise
            logger.exception(
                "user_webhook_subscriptions dispatch raised for event_id=%s",
                envelope.get("id"),
            )

    return log
