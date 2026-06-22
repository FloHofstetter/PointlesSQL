"""Governed MCP service registry — the workspace tool inventory.

Two tables that give every workspace a Unity-Catalog-shaped inventory
of approved external Model Context Protocol services (Slack, Jira,
GitHub, a partner's own MCP endpoint, …) and the individual tools each
exposes:

* ``mcp_services`` — one registered MCP service per ``(workspace,
  name)``.  Admins register a service (its endpoint URL + transport)
  and flip ``enabled`` to publish it to developers or pull it from the
  catalog without deleting the registration.
* ``mcp_service_tools`` — one row per tool a service advertises, each
  with its own ``enabled`` toggle so an admin can allow a service while
  disabling individual high-risk tools.

Storage decision: PointlesSQL metadata DB.  This is *our* governance
inventory of which external tool surfaces a workspace has vetted — it
configures our admin/discovery UI and audit trail, not lakehouse
metadata, so soyuz-catalog never owns it.  External credentials for a
service live in a ``secret_scopes`` vault referenced by name; the
registry stores only the scope pointer, never a secret value.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

MCP_SERVICE_TRANSPORTS: tuple[str, ...] = ("sse", "http", "stdio")
"""Wire transports a registered MCP service can speak.

``sse`` and ``http`` are network endpoints (a URL is required);
``stdio`` is a locally-launched process block and carries a command
string in ``url`` instead of an HTTP address.
"""


class McpService(Base):
    """One registered external MCP service in a workspace's inventory.

    A vetted Model Context Protocol endpoint an admin has added to the
    workspace tool inventory.  Registration is governance metadata, not
    a live connection: PointlesSQL records *that* a service is approved
    and *which* tools it offers, so the eventual enforcement path (route
    an agent's MCP call only at approved + enabled services) and the
    discovery UI both read one source of truth.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Workspace this service belongs to.  FK on
            ``workspaces.id``; ``server_default='1'`` so a fresh
            single-tenant install adopts the seeded default workspace
            without a data migration.
        name: Service identifier, unique per workspace.
        url: Endpoint address — an HTTP/SSE URL for the network
            transports, or a launch command for ``stdio``.
        transport: One of :data:`MCP_SERVICE_TRANSPORTS`.
        description: Free-form purpose note (nullable).
        secret_scope: Name of a ``secret_scopes`` vault holding this
            service's external credentials (nullable — public services
            need none).  Only the pointer is stored here.
        enabled: When ``False`` the service is hidden from the
            developer discovery view and treated as un-published; the
            registration row is kept so re-enabling is one toggle.
        created_by: E-mail of the registering admin (nullable for
            system-seeded rows).
        created_at: Registration timestamp.
        updated_at: Timestamp of the most recent mutation.
    """

    __tablename__ = "mcp_services"

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_mcp_services_ws_name"),
        Index("ix_mcp_services_workspace", "workspace_id"),
        CheckConstraint(
            "transport IN ('sse', 'http', 'stdio')",
            name="ck_mcp_services_transport",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
        server_default="1",
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    transport: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    secret_scope: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    created_by: Mapped[str | None] = mapped_column(String(254), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class McpServiceTool(Base):
    """One advertised tool under one registered MCP service.

    The per-tool grain is what makes the inventory *governed* rather
    than all-or-nothing: an admin can keep a service approved while
    disabling an individual tool that is too broad for the workspace.

    Attributes:
        id: Auto-incremented primary key.
        service_id: FK to :class:`McpService` with ``ON DELETE
            CASCADE`` — tools follow their service.
        name: Tool name, unique within the service.
        description: Free-form note describing what the tool does
            (nullable).
        enabled: Per-tool allow toggle.  When ``False`` the tool is
            withheld from discovery even though its service is enabled.
        created_at: Timestamp the tool was added to the inventory.
    """

    __tablename__ = "mcp_service_tools"

    __table_args__ = (
        UniqueConstraint("service_id", "name", name="uq_mcp_service_tools_service_name"),
        Index("ix_mcp_service_tools_service", "service_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("mcp_services.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
