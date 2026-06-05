"""Mutation-killing tests for the fail-closed Cedar engine wrapper.

The real ``cedarpy.is_authorized`` call is stubbed so the wrapper's
own logic — empty-set short-circuit, effect mapping, error-class
derivation, latency capture, request assembly, the cached policy
composition and cache invalidation — is pinned deterministically.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from pointlessql.services.policy_as_code import _engine
from pointlessql.services.policy_as_code._engine import (
    Decision,
    _compose_policies,
    _serialise_diagnostics,
    cedar_evaluate,
    invalidate_cache,
)


@pytest.fixture(autouse=True)
def _clear_cache() -> Any:
    invalidate_cache()
    yield
    invalidate_cache()


def _module(module_id: int, version: int, source: str) -> Any:
    return SimpleNamespace(id=module_id, version=version, cedar_source=source)


def _result(*, allowed: bool, decision: str, reasons: list[str], errors: list[str]) -> Any:
    return SimpleNamespace(
        allowed=allowed,
        decision=decision,
        diagnostics=SimpleNamespace(reasons=reasons, errors=errors),
    )


# --- empty policy set -----------------------------------------------------


def test_empty_modules_short_circuit_to_empty_forbid() -> None:
    d = cedar_evaluate([], principal='User::"a"', action='Action::"r"', resource='R::"x"')
    assert d == Decision(
        effect="forbid",
        empty=True,
        latency_ms=0,
        diagnostics={"reason": "empty_policy_set"},
        error_class=None,
    )


# --- success path ---------------------------------------------------------


def test_allowed_result_maps_to_permit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _engine.cedarpy,
        "is_authorized",
        lambda **_: _result(allowed=True, decision="Allow", reasons=["policy0"], errors=[]),
    )
    d = cedar_evaluate(
        [_module(1, 1, "permit(principal, action, resource);")],
        principal='User::"a"',
        action='Action::"r"',
        resource='R::"x"',
    )
    assert d.effect == "permit"
    assert d.empty is False
    assert d.error_class is None
    assert d.diagnostics["reasons"] == ["policy0"]
    assert d.latency_ms is not None and d.latency_ms >= 0


def test_denied_result_maps_to_forbid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _engine.cedarpy,
        "is_authorized",
        lambda **_: _result(allowed=False, decision="Deny", reasons=[], errors=[]),
    )
    d = cedar_evaluate([_module(1, 1, "x")], principal="p", action="a", resource="r")
    assert d.effect == "forbid"
    assert d.error_class is None


def test_diagnostics_errors_set_parse_error_class(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _engine.cedarpy,
        "is_authorized",
        lambda **_: _result(allowed=False, decision="Deny", reasons=[], errors=["boom"]),
    )
    d = cedar_evaluate([_module(1, 1, "x")], principal="p", action="a", resource="r")
    assert d.error_class == "cedar_parse_error"
    assert d.diagnostics["errors"] == ["boom"]


def test_nodecision_without_allow_sets_runtime_error_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        _engine.cedarpy,
        "is_authorized",
        lambda **_: _result(allowed=False, decision="NoDecision", reasons=[], errors=[]),
    )
    d = cedar_evaluate([_module(1, 1, "x")], principal="p", action="a", resource="r")
    assert d.error_class == "cedar_runtime_error"


def test_request_is_assembled_and_entities_defaulted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _spy(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return _result(allowed=True, decision="Allow", reasons=[], errors=[])

    monkeypatch.setattr(_engine.cedarpy, "is_authorized", _spy)
    cedar_evaluate(
        [_module(1, 1, "permit(principal, action, resource);")],
        principal='User::"a"',
        action='Action::"read"',
        resource='DP::"x"',
        context={"mfa": True},
    )
    assert captured["request"] == {
        "principal": 'User::"a"',
        "action": 'Action::"read"',
        "resource": 'DP::"x"',
        "context": {"mfa": True},
    }
    assert captured["entities"] == []  # None -> [] default
    assert captured["policies"] == "permit(principal, action, resource);"


def test_context_none_becomes_empty_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        _engine.cedarpy,
        "is_authorized",
        lambda **kw: (
            captured.update(kw),
            _result(allowed=True, decision="Allow", reasons=[], errors=[]),
        )[1],
    )
    cedar_evaluate([_module(1, 1, "x")], principal="p", action="a", resource="r")
    assert captured["request"]["context"] == {}


# --- failure path ---------------------------------------------------------


def test_cedar_exception_collapses_to_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(**_: Any) -> Any:
        raise RuntimeError("engine exploded")

    monkeypatch.setattr(_engine.cedarpy, "is_authorized", _boom)
    d = cedar_evaluate([_module(1, 1, "x")], principal="p", action="a", resource="r")
    assert d.effect == "forbid"
    assert d.empty is False
    assert d.error_class == "cedar_runtime_error"
    assert "engine exploded" in d.diagnostics["message"]
    # Latency is a small forward delta, not the absolute monotonic clock.
    assert d.latency_ms is not None and 0 <= d.latency_ms < 1000


def test_compose_failure_is_parse_error_fail_closed() -> None:
    # A non-int version makes _compose_policies raise ValueError, which
    # collapses to the parse-error branch (no engine call).
    d = cedar_evaluate(
        [_module(1, "not-an-int", "x")],  # type: ignore[arg-type]
        principal="p",
        action="a",
        resource="r",
    )
    assert d == Decision(
        effect="forbid",
        empty=False,
        latency_ms=None,
        diagnostics={"reason": "compose_failed", "message": d.diagnostics["message"]},
        error_class="cedar_parse_error",
    )
    assert "int" in d.diagnostics["message"].lower()


def test_result_without_allowed_attr_defaults_to_forbid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Missing 'allowed' -> getattr default False -> forbid (a True
    # default mutant would flip this to permit).
    monkeypatch.setattr(
        _engine.cedarpy,
        "is_authorized",
        lambda **_: SimpleNamespace(
            decision="Allow", diagnostics=SimpleNamespace(reasons=[], errors=[])
        ),
    )
    d = cedar_evaluate([_module(1, 1, "x")], principal="p", action="a", resource="r")
    assert d.effect == "forbid"


def test_successful_eval_latency_is_small(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _engine.cedarpy,
        "is_authorized",
        lambda **_: _result(allowed=True, decision="Allow", reasons=[], errors=[]),
    )
    d = cedar_evaluate([_module(1, 1, "x")], principal="p", action="a", resource="r")
    assert d.latency_ms is not None and 0 <= d.latency_ms < 1000


# --- _serialise_diagnostics -----------------------------------------------


def test_serialise_diagnostics_full() -> None:
    result = _result(allowed=True, decision="Allow", reasons=["p0", "p1"], errors=["e0"])
    out = _serialise_diagnostics(result)
    assert out == {"decision": "Allow", "reasons": ["p0", "p1"], "errors": ["e0"]}


def test_serialise_diagnostics_missing_returns_empty() -> None:
    assert _serialise_diagnostics(SimpleNamespace(diagnostics=None)) == {}


def test_serialise_diagnostics_tolerates_absent_reason_lists() -> None:
    # diag without reasons/errors attributes must fall back to empty
    # lists, not raise (guards the getattr defaults).
    result = SimpleNamespace(diagnostics=SimpleNamespace(), decision="Allow")
    assert _serialise_diagnostics(result) == {
        "decision": "Allow",
        "reasons": [],
        "errors": [],
    }


# --- _compose_policies + cache --------------------------------------------


def test_compose_joins_with_blank_line() -> None:
    composed = _compose_policies([_module(1, 1, "A"), _module(2, 1, "B")])
    assert composed == "A\n\nB"


def test_compose_strips_each_module_source() -> None:
    assert _compose_policies([_module(1, 1, "  A  ")]) == "A"


def test_compose_caches_by_id_and_version() -> None:
    _compose_policies([_module(7, 1, "ORIGINAL")])
    # Same (id, version) -> served from cache, ignores the new source.
    assert _compose_policies([_module(7, 1, "CHANGED")]) == "ORIGINAL"
    # A version bump busts the cache.
    assert _compose_policies([_module(7, 2, "CHANGED")]) == "CHANGED"


def test_invalidate_cache_scoped_to_module() -> None:
    _compose_policies([_module(10, 1, "TEN"), _module(20, 1, "TWENTY")])
    invalidate_cache(10)
    # 10 re-reads the fresh source; 20 still cached.
    assert _compose_policies([_module(10, 1, "TEN_NEW")]) == "TEN_NEW"
    assert _compose_policies([_module(20, 1, "TWENTY_NEW")]) == "TWENTY"


def test_invalidate_cache_all() -> None:
    _compose_policies([_module(30, 1, "THIRTY")])
    invalidate_cache()
    assert _compose_policies([_module(30, 1, "THIRTY_NEW")]) == "THIRTY_NEW"
