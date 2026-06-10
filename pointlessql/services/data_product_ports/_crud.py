"""Output/input port CRUD primitives for data products.

Single write path for the declared-ports layer — the steward/admin
API and the agent plugin tools both go through these so kind/name
validation and the same-product guard live in one place.

Every function takes a ``session_factory`` and returns detached ORM
rows so callers can serialise them after the session closes (matching
:mod:`pointlessql.services.domains._crud`).
"""

from __future__ import annotations

import datetime

from sqlalchemy import select

from pointlessql.models import (
    INPUT_PORT_KINDS,
    OUTPUT_PORT_KINDS,
    DataProduct,
    DataProductInputPort,
    DataProductOutputPort,
)
from pointlessql.types import SessionFactory


def _clean_name(name: str) -> str:
    """Return *name* trimmed, or raise on an empty / over-long value."""
    cleaned = name.strip()
    if not cleaned or len(cleaned) > 120:
        raise ValueError("port name must be 1..120 chars")
    return cleaned


def create_output_port(
    session_factory: SessionFactory,
    *,
    data_product_id: int,
    name: str,
    kind: str,
    description: str | None = None,
    fmt: str | None = None,
    location: str | None = None,
    created_by_user_id: int | None = None,
) -> DataProductOutputPort:
    """Declare one output port on a product.

    Args:
        session_factory: Sessionmaker callable.
        data_product_id: Product the port belongs to.
        name: Short label, unique per product.
        kind: One of :data:`OUTPUT_PORT_KINDS`.
        description: Optional free-form note.
        fmt: Optional payload format (e.g. ``parquet``).
        location: Optional address (path / topic / URI).
        created_by_user_id: User declaring the port.

    Returns:
        The detached :class:`DataProductOutputPort` row.

    Raises:
        ValueError: On bad kind / name, an unknown product, or a name
            already taken on the product.
    """
    if kind not in OUTPUT_PORT_KINDS:
        raise ValueError(f"output port kind {kind!r} not in {OUTPUT_PORT_KINDS}")
    cleaned_name = _clean_name(name)
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        if session.get(DataProduct, data_product_id) is None:
            raise ValueError(f"data product id={data_product_id} not found")
        existing = session.scalar(
            select(DataProductOutputPort).where(
                DataProductOutputPort.data_product_id == data_product_id,
                DataProductOutputPort.name == cleaned_name,
            )
        )
        if existing is not None:
            raise ValueError(f"output port {cleaned_name!r} already exists on this product")
        row = DataProductOutputPort(
            data_product_id=data_product_id,
            name=cleaned_name,
            kind=kind,
            description=description.strip() if description else None,
            format=fmt.strip() if fmt else None,
            location=location.strip() if location else None,
            created_by_user_id=created_by_user_id,
            created_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row


def delete_output_port(
    session_factory: SessionFactory, *, data_product_id: int, port_id: int
) -> bool:
    """Remove an output port from a product.

    Args:
        session_factory: Sessionmaker callable.
        data_product_id: Product the port must belong to.
        port_id: Primary key of the output port to delete.

    Returns:
        ``True`` when a row was deleted, ``False`` when no matching
        port existed for the product.
    """
    with session_factory() as session:
        row = session.scalar(
            select(DataProductOutputPort).where(
                DataProductOutputPort.id == port_id,
                DataProductOutputPort.data_product_id == data_product_id,
            )
        )
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def list_output_ports(
    session_factory: SessionFactory, *, data_product_id: int
) -> list[DataProductOutputPort]:
    """Return every output port on *data_product_id* ordered by name."""
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(DataProductOutputPort)
                .where(DataProductOutputPort.data_product_id == data_product_id)
                .order_by(DataProductOutputPort.name.asc())
            ).all()
        )
        for row in rows:
            session.expunge(row)
        return rows


def create_input_port(
    session_factory: SessionFactory,
    *,
    data_product_id: int,
    name: str,
    kind: str,
    source_ref: str | None = None,
    source_workspace_id: int | None = None,
    description: str | None = None,
    created_by_user_id: int | None = None,
) -> DataProductInputPort:
    """Declare one upstream input port on a product.

    Args:
        session_factory: Sessionmaker callable.
        data_product_id: Product the input belongs to.
        name: Short label, unique per product.
        kind: One of :data:`INPUT_PORT_KINDS`.
        source_ref: ``catalog.schema`` for ``upstream_product``; a URI
            or system name otherwise.
        source_workspace_id: Optional workspace id when the upstream
            lives outside the consuming product's workspace.  ``None``
            (default) means same workspace as the consuming product.
        description: Optional free-form note.
        created_by_user_id: User declaring the input.

    Returns:
        The detached :class:`DataProductInputPort` row.

    Raises:
        ValueError: On bad kind / name, an unknown product, or a name
            already taken on the product.
    """
    if kind not in INPUT_PORT_KINDS:
        raise ValueError(f"input port kind {kind!r} not in {INPUT_PORT_KINDS}")
    cleaned_name = _clean_name(name)
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        if session.get(DataProduct, data_product_id) is None:
            raise ValueError(f"data product id={data_product_id} not found")
        existing = session.scalar(
            select(DataProductInputPort).where(
                DataProductInputPort.data_product_id == data_product_id,
                DataProductInputPort.name == cleaned_name,
            )
        )
        if existing is not None:
            raise ValueError(f"input port {cleaned_name!r} already exists on this product")
        row = DataProductInputPort(
            data_product_id=data_product_id,
            name=cleaned_name,
            kind=kind,
            source_ref=source_ref.strip() if source_ref else None,
            source_workspace_id=source_workspace_id,
            description=description.strip() if description else None,
            created_by_user_id=created_by_user_id,
            created_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row


def delete_input_port(
    session_factory: SessionFactory, *, data_product_id: int, port_id: int
) -> bool:
    """Remove an input port from a product.

    Args:
        session_factory: Sessionmaker callable.
        data_product_id: Product the port must belong to.
        port_id: Primary key of the input port to delete.

    Returns:
        ``True`` when a row was deleted, ``False`` when no matching
        port existed for the product.
    """
    with session_factory() as session:
        row = session.scalar(
            select(DataProductInputPort).where(
                DataProductInputPort.id == port_id,
                DataProductInputPort.data_product_id == data_product_id,
            )
        )
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def list_input_ports(
    session_factory: SessionFactory, *, data_product_id: int
) -> list[DataProductInputPort]:
    """Return every input port on *data_product_id* ordered by name."""
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(DataProductInputPort)
                .where(DataProductInputPort.data_product_id == data_product_id)
                .order_by(DataProductInputPort.name.asc())
            ).all()
        )
        for row in rows:
            session.expunge(row)
        return rows
