"""SLO-evaluation scan — flags failing objectives across a workspace.

Evaluates every product's declared (and implicit-freshness) objectives
and logs each ``fail`` verdict to the durable audit log as an
``slo.violation`` row (``target = "data_product:{catalog}.{schema}"``)
so failures surface in the audit cockpit + the product's SLO panel.
Mirrors the governance compliance scan: deterministic findings → audit
log, not the statistical anomaly inbox.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from pointlessql.models import DataProduct
from pointlessql.services.audit._core import log_action
from pointlessql.services.slo._evaluate import evaluate_product

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

#: Audit action stamped for every failing SLO.
SLO_VIOLATION_ACTION = "slo.violation"


def scan_workspace(
    session_factory: sessionmaker[Session],
    *,
    workspace_id: int,
    actor_user_id: int = 0,
    actor_email: str = "system",
    sigma: float = 2.0,
) -> dict[str, Any]:
    """Evaluate every product's SLOs + log failures to the audit log.

    Args:
        session_factory: Sessionmaker callable.
        workspace_id: Workspace to scan.
        actor_user_id: Audit actor id (run-as user, or 0 for system).
        actor_email: Audit actor email.
        sigma: z-score threshold for statistical-shape verdicts.

    Returns:
        ``{"products_scanned", "violations": [...]}`` — each violation
        carries the product ref + the failing SLO fields.
    """
    with session_factory() as session:
        products = list(
            session.scalars(
                select(DataProduct).where(DataProduct.workspace_id == workspace_id)
            ).all()
        )
        product_meta = [(p.id, p.catalog_name, p.schema_name) for p in products]

    violations: list[dict[str, Any]] = []
    for product_id, catalog, schema in product_meta:
        evaluation = evaluate_product(
            session_factory, data_product_id=product_id, sigma=sigma
        )
        target = f"data_product:{catalog}.{schema}"
        for result in evaluation["results"]:
            if result["verdict"] != "fail":
                continue
            finding = {
                "slo_kind": result["slo_kind"],
                "table": result["table"],
                "target": result["target"],
                "observed": result["observed"],
                "comparator": result["comparator"],
                "unit": result["unit"],
            }
            violations.append(
                {**finding, "data_product_id": product_id, "ref": f"{catalog}.{schema}"}
            )
            log_action(
                session_factory,
                actor_user_id,
                actor_email,
                SLO_VIOLATION_ACTION,
                target,
                finding,
                actor_role="system",
                workspace_id=workspace_id,
            )

    logger.info(
        "slo.scan_workspace: scanned %s products, %s violations",
        len(product_meta),
        len(violations),
    )
    return {"products_scanned": len(product_meta), "violations": violations}
