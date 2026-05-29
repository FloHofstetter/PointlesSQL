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
    unbind_column,
)

__all__ = [
    "bind_column",
    "create_term",
    "delete_term",
    "get_term_by_slug",
    "list_bindings",
    "list_terms",
    "terms_for_column",
    "terms_for_schema",
    "unbind_column",
]
