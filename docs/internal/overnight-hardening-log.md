# Overnight Hardening Marathon — run log

Autonomous hardening run started 2026-06-02. Lands as **Hardening Cluster (Phase 189+)**
on top of ROADMAP head Phase 188. One local commit per phase, full `pytest` green gate,
**no push** — left for Florian's morning review.

Baseline: `4131 passed, 14 skipped, 10 deselected` (243s).

---

## ⭐ For Florian's review (morning summary)

Everything below is **committed locally, not pushed** — review and `git push` when happy.
Tree is clean apart from the untracked scratch `.jpg`s (left alone deliberately).

**What landed (all four focus areas):**
- **Test coverage** — ~290 new tests across previously-thin pure-logic / mockable modules;
  full suite 4131 → ~4410, still green. Each batch was coverage-map-guided (two `--cov`
  passes) to hit genuine gaps, not duplicate existing tests. Modules covered: output_rendering,
  aws_sigv4, lineage (graph-builder / pruner / row-edge store), conformance, pql (time-travel /
  merge / aggregate / pql_read / embedders), sql-statements retention, external-write scanner,
  UC mixins (models / catalogs / metadata), agent-run stats, social target-resolver, Cedar
  policy CRUD, contract-test CRUD, audit-sink decoders + soyuz reader, canvas block modules
  (columns / reshape), visual SQL builder, editor-chat factory.
- **Refactor** — `services/dp_canvas/_blocks.py` (1546 lines, the largest non-alembic file)
  split into a `_blocks/` package (`_base` + 5 category modules, largest 454); public surface
  unchanged, ruff/pyright(strict)/pydoclint clean.
- **Type-debt** — `db.py` engine listeners re-typed with `DBAPIConnection` (9 → 2 ignores,
  a precision gain, not `Any`-erasure).
- **A11y** — global `prefers-reduced-motion` catch-all (WCAG 2.3.3).

**Needs a human eye (best-effort calls I made):**
- **`dependencies.py` split → reverted.** Splitting a test-monkeypatched module changes
  patch-target semantics (27 tests went red). Reverted cleanly. Only pure-logic, non-patched
  modules are split-safe.
- **`citations.py` split → not taken.** Verified monkeypatch-safe, but its good split needs a
  central-list→per-module-registration conversion (fiddly, real transcription risk) for modest
  marginal value vs. `_blocks`. Left as a clean candidate for a supervised pass.
- **Broad-except audit + broader type-debt → assessed as low-yield** (codebase already
  disciplined + ruff-clean; remaining ignores are justified third-party-stub boundaries with no
  stale-ignore tooling to harvest). No churn manufactured.
- The Phase-0 commit bundled your in-progress **canvas run-dock** work (it was coherent and
  already documented in ROADMAP/CHANGELOG).

Per-phase detail follows below.

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

### Phase 12 (dependencies.py split) — ATTEMPTED, REVERTED
- Split `api/dependencies.py` (872) into a `dependencies/` package (`_pagination` /
  `_principal` / `_roles` / `_workspace` / `_http`), re-exporting all 22 public names.
  ruff/pyright(0 err)/pydoclint clean, app built, all names importable.
- BUT the full gate went red (tests that `monkeypatch.setattr("pointlessql.api.dependencies.
  <name>", …)`): splitting a module moves each cross-reference into the submodule's own
  namespace, so patching the package re-export no longer affects the caller. `dependencies`
  is monkeypatched by the suite, so the split changes patch-target semantics. Reverted
  cleanly (best-effort posture) rather than rewrite test patch targets unattended.
- **Lesson recorded:** only pure-logic modules (no test monkeypatching of their internals)
  are safe to split. `_blocks` qualified; `dependencies` / auth / route modules do not.

## Group C — type-debt (assessed low-yield in this mature codebase; precise-typing wins only)

