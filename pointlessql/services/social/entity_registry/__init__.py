"""Polymorphic entity registry — split per concern.

The helpers are split along the natural axes:

* :mod:`._spec`          — the :class:`EntityKindSpec` dataclass.
* :mod:`._url_builders`  — the 15 ``_xxx_url`` helpers, one per
  entity kind.
* :mod:`._registry_data` — the ``REGISTRY`` dict holding one
  :class:`EntityKindSpec` per registered kind.
* :mod:`._api`           — public ``register`` / ``get`` /
  ``all_kinds`` / ``url_for`` / ``audit_target`` callables.

The registry is the single source of truth for what each
``entity_kind`` means in the social layer.  Every Phase-77
sub-phase that adds a new entity kind (tables, models, branches,
runs, …) registers one :class:`EntityKindSpec` here and the rest
of the social plumbing — citation tokens, audit-target builders,
URL routers, tab strips — keys off this registry by `kind`
string.

Capability flags (``supports_*``) drive the per-entity tab
strip on the frontend.  A kind with ``supports_reviews=False``
hides the Reviews tab; ``supports_issues=False`` hides Issues;
``supports_readme=False`` hides README.  Defaults match the
DP-social Phase-76 shape so dropping the registry for a new
kind always *adds* capabilities, never accidentally removes
them.
"""

from __future__ import annotations

from pointlessql.services.social.entity_registry._api import (
    all_kinds,
    audit_target,
    get,
    register,
    url_for,
)
from pointlessql.services.social.entity_registry._spec import EntityKindSpec

__all__: list[str] = [
    "EntityKindSpec",
    "all_kinds",
    "audit_target",
    "get",
    "register",
    "url_for",
]
