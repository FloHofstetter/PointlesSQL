"""Governed MCP service registry — workspace tool-inventory CRUD.

The service layer behind the admin "MCP services" surface and the
developer discovery view.  It manages the workspace's vetted inventory
of external Model Context Protocol services and the individual tools
each exposes, all in PointlesSQL's own metadata DB:

* admins register / update / enable / disable services
  (:func:`register_service`, :func:`update_service`,
  :func:`set_service_enabled`, :func:`delete_service`);
* admins curate each service's tool list with a per-tool allow toggle
  (:func:`add_tool`, :func:`set_tool_enabled`, :func:`delete_tool`);
* developers read the published surface — only enabled services and
  their enabled tools — through :func:`discover_services`.

Every mutation validates its inputs and raises :class:`ValueError` on
bad shape or a duplicate name; the route layer maps that to HTTP 400.
This module never opens an MCP connection — it governs *which*
services + tools a workspace has approved, leaving live invocation to
the eventual enforcement path.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from pointlessql.models import McpService, McpServiceTool
from pointlessql.models.mcp_registry import MCP_SERVICE_TRANSPORTS

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


def _utcnow() -> datetime.datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.datetime.now(datetime.UTC)


def _clean_name(value: Any, *, what: str) -> str:
    """Return a trimmed non-empty name or raise :class:`ValueError`.

    Args:
        value: Raw candidate value.
        what: Field label woven into the error message.

    Returns:
        The stripped name.

    Raises:
        ValueError: When *value* is not a non-empty string.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{what} must be a non-empty string")
    return value.strip()


def _clean_optional(value: Any) -> str | None:
    """Return a trimmed non-empty string, or ``None``.

    Args:
        value: Raw request value.

    Returns:
        The stripped string when it is a non-empty ``str``, else ``None``.
    """
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _validate_transport(value: Any) -> str:
    """Return a valid transport string or raise :class:`ValueError`.

    Args:
        value: Raw transport value.

    Returns:
        One of :data:`MCP_SERVICE_TRANSPORTS`.

    Raises:
        ValueError: When *value* is not a recognised transport.
    """
    transport = value.strip() if isinstance(value, str) else value
    if transport not in MCP_SERVICE_TRANSPORTS:
        allowed = ", ".join(MCP_SERVICE_TRANSPORTS)
        raise ValueError(f"transport must be one of {allowed}")
    return transport


def _service_dict(service: McpService, tools: list[McpServiceTool]) -> dict[str, Any]:
    """Serialise a service plus its tools into a JSON-ready dict.

    Args:
        service: The :class:`McpService` row.
        tools: The service's :class:`McpServiceTool` rows, in name order.

    Returns:
        A dict with the service fields, an ordered ``tools`` list, and
        the ``tool_count`` / ``enabled_tool_count`` rollups the admin
        list view renders without a second query.
    """
    tool_dicts = [_tool_dict(tool) for tool in tools]
    return {
        "id": service.id,
        "workspace_id": service.workspace_id,
        "name": service.name,
        "url": service.url,
        "transport": service.transport,
        "description": service.description,
        "secret_scope": service.secret_scope,
        "enabled": service.enabled,
        "created_by": service.created_by,
        "created_at": service.created_at.isoformat() if service.created_at else None,
        "updated_at": service.updated_at.isoformat() if service.updated_at else None,
        "tools": tool_dicts,
        "tool_count": len(tool_dicts),
        "enabled_tool_count": sum(1 for tool in tool_dicts if tool["enabled"]),
    }


def _tool_dict(tool: McpServiceTool) -> dict[str, Any]:
    """Serialise one :class:`McpServiceTool` row into a JSON-ready dict."""
    return {
        "id": tool.id,
        "service_id": tool.service_id,
        "name": tool.name,
        "description": tool.description,
        "enabled": tool.enabled,
        "created_at": tool.created_at.isoformat() if tool.created_at else None,
    }


def _load_tools(session: Session, service_id: int) -> list[McpServiceTool]:
    """Return a service's tools ordered by name."""
    return list(
        session.scalars(
            select(McpServiceTool)
            .where(McpServiceTool.service_id == service_id)
            .order_by(McpServiceTool.name)
        )
    )


