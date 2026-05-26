"""CDF tail subscription registry + captured event log.

Pull-model counterpart to the push-model
``POST /api/lineage/openlineage`` endpoint.  Admins register one
:class:`CdfTailSubscription` per Delta table whose Change Data Feed
they want PointlesSQL to tail; a background worker advances each
subscription's pointer over time and INSERT-OR-IGNOREs every row
into :class:`CdfTailEvent`.

Both tables sit in the PointlesSQL metadata DB (not soyuz).  The
registry stays small (one row per opted-in foreign Delta table) and
the event log is bounded by how busy the foreign producer is —
identical economics to ``audit_log`` and ``unattributed_writes``.
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
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class CdfTailSubscription(Base):
    """One opt-in CDF subscription against a Delta table.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Workspace this subscription belongs to.
        table_full_name: Three-part UC name of the table whose CDF
            should be tailed.  Resolved via ``uc.get_table`` to a
            ``storage_location`` per worker tick.
        row_id_column: Column name on the foreign table that the
            tail uses as row identity.  Operator-supplied because
            foreign tables have no PointlesSQL ``_lineage_row_id``
            convention; common picks are ``"id"`` or a natural key.
        producer_label: Free-form label written into
            :class:`CdfTailEvent.producer_label`.  Defaults to
            ``cdf-tail:<table_full_name>`` when the operator
            supplies an empty string.
        last_version_processed: Highest ``delta_version`` the worker
            has processed; ``None`` means "tail everything from the
            current minimum readable version".  Re-tails are
            idempotent because of the UNIQUE on
            :class:`CdfTailEvent`.
        is_active: Pause toggle — inactive rows skip the worker tick
            but stay registered for audit history.
        last_tailed_at: Wall-clock of the most recent worker tick
            (success or failure).
        last_error: Truncated error message from the most recent
            failing tick.  ``None`` when the last tick succeeded.
        created_at: Wall-clock the row was registered.
    """

    __tablename__ = "cdf_tail_subscriptions"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "table_full_name",
            name="uq_cdf_tail_subscriptions_ws_table",
        ),
        Index(
            "ix_cdf_tail_subscriptions_workspace_active",
            "workspace_id",
            "is_active",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
        server_default="1",
    )
    table_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    row_id_column: Mapped[str] = mapped_column(String(128), nullable=False)
    producer_label: Mapped[str] = mapped_column(String(255), nullable=False)
    last_version_processed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    last_tailed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CdfTailEvent(Base):
    """One captured Delta CDF row from a foreign table.

    Each row represents one
    ``(table_full_name, delta_version, row_id, change_type)`` tuple
    extracted from ``DeltaTable.load_cdf(...).read_all()``.  The
    UNIQUE on that 4-tuple makes the worker re-tail idempotent — a
    crash mid-version replays the same range on next startup
    without duplicates.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Workspace the event belongs to (denormalised
            from the parent subscription).
        subscription_id: FK to :class:`CdfTailSubscription`.
            ``ON DELETE CASCADE`` so removing a subscription cleans
            up its history.
        table_full_name: Denormalised from the subscription so
            row-trace UI joins don't need the subscription table.
        delta_version: Delta commit version this row came from.
        row_id: Stringified value of the subscription's
            ``row_id_column`` for this row.  ``str`` cast applied
            at capture time so downstream queries don't need to
            care about the source column dtype.
        change_type: One of ``insert`` / ``update_preimage`` /
            ``update_postimage`` / ``delete`` per the Delta CDF
            spec.  CHECK-constrained.
        producer_label: Copied from
            :class:`CdfTailSubscription.producer_label` at tick
            time; preserves attribution if the subscription's
            label is later edited.
        commit_timestamp: Wall-clock of the Delta commit (epoch ms
            in CDF, parsed to UTC); ``None`` when CDF didn't
            surface one.
        created_at: Wall-clock of the worker tick that wrote this
            row.
    """

    __tablename__ = "cdf_tail_events"

    __table_args__ = (
        UniqueConstraint(
            "table_full_name",
            "delta_version",
            "row_id",
            "change_type",
            name="uq_cdf_tail_events_table_version_row_kind",
        ),
        CheckConstraint(
            "change_type IN ('insert','update_preimage','update_postimage','delete')",
            name="ck_cdf_tail_events_change_type",
        ),
        Index(
            "ix_cdf_tail_events_table_version",
            "table_full_name",
            "delta_version",
        ),
        Index(
            "ix_cdf_tail_events_row",
            "table_full_name",
            "row_id",
        ),
        Index(
            "ix_cdf_tail_events_workspace_created",
            "workspace_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
        server_default="1",
    )
    subscription_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("cdf_tail_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    table_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    delta_version: Mapped[int] = mapped_column(Integer, nullable=False)
    row_id: Mapped[str] = mapped_column(String(255), nullable=False)
    change_type: Mapped[str] = mapped_column(String(32), nullable=False)
    producer_label: Mapped[str] = mapped_column(String(255), nullable=False)
    commit_timestamp: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
