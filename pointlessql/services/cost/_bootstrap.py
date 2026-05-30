"""Wire the quota check into the PQL hook registry.

Idempotent — calling :func:`register_cost_hooks` twice does not
double-register; the second call is a no-op.  The boot path calls
this once at process start; tests use
:func:`pointlessql.pql._hooks.HookContext` to isolate from boot-time
state.
"""

from __future__ import annotations

from typing import Any, Protocol

from pointlessql.pql._hooks import register_before_read
from pointlessql.services.cost._quota import check_quota


class _SessionFactory(Protocol):
    """Sessionmaker-shaped callable protocol."""

    def __call__(self) -> Any:
        """Return a SQLAlchemy session."""
        ...


_registered: bool = False


def register_cost_hooks(session_factory: _SessionFactory) -> None:
    """Register the quota before-read hook (idempotent)."""
    global _registered
    if _registered:
        return

    def read_callback(ctx: dict[str, Any]) -> None:
        product_id = ctx.get("authoring_product_id")
        if not isinstance(product_id, int):
            return
        principal = ctx.get("principal") or {}
        consumer_id: int | None = None
        if isinstance(principal, dict):
            raw = principal.get("id")
            if isinstance(raw, int):
                consumer_id = raw
            elif isinstance(raw, str) and raw.isdigit():
                consumer_id = int(raw)
        workspace_id = int(ctx.get("workspace_id") or 1)
        check_quota(
            session_factory,
            consumer_user_id=consumer_id,
            data_product_id=product_id,
            workspace_id=workspace_id,
        )

    register_before_read(read_callback)
    _registered = True


def reset_for_tests() -> None:
    """Drop the idempotency flag so a fresh ``HookContext`` re-registers."""
    global _registered
    _registered = False
