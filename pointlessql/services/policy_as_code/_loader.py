"""Pull active / linked policy modules from the metadata DB.

Two access paths:

* :func:`load_active_modules_for_workspace` returns every enabled
  module in a workspace, used by the ad-hoc test sandbox.
* :func:`load_linked_modules_for_product` resolves the effective
  link set for a data product: the product's own
  ``linked_policy_module_ids`` overrides the workspace default,
  matching the rest of :data:`POLICY_FIELDS` inheritance.

Both helpers filter out disabled rows so callers never have to
re-check ``enabled``.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from sqlalchemy import select

from pointlessql.models import (
    DataProductPolicy,
    PolicyModule,
    WorkspaceGovernancePolicy,
)


class _SessionFactory(Protocol):
    """Sessionmaker-shaped callable protocol."""

    def __call__(self) -> Any:
        """Return a SQLAlchemy session."""
        ...


def _parse_link_list(raw: str | None) -> list[int]:
    """Decode a ``linked_policy_module_ids`` JSON blob to a list."""
    if not raw:
        return []
    try:
        decoded = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
    if not isinstance(decoded, list):
        return []
    out: list[int] = []
    for item in decoded:
        if isinstance(item, int):
            out.append(item)
        elif isinstance(item, str) and item.isdigit():
            out.append(int(item))
    return out


def load_active_modules_for_workspace(
    session_factory: _SessionFactory, *, workspace_id: int
) -> list[PolicyModule]:
    """Return every enabled :class:`PolicyModule` in the workspace."""
    with session_factory() as session:
        rows = session.scalars(
            select(PolicyModule)
            .where(PolicyModule.workspace_id == workspace_id)
            .where(PolicyModule.enabled.is_(True))
            .order_by(PolicyModule.id)
        ).all()
        return list(rows)


def load_linked_modules_for_product(
    session_factory: _SessionFactory,
    *,
    data_product_id: int,
    workspace_id: int,
) -> list[PolicyModule]:
    """Resolve the effective link set for one product.

    Override order — product link list, falling back to workspace
    default; disabled modules are filtered out.

    Args:
        session_factory: Sessionmaker callable.
        data_product_id: Product to resolve.
        workspace_id: Workspace the product belongs to.

    Returns:
        Ordered list of enabled :class:`PolicyModule` rows.
    """
    with session_factory() as session:
        product_row = session.scalar(
            select(DataProductPolicy).where(
                DataProductPolicy.data_product_id == data_product_id
            )
        )
        product_links = (
            _parse_link_list(getattr(product_row, "linked_policy_module_ids", None))
            if product_row is not None
            else []
        )
        if product_links:
            link_ids = product_links
        else:
            ws_row = session.scalar(
                select(WorkspaceGovernancePolicy).where(
                    WorkspaceGovernancePolicy.workspace_id == workspace_id
                )
            )
            link_ids = (
                _parse_link_list(getattr(ws_row, "linked_policy_module_ids", None))
                if ws_row is not None
                else []
            )
        if not link_ids:
            return []
        rows = session.scalars(
            select(PolicyModule)
            .where(PolicyModule.id.in_(link_ids))
            .where(PolicyModule.workspace_id == workspace_id)
            .where(PolicyModule.enabled.is_(True))
        ).all()
        order = {link: idx for idx, link in enumerate(link_ids)}
        return sorted(rows, key=lambda m: order.get(int(m.id), len(order)))
