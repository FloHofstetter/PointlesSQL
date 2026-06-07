"""Per-product quality scorecard — pure weighted aggregation.

Rolls the quality signals that already exist for a data product — contract
tests, SLO verdicts, statistical drift, and freshness — into one 0–100 score
across four dimensions, with the per-dimension breakdown and an explicit
*reasoning* string so a steward can see how the number was reached.

The function is pure: it takes the already-computed component metrics and
returns the scorecard.  Gathering those metrics from the DB (contract result
ledger, SLO evaluator, drift, freshness scanner) and persisting the
scorecard are the caller's job — kept out of here so the scoring is trivially
testable and the weighting is auditable in one place.
"""

from __future__ import annotations

from dataclasses import dataclass

# Dimension weights (sum to 1.0).  Correctness (do contracts hold) is
# weighted highest; timeliness lowest because freshness is already its own
# first-class SLO surface.
_WEIGHTS = {
    "correctness": 0.40,
    "reliability": 0.30,
    "stability": 0.20,
    "timeliness": 0.10,
}

# Drift sigma at/above which the stability dimension scores zero.
_DRIFT_SIGMA_FLOOR = 4.0


@dataclass(frozen=True)
class ScorecardResult:
    """A computed quality scorecard for one data product.

    Attributes:
        overall: Weighted overall score in ``[0, 100]``.
        dimensions: Per-dimension scores in ``[0, 100]``
            (correctness / reliability / stability / timeliness).
        reasoning: Human-readable note on how the score was derived.
    """

    overall: float
    dimensions: dict[str, float]
    reasoning: str


def _clamp(value: float) -> float:
    """Clamp a score to ``[0.0, 100.0]``."""
    return max(0.0, min(100.0, value))


def compute_scorecard(
    *,
    contract_pass_rate: float | None,
    slo_pass_rate: float | None,
    max_drift_sigma: float | None,
    freshness_ok: bool | None,
) -> ScorecardResult:
    """Compute the weighted quality scorecard from component metrics.

    Each component may be ``None`` (not measured); a missing dimension is
    treated neutrally (scored 100 and noted) so a product with no contract
    tests is not penalised for a signal it never opted into.

    Args:
        contract_pass_rate: Fraction of latest contract tests passing
            (``0.0``–``1.0``), or ``None`` if none are declared.
        slo_pass_rate: Fraction of SLOs met (``0.0``–``1.0``), or ``None``.
        max_drift_sigma: The largest drift z-score across monitored
            metrics, or ``None`` if drift is not measured.
        freshness_ok: Whether the freshness SLA is currently met, or
            ``None`` if no freshness SLA is declared.

    Returns:
        A :class:`ScorecardResult`.
    """
    notes: list[str] = []

    if contract_pass_rate is None:
        correctness = 100.0
        notes.append("correctness: no contract tests (neutral)")
    else:
        correctness = _clamp(contract_pass_rate * 100.0)
        notes.append(f"correctness: {contract_pass_rate:.0%} contracts pass")

    if slo_pass_rate is None:
        reliability = 100.0
        notes.append("reliability: no SLOs (neutral)")
    else:
        reliability = _clamp(slo_pass_rate * 100.0)
        notes.append(f"reliability: {slo_pass_rate:.0%} SLOs met")

    if max_drift_sigma is None:
        stability = 100.0
        notes.append("stability: no drift signal (neutral)")
    else:
        stability = _clamp(
            100.0 * (1.0 - min(max_drift_sigma, _DRIFT_SIGMA_FLOOR) / _DRIFT_SIGMA_FLOOR)
        )
        notes.append(f"stability: max drift {max_drift_sigma:.1f}σ")

    if freshness_ok is None:
        timeliness = 100.0
        notes.append("timeliness: no freshness SLA (neutral)")
    else:
        timeliness = 100.0 if freshness_ok else 0.0
        notes.append(f"timeliness: freshness {'met' if freshness_ok else 'breached'}")

    dimensions = {
        "correctness": round(correctness, 1),
        "reliability": round(reliability, 1),
        "stability": round(stability, 1),
        "timeliness": round(timeliness, 1),
    }
    overall = round(sum(dimensions[name] * weight for name, weight in _WEIGHTS.items()), 1)
    return ScorecardResult(overall=overall, dimensions=dimensions, reasoning="; ".join(notes))
