"""Hosted data apps — user-authored web apps behind the reverse-proxy.

One table backing the hosted-apps surface: each row carries the
source code of a small data app (a FastAPI module, a Streamlit
script, or an arbitrary command line) and tracks the lifecycle of
the local worker subprocess that serves it.  The worker itself is
managed by :mod:`pointlessql.services.app_hosting`; rows survive
restarts (state resets to ``stopped``), workers do not.
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

HOSTED_APP_STATES: tuple[str, ...] = ("stopped", "starting", "ready", "failed")
"""Worker lifecycle states the UI renders."""

HOSTED_APP_KINDS: tuple[str, ...] = ("fastapi", "streamlit", "command")
"""Supported app runtimes — each maps to one spawn recipe."""


class AppSpace(Base):
    """A governance boundary grouping several hosted apps.

    An App Space lets an admin define the API scopes (for on-behalf-of-
    user access) and a shared rationale once for a group of apps, rather
    than per app.  Apps point at a space via ``HostedApp.app_space_id``;
    the space's scopes are the apps' effective grant set.  The actual
    enforcement is layered by the grant / policy stack on top.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: FK to ``workspaces.id``; spaces are
            workspace-scoped.
        name: Space identifier, unique per workspace.
        description: Free-text rationale shown in the UI.
        api_scopes: JSON-encoded list of API scope strings the space's
            apps may use on behalf of a user.
        created_by: E-mail of the creating principal.
        created_at: Creation timestamp.
        updated_at: Timestamp of the most recent mutation.
    """

    __tablename__ = "app_spaces"

    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_app_spaces_ws_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_scopes: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    created_by: Mapped[str | None] = mapped_column(String(254), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class HostedApp(Base):
    """One hosted data app and its worker lifecycle.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: FK to ``workspaces.id``; apps are
            workspace-scoped like the rest of the metadata DB.
        slug: URL identifier derived from the title, unique per
            workspace; appears in the proxy path ``/apps/<slug>/``.
        title: Human-readable name the list page shows.
        description: Optional free-form description.
        kind: One of :data:`HOSTED_APP_KINDS` — selects the spawn
            recipe (uvicorn module, streamlit script, or an
            operator-supplied command line).
        source_code: Contents of the app's ``app.py``, materialised
            to disk on every start so edits take effect on restart.
        command_override: Custom argv template for ``kind="command"``
            apps (supports a ``{port}`` placeholder); unused for the
            other kinds.
        env_json: JSON object of extra environment variables passed
            to the worker.  Values may carry
            ``{{secrets/<scope>/<key>}}`` references which the start
            route resolves just-in-time — the stored text keeps the
            placeholder, never the secret.
        state: One of :data:`HOSTED_APP_STATES`.  Reset to
            ``stopped`` on app start — workers never outlive the
            process.
        last_error: Most recent startup/runtime failure, for the
            detail page.
        app_space_id: Optional FK to :class:`AppSpace` — the governance
            boundary the app belongs to; ``None`` when ungrouped.  SET
            NULL on space delete so the app survives losing its space.
        created_by_user_id: FK to ``users.id`` — the creating admin.
        created_at: Timestamp when the app was created.
        updated_at: Timestamp of the most recent mutation.
    """

    __tablename__ = "hosted_apps"

    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="uq_hosted_apps_ws_slug"),
        Index("ix_hosted_apps_workspace", "workspace_id"),
        CheckConstraint(
            "state IN ('stopped', 'starting', 'ready', 'failed')",
            name="ck_hosted_apps_state",
        ),
        CheckConstraint(
            "kind IN ('fastapi', 'streamlit', 'command')",
            name="ck_hosted_apps_kind",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    command_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    env_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="stopped", server_default="stopped"
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    #  Optional App Space grouping — the space's API scopes apply to
    # every member app.  SET NULL on space delete so the app survives.
    app_space_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("app_spaces.id", ondelete="SET NULL", name="fk_hosted_apps_app_space"),
        nullable=True,
    )
    created_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
