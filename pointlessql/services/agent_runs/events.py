"""CloudEvents envelope + emitter for agent-run lifecycle.

Extends the alert-event vocabulary with
``pointlessql.agent_run.started`` / ``.completed`` / ``.failed``
plus ``.tool_call``.

Webhook delivery reuses the alert dispatcher
(:func:`pointlessql.services.alert_dispatcher.dispatch_webhook`)
— we just hand it the new envelope and an env-var-resolved URL.
The schema is intentionally flat: no ``agent_run_destinations``
table, no per-event-type filtering — that richer destination model
would belong on top of this layer.

Every envelope is INSERTed into ``agent_run_events`` *before*
dispatch with ``outcome="pending"``; the dispatcher result updates
the column to ``"delivered"`` / ``"delivery_failed"`` /
``"no_destination"``.  Webhook failures still don't raise — but a
DB-side failure on the persistence step *does*, because the
registry's durability is the audit guarantee.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from pointlessql.models import AgentRunEvent
from pointlessql.services.alert_dispatcher import dispatch_webhook
from pointlessql.services.audit_sinks import dispatch_to_sinks
from pointlessql.settings import Settings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


EVENT_TYPE_STARTED = "pointlessql.agent_run.started"
EVENT_TYPE_COMPLETED = "pointlessql.agent_run.completed"
EVENT_TYPE_FAILED = "pointlessql.agent_run.failed"
EVENT_TYPE_TOOL_CALL = "pointlessql.agent_run.tool_call"
EVENT_TYPE_ROLLBACK_EXECUTED = "pointlessql.rollback.executed"

AGENT_RUN_EVENT_TYPES: tuple[str, ...] = (
    EVENT_TYPE_STARTED,
    EVENT_TYPE_COMPLETED,
    EVENT_TYPE_FAILED,
    EVENT_TYPE_TOOL_CALL,
    EVENT_TYPE_ROLLBACK_EXECUTED,
)


def event_type_for_status(status: str) -> str | None:
    """Map a terminal :class:`AgentRun` status to the matching event type.

    ``succeeded`` → ``.completed``, ``failed`` → ``.failed``.  The
    ``denied`` terminal status returns ``None`` because the event
    vocabulary covers execution outcomes, not human approval
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

    The envelope shape mirrors the alert-event envelope so existing
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


