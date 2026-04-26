"""Medallion layer conventions and ``pointlessql.yaml`` loader.

The *opinionated primitives* that turn an agent-authored Delta
write into a real Medallion lakehouse instead of three ad-hoc
tables.  The defaults encode the bronze (raw + audit-columns +
append-only) / silver (deduped + typed + conformed-keys) / gold
(business facts + star-schema-ready) contract; a repo-level
``pointlessql.yaml`` can override layer names, audit-column
names, or UC tag-key without code changes.

This package ships the data + parser only.  The
``hermes-plugin-pointlessql`` surfaces :func:`load_conventions`
to agents as a ``pql_conventions()`` tool that drops the parsed
config + the prose contract from ``docs/data-layers.md`` into
the system prompt.

The decision behind the DuckDB-first compute opinion this
package codifies lives in ``docs/adr/0002-duckdb-first.md``.
"""

from __future__ import annotations

from pointlessql.conventions._defaults import DEFAULT_CONVENTIONS
from pointlessql.conventions._loader import load_conventions
from pointlessql.conventions._schema import ConventionsConfig, LayerConvention

__all__ = [
    "ConventionsConfig",
    "DEFAULT_CONVENTIONS",
    "LayerConvention",
    "load_conventions",
]