### Phase 15 — db.py precise DBAPI typing (9 → 2 ignores)
- `db.py` engine-init event listeners typed `dbapi_conn: object` and carried 7
  `# type: ignore[union-attr]` on the `.cursor()` calls. Re-typed to
  `sqlalchemy.engine.interfaces.DBAPIConnection` (a Protocol that types `.cursor()`),
  removing all 7 ignores — a genuine precision gain, not an `Any`-erasure. Only the 2
  `reportUnusedFunction` ignores (inherent to the `@event.listens_for` decorator pattern)
  remain. Annotation-only (zero runtime change). ruff/pyright clean.
- Broader type-debt assessed and largely left alone: the remaining ignores cluster at
  third-party stub boundaries (FastAPI internals, pycrdt C-ext) where removal needs `Any`
  (no precision gain), and the project enables no stale-ignore tooling
  (`reportUnnecessaryTypeIgnore` / `RUF100` off), so there is no automated dead-suppression
  to harvest. Consistent with the known "third-party stubs are the bottleneck" finding.

## Group D — a11y / UX

### Phase 18 — global reduced-motion catch-all
- `frontend/css/base.css` only honoured `prefers-reduced-motion` for two named animations
  (badge pulse, root view-transition); the dozens of `transition:` / `animation:`
  declarations across the component stylesheets ignored it. Added the WCAG 2.3.3 standard
  global catch-all (`*,*::before,*::after { animation/transition-duration: 0.01ms !important }`
  under the reduce query) so every motion in the app is neutralised for users who request it,
  without each component repeating the media query. Pure CSS, asset version bumped
  rc254→rc255. (No `x-data`/Alpine/modal markup touched, so no browser replay gate required.)
- Assessed but left alone: 5 `outline:none/0` sites — they may pair with custom focus styling,
  so blind removal could regress; not safe to change unattended without browser verification.
  `:focus-visible` rules already exist in base/list_table/canvas_shared.

## Group A (continued) — more coverage

### UC catalog + metadata wrappers (+20 tests)
- `tests/test_unitycatalog_catalogs.py` (+10) and `tests/test_unitycatalog_metadata.py` (+10):
  `services/unitycatalog/_catalogs.py` (was 54%) and `_metadata.py` (was 53%). The conftest
  mocks the whole `UnityCatalogClient`, so these wrappers' real logic (type guards, `.to_dict()`
  projection, empty-body fallbacks, request-body construction, securable-type enum coercion,
  force/full-name forwarding) was unexercised. Same proven pattern as the models mixin: host the
  mixin on a stub, monkeypatch each generated endpoint's `.asyncio`. Committed.

### Row-level lineage edge store (+7 tests)
- `tests/test_lineage_rows.py`: `services/lineage/rows.py` (was 60%). Covers `record_edges`
  no-op guards (empty / length-mismatched id lists), a successful aligned-pair insert
  (workspace resolved from a seeded op), the predecessor / descendant lookups, and the
  per-op edge counter (incl. empty-input). Committed.

### Social target resolver (+6 tests)
- `tests/test_social_target_resolver.py`: `services/social/_target_resolver.py` (was 62%).
  `get_or_create_target` kind/parity validation (unknown kind, dp↔data_product_id parity),
  create + get-or-create idempotency, and `resolve_dp_target` LookupError on a missing DP.
  Committed.

### Cedar policy-module CRUD (+10 tests)
- `tests/test_policy_as_code_crud.py`: `services/policy_as_code/_crud.py` (was 49%). Create
  validation (blank name/source, duplicate-name conflict), get/list reads (+ disabled
  filter), in-place update (version bumps only on source change), enable toggle (no version
  bump), and delete (found/missing). Committed.

### Data-product contract-test CRUD (+8 tests)
- `tests/test_contract_tests_crud.py`: `services/contract_tests/_crud.py` (was 56%).
  `declare_contract_test` validation (unknown assertion-kind / severity, blank name), its
  idempotent create-then-update, dict-spec serialisation, and the list/delete helpers.
  Committed.

