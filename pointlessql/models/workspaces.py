"""Workspace primitives — soft tenant boundary over a shared catalog.

PointlesSQL's Phase-28 isolation model treats a *workspace* as a
governance / audit container that floats *above* the Unity Catalog
namespace.  Catalogs themselves stay global so cross-workspace data
sharing (dev workspace reading ``prod.silver.orders`` to bootstrap a
sandbox merge) keeps working without any new code — UC privileges
already gate it.  Every PointlesSQL-owned table that today represents
per-user / per-run / global-audit state grows a ``workspace_id`` FK
in subsequent sub-sprints; **this module only ships the three
foundation tables** the rest of Phase 28 hangs off:

* :class:`Workspace` — the container itself.  Has a stable ``slug``
  for URL / header use plus a human ``name``.  Soft-archived via
  ``archived_at`` rather than hard-deleted so historical audit rows
  always resolve back to a real workspace.
* :class:`WorkspaceMember` — M:M junction between users and
  workspaces.  Carries a per-membership ``role`` (member or admin)
  so workspace-local admin rights can be granted without elevating
  the user to a tenant-wide :attr:`User.is_admin`.
* :class:`WorkspaceCatalogPin` — *cosmetic* default-catalog hint
  for the sidebar tree.  No enforcement — every workspace can still
  query every catalog subject to UC privileges.  Pins exist so the
  UI knows which catalog to expand on first load and which catalogs
  to surface in compact "primary catalogs" listings.
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

#: Allowed values for :attr:`WorkspaceMember.role`.  Stored as a plain
#: ``String`` (matching the rest of the schema's enum-via-tuple
#: convention) so future role additions don't require an enum
#: migration.
WORKSPACE_ROLES: tuple[str, ...] = ("member", "admin")

#: Allowed values for :attr:`WorkspaceCatalogPin.mode`.  ``primary``
#: is the single default-expansion catalog; ``pinned`` are siblings
#: that should appear in the workspace's compact listing without
#: dominating the tree's initial view.
WORKSPACE_PIN_MODES: tuple[str, ...] = ("primary", "pinned")


class Workspace(Base):
    """One tenant-style governance container.

    A fresh install always carries one workspace (``id=1, slug='default'``)
    seeded by the Sprint-28.0 migration so single-tenant deployments stay
    behaviour-identical: every existing audit / job / saved-query row
    backfills to the default workspace and the UI hides the switcher
    until a second workspace is created.

    Attributes:
        id: Auto-incremented primary key.  ``id=1`` is reserved for the
            seeded ``default`` workspace.
        slug: URL- and header-safe identifier (max 64 chars, unique).
            Used by the ``X-Workspace`` request header and the
            ``current_workspace_slug`` session-cookie field.
        name: Human-readable label shown in the switcher dropdown
            (max 200 chars).
        description: Free-form note for admins (Text, nullable).
        created_at: Wall-clock when the workspace was created.
        archived_at: Wall-clock when the admin archived the workspace.
            ``None`` for active workspaces.  Archived workspaces hide
            from the switcher and from default listings but keep their
            data so historical audit rows still resolve.
    """

    __tablename__ = "workspaces"

    __table_args__ = (Index("ix_workspaces_slug", "slug", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    archived_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WorkspaceMember(Base):
    """One user's membership in one workspace.

    The M:M shape (rather than a single ``users.workspace_id`` column)
    is deliberate even though the UI initially only exposes a single
    active workspace at a time — moving to multi-workspace membership
    later requires zero migrations, and the ``users.default_workspace_id``
    pointer alone gives every existing single-membership user the same
    UX as before.

    The per-membership ``role`` lets an admin grant workspace-local
    admin rights (manage members, edit pins) without elevating the
    user to a tenant-wide :attr:`User.is_admin`, which retains the
    god-eye cross-workspace lens.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: FK to :class:`Workspace`.
        user_id: FK to :class:`~pointlessql.models.User`.
        role: One of :data:`WORKSPACE_ROLES`.  Stored as a plain
            string so future role additions don't need an enum
            migration.
        created_at: Wall-clock the membership was granted.
    """

    __tablename__ = "workspace_members"

    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_identity"),
        Index("ix_workspace_members_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey("workspaces.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="member")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorkspaceCatalogPin(Base):
    """A cosmetic catalog default for one workspace's sidebar.

    Pins are a UX hint, never an enforcement boundary — the global-
    catalog decision (Phase-28 ADR-0008) means every workspace can
    query every catalog subject to UC privileges.  A workspace with
    no pins shows the full catalog tree exactly like the pre-Phase-28
    UI; a workspace with pins simply pre-expands its ``primary`` and
    surfaces ``pinned`` siblings in a compact listing.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: FK to :class:`Workspace`.
        catalog_name: UC catalog name (max 255 chars).  Not validated
            against soyuz at write time — admins can pin a catalog
            before it exists in UC, and stale pins for deleted
            catalogs are silently skipped at render time.
        mode: One of :data:`WORKSPACE_PIN_MODES`.  At most one pin
            per workspace should carry ``primary``; the application
            layer enforces this on write rather than via a partial
            unique index (kept dialect-portable).
        created_at: Wall-clock the pin was created.
    """

    __tablename__ = "workspace_catalog_pins"

    __table_args__ = (
        UniqueConstraint("workspace_id", "catalog_name", name="uq_workspace_catalog_pins_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey("workspaces.id"), nullable=False)
    catalog_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="pinned")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
