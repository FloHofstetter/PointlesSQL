"""Cross-product join suggestions from shared mesh entities.

When two products each bind a column to the same mesh entity, those
columns are the natural join key between them.  :func:`joinable_columns`
pairs them and emits a ready-to-paste sample JOIN so a consumer can
combine products across domain boundaries without guessing keys.
"""

from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy import select

from pointlessql.models import (
    DataProduct,
    MeshEntity,
    MeshEntityBinding,
)


class _SessionFactory(Protocol):
    """Structural protocol matching ``sessionmaker``'s ``__call__``."""

    def __call__(self) -> Any:
        """Return a new SQLAlchemy session."""
        ...


def _bindings_by_entity(session: Any, data_product_id: int) -> dict[int, MeshEntityBinding]:
    """Return ``{mesh_entity_id: first binding}`` for a product."""
    rows = session.scalars(
        select(MeshEntityBinding)
        .where(MeshEntityBinding.data_product_id == data_product_id)
        .order_by(MeshEntityBinding.table_name.asc(), MeshEntityBinding.column_name.asc())
    ).all()
    out: dict[int, MeshEntityBinding] = {}
    for row in rows:
        out.setdefault(row.mesh_entity_id, row)
    return out


def joinable_columns(
    session_factory: _SessionFactory,
    *,
    left_product_id: int,
    right_product_id: int,
) -> list[dict[str, Any]]:
    """Return the shared-entity join keys between two products.

    Args:
        session_factory: Sessionmaker callable.
        left_product_id: One product.
        right_product_id: The other product.

    Returns:
        One dict per shared entity — ``entity`` (slug + name), the
        ``left`` / ``right`` ``(table, column)`` pair, and a sample
        ``join_sql`` snippet.  Empty when the products share no entity.
    """
    if left_product_id == right_product_id:
        return []
    with session_factory() as session:
        left = session.get(DataProduct, left_product_id)
        right = session.get(DataProduct, right_product_id)
        if left is None or right is None:
            return []
        left_bindings = _bindings_by_entity(session, left_product_id)
        right_bindings = _bindings_by_entity(session, right_product_id)
        shared = set(left_bindings) & set(right_bindings)
        if not shared:
            return []
        suggestions: list[dict[str, Any]] = []
        for entity_id in shared:
            entity = session.get(MeshEntity, entity_id)
            if entity is None:
                continue
            lb = left_bindings[entity_id]
            rb = right_bindings[entity_id]
            left_fqn = f"{lb.catalog}.{lb.schema_name}.{lb.table_name}"
            right_fqn = f"{rb.catalog}.{rb.schema_name}.{rb.table_name}"
            join_sql = (
                f"SELECT *\nFROM {left_fqn} AS l\n"
                f"JOIN {right_fqn} AS r\n"
                f"  ON l.{lb.column_name} = r.{rb.column_name}"
            )
            suggestions.append(
                {
                    "entity": {"slug": entity.slug, "name": entity.name},
                    "left": {
                        "table": left_fqn,
                        "column": lb.column_name,
                    },
                    "right": {
                        "table": right_fqn,
                        "column": rb.column_name,
                    },
                    "join_sql": join_sql,
                }
            )
        suggestions.sort(key=lambda s: s["entity"]["slug"])
        return suggestions
