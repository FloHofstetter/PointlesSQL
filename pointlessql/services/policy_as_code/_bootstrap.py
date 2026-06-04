"""Wire the Cedar engine into the PQL hook registry.

Idempotent — calling :func:`register_cedar_hooks` twice does not
double-register; the second call is a no-op.  The boot path calls
this once at process start; tests use
:func:`pointlessql.pql._hooks.HookContext` to isolate from boot-time
state.
"""

from __future__ import annotations

import datetime
from typing import Any

from pointlessql.exceptions import PermissionDeniedError
from pointlessql.pql._hooks import (
    register_before_read,
    register_before_write,
)
from pointlessql.services.policy_as_code._audit import persist_decision
from pointlessql.services.policy_as_code._engine import (
    CEDAR_DEFAULT_DENY_REASON,
    Decision,
    cedar_evaluate,
)
from pointlessql.services.policy_as_code._loader import (
    load_linked_modules_for_product,
)
from pointlessql.services.policy_as_code._translator import (
    build_resource_id,
    cedar_action,
    principal_uid,
)
from pointlessql.types import SessionFactory

_registered: bool = False


def register_cedar_hooks(session_factory: SessionFactory) -> None:
    """Register Cedar before-read + before-write hooks (idempotent)."""
    global _registered
    if _registered:
        return
    read_hook = _make_evaluator(session_factory, action="read")
    write_hook = _make_evaluator(session_factory, action="write")

    def read_callback(ctx: dict[str, Any]) -> None:
        read_hook(ctx)

    def write_callback(_frame: Any, ctx: dict[str, Any]) -> Any:
        write_hook(ctx)
        return None

    register_before_read(read_callback)
    register_before_write(write_callback)
    _registered = True


def reset_for_tests() -> None:
    """Drop the idempotency flag so a fresh ``HookContext`` re-registers."""
    global _registered
    _registered = False


def _make_evaluator(
    session_factory: SessionFactory, *, action: str
) -> Any:
    """Build a closure that evaluates Cedar for one action verb."""
    def hook(ctx: dict[str, Any]) -> None:
        product_id = ctx.get("authoring_product_id")
        workspace_id = int(ctx.get("workspace_id") or 1)
        if not isinstance(product_id, int):
            return
        modules = load_linked_modules_for_product(
            session_factory,
            data_product_id=product_id,
            workspace_id=workspace_id,
        )
        if not modules:
            return
        principal = ctx.get("principal") or {}
        full_name = ctx.get("full_name") or ""
        catalog, schema, *_ = (full_name + "..").split(".")
        decision = cedar_evaluate(
            modules,
            principal=principal_uid(principal),
            action=cedar_action(action),
            resource=build_resource_id(
                resource_type="DataProduct",
                catalog=catalog or None,
                schema=schema or None,
            ),
            context={"full_name": full_name},
        )
        for module in modules:
            persist_decision(
                session_factory,
                policy_module_id=int(module.id),
                workspace_id=workspace_id,
                principal_user_id=(
                    int(principal["id"]) if principal.get("id") else None
                ),
                principal_email=str(principal.get("email", "")),
                action=action,
                resource_type="DataProduct",
                resource_id=f"{catalog}.{schema}" if catalog and schema else "unknown",
                decision=decision,
                emit_audit=False,
            )
        if decision.effect == "forbid":
            reason = decision.error_class or CEDAR_DEFAULT_DENY_REASON
            raise PermissionDeniedError(
                detail=f"Cedar policy denied {action} on {full_name} ({reason})"
            )

    return hook


def evaluate_via_modules_for_test(
    session_factory: SessionFactory,
    *,
    workspace_id: int,
    principal: dict[str, Any],
    action: str,
    catalog: str,
    schema: str,
) -> Decision:
    """Drive the same evaluation path the hook uses, for unit tests."""
    from pointlessql.services.policy_as_code._loader import (
        load_active_modules_for_workspace,
    )

    modules = load_active_modules_for_workspace(
        session_factory, workspace_id=workspace_id
    )
    _ = datetime.datetime.now(datetime.UTC)
    return cedar_evaluate(
        modules,
        principal=principal_uid(principal),
        action=cedar_action(action),
        resource=build_resource_id(
            resource_type="DataProduct",
            catalog=catalog,
            schema=schema,
        ),
        context={},
    )
