"""Asset bundles: declarative jobs / pipelines / BI dashboards as YAML.

The bundle workflow mirrors data-product-as-code: author a YAML spec,
``plan`` it against the live metadata DB, ``apply`` it idempotently,
and ``export`` live state back into a spec.

* :mod:`_spec` — strict pydantic ``BundleSpec`` (extra=``forbid``)
  parses YAML or dict input.
* :mod:`_planner` — diffs each declared resource by identity (job
  name / pipeline slug / dashboard slug) into create / update /
  unchanged entries; never plans deletes, but reports unmanaged live
  resources as orphans.
* :mod:`_applier` — reconciles the spec via direct ORM upserts with
  per-resource error scoping.
* :mod:`_exporter` — snapshots live state into a round-trippable spec.
"""

from __future__ import annotations

from pointlessql.services.asset_bundles._applier import (
    BundleApplyOutcome,
    ResourceResult,
    apply_bundle,
)
from pointlessql.services.asset_bundles._exporter import (
    bundle_to_yaml,
    export_bundle,
)
from pointlessql.services.asset_bundles._planner import (
    BundlePlan,
    OrphanEntry,
    PlanEntry,
    plan_bundle,
)
from pointlessql.services.asset_bundles._spec import (
    BundleInfo,
    BundleSpec,
    DashboardParamSpec,
    DashboardSpec,
    DatasetSpec,
    ExpectationSpec,
    JobSpec,
    JobTaskSpec,
    JobTriggerSpec,
    PipelineSpec,
    WidgetSpec,
    parse_bundle,
)

__all__ = [
    "BundleApplyOutcome",
    "BundleInfo",
    "BundlePlan",
    "BundleSpec",
    "DashboardParamSpec",
    "DashboardSpec",
    "DatasetSpec",
    "ExpectationSpec",
    "JobSpec",
    "JobTaskSpec",
    "JobTriggerSpec",
    "OrphanEntry",
    "PipelineSpec",
    "PlanEntry",
    "ResourceResult",
    "WidgetSpec",
    "apply_bundle",
    "bundle_to_yaml",
    "export_bundle",
    "parse_bundle",
    "plan_bundle",
]
