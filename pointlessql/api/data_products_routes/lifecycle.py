"""Product-lifecycle endpoints — read state + drive transitions.

The lifecycle surface lives under ``/api/data-products/{catalog}/{schema}``:

* ``GET    .../lifecycle`` — any authenticated user; returns the
  current state, reachable targets, the optional successor URN, and a
  short audit-log-driven history.
* ``POST   .../lifecycle/{target}`` — steward/admin only; drives the
  state-machine.  Targets: ``promote-to-active``, ``deprecate``,
  ``retire`` (body may carry ``replacement_uri``), ``archive``,
  ``restore``.
* ``POST   .../lifecycle/propose`` — any user; validates a proposed
  transition (no state write) and records an audit row so a steward
  can review.  Used by the supervised-agent plugin tool.

A successful transition stamps the audit log with action
``data_product.lifecycle_changed`` plus a ``detail`` payload carrying
``{from_state, to_state, replacement_uri?, note?}``; the proposal
records action ``data_product.lifecycle_proposed`` with the same
payload shape.  The history endpoint replays both actions.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Body, Request
from sqlalchemy import select

from pointlessql.api._audit_helpers import audit
from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.data_products_routes.proposals import (
    _require_steward_or_admin,  # pyright: ignore[reportPrivateUsage]
)
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.exceptions import BadRequestError, ResourceNotFoundError
from pointlessql.models import DataProduct, Workspace
from pointlessql.services import lifecycle as lifecycle_service
from pointlessql.services.lifecycle import (
    LifecycleHistoryEntry,
    LifecycleTransitionError,
)

router = APIRouter(tags=["data-products"])


#: Maps the URL-friendly target slug to the internal state name.  The
#: URL form uses kebab-case for the multi-word transitions; the
#: internal state is the bare name.
_TARGET_MAP: dict[str, str] = {
    "promote-to-active": "active",
    "deprecate": "deprecated",
    "retire": "retired",
    "archive": "archived",
    "restore": "active",
}


def _serialise_history(entry: LifecycleHistoryEntry) -> dict[str, Any]:
    """Render one :class:`LifecycleHistoryEntry` as JSON."""
    return {
        "from_state": entry.from_state,
        "to_state": entry.to_state,
        "actor_email": entry.actor_email,
        "proposed": entry.proposed,
        "replacement_uri": entry.replacement_uri,
        "note": entry.note,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


def _resolve_workspace_slug(factory: Any, workspace_id: int) -> str:
    """Return the workspace slug, falling back to the id as a string."""
    with factory() as session:
        ws = session.get(Workspace, workspace_id)
        return ws.slug if ws is not None else str(workspace_id)


def _resolve_replacement(
    factory: Any,
    *,
    workspace_id: int,
    replacement_uri: str | None,
) -> tuple[int | None, str | None]:
    """Look up the successor product id from a discovery URN.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Caller's workspace.
        replacement_uri: URN of the form
            ``urn:pointlessql:product:{ws_slug}:{catalog}:{schema}``.

    Returns:
        Tuple of ``(data_product_id, canonical_uri)`` or ``(None, None)``
        when *replacement_uri* is empty.

    Raises:
        BadRequestError: When the URN is malformed or the workspace slug
            in it does not match the caller's workspace.
        ResourceNotFoundError: When the URN resolves to no product.
    """
    if not replacement_uri:
        return None, None
    parts = replacement_uri.split(":")
    if len(parts) != 6 or parts[0] != "urn" or parts[1] != "pointlessql" or parts[2] != "product":
        raise BadRequestError(
            "replacement_uri must be of the form "
            "urn:pointlessql:product:{workspace}:{catalog}:{schema}"
        )
    ws_slug, catalog, schema = parts[3], parts[4], parts[5]
    caller_slug = _resolve_workspace_slug(factory, workspace_id)
    if ws_slug != caller_slug:
        raise BadRequestError(
            "replacement_uri must point to a product in your workspace "
            f"(expected {caller_slug!r}, got {ws_slug!r})"
        )
    with factory() as session:
        successor = session.scalar(
            select(DataProduct).where(
                DataProduct.workspace_id == workspace_id,
                DataProduct.catalog_name == catalog,
                DataProduct.schema_name == schema,
            )
        )
    if successor is None:
        raise ResourceNotFoundError(f"replacement product {catalog}.{schema} not found")
    return successor.id, replacement_uri


def _successor_uri(factory: Any, workspace_id: int, replacement_id: int | None) -> str | None:
    """Render the successor's URN, or ``None`` when none is set."""
    if replacement_id is None:
        return None
    with factory() as session:
        row = session.get(DataProduct, replacement_id)
        if row is None:
            return None
    slug = _resolve_workspace_slug(factory, workspace_id)
    return f"urn:pointlessql:product:{slug}:{row.catalog_name}:{row.schema_name}"


