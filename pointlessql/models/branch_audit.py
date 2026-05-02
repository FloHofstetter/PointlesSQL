"""Branch-operation audit trail.

UC tags carry per-branch metadata while the schema exists, but they
disappear with the schema once a branch is discarded.  ``branch_audit_log``
is PointlesSQL's own append-only record of every branch life-cycle
event so an auditor can answer questions like "which branches were
discarded last week and which run created them?" weeks after the
schemas themselves are gone.

A row is written:

* On branch creation — by ``pql.branch`` ( emits the row
  too if the table is available; older creations only show in the
  log from this sprint forward).
* On branch promotion — by ``pql.branch_promote``.
* On branch discard — by ``pql.branch_discard`` (this sprint).
* On auto-cleanup discard — by ``services/branch_cleanup.py``
  with ``run_id=None``.

The table is intentionally *not* coupled to ``agent_run_operations``
(which only records ops that ran inside a run scope).  Some branch
ops happen outside any run — auto-cleanup, admin-driven promote /
discard from the Control-Room UI — and we want the audit row regardless.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    DateTime,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

BRANCH_ACTIONS: tuple[str, ...] = (
    "create",
    "promote",
    "discard",
    "auto_cleanup",
)


class BranchAuditLog(Base):
    """One row per branch life-cycle event.

    Attributes:
        id: Auto-incremented primary key.
        branch_schema_fqn: ``catalog.schema`` of the branch.
        parent_schema_fqn: ``catalog.schema`` of the source the
            branch was made from.  May be ``None`` on legacy
            ``auto_cleanup`` rows where the parent is unrecoverable.
        action: One of :data:`BRANCH_ACTIONS`.
        run_id: Active ``agent_runs.id`` when the op fired inside a
            run, ``None`` for admin- or scheduler-driven ops.  Stored
            as a logical link (no FK) so deleting the originating run
            doesn't cascade-orphan audit rows.
        payload_json: Free-form JSON blob with op-specific details
            (strategy chosen, parent_versions snapshot, conflict
            details, etc.).  Capped at ~1 MiB by convention.
        created_at: UTC timestamp of the operation.
    """

    __tablename__ = "branch_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    branch_schema_fqn: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    parent_schema_fqn: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
