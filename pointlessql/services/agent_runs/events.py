"""CloudEvents envelope + emitter for agent-run lifecycle.

Sprint 13.3 — extends the Sprint-55 alert envelope vocabulary with
``pointlessql.agent_run.started`` / ``.completed`` / ``.failed``.
The fourth type listed in the ROADMAP, ``.cell_completed``, will
land alongside the per-cell POST route in a later sprint; emitting
it from a route that doesn't exist yet would be misleading.

Webhook delivery is the existing Sprint-55 dispatcher
(:func:`pointlessql.services.alert_dispatcher.dispatch_webhook`)
— we just hand it the new envelope and an env-var-resolved URL.
This deliberately keeps the schema flat: no ``agent_run_destinations``
table in 13.3, no per-event-type filtering yet.  Sprint 13.4 owns
the richer destination model when the control-room UI lands.

Failures are logged but never raised — a flaky webhook must not
prevent the run row from being recorded, because the registry's
durability is the more important guarantee than every subscriber
receiving every event.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

from pointlessql.services.alert_dispatcher import dispatch_webhook
from pointlessql.settings import Settings

logger = logging.getLogger(__name__)


EVENT_TYPE_STARTED = "pointlessql.agent_run.started"
EVENT_TYPE_COMPLETED = "pointlessql.agent_run.completed"
EVENT_TYPE_FAILED = "pointlessql.agent_run.failed"

AGENT_RUN_EVENT_TYPES: tuple[str, ...] = (
    EVENT_TYPE_STARTED,
    EVENT_TYPE_COMPLETED,
    EVENT_TYPE_FAILED,
)


def event_type_for_status(status: str) -> str | None:
    """Map a terminal :class:`AgentRun` status to the matching event type.

    ``succeeded`` → ``.completed``, ``failed`` → ``.failed``.  The
    ``denied`` terminal status returns ``None`` because Sprint 13.3's
    event vocabulary covers execution outcomes, not human approval
    decisions; surfacing those would mis-signal that the runtime
    actually executed something.

    Args:
        status: A terminal status from
            :data:`pointlessql.models.agent_runs.TERMINAL_STATUSES`.

    Returns:
        The matching CloudEvents ``type``, or ``None`` when no event
        should fire for that status.
    """
    if status == "succeeded":
        return EVENT_TYPE_COMPLETED
    if status == "failed":
        return EVENT_TYPE_FAILED
    return None


def build_agent_run_cloudevent(
    *,
    event_id: str,
    event_type: str,
    agent_run_data: dict[str, Any],
    fired_at: datetime.datetime,
) -> dict[str, Any]:
    """Build a CloudEvents 1.0 envelope for an agent-run lifecycle event.

    The envelope shape mirrors the Sprint-55 alert event so existing
    subscribers can decode both with the same parser — only the
    ``type`` and ``data`` payload differ.  ``source`` includes the
    agent-run id so receivers can correlate by URL prefix without
    decoding the body.

    Args:
        event_id: Unique CloudEvents ``id`` (uuid4 hex by convention).
        event_type: One of :data:`AGENT_RUN_EVENT_TYPES`.
        agent_run_data: The serialized agent-run row, as produced by
            :func:`pointlessql.api.agent_runs_routes.serialize_agent_run`.
            Must include an ``id`` key.
        fired_at: UTC timestamp the event fired.

    Returns:
        A plain dict ready to ``json.dumps``-serialise onto the wire
        with ``Content-Type: application/cloudevents+json``.
    """
    run_id = agent_run_data.get("id", "unknown")
    return {
        "specversion": "1.0",
        "id": event_id,
        "source": f"/pointlessql/agent_runs/{run_id}",
        "type": event_type,
        "time": fired_at.astimezone(datetime.UTC).isoformat(),
        "datacontenttype": "application/json",
        "subject": str(run_id),
        "data": dict(agent_run_data),
    }


async def emit_agent_run_event(
    event_type: str,
    agent_run_data: dict[str, Any],
    *,
    settings: Settings | None = None,
    fired_at: datetime.datetime | None = None,
) -> None:
    """Build the envelope and (if configured) POST it to the webhook URL.

    Reads the webhook URL + optional HMAC secret from
    :class:`pointlessql.settings.AgentRunsSettings`.  When no URL is
    configured this is a logged no-op so unit-test runs and dev
    environments don't have to mock anything.

    Delivery uses the existing Sprint-55 dispatcher so HMAC signing,
    retry/backoff, and 4xx-vs-5xx semantics stay one implementation.

    Args:
        event_type: One of :data:`AGENT_RUN_EVENT_TYPES`.  Unknown
            types are logged and ignored — calling code shouldn't
            need a try/except just to be safe.
        agent_run_data: Serialized agent-run row (see
            :func:`build_agent_run_cloudevent`).
        settings: Optional :class:`Settings` override; defaults to a
            fresh ``Settings()`` so callers don't have to thread it
            through every layer.
        fired_at: Optional override for the event timestamp; defaults
            to ``datetime.now(UTC)``.
    """
    if event_type not in AGENT_RUN_EVENT_TYPES:
        logger.warning("emit_agent_run_event: ignoring unknown event_type %r", event_type)
        return

    resolved_settings = settings or Settings()
    url = resolved_settings.agent_runs.webhook_url
    if not url:
        logger.debug(
            "emit_agent_run_event: no agent-runs webhook configured, "
            "skipping %s for run=%s",
            event_type,
            agent_run_data.get("id"),
        )
        return

    envelope = build_agent_run_cloudevent(
        event_id=uuid.uuid4().hex,
        event_type=event_type,
        agent_run_data=agent_run_data,
        fired_at=fired_at or datetime.datetime.now(datetime.UTC),
    )

    try:
        delivered = await dispatch_webhook(
            url,
            envelope,
            hmac_secret=resolved_settings.agent_runs.webhook_hmac_secret,
        )
    except Exception:  # noqa: BLE001 — emitter must never raise into the route
        logger.exception(
            "emit_agent_run_event: webhook dispatch raised for %s run=%s",
            event_type,
            agent_run_data.get("id"),
        )
        return

    if not delivered:
        logger.warning(
            "emit_agent_run_event: dispatch returned False for %s run=%s url=%s",
            event_type,
            agent_run_data.get("id"),
            url,
        )
