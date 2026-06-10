"""Contract tests for the typed principal accessors."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from fastapi import Request

from pointlessql.api.dependencies import get_optional_user, get_user
from pointlessql.types import UserInfo


def _request_with_state(**state: Any) -> Request:
    return cast(Request, SimpleNamespace(state=SimpleNamespace(**state)))


_USER = UserInfo(
    id=7,
    email="someone@example.com",
    display_name="Someone",
    is_admin=False,
    is_supervisor=False,
    is_auditor=False,
)


def test_get_optional_user_returns_none_for_anonymous() -> None:
    assert get_optional_user(_request_with_state()) is None
    assert get_optional_user(_request_with_state(user=None)) is None


def test_get_optional_user_returns_the_middleware_user() -> None:
    assert get_optional_user(_request_with_state(user=_USER)) is _USER


def test_get_user_returns_zero_id_placeholder_for_anonymous() -> None:
    """Pins the None-vs-placeholder contract between the two accessors.

    ``get_user`` must keep handing anonymous callers the zero-id
    placeholder (callers index it unconditionally), while
    ``get_optional_user`` preserves ``None`` for nullable actor
    columns. Changing either silently corrupts audit attribution.
    """
    placeholder = get_user(_request_with_state())
    assert placeholder["id"] == 0
    assert placeholder["email"] == ""
    assert placeholder["is_admin"] is False


def test_get_user_passes_through_the_middleware_user() -> None:
    assert get_user(_request_with_state(user=_USER)) is _USER
