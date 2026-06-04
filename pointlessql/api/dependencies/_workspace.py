"""Workspace-context request dependencies.

Resolve the active workspace id / row, the data-product the caller is
reading "in the context of" (for the consumption check), and the
workspace-admin gate.  A transient placeholder workspace keeps the
request pipeline from 500-ing when the seeded default is missing.
"""

from __future__ import annotations

from fastapi import Request

from pointlessql.exceptions import AuthorizationError
from pointlessql.models import DataProduct, Workspace
from pointlessql.services.workspace import _crud as workspaces_service

from ._principal import get_user


def current_workspace_id(request: Request) -> int:
    """Return the active workspace id resolved by :func:`auth_middleware`.

    The auth middleware attaches ``request.state.workspace_id`` on
    every request via
    :func:`pointlessql.services.workspace._crud.resolve_workspace_id`.
    Routes that need to scope SQL by workspace pull the id through
    this dependency instead of reading the request state directly so
    the contract stays grep-able and a future swap-out (e.g. flipping
    to a typed dataclass) only touches one helper.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The active workspace id, defaulting to
        :data:`workspaces_service.DEFAULT_WORKSPACE_ID` when the
        middleware did not run (e.g. unit tests bypassing it).
    """
    value = getattr(request.state, "workspace_id", None)
    if isinstance(value, int) and value > 0:
        return value
    return workspaces_service.DEFAULT_WORKSPACE_ID


_AUTHORING_PRODUCT_HEADER = "x-pointlessql-authoring-product"


def get_authoring_product(request: Request) -> int | None:
    """Return the data-product PK the caller is reading "in the context of".

    Resolved in order:

    1. The ``X-PointlesSQL-Authoring-Product`` header,
       ``catalog.schema`` form.  External agents (Hermes, dbt, an
       ops script) declare the consuming product explicitly so the
       D2 consumption check has something to enforce against.
    2. The ``?as_product=`` query param on the SQL-editor / notebook
       session — the in-browser flow that binds an editor tab to a
       product.
    3. ``request.state.authoring_data_product_id`` when the caller
       opened a notebook in product-context (set by the notebook
       open handler when 124's domain binding is present).

    When none of these set a value the function returns ``None`` —
    no enforcement; admin / free-form reads keep working untouched.
    The honest-split lives here: the *absence* of an authoring
    product is interpreted as "the request is not bound to a product
    contract" rather than "deny by default".

    Args:
        request: Incoming FastAPI request.

    Returns:
        The matching :class:`DataProduct` PK, or ``None`` when no
        authoring product is bound or the binding can't be resolved.
    """
    from sqlalchemy import select  # noqa: PLC0415 — lazy, dep-tree gain

    raw: str | None = None
    header = request.headers.get(_AUTHORING_PRODUCT_HEADER)
    if header and header.strip():
        raw = header.strip()
    if raw is None:
        query_value = request.query_params.get("as_product")
        if query_value and query_value.strip():
            raw = query_value.strip()
    if raw is None:
        state_value = getattr(request.state, "authoring_data_product_id", None)
        if isinstance(state_value, int) and state_value > 0:
            return state_value
        return None

    parts = raw.split(".")
    if len(parts) != 2 or not all(parts):
        return None
    catalog, schema = parts[0], parts[1]
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return None
    workspace_id = current_workspace_id(request)
    with factory() as session:
        row = session.scalar(
            select(DataProduct).where(
                DataProduct.workspace_id == workspace_id,
                DataProduct.catalog_name == catalog,
                DataProduct.schema_name == schema,
            )
        )
    return int(row.id) if row is not None else None


def current_workspace(request: Request) -> Workspace:
    """Return the active :class:`Workspace` row resolved for this request.

    Convenience for HTML routes that want the slug / name in the
    rendered template.  Always returns a row — when the seeded
    default is missing (development-time anomaly) we synthesise a
    transient placeholder rather than raise, because the request
    pipeline must not 500 on a startup edge case.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The detached :class:`Workspace` row.
    """
    factory = getattr(request.app.state, "session_factory", None)
    workspace_id = current_workspace_id(request)
    if factory is None:
        return _placeholder_workspace(workspace_id)
    row = workspaces_service.get_workspace(factory, workspace_id=workspace_id)
    if row is None:
        return _placeholder_workspace(workspace_id)
    return row


def _placeholder_workspace(workspace_id: int) -> Workspace:
    """Synthesise a detached :class:`Workspace` row for safe template fallback.

    The pipeline must never 500 on a missing-default-workspace edge
    case (e.g. tests that bypass the seed migration).  This stand-in
    carries the resolved id and the conventional slug so templates
    that surface ``workspace.slug`` show something coherent.
    """
    import datetime

    placeholder = Workspace(
        id=workspace_id,
        slug=workspaces_service.DEFAULT_WORKSPACE_SLUG,
        name="Default workspace",
        description=None,
        created_at=datetime.datetime.now(datetime.UTC),
        archived_at=None,
    )
    return placeholder


def require_workspace_admin(request: Request) -> None:
    """Raise :class:`AuthorizationError` unless the caller is admin in this workspace.

    Tenant-wide admins (``users.is_admin = True``) always pass —
    they are strictly stronger than workspace-local admins so the
    cross-workspace lens and admin CRUD don't need to special-case
    themselves.  Workspace-local admins
    pass too via the :class:`WorkspaceMember.role` lookup.  Bearer
    keys never carry a per-workspace role today; admin UI pages are
    cookie-only by convention so this check refuses Bearer auth
    entirely.

    Args:
        request: Incoming FastAPI request.

    Raises:
        AuthorizationError: When the caller is neither a tenant
            admin nor a workspace-local admin.
    """
    user = get_user(request)
    if user.get("is_admin"):
        return
    user_id = user.get("id", 0)
    if not user_id:
        raise AuthorizationError(
            principal=user.get("email", ""),
            privilege="workspace.admin",
            securable_type="workspace",
            full_name="workspace",
        )
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise AuthorizationError(
            principal=user.get("email", ""),
            privilege="workspace.admin",
            securable_type="workspace",
            full_name="workspace",
        )
    workspace_id = current_workspace_id(request)
    role = workspaces_service.get_membership_role(
        factory, workspace_id=workspace_id, user_id=int(user_id)
    )
    if role == "admin":
        return
    raise AuthorizationError(
        principal=user.get("email", ""),
        privilege="workspace.admin",
        securable_type="workspace",
        full_name=f"workspace:{workspace_id}",
    )
