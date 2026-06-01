# Overnight Hardening Marathon — run log

Autonomous hardening run started 2026-06-02. Lands as **Hardening Cluster (Phase 189+)**
on top of ROADMAP head Phase 188. One local commit per phase, full `pytest` green gate,
**no push** — left for Florian's morning review.

Baseline: `4131 passed, 14 skipped, 10 deselected` (243s).

Adaptation (recorded up front): the Explore scoping heuristic over-counted "untested"
services — e.g. `dp_canvas` is already saturated (~95 tests). So **Group A is run
coverage-guided**: each test phase does a real gap analysis (`pytest --cov` on the target
module) and fills genuine gaps rather than duplicating existing tests; saturated modules
are skipped in favour of genuinely low-coverage ones.

---

## Phase log

### Phase 0 — Re-baseline + commit canvas WIP
- Baseline suite green at 4131 passed / 14 skipped / 10 deselected.
- Reviewed canvas run-dock WIP: coherent, already documented in ROADMAP + CHANGELOG;
  pyproject bump clean rc252→rc254. Staged only tracked files (left scratch `.jpg`s untracked).
- Committed as Phase 0. Tree clean apart from scratch artifacts.

Generated a full `--cov` map up front (`/tmp/pql-cov.json`) and drive Group A from it.
ROADMAP/CHANGELOG churn is batched into a single Hardening-Cluster node at the closing
phase (rather than 20+ per-phase edits); this log is the per-phase record in the meantime.

### Phase 1 — pure-logic gap tests (suite 4131→4170, +39)
- `tests/test_output_rendering.py` (+27): `services/output_rendering.py` was 0% / zero test
  refs. Covers the full mime-bundle priority order (markdown>html>svg>png>jpeg>json>plain),
  the widget placeholder + model_id truncation, stream stdout/stderr, error traceback vs
  ename/evalue fallback, list-payload coercion, HTML-escaping, and the unknown-type fallbacks.
- `tests/test_aws_sigv4.py` (+12): `services/aws_sigv4.py` was 22% / zero test refs. Verifies
  the signature against an independent in-test re-derivation of the SigV4 algorithm (genuine
  cross-check), the empty-body SHA-256 external known-answer, determinism for a fixed clock,
  signature sensitivity to body/region, extra-header signing, and canonical-URI encoding.
- Committed.

### Phase 2 — lineage + conformance gap tests (suite 4170→4192, +22)
- `tests/test_lineage_graph_builder.py` (+6): `services/lineage/graph_builder.py` was 0%.
  Seeds row-edges + column-map through the app session factory and asserts node/edge
  aggregation, op-filter, NULL-source column annotation, row-only-edge fallback, and the
  stable node/edge ordering contract. Found the `op_name` CHECK-constraint enum the hard
  way (only the fixed `merge`/`sql`/`aggregate`/… set is allowed) — tests use valid names.
- `tests/test_lineage_pruner.py` (+4): `services/lineage/pruner.py` was 0%. Drives
  `prune_once` with a stand-in settings object: positive threshold deletes only old rows,
  `None`/`<=0` skip the axis, fresh rows report a zero count.
- `tests/test_conformance_checks.py` (+12): `services/conformance/_checks.py` was 28%.
  Full coverage of schema-name layer inference + bronze/silver/gold checks and the
  None/unknown-layer short-circuits. Pure functions, no DB.
- Committed.

### Phase 3 — pql time-travel + sql-statements retention (suite 4192→4206, +14)
- `tests/test_pql_time_travel.py` (+9): `pql/_time_travel.py` was 0%. Monkeypatches the
  catalog lookup + `deltalake.DeltaTable`; covers storage-location resolution (found /
  two-part-name / missing-table / no-location / connect-error), version + timestamp reads,
  delta-error propagation, and the naive-datetime guard. (Audit row self-skips with no
  `POINTLESSQL_AGENT_RUN_ID`, so no DB.)
- `tests/test_sql_statements_retention.py` (+5): `services/sql_statements/_retention.py` was
  38%. Window prune by `submitted_at`, zero/negative-retention no-ops, idempotent executor
  registration that preserves an existing registry.
