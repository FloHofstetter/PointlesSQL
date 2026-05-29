"""Persist Cedar decisions + emit an audit-log row.

A single Cedar evaluation produces two artefacts: a row in
``policy_module_decisions`` (the engineering-shaped decision ledger
the admin UI renders) and one ``log_action`` call to the platform
audit log (the human-shaped action stream).  This module keeps both
writes in one place so a hook author can call a single function.
"""

from __future__ import annotations

import datetime
import json
from typing import Any, Protocol

from pointlessql.models import PolicyModuleDecision
from pointlessql.services.audit._core import log_action
from pointlessql.services.policy_as_code._engine import (
    CEDAR_DEFAULT_DENY_REASON,
    Decision,
)


class _SessionFactory(Protocol):
    """Sessionmaker-shaped callable protocol."""

    def __call__(self) -> Any:
        """Return a SQLAlchemy session."""
        ...


def persist_decision(
    session_factory: _SessionFactory,
    *,
    policy_module_id: int,
    workspace_id: int,
    principal_user_id: int | None,
    principal_email: str,
    action: str,
    resource_type: str,
    resource_id: str,
    decision: Decision,
    emit_audit: bool = True,
) -> None:
    """Persist one Cedar decision row + optional audit-log entry.

    Args:
        session_factory: Sessionmaker callable.
        policy_module_id: Module that produced the decision.  When a
            decision is produced for an empty policy set, callers
            should still pass a sentinel module id so the decision
            joins back to *something* in the UI; an empty-set hook
            should typically skip persistence altogether instead.
        workspace_id: Workspace the request ran in.
        principal_user_id: Principal user PK; ``None`` for anonymous.
        principal_email: Principal email (snapshot for audit).
        action: Cedar action (``read``, ``write``, ``consume``).
        resource_type: Cedar resource type (``DataProduct``,
            ``OutputPort``).
        resource_id: Cedar resource UID payload.
        decision: The :class:`Decision` to persist.
        emit_audit: When True, also write an audit-log row.  Hooks
            running on a hot read path may set this False to keep
            the ledger row but skip the audit fan-out (the read
            audit lands separately).
    """
    context = dict(decision.diagnostics)
    if decision.error_class:
        context["error_class"] = decision.error_class
        context["reason"] = CEDAR_DEFAULT_DENY_REASON
    encoded = json.dumps(context, default=str, separators=(",", ":"))
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        row = PolicyModuleDecision(
            policy_module_id=policy_module_id,
            workspace_id=workspace_id,
            decision_at=now,
            principal_user_id=principal_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            effect=decision.effect,
            context_json=encoded,
            latency_ms=decision.latency_ms,
        )
        session.add(row)
        session.commit()
    if not emit_audit:
        return
    log_action(
        session_factory,  # type: ignore[arg-type]
        user_id=principal_user_id or 0,
        user_email=principal_email,
        action="policy.evaluation",
        target=f"{resource_type}:{resource_id}",
        detail={
            "policy_module_id": policy_module_id,
            "cedar_action": action,
            "effect": decision.effect,
            "latency_ms": decision.latency_ms,
            "error_class": decision.error_class,
        },
        actor_role="system",
        workspace_id=workspace_id,
    )
