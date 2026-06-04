"""CRUD helpers for entity declarations + cross-product links.

Owns the persistence path for :class:`DataProductEntity` and
:class:`EntityLink`.  Callers (route layer, resolver, auto-discovery)
funnel through here so the JSON-array encoding of
``primary_key_columns`` stays consistent.
"""

from __future__ import annotations

import datetime
import json
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select

from pointlessql.models.catalog._entity import (
    ENTITY_LINK_KINDS,
    DataProductEntity,
    EntityLink,
)
from pointlessql.types import SessionFactory


def _now() -> datetime.datetime:
    """UTC wall-clock used for ``created_at``/``updated_at``."""
    return datetime.datetime.now(datetime.UTC)


def _encode_pk(columns: Iterable[str]) -> str:
    """JSON-encode the PK-column tuple, preserving order."""
    return json.dumps([str(c) for c in columns])


def _decode_pk(raw: str) -> list[str]:
    """Decode the JSON PK-column tuple.  Empty list on parse error."""
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return [str(c) for c in value] if isinstance(value, list) else []


def declare_entity(
    factory: SessionFactory,
    *,
    data_product_id: int,
    entity_name: str,
    source_table: str,
    primary_key_columns: Iterable[str],
    description: str | None = None,
    created_by_user_id: int | None = None,
) -> dict[str, Any]:
    """Insert or update a :class:`DataProductEntity`.

    Args:
        factory: Sessionmaker callable.
        data_product_id: Owning product PK.
        entity_name: Unique-in-product label.
        source_table: Table the entity is sourced from.
        primary_key_columns: Ordered list of PK column names.
        description: Free-form prose.
        created_by_user_id: Author of the declaration.

    Returns:
        Dict of the persisted row (post-flush).

    Raises:
        ValueError: When ``entity_name`` or ``source_table`` is empty,
            or when ``primary_key_columns`` is empty.
    """
    if not entity_name:
        raise ValueError("entity_name is required")
    if not source_table:
        raise ValueError("source_table is required")
    pk_list = list(primary_key_columns)
    if not pk_list:
        raise ValueError("primary_key_columns must be non-empty")

    now = _now()
    with factory() as session:
        existing = session.scalar(
            select(DataProductEntity).where(
                DataProductEntity.data_product_id == data_product_id,
                DataProductEntity.entity_name == entity_name,
            )
        )
        if existing is None:
            row = DataProductEntity(
                data_product_id=data_product_id,
                entity_name=entity_name,
                source_table=source_table,
                primary_key_columns=_encode_pk(pk_list),
                description=description,
                created_by_user_id=created_by_user_id,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        else:
            existing.source_table = source_table
            existing.primary_key_columns = _encode_pk(pk_list)
            existing.description = description
            existing.updated_at = now
            row = existing
        session.commit()
        return {
            "id": row.id,
            "data_product_id": row.data_product_id,
            "entity_name": row.entity_name,
            "source_table": row.source_table,
            "primary_key_columns": _decode_pk(row.primary_key_columns),
            "description": row.description,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }


def list_entities(
    factory: SessionFactory,
    *,
    data_product_id: int,
) -> list[dict[str, Any]]:
    """Return every entity owned by *data_product_id*."""
    with factory() as session:
        rows = session.scalars(
            select(DataProductEntity)
            .where(DataProductEntity.data_product_id == data_product_id)
            .order_by(DataProductEntity.entity_name)
        ).all()
        return [
            {
                "id": row.id,
                "data_product_id": row.data_product_id,
                "entity_name": row.entity_name,
                "source_table": row.source_table,
                "primary_key_columns": _decode_pk(row.primary_key_columns),
                "description": row.description,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]


def delete_entity(
    factory: SessionFactory,
    *,
    entity_id: int,
) -> bool:
    """Delete the entity by PK.  Returns ``True`` when a row was removed."""
    with factory() as session:
        row = session.get(DataProductEntity, entity_id)
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def link_entities(
    factory: SessionFactory,
    *,
    source_entity_id: int,
    target_entity_id: int,
    kind: str,
    confidence: float | None = None,
    declared_by_user_id: int | None = None,
) -> dict[str, Any]:
    """Insert an :class:`EntityLink` row.  Idempotent on identity.

    Args:
        factory: Sessionmaker callable.
        source_entity_id: Source entity PK.
        target_entity_id: Target entity PK.
        kind: One of :data:`ENTITY_LINK_KINDS`.
        confidence: Optional discovery score; ``None`` for manual.
        declared_by_user_id: Author of the declaration.

    Returns:
        Dict of the link row.

    Raises:
        ValueError: When *kind* is not in :data:`ENTITY_LINK_KINDS` or
            when source and target are identical.
    """
    if kind not in ENTITY_LINK_KINDS:
        raise ValueError(f"unknown link kind: {kind!r}")
    if source_entity_id == target_entity_id:
        raise ValueError("source and target entity must differ")
    with factory() as session:
        existing = session.scalar(
            select(EntityLink).where(
                EntityLink.source_entity_id == source_entity_id,
                EntityLink.target_entity_id == target_entity_id,
                EntityLink.kind == kind,
            )
        )
        if existing is not None:
            row = existing
        else:
            row = EntityLink(
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                kind=kind,
                confidence=confidence,
                declared_by_user_id=declared_by_user_id,
                created_at=_now(),
            )
            session.add(row)
            session.commit()
        return {
            "id": row.id,
            "source_entity_id": row.source_entity_id,
            "target_entity_id": row.target_entity_id,
            "kind": row.kind,
            "confidence": float(row.confidence) if row.confidence is not None else None,
            "declared_by_user_id": row.declared_by_user_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


def unlink_entities(
    factory: SessionFactory,
    *,
    link_id: int,
) -> bool:
    """Delete the link by PK.  Returns ``True`` when a row was removed."""
    with factory() as session:
        row = session.get(EntityLink, link_id)
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def list_links(
    factory: SessionFactory,
    *,
    entity_id: int,
    direction: str = "both",
) -> list[dict[str, Any]]:
    """Return links incident on *entity_id*.

    Args:
        factory: Sessionmaker callable.
        entity_id: Entity PK to query.
        direction: ``"outgoing"`` (source-side), ``"incoming"`` (target-
            side), or ``"both"`` (default).

    Returns:
        List of link dicts ordered by ``created_at``.
    """
    with factory() as session:
        stmt = select(EntityLink)
        if direction == "outgoing":
            stmt = stmt.where(EntityLink.source_entity_id == entity_id)
        elif direction == "incoming":
            stmt = stmt.where(EntityLink.target_entity_id == entity_id)
        else:
            stmt = stmt.where(
                (EntityLink.source_entity_id == entity_id)
                | (EntityLink.target_entity_id == entity_id)
            )
        rows = session.scalars(stmt.order_by(EntityLink.created_at)).all()
        return [
            {
                "id": row.id,
                "source_entity_id": row.source_entity_id,
                "target_entity_id": row.target_entity_id,
                "kind": row.kind,
                "confidence": (
                    float(row.confidence) if row.confidence is not None else None
                ),
                "declared_by_user_id": row.declared_by_user_id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
