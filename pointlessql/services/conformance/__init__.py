"""Medallion conformance checks — Sprint 13.5.4 passive surface.

The run-detail view (:mod:`pointlessql.api.runs_routes`) calls
:func:`check_tables_touched` for each ``tables_touched`` entry on
an agent run and surfaces the resulting findings as warning
badges.  No enforcement: the goal is visibility — operators see
that bronze.x is missing audit columns and decide what to do
about it.  Phase 15+ may convert selected checks into shoreguard
policies if that signal materialises.

Layer inference is lexical (schema-name match against the
configured layer names).  When a schema name doesn't match any
layer the table is silently passed; an explicit ``layer`` UC
tag (Sprint 13.5.1's ``layer_tag_key``) is the future hook for
overriding the schema-name heuristic, but the soyuz-catalog
generated client doesn't surface tags directly yet — schema-name
match is the MVP.
"""

from __future__ import annotations

from pointlessql.services.conformance._checks import (
    ConformanceFinding,
    check_table_against_layer,
    infer_layer_from_full_name,
)

__all__ = [
    "ConformanceFinding",
    "check_table_against_layer",
    "infer_layer_from_full_name",
]