@router.get("/api/data-products/{catalog}/{schema}/lifecycle")
async def get_lifecycle(catalog: str, schema: str, request: Request) -> dict[str, Any]:
    """Return the product's current lifecycle state + reachable targets."""
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    history = lifecycle_service.list_history(
        factory, workspace_id=workspace_id, catalog=catalog, schema=schema
    )
    return {
        "state": dp_row.lifecycle_state,
        "changed_at": (
            dp_row.lifecycle_changed_at.isoformat() if dp_row.lifecycle_changed_at else None
        ),
        "reachable_targets": sorted(lifecycle_service.allowed_targets(dp_row.lifecycle_state)),
        "replacement_uri": _successor_uri(
            factory, workspace_id, dp_row.replacement_data_product_id
        ),
        "history": [_serialise_history(entry) for entry in history],
    }


@router.post("/api/data-products/{catalog}/{schema}/lifecycle/propose")
async def propose_lifecycle(
    catalog: str,
    schema: str,
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Record a proposed transition without applying it.

    Open to any authenticated user; intended for supervised agents that
    suggest a lifecycle move for a steward to review.  Body:
    ``{"target": "active"|"deprecated"|"retired"|"archived",
       "note"?: str}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)

    target = str(body.get("target") or "").strip()
    note = str(body.get("note") or "").strip()
    if not target:
        raise BadRequestError("target is required")
    try:
        current = lifecycle_service.propose_transition(
            factory,
            data_product_id=dp_row.id,
            target=target,
            actor_user_id=int(user["id"]) if user["id"] > 0 else None,
            note=note,
        )
    except LifecycleTransitionError as exc:
        raise BadRequestError(str(exc)) from exc
    await audit(
        request,
        lifecycle_service.LIFECYCLE_PROPOSED_ACTION,
        f"data_product:{catalog}.{schema}",
        {"from_state": current, "to_state": target, "note": note},
    )
    return {
        "current_state": current,
        "proposed_target": target,
        "note": note,
        "recorded_at": datetime.datetime.now(datetime.UTC).isoformat(),
    }


@router.post("/api/data-products/{catalog}/{schema}/lifecycle/{target_slug}")
async def transition_lifecycle(
    catalog: str,
    schema: str,
    target_slug: str,
    request: Request,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Drive the state machine.  Steward/admin only.

    Targets (URL-friendly): ``promote-to-active``, ``deprecate``,
    ``retire``, ``archive``, ``restore``.  ``retire`` accepts
    ``{"replacement_uri": str, "note"?: str}``; the other targets accept
    ``{"note"?: str}`` only.
    """
    if target_slug not in _TARGET_MAP:
        raise BadRequestError(f"target {target_slug!r} not in {sorted(_TARGET_MAP)}")
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    dp_row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)
    _require_steward_or_admin(user, dp_row)

    target_state = _TARGET_MAP[target_slug]
    note = str(body.get("note") or "").strip()
    replacement_uri_in = str(body.get("replacement_uri") or "").strip() or None
    try:
        replacement_id, canonical_uri = _resolve_replacement(
            factory, workspace_id=workspace_id, replacement_uri=replacement_uri_in
        )
    except BadRequestError, ResourceNotFoundError:
        raise
    if replacement_id is not None and target_state != "retired":
        raise BadRequestError("replacement_uri is only valid for the 'retire' target")
    try:
        updated = lifecycle_service.transition(
            factory,
            data_product_id=dp_row.id,
            target=target_state,
            actor_user_id=int(user["id"]) if user["id"] > 0 else None,
            replacement_data_product_id=replacement_id,
            note=note,
        )
    except LifecycleTransitionError as exc:
        raise BadRequestError(str(exc)) from exc

    detail: dict[str, Any] = {
        "from_state": dp_row.lifecycle_state,
        "to_state": target_state,
    }
    if canonical_uri is not None:
        detail["replacement_uri"] = canonical_uri
    if note:
        detail["note"] = note
    await audit(
        request,
        lifecycle_service.LIFECYCLE_CHANGED_ACTION,
        f"data_product:{catalog}.{schema}",
        detail,
    )
    return {
        "state": updated.lifecycle_state,
        "changed_at": (
            updated.lifecycle_changed_at.isoformat() if updated.lifecycle_changed_at else None
        ),
        "replacement_uri": _successor_uri(
            factory, workspace_id, updated.replacement_data_product_id
        ),
    }
