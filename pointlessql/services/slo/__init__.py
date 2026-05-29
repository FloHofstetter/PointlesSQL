"""Service-level-objective layer — declaration, drift, evaluation, scan.

Re-exports the SLO CRUD, the statistical-shape drift detector, the
per-product evaluator, and the workspace scan so callers do
``from pointlessql.services import slo`` without reaching into the
private sub-modules.
"""

from __future__ import annotations

from pointlessql.services.slo._crud import (
    declare_slo,
    delete_slo,
    list_slos,
)
from pointlessql.services.slo._drift import compute_drift, max_drift_sigma
from pointlessql.services.slo._evaluate import evaluate_product
from pointlessql.services.slo._kinds import KIND_META, MEASURABLE_SLO_KINDS, SLO_KINDS
from pointlessql.services.slo._scan import SLO_VIOLATION_ACTION, scan_workspace

__all__ = [
    "KIND_META",
    "MEASURABLE_SLO_KINDS",
    "SLO_KINDS",
    "SLO_VIOLATION_ACTION",
    "compute_drift",
    "declare_slo",
    "delete_slo",
    "evaluate_product",
    "list_slos",
    "max_drift_sigma",
    "scan_workspace",
]
