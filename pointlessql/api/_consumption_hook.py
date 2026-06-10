"""Route-layer D2 consumption-enforcement helper (D2).

The three product-bound read routes — Parquet export, table preview,
and SQL editor SELECT — all share the same pre-read shape:

1. Resolve the authoring product (``Depends(get_authoring_product)``).
2. Look up the effective ``consumption_enforcement`` policy.
3. Assert the source table matches a declared upstream input-port.
4. On ``WARN``, emit an audit row but allow the read.
5. On ``BLOCK``, raise :class:`ConsumptionViolation` (handled as 403
   by the central error handler).

This module centralises that shape so every read route looks identical.
"""

from __future__ import annotations

from fastapi import Request

from pointlessql.services import governance as governance_service
from pointlessql.types import SessionFactory, UserInfo


def enforce_consumption_for_read(
    request: Request,
    *,
    factory: SessionFactory,
    workspace_id: int,
    user: UserInfo,
    authoring_product_id: int | None,
    source_fqn: str,
) -> None:
    """Run the D2 verdict + audit for one ``source_fqn`` read.

    No-op when ``authoring_product_id`` is ``None`` — the request is
    not bound to a product contract so there is no consumption rule
    to enforce.

    Args:
        request: Incoming request — used for the ``client_ip`` audit
            field only.
        factory: Sessionmaker callable.
        workspace_id: Workspace the read happens in (audit scoping).
        user: The acting user (audit subject).
        authoring_product_id: The consumer product PK, or ``None``.
        source_fqn: The source being read, ``catalog.schema.table``.

    Raises:
        governance_service.ConsumptionViolation: When the effective
            policy is ``strict`` and the source is undeclared.
    """
    if authoring_product_id is None:
        return
    effective = governance_service.get_effective_policy(
        factory,
        data_product_id=authoring_product_id,
        workspace_id=workspace_id,
    )
    field = effective.get("consumption_enforcement", {})
    mode = field.get("value") or "advisory"
    decision = governance_service.evaluate_consumption(
        factory,
        mode=mode,
        consumer_product_id=authoring_product_id,
        source_fqn=source_fqn,
    )
    if decision.verdict is not governance_service.ConsumptionVerdict.ALLOW:
        governance_service.emit_consumption_audit(
            factory,
            decision=decision,
            user_id=int(user.get("id", 0)),
            user_email=user.get("email", "") or "",
            actor_role="admin" if user.get("is_admin") else "user",
            workspace_id=workspace_id,
            client_ip=request.client.host if request.client else None,
        )
    if decision.verdict is governance_service.ConsumptionVerdict.BLOCK:
        raise governance_service.ConsumptionViolation(decision)
