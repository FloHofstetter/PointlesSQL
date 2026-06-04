"""Workspace service layer — CRUD + non-HTTP context resolution.

Three discrete responsibilities:

1. **CRUD primitives** (:func:`create_workspace`, :func:`add_member`,
   :func:`list_workspaces_for_user`, :func:`get_workspace_by_slug`)
   used by the admin UI and the bootstrap seed migration.

2. **The non-HTTP context resolver** :func:`resolve_workspace_id`
   that the auth middleware, the scheduler tick loop, the CLI, and
   the test fixtures all share.  Resolution priority is::

       X-Workspace header → session-cookie → user.default → 1

   so a Hermes-style runtime can pin per-call workspace via the
   header while a browser session falls back to the user's stored
   default; the fixed ``1`` floor guarantees that even an entirely
   unauthenticated path resolves to *some* workspace, keeping the
   request pipeline crash-free during deployment-time edge cases
   (a brand-new install before any user has registered, an
   anonymous probe to a public endpoint, etc.).

3. **Mismatch logging** (:func:`audit_workspace_mismatch`) for the
   case where a request asks for a workspace the user is *not* a
   member of.  The middleware writes an ``audit_log`` row with
   ``action='workspace.context_mismatch'`` and 403s the request so
   the cross-workspace probe is observable in the same audit lake
   the cockpit reads.
"""

from __future__ import annotations

import datetime
import logging
import re

from sqlalchemy import select

from pointlessql.models import (
    WORKSPACE_PIN_MODES,
    WORKSPACE_ROLES,
    User,
    Workspace,
    WorkspaceCatalogPin,
    WorkspaceMember,
)
from pointlessql.types import SessionFactory

logger = logging.getLogger(__name__)

#: Reserved workspace id always present after the bootstrap
#: migration.  Used as the ultimate-fallback floor so the request
#: pipeline never sees ``workspace_id == None``.
DEFAULT_WORKSPACE_ID: int = 1
DEFAULT_WORKSPACE_SLUG: str = "default"


_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}[a-z0-9]$|^[a-z0-9]$")



def _validate_slug(slug: str) -> str:
    """Return *slug* lowered and stripped, or raise on shape violation.

    Slugs are URL- and header-safe identifiers — the ``X-Workspace``
    header carries them verbatim and the auth-routes ``switch-workspace``
    endpoint reads them off a cookie, so anything outside
    ``[a-z0-9_-]`` would force escaping at every hop.

    Args:
        slug: Caller-supplied workspace slug.

    Returns:
        The cleaned slug (lower-cased, trimmed).

    Raises:
        ValueError: When *slug* is empty, longer than 64 chars, or
            contains characters outside ``[a-z0-9_-]``, or starts /
            ends with a separator.
    """
    cleaned = slug.strip().lower()
    if not cleaned or len(cleaned) > 64:
        raise ValueError("workspace slug must be 1..64 chars")
    if not _SLUG_RE.match(cleaned):
        raise ValueError(
            f"workspace slug {cleaned!r} must match [a-z0-9_-] and not start/end with - or _"
        )
    return cleaned


