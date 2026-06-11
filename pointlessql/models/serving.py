"""Model-serving endpoints — REST inference over registry models.

One table backing the serving surface: each row names a registry
model (+ version or alias) and tracks the lifecycle of the local
scoring worker that serves it.  The worker itself is an
``mlflow models serve`` subprocess managed by
:mod:`pointlessql.services.model_serving`; rows survive restarts
(state resets to ``stopped``), workers do not.
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

SERVING_ENDPOINT_STATES: tuple[str, ...] = ("stopped", "starting", "ready", "failed")
"""Worker lifecycle states the UI renders."""


class ServingEndpoint(Base):
    """One named inference endpoint over one registry model.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: FK to ``workspaces.id``; endpoints are
            workspace-scoped like the rest of the metadata DB.
        name: Endpoint identifier, unique per workspace; appears in
            the invocation URL.
        model_name: Registry model name (MLflow registry).
        model_version: Version number as string, or an alias when
            prefixed with ``@`` (``"3"`` / ``"@champion"``).
        state: One of :data:`SERVING_ENDPOINT_STATES`.  Reset to
            ``stopped`` on app start — workers never outlive the
            process.
        last_error: Most recent startup/runtime failure, for the
            detail page.
        created_by: E-mail of the creating principal.
        invocation_count: Lifetime number of served requests.
        last_invoked_at: Wall-clock of the most recent invocation.
        created_at: Timestamp when the endpoint was created.
        updated_at: Timestamp of the most recent mutation.
    """

    __tablename__ = "serving_endpoints"

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_serving_endpoints_ws_name"),
        Index("ix_serving_endpoints_workspace", "workspace_id"),
        CheckConstraint(
            "state IN ('stopped', 'starting', 'ready', 'failed')",
            name="ck_serving_endpoints_state",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_name: Mapped[str] = mapped_column(String(256), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="stopped", server_default="stopped"
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(254), nullable=True)
    invocation_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_invoked_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
