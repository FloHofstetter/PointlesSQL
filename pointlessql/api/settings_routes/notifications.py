"""``/api/settings/notifications`` — per-event-type prefs.

Two endpoints:

* ``GET`` — current ``notification_prefs_json`` + list of known
  event types so the UI can render a complete grid.
* ``PUT`` — merge-update of the prefs dict.  Unknown keys are
  silently accepted (forward-compatible for future event types
  before the canonical list catches up).

Missing keys + missing event_type entries default to all-true
both server-side (in ``fanout._opted_in_inbox``) and in the
``/settings/notifications`` UI.
"""

from __future__ import annotations

import json
from typing import Any, cast

from fastapi import APIRouter, Request

from pointlessql.api.dependencies import get_user, require_user
from pointlessql.exceptions import BadRequestError, ResourceNotFoundError
from pointlessql.models.auth import User
from pointlessql.services.workspace.governance import GOVERNANCE_EVENT_TYPES

router = APIRouter(tags=["settings"])

# Subset of GOVERNANCE_EVENT_TYPES that is user-facing — every type
# the per-user inbox fan-out could realistically fire.  Trims out
# the system-emitted ones (audit-export-issued, lineage-pruned,
# branch lifecycle) which never reach the inbox today.
USER_FACING_EVENT_TYPES: tuple[str, ...] = tuple(
    et
    for et in GOVERNANCE_EVENT_TYPES
    if et.startswith("pointlessql.data_product.")
    or et.startswith("pointlessql.user.")
    or et.startswith("pointlessql.topic.")
    or et == "pointlessql.notification.digest"
)


@router.get("/api/settings/notifications")
async def get_notification_prefs(request: Request) -> dict[str, Any]:
    """Return the caller's prefs + the canonical event-type list.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"prefs": {event_type: {inbox, email, webhook}},
        "known_event_types": [...]}``.  Missing keys + missing
        sub-keys are filled in as ``True``.
    """
    require_user(request)
    caller = get_user(request)
    factory = request.app.state.session_factory
    raw_prefs: dict[str, Any]
    with factory() as session:
        user = session.get(User, caller["id"])
        prefs_text = user.notification_prefs_json if user else "{}"
    try:
        raw_value: Any = json.loads(prefs_text or "{}")
    except ValueError, TypeError:
        raw_value = {}
    if not isinstance(raw_value, dict):
        raw_value = {}
    raw_prefs: dict[str, Any] = raw_value  # pyright: ignore[reportUnknownVariableType]

    filled: dict[str, dict[str, bool]] = {}
    for event_type in USER_FACING_EVENT_TYPES:
        per_value: Any = raw_prefs.get(event_type, {})  # pyright: ignore[reportUnknownMemberType]
        per: dict[str, Any] = per_value if isinstance(per_value, dict) else {}  # pyright: ignore[reportUnknownVariableType]
        filled[event_type] = {
            "inbox": bool(per.get("inbox", True)),  # pyright: ignore[reportUnknownArgumentType]
            "email": bool(per.get("email", True)),  # pyright: ignore[reportUnknownArgumentType]
            "webhook": bool(per.get("webhook", True)),  # pyright: ignore[reportUnknownArgumentType]
        }
    return {"prefs": filled, "known_event_types": list(USER_FACING_EVENT_TYPES)}


@router.put("/api/settings/notifications")
async def update_notification_prefs(request: Request) -> dict[str, Any]:
    """Merge-update the caller's notification prefs.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The full updated prefs payload (same shape as ``GET``).

    Raises:
        BadRequestError: 400 when the body is not a JSON object.
        ResourceNotFoundError: 404 when the caller's user row no
            longer exists.
    """
    require_user(request)
    caller = get_user(request)
    body: Any = await request.json()
    if not isinstance(body, dict):
        raise BadRequestError("body must be a JSON object")

    factory = request.app.state.session_factory
    with factory() as session:
        user = session.get(User, caller["id"])
        if user is None:
            raise ResourceNotFoundError("user not found.")
        try:
            current_any: Any = json.loads(user.notification_prefs_json or "{}")
        except ValueError, TypeError:
            current_any = {}
        current: dict[str, Any] = (
            cast(dict[str, Any], current_any) if isinstance(current_any, dict) else {}
        )
        body_dict = cast(dict[str, Any], body)
        for event_key_raw, incoming in body_dict.items():
            event_key = str(event_key_raw)
            if not isinstance(incoming, dict):
                continue
            incoming_typed = cast(dict[str, Any], incoming)
            existing_any: Any = current.get(event_key, {})
            existing: dict[str, Any] = (
                cast(dict[str, Any], existing_any) if isinstance(existing_any, dict) else {}
            )
            for channel in ("inbox", "email", "webhook"):
                if channel in incoming_typed:
                    existing[channel] = bool(incoming_typed[channel])
            current[event_key] = existing
        user.notification_prefs_json = json.dumps(current)
        session.commit()

    return await get_notification_prefs(request)
