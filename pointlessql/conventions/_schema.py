"""Pydantic models for the Medallion conventions config.

The two models are deliberately small — :class:`LayerConvention`
captures one layer's contract (name + required audit columns +
short prose hint), :class:`ConventionsConfig` aggregates the
ordered list of layers plus the UC tag-key under which each
table advertises its layer.

Pydantic is used (not dataclasses) so YAML parsing in
:mod:`pointlessql.conventions._loader` can validate user
overrides at load time and surface field-level errors instead
of crashing later inside the merge/autoload primitives.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LayerConvention(BaseModel):
    """One Medallion layer's contract.

    A layer has a stable ``name`` (used as the catalog-side schema
    prefix and as the UC-tag value), a one-line ``description`` for
    surfacing in agent system prompts, and a ``required_audit_columns``
    list that the conformance check and the autoload primitive both
    consult.

    The list ordering on bronze (``_ingested_at``, ``_source_file``,
    ``_source_system``) is meaningful — autoload appends the columns
    in this order so the on-disk Delta schema is stable across runs
    and across agents.

    ``name`` is the layer identifier (used both as the UC tag value
    and as a schema-name prefix convention); ``description`` is the
    one-sentence prose contract surfaced verbatim to agents via the
    ``pql_conventions()`` tool; ``required_audit_columns`` is the
    (possibly empty) set of audit columns the layer must carry.
    Empty means no audit-column contract — the default for
    silver/gold.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    required_audit_columns: tuple[str, ...] = ()


class ConventionsConfig(BaseModel):
    """Top-level Medallion conventions.

    The ``layers`` list is ordered bronze → silver → gold (default)
    so consumers that iterate it process raw → conformed → curated
    in the natural reading direction.  ``layer_tag_key`` is the UC
    tag key under which a table declares its layer (``layer=bronze``,
    etc.) — kept as a single string field so an operator can rename
    it via ``pointlessql.yaml`` without restructuring the model.

    The model is frozen so callers can rely on the parsed config
    being immutable for the lifetime of the process.

    ``layers`` is an ordered tuple of :class:`LayerConvention`
    (bronze → silver → gold by default); ``layer_tag_key`` is the
    UC-tag key under which each table declares its layer (default
    ``"layer"``).
    """

    model_config = ConfigDict(frozen=True)

    layers: tuple[LayerConvention, ...] = Field(default_factory=tuple)
    layer_tag_key: str = "layer"

    def get_layer(self, name: str) -> LayerConvention | None:
        """Return the named layer or ``None``.

        Used by the conformance check and the autoload primitive when
        translating a target-table name (or its UC tag value) into
        the audit-column contract for that layer.

        Args:
            name: Layer name, case-sensitive.

        Returns:
            LayerConvention | None: Matching layer, or ``None`` if
                this config doesn't define a layer by that name.
        """
        for layer in self.layers:
            if layer.name == name:
                return layer
        return None
