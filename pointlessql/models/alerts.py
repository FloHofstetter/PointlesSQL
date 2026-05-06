"""Alert, alert-event, and alert-destination ORM models."""

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
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class Alert(Base):
    """A scheduled condition check against a saved query.

    An alert fires when ``row_count`` of its saved query, evaluated on
    the configured cron, satisfies ``condition_op threshold``.  Each
    firing records one :class:`AlertEvent` and fans out to every
    enabled :class:`AlertDestination` via
    :mod:`pointlessql.services.alert_dispatcher`.

    The scheduler drives alerts through a hidden backing :class:`Job`
    created when ``is_active`` flips to ``True``; see
    :func:`pointlessql.services.scheduler._alert_check_executor`.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: FK to :class:`Workspace`.  Every alert lives
            in exactly one workspace.
        slug: URL-safe identifier (unique across tenants).
        title: Human-readable name shown in the UI.
        saved_query_id: FK to :class:`SavedQuery` that produces the
            ``row_count`` the condition compares.
        owner_id: FK to :class:`User` — the "run-as" identity used by
            the executor so UC enforcement applies.
        cron_expr: 5-field croniter expression.  Minute granularity.
        condition_op: One of ``gt`` / ``lt`` / ``eq`` / ``ne``.
        threshold: Integer compared against the result ``row_count``.
        is_active: Scheduler skips inactive alerts.
        backing_job_id: FK to :class:`Job`.  Materialised when the
            alert is first activated; cleared on deletion.
        created_at: Timestamp when the alert was created.
        updated_at: Timestamp of the most recent mutation.
    """

    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_owner", "owner_id"),
        Index("ix_alerts_workspace_owner", "workspace_id", "owner_id"),
        CheckConstraint(
            "condition_op IN ('gt','lt','eq','ne')",
            name="ck_alerts_condition_op",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Every alert lives in exactly one workspace.
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    saved_query_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("saved_queries.id"), nullable=False
    )
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    cron_expr: Mapped[str] = mapped_column(String(120), nullable=False)
    condition_op: Mapped[str] = mapped_column(String(8), nullable=False)
    threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    backing_job_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("jobs.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AlertDestination(Base):
    """A single sink that receives a fired :class:`Alert`'s CloudEvents envelope.

    Two kinds: ``webhook`` (outbound POST with optional HMAC-SHA256
    signing) and ``feed`` (the per-owner Atom / JSON Feed surface,
    which reads from :class:`AlertEvent` directly — there is nothing
    to ``POST``).  Per-destination ``hmac_secret`` is plaintext MVP;
    encrypted-at-rest is a follow-up.

    Attributes:
        id: Auto-incremented primary key.
        alert_id: FK to :class:`Alert`.
        kind: ``webhook`` or ``feed``.
        webhook_url: Non-empty when ``kind == "webhook"``.
        hmac_secret: Optional shared secret; when set, the dispatcher
            signs the body and attaches the
            ``X-PointlesSQL-Signature: sha256=<hex>`` header.
        is_active: The dispatcher skips inactive destinations.
        created_at: Timestamp.
    """

    __tablename__ = "alert_destinations"
    __table_args__ = (
        Index("ix_alert_destinations_alert", "alert_id"),
        Index("ix_alert_destinations_kind", "kind"),
        CheckConstraint(
            "kind IN ('webhook','feed')",
            name="ck_alert_destinations_kind",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(Integer, ForeignKey("alerts.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    webhook_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    hmac_secret: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AlertEvent(Base):
    """One firing of an :class:`Alert`.

    The ``payload_json`` column stores the full CloudEvents 1.0
    envelope verbatim so feed renderers and debug replays can work
    without reconstruction.  ``outcome`` is ``fired`` when the
    condition matched, ``suppressed`` for future dedup logic, or
    ``delivery_failed`` once at least one destination has exhausted
    its retries.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: FK to :class:`Workspace`.  Denormalised from the
            parent :class:`Alert` for workspace-scoped queries.
        alert_id: FK to :class:`Alert`.
        event_id: CloudEvents ``id`` (uuid4 hex, unique).
        fired_at: Timestamp the executor evaluated the condition.
        row_count: The ``row_count`` that satisfied the condition, or
            ``None`` when the underlying query failed.
        outcome: ``fired`` / ``suppressed`` / ``delivery_failed``.
        payload_json: Full CloudEvents envelope (``application/
            cloudevents+json``) as serialised JSON.
    """

    __tablename__ = "alert_events"
    __table_args__ = (
        Index("ix_alert_events_fired", "alert_id", "fired_at"),
        Index("ix_alert_events_workspace_alert", "workspace_id", "alert_id"),
        CheckConstraint(
            "outcome IN ('fired','suppressed','delivery_failed')",
            name="ck_alert_events_outcome",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Denormalised from parent Alert.
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    alert_id: Mapped[int] = mapped_column(Integer, ForeignKey("alerts.id"), nullable=False)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    fired_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