### Audit-sink config/filter decoders (+14 tests)
- `tests/test_audit_sinks_decode.py`: `services/audit/sinks.py` (was 48%) decode helpers.
  `_decode_config` fail-loud (bad JSON / non-object raises); `_decode_event_filter` and
  `_decode_workspace_filter` fail-open (None / empty / malformed / non-list → None,
  int-coercion with bad-entry skipping). Network dispatchers (webhook/s3/cloudtrail) left
  to their existing integration tests. Committed.

### Refactor candidates assessed, not taken
- `services/social/citations.py` (593 lines): a per-kind registry, structurally like
  `_blocks`, and verified **monkeypatch-safe** (tests use only the public `resolve_citations`
  / registry API). Deprioritised unattended: unlike `_blocks` (registration already
  per-block), citations registers all 12 kinds in one central list literal, so a clean
  per-kind split needs that list converted to per-module `register_citation_kind` calls —
  fiddly per-kind extraction with real transcription risk for a *second* refactor of modest
  marginal value. `_blocks` (the largest file, 1546 lines) already represents the refactor
  thread. Left as a clean, safe candidate for a supervised pass.
- `api/dependencies.py` / auth / route modules: NOT split-safe — heavily test-monkeypatched
  (see the reverted Phase 12 above). Only pure-logic, non-patched modules qualify.

## Group A (continued) — fresh-coverage-map-guided batches

Regenerated a fresh `--cov` map (`/tmp/pql-cov2.json`) after the first ~200 tests to target the
genuinely-remaining gaps instead of the stale baseline.

### OpenAI embedder + canvas column blocks (+20 tests)
- `tests/test_openai_embedder.py` (+6): `pql/embedders/_openai.py` (was 47%). Unknown-model
  validation, missing-`OPENAI_API_KEY` guard, default/large dims, and the `embed()` batch
  (empty-string substitution + one vector per input) via a faked client.
- `tests/test_dp_canvas_column_blocks.py` (+14): the refactored `_blocks/_columns.py` (was 62%)
  Cast / Rename / CalcColumn compile error branches (missing input, empty/invalid config) and
  schema-inference paths, driven through the public `compile_block` / `infer_block` dispatch.
  Committed.

### Canvas reshape blocks (+24 tests)
- `tests/test_dp_canvas_reshape_blocks.py`: the refactored `_blocks/_reshape.py` (was 62%)
  Window / Pivot / Unpivot / Union / Distinct / Sort / Sample — compile error branches
  (missing input, bad function/aggregate/kind, missing required config, non-numeric value)
  and inference paths (Window alias typing, Union column-mismatch detection, Unpivot column
  reshaping, dynamic-schema → unknown). Pure dispatch, no DB. Committed.

### Visual SQL builder translation (+19 tests)
- `tests/test_sql_builder_extra.py`: `services/sql/builder.py` (was 64%). The filter-operator
  branches (IS NULL / IS NOT NULL / IN-from-csv / IN-from-list / LIKE / ILIKE / comparisons /
  empty-value skip / unknown-op), the `_literal` type wrapping (bool/int/float/string), and
  build-side validation + aggregate/group-by/order/limit rendering. Pure sqlglot, no DB.
  Committed.

### Sentence-transformers embedder + soyuz audit reader (+11 tests)
- `tests/test_sentence_transformers_embedder.py` (+5): `pql/embedders/_sentence_transformers.py`
  (was 48%) — default/custom model, dim-from-model, float-list embed, per-model cache, all via
  a mocked `_load` (no `[vector]` dependency pulled).
- `tests/test_audit_soyuz.py` (+6): `services/audit/_soyuz.py` (was 46%) — `fetch_for_run`
  best-effort branches (200-list, 404, non-200, transport error, non-JSON, non-list → `[]`)
  via a fake UC-client httpx seam. Committed.

### Editor-chat agent factory (+5 tests)
- `tests/test_editor_chat_agent_factory.py`: `services/editor_chat/_agent_factory.py` (was 38%).
  Pure `check_llm_configured` (no-keys / with-key), and `build_agent`'s pre-import logic — the
  no-LLM `ValidationError` guard and the sql/notebook surface env-var routing — covered by
  isolating `os.environ` and faking the lazily-imported `run_agent` module. Committed.