- Noted in passing: `external_write_scanner.py:65` uses parens-free multi-exception `except`
  (PEP 758, valid on the project's Python 3.14) — looked like a Py2 bug but imports fine.
- Committed.

### Phase 4 — external write scanner (suite 4206→4220, +14)
- `tests/test_external_write_scanner.py` (+14): `services/external_write_scanner.py` was 18%.
  Pure `_parse_commit_timestamp`; `scan_table` against a fake `deltalake.DeltaTable`
  (unattributed insert, attributed-skip via seeded `agent_run_operations`, idempotent
  re-scan, history-read error, non-int version skip); and the `unattributed_writes` CRUD
  helpers (list/ack/count).
- Coedit-bus assessed + skipped: its 112 missing lines are PG LISTEN/NOTIFY async runtime
  paths (constructor rejects SQLite), not meaningfully unit-testable here.
- Committed.

### Phase 5 — PQL merge strategies + stats (suite 4220→4231, +11)
- `tests/test_pql_merge.py` (+11): `pql/_merge/_stats.py` (was 48%) pure row-count rollups
  + JSON-safe coercion; `pql/_merge/_strategies.py` (was 45%) `_augment_for_scd2` column
  shaping plus real temp-Delta round-trips for `_do_upsert` (update+insert) and `_do_scd2`
  (close open row + append new current). deltalake is a core dep, so the round-trips run live.
- Committed.

### Phase 6 — UC models mixin + business-time read (suite 4231→4245, +14)
- `tests/test_unitycatalog_models.py` (+10): `services/unitycatalog/_models.py` (was 45%).
  Hosts `ModelsMixin` on a stub and monkeypatches each generated endpoint's `.asyncio`
  coroutine; covers list/get for registered models + versions (type guards, `.to_dict()`
  projection, empty/None fallbacks) and the `update` patch-body construction.
- `tests/test_pql_read_event_time.py` (+4): `pql/_pql_read.py` (was 48%)
  `table_as_of_event_time` — the `<=` business-time filter, settings-default column
  resolution, and the missing-column / non-frame guards via a `table`-overriding stub.
- Committed.

### Phase 7 — pql.aggregate pure helpers (suite 4245→4261, +16)
- `tests/test_pql_aggregate.py` (+16): `pql/_aggregate.py` (was 59%). Fail-fast validation
  (empty group_by / source_fqn / aggs, non-DataFrame, missing column); `_build_aggregate_frame`
  groupby + deterministic `_lineage_row_id` stamping + fan-in source-id collection; and the
  `_build_aggregate_column_edges` branch matrix (identity / derived / aggregate / unknown_origin
  + the synth row-id edge). The catalog/engine write path is left to integration tests.
- Committed.

### Phase 8 — data-product statistics hook (suite 4261→4266, +5)
- `tests/test_agent_runs_statistics.py` (+5): `services/agent_runs/operations/_statistics.py`
  (was 62%). Pure `_shape_from_cache` distiller (+ malformed-entry skip); the no-op
  short-circuit; a plain snapshot insert; and the cache-upgrade branch that swaps in the
  fuller shape via a monkeypatched `table_stats.read_cached`.
- Closes Group A (test coverage). Net Group A: ~113 new tests, suite 4131→4266, all green.
  The pure-logic / SQLite-testable gaps surfaced by the coverage map are now covered;
  remaining low-coverage modules are PG-only or live-integration paths (logged where skipped).
- Committed.

## Group B — refactors (big-file splits, behind the Group-A nets)

### Phase 10 — split `services/dp_canvas/_blocks.py` (1546 → package)
- The 1546-line single-file block registry is now a `_blocks/` package: `_base.py` (180:
  `BlockSpec`/`CompiledBlock`, `BLOCK_REGISTRY`, the two dispatch tables, public
  `compile_block`/`infer_block`) + five cohesive category modules — `_io` (213),
  `_relational` (454), `_reshape` (444), `_columns` (254), `_sql` (168) — plus `__init__`
  (40) re-exporting the exact prior public surface. Each category module registers its
  block types into the dispatch tables at import time; `__init__` imports them for the
  side effect. Largest file 1546 → 454.
- Old `_blocks.py` deleted (no shim). Bodies moved verbatim via line-range extraction;
  inline `_register(...)` calls untouched. ruff/pyright(strict, 0 err)/pydoclint clean;
  fixed a stale `BlockSpec` docstring (documented `compile`/`infer_output` attrs that the
  dataclass never had — pydoclint DOC602/603) and dropped a phase-ref from the docstring.
  Full suite 4266 (unchanged — pure refactor). Committed.
