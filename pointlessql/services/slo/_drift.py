"""Statistical-shape drift from the self-generated statistics history.

Every write stamps a :class:`DataProductStatistics` snapshot (row count
+ per-column null/distinct shape).  History over several writes gives a
baseline: this module compares the latest snapshot's row count + null
ratios against the mean/std of the prior snapshots and flags any metric
whose z-score exceeds a sigma threshold.  Pure read — no Delta IO.
"""

from __future__ import annotations

import json
import math
from typing import Any

from sqlalchemy import select

from pointlessql.models import DataProductStatistics
from pointlessql.types import SessionFactory

#: Default history depth used for the baseline (excludes the latest).
DEFAULT_BASELINE_DEPTH = 10



def _z_score(observed: float, baseline: list[float]) -> tuple[float, float, float]:
    """Return ``(z, mean, std)`` of *observed* against *baseline* values.

    With a zero-variance baseline the z-score is 0 when the value
    matches the mean and ``inf`` when it diverges, so a frozen series
    that suddenly jumps still flags.
    """
    n = len(baseline)
    if n == 0:
        return 0.0, observed, 0.0
    mean = sum(baseline) / n
    variance = sum((v - mean) ** 2 for v in baseline) / n
    std = math.sqrt(variance)
    if std == 0.0:
        return (0.0 if observed == mean else math.inf), mean, std
    return abs(observed - mean) / std, mean, std


def _null_ratios(shape_json: str, row_count: int | None) -> dict[str, float]:
    """Return ``{column: null_ratio}`` from a stored shape, or ``{}``."""
    if not row_count:
        return {}
    try:
        shape = json.loads(shape_json) if shape_json else {}
    except (TypeError, ValueError):
        return {}
    columns = shape.get("columns", {}) if isinstance(shape, dict) else {}
    ratios: dict[str, float] = {}
    for name, col in columns.items():
        if isinstance(col, dict) and isinstance(col.get("null_count"), int):
            ratios[str(name)] = col["null_count"] / row_count
    return ratios


def compute_drift(
    session_factory: SessionFactory,
    *,
    data_product_id: int,
    table_name: str,
    sigma: float = 2.0,
    baseline_depth: int = DEFAULT_BASELINE_DEPTH,
) -> dict[str, Any]:
    """Compare the latest statistics snapshot against its baseline.

    Args:
        session_factory: Sessionmaker callable.
        data_product_id: Product whose snapshots to read.
        table_name: Table within the product.
        sigma: z-score threshold above which a metric is "drifted".
        baseline_depth: How many prior snapshots form the baseline.

    Returns:
        ``{"measured": bool, "drifted": bool, "baseline_n": int,
        "metrics": [{"metric", "observed", "mean", "std", "z",
        "drifted"}]}`` — ``measured`` is ``False`` when there is no
        baseline yet (a single snapshot can't drift).
    """
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(DataProductStatistics)
                .where(
                    DataProductStatistics.data_product_id == data_product_id,
                    DataProductStatistics.table_name == table_name,
                )
                .order_by(DataProductStatistics.created_at.desc())
                .limit(baseline_depth + 1)
            ).all()
        )
        snapshots = [(r.row_count, r.shape_json) for r in rows]

    if len(snapshots) < 2:
        return {"measured": False, "drifted": False, "baseline_n": 0, "metrics": []}

    latest_rows, latest_shape = snapshots[0]
    baseline = snapshots[1:]
    metrics: list[dict[str, Any]] = []

    if latest_rows is not None:
        baseline_rows = [float(r) for r, _ in baseline if r is not None]
        if baseline_rows:
            z, mean, std = _z_score(float(latest_rows), baseline_rows)
            metrics.append(
                {
                    "metric": "row_count",
                    "observed": float(latest_rows),
                    "mean": mean,
                    "std": std,
                    "z": z if math.isfinite(z) else None,
                    "drifted": z > sigma,
                }
            )

    latest_ratios = _null_ratios(latest_shape, latest_rows)
    baseline_ratios: dict[str, list[float]] = {}
    for r, shape in baseline:
        for col, ratio in _null_ratios(shape, r).items():
            baseline_ratios.setdefault(col, []).append(ratio)
    for col, observed in latest_ratios.items():
        series = baseline_ratios.get(col, [])
        if not series:
            continue
        z, mean, std = _z_score(observed, series)
        metrics.append(
            {
                "metric": f"null_ratio:{col}",
                "observed": observed,
                "mean": mean,
                "std": std,
                "z": z if math.isfinite(z) else None,
                "drifted": z > sigma,
            }
        )

    return {
        "measured": True,
        "drifted": any(m["drifted"] for m in metrics),
        "baseline_n": len(baseline),
        "metrics": metrics,
    }


def max_drift_sigma(drift: dict[str, Any]) -> float:
    """Return the largest finite z-score in a drift result, or 0.0.

    Used by the SLO evaluator to compare observed drift against a
    declared ``statistical_shape`` ceiling.
    """
    zs = [m["z"] for m in drift.get("metrics", []) if isinstance(m.get("z"), int | float)]
    return max(zs) if zs else 0.0
