"""Per-product semantic-model CRUD primitives.

Single write path for the concept list + the product's example query
(``sample_sql``), shared by the steward/admin API and the agent
plugin tools.  Returns detached ORM rows so callers can serialise
after the session closes.
"""

from __future__ import annotations

import datetime

from sqlalchemy import select

from pointlessql.models import DataProduct, DataProductSemanticConcept
from pointlessql.types import SessionFactory


def add_concept(
    session_factory: SessionFactory,
    *,
    data_product_id: int,
    concept: str,
    description: str | None = None,
    maps_to: str | None = None,
) -> DataProductSemanticConcept:
    """Declare one business concept on a product.

    Args:
        session_factory: Sessionmaker callable.
        data_product_id: Product the concept belongs to.
        concept: Business-entity label, unique per product.
        description: Optional free-form note.
        maps_to: Optional fully-qualified
            ``catalog.schema.table.column`` the concept realises.

    Returns:
        The detached :class:`DataProductSemanticConcept` row.

    Raises:
        ValueError: On an empty / over-long concept, an unknown
            product, or a concept already declared on the product.
    """
    cleaned = concept.strip()
    if not cleaned or len(cleaned) > 200:
        raise ValueError("concept must be 1..200 chars")
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        if session.get(DataProduct, data_product_id) is None:
            raise ValueError(f"data product id={data_product_id} not found")
        existing = session.scalar(
            select(DataProductSemanticConcept).where(
                DataProductSemanticConcept.data_product_id == data_product_id,
                DataProductSemanticConcept.concept == cleaned,
            )
        )
        if existing is not None:
            raise ValueError(f"concept {cleaned!r} already declared on this product")
        row = DataProductSemanticConcept(
            data_product_id=data_product_id,
            concept=cleaned,
            description=description.strip() if description else None,
            maps_to=maps_to.strip() if maps_to else None,
            created_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row


def delete_concept(
    session_factory: SessionFactory, *, data_product_id: int, concept_id: int
) -> bool:
    """Remove a semantic concept from a product.

    Returns:
        ``True`` when a row was deleted, ``False`` when no matching
        concept existed for the product.
    """
    with session_factory() as session:
        row = session.scalar(
            select(DataProductSemanticConcept).where(
                DataProductSemanticConcept.id == concept_id,
                DataProductSemanticConcept.data_product_id == data_product_id,
            )
        )
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def list_concepts(
    session_factory: SessionFactory, *, data_product_id: int
) -> list[DataProductSemanticConcept]:
    """Return every concept on *data_product_id* ordered by concept."""
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(DataProductSemanticConcept)
                .where(DataProductSemanticConcept.data_product_id == data_product_id)
                .order_by(DataProductSemanticConcept.concept.asc())
            ).all()
        )
        for row in rows:
            session.expunge(row)
        return rows


def set_sample_sql(
    session_factory: SessionFactory,
    *,
    data_product_id: int,
    sql: str | None,
) -> DataProduct:
    """Set (or clear) a product's example query.

    Passing ``sql=None`` (or an all-whitespace string) clears it.

    Args:
        session_factory: Sessionmaker callable.
        data_product_id: Product to update.
        sql: Example query text, or ``None`` to clear.

    Returns:
        The detached, updated :class:`DataProduct` row.

    Raises:
        ValueError: When the product does not exist.
    """
    with session_factory() as session:
        product = session.get(DataProduct, data_product_id)
        if product is None:
            raise ValueError(f"data product id={data_product_id} not found")
        cleaned = sql.strip() if sql else ""
        product.sample_sql = cleaned or None
        session.commit()
        session.refresh(product)
        session.expunge(product)
        return product
