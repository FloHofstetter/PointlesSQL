"""Governance CloudEvents emitter.

Five governance event types fan out to ``audit_sinks`` (the forwarder pluggable destination set):

* ``pointlessql.external_write.detected``.3 scanner found
  a Delta commit not attributed to any agent run.
* ``pointlessql.cost_gate.denied`` — :func:`/api/sql/explain` returned
  ``needs_approval=True`` because the row estimate exceeded
  :attr:`SQLSettings.cost_gate_threshold_rows`.
* ``pointlessql.audit_export.issued`` — an admin downloaded the
  ``/admin/audit/export`` JSON or CSV stream.
* ``pointlessql.policy.violated`` — a generic violation hook reserved
  for future policies; emit it from any code path that detects an
  out-of-policy condition.  The data payload is free-shape but
  should include a ``policy`` key.
* ``pointlessql.lineage.pruned``.2 pruner deleted N rows
  from a lineage table.

Run-tied lifecycle events stay in
:mod:`pointlessql.services.agent_runs.events`; this module is for
governance signals that aren't naturally attributable to a single
agent run.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from pointlessql.config import Settings, get_settings
from pointlessql.models.audit._sinks import GovernanceEvent
from pointlessql.services.audit.sinks import dispatch_to_sinks
from pointlessql.types import EventOutcome

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

#: Strong references to in-flight fire-and-forget governance-event tasks
#: spawned by :func:`spawn_governance_event`.  Without this the event loop
#: keeps only a weak reference and the task can be garbage-collected
#: mid-flight; the done-callback discards each task when it settles.
_background_event_tasks: set[asyncio.Task[None]] = set()


EVENT_TYPE_EXTERNAL_WRITE = "pointlessql.external_write.detected"
EVENT_TYPE_POLICY_VIOLATION = "pointlessql.policy.violated"
EVENT_TYPE_COST_GATE_DENIED = "pointlessql.cost_gate.denied"
EVENT_TYPE_AUDIT_EXPORT_ISSUED = "pointlessql.audit_export.issued"
EVENT_TYPE_LINEAGE_PRUNED = "pointlessql.lineage.pruned"
EVENT_TYPE_BRANCH_CREATED = "pointlessql.branch.created.v1"
EVENT_TYPE_BRANCH_PROMOTED = "pointlessql.branch.promoted.v1"
EVENT_TYPE_BRANCH_DISCARDED = "pointlessql.branch.discarded.v1"
# dbt-bridge events.  ``run.completed`` fires
# at the end of every ``/api/dbt/run`` and ``/api/dbt/test`` so a
# subscriber can render run-level summaries; ``test.failed`` fires
# once per failing error-severity test (these block the run);
# ``test.warned`` fires once per failing warn-severity test (the
# run still succeeds — the cockpit's anomaly inbox is the surface).
EVENT_TYPE_DBT_RUN_COMPLETED = "pointlessql.dbt.run.completed"
EVENT_TYPE_DBT_TEST_FAILED = "pointlessql.dbt.test.failed"
EVENT_TYPE_DBT_TEST_WARNED = "pointlessql.dbt.test.warned"
# fired when /api/dbt/test resolves at least
# one error-severity failure under the ``auto_rollback`` flag and
# walks the run's ``dbt_model`` ops calling ``pql.rollback`` for each.
# Payload carries every target attempted plus the per-target outcome
# (succeeded vs. refused) so the cockpit can render the auto-undo
# decision next to the failing tests that triggered it.
EVENT_TYPE_DBT_AUTO_ROLLBACK_EXECUTED = "pointlessql.dbt.auto_rollback.executed"
# fired by the data-product freshness scanner when a
# product whose contract declares ``sla_minutes`` has not received
# a write across any of its tables for longer than the SLA permits.
# Payload carries (workspace_id, catalog, schema, name, sla_minutes,
# last_write_at_iso, age_minutes) so subscribers can route alerts to
# the steward and render age in their preferred timezone.
EVENT_TYPE_DATA_PRODUCT_SLA_VIOLATED = "pointlessql.data_product.sla_violated"
EVENT_TYPE_DATA_PRODUCT_FORGOTTEN = "pointlessql.data_product.subject_forgotten"

# data-product marketplace social events.  Comment +
# review + follow events go through the same forwarder as the rest
# of the governance lane so existing webhook/S3/CloudTrail sinks
# pick them up without new pub-sub plumbing; the per-user inbox
# fan-out happens *next to* this emit (not as part of it).
EVENT_TYPE_DATA_PRODUCT_COMMENTED = "pointlessql.data_product.commented"
EVENT_TYPE_DATA_PRODUCT_REVIEWED = "pointlessql.data_product.reviewed"
EVENT_TYPE_DATA_PRODUCT_FOLLOWED = "pointlessql.data_product.followed"
EVENT_TYPE_DATA_PRODUCT_SCHEMA_CHANGED = "pointlessql.data_product.schema_changed"
EVENT_TYPE_DATA_PRODUCT_CONTRACT_VIOLATED = "pointlessql.data_product.contract_violated"
EVENT_TYPE_DATA_PRODUCT_PROPOSAL_OPENED = "pointlessql.data_product.proposal_opened"
EVENT_TYPE_DATA_PRODUCT_PROPOSAL_RESOLVED = "pointlessql.data_product.proposal_resolved"
# six-emoji reactions on comments + on the product
# itself, plus the typed-Q&A "answer accepted" event.  Same
# governance lane as the rest of the marketplace events; the
# fanout-side recipient policy differs (comment reactions only
# notify the comment author; DP reactions notify followers; an
# accepted answer notifies the answer's author + the asker).
EVENT_TYPE_DATA_PRODUCT_COMMENT_REACTED = "pointlessql.data_product.comment_reacted"
EVENT_TYPE_DATA_PRODUCT_REACTED = "pointlessql.data_product.reacted"
EVENT_TYPE_DATA_PRODUCT_ANSWER_ACCEPTED = "pointlessql.data_product.answer_accepted"
# user-to-user follow signal.  Recipient is the
# followed user (single inbox row), governance envelope carries
# follower + followed ids for SIEM correlation.
EVENT_TYPE_USER_FOLLOWED = "pointlessql.user.followed"
# sticky positive-only reputation badge.  The badges
# loop awards rows once per (user, badge_key) threshold crossing.
EVENT_TYPE_USER_BADGE_AWARDED = "pointlessql.user.badge_awarded"
# topic-membership signal.  Fans out to topic
# followers when a new DP joins a topic they follow.
EVENT_TYPE_TOPIC_DP_ADDED = "pointlessql.topic.dp_added"
EVENT_TYPE_NOTIFICATION_DIGEST = "pointlessql.notification.digest"
# GitHub-Issues entity events.  Two events split the
# lifecycle: ``opened`` fires once at issue creation; ``state_changed``
# fires on every close / reopen / mark-not-planned.  Both events
# carry the parent entity (kind + ref) so SIEM / Grafana can route
# by parent kind without joining ``issues`` to ``social_targets``.
EVENT_TYPE_ISSUE_OPENED = "pointlessql.issue.opened"
EVENT_TYPE_ISSUE_STATE_CHANGED = "pointlessql.issue.state_changed"

GOVERNANCE_EVENT_TYPES: tuple[str, ...] = (
    EVENT_TYPE_EXTERNAL_WRITE,
    EVENT_TYPE_POLICY_VIOLATION,
    EVENT_TYPE_COST_GATE_DENIED,
    EVENT_TYPE_AUDIT_EXPORT_ISSUED,
    EVENT_TYPE_LINEAGE_PRUNED,
    EVENT_TYPE_BRANCH_CREATED,
    EVENT_TYPE_BRANCH_PROMOTED,
    EVENT_TYPE_BRANCH_DISCARDED,
    EVENT_TYPE_DBT_RUN_COMPLETED,
    EVENT_TYPE_DBT_TEST_FAILED,
    EVENT_TYPE_DBT_TEST_WARNED,
    EVENT_TYPE_DBT_AUTO_ROLLBACK_EXECUTED,
    EVENT_TYPE_DATA_PRODUCT_SLA_VIOLATED,
    EVENT_TYPE_DATA_PRODUCT_FORGOTTEN,
    EVENT_TYPE_DATA_PRODUCT_COMMENTED,
    EVENT_TYPE_DATA_PRODUCT_REVIEWED,
    EVENT_TYPE_DATA_PRODUCT_FOLLOWED,
    EVENT_TYPE_DATA_PRODUCT_SCHEMA_CHANGED,
    EVENT_TYPE_DATA_PRODUCT_CONTRACT_VIOLATED,
    EVENT_TYPE_DATA_PRODUCT_PROPOSAL_OPENED,
    EVENT_TYPE_DATA_PRODUCT_PROPOSAL_RESOLVED,
    EVENT_TYPE_DATA_PRODUCT_COMMENT_REACTED,
    EVENT_TYPE_DATA_PRODUCT_REACTED,
    EVENT_TYPE_DATA_PRODUCT_ANSWER_ACCEPTED,
    EVENT_TYPE_USER_FOLLOWED,
    EVENT_TYPE_USER_BADGE_AWARDED,
    EVENT_TYPE_TOPIC_DP_ADDED,
    EVENT_TYPE_NOTIFICATION_DIGEST,
    EVENT_TYPE_ISSUE_OPENED,
    EVENT_TYPE_ISSUE_STATE_CHANGED,
)


def build_governance_envelope(
    *,
    event_id: str,
    event_type: str,
    data: dict[str, Any],
    fired_at: datetime.datetime,
) -> dict[str, Any]:
    """Build a CloudEvents 1.0 envelope for a governance event.

    The envelope shape mirrors the agent-run-lifecycle envelope so a
    single subscriber library decodes both with the same parser.
    The ``source`` is fixed to the install-level audit prefix so
    downstream consumers can route by URL prefix without decoding.

    Args:
        event_id: Unique CloudEvents ``id`` (uuid4 hex by convention).
        event_type: One of :data:`GOVERNANCE_EVENT_TYPES`.
        data: The event payload.  Must JSON-serialise; callers are
            responsible for redaction (e.g. PII columns) before
            calling this function — the emitter does not introspect.
        fired_at: UTC timestamp the event fired.

    Returns:
        A plain dict ready to ``json.dumps``-serialise onto the wire
        with ``Content-Type: application/cloudevents+json``.
    """
    return {
        "specversion": "1.0",
        "id": event_id,
        "source": "/pointlessql/governance",
        "type": event_type,
        "time": fired_at.astimezone(datetime.UTC).isoformat(),
        "datacontenttype": "application/json",
        "subject": event_type,
        "data": dict(data),
    }


def _persist_event(
    session_factory: sessionmaker[Session],
    *,
    event_id: str,
    event_type: str,
    fired_at: datetime.datetime,
    envelope: dict[str, Any],
    initial_outcome: str,
    workspace_id: int = 1,
) -> int | None:
    """Insert one ``governance_events`` row and return its primary key.

    Args:
        session_factory: SQLAlchemy session factory.
        event_id: CloudEvents ``id`` field, unique across rows.
        event_type: One of :data:`GOVERNANCE_EVENT_TYPES`.
        fired_at: UTC timestamp the envelope was built.
        envelope: Full CloudEvents envelope.
        initial_outcome: Either ``"pending"`` (will be updated by the
            dispatcher) or ``"no_destination"`` (terminal, no
            dispatch attempted).
        workspace_id: Workspace this governance event belongs to.
            Defaults to the install-default workspace (id=1) for
            callers that haven't yet been threaded through; Phase
            29.1 routes still treat this as the routing key when
            consulting :class:`AuditSink.workspace_filter`.

    Returns:
        The new row's primary key, or ``None`` when the insert
        failed (logged-and-swallowed — an audit-sink delivery is
        best-effort relative to the originating audit row).
    """
    try:
        with session_factory() as session:
            row = GovernanceEvent(
                workspace_id=workspace_id,
                event_id=event_id,
                event_type=event_type,
                fired_at=fired_at,
                outcome=initial_outcome,
                payload_json=json.dumps(envelope, sort_keys=True),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.id
    except Exception:  # noqa: BLE001 — never raise into the caller
        logger.exception(
            "governance_events persist failed for type=%s id=%s",
            event_type,
            event_id,
        )
        return None


def _update_event_outcome(
    session_factory: sessionmaker[Session],
    *,
    row_id: int,
    outcome: str,
    delivered_to: list[dict[str, Any]],
) -> None:
    """Best-effort update the persisted event's outcome + fan-out log.

    Args:
        session_factory: SQLAlchemy session factory.
        row_id: Primary key of the row to update.
        outcome: One of ``"delivered"`` / ``"delivery_failed"``.
        delivered_to: Per-sink fan-out result entries.
    """
    try:
        with session_factory() as session:
            row = session.scalar(select(GovernanceEvent).where(GovernanceEvent.id == row_id))
            if row is None:
                return
            row.outcome = outcome
            row.delivered_to_json = json.dumps(delivered_to)
            session.commit()
    except Exception:  # noqa: BLE001 — outcome update is cosmetic
        logger.exception("governance_events outcome update failed for id=%s", row_id)


async def emit_governance_event(
    event_type: str,
    data: dict[str, Any],
    *,
    settings: Settings | None = None,
    fired_at: datetime.datetime | None = None,
    session_factory: sessionmaker[Session] | None = None,
    workspace_id: int = 1,
) -> None:
    """Build the envelope, persist it, and fan it out to every active sink.

    When ``settings.audit_stream.enabled`` is ``False`` the event is
    still persisted (durability matters) but the fan-out step is
    skipped — the row stays at ``outcome="no_destination"``.  This
    way an admin who flips the flag on later sees a complete trail
    rather than a gap.

    Failures of the fan-out step are logged but never raised — a
    flaky webhook must not break the originating audit-row write.

    Args:
        event_type: One of :data:`GOVERNANCE_EVENT_TYPES`.  Unknown
            types are logged and ignored — calling code shouldn't
            need a try/except just to be safe.
        data: The event payload (must JSON-serialise).
        settings: Optional :class:`Settings` override; defaults to a
            fresh ``Settings()`` so callers don't have to thread it
            through every layer.
        fired_at: Optional override for the event timestamp; defaults
            to ``datetime.now(UTC)``.
        session_factory: SQLAlchemy session factory.  When ``None``
            the function is a logged no-op (used by unit tests that
            drive the envelope builder in isolation).
        workspace_id: Workspace the originating event belongs to;
            persisted to ``governance_events.workspace_id`` and
            threaded into :func:`dispatch_to_sinks` so a sink with a
            non-null ``workspace_filter`` only fires for matching
            workspaces.
    """
    if event_type not in GOVERNANCE_EVENT_TYPES:
        logger.warning("emit_governance_event: ignoring unknown event_type %r", event_type)
        return
    if session_factory is None:
        logger.debug(
            "emit_governance_event: no session_factory provided, skipping %s",
            event_type,
        )
        return

    resolved_settings = settings or get_settings()
    fired_at = fired_at or datetime.datetime.now(datetime.UTC)
    event_id = uuid.uuid4().hex
    envelope = build_governance_envelope(
        event_id=event_id,
        event_type=event_type,
        data=data,
        fired_at=fired_at,
    )

    fan_out_enabled = resolved_settings.audit_stream.enabled
    initial_outcome = "pending" if fan_out_enabled else "no_destination"
    row_id = _persist_event(
        session_factory,
        event_id=event_id,
        event_type=event_type,
        fired_at=fired_at,
        envelope=envelope,
        initial_outcome=initial_outcome,
        workspace_id=workspace_id,
    )

    if not fan_out_enabled:
        return

    log = await dispatch_to_sinks(session_factory, envelope, workspace_id=workspace_id)

    if row_id is None:
        return
    if not log:
        _update_event_outcome(
            session_factory,
            row_id=row_id,
            outcome=EventOutcome.NO_DESTINATION,
            delivered_to=[],
        )
        return
    delivered = all(entry["ok"] for entry in log)
    _update_event_outcome(
        session_factory,
        row_id=row_id,
        outcome=EventOutcome.DELIVERED if delivered else EventOutcome.DELIVERY_FAILED,
        delivered_to=log,
    )


def spawn_governance_event(
    loop: asyncio.AbstractEventLoop,
    coro: Coroutine[Any, Any, None],
    *,
    label: str,
) -> None:
    """Schedule a fire-and-forget governance-event emit with an error sink.

    :func:`emit_governance_event` swallows fan-out failures but lets a
    persistence error (the ``_persist_event`` write) propagate.  On a
    ``loop.create_task`` call site there is no caller to catch that, so the
    exception would vanish into the event-loop default handler.  This wraps
    the coroutine so failures are logged, and retains a strong reference to
    the task in :data:`_background_event_tasks` so it can't be
    garbage-collected before it completes.

    Args:
        loop: The running event loop to schedule the emit on.
        coro: The ``emit_governance_event(...)`` coroutine to run.
        label: Short identifier included in the failure log line.
    """

    async def _runner() -> None:
        try:
            await coro
        except Exception:  # noqa: BLE001
            # bare-broad-ok: fire-and-forget emit — the originating write
            # already succeeded and the caller can't act on this failure.
            logger.exception("governance event emit failed: %s", label)

    task = loop.create_task(_runner())
    _background_event_tasks.add(task)
    task.add_done_callback(_background_event_tasks.discard)
