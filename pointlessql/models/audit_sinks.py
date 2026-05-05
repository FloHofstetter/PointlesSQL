"""Audit-stream sink + governance-event ORM models.

Two tables that together implement 's audit-stream forwarder:

* :class:`AuditSink` — admin-configured destination for governance
  CloudEvents.  Three sink types (``webhook``, ``s3``,
  ``aws_cloudtrail``); each sink owns a JSON ``config_json`` blob
  whose shape is type-specific (URL+optional HMAC for webhook,
  ``{bucket, prefix, region, access_key_id, secret_access_key}`` for
  s3, ``{region, event_source, access_key_id, secret_access_key}``
  for aws_cloudtrail).  ``event_types_json`` is an optional allow-
  list of CloudEvent type strings; an empty/null list means "every
  event".
* :class:`GovernanceEvent` — persisted CloudEvents envelope for any
  event that is *not* tied to a specific agent run (audit-export,
  lineage-prune, cost-gate-denial, external-write detection, policy
  violation).  Mirrors :class:`AgentRunEvent` shape but FK-free so
  governance events can fire from anywhere.

Run-tied lifecycle events keep flowing through
:class:`AgentRunEvent` exactly as before; the new
:func:`pointlessql.services.audit_sinks.dispatch_to_sinks` helper
simply gains those envelopes as an additional fan-out destination.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

SINK_TYPES: frozenset[str] = frozenset({"webhook", "s3", "aws_cloudtrail"})
"""Allowed values for :attr:`AuditSink.type`.

Webhook reuses the saved-query webhook pipeline (HMAC + retries).
S3 uploads one JSON object per envelope under a date-prefixed key.
AWS CloudTrail posts via the PutEvents API.
"""


class AuditSink(Base):
    """One audit-stream destination: webhook, S3 bucket, or CloudTrail.

    Attributes:
        id: Auto-incremented primary key.
        name: Admin-facing label, unique across the install.
        type: One of :data:`SINK_TYPES`.  CHECK-constrained.
        config_json: Type-specific JSON blob.  Schemas:

            * ``webhook``:
              ``{"url": str, "hmac_secret": str | null}``.
            * ``s3``:
              ``{"bucket": str, "prefix": str, "region": str,
                 "access_key_id": str, "secret_access_key": str,
                 "endpoint_url": str | null}``.  ``endpoint_url``
              lets the same sink type talk to S3-compatible stores
              like MinIO or Cloudflare R2.
            * ``aws_cloudtrail``:
              ``{"region": str, "event_source": str,
                 "access_key_id": str, "secret_access_key": str}``.

            Secrets at rest are plaintext for the MVP — same posture
            as :class:`pointlessql.models.alerts.AlertDestination`'s
            ``hmac_secret``.  Encrypt-at-rest is a +
            follow-up.
        is_active: Inactive sinks are skipped by the dispatcher.
        event_types_json: Optional JSON-encoded list of
            ``"pointlessql.<…>"`` event-type strings the sink wants
            to receive.  ``None`` or ``"[]"`` means *every* event
            type fires the sink — easiest setup for "log everything"
            destinations like a compliance archive bucket.
        workspace_filter: Optional JSON-encoded list of workspace
            IDs the sink serves.  ``None`` (the default) preserves
            install-global behaviour: every workspace's events fire
            the sink.  ``[1, 2]`` restricts the sink to events whose
            ``workspace_id`` matches one of the listed values.
            Phase 29.1.
        created_at: Insert timestamp.
    """

    __tablename__ = "audit_sinks"
    __table_args__ = (
        Index("ix_audit_sinks_active", "is_active"),
        UniqueConstraint("name", name="uq_audit_sinks_name"),
        CheckConstraint(
            "type IN ('webhook','s3','aws_cloudtrail')",
            name="ck_audit_sinks_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    event_types_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    workspace_filter: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GovernanceEvent(Base):
    """One persisted governance CloudEvents envelope.

    Lives parallel to :class:`AgentRunEvent` but FK-free so events
    not tied to a single run (audit-export, lineage-prune, ...) have
    a durable home.  The row is INSERTed with
    ``outcome = "pending"`` *before* fan-out; the dispatcher updates
    it to ``"delivered"`` once *every* enabled sink ACKs, or
    ``"delivery_failed"`` if at least one sink returned non-2xx
    (per-sink results live in ``delivered_to_json``).
    ``"no_destination"`` means zero matching sinks were registered at
    fire time.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Workspace this governance event belongs to
            (Phase 28.1b).  Resolved from request.state at insert
            time.  ``audit_sinks`` themselves stay install-global
            on purpose — one Slack/webhook/S3 destination per
            install — but the events fanned out to those sinks
            carry the workspace context so downstream consumers
            can filter.
        event_id: CloudEvents ``id`` field, unique across rows.
        event_type: One of the governance event constants exported
            from
            :mod:`pointlessql.services.governance_events`.
        fired_at: When the envelope was built.
        outcome: ``pending`` | ``delivered`` | ``delivery_failed`` |
            ``no_destination``.  CHECK-constrained.
        payload_json: Full CloudEvents 1.0 envelope as JSON text,
            for replay and debug.
        delivered_to_json: Optional JSON list of fan-out result
            entries, shape
            ``{sink_id, name, type, delivered_at, ok}``.
    """

    __tablename__ = "governance_events"
    __table_args__ = (
        Index("ix_governance_events_fired", "event_type", "fired_at"),
        Index("ix_governance_events_workspace_fired", "workspace_id", "fired_at"),
        CheckConstraint(
            "outcome IN ('pending','delivered','delivery_failed','no_destination')",
            name="ck_governance_events_outcome",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
        server_default="1",
    )
    event_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    fired_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    delivered_to_json: Mapped[str | None] = mapped_column(Text, nullable=True)
