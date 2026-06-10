"""Computational policy-as-code: Cedar modules + per-evaluation ledger.

Two tables that turn governance from JSON-shaped policy fields into
executable Cedar modules with an auditable decision trail:

* ``policy_modules`` — authored Cedar source.  One row per module,
  workspace-scoped, name-unique inside the workspace.  ``version`` is
  bumped by the engine cache whenever ``cedar_source`` changes; an
  ``enabled=False`` row is excluded from policy-set assembly.
* ``policy_module_decisions`` — one row per Cedar ``is_authorized``
  call.  Drives the decision-log surface and post-hoc compliance
  review.  Persisted async; never on the request critical path.

The link to a data-product or workspace lives in the existing policy
rows as the JSON column ``linked_policy_module_ids`` (introduced in
the same migration).  Linking, not foreign-key explosion, keeps the
join-graph flat and lets a single module serve multiple products.
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

#: Outcomes a Cedar evaluation can produce.  ``permit`` and ``forbid``
#: mirror Cedar's ``Decision.Allow`` / ``Decision.Deny``; the platform
#: treats parse / runtime errors as ``forbid`` (fail-closed).
POLICY_MODULE_EFFECTS: tuple[str, ...] = ("permit", "forbid")


class PolicyModule(Base):
    """Authored, versioned Cedar module bound to one workspace.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Workspace this module belongs to; FK on
            ``workspaces.id`` with CASCADE.
        name: Human-readable module name; unique inside the workspace.
        cedar_source: Cedar policy source (one or more ``permit`` /
            ``forbid`` statements).
        version: Monotonic version, bumped on every source edit;
            the engine cache keys parsed ASTs on
            ``(module_id, version)``.
        enabled: Whether the module participates in policy-set
            assembly.  Disabled modules stay around for re-enable.
        created_by_user_id: Nullable FK on ``users.id``.
        created_at: Wall-clock the row was first inserted.
        updated_at: Wall-clock of the last edit.
    """

    __tablename__ = "policy_modules"

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_policy_modules_ws_name"),
        Index("ix_policy_modules_ws", "workspace_id", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    cedar_source: Mapped[str] = mapped_column(Text(), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PolicyModuleDecision(Base):
    """One row per Cedar ``is_authorized`` evaluation.

    Attributes:
        id: Auto-incremented primary key.
        policy_module_id: FK on ``policy_modules.id`` with CASCADE.
        workspace_id: Workspace the request ran in; FK on
            ``workspaces.id`` with CASCADE.  Denormalised for fast
            per-workspace decision-log queries.
        decision_at: Wall-clock the evaluation finished.
        principal_user_id: Nullable FK on ``users.id`` — the
            principal Cedar evaluated against.  ``None`` for system
            calls or unauthenticated paths.
        action: Cedar action segment (e.g. ``read``, ``write``,
            ``consume``).
        resource_type: Cedar resource type segment (e.g.
            ``DataProduct``, ``OutputPort``).
        resource_id: Cedar resource id segment (e.g. ``main.silver``).
        effect: ``permit`` or ``forbid``.  Parse / runtime errors are
            persisted as ``forbid`` with the error class in the
            context json so fail-closed is observable.
        context_json: Optional JSON-shaped context blob; carries the
            request-context dict + error-class tag on failure.
        latency_ms: Evaluation latency in milliseconds; ``None`` when
            the engine never returned (parse error before evaluate).
    """

    __tablename__ = "policy_module_decisions"

    __table_args__ = (
        CheckConstraint(
            "effect IN ('permit','forbid')",
            name="ck_policy_module_decisions_effect",
        ),
        Index(
            "ix_policy_module_decisions_module",
            "policy_module_id",
            "decision_at",
        ),
        Index(
            "ix_policy_module_decisions_principal",
            "principal_user_id",
            "decision_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    policy_module_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("policy_modules.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    decision_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    principal_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    effect: Mapped[str] = mapped_column(String(8), nullable=False)
    context_json: Mapped[str | None] = mapped_column(Text(), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
