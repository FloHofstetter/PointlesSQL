"""Data-Product-as-Code: declarative spec + planner + applier + exporter.

The book wants products versioned as YAML in Git, reconciled into the
metadata DB via a plan → apply flow.  PointlesSQL already has a
:class:`DataProductYamlDraft` row tracking authored drafts on disk;
this package adds the *reconciler* on top of it:

* :mod:`_spec` — strict pydantic ``DataProductSpec`` (extra=``forbid``)
  parses YAML or dict input.
* :mod:`_planner` — computes the additive / modification / removal
  ops between a spec and the live DB state.
* :mod:`_applier` — runs the plan idempotently, reusing the existing
  CRUDs.
* :mod:`_exporter` — snapshots the live DB state into a spec.
"""

from __future__ import annotations

from pointlessql.services.data_product_as_code._applier import (
    ApplyOutcome,
    apply_plan,
)
from pointlessql.services.data_product_as_code._exporter import (
    export_data_product,
)
from pointlessql.services.data_product_as_code._planner import (
    Op,
    Plan,
    plan_spec,
)
from pointlessql.services.data_product_as_code._spec import (
    DataProductSpec,
    EntitySpec,
    InputPortSpec,
    OutputPortSpec,
    PolicySpec,
    SloSpec,
    parse_spec,
)

__all__ = [
    "ApplyOutcome",
    "DataProductSpec",
    "EntitySpec",
    "InputPortSpec",
    "Op",
    "OutputPortSpec",
    "Plan",
    "PolicySpec",
    "SloSpec",
    "apply_plan",
    "export_data_product",
    "parse_spec",
    "plan_spec",
]
