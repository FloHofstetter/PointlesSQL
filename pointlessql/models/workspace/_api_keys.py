"""API-key store — DB-backed Bearer-token gate.

Replaces the earlier env-var ``POINTLESSQL_API_KEYS`` parser with
a real table so admins can rotate keys without a process restart,
and so the ``supervisor`` scope (gating the supervisor routes)
lives next to the secret it authorises.
"""

from __future__ import annotations

import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class ApiKey(Base):
    """One Bearer-token credential addressable by ``Authorization: Bearer``.

    Secrets are stored hashed; the plaintext is shown to the admin
    once at creation time and never persisted.  ``secret_prefix`` is
    the first 8 characters of the plaintext so the admin UI can
    label the key without revealing the secret.

    Attributes:
        id: Auto-incremented primary key.
        name: Unique human-readable label (used as audit attribution
            via ``api_key:<name>``).
        secret_hash: SHA-256-hex of the plaintext secret.  API keys
            are high-entropy random, so a fast hash is enough — bcrypt
            would only buy resistance against brute-force on weak
            secrets, and we control the secrets here.
        secret_prefix: First 8 plaintext characters for UI display.
        supervisor: When ``True``, the key may invoke the supervisor
            routes (per-run summary / diff).
        auditor: When ``True``, the key may invoke the audit-read
            surface (tenant-wide ``/api/audit/*`` aggregates and the
            per-run audit-axis routes).  Independent of
            ``supervisor``.1 separates read-audit from
            run-supervision so the daily Audit-Reviewer-Agent can be
            issued an auditor key without inheriting supervisor
            privileges (or admin's PII-reveal).
        lineage_inbound: When ``True``, the key may invoke
            ``POST /api/lineage/openlineage``.  Independent of
            ``supervisor`` / ``auditor`` so a federation-only key
            can land lineage events without seeing run audit
            telemetry.
        analyst: When ``True``, the key may invoke the Lens read-only
            Q&A surface (``/api/lens/*`` and the MCP server).  The
            scope is narrower than ``auditor`` (no audit-internals)
            but wider than anonymous (catalog browsing, query
            execution gated by EXPLAIN cost).  Lens promotes analyst
            up the ladder so analyst-keys also pass auditor gates,
            because "when did this table last change" is an
            analyst-shaped question.
        sql_execute: When ``True``, the key may invoke the public
            DBX-compatible SQL Statement Execution API
            (``/api/2.0/sql/statements``).  Independent of every
            other scope: this surface is read-only (SELECT only) but
            executes arbitrary user-supplied SQL against soyuz-enforced
            UC SELECT grants — narrow enough to issue to a dbt /
            BI-tool integration without granting Lens or audit reads.
        created_at: Timestamp the key was created.
        created_by_user_id: Admin who created the key, or ``None``
            for env-var-bootstrapped keys + CLI-provisioned keys.
        revoked_at: Timestamp the key was revoked, or ``None`` when
            still active.  Revoked keys stay in the table so the
            audit trail keeps resolving ``api_key:<name>`` after a
            rotation.
        last_used_at: Best-effort wall-clock of the most recent
            successful auth.  Updated by the middleware on each
            cache-miss verification — not transactionally critical
            (a swallowed UPDATE is fine).
        workspace_id: Workspace this key pins to.  The bootstrap
            migration backfills every existing key to the seeded
            ``default`` workspace (id=1); admin-issued keys land on
            the workspace selected at creation time.  The middleware
            uses this as the resolved workspace for Bearer-authed
            requests when no ``X-Workspace`` header is supplied.
    """

    __tablename__ = "api_keys"

    __table_args__ = (Index("ix_api_keys_secret_hash", "secret_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    secret_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    # Phase 118 widened from VARCHAR(8) to VARCHAR(32) so the new
    # ``pql_{env}_v1_xxxxxxxxxx`` prefix (~24 chars) fits.  Legacy
    # keys keep their original 8-char prefix unchanged.
    secret_prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    # token format discriminator.  ``'legacy'`` for pre-118
    # ``secrets.token_urlsafe(32)`` tokens; ``'v1'`` for the
    # ``pql_{env}_v1_{body40}_{crc8}`` format.  Drives badge rendering
    # and lets future code drop legacy support cleanly.
    token_format: Mapped[str] = mapped_column(
        String(8), nullable=False, default="legacy", server_default=text("'legacy'")
    )
    # env discriminator.  ``'live'`` / ``'test'`` for v1
    # tokens, ``'legacy'`` for pre-118 keys.  Test keys are visually
    # distinct in audit logs; refusal in production is wired by config.
    token_env: Mapped[str] = mapped_column(
        String(8), nullable=False, default="legacy", server_default=text("'legacy'")
    )
    supervisor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auditor: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Phase-40: ``lineage_inbound`` gates ``POST /api/lineage/openlineage``.
    # Independent of ``supervisor`` / ``auditor`` so a federation-only key
    # can land lineage events without seeing run audit telemetry.
    lineage_inbound: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    analyst: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # gates the public DBX-compatible SQL Statement
    # Execution API.  Independent of every other scope.
    sql_execute: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Every key pins to exactly one workspace.  The bootstrap
    # migration backfills existing rows to the default workspace
    # (id=1) and the column is NOT NULL after backfill so the catalog
    # enforcement and plugin paths never have to defend against an
    # unscoped key.
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    # lifecycle columns.  All NULL-able with NULL = no
    # constraint, so every pre-119 key keeps unchanged behaviour
    # until an admin opts in by setting a TTL or rotating.
    expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rotated_from_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True
    )
    rotated_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    grace_until: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    quarantined_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    quarantine_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    expiry_warned_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
