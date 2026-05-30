"""Wire the schema-versioning enforcer into the PQL hook registry.

Idempotent — calling :func:`register_schema_versioning_hooks` twice
does not double-register; the second call is a no-op.  The boot path
calls this once at process start; tests use
:func:`pointlessql.pql._hooks.HookContext` to isolate from boot-time
state.

The hook is a no-op when the write frame does not expose a schema or
when the writing product has no registered output port — both common
in tests and migration paths.
"""

from __future__ import annotations

from typing import Any, Protocol

from pointlessql.pql._hooks import register_before_write
from pointlessql.services.governance._policy import get_effective_policy
from pointlessql.services.schema_versioning._enforcer import (
    assert_schema_compatibility,
)


class _SessionFactory(Protocol):
    """Sessionmaker-shaped callable protocol."""

    def __call__(self) -> Any:
        """Return a SQLAlchemy session."""
        ...


_registered: bool = False


def register_schema_versioning_hooks(session_factory: _SessionFactory) -> None:
    """Register the breaking-change before-write hook (idempotent)."""
    global _registered
    if _registered:
        return

    def write_callback(frame: Any, ctx: dict[str, Any]) -> Any:
        product_id = ctx.get("authoring_product_id")
        if not isinstance(product_id, int):
            return None
        schema = _frame_schema_dict(frame)
        if schema is None:
            return None
        table_name = ctx.get("table_name")
        workspace_id = int(ctx.get("workspace_id") or 1)
        policy = get_effective_policy(
            session_factory,
            data_product_id=product_id,
            workspace_id=workspace_id,
        )
        mode = str(
            policy.get("breaking_change_policy", {}).get("value") or "warn"
        )
        assert_schema_compatibility(
            session_factory,
            data_product_id=product_id,
            table_name=table_name if isinstance(table_name, str) else None,
            new_schema=schema,
            mode=mode,
        )
        return None

    register_before_write(write_callback)
    _registered = True


def reset_for_tests() -> None:
    """Drop the idempotency flag so a fresh ``HookContext`` re-registers."""
    global _registered
    _registered = False


def _frame_schema_dict(frame: Any) -> dict[str, Any] | None:
    """Extract the canonical schema-diff shape from *frame*.

    Returns ``None`` when the frame is missing or shaped unexpectedly —
    the hook treats absent schemas as "writer is not committing a
    schema yet" and stays out of the way.  The shape matches what
    :mod:`_diff` expects: ``{"columns": [{"name", "type", "nullable"}]}``.
    """
    if frame is None:
        return None
    schema = getattr(frame, "schema", None)
    if schema is None:
        return None
    names = getattr(schema, "names", None)
    if names is None:
        return None
    columns: list[dict[str, Any]] = []
    for index, name in enumerate(names):
        field = None
        if hasattr(schema, "field"):
            try:
                field = schema.field(index)
            except (IndexError, KeyError, TypeError):
                field = None
        type_name = str(getattr(field, "type", "unknown")) if field else "unknown"
        nullable = bool(getattr(field, "nullable", True)) if field else True
        columns.append({"name": str(name), "type": type_name, "nullable": nullable})
    return {"columns": columns}
