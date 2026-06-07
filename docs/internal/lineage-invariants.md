---
title: "Lineage correctness invariants"
audience: contributor
---

# Lineage correctness invariants

The hard properties row/column/value lineage must satisfy for **every**
lineage-bearing PQL operation, independent of operator or example. Each
invariant has a pure checker in
[`services/lineage/verify/_invariants.py`](../../pointlessql/services/lineage/verify/_invariants.py)
— a function `(facts) -> list[Violation]` with no I/O — so the property
suite and the golden corpus both verify the same definition.

The checkers operate on an `OperationFacts` value (a pure snapshot of one
operation's inputs, outputs and recorded lineage rows), not on the live DB,
so they are unit-testable and reusable from Hypothesis-generated pipelines,
the golden corpus, and (adapted) real recorded rows.

## Vocabulary

- **`_lineage_row_id`** — the magic column (`LINEAGE_ROW_ID_COLUMN`) that
  carries a row's identity. Minted on bronze autoload, propagated forward.
- **target id synthesis** — for a row written from a source row,
  `target_row_id = SHA-256(f"{source_row_id}:{target_table}")`
  (`synth_target_row_id`). Deterministic and stable across re-runs.
- **lineage-bearing operation** — one whose source carried
  `_lineage_row_id`; only these owe row edges.

## Invariants

### INV-1 — Row-edge closure
Every output row of a lineage-bearing write carries a `_lineage_row_id` and
has at least one `LineageRowEdge` back to a source row — **unless** that
source row is recorded in the `LineageRowReject` ledger. A lineage-bearing
operation that produces output rows but records **zero** edges (and no
rejects) is the 15.8 failure mode (a SELECT that dropped `_lineage_row_id`)
and is a violation, not a silent gap.

Checker: `check_row_edge_closure`.

### INV-2 — Target-id determinism
Every recorded `LineageRowEdge` satisfies
`target_row_id == synth_target_row_id(source_row_id, target_table)`. A
mismatch means the propagation diverged from the canonical synthesis (a
broken merge path, a stale id, a hand-rolled hash).

Checker: `check_target_id_synthesis`.

### INV-3 — Edge source/target validity
Every edge's `source_row_id` is one of the operation's input row ids, and
every edge's `target_row_id` is one of the operation's output row ids. No
edge may reference a row that does not exist on either side.

Checker: `check_edge_endpoints`.

### INV-4 — Column-map coverage
Every non-constant output column has a `LineageColumnMap` row with a
traceable `transform_kind` (not `unknown_origin`). Constant / injected
columns are exempt only when explicitly marked `unknown_origin` with
`transform_detail` in `{"audit", "synth_target_row_id"}`, or are the
`_lineage_row_id` column itself.

Checker: `check_column_map_coverage`.

### INV-5 — Value-changes are real changes on real rows
Every `LineageValueChange` targets a row id that exists in the operation's
output, and records an **actual** change (`old_value != new_value`). A
recorded "change" where old equals new, or against an unknown row, means
the CDF pairing leaked a non-update.

Checker: `check_value_changes_real`.

### INV-6 — Reject-reason validity
Every `LineageRowReject.reason` is one of the allowed reasons
(`on_key_null`, `schema_mismatch`, `duplicate_in_source`,
`merge_predicate_excluded`, `other`, `expectation_failed`), and a rejected
source row does **not** also have an edge (a row is either kept or
rejected, never both).

Checker: `check_reject_reasons`.

## Aggregate

`verify_operation(facts)` runs every checker and returns the concatenated
violations — the single entry point the property suite, golden corpus and
CI marker call.
