"""CRUD operations on policy modules + link list + decision read.

Mirrors the shape of the other admin-CRUD services in
:mod:`pointlessql.services.governance`.  Each function takes a
sessionmaker, opens one session, commits or raises on conflict.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from pointlessql.models import (
    DataProductPolicy,
    PolicyModule,
    PolicyModuleDecision,
    WorkspaceGovernancePolicy,
)
from pointlessql.services.policy_as_code._engine import invalidate_cache
from pointlessql.types import SessionFactory


def _serialise_module(row: PolicyModule) -> dict[str, Any]:
    """Return a discovery-shaped dict for *row*."""
    return {
        "id": int(row.id),
        "workspace_id": int(row.workspace_id),
        "name": row.name,
        "cedar_source": row.cedar_source,
        "version": int(row.version),
        "enabled": bool(row.enabled),
        "created_by_user_id": (
            int(row.created_by_user_id)
            if row.created_by_user_id is not None
            else None
        ),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def list_modules(
    session_factory: SessionFactory,
    *,
    workspace_id: int,
    include_disabled: bool = True,
) -> list[dict[str, Any]]:
    """Return every policy module in *workspace_id*."""
    with session_factory() as session:
        stmt = select(PolicyModule).where(
            PolicyModule.workspace_id == workspace_id
        )
        if not include_disabled:
            stmt = stmt.where(PolicyModule.enabled.is_(True))
        rows = session.scalars(stmt.order_by(PolicyModule.id)).all()
        return [_serialise_module(r) for r in rows]


def get_module(
    session_factory: SessionFactory,
    *,
    module_id: int,
) -> dict[str, Any] | None:
    """Return one module or ``None``."""
    with session_factory() as session:
        row = session.get(PolicyModule, module_id)
        return _serialise_module(row) if row is not None else None


def create_module(
    session_factory: SessionFactory,
    *,
    workspace_id: int,
    name: str,
    cedar_source: str,
    created_by_user_id: int | None,
    enabled: bool = True,
) -> dict[str, Any]:
    """Create a new policy module.

    Raises:
        ValueError: When *name* is blank or already used in the
            workspace.
    """
    if not name or not name.strip():
        raise ValueError("name is required")
    if not cedar_source or not cedar_source.strip():
        raise ValueError("cedar_source is required")
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        row = PolicyModule(
            workspace_id=workspace_id,
            name=name.strip(),
            cedar_source=cedar_source,
            version=1,
            enabled=enabled,
            created_by_user_id=created_by_user_id,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise ValueError(
                f"policy module name '{name}' already exists in workspace"
            ) from exc
        session.refresh(row)
        invalidate_cache(int(row.id))
        return _serialise_module(row)


def update_module(
    session_factory: SessionFactory,
    *,
    module_id: int,
    cedar_source: str | None = None,
    name: str | None = None,
    enabled: bool | None = None,
) -> dict[str, Any] | None:
    """Patch a module in place; ``cedar_source`` change bumps version."""
    with session_factory() as session:
        row = session.get(PolicyModule, module_id)
        if row is None:
            return None
        bump = False
        if cedar_source is not None and cedar_source.strip() != (
            row.cedar_source or ""
        ).strip():
            row.cedar_source = cedar_source
            row.version = int(row.version) + 1
            bump = True
        if name is not None and name.strip() and name.strip() != row.name:
            row.name = name.strip()
        if enabled is not None and bool(enabled) != bool(row.enabled):
            row.enabled = bool(enabled)
        row.updated_at = datetime.datetime.now(datetime.UTC)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise ValueError("policy module name conflict") from exc
        session.refresh(row)
        if bump or enabled is not None:
            invalidate_cache(int(row.id))
        return _serialise_module(row)


def delete_module(
    session_factory: SessionFactory,
    *,
    module_id: int,
) -> bool:
    """Delete a module by id; returns True if a row was removed."""
    with session_factory() as session:
        row = session.get(PolicyModule, module_id)
        if row is None:
            return False
        session.delete(row)
        session.commit()
        invalidate_cache(module_id)
        return True


def set_module_enabled(
    session_factory: SessionFactory,
    *,
    module_id: int,
    enabled: bool,
) -> dict[str, Any] | None:
    """Flip the ``enabled`` flag without bumping the version."""
    return update_module(
        session_factory, module_id=module_id, enabled=enabled
    )


def list_decisions(
    session_factory: SessionFactory,
    *,
    module_id: int,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return recent decisions for *module_id*, newest first."""
    with session_factory() as session:
        rows = session.scalars(
            select(PolicyModuleDecision)
            .where(PolicyModuleDecision.policy_module_id == module_id)
            .order_by(PolicyModuleDecision.decision_at.desc())
            .limit(max(1, min(limit, 500)))
            .offset(max(0, offset))
        ).all()
        out: list[dict[str, Any]] = []
        for row in rows:
            context: dict[str, Any] = {}
            if row.context_json:
                try:
                    decoded = json.loads(row.context_json)
                    if isinstance(decoded, dict):
                        context = decoded
                except (json.JSONDecodeError, ValueError):
                    context = {"raw": row.context_json}
            out.append({
                "id": int(row.id),
                "policy_module_id": int(row.policy_module_id),
                "workspace_id": int(row.workspace_id),
                "decision_at": row.decision_at.isoformat(),
                "principal_user_id": row.principal_user_id,
                "action": row.action,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "effect": row.effect,
                "latency_ms": row.latency_ms,
                "context": context,
            })
        return out


def link_modules_to_product(
    session_factory: SessionFactory,
    *,
    data_product_id: int,
    module_ids: list[int],
    updated_by_user_id: int | None,
) -> list[int]:
    """Set the product's ``linked_policy_module_ids`` list (idempotent)."""
    cleaned = [int(m) for m in module_ids if isinstance(m, int)]
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        row = session.scalar(
            select(DataProductPolicy).where(
                DataProductPolicy.data_product_id == data_product_id
            )
        )
        if row is None:
            row = DataProductPolicy(
                data_product_id=data_product_id,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        row.linked_policy_module_ids = json.dumps(cleaned)
        row.updated_by_user_id = updated_by_user_id
        row.updated_at = now
        session.commit()
    invalidate_cache()
    return cleaned


def link_modules_to_workspace(
    session_factory: SessionFactory,
    *,
    workspace_id: int,
    module_ids: list[int],
    updated_by_user_id: int | None,
) -> list[int]:
    """Set the workspace default ``linked_policy_module_ids`` list."""
    cleaned = [int(m) for m in module_ids if isinstance(m, int)]
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        row = session.scalar(
            select(WorkspaceGovernancePolicy).where(
                WorkspaceGovernancePolicy.workspace_id == workspace_id
            )
        )
        if row is None:
            row = WorkspaceGovernancePolicy(
                workspace_id=workspace_id,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        row.linked_policy_module_ids = json.dumps(cleaned)
        row.updated_by_user_id = updated_by_user_id
        row.updated_at = now
        session.commit()
    invalidate_cache()
    return cleaned
