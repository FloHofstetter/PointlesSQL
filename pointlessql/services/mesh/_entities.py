"""Polysemic-identity registry: mesh entities + column bindings.

A mesh entity is a named business concept (e.g. "Customer") declared
once per workspace; binding it to columns in different products lets the
platform recognise those columns as the same real-world thing.  This
module is the CRUD + the batch lookups the join helper + discovery use.
"""

from __future__ import annotations

import datetime
import re

from sqlalchemy import select

from pointlessql.models import (
    DataProduct,
    MeshEntity,
    MeshEntityBinding,
)
from pointlessql.types import SessionFactory

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Return a URL-safe slug for an entity name.

    Args:
        value: Raw entity name or slug.

    Returns:
        Lower-cased, hyphen-collapsed slug.

    Raises:
        ValueError: When *value* reduces to the empty string.
    """
    slug = _SLUG_RE.sub("-", value.strip().lower()).strip("-")
    if not slug:
        raise ValueError("entity slug/name must contain an alphanumeric character")
    return slug


def list_entities(session_factory: SessionFactory, *, workspace_id: int) -> list[MeshEntity]:
    """Return every mesh entity in a workspace ordered by name."""
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(MeshEntity)
                .where(MeshEntity.workspace_id == workspace_id)
                .order_by(MeshEntity.name.asc())
            ).all()
        )
        for row in rows:
            session.expunge(row)
        return rows


def create_entity(
    session_factory: SessionFactory,
    *,
    workspace_id: int,
    name: str,
    slug: str | None = None,
    description: str = "",
    created_by_user_id: int | None = None,
) -> MeshEntity:
    """Create (or fetch-by-slug) a mesh entity.

    Args:
        session_factory: Sessionmaker callable.
        workspace_id: Workspace the entity belongs to.
        name: Human label.
        slug: Optional explicit slug; derived from *name* when omitted.
        description: Free-form description.
        created_by_user_id: User declaring the entity.

    Returns:
        The detached entity row (existing one when the slug already
        existed — idempotent create).

    Raises:
        ValueError: When *name* is empty or the slug is invalid.
    """
    name = name.strip()
    if not name:
        raise ValueError("entity name must not be empty")
    resolved_slug = slugify(slug or name)
    now = datetime.datetime.now(datetime.UTC)
    with session_factory() as session:
        existing = session.scalar(
            select(MeshEntity).where(
                MeshEntity.workspace_id == workspace_id,
                MeshEntity.slug == resolved_slug,
            )
        )
        if existing is not None:
            session.expunge(existing)
            return existing
        row = MeshEntity(
            workspace_id=workspace_id,
            slug=resolved_slug,
            name=name,
            description=description or "",
            created_by_user_id=created_by_user_id,
            created_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row


def delete_entity(session_factory: SessionFactory, *, workspace_id: int, entity_id: int) -> bool:
    """Delete an entity (and its bindings, via CASCADE).

    Returns:
        ``True`` when a row was deleted, ``False`` when none matched.
    """
    with session_factory() as session:
        row = session.scalar(
            select(MeshEntity).where(
                MeshEntity.id == entity_id,
                MeshEntity.workspace_id == workspace_id,
            )
        )
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def list_bindings(
    session_factory: SessionFactory,
    *,
    mesh_entity_id: int | None = None,
    data_product_id: int | None = None,
) -> list[MeshEntityBinding]:
    """Return entity-column bindings filtered by entity and/or product."""
    with session_factory() as session:
        stmt = select(MeshEntityBinding)
        if mesh_entity_id is not None:
            stmt = stmt.where(MeshEntityBinding.mesh_entity_id == mesh_entity_id)
        if data_product_id is not None:
            stmt = stmt.where(MeshEntityBinding.data_product_id == data_product_id)
        rows = list(
            session.scalars(
                stmt.order_by(
                    MeshEntityBinding.table_name.asc(),
                    MeshEntityBinding.column_name.asc(),
                )
            ).all()
        )
        for row in rows:
            session.expunge(row)
        return rows


def add_binding(
    session_factory: SessionFactory,
    *,
    mesh_entity_id: int,
    data_product_id: int,
    catalog: str,
    schema: str,
    table: str,
    column: str,
    created_by_user_id: int | None = None,
) -> MeshEntityBinding:
    """Bind an entity to one UC column inside a product.

    Args:
        session_factory: Sessionmaker callable.
        mesh_entity_id: The entity to bind.
        data_product_id: The product the column belongs to.
        catalog: UC catalog segment.
        schema: UC schema segment.
        table: UC table name.
        column: UC column name.
        created_by_user_id: User declaring the binding.

    Returns:
        The detached binding row (existing one when the identity already
        existed — idempotent).

    Raises:
        ValueError: On unknown entity/product or empty identity.
    """
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
        if session.get(MeshEntity, mesh_entity_id) is None:
            raise ValueError(f"mesh entity id={mesh_entity_id} not found")
        if session.get(DataProduct, data_product_id) is None:
            raise ValueError(f"data product id={data_product_id} not found")
        existing = session.scalar(
            select(MeshEntityBinding).where(
                MeshEntityBinding.mesh_entity_id == mesh_entity_id,
                MeshEntityBinding.data_product_id == data_product_id,
                MeshEntityBinding.table_name == table,
                MeshEntityBinding.column_name == column,
            )
        )
        if existing is not None:
            session.expunge(existing)
            return existing
        row = MeshEntityBinding(
            mesh_entity_id=mesh_entity_id,
            data_product_id=data_product_id,
            catalog=catalog,
            schema_name=schema,
            table_name=table,
            column_name=column,
            created_by_user_id=created_by_user_id,
            created_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row


def delete_binding(session_factory: SessionFactory, *, binding_id: int) -> bool:
    """Remove an entity-column binding.

    Returns:
        ``True`` when a row was deleted, ``False`` when none matched.
    """
    with session_factory() as session:
        row = session.get(MeshEntityBinding, binding_id)
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def entities_for_schema(
    session_factory: SessionFactory, *, catalog: str, schema: str
) -> dict[tuple[str, str], list[str]]:
    """Return ``{(table, column): [entity_slug, ...]}`` for a schema.

    The batch lookup the discovery contract + the Interop panel use:
    one query returns every bound column in the schema with the entity
    slugs it maps to.

    Args:
        session_factory: Sessionmaker callable.
        catalog: UC catalog segment.
        schema: UC schema segment.

    Returns:
        Mapping keyed by ``(table_name, column_name)``.
    """
    index: dict[tuple[str, str], list[str]] = {}
    with session_factory() as session:
        rows = session.execute(
            select(MeshEntityBinding, MeshEntity.slug)
            .join(MeshEntity, MeshEntity.id == MeshEntityBinding.mesh_entity_id)
            .where(
                MeshEntityBinding.catalog == catalog,
                MeshEntityBinding.schema_name == schema,
            )
        ).all()
        for binding, slug in rows:
            index.setdefault((binding.table_name, binding.column_name), []).append(slug)
    return index
