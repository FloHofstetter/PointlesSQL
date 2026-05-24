"""Workspace-repo cache rows + per-repo encrypted secrets.

each workspace can pin
1..n git repositories whose contents (yaml bundles, notebooks,
dashboards, saved queries) feed PointlesSQL's loaders.  The git
clone lives on disk under
``<repos_base_dir>/<workspace_id>/<slug>/``.  The two tables in
this module give the application:

* :class:`WorkspaceRepo` — one row per (workspace, slug) pinning a
  remote URL + tracked branch + provider kind + sync state.
* :class:`WorkspaceRepoSecret` — encrypted auth credentials
  (deploy key, PAT, OAuth token).  At most one row per
  ``(workspace_repo_id, kind)``.

Yaml is canonical; the on-disk clone + DB row are both caches.
The convention "git is truth, DB is cache" is shared with data
products and other repo-backed conventions.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
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

#: Allowed values for :attr:`WorkspaceRepo.provider_kind`.  Stays
#: string-typed (rather than enum) so adding a new provider only
#: needs a code change, not a migration.
WORKSPACE_REPO_PROVIDER_KINDS: tuple[str, ...] = ("generic", "github")

#: Allowed values for :attr:`WorkspaceRepo.sync_state`.
WORKSPACE_REPO_SYNC_STATES: tuple[str, ...] = ("idle", "syncing", "ok", "error")

#: Allowed values for :attr:`WorkspaceRepoSecret.kind`.
WORKSPACE_REPO_SECRET_KINDS: tuple[str, ...] = ("deploy_key", "https_token", "oauth_token")


class WorkspaceRepo(Base):
    """One git-canonical configuration source pinned to a workspace.

    The clone lives at
    ``<settings.workspace_repos.base_dir>/<workspace_id>/<slug>/``.
    Every successful sync upserts ``last_synced_sha`` /
    ``last_synced_at`` and re-runs the workspace-scoped loaders.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: FK to :class:`Workspace`.
        slug: Short identifier unique within the workspace
            (``platform-yaml``, ``data-team-prod``, ...).
        url: Full clone URL.  https or ssh.  Stored verbatim;
            credentials live in :class:`WorkspaceRepoSecret` and
            are injected at clone time.
        default_branch: Branch tracked on every sync (typically
            ``main``).
        provider_kind: Discriminator picking the
            :class:`pointlessql.git.GitProvider` impl that drives
            clone / pull / webhook verification.
        sync_state: ``idle`` (never synced), ``syncing`` (in
            progress), ``ok`` (last sync succeeded), ``error``
            (last sync failed; ``last_sync_error`` carries the
            diagnostic).
        last_synced_sha: 40-char hex of ``HEAD`` after the last
            successful pull.  ``None`` until the first sync lands.
        last_synced_at: Timestamp of the last successful pull.
        last_sync_error: Captured stderr / diagnostic from the
            last failed sync.  Cleared on the next success.
        webhook_secret: Random shared-secret used by the inbound
            webhook endpoint to verify signatures.  Reveal-once at
            create time; rotation generates a fresh value.
        created_by_user_id: User who registered the repo.  Loose
            FK (no DB-level enforcement) so the audit trail
            survives user deletion.
        created_at: Wall-clock at registration.
    """

    __tablename__ = "workspace_repos"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "slug",
            name="uq_workspace_repos_workspace_slug",
        ),
        Index("ix_workspace_repos_workspace_synced", "workspace_id", "last_synced_at"),
        Index("ix_workspace_repos_state", "sync_state"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    default_branch: Mapped[str] = mapped_column(
        String(120), nullable=False, default="main", server_default="main"
    )
    provider_kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default="generic", server_default="generic"
    )
    sync_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="idle", server_default="idle"
    )
    last_synced_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_synced_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_secret: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorkspaceRepoSecret(Base):
    """One encrypted auth credential for one repo.

    The encrypted envelope is produced by
    :func:`pointlessql.services.secrets.encrypt_value` (Fernet,
    keyed off an install master key in :class:`SystemKey`).
    Plaintext never lives at rest.

    Attributes:
        id: Auto-incremented primary key.
        workspace_repo_id: FK to :class:`WorkspaceRepo` with
            ``ON DELETE CASCADE`` — secrets follow their repo.
        kind: One of :data:`WORKSPACE_REPO_SECRET_KINDS`.  The
            ``(workspace_repo_id, kind)`` pair is unique so a
            repo cannot carry two deploy keys at once.
        encrypted_value: Fernet token.  Decrypt via
            :func:`pointlessql.services.secrets.decrypt_value`.
        created_at: First-write timestamp.
        rotated_at: Set when the value is overwritten in place;
            ``None`` for never-rotated rows.
    """

    __tablename__ = "workspace_repo_secrets"

    __table_args__ = (
        UniqueConstraint(
            "workspace_repo_id",
            "kind",
            name="uq_workspace_repo_secrets_repo_kind",
        ),
        Index(
            "ix_workspace_repo_secrets_repo",
            "workspace_repo_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_repo_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspace_repos.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rotated_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
