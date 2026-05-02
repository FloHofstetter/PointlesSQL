"""Version-compare diff helpers for the model compare-view.

Three pure functions consumed by the
``/models/{full_name}/compare`` route to compute the diff between
two model-version MLflow contexts:

- :func:`compute_metric_diff` — joined metric table with absolute +
  relative deltas and a ``"better"|"worse"|"neutral"`` direction
  classification.
- :func:`params_diff` — added / removed / changed param keys.
- :func:`tags_diff` — same shape as :func:`params_diff` but for tags.

The metric direction heuristic uses substring rules that match
roughly 90% of common ML metric names.  Domain-specific overrides
are out of scope for ; a future enhancement could read a
per-metric direction map from the soyuz catalog row.
"""

from __future__ import annotations

from typing import Any

_LOWER_BETTER_TOKENS = ("loss", "error", "mse", "rmse", "mae", "cost")
_HIGHER_BETTER_TOKENS = (
    "accuracy",
    "acc",
    "f1",
    "auc",
    "recall",
    "precision",
    "score",
)


def _classify_metric(name: str) -> str:
    """Return ``'lower-better' | 'higher-better' | 'neutral'`` for a metric.

    Args:
        name: Raw MLflow metric name (case-insensitive matching).

    Returns:
        str: The polarity classification.  Names that contain
            any ``_LOWER_BETTER_TOKENS`` substring win regardless of
            secondary matches (so ``f1_loss`` is still
            ``lower-better``).
    """
    lowered = (name or "").lower()
    if any(tok in lowered for tok in _LOWER_BETTER_TOKENS):
        return "lower-better"
    if any(tok in lowered for tok in _HIGHER_BETTER_TOKENS):
        return "higher-better"
    return "neutral"


def _coerce_float(value: Any) -> float | None:
    """Best-effort numeric coercion; returns ``None`` for non-numeric."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_metric_diff(
    v1_mlflow: dict[str, Any], v2_mlflow: dict[str, Any]
) -> list[dict[str, Any]]:
    """Build the metric-by-metric diff table sorted alphabetically.

    Args:
        v1_mlflow: MLflow context for the first version (must contain
            a ``metrics`` dict; missing keys are tolerated).
        v2_mlflow: MLflow context for the second version.

    Returns:
        list[dict]: One entry per metric name. Each entry carries
            ``name``, ``v1``, ``v2``, ``delta_abs``, ``delta_pct``,
            ``classification``, and ``direction``. ``v1``/``v2`` are
            ``None`` when the metric is missing from that side.
    """
    m1: dict[str, Any] = dict(v1_mlflow.get("metrics") or {})
    m2: dict[str, Any] = dict(v2_mlflow.get("metrics") or {})
    names = sorted(set(m1) | set(m2))

    rows: list[dict[str, Any]] = []
    for name in names:
        v1 = _coerce_float(m1.get(name))
        v2 = _coerce_float(m2.get(name))
        classification = _classify_metric(name)
        delta_abs: float | None = None
        delta_pct: float | None = None
        direction = "neutral"
        if v1 is not None and v2 is not None:
            delta_abs = v2 - v1
            if v1 != 0:
                delta_pct = (v2 - v1) / abs(v1) * 100.0
            if classification == "lower-better":
                direction = "better" if v2 < v1 else ("worse" if v2 > v1 else "neutral")
            elif classification == "higher-better":
                direction = "better" if v2 > v1 else ("worse" if v2 < v1 else "neutral")
        rows.append(
            {
                "name": name,
                "v1": v1,
                "v2": v2,
                "delta_abs": delta_abs,
                "delta_pct": delta_pct,
                "classification": classification,
                "direction": direction,
            }
        )
    return rows


def _key_diff(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Return ``{added, removed, changed}`` for two flat dicts."""
    a_keys = set(a)
    b_keys = set(b)
    added = {k: b[k] for k in sorted(b_keys - a_keys)}
    removed = {k: a[k] for k in sorted(a_keys - b_keys)}
    changed: list[dict[str, Any]] = []
    for k in sorted(a_keys & b_keys):
        if a[k] != b[k]:
            changed.append({"name": k, "v1": a[k], "v2": b[k]})
    return {"added": added, "removed": removed, "changed": changed}


def params_diff(
    v1_params: dict[str, Any], v2_params: dict[str, Any]
) -> dict[str, Any]:
    """Return the added / removed / changed param keys."""
    return _key_diff(v1_params, v2_params)


def tags_diff(
    v1_tags: dict[str, Any], v2_tags: dict[str, Any]
) -> dict[str, Any]:
    """Return the added / removed / changed tag keys."""
    return _key_diff(v1_tags, v2_tags)
