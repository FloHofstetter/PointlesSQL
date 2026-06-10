"""SLO declaration CRUD.

Declare/list/delete the service-level objectives a product publishes.
Mirrors the column-classification CRUD shape: validate the kind +
comparator, upsert on the (product, table, kind) identity, return
detached rows.
"""

from __future__ import annotations

import datetime

from sqlalchemy import select

from pointlessql.models import (
    SLO_COMPARATORS,
    SLO_KINDS,
    DataProduct,
    DataProductSLO,
)
from pointlessql.services.slo._kinds import KIND_META
from pointlessql.types import SessionFactory


def list_slos(session_factory: SessionFactory, *, data_product_id: int) -> list[DataProductSLO]:
    """Return every SLO declared on a product ordered by table/kind."""
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(DataProductSLO)
                .where(DataProductSLO.data_product_id == data_product_id)
                .order_by(
                    DataProductSLO.table_name.asc(),
                    DataProductSLO.slo_kind.asc(),
                )
            ).all()
        )
        for row in rows:
            session.expunge(row)
        return rows


def declare_slo(
    session_factory: SessionFactory,
    *,
    data_product_id: int,
    slo_kind: str,
    target_value: float | None = None,
    table_name: str | None = None,
    comparator: str | None = None,
    unit: str | None = None,
    enabled: bool = True,
    created_by_user_id: int | None = None,
) -> DataProductSLO:
    """Declare (upsert) one SLO on a product.

    Args:
        session_factory: Sessionmaker callable.
        data_product_id: Product the objective belongs to.
        slo_kind: One of :data:`SLO_KINDS`.
        target_value: Numeric target; may be ``None`` for declaration-
            only kinds.
        table_name: Table the objective scopes to, or ``None`` for
            product-wide.
        comparator: One of :data:`SLO_COMPARATORS`; defaults to the
            kind's natural comparator.
        unit: Optional unit label; defaults to the kind's unit.
        enabled: Whether the evaluator considers the objective.
        created_by_user_id: User declaring the objective.

    Returns:
        The detached SLO row.

    Raises:
        ValueError: On an unknown kind/comparator or unknown product.
    """
    if slo_kind not in SLO_KINDS:
        raise ValueError(f"slo_kind {slo_kind!r} not in {SLO_KINDS}")
    meta = KIND_META.get(slo_kind, {})
    resolved_comparator = comparator or meta.get("comparator", "lte")
    if resolved_comparator not in SLO_COMPARATORS:
        raise ValueError(f"comparator {resolved_comparator!r} not in {SLO_COMPARATORS}")
    resolved_table = table_name.strip() if table_name and table_name.strip() else None
    resolved_unit = unit if unit else meta.get("unit")
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        if session.get(DataProduct, data_product_id) is None:
            raise ValueError(f"data product id={data_product_id} not found")
        row = session.scalar(
            select(DataProductSLO).where(
                DataProductSLO.data_product_id == data_product_id,
                DataProductSLO.table_name.is_(resolved_table)
                if resolved_table is None
                else DataProductSLO.table_name == resolved_table,
                DataProductSLO.slo_kind == slo_kind,
            )
        )
        if row is None:
            row = DataProductSLO(
                data_product_id=data_product_id,
                table_name=resolved_table,
                slo_kind=slo_kind,
                created_by_user_id=created_by_user_id,
                created_at=now,
            )
            session.add(row)
        row.target_value = target_value
        row.comparator = resolved_comparator
        row.unit = resolved_unit
        row.enabled = enabled
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row


def delete_slo(session_factory: SessionFactory, *, data_product_id: int, slo_id: int) -> bool:
    """Remove an SLO from a product.

    Args:
        session_factory: SQLAlchemy sessionmaker for the metadata DB.
        data_product_id: Product the SLO must belong to; guards
            against deleting another product's SLO by id alone.
        slo_id: Primary key of the SLO row to delete.

    Returns:
        ``True`` when a row was deleted, ``False`` when none matched.
    """
    with session_factory() as session:
        row = session.scalar(
            select(DataProductSLO).where(
                DataProductSLO.id == slo_id,
                DataProductSLO.data_product_id == data_product_id,
            )
        )
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True
