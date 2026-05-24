"""Promotion-candidate cache rows.

One row per ``(workspace, catalog, schema)`` triple that the
promotion scanner has spotted as a stable agent-driven write
pattern.  A periodic loop
(``_data_product_promotion_loop``) UPSERTs candidate rows; the
``/data-products/candidates`` page reads from this table.

A dismissed candidate stays as a row (``status='dismissed'``)
so the scanner doesn't re-suggest the same schema next tick.
A promoted candidate (yaml authored + reloaded) stays as a
row too — the link via ``promoted_to_data_product_id``
preserves the trail.
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
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

CANDIDATE_STATUSES: tuple[str, ...] = ("open", "dismissed", "promoted")


class DataProductPromotionCandidate(Base):
    """One promote-to-DP suggestion.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Tenant scope.
        catalog_name: UC catalog segment of the candidate.
        schema_name: UC schema segment.  ``(workspace_id,
            catalog_name, schema_name)`` is unique — at most one
            candidate row per schema lives in the table.
        table_signature_hash: SHA-256 of sorted ``(column_name,
            type)`` tuples across the tables observed in the
            schema.  Lets the scanner detect when the shape
            stabilised vs when agents are still iterating.
        first_seen_at: Wall-clock when the candidate first
            matched the threshold.
        last_seen_at: Wall-clock of the most recent matching
            agent_run_operation row.
        distinct_run_count: How many distinct ``agent_run_id``
            values touched any table in the schema within the
            scan window.
        write_op_count: Total ``agent_run_operations`` rows in
            the same window.
        distinct_table_count: How many distinct
            ``target_table`` values were observed in the
            schema during the window.
        sample_target_table: One representative
            ``"catalog.schema.table"`` for inspection; the
            "Generate draft" flow reads the schema of this
            table (and every other in the same schema) via
            ``DeltaTable``.
        status: One of :data:`CANDIDATE_STATUSES`.  CHECK
            constraint at the DB layer.
        dismissed_by_user_id: Who dismissed the candidate.
            Stays NULL while ``status='open'`` or
            ``'promoted'``.
        dismissed_at: Wall-clock at dismissal.
        promoted_to_data_product_id: FK on
            ``data_products.id`` once a yaml lands and a row
            is created by the loader.  Set by the promote
            path; stays NULL otherwise.
        refreshed_at: Wall-clock when the scanner last
            UPSERTed this row.
    """

    __tablename__ = "data_product_candidates"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "catalog_name",
            "schema_name",
            name="uq_dp_candidate_target",
        ),
        Index("ix_dp_candidate_ws_status", "workspace_id", "status"),
        CheckConstraint(
            "status IN ('open', 'dismissed', 'promoted')",
            name="ck_dp_candidate_status",
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
    table_signature_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    distinct_run_count: Mapped[int] = mapped_column(Integer, nullable=False)
    write_op_count: Mapped[int] = mapped_column(Integer, nullable=False)
    distinct_table_count: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_target_table: Mapped[str] = mapped_column(String(767), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="open")
    dismissed_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    dismissed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    promoted_to_data_product_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="SET NULL"),
        nullable=True,
    )
    refreshed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
