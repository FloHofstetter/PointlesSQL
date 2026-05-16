"""Per-request context injection for the shared TemplateResponse wrapper.

Phase 86 B4 split this out of ``main.py``.  The wrapper attaches:

* ``current_user`` from ``request.state.user``.
* ``current_workspace`` / ``available_workspaces`` /
  ``current_workspace_primary_catalog`` from a single per-request DB
  hit, with try/except so a transient DB failure during template
  render falls back to a blank context instead of 500-ing.
* ``nav_badges`` computed via
  :func:`pointlessql.services.nav_badges.compute_nav_badges`.

The wrapper is installed by :func:`install_template_wrapper`, which
captures the original ``Jinja2Templates.TemplateResponse`` and rebinds
the attribute in place — same one-shot mutation the monolith did.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from fastapi import Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)


def _resolve_workspace_context(request: Request) -> dict[str, Any]:
    """Build the workspace-scoped Jinja context for one TemplateResponse call.

    Returns a dict with ``current_workspace``, ``available_workspaces``
    (the list rendered by the topbar switcher), and
    ``current_workspace_primary_catalog`` (used by the catalog tree
    to pre-expand on first load).  Every lookup is wrapped in a
    try/except so a transient DB failure during template render
    falls back to a blank context rather than 500ing the whole
    page.
    """
    factory = getattr(request.app.state, "session_factory", None)
    workspace_id = getattr(request.state, "workspace_id", None)
    user = getattr(request.state, "user", None)
    if factory is None or workspace_id is None:
        return {
            "current_workspace": None,
            "available_workspaces": [],
            "current_workspace_primary_catalog": None,
        }
    try:
        from sqlalchemy import select as _select

        from pointlessql.models import Workspace, WorkspaceCatalogPin
        from pointlessql.services.workspace import _crud as ws_service

        with factory() as session:
            current = session.get(Workspace, workspace_id)
            primary_pin = None
            if current is not None:
                primary_pin = session.scalar(
                    _select(WorkspaceCatalogPin).where(
                        WorkspaceCatalogPin.workspace_id == current.id,
                        WorkspaceCatalogPin.mode == "primary",
                    )
                )
            if current is not None:
                session.expunge(current)

        available: list[Any] = []
        if user is not None and isinstance(user.get("id"), int) and user["id"] > 0:
            available = ws_service.list_workspaces_for_user(factory, user_id=int(user["id"]))

        return {
            "current_workspace": current,
            "available_workspaces": available,
            "current_workspace_primary_catalog": (
                primary_pin.catalog_name if primary_pin is not None else None
            ),
        }
    except Exception:  # noqa: BLE001 — template render must not 500 on a workspace-lookup hiccup
        logger.debug("Failed to resolve workspace context for template", exc_info=True)
        return {
            "current_workspace": None,
            "available_workspaces": [],
            "current_workspace_primary_catalog": None,
        }


def _resolve_nav_badges(request: Request) -> dict[str, int]:
    """Compute the primary-rail badge counts for one TemplateResponse.

    Delegates to :func:`pointlessql.services.nav_badges.compute_nav_badges`
    so the query lives next to the other audit aggregators rather than
    in the templates wrapper.  Keys consumed by
    ``components/primary_rail.html``:

    * ``runs_pending``  — agent runs awaiting approval.
    * ``audit_unread``  — unread notification count.
    * ``alerts_firing`` — active alert definitions.

    Args:
        request: Starlette request whose ``state.workspace_id`` /
            ``state.user`` resolve the workspace scope.

    Returns:
        Dict mapping badge key to integer count.  Empty if the request
        has no DB factory or the aggregator throws.  Zero-valued keys
        are filtered template-side via ``and value > 0``.
    """
    factory = getattr(request.app.state, "session_factory", None)
    user = getattr(request.state, "user", None)
    workspace_id = int(getattr(request.state, "workspace_id", 0) or 0)
    user_id = int((user or {}).get("id") or 0)
    from pointlessql.services.nav_badges import compute_nav_badges

    badges = compute_nav_badges(factory, user_id, workspace_id)
    # NavBadges is a TypedDict with int values; cast each via
    # ``cast(int, …)`` for the Jinja consumer.  ``.items()`` returns
    # the values as ``object`` because TypedDict is invariant.
    return {key: cast(int, value) for key, value in badges.items()}


def install_template_wrapper(templates: Jinja2Templates) -> None:
    """Rebind ``templates.TemplateResponse`` to the context-injecting wrapper.

    The wrapper preserves the original positional / keyword call
    shapes used by Starlette 0.37+ (``TemplateResponse(request, name,
    context={})``) plus the legacy ``(name, context, request=request)``
    one some routes still use.  ``setdefault`` keeps explicit per-call
    overrides — routes that pass ``current_user`` or ``nav_badges``
    deliberately are never clobbered.

    Args:
        templates: The shared :class:`Jinja2Templates` instance.
    """
    original = templates.TemplateResponse

    def wrapped(request: Request, *args: Any, **kwargs: Any) -> Response:
        # TemplateResponse(request, name, context) or (name, context, request=request)
        # Starlette 0.37+ signature: TemplateResponse(request, name, context={}, ...)
        workspace_ctx = _resolve_workspace_context(request)
        nav_badges = _resolve_nav_badges(request)
        user = getattr(request.state, "user", None)
        if "context" in kwargs:
            ctx = kwargs["context"]
            ctx.setdefault("current_user", user)
            ctx.setdefault("nav_badges", nav_badges)
            for key, value in workspace_ctx.items():
                ctx.setdefault(key, value)
        elif len(args) >= 2 and isinstance(args[1], dict):
            mutable = list(args)
            ctx = mutable[1]
            ctx.setdefault("current_user", user)
            ctx.setdefault("nav_badges", nav_badges)
            for key, value in workspace_ctx.items():
                ctx.setdefault(key, value)
            args = tuple(mutable)
        return original(request, *args, **kwargs)

    templates.TemplateResponse = wrapped  # type: ignore[assignment]


__all__ = ["install_template_wrapper"]
