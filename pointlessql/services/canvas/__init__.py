"""Phase 85.1 — Dataflow canvas service layer.

The canvas is a deliberately-bounded prototype: a single linear
pipeline of typed nodes that translates to a short PQL script.
The 5+1 node kinds match the roadmap's spike scope (Read DP,
Filter, Join, Aggregate, Write DP, Run Model) plus a Group-By
helper because aggregation without an explicit grouping spec
would be too constrained to demonstrate the concept.

Public surface is just :func:`compile_nodes` — given an ordered
list of node dicts, return either ``(code, errors=[])`` or
``(code="", errors=[...])`` so the route layer can present errors
inline without separate "validate" + "compile" round-trips.
"""

from __future__ import annotations

from pointlessql.services.canvas._compiler import (
    SUPPORTED_NODE_KINDS,
    compile_nodes,
)

__all__ = ["SUPPORTED_NODE_KINDS", "compile_nodes"]
