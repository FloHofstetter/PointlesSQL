"""Draft ``pointlessql.yaml`` file tracking rows (Phase 73.1).

Tracks every yaml draft authored by Phase 73 surfaces:

* ``source_kind='candidate_generate'`` — Sprint 73.1's
  "Generate draft yaml" flow on the candidates page.
* ``source_kind='pql_contract'`` — Sprint 73.2's notebook
  ``pql.contract(...).save()`` call.
* ``source_kind='agent_proposal'`` — Sprint 73.3's schema-
  change proposal approval (draft path).

The draft file lives on disk under
``settings.data_products.draft_dir``.  Admin promotes a draft
by copying it into a ``yaml_search_paths`` entry; the
``promote`` endpoint stamps ``promoted_at`` +
``promoted_to_data_product_id`` and triggers the existing
loader so the cache catches up immediately.
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
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

YAML_DRAFT_SOURCE_KINDS: tuple[str, ...] = (
    "candidate_generate",
    "pql_contract",
    "agent_proposal",
)


class DataProductYamlDraft(Base):
    """One yaml draft authored by a Phase-73 surface.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Tenant scope.
        catalog_name: UC catalog segment in the draft.
        schema_name: UC schema segment in the draft.
        draft_path: Absolute path to the yaml file on disk
            (under ``settings.data_products.draft_dir``).
        source_kind: One of
            :data:`YAML_DRAFT_SOURCE_KINDS`.  CHECK at DB.
        created_by_user_id: Author user.  NULL when an
            agent-run authored it without a session.
        created_by_agent_run_id: Author agent run.  NULL for
            human-authored drafts.
        created_at: Wall-clock at insert.
        promoted_at: Wall-clock when an admin promoted the
            draft to an active ``pointlessql.yaml``.
        promoted_to_data_product_id: FK on the resulting
            DataProduct row.  NULL until promoted.
        discarded_at: Wall-clock when the draft was soft-
            discarded.  Mutually exclusive with
            ``promoted_at``.
        yaml_hash: SHA-256 of the yaml content.  UNIQUE with
            ``(workspace_id, catalog_name, schema_name)`` so
            two identical drafts collapse into one row.
    """

    __tablename__ = "data_product_yaml_drafts"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "catalog_name",
            "schema_name",
            "yaml_hash",
            name="uq_dp_yaml_draft_content",
        ),
        Index(
            "ix_dp_yaml_draft_ws_open",
            "workspace_id",
            "catalog_name",
            "schema_name",
        ),
        CheckConstraint(
            "source_kind IN ('candidate_generate', 'pql_contract', "
            "'agent_proposal')",
            name="ck_dp_yaml_draft_source",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
        server_default="1",
    )
    catalog_name: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(255), nullable=False)
    draft_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_by_agent_run_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    promoted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    promoted_to_data_product_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="SET NULL"),
        nullable=True,
    )
    discarded_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    yaml_hash: Mapped[str] = mapped_column(String(64), nullable=False)
