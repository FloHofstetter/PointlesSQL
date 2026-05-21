"""Polymorphic social-target anchor (Phase 77.0).

Every social row (comment / review / endorsement / follow /
reaction / readme / star / pin) keys on
``social_targets.id``.  The anchor row carries the polymorphic
discriminator ``entity_kind`` plus an opaque ``entity_ref``
string that addresses the underlying entity:

* ``dp`` — ``entity_ref = "{catalog}.{schema}"``, plus the
  optional ``data_product_id`` back-pointer that preserves
  CASCADE-on-DP-delete for the historical rows.
* ``table`` — ``entity_ref = "{catalog}.{schema}.{table}"``,
  ``data_product_id = NULL``.
* ``model`` — ``entity_ref = "{catalog}.{schema}.{name}"``,
  ``data_product_id = NULL``.
* ``branch`` — ``entity_ref`` = the branch schema FQN
  (``catalog.schema__branch_xxx``), ``data_product_id = NULL``.
* ``run`` — ``entity_ref`` = the run UUID, no DP back-pointer.
* ``schema`` / ``catalog`` / ``query`` / ``notebook`` /
  ``saved_query`` / ``issue`` / ``workspace`` — same pattern.

The two CHECK constraints (kind whitelist + dp back-pointer
parity) keep the row shape consistent: a kind='dp' row always
carries a ``data_product_id``, every other kind never does.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
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

ENTITY_KINDS: tuple[str, ...] = (
    "dp",
    "table",
    "schema",
    "catalog",
    "model",
    "branch",
    "run",
    "query",
    "notebook",
    "saved_query",
    "issue",
    "workspace",
    "agent_memory",
    "notebook_cell",
    "notebook_revision",
    "notebook_cell_output",
)


class SocialTarget(Base):
    """One anchor row addressing a single platform entity.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Tenant scope.  Same kind+ref pair under
            two workspaces gets two anchor rows (followers do
            not bleed across workspaces).
        entity_kind: Polymorphic discriminator — one of
            :data:`ENTITY_KINDS`.
        entity_ref: Opaque string that addresses the entity
            *within* its kind (see module docstring for the
            shape per kind).
        data_product_id: Optional back-pointer to
            ``data_products.id`` with ``ondelete=CASCADE``.  Set
            iff ``entity_kind='dp'``; preserves the original
            Phase-76 behaviour where deleting a DP cleans up its
            social rows.  ``NULL`` for every other kind.
        created_at: Wall-clock when the anchor row was created.
    """

    __tablename__ = "social_targets"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "entity_kind",
            "entity_ref",
            name="uq_social_targets_entity",
        ),
        CheckConstraint(
            "entity_kind IN ("
            "'dp', 'table', 'schema', 'catalog', "
            "'model', 'branch', 'run', 'query', "
            "'notebook', 'saved_query', 'issue', "
            "'workspace', 'agent_memory', 'notebook_cell', "
            "'notebook_revision', 'notebook_cell_output'"
            ")",
            name="ck_social_targets_kind",
        ),
        CheckConstraint(
            "(entity_kind = 'dp' AND data_product_id IS NOT NULL) "
            "OR (entity_kind <> 'dp' AND data_product_id IS NULL)",
            name="ck_social_targets_dp_backref",
        ),
        Index(
            "ix_social_targets_kind_ref",
            "entity_kind",
            "entity_ref",
        ),
        Index(
            "ix_social_targets_dp",
            "data_product_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
        server_default="1",
    )
    entity_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    data_product_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
