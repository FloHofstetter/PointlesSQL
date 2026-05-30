"""Per-product computational-governance policy-as-code.

Four tables that turn governance from central access checks into
declarative, per-product policy the platform executes at the access
point:

* ``workspace_governance_policies`` — workspace-wide *default* policy
  (one row per workspace).  Products inherit these values unless they
  override them, so a single change applies mesh-wide.
* ``data_product_policies`` — per-product override of the policy
  fields (retention, encryption class, residency, consent).  Every
  field is nullable; ``NULL`` means "inherit the workspace default".
  One row per product.
* ``data_product_column_classifications`` — the confidentiality class
  of a single UC column (``catalog.schema.table.column``).  The class
  drives read-time masking at the product's output ports; an optional
  ``masking_strategy`` overrides the per-class default.
* ``data_product_forget_requests`` — the right-to-be-forgotten ledger.
  A request names a subject column + value (stored *hashed* — the
  ledger must never itself leak the subject); a steward/admin executes
  it, deleting matching rows across the product's declared tables.

Only retention monitoring, read-time masking, and right-to-be-forgotten
are actually *enforced* at runtime; encryption class, residency, and
consent are honest declarations surfaced in the discovery contract and
the compliance scan (a single-node Python app does not control at-rest
crypto or geo placement).

Storage decision: PointlesSQL metadata DB.  Edited via the
steward/admin API + agent plugin tools, mirroring how ports and
classifications are authored — agents propose, owners approve.
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

#: Confidentiality classes a column can carry, least → most sensitive.
#: ``pii`` and ``phi`` always mask for non-privileged viewers;
#: ``confidential`` hashes; ``internal``/``public`` are visible.
CLASSIFICATIONS: tuple[str, ...] = (
    "public",
    "internal",
    "confidential",
    "pii",
    "phi",
)

#: How a classified column is rendered to a viewer who may not see it
#: in the clear.  ``none`` passes through; ``hash`` HMACs the value;
#: ``partial`` keeps the value's shape (e.g. ``***@***.***``);
#: ``full`` replaces the whole value; ``null`` blanks it.
MASKING_STRATEGIES: tuple[str, ...] = ("none", "hash", "partial", "full", "null")

#: Declared encryption posture of a product's data.  Declaration only —
#: the platform surfaces + monitors it but does not perform the crypto.
ENCRYPTION_CLASSES: tuple[str, ...] = ("none", "at_rest", "in_transit", "full")

#: Lifecycle of a right-to-be-forgotten request.  Agents create
#: ``proposed`` rows; a steward/admin transitions them to ``executed``
#: (the deletion ran) or ``rejected``.
FORGET_STATUSES: tuple[str, ...] = ("proposed", "executed", "rejected")

#: Allowed values for ``consumption_enforcement`` on both
#: :class:`WorkspaceGovernancePolicy` and :class:`DataProductPolicy`.
#: ``off`` — disabled, ``advisory`` — warn + audit, ``strict`` — block.
CONSUMPTION_ENFORCEMENT_MODES: tuple[str, ...] = ("off", "advisory", "strict")


class WorkspaceGovernancePolicy(Base):
    """Workspace-wide default policy that products inherit.

    One row per workspace.  A product's effective policy is its own
    override value, falling back to this default, falling back to
    "unset".  Editing this row applies the change mesh-wide to every
    product that has not overridden the field.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Workspace this default applies to.  FK on
            ``workspaces.id``; unique; ``server_default='1'`` so a
            fresh single-tenant install adopts the seeded default
            workspace without a data migration.
        retention_days: Default retention window in days; ``None``
            means "no retention expectation".
        encryption_class: One of :data:`ENCRYPTION_CLASSES`; ``None``
            when undeclared.
        residency_region: Free-form geo constraint (e.g. ``eu-central``);
            declaration only.
        consent_required: Whether consumption requires recorded consent.
        consent_basis: Free-form legal basis note (nullable).
        updated_by_user_id: Nullable FK on ``users.id``.
        created_at: Wall-clock the row was first inserted.
        updated_at: Wall-clock of the last edit.
    """

    __tablename__ = "workspace_governance_policies"

    __table_args__ = (
        UniqueConstraint("workspace_id", name="uq_workspace_governance_policies_ws"),
        CheckConstraint(
            "encryption_class IS NULL OR "
            "encryption_class IN ('none','at_rest','in_transit','full')",
            name="ck_workspace_governance_policies_encryption",
        ),
        CheckConstraint(
            "consumption_enforcement IN ('off','advisory','strict')",
            name="ck_workspace_governance_policies_consumption",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
        server_default="1",
    )
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    encryption_class: Mapped[str | None] = mapped_column(String(16), nullable=True)
    residency_region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    consent_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    consent_basis: Mapped[str | None] = mapped_column(String(200), nullable=True)
    consumption_enforcement: Mapped[str] = mapped_column(
        String(16), nullable=False, default="advisory", server_default="advisory"
    )
    iso8601_enforcement: Mapped[str] = mapped_column(
        String(8), nullable=False, default="warn", server_default="warn"
    )
    linked_policy_module_ids: Mapped[str | None] = mapped_column(
        Text(), nullable=True
    )
    breaking_change_policy: Mapped[str] = mapped_column(
        String(8), nullable=False, default="warn", server_default="warn"
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DataProductPolicy(Base):
    """Per-product override of the workspace default policy.

    One row per product.  Each field is nullable; a ``NULL`` field
    inherits the matching :class:`WorkspaceGovernancePolicy` value.
    The effective-policy resolver layers product → workspace → unset.

    Attributes:
        id: Auto-incremented primary key.
        data_product_id: FK on ``data_products.id`` with CASCADE
            delete; unique (one policy row per product).
        retention_days: Override retention window in days.
        encryption_class: Override encryption class
            (:data:`ENCRYPTION_CLASSES`).
        residency_region: Override geo constraint.
        consent_required: Override consent requirement; ``None`` here
            inherits the workspace value.
        consent_basis: Override legal-basis note.
        updated_by_user_id: Nullable FK on ``users.id``.
        created_at: Wall-clock the row was first inserted.
        updated_at: Wall-clock of the last edit.
    """

    __tablename__ = "data_product_policies"

    __table_args__ = (
        UniqueConstraint("data_product_id", name="uq_data_product_policies_product"),
        CheckConstraint(
            "encryption_class IS NULL OR "
            "encryption_class IN ('none','at_rest','in_transit','full')",
            name="ck_data_product_policies_encryption",
        ),
        CheckConstraint(
            "consumption_enforcement IS NULL OR "
            "consumption_enforcement IN ('off','advisory','strict')",
            name="ck_data_product_policies_consumption",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    encryption_class: Mapped[str | None] = mapped_column(String(16), nullable=True)
    residency_region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    consent_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    consent_basis: Mapped[str | None] = mapped_column(String(200), nullable=True)
    consumption_enforcement: Mapped[str | None] = mapped_column(String(16), nullable=True)
    iso8601_enforcement: Mapped[str | None] = mapped_column(String(8), nullable=True)
    linked_policy_module_ids: Mapped[str | None] = mapped_column(
        Text(), nullable=True
    )
    breaking_change_policy: Mapped[str | None] = mapped_column(
        String(8), nullable=True
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DataProductColumnClassification(Base):
    """Confidentiality class of one UC column inside a product.

    The class drives read-time masking at the product's access points
    (export port, table preview, SQL results) for viewers who may not
    see the column in the clear.  ``masking_strategy`` overrides the
    per-class default when set.

    Attributes:
        id: Auto-incremented primary key.
        data_product_id: FK on ``data_products.id`` with CASCADE
            delete.
        catalog: UC catalog segment.
        schema_name: UC schema segment.
        table_name: UC table name (last segment).
        column_name: UC column name.
        classification: One of :data:`CLASSIFICATIONS`.
        masking_strategy: Optional override
            (:data:`MASKING_STRATEGIES`); ``None`` derives the strategy
            from ``classification``.
        created_by_user_id: Nullable FK on ``users.id``.
        created_at: Wall-clock the classification was declared.
    """

    __tablename__ = "data_product_column_classifications"

    __table_args__ = (
        UniqueConstraint(
            "data_product_id",
            "catalog",
            "schema_name",
            "table_name",
            "column_name",
            name="uq_dp_classifications_identity",
        ),
        Index(
            "ix_dp_classifications_lookup",
            "catalog",
            "schema_name",
            "table_name",
            "column_name",
        ),
        Index("ix_dp_classifications_product", "data_product_id"),
        CheckConstraint(
            "classification IN ('public','internal','confidential','pii','phi')",
            name="ck_dp_classifications_class",
        ),
        CheckConstraint(
            "masking_strategy IS NULL OR "
            "masking_strategy IN ('none','hash','partial','full','null')",
            name="ck_dp_classifications_strategy",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    catalog: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(255), nullable=False)
    table_name: Mapped[str] = mapped_column(String(255), nullable=False)
    column_name: Mapped[str] = mapped_column(String(255), nullable=False)
    classification: Mapped[str] = mapped_column(String(16), nullable=False)
    masking_strategy: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DataProductForgetRequest(Base):
    """Right-to-be-forgotten ledger row for one data subject.

    Records a privileged control-port operation: delete a subject's
    rows across the product's declared tables.  The subject value is
    stored *hashed* (HMAC) so the audit ledger never itself leaks the
    PII it exists to erase.  Agents may create ``proposed`` rows; a
    steward/admin executes the deletion directly.

    Attributes:
        id: Auto-incremented primary key.
        data_product_id: FK on ``data_products.id`` with CASCADE
            delete.
        subject_column: The column identifying the data subject (e.g.
            ``customer_id``).
        subject_value_hash: HMAC of the subject value — never the raw
            value.
        status: One of :data:`FORGET_STATUSES`.
        tables_affected_json: JSON list of ``catalog.schema.table``
            the deletion touched; ``[]`` until executed.
        rows_deleted: Total rows removed; ``None`` until executed.
        requested_by_user_id: Nullable FK on ``users.id`` (the
            proposer; ``None`` for agent proposals without a user).
        agent_run_id: Nullable FK on ``agent_runs.id`` (SET NULL on
            delete) when an agent proposed the request.
        executed_by_user_id: Nullable FK on ``users.id`` (the steward
            who ran it).
        executed_at: Wall-clock the deletion ran; ``None`` until then.
        created_at: Wall-clock the request was created.
    """

    __tablename__ = "data_product_forget_requests"

    __table_args__ = (
        Index("ix_dp_forget_product", "data_product_id"),
        CheckConstraint(
            "status IN ('proposed','executed','rejected')",
            name="ck_dp_forget_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    subject_column: Mapped[str] = mapped_column(String(255), nullable=False)
    subject_value_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="proposed", server_default="proposed"
    )
    tables_affected_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    rows_deleted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    agent_run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    executed_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    executed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