def _load_tools_bulk(session: Session, service_ids: list[int]) -> dict[int, list[McpServiceTool]]:
    """Return tools for many services in one query, grouped by service id.

    Loads every service's tools in a single round-trip rather than the
    per-service query a list/discover view would otherwise fan out, so
    rendering N services costs two queries instead of N + 1.  Each
    group is ordered by tool name, matching :func:`_load_tools`.

    Args:
        session: Active SQLAlchemy session.
        service_ids: Service primary keys to load tools for.

    Returns:
        A mapping of every requested service id to its (possibly empty)
        name-ordered tool list.
    """
    grouped: dict[int, list[McpServiceTool]] = {sid: [] for sid in service_ids}
    if not service_ids:
        return grouped
    rows = session.scalars(
        select(McpServiceTool)
        .where(McpServiceTool.service_id.in_(service_ids))
        .order_by(McpServiceTool.service_id, McpServiceTool.name)
    )
    for tool in rows:
        grouped[tool.service_id].append(tool)
    return grouped


def list_services(factory: sessionmaker[Session], *, workspace_id: int) -> list[dict[str, Any]]:
    """Return every registered service in *workspace_id*, tools included.

    This is the admin view: enabled and disabled services alike, each
    with its full tool list and the enabled/total tool rollups.

    Args:
        factory: SQLAlchemy session factory bound to the metadata DB.
        workspace_id: Workspace whose inventory to list.

    Returns:
        Services ordered by name, each serialised via
        :func:`_service_dict`.
    """
    with factory() as session:
        services = list(
            session.scalars(
                select(McpService)
                .where(McpService.workspace_id == workspace_id)
                .order_by(McpService.name)
            )
        )
        tools_by_service = _load_tools_bulk(session, [svc.id for svc in services])
        return [_service_dict(svc, tools_by_service[svc.id]) for svc in services]


def get_service(
    factory: sessionmaker[Session], *, service_id: int, workspace_id: int
) -> dict[str, Any] | None:
    """Return one service with its tools, or ``None`` when absent.

    Args:
        factory: SQLAlchemy session factory.
        service_id: Primary key of the service.
        workspace_id: Owning workspace; a service in any other workspace
            is treated as absent so the registry stays tenant-bounded.

    Returns:
        The serialised service dict, or ``None`` if no such row.
    """
    with factory() as session:
        service = session.get(McpService, service_id)
        if service is None or int(service.workspace_id) != workspace_id:
            return None
        return _service_dict(service, _load_tools(session, service.id))


def discover_services(factory: sessionmaker[Session], *, workspace_id: int) -> list[dict[str, Any]]:
    """Return the published surface developers may use.

    Only enabled services appear, and each carries only its enabled
    tools — the disabled-tool rows are filtered out entirely so a
    consumer never discovers a withheld tool.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Workspace whose published surface to read.

    Returns:
        Enabled services ordered by name, each with only its enabled
        tools and recomputed rollups.
    """
    published: list[dict[str, Any]] = []
    for service in list_services(factory, workspace_id=workspace_id):
        if not service["enabled"]:
            continue
        enabled_tools = [tool for tool in service["tools"] if tool["enabled"]]
        service["tools"] = enabled_tools
        # Discovery publishes only enabled tools, so on this surface the
        # total and enabled counts are the same figure by construction —
        # derive one from the other rather than recomputing it twice.
        service["enabled_tool_count"] = len(enabled_tools)
        service["tool_count"] = service["enabled_tool_count"]
        published.append(service)
    return published


