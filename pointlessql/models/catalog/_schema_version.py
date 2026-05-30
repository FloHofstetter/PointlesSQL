"""Output-port schema-contract version history.

One row per bump.  ``version_semver`` is the new semver after the bump
applies; ``schema_json`` snapshots the schema at that moment, so a
later reader can diff against the prior version without re-reading
the live Delta log.

Bumps are append-only: a bump never modifies an existing row.  The
authoritative current version lives on
:class:`DataProductOutputPort.version_semver`.
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

#: Schema-contract change kinds.  Drives the semver bump.
CHANGE_KINDS: tuple[str, ...] = ("major", "minor", "patch")

#: Policy modes for breaking-change enforcement on the write path.
BREAKING_CHANGE_POLICIES: tuple[str, ...] = ("block", "warn", "off")


class OutputPortSchemaVersion(Base):
    """One bump of an output port's schema contract.

    Attributes:
        id: Auto-incremented primary key.
        output_port_id: FK on ``data_product_output_ports.id`` with
            CASCADE; the version disappears with its port.
        version_semver: ``MAJOR.MINOR.PATCH`` after the bump.
        schema_json: JSON snapshot of the schema at this version.
        change_kind: One of :data:`CHANGE_KINDS`.  CHECK-bounded.
        change_summary: Free-form human note (the PR title, the
            reason for the bump).
        bumped_at: Wall-clock the bump landed.
        bumped_by_user_id: Nullable FK on ``users.id``.
    """

    __tablename__ = "output_port_schema_versions"

    __table_args__ = (
        CheckConstraint(
            "change_kind IN ('major','minor','patch')",
            name="ck_output_port_schema_versions_kind",
        ),
        UniqueConstraint(
            "output_port_id",
            "version_semver",
            name="uq_output_port_schema_versions_port_version",
        ),
        Index(
            "ix_output_port_schema_versions_port",
            "output_port_id",
            "bumped_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    output_port_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_product_output_ports.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_semver: Mapped[str] = mapped_column(String(16), nullable=False)
    schema_json: Mapped[str] = mapped_column(Text(), nullable=False)
    change_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    bumped_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    bumped_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
