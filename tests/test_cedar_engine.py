"""Cedar engine basics — parse, evaluate, cache, fail-closed (Phase 141)."""

from __future__ import annotations

import datetime

from pointlessql.api.main import app
from pointlessql.models import PolicyModule
from pointlessql.services.policy_as_code._engine import (
    cedar_evaluate,
    invalidate_cache,
)


def _factory():
    return app.state.session_factory


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _module(name: str, source: str) -> PolicyModule:
    return PolicyModule(
        id=1,
        workspace_id=1,
        name=name,
        cedar_source=source,
        version=1,
        enabled=True,
        created_by_user_id=None,
        created_at=_now(),
        updated_at=_now(),
    )


def test_empty_module_list_returns_empty_decision() -> None:
    invalidate_cache()
    decision = cedar_evaluate(
        [],
        principal='User::"1"',
        action='Action::"read"',
        resource='DataProduct::"main.silver"',
    )
    assert decision.effect == "forbid"
    assert decision.empty is True
    assert decision.error_class is None


def test_permit_policy_allows_request() -> None:
    invalidate_cache()
    module = _module(
        "allow_alice_read",
        'permit(principal == User::"1", action == Action::"read", resource);',
    )
    decision = cedar_evaluate(
        [module],
        principal='User::"1"',
        action='Action::"read"',
        resource='DataProduct::"main.silver"',
    )
    assert decision.effect == "permit"
    assert decision.empty is False
    assert decision.error_class is None


def test_unmatched_principal_falls_back_to_forbid() -> None:
    invalidate_cache()
    module = _module(
        "only_alice",
        'permit(principal == User::"1", action == Action::"read", resource);',
    )
    decision = cedar_evaluate(
        [module],
        principal='User::"2"',
        action='Action::"read"',
        resource='DataProduct::"main.silver"',
    )
    assert decision.effect == "forbid"
    assert decision.error_class is None


def test_explicit_forbid_overrides_permit() -> None:
    invalidate_cache()
    permit = _module(
        "broad_permit",
        "permit(principal, action, resource);",
    )
    forbid = _module(
        "lock_silver",
        'forbid(principal, action, resource == DataProduct::"main.silver");',
    )
    forbid.id = 2
    decision = cedar_evaluate(
        [permit, forbid],
        principal='User::"1"',
        action='Action::"read"',
        resource='DataProduct::"main.silver"',
    )
    assert decision.effect == "forbid"


def test_parse_error_fails_closed_with_error_class() -> None:
    invalidate_cache()
    broken = _module("broken", "this is not cedar source")
    decision = cedar_evaluate(
        [broken],
        principal='User::"1"',
        action='Action::"read"',
        resource='DataProduct::"main.silver"',
    )
    assert decision.effect == "forbid"
    assert decision.error_class == "cedar_parse_error"


def test_cache_keys_on_version_bump() -> None:
    invalidate_cache()
    module = _module(
        "cache_test",
        'permit(principal, action == Action::"read", resource);',
    )
    cedar_evaluate(
        [module],
        principal='User::"1"',
        action='Action::"read"',
        resource='DataProduct::"x.y"',
    )
    bumped = _module(
        "cache_test",
        'permit(principal, action == Action::"write", resource);',
    )
    bumped.version = 2
    decision = cedar_evaluate(
        [bumped],
        principal='User::"1"',
        action='Action::"write"',
        resource='DataProduct::"x.y"',
    )
    assert decision.effect == "permit"


def test_action_mismatch_falls_back_to_forbid() -> None:
    invalidate_cache()
    module = _module(
        "read_only",
        'permit(principal, action == Action::"read", resource);',
    )
    decision = cedar_evaluate(
        [module],
        principal='User::"1"',
        action='Action::"write"',
        resource='DataProduct::"main.silver"',
    )
    assert decision.effect == "forbid"


def test_invalidate_cache_per_module() -> None:
    invalidate_cache()
    one = _module("one", "permit(principal, action, resource);")
    two = _module("two", "permit(principal, action, resource);")
    two.id = 2
    cedar_evaluate(
        [one, two],
        principal='User::"1"',
        action='Action::"read"',
        resource='DataProduct::"x.y"',
    )
    invalidate_cache(1)
    decision = cedar_evaluate(
        [one, two],
        principal='User::"1"',
        action='Action::"read"',
        resource='DataProduct::"x.y"',
    )
    assert decision.effect == "permit"
