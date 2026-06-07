"""Data-quality depth: expectations, scorecards, and the pre-write gate.

Re-export facade for the quality service.  Three pure layers build on the
existing contract-test / SLO / drift signals:

* extended **expectations** — six new assertion kinds;
* a per-product **scorecard** — weighted roll-up across correctness /
  reliability / stability / timeliness;
* a pre-write **gate** — off / warn / block on the overall score.

All three are pure compute (no DB, no soyuz).  Persisting scorecards,
wiring the new expectations into the live contract-test dispatcher (behind a
CHECK-constraint migration), registering the gate on the before-write hook,
anomaly emission, and the Quality UI tab are tracked follow-ups.
"""

from __future__ import annotations

from pointlessql.services.quality._expectations import (
    EXTENDED_ASSERTION_KINDS,
    EXTENDED_ASSERTIONS,
)
from pointlessql.services.quality._gate import (
    GateOutcome,
    QualityGateError,
    QualityGateMode,
    evaluate_gate,
)
from pointlessql.services.quality._scorecard import ScorecardResult, compute_scorecard

__all__ = [
    "EXTENDED_ASSERTIONS",
    "EXTENDED_ASSERTION_KINDS",
    "GateOutcome",
    "QualityGateError",
    "QualityGateMode",
    "ScorecardResult",
    "compute_scorecard",
    "evaluate_gate",
]
