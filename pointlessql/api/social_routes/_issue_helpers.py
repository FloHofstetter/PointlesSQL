"""Shared helpers for the Phase-77.7 Issues router.

Split out from :mod:`pointlessql.api.social_routes.issues` so the
issue-route surface stays under the file-size budget.  Pure
helpers, no router state — everything here is reachable from the
issue routes via plain function calls.
"""

from __future__ import annotations

import json
from typing import Any, cast

from sqlalchemy import select

from pointlessql.api.social_routes._kind_dispatch import (
    parse_dp_ref,
    parse_ref,
)
from pointlessql.exceptions import BadRequestError, ResourceNotFoundError
from pointlessql.models.auth import User
from pointlessql.models.social._issue import Issue
from pointlessql.models.social._social_target import SocialTarget
from pointlessql.services.social._target_resolver import (
    get_or_create_target,
    resolve_dp_target,
)
from pointlessql.services.social.entity_registry import get as registry_get

_MAX_LABELS = 20


def ensure_parent_supports_issues(kind: str) -> None:
    """Raise 404 when the parent kind has ``supports_issues=False``."""
    spec = registry_get(kind)
    if not spec.supports_issues:
        raise ResourceNotFoundError(f"kind={kind!r} does not support issues.")


def resolve_parent_target_id(
    session: Any,
    workspace_id: int,
    kind: str,
    ref: str,
) -> int:
    """Return the parent's ``social_targets.id`` for an issue create.

    Args:
        session: Active SQLAlchemy session.
        workspace_id: Tenant scope for both the parent + the issue.
        kind: Parent entity kind discriminator.
        ref: Parent entity reference.

    Returns:
        The parent's ``social_targets.id``.  Created on demand for
        non-DP kinds; looked up via ``resolve_dp_target`` for
        ``kind='dp'`` so the back-pointer is populated.

    Raises:
        ResourceNotFoundError: When ``kind='dp'`` and the DP row is
            missing in the workspace.
    """
    if kind == "dp":
        try:
            target = resolve_dp_target(
                session,
                workspace_id=workspace_id,
                catalog_name=ref.split(".", 1)[0],
                schema_name=ref.split(".", 1)[1],
            )
        except LookupError as exc:
            raise ResourceNotFoundError(str(exc)) from exc
    else:
        target = get_or_create_target(
            session,
            workspace_id=workspace_id,
            kind=kind,
            ref=ref,
        )
    return int(target.id)


def normalise_parent_ref(kind: str, ref: str) -> str:
    """Validate the parent ``(kind, ref)`` pair and return the canonical ref."""
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return f"{catalog}.{schema}"
    return parse_ref(kind, ref)


def validate_labels(raw: Any) -> str:
    """Coerce a labels-input value into a JSON string of slugs.

    Args:
        raw: Either a Python list of strings, or a JSON-encoded
            string already.  Anything else triggers a 400.

    Returns:
        Canonical JSON-encoded list of label slugs.

    Raises:
        BadRequestError: On malformed input or > :data:`_MAX_LABELS`.
    """
    if raw is None:
        return "[]"
    parsed: Any
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BadRequestError(f"labels not JSON: {exc}") from exc
    else:
        parsed = raw
    if not isinstance(parsed, list):
        raise BadRequestError("labels must be a JSON array of strings")
    parsed_list = cast(list[Any], parsed)
    if len(parsed_list) > _MAX_LABELS:
        raise BadRequestError(f"too many labels (max {_MAX_LABELS})")
    cleaned: list[str] = []
    for item in parsed_list:
        if not isinstance(item, str) or not item:
            raise BadRequestError("every label must be a non-empty string slug")
        cleaned.append(item)
    return json.dumps(cleaned)


def serialise_issue(
    issue: Issue,
    *,
    parent_kind: str | None = None,
    parent_ref: str | None = None,
    assignee_email: str | None = None,
    opener_email: str | None = None,
) -> dict[str, Any]:
    """Render one issue row as a JSON-friendly dict."""
    return {
        "id": issue.id,
        "social_target_id": issue.social_target_id,
        "parent_social_target_id": issue.parent_social_target_id,
        "parent_kind": parent_kind,
        "parent_ref": parent_ref,
        "title": issue.title,
        "body_md": issue.body_md,
        "state": issue.state,
        "assignee": {
            "user_id": issue.assignee_user_id,
            "email": assignee_email,
        }
        if issue.assignee_user_id is not None
        else None,
        "opened_by": {
            "user_id": issue.opened_by_user_id,
            "email": opener_email,
        },
        "opened_at": issue.opened_at.isoformat(),
        "closed_at": issue.closed_at.isoformat()
        if issue.closed_at
        else None,
        "closed_reason": issue.closed_reason,
        "milestone_id": issue.milestone_id,
        "labels": json.loads(issue.labels_json or "[]"),
    }


def hydrate_parent(
    session: Any, parent_social_target_id: int
) -> tuple[str | None, str | None]:
    """Look up ``(parent_kind, parent_ref)`` for a parent social_target id."""
    row = session.execute(
        select(SocialTarget.entity_kind, SocialTarget.entity_ref).where(
            SocialTarget.id == parent_social_target_id
        )
    ).first()
    if row is None:
        return None, None
    return str(row[0]), str(row[1])


def hydrate_emails(
    session: Any, user_ids: list[int]
) -> dict[int, str]:
    """Bulk-resolve user ids to email strings."""
    if not user_ids:
        return {}
    rows = session.execute(
        select(User.id, User.email).where(User.id.in_(user_ids))
    ).all()
    return {int(uid): str(email) for uid, email in rows}


def can_edit_issue(user: Any, issue: Issue) -> bool:
    """Return whether *user* may PATCH *issue*.

    Opener + admin only.  Mirrors GitHub's perms.
    """
    if user.get("is_admin"):
        return True
    return int(user.get("id") or 0) == int(issue.opened_by_user_id)


__all__: list[str] = [
    "can_edit_issue",
    "ensure_parent_supports_issues",
    "hydrate_emails",
    "hydrate_parent",
    "normalise_parent_ref",
    "resolve_parent_target_id",
    "serialise_issue",
    "validate_labels",
]
