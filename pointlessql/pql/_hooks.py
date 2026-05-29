"""PQL-layer policy-hook registry (B6).

Central registry for the pre/post hooks every PQL read/write must
trigger.  Consolidates the policies that historically lived at the
HTTP-route rim so notebook / script / agent callers can never
bypass them.

Hooks are stored as plain function lists; callers add their handlers
once at boot via :func:`register_before_read` / similar.  Each PQL
primitive invokes the matching list in registration order; a hook
that raises propagates and aborts the operation.

Order matters — typical wiring (boot-time):

1. ``before_read``  → consumption-enforcement, quota-check (146),
   policy-as-code evaluation (141).
2. ``after_read``   → PII masking, audit-emit.
3. ``before_write`` → bitemporal-validate, ISO-8601-validate (136),
   schema-versioning compatibility check (144),
   policy-as-code evaluation.
4. ``after_write``  → retention-tag, lineage-record, audit-emit.

The registry is *additive only*: there is no remove path on purpose —
remove-hook calls would let stray test fixtures detach a production
policy.  Tests that need a clean slate use the
:func:`HookContext` helper, which snapshots + restores the lists.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator
from typing import Any

#: Callback signature for hooks that run before a read.
#: ``ctx`` carries: ``full_name``, ``principal``, ``authoring_product_id``.
BeforeReadHook = Callable[[dict[str, Any]], None]
#: Callback signature for after-read hooks.  ``frame`` may be mutated
#: in place; a hook that returns a new frame replaces it.
AfterReadHook = Callable[[Any, dict[str, Any]], Any]
#: Callback signature for hooks that run before a write.
BeforeWriteHook = Callable[[Any, dict[str, Any]], Any]
#: Callback signature for after-write hooks.
AfterWriteHook = Callable[[dict[str, Any]], None]


_before_read: list[BeforeReadHook] = []
_after_read: list[AfterReadHook] = []
_before_write: list[BeforeWriteHook] = []
_after_write: list[AfterWriteHook] = []


def register_before_read(hook: BeforeReadHook) -> None:
    """Append *hook* to the before-read chain."""
    _before_read.append(hook)


def register_after_read(hook: AfterReadHook) -> None:
    """Append *hook* to the after-read chain."""
    _after_read.append(hook)


def register_before_write(hook: BeforeWriteHook) -> None:
    """Append *hook* to the before-write chain."""
    _before_write.append(hook)


def register_after_write(hook: AfterWriteHook) -> None:
    """Append *hook* to the after-write chain."""
    _after_write.append(hook)


def run_before_read(context: dict[str, Any]) -> None:
    """Run every before-read hook with *context*.  Hooks may raise."""
    for hook in list(_before_read):
        hook(context)


def run_after_read(frame: Any, context: dict[str, Any]) -> Any:
    """Run every after-read hook; returns the (possibly replaced) frame."""
    current = frame
    for hook in list(_after_read):
        result = hook(current, context)
        if result is not None:
            current = result
    return current


def run_before_write(frame: Any, context: dict[str, Any]) -> Any:
    """Run every before-write hook; returns the (possibly replaced) frame."""
    current = frame
    for hook in list(_before_write):
        result = hook(current, context)
        if result is not None:
            current = result
    return current


def run_after_write(context: dict[str, Any]) -> None:
    """Run every after-write hook with *context*.  Hooks may raise."""
    for hook in list(_after_write):
        hook(context)


@contextlib.contextmanager
def HookContext() -> Iterator[None]:
    """Snapshot + restore the four hook lists.

    Used by tests so an isolated hook list does not leak into the
    next test.  Production code never calls this.
    """
    snapshot = (
        list(_before_read),
        list(_after_read),
        list(_before_write),
        list(_after_write),
    )
    _before_read.clear()
    _after_read.clear()
    _before_write.clear()
    _after_write.clear()
    try:
        yield
    finally:
        _before_read[:] = snapshot[0]
        _after_read[:] = snapshot[1]
        _before_write[:] = snapshot[2]
        _after_write[:] = snapshot[3]


def registered_counts() -> dict[str, int]:
    """Return ``{phase: count}`` for diagnostics + tests."""
    return {
        "before_read": len(_before_read),
        "after_read": len(_after_read),
        "before_write": len(_before_write),
        "after_write": len(_after_write),
    }
