"""Column-classification CRUD + the sidecar's batch lookup.

A classification tags one UC column with a confidentiality class; the
class drives read-time masking.  ``effective_strategy`` maps a class to
its default masking strategy (overridable per row), and
``classifications_for_schema`` is the batch reverse-lookup the masking
sidecar + the discovery contract use to find every classified column in
a product's schema in one query.
"""

from __future__ import annotations

import datetime
from typing import Any, Protocol

from sqlalchemy import select

from pointlessql.models import (
    CLASSIFICATIONS,
    MASKING_STRATEGIES,
    DataProduct,
    DataProductColumnClassification,
)

#: Default masking strategy applied when a classification row leaves
#: ``masking_strategy`` NULL.  Least → most aggressive: public/internal
#: pass through, confidential hashes, pii keeps shape, phi blanks fully.
DEFAULT_STRATEGY_BY_CLASS: dict[str, str] = {
    "public": "none",
    "internal": "none",
    "confidential": "hash",
    "pii": "partial",
    "phi": "full",
}


class _SessionFactory(Protocol):
    """Structural protocol matching ``sessionmaker``'s ``__call__``."""

    def __call__(self) -> Any:
        """Return a new SQLAlchemy session."""
        ...


def effective_strategy(classification: str, override: str | None) -> str:
    """Return the masking strategy for a class + optional override.

    Args:
        classification: One of :data:`CLASSIFICATIONS`.
        override: An explicit :data:`MASKING_STRATEGIES` value, or
            ``None`` to use the per-class default.

    Returns:
        The strategy to apply at read time.
    """
    if override:
        return override
    return DEFAULT_STRATEGY_BY_CLASS.get(classification, "none")


def list_classifications(
    session_factory: _SessionFactory, *, data_product_id: int
) -> list[DataProductColumnClassification]:
    """Return every classification on a product ordered by table/column."""
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(DataProductColumnClassification)
                .where(DataProductColumnClassification.data_product_id == data_product_id)
                .order_by(
                    DataProductColumnClassification.table_name.asc(),
                    DataProductColumnClassification.column_name.asc(),
                )
            ).all()
        )
        for row in rows:
            session.expunge(row)
        return rows


def add_classification(
    session_factory: _SessionFactory,
    *,
    data_product_id: int,
    catalog: str,
    schema: str,
    table: str,
    column: str,
    classification: str,
    masking_strategy: str | None = None,
    created_by_user_id: int | None = None,
) -> DataProductColumnClassification:
    """Classify one column; upserts on the (product, column) identity.

    Args:
        session_factory: Sessionmaker callable.
        data_product_id: Product the column belongs to.
        catalog: UC catalog segment.
        schema: UC schema segment.
        table: UC table name.
        column: UC column name.
        classification: One of :data:`CLASSIFICATIONS`.
        masking_strategy: Optional override (:data:`MASKING_STRATEGIES`);
            ``None`` derives from the class.
        created_by_user_id: User declaring the classification.

    Returns:
        The detached classification row.

    Raises:
        ValueError: On a bad class/strategy, an unknown product, or
            empty identity segments.
    """
    if classification not in CLASSIFICATIONS:
        raise ValueError(f"classification {classification!r} not in {CLASSIFICATIONS}")
    if masking_strategy is not None and masking_strategy not in MASKING_STRATEGIES:
        raise ValueError(f"masking strategy {masking_strategy!r} not in {MASKING_STRATEGIES}")
    catalog, schema, table, column = (
        catalog.strip(),
        schema.strip(),
        table.strip(),
        column.strip(),
    )
    if not (catalog and schema and table and column):
        raise ValueError("catalog/schema/table/column must all be non-empty")
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        if session.get(DataProduct, data_product_id) is None:
            raise ValueError(f"data product id={data_product_id} not found")
        row = session.scalar(
            select(DataProductColumnClassification).where(
                DataProductColumnClassification.data_product_id == data_product_id,
                DataProductColumnClassification.catalog == catalog,
                DataProductColumnClassification.schema_name == schema,
                DataProductColumnClassification.table_name == table,
                DataProductColumnClassification.column_name == column,
            )
        )
        if row is None:
            row = DataProductColumnClassification(
                data_product_id=data_product_id,
                catalog=catalog,
                schema_name=schema,
                table_name=table,
                column_name=column,
                created_by_user_id=created_by_user_id,
                created_at=now,
            )
            session.add(row)
        row.classification = classification
        row.masking_strategy = masking_strategy
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row


def delete_classification(
    session_factory: _SessionFactory, *, data_product_id: int, classification_id: int
) -> bool:
    """Remove a classification from a product.

    Returns:
        ``True`` when a row was deleted, ``False`` when none matched.
    """
    with session_factory() as session:
        row = session.scalar(
            select(DataProductColumnClassification).where(
                DataProductColumnClassification.id == classification_id,
                DataProductColumnClassification.data_product_id == data_product_id,
            )
        )
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def classifications_for_schema(
    session_factory: _SessionFactory, *, catalog: str, schema: str
) -> dict[tuple[str, str], tuple[str, str]]:
    """Return ``{(table, column): (classification, strategy)}`` for a schema.

    The batch lookup the masking sidecar + the discovery contract use:
    one query returns every classified column in the schema with its
    effective masking strategy resolved.

    Args:
        session_factory: Sessionmaker callable.
        catalog: UC catalog segment.
        schema: UC schema segment.

    Returns:
        Mapping keyed by ``(table_name, column_name)``.
    """
    index: dict[tuple[str, str], tuple[str, str]] = {}
    with session_factory() as session:
        rows = session.scalars(
            select(DataProductColumnClassification).where(
                DataProductColumnClassification.catalog == catalog,
                DataProductColumnClassification.schema_name == schema,
            )
        ).all()
        for row in rows:
            index[(row.table_name, row.column_name)] = (
                row.classification,
                effective_strategy(row.classification, row.masking_strategy),
            )
    return index
