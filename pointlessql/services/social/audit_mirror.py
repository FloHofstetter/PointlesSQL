"""Generic audit-log mirror for social-layer writes (Phase 77.0.C).

Replaces the ad-hoc ``audit_service.log_action(...)`` call
pattern that every Phase-76 social route hand-rolls today.  The
key difference vs ``log_action``: the ``target`` column is built
*via the entity registry* — locked decision #9 of the Phase 77
plan keeps the legacy ``data_product:{ref}`` prefix for
``entity_kind='dp'`` rows while every new kind writes the
generic ``{kind}:{ref}`` form.  Existing SIEM / Grafana queries
on ``target LIKE 'data_product:%'`` stay functional; the kind
migration costs zero ops churn for the DP path.

The detail-JSON auto-injects ``entity_kind`` and ``entity_ref``
so downstream consumers can route by kind without re-parsing
the target string.  Existing keys in the caller-supplied
``detail`` are preserved.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from pointlessql.services import audit as audit_service
from pointlessql.services.social import entity_registry


def mirror_social_to_audit(
    factory: sessionmaker[Session],
    *,
    user_id: int,
    user_email: str,
    action: str,
    entity_kind: str,
    entity_ref: str,
    suffix: str | None = None,
    detail: dict[str, Any] | None = None,
    workspace_id: int = 1,
    actor_role: str = "user",
    client_ip: str | None = None,
) -> None:
    """Write one ``audit_log`` row tagged with a polymorphic target.

    Args:
        factory: SQLAlchemy session factory.
        user_id: ID of the acting user.  ``0`` for system writes.
        user_email: Email snapshot for the audit row.
        action: Short verb (e.g. ``audit.discussion.posted``).
        entity_kind: Discriminator from
            :data:`pointlessql.models.social.ENTITY_KINDS`.
        entity_ref: Reference string within *entity_kind*.
        suffix: Optional trailing fragment for the ``target``
            column (e.g. ``tab-discussion-comment-42``).
            Appended after a ``#`` separator.
        detail: Optional extra context.  Always JSON-encoded.
            ``entity_kind`` and ``entity_ref`` are auto-injected
            if absent so downstream consumers can route by kind.
        workspace_id: Workspace scope.
        actor_role: Role at write time — ``admin`` / ``user`` /
            ``system``.
        client_ip: Optional IPv4/IPv6 address of the caller.
    """
    target = entity_registry.audit_target(
        entity_kind, entity_ref, suffix=suffix
    )
    merged_detail: dict[str, Any] = dict(detail or {})
    merged_detail.setdefault("entity_kind", entity_kind)
    merged_detail.setdefault("entity_ref", entity_ref)
    audit_service.log_action(
        factory,
        user_id=user_id,
        user_email=user_email,
        action=action,
        target=target,
        detail=merged_detail,
        actor_role=actor_role,
        client_ip=client_ip,
        workspace_id=workspace_id,
    )


__all__: list[str] = ["mirror_social_to_audit"]
