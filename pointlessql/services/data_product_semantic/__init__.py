"""Per-product semantic-model service layer.

Re-exports the concept + sample-SQL CRUD primitives so callers do
``from pointlessql.services.data_product_semantic import add_concept``
without reaching into the private sub-module.
"""

from __future__ import annotations

from pointlessql.services.data_product_semantic._crud import (
    add_concept,
    delete_concept,
    list_concepts,
    set_sample_sql,
)

__all__ = [
    "add_concept",
    "delete_concept",
    "list_concepts",
    "set_sample_sql",
]
