"""Domain ownership service layer.

Re-exports the CRUD primitives from :mod:`._crud` so callers do
``from pointlessql.services.domains import create_domain`` (or import
the module as ``domains_service``) without reaching into the private
sub-module.
"""

from __future__ import annotations

from pointlessql.services.domains._crud import (
    add_member,
    assign_product_domain,
    bind_transformation,
    create_domain,
    get_domain,
    get_domain_by_slug,
    list_domains,
    list_members,
    list_products_for_domain,
    list_transformations,
    remove_member,
    unbind_transformation,
)

__all__ = [
    "add_member",
    "assign_product_domain",
    "bind_transformation",
    "create_domain",
    "get_domain",
    "get_domain_by_slug",
    "list_domains",
    "list_members",
    "list_products_for_domain",
    "list_transformations",
    "remove_member",
    "unbind_transformation",
]
