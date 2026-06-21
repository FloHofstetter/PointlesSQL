"""Predictive-optimization policy CRUD + effective resolution.

The control plane for autonomous Delta maintenance: per-catalog /
schema / table policies declaring which operations (OPTIMIZE, VACUUM,
ANALYZE) should run, plus a most-specific-first resolver so a table
inherits a schema's or catalog's policy unless it sets its own.  These
are control records — the maintenance itself runs through the existing
PQL / deltalake path.
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.exceptions import ValidationError
from pointlessql.models import OPTIMIZATION_SCOPE_TYPES, OptimizationPolicy
from pointlessql.services._scope import split_dotted_scope

_SCOPE_DEPTH = {"catalog": 1, "schema": 2, "table": 3}


def _utcnow() -> datetime.datetime:
    """Return the current UTC wall-clock."""
    return datetime.datetime.now(datetime.UTC)


def _normalize_scope(scope_type: str, scope_value: str) -> tuple[str, str]:
    """Validate a scope and return its normalized ``(type, value)``.

    Args:
        scope_type: One of :data:`OPTIMIZATION_SCOPE_TYPES`.
        scope_value: The dotted securable name.

    Returns:
        The cleaned scope pair, with the name case-folded so resolution
        matches case-insensitively the way Unity Catalog names do.

    Raises:
        ValidationError: On an unknown scope type, an empty value, an
            empty name part, or a dotted depth that does not match the
            scope kind (catalog=1, schema=2, table=3).
    """
    if scope_type not in OPTIMIZATION_SCOPE_TYPES:
        raise ValidationError(f"scope_type must be one of {list(OPTIMIZATION_SCOPE_TYPES)}")
    value = (scope_value or "").strip()
    if not value:
        raise ValidationError("scope_value is required")
    split_dotted_scope(scope_type, value, _SCOPE_DEPTH[scope_type])
    return scope_type, value.lower()


def _serialize(row: OptimizationPolicy) -> dict[str, Any]:
    """Render a policy row into a JSON-safe dict."""
    return {
        "id": row.id,
        "scope_type": row.scope_type,
        "scope_value": row.scope_value,
        "enabled": row.enabled,
        "optimize": row.optimize,
        "vacuum": row.vacuum,
        "analyze": row.analyze,
        "vacuum_retention_hours": row.vacuum_retention_hours,
        "created_by": row.created_by,
    }


def list_policies(factory: sessionmaker[Session], *, workspace_id: int) -> list[dict[str, Any]]:
    """List a workspace's maintenance policies, broadest scope first.

    Args:
        factory: Session factory.
        workspace_id: Active workspace.

    Returns:
        Serialized policy dicts ordered catalog → schema → table.
    """
    with factory() as session:
        rows = list(
            session.scalars(
                select(OptimizationPolicy).where(OptimizationPolicy.workspace_id == workspace_id)
            ).all()
        )
    rows.sort(key=lambda r: (_SCOPE_DEPTH.get(r.scope_type, 9), r.scope_value))
    return [_serialize(row) for row in rows]


def set_policy(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    scope_type: str,
    scope_value: str,
    enabled: bool = True,
    optimize: bool = True,
    vacuum: bool = True,
    analyze: bool = True,
    vacuum_retention_hours: int | None = None,
    created_by: str | None = None,
) -> dict[str, Any]:
    """Create or update the policy for a scope (upsert by scope).

    Args:
        factory: Session factory.
        workspace_id: Active workspace.
        scope_type: ``catalog`` / ``schema`` / ``table``.
        scope_value: The dotted securable name (validated).
        enabled: Master switch for the scope.
        optimize: Run OPTIMIZE / compaction.
        vacuum: Run VACUUM.
        analyze: Refresh statistics.
        vacuum_retention_hours: Optional VACUUM retention override.
        created_by: Authoring principal.

    Returns:
        The serialized, persisted policy.  A malformed scope propagates
        the scope validator's :class:`ValidationError` (HTTP 400).
    """
    norm_type, norm_value = _normalize_scope(scope_type, scope_value)
    now = _utcnow()
    with factory() as session:
        row = session.scalar(
            select(OptimizationPolicy).where(
                OptimizationPolicy.workspace_id == workspace_id,
                OptimizationPolicy.scope_type == norm_type,
                OptimizationPolicy.scope_value == norm_value,
            )
        )
        if row is None:
            row = OptimizationPolicy(
                workspace_id=workspace_id,
                scope_type=norm_type,
                scope_value=norm_value,
                created_by=created_by,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        row.enabled = enabled
        row.optimize = optimize
        row.vacuum = vacuum
        row.analyze = analyze
        row.vacuum_retention_hours = vacuum_retention_hours
        row.updated_at = now
        session.commit()
        session.refresh(row)
        return _serialize(row)


def delete_policy(factory: sessionmaker[Session], *, policy_id: int, workspace_id: int) -> bool:
    """Delete one maintenance policy; returns whether a row was removed.

    Args:
        factory: Session factory.
        policy_id: Target policy id.
        workspace_id: Owning workspace; a policy in any other workspace is
            left untouched and reported as no-match.

    Returns:
        ``True`` when the policy existed.
    """
    with factory() as session:
        row = session.get(OptimizationPolicy, policy_id)
        if row is None or int(row.workspace_id) != workspace_id:
            return False
        session.delete(row)
        session.commit()
    return True


def effective_policy(
    factory: sessionmaker[Session], *, workspace_id: int, full_name: str
) -> dict[str, Any]:
    """Resolve a table's effective maintenance policy, most-specific-first.

    A ``table`` policy wins over a ``schema`` policy over a ``catalog``
    policy.  When no scope matches, the default (no autonomous
    maintenance) applies.

    Args:
        factory: Session factory.
        workspace_id: Active workspace.
        full_name: Three-part ``catalog.schema.table`` name.

    Returns:
        A JSON-safe dict with the resolved ``enabled`` / ``optimize`` /
        ``vacuum`` / ``analyze`` / ``vacuum_retention_hours`` settings,
        the ``matched_scope`` (e.g. ``"schema:main.sales"`` or ``None``),
        and ``source`` (``"policy"`` / ``"default"``).
    """
    # Scope values are stored case-folded, so fold the queried name too:
    # Unity Catalog identifiers are case-insensitive and a policy set on
    # ``Main.Sales`` must still resolve for a query against ``main.sales``.
    parts = full_name.lower().split(".")
    candidates: list[tuple[str, str]] = []
    if len(parts) >= 3 and all(parts[:3]):
        candidates.append(("table", ".".join(parts[:3])))
    if len(parts) >= 2 and all(parts[:2]):
        candidates.append(("schema", ".".join(parts[:2])))
    if parts and parts[0]:
        candidates.append(("catalog", parts[0]))

    with factory() as session:
        rows = list(
            session.scalars(
                select(OptimizationPolicy).where(OptimizationPolicy.workspace_id == workspace_id)
            ).all()
        )
    by_key = {(row.scope_type, row.scope_value): row for row in rows}
    for scope_type, scope_value in candidates:
        row = by_key.get((scope_type, scope_value))
        if row is not None:
            return {
                "enabled": row.enabled,
                "optimize": row.optimize,
                "vacuum": row.vacuum,
                "analyze": row.analyze,
                "vacuum_retention_hours": row.vacuum_retention_hours,
                "matched_scope": f"{scope_type}:{scope_value}",
                "source": "policy",
            }

    return {
        "enabled": False,
        "optimize": False,
        "vacuum": False,
        "analyze": False,
        "vacuum_retention_hours": None,
        "matched_scope": None,
        "source": "default",
    }
