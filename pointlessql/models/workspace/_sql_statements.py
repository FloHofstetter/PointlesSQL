"""External SQL Statement Execution API state.

Phase 117 introduces a public, token-authenticated REST surface for
external SQL clients (curl, dbt, BI tools) that mirrors the
Databricks SQL Statement Execution API.  Each submitted statement
gets one row in :class:`SqlStatement` whose lifecycle parallels the
DBX ``status.state`` enum:

* ``PENDING``   — row created, executor task not yet started.
* ``RUNNING``   — executor task entered ``run_sql_sync``.
* ``SUCCEEDED`` — DuckDB returned rows; serialised DBX envelope
                  cached in ``result_payload``.
* ``FAILED``    — parse / privilege / execution error captured in
                  ``error_code`` + ``error_message``.
* ``CANCELED``  — explicit cancel via
                  ``POST /api/2.0/sql/statements/{id}/cancel`` OR
                  ``on_wait_timeout=CANCEL`` exceeded.

Rows linger until the retention sweeper drops them (default 24h)
so the polling client has time to fetch the result after a
``CONTINUE``-on-timeout submit.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

# Lifecycle states — module-level frozen tuple kept in sync with the
# DBX ``status.state`` enum.  The route layer maps internal state ↔
# wire-form state directly; no translation needed because the storage
# vocabulary IS the wire vocabulary.
SQL_STATEMENT_STATES = (
    "PENDING",
    "RUNNING",
    "SUCCEEDED",
    "FAILED",
    "CANCELED",
)


class SqlStatement(Base):
    """One row per ``POST /api/2.0/sql/statements`` submission.

    The ``statement_id`` UUID is the public handle external clients
    poll with; it doubles as the audit-log ``target`` so a single
    grep links the API request, the audit row, and (when present)
    the cached result payload.

    Attributes:
        statement_id: Public UUIDv4 handle.  Primary key — chosen
            over an auto-increment integer because the value is
            user-visible and must survive backup-restore without
            collision risk.
        api_key_id: FK into ``api_keys.id``.  Anchors the row to
            the credential that authorised the submission so a
            revoked key's statements can still be audited.
        submitted_by_user_id: Resolved user-id for the API key's
            owner; ``0`` for env-var-bootstrapped keys that pre-date
            the FK column.
        workspace_id: Workspace the API key pins to at submit-time;
            snapshotted so a later key-rotation can't smear the
            statement across workspaces.
        statement_text: Verbatim SQL the client submitted (truncated
            to 64 KB to bound the column).
        catalog: Default catalog from the request body, or ``None``
            when client supplied fully-qualified refs.
        schema_name: Default schema from the request body.  Column
            name avoids the reserved-keyword conflict ``schema`` has
            with Pydantic's ``BaseModel.schema``.
        row_limit: Effective row cap after clamping to
            ``settings.sql_execution_api.max_row_limit``.
        status: One of :data:`SQL_STATEMENT_STATES`.  Indexed for
            the retention sweep that filters by terminal states.
        error_code: DBX-shape error code (``SQL_PARSE_ERROR``,
            ``PERMISSION_DENIED``, …) for ``FAILED`` rows.
        error_message: Human-readable failure detail.
        result_payload: ``gzip`` of the serialised DBX envelope
            (``{"manifest": {...}, "result": {...}}``) for
            ``SUCCEEDED`` rows.  Stored as bytes so polling /
            chunk-fetch routes can stream straight back without
            re-serialising.
        submitted_at: Wall-clock at row insert; primary index for
            retention.
        started_at: Wall-clock at ``RUNNING`` transition.  ``None``
            for rows that never entered the executor (e.g. cancel
            before start).
        completed_at: Wall-clock at terminal-state transition.
        cancel_requested: Flag the cancel route sets before invoking
            ``conn.interrupt()`` so the executor knows to mark
            ``CANCELED`` instead of ``FAILED`` when the DuckDB
            ``InterruptException`` propagates.
    """

    __tablename__ = "sql_statements"

    __table_args__ = (
        Index("ix_sql_statements_submitted_at", "submitted_at"),
        Index("ix_sql_statements_status", "status"),
        Index("ix_sql_statements_api_key_id", "api_key_id"),
    )

    statement_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    api_key_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("api_keys.id"), nullable=False
    )
    submitted_by_user_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, default=1
    )
    statement_text: Mapped[str] = mapped_column(Text, nullable=False)
    catalog: Mapped[str | None] = mapped_column(String(255), nullable=True)
    schema_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    row_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=10_000)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_payload: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    submitted_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
