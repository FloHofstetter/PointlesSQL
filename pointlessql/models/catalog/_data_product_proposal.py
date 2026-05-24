"""Schema-change proposal rows for DPs.

Both agents and humans can propose schema changes to an
existing :class:`DataProduct`.  Steward + install-admin
approve or reject.  Approval routes either rewrite the yaml
in-place (for safe deltas) or drop a draft yaml under
``draft_dir`` (for everything else).

Distinct from :class:`AgentReview` — that model is
audit-review-oriented (severity / period bounds / kind enum)
not write-proposal oriented.
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
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

PROPOSAL_STATUSES: tuple[str, ...] = (
    "open",
    "approved_inplace",
    "approved_draft",
    "rejected",
)


class DataProductSchemaProposal(Base):
    """One typed proposal authored by an agent or a human.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Tenant scope.
        data_product_id: FK on ``data_products.id`` with
            ``ondelete='CASCADE'``.
        proposer_user_id: Nullable FK on ``users.id``.  Set when
            a human authored the proposal via the session-cookie
            path.
        proposer_agent_run_id: Nullable FK on ``agent_runs.id``.
            Set when an agent authored via the
            ``X-Agent-Run-Id`` header path.  CHECK at row level
            ensures at least one of the two is set.
        diff_json: Serialised diff payload:
            ``{add_columns: [...], remove_columns: [...],
            change_columns: [...]}`` per table.
        summary_md: Short markdown summary of the change.
        status: One of :data:`PROPOSAL_STATUSES`.  CHECK at DB.
        created_at: Wall-clock at insert.
        resolved_at: Wall-clock at approve / reject.
        resolved_by_user_id: FK on ``users.id``.  Set on
            resolution.
        resolution_note_md: Free-form reviewer note.
    """

    __tablename__ = "data_product_schema_proposals"

    __table_args__ = (
        Index(
            "ix_dp_proposal_ws_status",
            "workspace_id",
            "status",
        ),
        Index(
            "ix_dp_proposal_dp_status",
            "data_product_id",
            "status",
        ),
        CheckConstraint(
            "status IN ('open', 'approved_inplace', "
            "'approved_draft', 'rejected')",
            name="ck_dp_proposal_status",
        ),
        CheckConstraint(
            "(proposer_user_id IS NOT NULL) OR "
            "(proposer_agent_run_id IS NOT NULL)",
            name="ck_dp_proposal_proposer_present",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
        server_default="1",
    )
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    proposer_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    proposer_agent_run_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    diff_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    summary_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="open")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    resolution_note_md: Mapped[str | None] = mapped_column(Text, nullable=True)
