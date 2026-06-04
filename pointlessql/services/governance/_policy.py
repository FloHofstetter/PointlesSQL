"""Policy CRUD + effective-policy resolution (product ⇐ workspace).

A product's *effective* policy layers three sources, in order:

1. the product's own override row (:class:`DataProductPolicy`),
2. the workspace default (:class:`WorkspaceGovernancePolicy`),
3. "unset" — neither declared a value.

Each policy field resolves independently, so a product can override
retention while still inheriting the workspace's encryption class.  The
resolver tags every field with its winning source so the UI can render
"inherited" vs. "overridden".
"""

from __future__ import annotations

import datetime
import json
from typing import Any

from sqlalchemy import select

from pointlessql.models import DataProductPolicy, WorkspaceGovernancePolicy
from pointlessql.types import SessionFactory

#: Policy fields that participate in the product ⇐ workspace inheritance.
POLICY_FIELDS: tuple[str, ...] = (
    "retention_days",
    "encryption_class",
    "residency_region",
    "consent_required",
    "consent_basis",
    "consumption_enforcement",
    "iso8601_enforcement",
    "linked_policy_module_ids",
    "breaking_change_policy",
    "max_cost_per_day",
    "max_queries_per_hour",
    "quota_enforcement",
)


def _row_values(row: Any) -> dict[str, Any]:
    """Return the policy field values of *row*, or all-``None`` when missing."""
    if row is None:
        return {field: None for field in POLICY_FIELDS}
    values: dict[str, Any] = {field: getattr(row, field) for field in POLICY_FIELDS}
    # ``linked_policy_module_ids`` is persisted as a JSON-encoded string
    # (the policy-as-code CRUD and the data-product applier both
    # ``json.dumps`` the list before writing).  Decode it back to the
    # ``list[int]`` shape that ``PolicySpec``, the planner diff, and the
    # effective-policy consumers expect, so an export / plan round-trip of a
    # product with linked policy modules does not choke on the raw string.
    raw = values.get("linked_policy_module_ids")
    if isinstance(raw, str):
        try:
            values["linked_policy_module_ids"] = json.loads(raw)
        except ValueError:
            values["linked_policy_module_ids"] = None
    return values


def get_workspace_policy(session_factory: SessionFactory, *, workspace_id: int) -> dict[str, Any]:
    """Return the workspace default policy field values (all-``None`` if unset)."""
    with session_factory() as session:
        row = session.scalar(
            select(WorkspaceGovernancePolicy).where(
                WorkspaceGovernancePolicy.workspace_id == workspace_id
            )
        )
        return _row_values(row)


def get_product_policy(session_factory: SessionFactory, *, data_product_id: int) -> dict[str, Any]:
    """Return the product's override field values (all-``None`` if unset)."""
    with session_factory() as session:
        row = session.scalar(
            select(DataProductPolicy).where(DataProductPolicy.data_product_id == data_product_id)
        )
        return _row_values(row)


def get_effective_policy(
    session_factory: SessionFactory,
    *,
    data_product_id: int,
    workspace_id: int,
) -> dict[str, dict[str, Any]]:
    """Resolve the product's effective policy with per-field provenance.

    Args:
        session_factory: Sessionmaker callable.
        data_product_id: Product to resolve.
        workspace_id: Workspace the product belongs to.

    Returns:
        ``{field: {"value": Any, "source": "product"|"workspace"|"unset"}}``
        for every field in :data:`POLICY_FIELDS`.
    """
    product = get_product_policy(session_factory, data_product_id=data_product_id)
    workspace = get_workspace_policy(session_factory, workspace_id=workspace_id)
    resolved: dict[str, dict[str, Any]] = {}
    for field in POLICY_FIELDS:
        if product[field] is not None:
            resolved[field] = {"value": product[field], "source": "product"}
        elif workspace[field] is not None:
            resolved[field] = {"value": workspace[field], "source": "workspace"}
        else:
            resolved[field] = {"value": None, "source": "unset"}
    return resolved


def _coerce_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Keep only known policy fields, trimming free-text strings."""
    cleaned: dict[str, Any] = {}
    for field in POLICY_FIELDS:
        if field not in fields:
            continue
        value = fields[field]
        if isinstance(value, str):
            value = value.strip() or None
        cleaned[field] = value
    return cleaned


def set_product_policy(
    session_factory: SessionFactory,
    *,
    data_product_id: int,
    fields: dict[str, Any],
    updated_by_user_id: int | None = None,
) -> dict[str, Any]:
    """Upsert the product's policy override row.

    Only keys present in *fields* are written; pass an explicit
    ``None`` to clear a field back to "inherit".

    Args:
        session_factory: Sessionmaker callable.
        data_product_id: Product whose override row to upsert.
        fields: Policy field values to write; only known
            :data:`POLICY_FIELDS` keys are applied.
        updated_by_user_id: User id recorded as the editor, or ``None``.

    Returns:
        The product override field values after the write.
    """
    cleaned = _coerce_fields(fields)
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        row = session.scalar(
            select(DataProductPolicy).where(DataProductPolicy.data_product_id == data_product_id)
        )
        if row is None:
            row = DataProductPolicy(
                data_product_id=data_product_id,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        for field, value in cleaned.items():
            setattr(row, field, value)
        row.updated_by_user_id = updated_by_user_id
        row.updated_at = now
        session.commit()
        return _row_values(row)


def set_workspace_policy(
    session_factory: SessionFactory,
    *,
    workspace_id: int,
    fields: dict[str, Any],
    updated_by_user_id: int | None = None,
) -> dict[str, Any]:
    """Upsert the workspace default policy row.

    Args:
        session_factory: Sessionmaker callable.
        workspace_id: Workspace whose default policy row to upsert.
        fields: Policy field values to write; only known
            :data:`POLICY_FIELDS` keys are applied.
        updated_by_user_id: User id recorded as the editor, or ``None``.

    Returns:
        The workspace default field values after the write.
    """
    cleaned = _coerce_fields(fields)
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
        for field, value in cleaned.items():
            setattr(row, field, value)
        row.updated_by_user_id = updated_by_user_id
        row.updated_at = now
        session.commit()
        return _row_values(row)
