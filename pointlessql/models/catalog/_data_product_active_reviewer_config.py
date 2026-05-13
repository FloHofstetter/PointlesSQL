"""Per-DP active-reviewer configuration (Phase 74.0).

Tracks which DPs opt into the daily active-reviewer surface (Phase
74 promotes the Phase 19 passive ``AgentReview`` writer to an
active LLM-calling steward delegate).

Two runners are supported via the ``runner`` enum:

* ``'inproc'`` — PointlesSQL-side
  ``_active_reviewer_loop`` ticks at
  ``settings.data_products.active_reviewer_trigger_hour``, picks
  the DP, calls the configured LLM provider via
  ``services/lens/llm_provider.py``, and posts the response as a
  ``DataProductComment`` + a typed ``DataProductEndorsement``
  + a ``kind='audit_review'`` ``AgentReview`` row.
* ``'hermes_cron'`` — Hermes-cron job (out-of-tree) enumerates
  opted-in DPs via ``GET /api/data-products/active-reviewer/queue``
  and posts back via the existing tool surface.

The two runners are mutually exclusive per row; the steward picks
on the DP detail Settings tab.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

ACTIVE_REVIEWER_RUNNERS: tuple[str, ...] = ("inproc", "hermes_cron")
ACTIVE_REVIEWER_PROVIDERS: tuple[str, ...] = ("anthropic", "openai")


class DataProductActiveReviewerConfig(Base):
    """Per-DP active-reviewer toggle + runtime config.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Tenant scope.
        data_product_id: FK on ``data_products.id`` with
            ``ondelete='CASCADE'``.  UNIQUE per workspace+dp so
            steward edits are UPSERTs.
        enabled: Master switch.  When ``False`` the loop skips the
            DP even if a runner is configured.
        runner: One of :data:`ACTIVE_REVIEWER_RUNNERS`.  CHECK at
            DB.
        llm_provider: ``'anthropic'`` / ``'openai'`` / ``None``.
            Only meaningful when ``runner='inproc'`` — Hermes-cron
            jobs configure their LLM out of the plugin.
        llm_model: Per-DP override for the model id (when
            ``runner='inproc'``).  ``None`` falls back to
            ``settings.data_products.active_reviewer_model``.
        prompt_override_md: Optional markdown appended to the
            default prompt template (added at
            :func:`services.data_products.active_reviewer.build_prompt`
            time).  Empty string is treated as ``None``.
        last_run_at: Wall-clock of the most recent successful
            tick (loop OR manual run-now).
        last_run_comment_id: FK on
            ``data_product_comments.id`` nullable; points at the
            comment the last tick posted.  ``None`` until first
            successful run.
        acting_user_id: FK on ``users.id``; the steward / admin who
            enabled or last updated the reviewer.  The in-proc
            runner posts the comment + endorsement *as* this user
            so the audit row carries a real author and the existing
            comment / endorsement schemas stay non-nullable.
        agent_slug: Optional agent slug (Phase 76.5.1) — when set,
            the in-proc runner additionally stamps
            ``author_agent_id`` on the posted comment + endorsement
            so the row renders as authored *by the agent on behalf
            of* ``acting_user_id``.  ``None`` falls back to the
            steward-proxy posting path (existing Phase 74 behaviour).
        created_at: Wall-clock at insert.
        updated_at: Wall-clock of the most recent UPSERT.
    """

    __tablename__ = "data_product_active_reviewer_configs"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "data_product_id",
            name="uq_dp_active_reviewer_cfg",
        ),
        CheckConstraint(
            "runner IN ('inproc', 'hermes_cron')",
            name="ck_dp_active_reviewer_runner",
        ),
        CheckConstraint(
            "(llm_provider IS NULL) OR (llm_provider IN ('anthropic', 'openai'))",
            name="ck_dp_active_reviewer_provider",
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
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="0",
    )
    runner: Mapped[str] = mapped_column(String(20), nullable=False)
    llm_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_override_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_run_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_run_comment_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("data_product_comments.id", ondelete="SET NULL"),
        nullable=True,
    )
    acting_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )
    agent_slug: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