def register_service(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    name: Any,
    url: Any,
    transport: Any,
    description: Any = None,
    secret_scope: Any = None,
    created_by: str | None = None,
) -> dict[str, Any]:
    """Register a new external MCP service in the workspace inventory.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Workspace the service is registered under.
        name: Service name, unique within the workspace.
        url: Endpoint URL (network transports) or launch command
            (``stdio``).
        transport: One of :data:`MCP_SERVICE_TRANSPORTS`.
        description: Optional free-form purpose note.
        secret_scope: Optional name of a ``secret_scopes`` vault
            holding the service's external credentials.
        created_by: E-mail of the registering admin, for the audit
            column.

    Returns:
        The serialised newly-created service (with an empty tool list).

    Raises:
        ValueError: When a field is malformed or the name already
            exists in the workspace.
    """
    clean_name = _clean_name(name, what="name")
    clean_url = _clean_name(url, what="url")
    clean_transport = _validate_transport(transport)
    now = _utcnow()
    with factory() as session:
        existing = session.scalar(
            select(McpService.id).where(
                McpService.workspace_id == workspace_id,
                McpService.name == clean_name,
            )
        )
        if existing is not None:
            raise ValueError(
                f"an MCP service named {clean_name!r} already exists in this workspace"
            )
        service = McpService(
            workspace_id=workspace_id,
            name=clean_name,
            url=clean_url,
            transport=clean_transport,
            description=_clean_optional(description),
            secret_scope=_clean_optional(secret_scope),
            enabled=True,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        session.add(service)
        try:
            session.commit()
        except IntegrityError as exc:
            # A concurrent register raced past the existence check above.
            session.rollback()
            raise ValueError(
                f"an MCP service named {clean_name!r} already exists in this workspace"
            ) from exc
        session.refresh(service)
        return _service_dict(service, [])


def update_service(
    factory: sessionmaker[Session],
    *,
    service_id: int,
    workspace_id: int,
    name: Any = None,
    url: Any = None,
    transport: Any = None,
    description: Any = None,
    secret_scope: Any = None,
) -> dict[str, Any]:
    """Patch the mutable fields of a registered service.

    Only the arguments that are not ``None`` are applied, except
    ``description`` and ``secret_scope`` which accept an explicit empty
    string to clear the column.

    Args:
        factory: SQLAlchemy session factory.
        service_id: Primary key of the service to patch.
        workspace_id: Owning workspace; a service in any other workspace
            is rejected as unknown.
        name: New unique name, when changing it.
        url: New endpoint URL / launch command.
        transport: New transport — one of
            :data:`MCP_SERVICE_TRANSPORTS`.
        description: New description; ``""`` clears it, ``None`` leaves
            it unchanged.
        secret_scope: New secret-scope pointer; ``""`` clears it,
            ``None`` leaves it unchanged.

    Returns:
        The serialised updated service with its current tools.

    Raises:
        ValueError: When the service is unknown, a field is malformed,
            or the new name collides with another service in the
            workspace.
    """
    with factory() as session:
        service = session.get(McpService, service_id)
        if service is None or int(service.workspace_id) != workspace_id:
            raise ValueError(f"MCP service {service_id} not found")
        if name is not None:
            clean_name = _clean_name(name, what="name")
            clash = session.scalar(
                select(McpService.id).where(
                    McpService.workspace_id == service.workspace_id,
                    McpService.name == clean_name,
                    McpService.id != service_id,
                )
            )
            if clash is not None:
                raise ValueError(
                    f"an MCP service named {clean_name!r} already exists in this workspace"
                )
            service.name = clean_name
        if url is not None:
            service.url = _clean_name(url, what="url")
        if transport is not None:
            service.transport = _validate_transport(transport)
        if description is not None:
            service.description = _clean_optional(description)
        if secret_scope is not None:
            service.secret_scope = _clean_optional(secret_scope)
        service.updated_at = _utcnow()
        session.commit()
        session.refresh(service)
        return _service_dict(service, _load_tools(session, service.id))


def set_service_enabled(
    factory: sessionmaker[Session], *, service_id: int, workspace_id: int, enabled: bool
) -> dict[str, Any]:
    """Publish or un-publish a service without deleting it.

    Args:
        factory: SQLAlchemy session factory.
        service_id: Primary key of the service.
        workspace_id: Owning workspace; a service in any other workspace
            is rejected as unknown.
        enabled: Target enabled state.

    Returns:
        The serialised service with its tools.

    Raises:
        ValueError: When the service is unknown.
    """
    with factory() as session:
        service = session.get(McpService, service_id)
        if service is None or int(service.workspace_id) != workspace_id:
            raise ValueError(f"MCP service {service_id} not found")
        service.enabled = bool(enabled)
        service.updated_at = _utcnow()
        session.commit()
        session.refresh(service)
        return _service_dict(service, _load_tools(session, service.id))


def delete_service(factory: sessionmaker[Session], *, service_id: int, workspace_id: int) -> bool:
    """Delete a service and (via cascade) all of its tools.

    Args:
        factory: SQLAlchemy session factory.
        service_id: Primary key of the service.
        workspace_id: Owning workspace; a service in any other workspace
            is left untouched and reported as no-match.

    Returns:
        ``True`` when a row was removed, ``False`` when none matched.
    """
    with factory() as session:
        service = session.get(McpService, service_id)
        if service is None or int(service.workspace_id) != workspace_id:
            return False
        # Explicit child delete keeps SQLite (no ON DELETE enforcement
        # without PRAGMA) and Postgres on the same footing.
        session.execute(delete(McpServiceTool).where(McpServiceTool.service_id == service_id))
        session.delete(service)
        session.commit()
        return True


def add_tool(
    factory: sessionmaker[Session],
    *,
    service_id: int,
    workspace_id: int,
    name: Any,
    description: Any = None,
) -> dict[str, Any]:
    """Add one advertised tool to a service's inventory.

    Args:
        factory: SQLAlchemy session factory.
        service_id: Primary key of the owning service.
        workspace_id: Owning workspace; a service in any other workspace
            is rejected as unknown.
        name: Tool name, unique within the service.
        description: Optional free-form note.

    Returns:
        The serialised newly-created tool.

    Raises:
        ValueError: When the service is unknown, the name is malformed,
            or the tool name already exists on the service.
    """
    clean_name = _clean_name(name, what="name")
    with factory() as session:
        service = session.get(McpService, service_id)
        if service is None or int(service.workspace_id) != workspace_id:
            raise ValueError(f"MCP service {service_id} not found")
        existing = session.scalar(
            select(McpServiceTool.id).where(
                McpServiceTool.service_id == service_id,
                McpServiceTool.name == clean_name,
            )
        )
        if existing is not None:
            raise ValueError(f"a tool named {clean_name!r} already exists on this service")
        tool = McpServiceTool(
            service_id=service_id,
            name=clean_name,
            description=_clean_optional(description),
            enabled=True,
            created_at=_utcnow(),
        )
        session.add(tool)
        service.updated_at = _utcnow()
        try:
            session.commit()
        except IntegrityError as exc:
            # A concurrent add raced past the existence check above.
            session.rollback()
            raise ValueError(f"a tool named {clean_name!r} already exists on this service") from exc
        session.refresh(tool)
        return _tool_dict(tool)


def set_tool_enabled(
    factory: sessionmaker[Session],
    *,
    service_id: int,
    workspace_id: int,
    tool_id: int,
    enabled: bool,
) -> dict[str, Any]:
    """Toggle the per-tool allow flag.

    Args:
        factory: SQLAlchemy session factory.
        service_id: Primary key of the owning service (guards against
            cross-service tool ids).
        workspace_id: Owning workspace; a service in any other workspace
            is rejected as unknown.
        tool_id: Primary key of the tool.
        enabled: Target enabled state.

    Returns:
        The serialised tool.

    Raises:
        ValueError: When no tool with that id belongs to the service.
    """
    with factory() as session:
        service = session.get(McpService, service_id)
        if service is None or int(service.workspace_id) != workspace_id:
            raise ValueError(f"tool {tool_id} not found on MCP service {service_id}")
        tool = session.get(McpServiceTool, tool_id)
        if tool is None or tool.service_id != service_id:
            raise ValueError(f"tool {tool_id} not found on MCP service {service_id}")
        tool.enabled = bool(enabled)
        session.commit()
        session.refresh(tool)
        return _tool_dict(tool)


def delete_tool(
    factory: sessionmaker[Session], *, service_id: int, workspace_id: int, tool_id: int
) -> bool:
    """Remove one tool from a service's inventory.

    Args:
        factory: SQLAlchemy session factory.
        service_id: Primary key of the owning service.
        workspace_id: Owning workspace; a service in any other workspace
            is left untouched and reported as no-match.
        tool_id: Primary key of the tool.

    Returns:
        ``True`` when the tool was removed, ``False`` when no matching
        tool belongs to the service.
    """
    with factory() as session:
        service = session.get(McpService, service_id)
        if service is None or int(service.workspace_id) != workspace_id:
            return False
        tool = session.get(McpServiceTool, tool_id)
        if tool is None or tool.service_id != service_id:
            return False
        session.delete(tool)
        session.commit()
        return True