def create_workspace(
    session_factory: SessionFactory,
    *,
    slug: str,
    name: str,
    description: str | None = None,
    creator_user_id: int | None = None,
) -> Workspace:
    """Insert a new :class:`Workspace` row plus admin membership for the creator.

    The creator (when given) is auto-added as a workspace-local
    ``admin`` so the CRUD UI immediately has a manage-this-workspace
    surface for the user who just created it.  The seeded
    ``default`` workspace skips this hop because there is no creator
    at migration time — every existing user is added as a member by
    the bootstrap migration directly.

    Args:
        session_factory: Sessionmaker callable.
        slug: URL-safe identifier; see :func:`_validate_slug`.
        name: Human-readable label (max 200 chars).
        description: Optional free-form note.
        creator_user_id: User who created the workspace.  When set,
            also inserted as a workspace-local admin in the same
            transaction.

    Returns:
        The detached :class:`Workspace` row.

    Raises:
        ValueError: When the slug is malformed or already taken.
    """
    cleaned_slug = _validate_slug(slug)
    cleaned_name = name.strip()
    if not cleaned_name or len(cleaned_name) > 200:
        raise ValueError("workspace name must be 1..200 chars")
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        existing = session.scalar(select(Workspace).where(Workspace.slug == cleaned_slug))
        if existing is not None:
            raise ValueError(f"workspace slug {cleaned_slug!r} already exists")
        row = Workspace(
            slug=cleaned_slug,
            name=cleaned_name,
            description=description.strip() if description else None,
            created_at=now,
        )
        session.add(row)
        session.flush()
        if creator_user_id is not None:
            session.add(
                WorkspaceMember(
                    workspace_id=row.id,
                    user_id=creator_user_id,
                    role="admin",
                    created_at=now,
                )
            )
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def add_member(
    session_factory: SessionFactory,
    *,
    workspace_id: int,
    user_id: int,
    role: str = "member",
) -> WorkspaceMember:
    """Grant *user_id* membership of *workspace_id* with *role*.

    Idempotent at the API level: re-adding an existing member with
    the same role is a no-op (the existing row is returned).
    Re-adding with a *different* role updates the existing row in
    place — the unique constraint on (workspace_id, user_id) means
    the alternative would be an :class:`IntegrityError` that the
    admin UI would have to special-case.

    Args:
        session_factory: Sessionmaker callable.
        workspace_id: FK to :class:`Workspace`.
        user_id: FK to :class:`User`.
        role: One of :data:`WORKSPACE_ROLES`.

    Returns:
        The detached :class:`WorkspaceMember` row.

    Raises:
        ValueError: When *role* is not in :data:`WORKSPACE_ROLES`.
    """
    if role not in WORKSPACE_ROLES:
        raise ValueError(f"workspace role {role!r} not in {WORKSPACE_ROLES}")
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        existing = session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        if existing is not None:
            if existing.role != role:
                existing.role = role
                session.commit()
                session.refresh(existing)
            session.expunge(existing)
            return existing
        row = WorkspaceMember(
            workspace_id=workspace_id,
            user_id=user_id,
            role=role,
            created_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row


def list_workspaces_for_user(
    session_factory: SessionFactory,
    *,
    user_id: int,
    include_archived: bool = False,
) -> list[Workspace]:
    """Return every active workspace *user_id* is a member of.

    Used by the switcher dropdown and by the middleware to validate
    ``X-Workspace`` requests.  Tenant-wide admins
    (``users.is_admin = True``) still see only their explicit
    memberships here; the cross-workspace lens is a separate route
    that explicitly opts into the god-eye view.

    Args:
        session_factory: Sessionmaker callable.
        user_id: User whose memberships to return.
        include_archived: When ``True``, include workspaces whose
            :attr:`Workspace.archived_at` is set.

    Returns:
        Detached :class:`Workspace` rows ordered by ``name``.
    """
    with session_factory() as session:
        stmt = (
            select(Workspace)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == user_id)
        )
        if not include_archived:
            stmt = stmt.where(Workspace.archived_at.is_(None))
        stmt = stmt.order_by(Workspace.name.asc())
        rows = list(session.scalars(stmt).all())
        for row in rows:
            session.expunge(row)
        return rows


def get_workspace_by_slug(session_factory: SessionFactory, *, slug: str) -> Workspace | None:
    """Return the workspace with *slug* or ``None`` when no such row exists.

    Args:
        session_factory: Sessionmaker callable.
        slug: Workspace slug (case-insensitive).

    Returns:
        The detached :class:`Workspace` row, or ``None``.
    """
    cleaned = slug.strip().lower()
    with session_factory() as session:
        row = session.scalar(select(Workspace).where(Workspace.slug == cleaned))
        if row is not None:
            session.expunge(row)
        return row


def get_workspace(session_factory: SessionFactory, *, workspace_id: int) -> Workspace | None:
    """Return the workspace with *workspace_id* or ``None``."""
    with session_factory() as session:
        row = session.get(Workspace, workspace_id)
        if row is not None:
            session.expunge(row)
        return row


