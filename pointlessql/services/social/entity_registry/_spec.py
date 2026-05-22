"""The :class:`EntityKindSpec` dataclass — capability shape for one social entity kind."""

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
