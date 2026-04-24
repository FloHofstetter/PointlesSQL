"""Built-in Medallion conventions.

The defaults match the Phase 13.5 ROADMAP narrative verbatim so
the prose contract in ``docs/data-layers.md``, the YAML example
file at the repo root, and the agent-facing tool surface from
Sprint 13.7 all reference one source of truth.

Bronze carries the audit-column contract because that is where
provenance lives — silver and gold inherit it by lineage.  The
prose hints are deliberately one-sentence each so they fit
inside an agent system prompt without ballooning the token
budget.
"""

from __future__ import annotations

from pointlessql.conventions._schema import ConventionsConfig, LayerConvention

_BRONZE = LayerConvention(
    name="bronze",
    description=(
        "Raw fidelity from the source, append-only, every row carries "
        "audit columns so provenance is recoverable months later."
    ),
    required_audit_columns=("_ingested_at", "_source_file", "_source_system"),
)

_SILVER = LayerConvention(
    name="silver",
    description=(
        "Deduplicated, typed, conformed keys — the cleanest representation "
        "of the source domain after the bronze noise has been removed."
    ),
    required_audit_columns=(),
)

_GOLD = LayerConvention(
    name="gold",
    description=(
        "Business facts, aggregated and star-schema-ready — the layer "
        "downstream BI tools and ML features read from."
    ),
    required_audit_columns=(),
)

DEFAULT_CONVENTIONS: ConventionsConfig = ConventionsConfig(
    layers=(_BRONZE, _SILVER, _GOLD),
    layer_tag_key="layer",
)