def is_member(session_factory: SessionFactory, *, workspace_id: int, user_id: int) -> bool:
    """Return ``True`` when the user is a member of the workspace."""
    with session_factory() as session:
        row = session.scalar(
            select(WorkspaceMember.id).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        return row is not None


def get_membership_role(
    session_factory: SessionFactory, *, workspace_id: int, user_id: int
) -> str | None:
    """Return the user's role in the workspace, or ``None`` when not a member."""
    with session_factory() as session:
        row = session.scalar(
            select(WorkspaceMember.role).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        return row


def resolve_workspace_id(
    session_factory: SessionFactory | None,
    *,
    user_id: int | None,
    header_value: str | None = None,
    cookie_value: str | None = None,
    api_key_workspace_id: int | None = None,
) -> tuple[int, str]:
    """Pick the active workspace for the current request / tick.

    The non-HTTP entry point used by middleware, scheduler tick,
    CLI, and test fixtures.  Resolution priority::

        explicit X-Workspace header (slug)
            → API-key's pinned workspace_id
                → session-cookie current_workspace_slug
                    → user.default_workspace_id
                        → DEFAULT_WORKSPACE_ID (=1)

    The order is deliberate:

    * **Header wins** so a Hermes-driven agent can re-target per
      tool call without touching the user's stored default.
    * **API-key pin beats cookie** because Bearer-token auth
      doesn't carry a session cookie at all — the pin IS the
      caller's stored intent.
    * **User default beats fallback** so a browser session ends up
      where the user last logged in.
    * **The literal ``1`` floor** keeps the request pipeline safe
      during exotic edge cases (anonymous public-prefix probe,
      brand-new install before the seed migration ran, test fixture
      that bypasses the standard bootstrap).

    The function never raises — even an invalid header is treated
    as *resolution failure* and degrades to the next priority tier
    rather than 4xxing.  The middleware separately enforces
    membership and surfaces the 403 / audit-log row when a known
    user asks for a workspace they don't belong to.

    Args:
        session_factory: Sessionmaker callable.  ``None`` is
            tolerated for paths that haven't wired the DB yet
            (the function falls back to ``DEFAULT_WORKSPACE_ID``).
        user_id: ID of the authenticated user, or ``None`` for
            anonymous / API-key calls.
        header_value: Raw ``X-Workspace`` header value (slug).
        cookie_value: ``current_workspace_slug`` from the session
            cookie payload.
        api_key_workspace_id: Pinned workspace from the matched
            ``api_keys`` row, or ``None`` when not Bearer-authed.

    Returns:
        ``(workspace_id, source)`` tuple where ``source`` is one of
        ``"header"``, ``"api_key"``, ``"cookie"``, ``"user_default"``,
        or ``"fallback"`` for telemetry / mismatch-logging.
    """
    if session_factory is None:
        return DEFAULT_WORKSPACE_ID, "fallback"

    try:
        # 1. Explicit header (slug → id).
        if header_value and header_value.strip():
            ws = get_workspace_by_slug(session_factory, slug=header_value.strip())
            if ws is not None:
                return ws.id, "header"

        # 2. API-key pin.
        if api_key_workspace_id is not None:
            return api_key_workspace_id, "api_key"

        # 3. Cookie slug.
        if cookie_value and cookie_value.strip():
            ws = get_workspace_by_slug(session_factory, slug=cookie_value.strip())
            if ws is not None:
                return ws.id, "cookie"

        # 4. User default.
        if user_id:
            with session_factory() as session:
                user = session.get(User, user_id)
                if user is not None and user.default_workspace_id is not None:
                    return user.default_workspace_id, "user_default"
    except Exception:  # noqa: BLE001 — resolution must never break the request pipeline
        logger.debug("Workspace resolution failed; falling back to default", exc_info=True)
        return DEFAULT_WORKSPACE_ID, "fallback"

    return DEFAULT_WORKSPACE_ID, "fallback"


__all__ = [
    "DEFAULT_WORKSPACE_ID",
    "DEFAULT_WORKSPACE_SLUG",
    "WORKSPACE_PIN_MODES",
    "WORKSPACE_ROLES",
    "WorkspaceCatalogPin",
    "add_member",
    "create_workspace",
    "get_membership_role",
    "get_workspace",
    "get_workspace_by_slug",
    "is_member",
    "list_workspaces_for_user",
    "resolve_workspace_id",
]
