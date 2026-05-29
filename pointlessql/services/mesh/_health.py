"""Mesh-health rollup — SLO verdicts aggregated across all products.

Evaluates every product's objectives (via the SLO evaluator) and derives
a per-product health band plus a mesh-level summary, so an operator sees
the whole mesh's trustworthiness at a glance.  Pure read — the evaluator
works off the self-generated statistics, so no Delta IO.
"""

from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy import select

from pointlessql.models import DataProduct
from pointlessql.services import slo as slo_service


class _SessionFactory(Protocol):
    """Structural protocol matching ``sessionmaker``'s ``__call__``."""

    def __call__(self) -> Any:
        """Return a new SQLAlchemy session."""
        ...


def _band(passed: int, failed: int) -> str:
    """Return a health band from pass/fail counts.

    ``red`` when any objective fails, ``green`` when at least one is
    scored and none fail, ``unknown`` when nothing could be scored.
    """
    if failed > 0:
        return "red"
    if passed > 0:
        return "green"
    return "unknown"


def mesh_health(
    session_factory: _SessionFactory,
    *,
    workspace_id: int,
    sigma: float = 2.0,
) -> dict[str, Any]:
    """Roll up SLO health across every product in a workspace.

    Args:
        session_factory: Sessionmaker callable.
        workspace_id: Workspace to summarise.
        sigma: z-score threshold passed to the SLO evaluator.

    Returns:
        ``{"products": [...], "summary": {...}}`` — each product entry
        carries its ref, band, and SLO counts; the summary carries the
        band tally + the mesh-wide pass rate + the worst offenders.
    """
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(DataProduct)
                .where(DataProduct.workspace_id == workspace_id)
                .order_by(DataProduct.catalog_name.asc(), DataProduct.schema_name.asc())
            ).all()
        )
        specs = [(r.id, r.catalog_name, r.schema_name) for r in rows]

    products: list[dict[str, Any]] = []
    bands = {"green": 0, "red": 0, "unknown": 0}
    total_passed = 0
    total_failed = 0
    for product_id, catalog, schema in specs:
        evaluation = slo_service.evaluate_product(
            session_factory, data_product_id=product_id, sigma=sigma
        )
        band = _band(evaluation["passed"], evaluation["failed"])
        bands[band] += 1
        total_passed += evaluation["passed"]
        total_failed += evaluation["failed"]
        products.append(
            {
                "data_product_id": product_id,
                "ref": f"{catalog}.{schema}",
                "catalog": catalog,
                "schema": schema,
                "band": band,
                "passed": evaluation["passed"],
                "failed": evaluation["failed"],
                "unmeasured": evaluation["unmeasured"],
                "pass_rate": evaluation["pass_rate"],
            }
        )

    total = len(specs)
    scored = total_passed + total_failed
    worst = sorted(
        (p for p in products if p["failed"] > 0),
        key=lambda p: p["failed"],
        reverse=True,
    )[:5]
    return {
        "products": products,
        "summary": {
            "total_products": total,
            "bands": bands,
            "green_pct": (bands["green"] / total * 100.0) if total else None,
            "pass_rate": (total_passed / scored) if scored else None,
            "worst_offenders": [
                {"ref": p["ref"], "failed": p["failed"]} for p in worst
            ],
        },
    }
