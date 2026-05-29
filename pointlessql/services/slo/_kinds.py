"""SLO-kind metadata: labels, units, comparators, measurability.

Re-exports the kind tuples from the model and adds a per-kind metadata
map the UI + the evaluator share.  ``measurable`` marks the kinds the
platform can compute a verdict for from data it already holds; the rest
are honest declarations surfaced in the discovery contract.
"""

from __future__ import annotations

from typing import Any

from pointlessql.models import MEASURABLE_SLO_KINDS, SLO_KINDS

__all__ = ["KIND_META", "MEASURABLE_SLO_KINDS", "SLO_KINDS"]

#: Per-kind UI/evaluator metadata.  ``comparator`` is the default the
#: declare form pre-selects; ``measurable`` mirrors
#: :data:`MEASURABLE_SLO_KINDS`.
KIND_META: dict[str, dict[str, Any]] = {
    "freshness": {
        "label": "Freshness",
        "unit": "minutes",
        "comparator": "lte",
        "measurable": True,
        "help": "Max age of the latest write before the product is stale.",
    },
    "timeliness": {
        "label": "Timeliness",
        "unit": "minutes",
        "comparator": "lte",
        "measurable": False,
        "help": "Max lag from event time to availability (declared).",
    },
    "completeness": {
        "label": "Completeness",
        "unit": "percent",
        "comparator": "gte",
        "measurable": True,
        "help": "Min fraction of non-null values across the table.",
    },
    "volume": {
        "label": "Volume",
        "unit": "rows",
        "comparator": "gte",
        "measurable": True,
        "help": "Min row count expected in the latest snapshot.",
    },
    "statistical_shape": {
        "label": "Statistical shape",
        "unit": "sigma",
        "comparator": "lte",
        "measurable": True,
        "help": "Max drift (z-score) of volume/null ratios vs. baseline.",
    },
    "lineage": {
        "label": "Lineage coverage",
        "unit": "percent",
        "comparator": "gte",
        "measurable": True,
        "help": "Min fraction of upstreams declared as input ports.",
    },
    "precision_accuracy": {
        "label": "Precision / accuracy",
        "unit": "percent",
        "comparator": "gte",
        "measurable": False,
        "help": "Correctness vs. ground truth (declared — needs an oracle).",
    },
    "availability": {
        "label": "Availability",
        "unit": "percent",
        "comparator": "gte",
        "measurable": False,
        "help": "Uptime of the product's access ports (declared).",
    },
    "performance": {
        "label": "Performance",
        "unit": "ms",
        "comparator": "lte",
        "measurable": False,
        "help": "Max query latency at the output port (declared).",
    },
}
