"""Pydantic ``DataProductSpec`` — strict YAML-or-dict input.

``extra=forbid`` everywhere so typos in user-authored YAML surface as
validation errors rather than silently-ignored fields.  Field names
follow the discovery contract verbatim so the spec is round-trippable
against ``services/data_product_as_code._exporter``.
"""

from __future__ import annotations

from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class InputPortSpec(BaseModel):
    """One declared upstream source."""

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: str = Field(
        description="One of operational_system, upstream_product, external."
    )
    source_ref: str | None = None
    description: str | None = None


class OutputPortSpec(BaseModel):
    """One externally addressable port."""

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: str = Field(description="One of sql, file, event.")
    description: str | None = None
    format: str | None = None
    location: str | None = None
    identity_requirements: dict[str, Any] | None = None


class SloSpec(BaseModel):
    """One SLO declaration."""

    model_config = ConfigDict(extra="forbid")

    kind: str
    comparator: str = Field(default="lte", description="One of lte, gte, eq.")
    target_value: float | None = None
    table: str | None = None
    unit: str | None = None


class PolicySpec(BaseModel):
    """Inheritable governance fields on the product."""

    model_config = ConfigDict(extra="forbid")

    retention_days: int | None = None
    encryption_class: str | None = None
    residency_region: str | None = None
    consent_required: bool | None = None
    consent_basis: str | None = None
    consumption_enforcement: str | None = None
    iso8601_enforcement: str | None = None
    linked_policy_module_ids: list[int] | None = None
    breaking_change_policy: str | None = None
    max_cost_per_day: float | None = None
    max_queries_per_hour: int | None = None
    quota_enforcement: str | None = None


class EntitySpec(BaseModel):
    """One declared polysemic entity on the product."""

    model_config = ConfigDict(extra="forbid")

    name: str
    source_table: str
    primary_key_columns: list[str]
    description: str | None = None


class ContractTestSpec(BaseModel):
    """One declared contract assertion."""

    model_config = ConfigDict(extra="forbid")

    name: str
    assertion_kind: str
    assertion_spec: dict[str, Any]
    severity: str = "warn"
    enabled: bool = True


class FixtureSpec(BaseModel):
    """One synthetic fixture descriptor."""

    model_config = ConfigDict(extra="forbid")

    table_name: str
    generator_spec: list[dict[str, Any]]
    row_count: int = 100


class GlossaryBindingSpec(BaseModel):
    """One glossary-binding declaration."""

    model_config = ConfigDict(extra="forbid")

    term_slug: str
    column: str
    table: str | None = None


class DataProductSpec(BaseModel):
    """Top-level spec.  ``catalog`` + ``schema`` identify the product."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    name: str
    catalog: str
    schema: str  # type: ignore[assignment]
    domain: str | None = None
    lifecycle: str | None = None
    owner_email: str | None = None
    description: str | None = None
    input_ports: list[InputPortSpec] = Field(default_factory=list)
    output_ports: list[OutputPortSpec] = Field(default_factory=list)
    slos: list[SloSpec] = Field(default_factory=list)
    policies: PolicySpec | None = None
    contract_tests: list[ContractTestSpec] = Field(default_factory=list)
    fixtures: list[FixtureSpec] = Field(default_factory=list)
    entities: list[EntitySpec] = Field(default_factory=list)
    glossary_bindings: list[GlossaryBindingSpec] = Field(default_factory=list)

    @field_validator("catalog", "schema", "name")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("name / catalog / schema cannot be blank")
        return cleaned


def parse_spec(source: str | dict[str, Any]) -> DataProductSpec:
    """Return a validated :class:`DataProductSpec`.

    Args:
        source: YAML text or a pre-decoded dict.

    Raises:
        ValueError: On YAML parse error or pydantic validation error.
    """
    if isinstance(source, dict):
        return DataProductSpec.model_validate(source)
    try:
        decoded = yaml.safe_load(source)
    except yaml.YAMLError as exc:
        raise ValueError(f"yaml parse error: {exc}") from exc
    if not isinstance(decoded, dict):
        raise ValueError("spec must be a YAML mapping")
    return DataProductSpec.model_validate(decoded)
