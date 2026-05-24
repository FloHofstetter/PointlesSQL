"""Shared ``(kind, ref)`` dispatch helper for polymorphic social routes.

Phase 77.0.F.2 introduces the ``/api/social/{kind}/{ref:path}/...``
namespace.  Phase 77.1.5 extends the dispatch so non-DP kinds
(currently ``table`` and ``branch``) route through generic
polymorphic handlers instead of returning 501.  The DP path keeps
delegating to its existing DP-scoped service-layer functions for
zero behavioural drift.
"""

from __future__ import annotations

from fastapi import HTTPException

from pointlessql.api.social_routes._ref_kinds import find_ref_kind
from pointlessql.exceptions import BadRequestError
from pointlessql.services.social import entity_registry


def parse_dp_ref(kind: str, ref: str) -> tuple[str, str]:
    """Parse ``(kind='dp', ref='catalog.schema')`` into its parts.

    Args:
        kind: Entity kind discriminator from the URL.
        ref: Entity reference from the URL.

    Returns:
        ``(catalog_name, schema_name)`` tuple.

    Raises:
        HTTPException: 501 when *kind* is registered but not yet
            wired through this router; 400 when *kind* is unknown
            or *ref* is malformed.
    """
    if kind not in entity_registry.all_kinds():
        known = sorted(entity_registry.all_kinds())
        shown = ", ".join(known[:5])
        more = "" if len(known) <= 5 else f" (+{len(known) - 5} more)"
        raise BadRequestError(
            f"unknown entity_kind: {kind!r}. Known: {shown}{more}."
        )
    if kind != "dp":
        # bare-http-ok: 501 has no domain-exception counterpart — kind is
        # registered but this code path is the DP delegator only; callers
        # should route through ``parse_ref`` + the polymorphic handlers.
        raise HTTPException(
            status_code=501,
            detail=(
                f"kind={kind!r} is not handled by the DP delegator; "
                "the polymorphic handler should be called instead"
            ),
        )
    parts = ref.split(".", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise BadRequestError("kind='dp' ref must be 'catalog.schema'.")
    return parts[0], parts[1]


def parse_ref(kind: str, ref: str) -> str:
    """Validate the ``(kind, ref)`` shape for the polymorphic path.

    Phase 121.6 Item A refactor: per-kind validators now live in
    :mod:`._ref_kinds` as a :class:`RefKind` registry.  Adding a new
    kind is a single :func:`register_ref_kind` call — no edit to
    this dispatcher.

    Args:
        kind: Entity kind discriminator from the URL.
        ref: Entity reference from the URL.

    Returns:
        The reference string verbatim (no parsing into parts —
        callers store it as opaque text on ``social_targets.entity_ref``).

    Raises:
        HTTPException: 400 when *kind* is unknown or *ref* is
            malformed; 501 when *kind* is registered with soyuz
            entity_registry but no :class:`RefKind` is wired
            through yet.
    """
    if kind not in entity_registry.all_kinds():
        known = sorted(entity_registry.all_kinds())
        shown = ", ".join(known[:5])
        more = "" if len(known) <= 5 else f" (+{len(known) - 5} more)"
        raise BadRequestError(
            f"unknown entity_kind: {kind!r}. Known: {shown}{more}."
        )
    if kind == "dp":
        raise BadRequestError(
            "kind='dp' is handled by the DP delegator path; use parse_dp_ref."
        )
    spec = find_ref_kind(kind)
    if spec is None:
        # bare-http-ok: 501 has no domain-exception counterpart — kind is
        # registered with entity_registry but no polymorphic handler is
        # wired through yet.  Later Phase-77 sub-phases add the missing
        # ones by registering a new RefKind in _ref_kinds.py.
        raise HTTPException(
            status_code=501,
            detail=(
                f"kind={kind!r} not yet wired through polymorphic "
                "/api/social/; later Phase-77 sub-phases add it"
            ),
        )
    if not spec.validate(ref):
        raise BadRequestError(spec.message)
    return ref


__all__: list[str] = ["parse_dp_ref", "parse_ref"]
