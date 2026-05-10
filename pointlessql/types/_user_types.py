"""Shared type definitions for PointlesSQL."""

from __future__ import annotations

from typing import TypedDict


class UserInfo(TypedDict):
    """Authenticated user metadata flowing through middleware and routes.

    Built by :func:`pointlessql.services.auth.get_current_user` and
    attached to ``request.state.user`` by the auth middleware.

    ``is_supervisor`` and ``is_auditor`` let OIDC group → scope
    mappings flow into ``require_supervisor`` / ``require_auditor``
    for session-cookie callers without requiring a parallel API key.
    """

    id: int
    email: str
    display_name: str
    is_admin: bool
    is_supervisor: bool
    is_auditor: bool
