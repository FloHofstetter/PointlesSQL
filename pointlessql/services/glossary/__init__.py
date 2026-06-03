"""Business-glossary service layer.

Re-exports the term + binding CRUD primitives so callers do
``from pointlessql.services.glossary import create_term`` without
reaching into the private sub-module.
"""

from __future__ import annotations

from pointlessql.services.glossary._crud import (
    bind_column,
    create_term,
    delete_term,
    get_term_by_slug,
    list_bindings,
    list_terms,
    terms_for_column,
    terms_for_schema,
    terms_for_schemas,
    unbind_column,
)
from pointlessql.services.glossary._relations import (
    add_relation,
    delete_relation,
    list_relations,
    term_graph,
)

__all__ = [
    "add_relation",
    "bind_column",
    "create_term",
    "delete_relation",
    "delete_term",
    "get_term_by_slug",
    "list_bindings",
    "list_relations",
    "list_terms",
    "term_graph",
    "terms_for_column",
    "terms_for_schema",
    "terms_for_schemas",
    "unbind_column",
]
