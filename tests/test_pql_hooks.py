"""PQL-layer hook registry (B6)."""

from __future__ import annotations

import pytest

from pointlessql.pql import _hooks


def test_register_and_run_before_read_chain() -> None:
    with _hooks.HookContext():
        calls: list[dict] = []

        def hook(ctx: dict) -> None:
            calls.append(ctx)

        _hooks.register_before_read(hook)
        _hooks.run_before_read({"full_name": "a.b.c"})
        assert calls == [{"full_name": "a.b.c"}]


def test_before_read_hook_raise_propagates() -> None:
    with _hooks.HookContext():
        def hook(ctx: dict) -> None:
            raise PermissionError("blocked")

        _hooks.register_before_read(hook)
        with pytest.raises(PermissionError):
            _hooks.run_before_read({})


def test_after_read_hook_can_replace_frame() -> None:
    with _hooks.HookContext():
        def mask(frame, ctx):
            return frame + "_masked"

        _hooks.register_after_read(mask)
        result = _hooks.run_after_read("raw", {})
        assert result == "raw_masked"


def test_after_read_hook_returning_none_keeps_frame() -> None:
    with _hooks.HookContext():
        def noop(frame, ctx):
            return None

        _hooks.register_after_read(noop)
        result = _hooks.run_after_read("raw", {})
        assert result == "raw"


def test_before_write_hook_can_replace_frame() -> None:
    with _hooks.HookContext():
        def stamp(frame, ctx):
            return f"{frame}+stamped"

        _hooks.register_before_write(stamp)
        result = _hooks.run_before_write("payload", {})
        assert result == "payload+stamped"


def test_after_write_runs_with_context() -> None:
    with _hooks.HookContext():
        calls: list[dict] = []

        def tag(ctx: dict) -> None:
            calls.append(ctx)

        _hooks.register_after_write(tag)
        _hooks.run_after_write({"rows": 5})
        assert calls == [{"rows": 5}]


def test_hook_context_isolation() -> None:
    baseline = _hooks.registered_counts()
    with _hooks.HookContext():
        _hooks.register_before_read(lambda ctx: None)
        assert _hooks.registered_counts()["before_read"] >= 1
    assert _hooks.registered_counts() == baseline


def test_hooks_run_in_registration_order() -> None:
    with _hooks.HookContext():
        order: list[int] = []

        def a(frame, ctx):
            order.append(1)
            return frame

        def b(frame, ctx):
            order.append(2)
            return frame

        _hooks.register_after_read(a)
        _hooks.register_after_read(b)
        _hooks.run_after_read("frame", {})
        assert order == [1, 2]


def test_registered_counts_returns_per_phase() -> None:
    with _hooks.HookContext():
        _hooks.register_before_read(lambda ctx: None)
        _hooks.register_after_write(lambda ctx: None)
        counts = _hooks.registered_counts()
        assert counts == {
            "before_read": 1,
            "after_read": 0,
            "before_write": 0,
            "after_write": 1,
        }
