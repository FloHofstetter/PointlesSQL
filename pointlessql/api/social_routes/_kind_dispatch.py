"""Shared ``(kind, ref)`` dispatch helper for polymorphic social routes.

Phase 77.0.F.2 introduces the ``/api/social/{kind}/{ref:path}/...``
namespace.  Routes accept the polymorphic ``(kind, ref)`` tuple and
delegate to the existing DP-scoped service-layer functions when
``kind='dp'``.  Other kinds will be registered in 77.1+ (tables,
models, branches, runs, ...); until then the dispatcher raises a
clean 501 instead of crashing.
"""

from __future__ import annotations

from fastapi import HTTPException

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
        # bare-http-ok: unknown kind is a client mistake.
        raise HTTPException(
            status_code=400, detail=f"unknown entity_kind: {kind!r}"
        )
    if kind != "dp":
        # bare-http-ok: kind registered but not yet routable here.
        raise HTTPException(
            status_code=501,
            detail=(
                f"kind={kind!r} not yet wired through /api/social/; "
                "Phase 77.1+ adds per-kind routing"
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


__all__: list[str] = ["parse_dp_ref"]
