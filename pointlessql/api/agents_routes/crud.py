"""``/api/agents`` — CRUD + verify.

Admin-only mutations.  Listing is workspace-scoped and visible
to any authenticated caller.
"""

from __future__ import annotations

import datetime
import re
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import func, select

from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.exceptions import (
    AuthorizationError,
    BadRequestError,
    ResourceNotFoundError,
)
from pointlessql.models.agent._agents import AVATAR_KINDS, Agent
from pointlessql.models.auth import User
from pointlessql.services import audit as audit_service

router = APIRouter(tags=["agents"])

_AUDIT_AGENT_CREATED = "audit.agent.created"
_AUDIT_AGENT_VERIFIED = "audit.agent.verified"
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    """Lowercase + collapse non-alphanumeric runs."""
    return _SLUG_RE.sub("-", name.strip().lower()).strip("-")[:60] or "agent"


def _serialise_agent(agent: Agent, principal_email: str | None = None) -> dict[str, Any]:
    """Serialise an Agent row as a JSON-friendly dict."""
    return {
        "id": agent.id,
        "slug": agent.slug,
        "display_name": agent.display_name,
        "avatar_kind": agent.avatar_kind,
        "avatar_url": agent.avatar_url,
        "home_url": agent.home_url,
        "principal_user_id": agent.principal_user_id,
        "principal_email": principal_email,
        "is_verified": bool(agent.is_verified),
        "verified_by_user_id": agent.verified_by_user_id,
        "verified_at": agent.verified_at.isoformat()
        if agent.verified_at
        else None,
        "bio_md": agent.bio_md,
        "created_at": agent.created_at.isoformat(),
    }


@router.get("/api/agents")
async def list_agents(
    request: Request, q: str | None = None
) -> dict[str, Any]:
    """Return the workspace's registered agents.

    Args:
        request: Incoming FastAPI request.
        q: Optional name / slug filter — case-
            insensitive prefix match against ``display_name`` or
            ``slug`` used by the mention-autocomplete picker.

    Returns:
        ``{"agents": [...]}`` sorted by display name.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        stmt = (
            select(Agent)
            .where(Agent.workspace_id == workspace_id)
            .order_by(Agent.display_name)
        )
        if q:
            needle = f"{q.strip().lower()}%"
            stmt = stmt.where(
                func.lower(Agent.slug).like(needle)
                | func.lower(Agent.display_name).like(needle)
            )
        rows = session.execute(stmt).scalars().all()
        principals = {
            int(uid): email
            for uid, email in session.execute(
                select(User.id, User.email).where(
                    User.id.in_({a.principal_user_id for a in rows})
                )
            ).all()
        }
    return {
        "agents": [
            _serialise_agent(a, principals.get(int(a.principal_user_id)))
            for a in rows
        ]
    }


@router.post("/api/agents")
async def create_agent(request: Request) -> dict[str, Any]:
    """Register a new agent identity.

    Body keys: ``display_name`` (required), ``principal_user_id``
    (required), ``avatar_kind``, ``avatar_url``, ``home_url``,
    ``bio_md``.

    Args:
        request: Incoming FastAPI request.

    Returns:
        Serialised agent row.

    Raises:
        AuthorizationError: When the caller is not install-admin.
        HTTPException: 400 on missing fields, unknown avatar_kind,
            slug collision; 404 if principal_user_id is unknown.
    """
    require_user(request)
    caller = get_user(request)
    if not caller.get("is_admin"):
        raise AuthorizationError(
            principal=caller.get("email", ""),
            privilege="create_agent",
            securable_type="agent",
            full_name="*",
        )
    workspace_id = current_workspace_id(request)

    body = await request.json()
    display_name = (body.get("display_name") or "").strip()
    principal_user_id_raw = body.get("principal_user_id")
    avatar_kind = (body.get("avatar_kind") or "custom").strip().lower()
    if not display_name:
        raise BadRequestError("display_name is required")
    if principal_user_id_raw is None:
        raise BadRequestError("principal_user_id is required")
    if avatar_kind not in AVATAR_KINDS:
        raise BadRequestError(f"avatar_kind must be one of {AVATAR_KINDS}")
    principal_user_id = int(principal_user_id_raw)

    now = datetime.datetime.now(datetime.UTC)
    factory = request.app.state.session_factory
    with factory() as session:
        principal = session.get(User, principal_user_id)
        if principal is None:
            raise ResourceNotFoundError.not_found(
                what=f"principal user id={principal_user_id}"
            )
        slug_base = _slugify(display_name)
        slug = slug_base
        n = 1
        while session.execute(
            select(Agent.id).where(
                Agent.workspace_id == workspace_id, Agent.slug == slug
            )
        ).first() is not None:
            n += 1
            slug = f"{slug_base}-{n}"
        agent = Agent(
            workspace_id=workspace_id,
            slug=slug,
            display_name=display_name[:80],
            avatar_kind=avatar_kind,
            avatar_url=body.get("avatar_url"),
            home_url=body.get("home_url"),
            principal_user_id=principal_user_id,
            bio_md=(body.get("bio_md") or ""),
            created_at=now,
            created_by_user_id=caller["id"],
        )
        session.add(agent)
        session.commit()
        session.refresh(agent)
        principal_email = principal.email
        agent_payload = _serialise_agent(agent, principal_email)

    audit_service.log_action(
        factory,
        user_id=caller["id"],
        user_email=caller.get("email", ""),
        action=_AUDIT_AGENT_CREATED,
        target=f"agent:{agent_payload['slug']}",
        detail={
            "agent_id": agent_payload["id"],
            "principal_user_id": principal_user_id,
            "display_name": display_name,
        },
        workspace_id=workspace_id,
    )
    return agent_payload


@router.post("/api/agents/{slug}/verify")
async def verify_agent(slug: str, request: Request) -> dict[str, Any]:
    """Flip the verified flag on an agent.

    Args:
        slug: Agent identifier.
        request: Incoming FastAPI request.

    Returns:
        Serialised updated agent.

    Raises:
        AuthorizationError: Admin-only.
        HTTPException: 404 when slug is unknown.
    """
    require_user(request)
    caller = get_user(request)
    if not caller.get("is_admin"):
        raise AuthorizationError(
            principal=caller.get("email", ""),
            privilege="verify_agent",
            securable_type="agent",
            full_name=slug,
        )
    workspace_id = current_workspace_id(request)
    now = datetime.datetime.now(datetime.UTC)
    factory = request.app.state.session_factory
    with factory() as session:
        agent = session.execute(
            select(Agent).where(
                Agent.workspace_id == workspace_id, Agent.slug == slug
            )
        ).scalar_one_or_none()
        if agent is None:
            raise ResourceNotFoundError("agent not found.")
        agent.is_verified = True
        agent.verified_by_user_id = caller["id"]
        agent.verified_at = now
        session.commit()
        session.refresh(agent)
        principal = session.get(User, agent.principal_user_id)
        principal_email = principal.email if principal else None
        agent_payload = _serialise_agent(agent, principal_email)

    audit_service.log_action(
        factory,
        user_id=caller["id"],
        user_email=caller.get("email", ""),
        action=_AUDIT_AGENT_VERIFIED,
        target=f"agent:{slug}",
        detail={"agent_id": agent_payload["id"]},
        workspace_id=workspace_id,
    )
    return agent_payload
