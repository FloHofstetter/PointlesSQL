"""Bulk endorsement lookup for the data-product browse listing.

The detail page reads endorsements one product at a time; the
marketplace listing needs them for every product on the page in a
single round-trip so a "certified" badge can render without an N+1
fan-out.  Only *active* rows (``removed_at IS NULL``) count — a removed
endorsement leaves a tombstone row behind by design.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from pointlessql.models.catalog._data_product_endorsement import DataProductEndorsement


def endorsements_for_products(
    session: Any,
    *,
    workspace_id: int,
    dp_ids: list[int],
) -> dict[int, list[dict[str, Any]]]:
    """Group active endorsements by data-product id.

    Args:
        session: An open SQLAlchemy session (the listing handler's).
        workspace_id: Tenant scope.
        dp_ids: The product ids on the current page.

    Returns:
        ``{data_product_id: [{"type", "applied_at"}, ...]}`` with the
        most-recently-applied endorsement first.  Products with no
        active endorsement are absent from the map.
    """
    if not dp_ids:
        return {}
    rows = session.execute(
        select(
            DataProductEndorsement.data_product_id,
            DataProductEndorsement.endorsement_type,
            DataProductEndorsement.applied_at,
        )
        .where(
            DataProductEndorsement.workspace_id == workspace_id,
            DataProductEndorsement.data_product_id.in_(dp_ids),
            DataProductEndorsement.removed_at.is_(None),
        )
        .order_by(DataProductEndorsement.applied_at.desc())
    ).all()
    out: dict[int, list[dict[str, Any]]] = {}
    for dp_id, etype, applied_at in rows:
        if dp_id is None:
            continue
        out.setdefault(int(dp_id), []).append(
            {"type": etype, "applied_at": applied_at.isoformat() if applied_at else None}
        )
    return out
