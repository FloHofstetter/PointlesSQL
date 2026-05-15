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

from pointlessql.services.social import entity_registry

# Per-kind ref-shape contract.  Keys map to a one-line validator
# that accepts the post-split parts and raises 400 with a clean
# message when the shape doesn't match.
_POLYMORPHIC_KINDS: frozenset[str] = frozenset(
    {
        "table",
        "branch",
        "model",
        "run",
        "issue",
        "schema",
        "catalog",
        "notebook",
        "saved_query",
        "workspace",
    }
)


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
        # bare-http-ok: unknown kind is a client mistake.
        raise HTTPException(
            status_code=400, detail=f"unknown entity_kind: {kind!r}"
        )
    if kind != "dp":
        # bare-http-ok: kind registered but not handled by the DP
        # delegator.  Callers should use ``parse_ref`` + the
        # polymorphic handlers when this happens.
        raise HTTPException(
            status_code=501,
            detail=(
                f"kind={kind!r} is not handled by the DP delegator; "
                "the polymorphic handler should be called instead"
            ),
        )
    parts = ref.split(".", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        # bare-http-ok: ref shape is the API contract.
        raise HTTPException(
            status_code=400,
            detail="kind='dp' ref must be 'catalog.schema'",
        )
    return parts[0], parts[1]


def parse_ref(kind: str, ref: str) -> str:
    """Validate the ``(kind, ref)`` shape for the polymorphic path.

    Args:
        kind: Entity kind discriminator from the URL.
        ref: Entity reference from the URL.

    Returns:
        The reference string verbatim (no parsing into parts —
        callers store it as opaque text on ``social_targets.entity_ref``).

    Raises:
        HTTPException: 400 when *kind* is unknown or *ref* is
            malformed; 501 when *kind* is registered but not yet
            wired through the polymorphic handlers.
    """
    if kind not in entity_registry.all_kinds():
        # bare-http-ok: unknown kind is a client mistake.
        raise HTTPException(
            status_code=400, detail=f"unknown entity_kind: {kind!r}"
        )
    if kind == "dp":
        # bare-http-ok: dp uses parse_dp_ref + DP handlers.
        raise HTTPException(
            status_code=400,
            detail=(
                "kind='dp' is handled by the DP delegator path; "
                "use parse_dp_ref"
            ),
        )
    if kind == "table":
        parts = ref.split(".", 2)
        if len(parts) != 3 or not all(parts):
            # bare-http-ok: ref shape is the API contract.
            raise HTTPException(
                status_code=400,
                detail="kind='table' ref must be 'catalog.schema.table'",
            )
        return ref
    if kind == "branch":
        if "__branch_" not in ref or "." not in ref:
            # bare-http-ok: branch FQN must encode catalog.schema__branch_xxx.
            raise HTTPException(
                status_code=400,
                detail=(
                    "kind='branch' ref must be a branch FQN "
                    "('catalog.schema__branch_xxx')"
                ),
            )
        return ref
    if kind == "model":
        parts = ref.split(".", 2)
        if len(parts) != 3 or not all(parts):
            # bare-http-ok: ref shape is the API contract.
            raise HTTPException(
                status_code=400,
                detail="kind='model' ref must be 'catalog.schema.name'",
            )
        return ref
    if kind == "run":
        # Phase 77.4 — run refs are canonical 36-char UUIDs as text.
        if len(ref) != 36 or ref.count("-") != 4:
            # bare-http-ok: ref shape is the API contract.
            raise HTTPException(
                status_code=400,
                detail="kind='run' ref must be a 36-char UUID",
            )
        return ref
    if kind == "issue":
        # Phase 77.7 — issue refs are the integer issues.id serialised
        # as a base-10 string.  Validate digits-only + non-empty
        # upfront so a malformed ref doesn't fall through to a
        # downstream lookup with a fuzzy error.
        if not ref or not ref.isdigit():
            # bare-http-ok: ref shape is the API contract.
            raise HTTPException(
                status_code=400,
                detail="kind='issue' ref must be a numeric issue id",
            )
        return ref
    if kind == "schema":
        # Phase 77.5 — schema refs are ``catalog.schema`` two-part
        # identifiers (UC's address shape).  Two ASCII identifiers
        # joined by exactly one dot.
        parts = ref.split(".", 1)
        if len(parts) != 2 or not all(parts):
            # bare-http-ok: ref shape is the API contract.
            raise HTTPException(
                status_code=400,
                detail="kind='schema' ref must be 'catalog.schema'",
            )
        return ref
    if kind == "catalog":
        # Phase 77.5 — catalog refs are bare UC catalog names —
        # one ASCII identifier, no dots.
        if not ref or "." in ref or "/" in ref:
            # bare-http-ok: ref shape is the API contract.
            raise HTTPException(
                status_code=400,
                detail="kind='catalog' ref must be a bare identifier",
            )
        return ref
    if kind == "notebook":
        # Phase 77.6 — notebook refs are the 36-char UUID stored
        # on ``notebooks.id``.
        if len(ref) != 36 or ref.count("-") != 4:
            # bare-http-ok: ref shape is the API contract.
            raise HTTPException(
                status_code=400,
                detail="kind='notebook' ref must be a 36-char UUID",
            )
        return ref
    if kind == "saved_query":
        # Phase 77.6 — saved-query refs are the slug stored on the
        # saved_audit_queries row.  Accept the same shape as
        # citations (lowercase alphanumerics + hyphens).
        if not ref or "/" in ref:
            # bare-http-ok: ref shape is the API contract.
            raise HTTPException(
                status_code=400,
                detail="kind='saved_query' ref must be a slug",
            )
        return ref
    if kind == "workspace":
        # Phase 77.10 — workspace refs are the workspace slug.
        if not ref or "/" in ref or "." in ref:
            # bare-http-ok: ref shape is the API contract.
            raise HTTPException(
                status_code=400,
                detail="kind='workspace' ref must be a slug",
            )
        return ref
    if kind not in _POLYMORPHIC_KINDS:
        # bare-http-ok: registered but no polymorphic handler yet.
        raise HTTPException(
            status_code=501,
            detail=(
                f"kind={kind!r} not yet wired through polymorphic "
                "/api/social/; later Phase-77 sub-phases add it"
            ),
        )
    return ref


__all__: list[str] = ["parse_dp_ref", "parse_ref"]
