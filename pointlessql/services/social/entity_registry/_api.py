"""Public lookup + mutation API for the entity-kind registry."""

from __future__ import annotations

from pointlessql.services.social.entity_registry._registry_data import REGISTRY
from pointlessql.services.social.entity_registry._spec import EntityKindSpec


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
    if spec.key in REGISTRY:
        msg = f"entity_kind {spec.key!r} already registered"
        raise ValueError(msg)
    REGISTRY[spec.key] = spec


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
    spec = REGISTRY.get(kind)
    if spec is None:
        msg = f"entity_kind {kind!r} is not registered"
        raise KeyError(msg)
    return spec


def all_kinds() -> tuple[str, ...]:
    """Return every registered kind key in registration order."""
    return tuple(REGISTRY.keys())


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
