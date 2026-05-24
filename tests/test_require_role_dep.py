"""Tests for the require_role factory + PrivilegeSettings.

The factory is FastAPI-Depends-compatible and generalises the seven
existing single-role gates into one parametrised form.  These tests
exercise the factory directly (no full FastAPI app) so the contract
is verified in isolation from middleware.
"""

from __future__ import annotations

from typing import Any

import pytest

from pointlessql.api.dependencies import require_role
from pointlessql.exceptions import AuthorizationError
from pointlessql.types import UserInfo


def _make_request(
    *,
    user: UserInfo | None = None,
    api_key_supervisor: bool = False,
    api_key_auditor: bool = False,
    api_key_analyst: bool = False,
) -> Any:
    """Build a minimal stand-in Request with the request.state shape required."""

    class _State:
        pass

    state = _State()
    state.user = user
    state.api_key_supervisor = api_key_supervisor
    state.api_key_auditor = api_key_auditor
    state.api_key_analyst = api_key_analyst

    class _Request:
        pass

    request = _Request()
    request.state = state
    return request


def _user(
    *,
    is_admin: bool = False,
    is_supervisor: bool = False,
    is_auditor: bool = False,
    user_id: int = 1,
    email: str = "u@example.com",
) -> UserInfo:
    return UserInfo(
        id=user_id,
        email=email,
        display_name=email,
        is_admin=is_admin,
        is_supervisor=is_supervisor,
        is_auditor=is_auditor,
    )


# ---------------------------------------------------------------------
# Factory validation
# ---------------------------------------------------------------------


def test_factory_rejects_empty_role_list() -> None:
    with pytest.raises(ValueError, match="at least one role"):
        require_role()


def test_factory_rejects_unknown_role() -> None:
    with pytest.raises(ValueError, match="Unknown role"):
        require_role("admin", "wizard")


def test_factory_accepts_every_recognised_role() -> None:
    require_role("admin")
    require_role("supervisor")
    require_role("auditor")
    require_role("analyst")
    require_role("user")
    require_role("admin", "auditor", "analyst")


# ---------------------------------------------------------------------
# Single-role gates
# ---------------------------------------------------------------------


def test_admin_user_passes_admin_gate() -> None:
    dep = require_role("admin")
    dep(_make_request(user=_user(is_admin=True)))


def test_non_admin_fails_admin_gate() -> None:
    dep = require_role("admin")
    with pytest.raises(AuthorizationError):
        dep(_make_request(user=_user()))


def test_supervisor_user_passes_supervisor_gate() -> None:
    dep = require_role("supervisor")
    dep(_make_request(user=_user(is_supervisor=True)))


def test_api_key_supervisor_passes_supervisor_gate() -> None:
    dep = require_role("supervisor")
    dep(_make_request(user=_user(), api_key_supervisor=True))


def test_auditor_user_passes_auditor_gate() -> None:
    dep = require_role("auditor")
    dep(_make_request(user=_user(is_auditor=True)))


def test_user_role_requires_authenticated_principal() -> None:
    dep = require_role("user")
    dep(_make_request(user=_user(user_id=42)))
    with pytest.raises(AuthorizationError):
        dep(_make_request(user=_user(user_id=0)))


# ---------------------------------------------------------------------
# Admin-strict-stronger semantics
# ---------------------------------------------------------------------


def test_admin_passes_any_role_set() -> None:
    """Admin caller passes even when 'admin' is not in the role set."""
    dep = require_role("auditor", "analyst")
    dep(_make_request(user=_user(is_admin=True)))


# ---------------------------------------------------------------------
# Multi-role OR semantics
# ---------------------------------------------------------------------


def test_supervisor_or_auditor_passes_for_each() -> None:
    dep = require_role("supervisor", "auditor")
    dep(_make_request(user=_user(is_supervisor=True)))
    dep(_make_request(user=_user(is_auditor=True)))


def test_supervisor_or_auditor_fails_for_neither() -> None:
    dep = require_role("supervisor", "auditor")
    with pytest.raises(AuthorizationError):
        dep(_make_request(user=_user()))


def test_analyst_role_promotes_via_auditor_scope() -> None:
    """is_auditor flag promotes the caller into analyst access (Lens covers auditor)."""
    dep = require_role("analyst")
    dep(_make_request(user=_user(is_auditor=True)))


def test_analyst_role_promotes_via_api_key_analyst() -> None:
    dep = require_role("analyst")
    dep(_make_request(user=_user(), api_key_analyst=True))


# ---------------------------------------------------------------------
# PrivilegeSettings scaffold
# ---------------------------------------------------------------------


def test_privilege_settings_default_false() -> None:
    from pointlessql.config import PrivilegeSettings

    settings = PrivilegeSettings()
    assert settings.enforce_global_privilege_gate is False


def test_privilege_settings_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POINTLESSQL_PRIVILEGE_ENFORCE_GLOBAL_PRIVILEGE_GATE", "true")
    from pointlessql.config import PrivilegeSettings

    settings = PrivilegeSettings()
    assert settings.enforce_global_privilege_gate is True


def test_privilege_settings_attached_to_root_settings() -> None:
    """The root Settings instance exposes a ``.privilege`` sub-model."""
    from pointlessql.config import Settings

    settings = Settings()
    assert hasattr(settings, "privilege")
    assert settings.privilege.enforce_global_privilege_gate is False