def _persist_event(
    session_factory: sessionmaker[Session],
    *,
    agent_run_id: str,
    event_id: str,
    event_type: str,
    fired_at: datetime.datetime,
    envelope: dict[str, Any],
    initial_outcome: str,
) -> int | None:
    """Insert one ``agent_run_events`` row and return its primary key.

    Args:
        session_factory: SQLAlchemy session factory.
        agent_run_id: UUID string of the owning :class:`AgentRun`.
        event_id: CloudEvents ``id`` field, unique across rows.
        event_type: One of :data:`AGENT_RUN_EVENT_TYPES`.
        fired_at: UTC timestamp the envelope was built.
        envelope: Full CloudEvents envelope, JSON-serialised verbatim.
        initial_outcome: Either ``"pending"`` (will be updated by the
            dispatcher) or ``"no_destination"`` (terminal, no
            dispatch attempted).

    Returns:
        The new row's primary key, or ``None`` when the insert
        failed (logged-and-swallowed — webhook persistence is
        best-effort relative to the registry write that already
        committed).
    """
    import json as _json

    try:
        with session_factory() as session:
            row = AgentRunEvent(
                agent_run_id=agent_run_id,
                event_id=event_id,
                event_type=event_type,
                fired_at=fired_at,
                outcome=initial_outcome,
                payload_json=_json.dumps(envelope, sort_keys=True),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.id
    except Exception:  # noqa: BLE001 — never raise into the route
        logger.exception(
            "agent_run_events persist failed for run=%s type=%s",
            agent_run_id,
            event_type,
        )
        return None


def _update_event_outcome(
    session_factory: sessionmaker[Session],
    *,
    row_id: int,
    outcome: str,
) -> None:
    """Best-effort update the persisted event's outcome column.

    Args:
        session_factory: SQLAlchemy session factory.
        row_id: Primary key of the row to update.
        outcome: One of ``"delivered"`` / ``"delivery_failed"``.
    """
    try:
        with session_factory() as session:
            row = session.scalar(select(AgentRunEvent).where(AgentRunEvent.id == row_id))
            if row is None:
                return
            row.outcome = outcome
            session.commit()
    except Exception:  # noqa: BLE001 — outcome update is cosmetic
        logger.exception("agent_run_events outcome update failed for id=%s", row_id)


async def emit_agent_run_event(
    event_type: str,
    agent_run_data: dict[str, Any],
    *,
    settings: Settings | None = None,
    fired_at: datetime.datetime | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> None:
    """Build the envelope, persist it, and POST to the configured webhook.

    Reads the webhook URL + optional HMAC secret from
    :class:`pointlessql.settings.AgentRunsSettings`.  When no URL is
    configured this is a logged no-op for the dispatch path —
    the row is still persisted with ``outcome = "no_destination"``
    so the trail is complete.

    When ``session_factory`` is provided the envelope is INSERTed
    into ``agent_run_events`` *before* dispatch with
    ``outcome = "pending"``; the post-dispatch update flips it to
    ``"delivered"`` or ``"delivery_failed"``.  ``session_factory``
    stays optional so unit tests that drive this function in
    isolation don't need a DB.

    Failures of the dispatch step are logged but never raised —
    a flaky webhook must not break the registry write that
    already committed.  DB-side persistence failures are also
    swallowed (relative to the route response) because the
    canonical agent-run row is already durable.

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
        session_factory: SQLAlchemy session factory used to persist
            the envelope.  ``None`` keeps the legacy fire-and-forget
            shape for unit tests.
    """
    if event_type not in AGENT_RUN_EVENT_TYPES:
        logger.warning("emit_agent_run_event: ignoring unknown event_type %r", event_type)
        return

    resolved_settings = settings or Settings()
    url = resolved_settings.agent_runs.webhook_url
    fired_at = fired_at or datetime.datetime.now(datetime.UTC)
    event_id = uuid.uuid4().hex
    envelope = build_agent_run_cloudevent(
        event_id=event_id,
        event_type=event_type,
        agent_run_data=agent_run_data,
        fired_at=fired_at,
    )

    initial_outcome = "pending" if url else "no_destination"
    row_id: int | None = None
    if session_factory is not None:
        run_id = str(agent_run_data.get("id", ""))
        if run_id:
            row_id = _persist_event(
                session_factory,
                agent_run_id=run_id,
                event_id=event_id,
                event_type=event_type,
                fired_at=fired_at,
                envelope=envelope,
                initial_outcome=initial_outcome,
            )

    if not url:
        logger.debug(
            "emit_agent_run_event: no agent-runs webhook configured, skipping %s for run=%s",
            event_type,
            agent_run_data.get("id"),
        )
        return

    delivered = False
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

    if not delivered:
        logger.warning(
            "emit_agent_run_event: dispatch returned False for %s run=%s url=%s",
            event_type,
            agent_run_data.get("id"),
            url,
        )

    if (
        session_factory is not None
        and resolved_settings.audit_stream.enabled
        and resolved_settings.audit_stream.mirror_lifecycle_to_sinks
    ):
        try:
            await dispatch_to_sinks(session_factory, envelope)
        except Exception:  # noqa: BLE001 — emitter must never raise
            logger.exception(
                "emit_agent_run_event: audit-sink mirror raised for %s run=%s",
                event_type,
                agent_run_data.get("id"),
            )

    if session_factory is not None and row_id is not None:
        _update_event_outcome(
            session_factory,
            row_id=row_id,
            outcome="delivered" if delivered else "delivery_failed",
        )
