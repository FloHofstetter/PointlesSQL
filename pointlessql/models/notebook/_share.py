"""Public share, widgets, and per-user permissions.

Three tables that govern how a notebook is exposed beyond its owning
workspace: public share links, parameter widgets, and the per-user
role lattice that layers on top of workspace membership.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class NotebookShare(Base):
    """Public-share grant for a notebook.

    One row mints an unguessable v4 UUID under
    ``/share/notebook/{share_uuid}`` so a notebook can be shared
    read-only without authentication.  Two modes:

    * ``snapshot`` *(default — safer)* — freezes the current state
      as a tagged :class:`NotebookRevision`; later in-place edits
      do not leak.  ``revision_uuid`` points at the frozen row.
      Re-publish updates the snapshot under the same share UUID
      (the link stays stable); Unpublish revokes entirely.
    * ``live`` — link always reflects the current ``.py`` +
      last-known outputs.  ``revision_uuid`` is null; the editor
      paints a persistent "LIVE share" badge while active so
      accidental secret-push is obvious.

    A second flag (``dashboard_mode``) toggles between
    "regular notebook" rendering and the dashboard rendering that
    strips code cells and shows only markdown + outputs.

    Attributes:
        id: Auto-incremented primary key.
        share_uuid: 36-char v4 UUID — the URL slug.  Stable across
          re-publish; rotated only on unpublish + republish.
        notebook_id: FK to :class:`Notebook` — cascade-delete with
          the notebook.
        share_mode: ``"snapshot"`` | ``"live"``.
        dashboard_mode: ``True`` when the share should render only
          markdown + outputs (no code).
        revision_uuid: For ``snapshot`` mode — FK-by-uuid to the
          :class:`NotebookRevision` row that is the frozen view.
          ``None`` for ``live``.
        created_by_user_id: Audit pointer.
        created_at: Wall-clock when the share row was minted.
        expires_at: Optional auto-expiry timestamp; ``None`` means
          no expiry.
        revoked_at: Soft-revoke tombstone.  Once set the share UUID
          returns 410 Gone.
    """

    __tablename__ = "notebook_shares"

    __table_args__ = (
        UniqueConstraint("share_uuid", name="uq_notebook_shares_uuid"),
        Index(
            "ix_notebook_shares_notebook_active",
            "notebook_id",
            "revoked_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    share_uuid: Mapped[str] = mapped_column(String(36), nullable=False)
    notebook_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notebooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    share_mode: Mapped[str] = mapped_column(String(10), nullable=False)
    dashboard_mode: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    revision_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class NotebookWidget(Base):
    """Parameter-widget definition attached to a notebook.

    Widgets are interactive controls rendered as a form above the
    notebook — dropdowns / sliders / text inputs.  Each row defines
    one widget; the kernel-side ``pql.widgets`` shim reads the current
    values via the env bridge so a parameterised notebook can drive
    its execution from a form rather than hard-coded constants.

    The widget vocabulary is intentionally small (dropdown / slider /
    text) so the UI stays narrow.  Default values + bounds are
    JSON-encoded so the same row can describe a dropdown's options
    AND a slider's min/max without column proliferation.

    Attributes:
        id: Auto-incremented primary key.
        notebook_id: FK to :class:`Notebook` — cascade-delete with
            the notebook.
        name: Identifier the kernel sees (e.g. ``"region"``).
            Unique per notebook.
        widget_kind: ``"dropdown"`` | ``"slider"`` | ``"text"``.
        label: Human-friendly label rendered above the input.
        config_json: JSON blob with the widget-kind-specific config
            (``options`` for dropdown, ``min`` / ``max`` / ``step``
            for slider, ``placeholder`` for text).
        default_value: Default value as a JSON-encoded scalar.
        position: Display order; smaller is earlier.
        created_at: When the widget was first defined.
        updated_at: Last edit timestamp.
    """

    __tablename__ = "notebook_widgets"

    __table_args__ = (
        UniqueConstraint("notebook_id", "name", name="uq_notebook_widgets_name_per_nb"),
        Index("ix_notebook_widgets_notebook", "notebook_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    notebook_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notebooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    widget_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    default_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class NotebookPermission(Base):
    """Per-notebook share permission.

    Layered on top of workspace membership: a workspace member who
    is not explicitly granted a notebook role still falls back to
    the workspace role (members can view; admins can edit).  This
    table lets a notebook be shared OUTSIDE its workspace's default
    permissioning — granting "view" to a stakeholder who otherwise
    has no edit rights, or upgrading "view" to "run" so a non-editor
    can re-execute cells.

    Roles form a lattice ``view < run < edit``; a higher role
    implicitly grants the lower ones.

    Attributes:
        id: Auto-incremented primary key.
        notebook_id: FK to :class:`Notebook` — cascade-delete with
            the notebook.
        user_id: FK to :class:`User` — the principal the role is
            granted to.
        role: ``"view"`` | ``"run"`` | ``"edit"``.
        granted_by_user_id: Audit pointer to the grantor — usually
            an admin or the notebook owner.
        granted_at: Wall-clock the grant landed.
    """

    __tablename__ = "notebook_permissions"

    __table_args__ = (
        UniqueConstraint("notebook_id", "user_id", name="uq_notebook_perms_per_user"),
        Index("ix_notebook_perms_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    notebook_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notebooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(8), nullable=False)
    granted_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    granted_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
