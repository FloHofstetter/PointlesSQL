"""Polymorphic entity registry (Phase 77.0).

Single source of truth for what each ``entity_kind`` means in
the social layer.  Every later Phase-77 sub-phase that adds a
new entity kind (tables, models, branches, runs, …) registers
one :class:`EntityKindSpec` here and the rest of the social
plumbing — citation tokens, audit-target builders, URL routers,
tab strips — keys off this registry by `kind` string.

Phase 77.0 only registers the ``dp`` kind so end-user behavior
stays identical.  Tables / models / branches / etc. land in
their respective sub-phases.

Capability flags (``supports_*``) drive the per-entity tab
strip on the frontend.  A kind with ``supports_reviews=False``
hides the Reviews tab; ``supports_issues=False`` hides Issues;
``supports_readme=False`` hides README.  Defaults match the
DP-social Phase-76 shape so dropping the registry for a new
kind always *adds* capabilities, never accidentally removes
them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EntityKindSpec:
    """Capability + addressing shape for one ``entity_kind``.

    Attributes:
        key: The discriminator string stored on
            :class:`SocialTarget.entity_kind`.  Must match one of
            :data:`pointlessql.models.social.ENTITY_KINDS`.
        label: Human-readable name for the entity class.  Used
            in audit-log target prefixes (post-77.0 generic form)
            and admin UIs.
        url_for: Callable that maps ``entity_ref`` to the
            canonical frontend route — e.g. for ``kind='dp'``,
            ``"main.sales" -> "/data-products/main/sales"``.
        audit_target_prefix: The string emitted as the
            ``audit_log.target`` column's leading prefix.  For
            ``kind='dp'`` this is the legacy ``data_product:``
            (locked decision #9 of the Phase-77 plan).  For every
            other kind it defaults to ``{key}:``.
        supports_reviews: ``True`` if the kind exposes a Reviews
            tab (star ratings).  Tables / branches / runs default
            to ``False``.
        supports_endorsements: ``True`` if the kind exposes
            steward endorsements.  Most kinds default to ``True``.
        supports_readme: ``True`` if the kind has a long-form
            polymorphic README (rendered alongside any
            short-form catalog comment).
        supports_issues: ``True`` if the kind can have GitHub-
            style tracked issues opened against it.
        supports_stars: ``True`` if the kind can be bookmarked
            via the lightweight Stars primitive.
        tab_keys: Ordered tuple of tab-key strings that the
            ``socialTabs`` Alpine factory renders for this kind.
            Driven by the ``supports_*`` flags but pinned here
            so the front-end has a stable contract.
    """

    key: str
    label: str
    url_for: Callable[[str], str]
    audit_target_prefix: str
    supports_reviews: bool = True
    supports_endorsements: bool = True
    supports_readme: bool = True
    supports_issues: bool = True
    supports_stars: bool = True
    tab_keys: tuple[str, ...] = field(
        default=(
            "discussion",
            "reviews",
            "endorsements",
            "followers",
            "readme",
            "issues",
        )
    )


def _dp_url(entity_ref: str) -> str:
    """Map ``cat.sch`` to the data-product detail URL."""
    parts = entity_ref.split(".", 1)
    if len(parts) != 2:
        return "/data-products"
    return f"/data-products/{parts[0]}/{parts[1]}"


_REGISTRY: dict[str, EntityKindSpec] = {
    "dp": EntityKindSpec(
        key="dp",
        label="Data Product",
        url_for=_dp_url,
        # Locked decision #9: kind='dp' keeps the legacy
        # ``data_product:`` audit-target prefix forever so
        # existing SIEM / Grafana queries on
        # ``target LIKE 'data_product:%'`` keep working.
        audit_target_prefix="data_product",
        supports_reviews=True,
        supports_endorsements=True,
        supports_readme=True,
        supports_issues=False,  # Issues land in 77.7
        supports_stars=False,   # Stars land in 77.8
        tab_keys=(
            "overview",
            "contract",
            "diff",
            "lineage",
            "compliance",
            "activity",
            "discussion",
            "reviews",
            "readme",
        ),
    ),
}


def register(spec: EntityKindSpec) -> None:
    """Register a new entity-kind spec.

    Args:
        spec: The kind specification to add.

    Raises:
        ValueError: If a spec with the same ``key`` is already
            registered.  Re-registration is rejected so a sloppy
            import order can't silently shadow another sub-phase's
            wiring.
    """
    if spec.key in _REGISTRY:
        msg = f"entity_kind {spec.key!r} already registered"
        raise ValueError(msg)
    _REGISTRY[spec.key] = spec


def get(kind: str) -> EntityKindSpec:
    """Look up the spec for *kind*.

    Args:
        kind: The discriminator string.

    Returns:
        The registered spec.

    Raises:
        KeyError: If no spec is registered for *kind*.  The
            error message names the kind so callers can
            distinguish "unregistered" from "misspelled".
    """
    spec = _REGISTRY.get(kind)
    if spec is None:
        msg = f"entity_kind {kind!r} is not registered"
        raise KeyError(msg)
    return spec


def all_kinds() -> tuple[str, ...]:
    """Return every registered kind key in registration order."""
    return tuple(_REGISTRY.keys())


def url_for(kind: str, entity_ref: str) -> str:
    """Build the frontend URL for ``(kind, entity_ref)``.

    Args:
        kind: The discriminator string.
        entity_ref: The entity reference string.

    Returns:
        The route under which the entity's detail page lives.
        Falls back to ``/`` if the kind is unregistered — the
        caller is expected to validate first; this fallback only
        protects against partially-migrated audit-log rows.
    """
    try:
        spec = get(kind)
    except KeyError:
        return "/"
    return spec.url_for(entity_ref)


def audit_target(kind: str, entity_ref: str, suffix: str | None = None) -> str:
    """Build the ``audit_log.target`` column value for an entity.

    Args:
        kind: The discriminator string.
        entity_ref: The entity reference string.
        suffix: Optional trailing fragment (e.g.
            ``tab-discussion-comment-42``) appended after a
            ``#`` separator.

    Returns:
        A string of the form ``{prefix}:{ref}`` or
        ``{prefix}:{ref}#{suffix}``.  Prefix is the kind-specific
        registry entry (``data_product`` for kind='dp' per locked
        decision #9, ``{kind}`` for every other kind).
    """
    try:
        prefix = get(kind).audit_target_prefix
    except KeyError:
        prefix = kind
    base = f"{prefix}:{entity_ref}"
    if suffix:
        return f"{base}#{suffix}"
    return base


__all__: list[str] = [
    "EntityKindSpec",
    "all_kinds",
    "audit_target",
    "get",
    "register",
    "url_for",
]
