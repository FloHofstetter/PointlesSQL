"""Workspace secret scopes — named vaults for runtime credentials.

Three tables that give every workspace a Databricks-shaped secrets
surface (scopes → keyed secrets → per-principal ACLs):

* ``secret_scopes`` — one named vault per workspace.  Creating a
  scope grants the creator ``MANAGE`` on it; admins implicitly hold
  ``MANAGE`` everywhere.
* ``secret_scope_secrets`` — one encrypted value per ``(scope, key)``.
  The envelope is produced by
  :func:`pointlessql.services.secrets.encrypt_value` (Fernet, keyed
  off the install master key in ``system_keys``).  Plaintext never
  lives at rest, and the management API never returns values — only
  the audited runtime getter decrypts.
* ``secret_scope_acls`` — per-principal permission rows.  The
  ``principal`` is a user e-mail (or ``*`` for every authenticated
  user of the workspace); permissions form the strict ladder
  ``READ < WRITE < MANAGE``.

Storage decision: PointlesSQL metadata DB — secrets configure *our*
runtime (ingest sources, notebook kernels, sync targets) and must
never leave the install.  soyuz-catalog deliberately stores no
secrets (its connection options are proxy-owned plaintext).
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

SECRET_SCOPE_PERMISSIONS: tuple[str, ...] = ("READ", "WRITE", "MANAGE")
"""Permission ladder, weakest first; each level implies the ones before it."""


class SecretScope(Base):
    """One named secret vault inside a workspace.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Workspace this scope belongs to.  FK on
            ``workspaces.id``; ``server_default='1'`` so a fresh
            single-tenant install adopts the seeded default
            workspace without a data migration.
        name: Scope identifier, unique per workspace.  Restricted to
            ``[A-Za-z0-9_.-]`` so it can travel inside
            ``{{secrets/<scope>/<key>}}`` references unescaped.
        description: Free-form purpose note (nullable).
        created_by: E-mail of the creating principal (nullable for
            system-created scopes).
        created_at: Wall-clock the scope was created.
    """

    __tablename__ = "secret_scopes"

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_secret_scopes_ws_name"),
        Index("ix_secret_scopes_workspace", "workspace_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
        server_default="1",
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(254), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SecretScopeSecret(Base):
    """One encrypted value under one key of one scope.

    Attributes:
        id: Auto-incremented primary key.
        scope_id: FK to :class:`SecretScope` with ``ON DELETE
            CASCADE`` — secrets follow their scope.
        key: Secret name, unique within the scope.  Same character
            policy as scope names.
        encrypted_value: Fernet token.  Decrypt via
            :func:`pointlessql.services.secrets.decrypt_value`; the
            management API never ships this column, encrypted or not.
        created_by: E-mail of the principal that first wrote the key.
        updated_by: E-mail of the principal behind the latest write
            (equals ``created_by`` until the first overwrite).
        created_at: First-write timestamp.
        updated_at: Latest-write timestamp.
    """

    __tablename__ = "secret_scope_secrets"

    __table_args__ = (
        UniqueConstraint("scope_id", "key", name="uq_secret_scope_secrets_scope_key"),
        Index("ix_secret_scope_secrets_scope", "scope_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("secret_scopes.id", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(254), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(254), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SecretScopeAcl(Base):
    """One principal's permission on one scope.

    Attributes:
        id: Auto-incremented primary key.
        scope_id: FK to :class:`SecretScope` with ``ON DELETE
            CASCADE`` — grants follow their scope.
        principal: User e-mail, or ``*`` to cover every
            authenticated user of the scope's workspace.
        permission: One of :data:`SECRET_SCOPE_PERMISSIONS`; the
            ladder is strict, so ``MANAGE`` implies ``WRITE`` implies
            ``READ``.
        created_at: Grant timestamp.
    """

    __tablename__ = "secret_scope_acls"

    __table_args__ = (
        UniqueConstraint("scope_id", "principal", name="uq_secret_scope_acls_scope_principal"),
        Index("ix_secret_scope_acls_scope", "scope_id"),
        CheckConstraint(
            "permission IN ('READ', 'WRITE', 'MANAGE')",
            name="ck_secret_scope_acls_permission",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("secret_scopes.id", ondelete="CASCADE"),
        nullable=False,
    )
    principal: Mapped[str] = mapped_column(String(254), nullable=False)
    permission: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
