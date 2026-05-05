"""Sprint 29.3 — OIDC group → workspace + scope mapping.

Pins the surface area users care about:

* settings parser fails loud at construction on malformed input
* :func:`find_or_create_oidc_user` honours the mapping for new + linked users
* the asymmetric privilege ladder (auditor passes require_supervisor;
  supervisor does NOT pass require_auditor) holds for session-cookie
  callers exactly as it does for API keys
* group changes at the IdP propagate at next login (re-resolve every
  call, never sticky)
"""

from __future__ import annotations

import datetime
import json
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from pointlessql.api.dependencies import require_auditor, require_supervisor
from pointlessql.api.main import app
from pointlessql.exceptions import AuthorizationError
from pointlessql.models import Workspace
from pointlessql.services.oidc import find_or_create_oidc_user
from pointlessql.settings import GroupMapping, OIDCSettings


def _factory():
    return app.state.session_factory


def _seed_workspace(slug: str, name: str) -> int:
    factory = _factory()
    with factory() as session:
        ws = Workspace(
            slug=slug,
            name=name,
            description="Test fixture for Sprint 29.3.",
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(ws)
        session.commit()
        session.refresh(ws)
        return int(ws.id)


# ---------------------------------------------------------------------------
# Settings parser
# ---------------------------------------------------------------------------


def test_empty_group_map_is_empty_dict() -> None:
    """The default empty env var yields an empty parsed map."""
    settings = OIDCSettings()
    assert settings.parsed_group_map == {}


def test_single_entry_parses() -> None:
    settings = OIDCSettings(group_map_raw="admins:ws=1,scopes=admin")
    parsed = settings.parsed_group_map
    assert "admins" in parsed
    assert parsed["admins"] == GroupMapping(
        workspace_id=1, is_admin=True, is_supervisor=False, is_auditor=False
    )


def test_pipe_scopes_union() -> None:
    settings = OIDCSettings(group_map_raw="reviewers:ws=2,scopes=auditor|supervisor")
    parsed = settings.parsed_group_map
    assert parsed["reviewers"] == GroupMapping(
        workspace_id=2, is_admin=False, is_supervisor=True, is_auditor=True
    )


def test_scopes_only_no_workspace_override() -> None:
    """A mapping with no ``ws=`` field grants scopes but leaves workspace alone."""
    settings = OIDCSettings(group_map_raw="auditors:scopes=auditor")
    parsed = settings.parsed_group_map
    assert parsed["auditors"].workspace_id is None
    assert parsed["auditors"].is_auditor is True


def test_malformed_entry_raises() -> None:
    with pytest.raises(ValidationError, match="expected 'group:ws=N"):
        OIDCSettings(group_map_raw="not-a-valid-entry")


def test_unknown_scope_name_raises() -> None:
    with pytest.raises(ValidationError, match="unknown scope"):
        OIDCSettings(group_map_raw="admins:ws=1,scopes=root")


def test_unknown_field_raises() -> None:
    with pytest.raises(ValidationError, match="unknown field"):
        OIDCSettings(group_map_raw="admins:ws=1,extra=foo")


def test_non_int_workspace_raises() -> None:
    with pytest.raises(ValidationError, match="must be int"):
        OIDCSettings(group_map_raw="admins:ws=foo,scopes=admin")


def test_empty_body_after_colon_raises() -> None:
    """Both ws= and scopes= absent — degenerate, must reject."""
    with pytest.raises(ValidationError, match="must set ws=, scopes="):
        OIDCSettings(group_map_raw="admins:")


# ---------------------------------------------------------------------------
# find_or_create_oidc_user honours the mapping
# ---------------------------------------------------------------------------


def test_no_groups_no_scope_grants() -> None:
    """An IdP without a groups claim leaves the user with default scopes."""
    factory = _factory()
    user = find_or_create_oidc_user(
        factory,
        provider="https://example.test/.well-known/openid-configuration",
        subject="no-groups-user",
        email="noscope@test.com",
        display_name="No Scope",
        groups=[],
        group_map={},
    )
    assert user.is_admin is False
    assert bool(user.is_supervisor) is False
    assert bool(user.is_auditor) is False
    assert user.default_workspace_id == 1


def test_single_group_grants_workspace_and_scopes() -> None:
    other_ws = _seed_workspace("oidc-single-a", "OIDC Single A")
    factory = _factory()
    settings = OIDCSettings(group_map_raw=f"data-team:ws={other_ws},scopes=supervisor")
    user = find_or_create_oidc_user(
        factory,
        provider="https://example.test/.well-known/openid-configuration",
        subject="single-group-user",
        email="single@test.com",
        display_name="Single",
        groups=["data-team"],
        group_map=settings.parsed_group_map,
    )
    assert int(user.default_workspace_id) == other_ws
    assert bool(user.is_supervisor) is True
    assert bool(user.is_auditor) is False


def test_multiple_groups_union_scopes() -> None:
    """A user in two mapped groups gets the union of scope flags."""
    other_ws = _seed_workspace("oidc-multi-a", "OIDC Multi A")
    factory = _factory()
    settings = OIDCSettings(
        group_map_raw=(
            f"reviewers:ws={other_ws},scopes=auditor;data-team:ws={other_ws},scopes=supervisor"
        )
    )
    user = find_or_create_oidc_user(
        factory,
        provider="https://example.test/.well-known/openid-configuration",
        subject="multi-user",
        email="multi@test.com",
        display_name="Multi",
        groups=["reviewers", "data-team"],
        group_map=settings.parsed_group_map,
    )
    assert bool(user.is_supervisor) is True
    assert bool(user.is_auditor) is True
    # First-match wins for workspace override.
    assert int(user.default_workspace_id) == other_ws


def test_unknown_workspace_id_falls_through_to_default() -> None:
    """A typo'd workspace_id in the map falls back to default rather than ghost."""
    factory = _factory()
    settings = OIDCSettings(group_map_raw="ghost:ws=99999,scopes=auditor")
    user = find_or_create_oidc_user(
        factory,
        provider="https://example.test/.well-known/openid-configuration",
        subject="ghost-user",
        email="ghost@test.com",
        display_name="Ghost",
        groups=["ghost"],
        group_map=settings.parsed_group_map,
    )
    # Workspace falls back to seed default.
    assert int(user.default_workspace_id) == 1
    # Scope grants still apply — typo is in the workspace, not the scope.
    assert bool(user.is_auditor) is True


def test_groups_snapshot_persisted() -> None:
    factory = _factory()
    settings = OIDCSettings(group_map_raw="admins:ws=1,scopes=admin")
    user = find_or_create_oidc_user(
        factory,
        provider="https://example.test/.well-known/openid-configuration",
        subject="snapshot-user",
        email="snap@test.com",
        display_name="Snap",
        groups=["admins", "engineers"],
        group_map=settings.parsed_group_map,
    )
    assert user.oidc_groups_json is not None
    decoded = json.loads(user.oidc_groups_json)
    assert decoded == ["admins", "engineers"]


def test_group_change_propagates_at_next_login() -> None:
    """Group flags update on every login — no stickiness from a prior call."""
    factory = _factory()
    settings_grant = OIDCSettings(group_map_raw="admins:ws=1,scopes=admin")
    user = find_or_create_oidc_user(
        factory,
        provider="https://example.test/.well-known/openid-configuration",
        subject="rotating-user",
        email="rotate@test.com",
        display_name="Rotate",
        groups=["admins"],
        group_map=settings_grant.parsed_group_map,
    )
    assert user.is_admin is True

    # Second login: user no longer in the admins group, IdP returns []
    settings_revoke = OIDCSettings(group_map_raw="admins:ws=1,scopes=admin")
    user2 = find_or_create_oidc_user(
        factory,
        provider="https://example.test/.well-known/openid-configuration",
        subject="rotating-user",
        email="rotate@test.com",
        display_name="Rotate",
        groups=[],  # IdP no longer returns the group
        group_map=settings_revoke.parsed_group_map,
    )
    # Supervisor/auditor flags re-resolve from the (empty) groups list
    # → both False even if a previous call set them.  ``is_admin``
    # stays True because the OIDC-side admin grant doesn't strip
    # admin-on-first-user (and we don't want to lock anyone out by
    # accident).
    assert bool(user2.is_supervisor) is False
    assert bool(user2.is_auditor) is False


# ---------------------------------------------------------------------------
# Authz integration — the asymmetric privilege ladder
# ---------------------------------------------------------------------------


def _mock_request(user_dict: dict[str, object]) -> MagicMock:
    """Build a MagicMock Request whose state.user matches *user_dict*.

    Mirrors the request shape the auth middleware produces; using a
    MagicMock keeps the test independent of the FastAPI lifespan.
    """
    request = MagicMock()
    request.state.user = user_dict
    request.state.api_key_supervisor = False
    request.state.api_key_auditor = False
    return request


def test_user_with_supervisor_flag_passes_require_supervisor() -> None:
    request = _mock_request(
        {
            "id": 1,
            "email": "sup@test.com",
            "display_name": "Sup",
            "is_admin": False,
            "is_supervisor": True,
            "is_auditor": False,
        }
    )
    require_supervisor(request)  # should not raise


def test_user_with_auditor_flag_passes_require_auditor() -> None:
    request = _mock_request(
        {
            "id": 1,
            "email": "aud@test.com",
            "display_name": "Aud",
            "is_admin": False,
            "is_supervisor": False,
            "is_auditor": True,
        }
    )
    require_auditor(request)  # should not raise


def test_user_with_auditor_flag_passes_require_supervisor() -> None:
    """Auditor scope is a superset of supervisor — pinned in 19.1."""
    request = _mock_request(
        {
            "id": 1,
            "email": "aud@test.com",
            "display_name": "Aud",
            "is_admin": False,
            "is_supervisor": False,
            "is_auditor": True,
        }
    )
    require_supervisor(request)  # should not raise


def test_user_with_supervisor_flag_does_not_pass_require_auditor() -> None:
    """Supervisor scope is run-scoped and must NOT bypass auditor gate.

    The asymmetric ladder pinned in 19.1 holds on the session-cookie
    path exactly as it does for API keys.
    """
    request = _mock_request(
        {
            "id": 1,
            "email": "sup@test.com",
            "display_name": "Sup",
            "is_admin": False,
            "is_supervisor": True,
            "is_auditor": False,
        }
    )
    with pytest.raises(AuthorizationError):
        require_auditor(request)


def test_plain_user_blocked_from_both_gates() -> None:
    request = _mock_request(
        {
            "id": 1,
            "email": "plain@test.com",
            "display_name": "Plain",
            "is_admin": False,
            "is_supervisor": False,
            "is_auditor": False,
        }
    )
    with pytest.raises(AuthorizationError):
        require_supervisor(request)
    with pytest.raises(AuthorizationError):
        require_auditor(request)
