"""Bitemporal-convention service layer.

Re-exports the processing-time injector + the effective-policy resolver
+ the event-time validator so callers do
``from pointlessql.services import bitemporal`` without reaching into
the private sub-modules.
"""

from __future__ import annotations

from pointlessql.services.bitemporal._policy import (
    EffectiveBitemporal,
    effective_policy,
    set_product_policy,
)
from pointlessql.services.bitemporal._stamp import inject_processing_time
from pointlessql.services.bitemporal._validate import (
    BitemporalRequirementError,
    validate_event_time_column,
)

__all__ = [
    "BitemporalRequirementError",
    "EffectiveBitemporal",
    "effective_policy",
    "inject_processing_time",
    "set_product_policy",
    "validate_event_time_column",
]
