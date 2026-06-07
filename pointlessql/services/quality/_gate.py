"""Pre-write quality gate — pure policy decision.

Mirrors the schema-versioning enforcer's off/warn/block shape: given a
product's overall quality score and a threshold, decide whether a write may
proceed.  ``off`` is a no-op, ``warn`` records the breach but allows the
write, ``block`` raises :class:`QualityGateError`.

Pure: it makes the decision from the score + mode + threshold.  Wiring it
onto the before-write hook chain (so a low-scoring product blocks new writes)
is deliberately a follow-up — auto-enrolling every write into a quality gate
is a behavioural change that warrants its own enablement step rather than
riding in with the scoring backbone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

QualityGateMode = Literal["off", "warn", "block"]

_DEFAULT_THRESHOLD = 60.0


class QualityGateError(PermissionError):
    """Raised in ``block`` mode when a product's quality score is too low."""


@dataclass(frozen=True)
class GateOutcome:
    """The result of evaluating the quality gate.

    Attributes:
        mode: The gate mode that was applied.
        overall_score: The product's overall quality score.
        threshold: The minimum score the gate requires.
        passed: Whether the score met the threshold.
        blocked: Whether the write was blocked (``block`` mode + failed).
    """

    mode: QualityGateMode
    overall_score: float
    threshold: float
    passed: bool
    blocked: bool


def evaluate_gate(
    overall_score: float,
    *,
    mode: QualityGateMode = "warn",
    threshold: float = _DEFAULT_THRESHOLD,
) -> GateOutcome:
    """Decide whether a write may proceed given the product's quality score.

    Args:
        overall_score: The product's overall quality score (``0``–``100``).
        mode: ``off`` (allow), ``warn`` (allow, record), or ``block``.
        threshold: Minimum score required to pass.

    Returns:
        A :class:`GateOutcome` describing the decision.

    Raises:
        QualityGateError: In ``block`` mode when the score is below
            *threshold*.
    """
    passed = overall_score >= threshold
    if mode == "off":
        return GateOutcome(mode, overall_score, threshold, passed=True, blocked=False)
    if passed:
        return GateOutcome(mode, overall_score, threshold, passed=True, blocked=False)
    if mode == "block":
        raise QualityGateError(
            f"quality gate (block): score {overall_score:.1f} is below the required {threshold:.1f}"
        )
    return GateOutcome(mode, overall_score, threshold, passed=False, blocked=False)
