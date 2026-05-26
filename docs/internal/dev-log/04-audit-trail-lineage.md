---
title: "Cluster 04 — Phase 14–15 audit-trail + lineage (dev-log)"
audience: contributor
cluster_id: "04"
phases: "14-15"
closed: "2026-04-26"
---

# Cluster 04 — Phase 14–15 audit-trail + lineage (dev-log)

> Phase 14 (audit-trail close + public-launch defer split), Phase 15.5 + 15.6 sprints (lineage backend foundation).

These entries were materialised from the pre-W3 ``CHANGELOG.md`` ``[Unreleased]`` block (Doc-Master-Plan W3, 2026-05-26).  They preserve the original phase-keyed narrative for contributors who want richer commit-level context than the auto-generated per-cluster CHANGELOG section provides.

---

> from CHANGELOG.md (bucket: **Added**)

### Added — Phase 15.7: Value-Level Lineage (2026-04-26)

Fourth lineage axis after row (Phase 15), reject (15.5),
column (15.6).  Answers *"this gold row's `revenue` is $1234 —
what was it last week, and which run changed it?"*.  Surface
scope is `pql.merge(strategy="upsert")` only — the only PQL
primitive that mutates rows in place.

Capture mechanic: every new Delta write enables Change Data Feed
(`delta.enableChangeDataFeed=true`).  When the caller opts in via
`pql.merge(track_value_changes=True)`, post-merge
`DeltaTable.load_cdf()` yields native preimage/postimage pairs;
we diff per-cell on `_lineage_row_id` and persist into a new
`lineage_value_changes` table.  PointlesSQL-only storage; opt-in
default-off; `MAX_VALUE_CHANGES_PER_OP = 100_000` cap with
`[lineage_value_partial]` audit-row marker.

Sub-sprints:

- **15.7.0** — Open Phase 15.7 in ROADMAP / CHANGELOG (7b42369).
- **15.7.1** — Alembic migration `h8c9d0e1f2a3` adds
  `lineage_value_changes` table.  ORM `LineageValueChange`
  with `Text`-typed `old_value` / `new_value` columns.
  `record_value_changes` / `count_value_changes_for_op` /
  `fetch_value_changes_for_row` service helpers.
  `OperationRecorder.pending_value_changes` post-commit hook
  with `[lineage_value_partial]` marker (6641ed2).
- **15.7.2** — `pointlessql/pql/_cdf.py` exposes
  `cdf_creation_config()` and `ensure_cdf_enabled()`.
  `pql.write_table` (create-path) and `pql.autoload`
  (first-write) call `ensure_cdf_enabled` so every new Delta
  table records CDF events going forward (acb9954).
- **15.7.3** — `pql.merge` gains `track_value_changes` kwarg.
  Pure-function `services/value_change_capture.extract_value_changes`
  pairs `update_preimage` / `update_postimage` events on
  `_lineage_row_id` and emits one `ValueChangeSpec` per changed
  cell.  SCD-2 logs warning and skips (31847dd).
- **15.7.4** — `GET /api/lineage/value-changes?table=&row_id=
  &column=` JSON.  Row-trace page gains collapsible
  "Value changes (N)" per step.  Run-detail Operations tab
  shows `value changes: N` counter (fb8fcb2).
- **15.7.5** — `notebooks/hermes_medallion.py` silver `pql.merge`
  gets `track_value_changes=True`; second cell tweaks one
  `unit_price` and re-runs the merge.  Live replay confirmed:
  exactly 1 value-change in DB (`unit_price` 2.5 → 2.51),
  API + row-trace + run-view counter all render correctly.

> from CHANGELOG.md (bucket: **Added**)

### Added — Phase 15.6: Column-Level Lineage (2026-04-26)

Orthogonal column dimension to the row-lineage Phase 15 / 15.5
already shipped.  Every PQL primitive now populates a new
`lineage_column_map` table that answers *"if I rename `unit_price`
in silver, which gold columns break?"*.  PointlesSQL-only storage
(soyuz columnLineage facet ingest deferred to Phase 15.8+).
Volume bounded by schema breadth: ~52 column edges for the
canonical Hermes-Medallion run vs the 102 row edges + 2 rejects
Phase 15.5 already accepts.

- **Sprint 15.6.1** — new `lineage_column_map` table (Alembic
  `g7b8c9d0e1f2`) parented on the 15.5.3 rejects table.
  CHECK-constrained `transform_kind` enum:
  `identity` / `rename` / `derived` / `aggregate` /
  `unknown_origin` / `sql_select` / `sql_function` /
  `sql_unknown`.  Indices on (target_table, target_column),
  (source_table, source_column), run_id, op_id.  Service helpers
  `record_column_edges` (with a 1000-edge per-op cap that returns
  a `ColumnEdgeCapExceeded` sentinel and stamps
  `[lineage_column_partial]` on the audit row), `walk_back_columns`
  (column-trace walkback mirroring the Sprint-15.5.2 fan-in
  shape), and `count_column_edges_for_op`.  Best-effort
  post-commit hook on `OperationRecorder.pending_column_edges`
  matching the row-lineage / rejects contract.
- **Sprint 15.6.2** — every declarative PQL primitive populates
  the new table:
  - `pql.aggregate`: `aggs` dict drives the `aggregate` edges
    (with the agg-fn name in `transform_detail`); `group_by`
    columns become identity edges; new `derivations={...}` kwarg
    captures upstream `.assign(...)` mappings as `derived` edges
    with chain detail (e.g. `via 'line_revenue' →
    sum('line_revenue')`).
  - `pql.merge` / `pql.write_table`: schema-diff against the
    source frame.  Identity edges for surviving columns;
    `_lineage_row_id` rewritten to a `derived` edge with
    `transform_detail="synth_target_row_id"` so the row-id
    origin chain is queryable from `lineage_column_map` alone.
    `derivations` kwarg honoured; no `source_table_fqn` skips
    edge emission quietly.
  - `pql.autoload`: post-append Delta schema reads — non-audit
    columns recorded as `unknown_origin` with detail =
    `source_volume_fqn` or `"file"`; audit columns recorded as
    `unknown_origin` with detail `"audit"`.
  - New `services/column_lineage_diff.infer_column_edges` helper
    encapsulates the merge/write_table/autoload classification.
- **Sprint 15.6.3** — `pql.sql` populates the table for SELECT
  projections via `sqlglot.lineage`.  Per output column:
  bare-column refs → `sql_select`, function/arithmetic/CASE →
  `sql_function` (with rendered subexpression as
  `transform_detail`), zero-downstream nodes (`count(*)`, window
  functions, lateral joins) → `sql_unknown`.  Schema dict built
  from DuckDB `DESCRIBE` against the already-registered Delta
  views — no soyuz round-trip at SQL time.  Synthetic
  `target_table="query"` since `pql.sql` results aren't
  persisted; op_id is the unique discriminator.
- **Sprint 15.6.4** — three UI surfaces around the walkback:
  - `GET /api/lineage/column-trace?table=&column=` JSON +
    `/catalogs/.../columns/{col}/trace` HTML page (`column_trace.html`)
    with colour-coded transform_kind badges, fan-in collapsibles,
    click-through to source columns.
  - Table-detail page renders a small "lineage" badge per column
    that has at least one `lineage_column_map` row.
  - Run-detail Operations tab adds a "column edges: N" badge per
    op that produced edges (no new tab; same shape as the 15.5.4
    rejects counter).
- **Sprint 15.6.5** — `notebooks/hermes_medallion.py` declares
  `derivations={"placed_day": ["placed_at"], "line_revenue":
  ["qty", "unit_price"]}` on the gold aggregate.  Live E2E
  replay (headful Firefox): two notebook runs against fresh
  schemas, 52 column edges total, column-trace API walks
  `revenue → (qty, unit_price)` and `placed_day → placed_at` to
  bronze, table-detail page shows lineage badges on all five
  gold columns, run-detail tab shows `column edges: 10/10/6` per
  op.  Console clean.

> from CHANGELOG.md (bucket: **Added**)

### Added — Phase 15.5: Aggregate Lineage + Reject Visibility (2026-04-26)

Closes the two row-lineage gaps the Phase-15 live replay surfaced.
Five sprints landed in one autonomous session, all with green
linters + unit tests + a headful Firefox walkthrough that exercised
every UI surface end-to-end.

- **Sprint 15.5.1** — new `pql.aggregate()` primitive with fan-in
  lineage emission.  Records one edge per (source row, target group)
  pair so gold tables become trace-able back to their silver
  sources.  `source_table_fqn` is required (fail-fast).
  `_lineage_row_id` synth via SHA-256(target || group_values) so
  re-runs reuse target IDs deterministically.  See the new
  `pointlessql/pql/_aggregate.py` module and the matching
  Alembic migration `e5f6a7b8c9d0` extending the
  `agent_run_operations.op_name` CHECK by `'aggregate'`.
- **Sprint 15.5.2** — `walk_back` returns predecessors per step.
  The row-trace UI surfaces fan-in as a collapsible
  "Aggregated from N source rows" block with click-through to each
  source row's own trace page.  Chain recursion still picks oldest
  for determinism.
- **Sprint 15.5.3** — opt-in `pql.merge(track_rejects=True)` records
  source rows that won't land in the target into a new
  `lineage_row_rejects` table (Alembic `f6a7b8c9d0e1`).  Reasons:
  `on_key_null` / `duplicate_in_source` (auto-detected pre-merge),
  `schema_mismatch` / `merge_predicate_excluded` / `other` (enum
  reserved for callers).
- **Sprint 15.5.4** — new "Rejects" tab on the run-detail page
  between Operations and Tool calls.  Counter badge in the tab
  label, reason badges per row (color-coded), click-throughs from
  rejected source-row IDs to the row-trace page.  Empty state
  explains "track_rejects=True not set on any merge call".
- **Sprint 15.5.5** — notebook + fixture migrated; live E2E replay
  produced 102 lineage edges across 2 ops + 2 rejects + a 24-source
  fan-in on a gold row, verified in headful Firefox with 0 console
  errors.  Caught and fixed a Jinja-filter bug
  (`format_datetime` doesn't exist) that linters never had a chance
  to flag — the replay-as-gate memo proves itself again.

### Fixed — Sprint 15.5.0: Phase-15 bugfix landing (2026-04-26)

Two bugs surfaced in the Phase-15 live E2E replay (headful Firefox
walkthrough of the medallion notebook).  Neither could be caught by
ruff / pyright / pydoclint — they required running the full ETL +
clicking through the UI.  Reinforces the "live replay as gate" memo.

- **Fixed** [`pointlessql/models/lineage.py`](pointlessql/models/lineage.py)
  + [`pointlessql/alembic/versions/d4e5f6a7b8c9_lineage_row_edges.py`](pointlessql/alembic/versions/d4e5f6a7b8c9_lineage_row_edges.py)
  — `lineage_row_edges.id` switched from `BigInteger` to `Integer`
  primary key.  Only `INTEGER PRIMARY KEY` autoincrements in SQLite;
  `BIGINT PRIMARY KEY` does not.  Symptom: every `pql.merge` stamped
  `[lineage_edges_partial] IntegrityError("NOT NULL constraint failed:
  lineage_row_edges.id")` on `agent_run_operations.error_message` and
  produced zero per-row edges.
- **Fixed** [`frontend/templates/pages/run_view.html`](frontend/templates/pages/run_view.html)
  — header link "View lineage graph" URL aligned with the rest of the
  codebase: `/catalogs/{cat}/{schema}/{table}` →
  `/catalogs/{cat}/schemas/{schema}/tables/{table}`.  Line 594 of the
  same template was already correct; line 87 was a copy-paste miss.

### Added — Sprint 15.4: Row-trace UI + run-detail Lineage tab (2026-04-26)

Closes Phase 15.  The lineage chain built by Sprints 15.1-15.3 is
now navigable in the browser: an agent or reviewer can take any
silver row, click its `_lineage_row_id`, and walk the edges back to
the originating bronze cell with the source filename attached.

- **Added** [`pointlessql/api/lineage_routes.py`](pointlessql/api/lineage_routes.py)
  with two endpoints:
  - `GET /api/lineage/row-trace?table=&row_id=` — JSON walkback via
    `services.lineage_edges.walk_back` (capped at 20 hops).  When
    the deepest step lands on a bronze table, opens the Delta table
    via deltalake + DuckDB and looks up the `_source_file` cell so
    the trace can label "this row came from `orders.csv`".
  - `GET /catalogs/{cat}/schemas/{sch}/tables/{tbl}/rows/{row_id}/trace`
    — HTML page rendering the same walkback as a Bootstrap
    list-group (one card per step with depth badge, table FQN,
    op-name badge, and a link to the originating run).
- **Updated** [`pointlessql/api/main.py`](pointlessql/api/main.py)
  registers `lineage_router` **before** `governance_router` so the
  exact-match `/api/lineage/row-trace` route wins over the existing
  `/api/lineage/{full_name:path}` catch-all (which would otherwise
  greedy-capture `"row-trace"` as a UC full name).
- **Added** [`frontend/templates/pages/row_trace.html`](frontend/templates/pages/row_trace.html)
  rendering the input row metadata, the walkback steps, and an
  "lineage break" badge when the chain stops at depth 0 (no
  predecessor edges recorded).
- **Updated** [`frontend/templates/components/lineage_card.html`](frontend/templates/components/lineage_card.html)
  the card now accepts an optional `table_columns` context list and
  renders a card-footer hint when `_lineage_row_id` is present;
  also drops an `<a id="lineage">` anchor so the run-detail
  "View lineage graph" deep-link from Sprint 15.1 lands at the card.
- **Updated** [`frontend/templates/pages/table.html`](frontend/templates/pages/table.html)
  passes the table's column names to `lineage_card`; the Alpine
  preview now renders `_lineage_row_id` cells as deep-links to the
  row-trace page (truncated display, full UUID in the URL).
- **Updated** [`frontend/templates/pages/run_view.html`](frontend/templates/pages/run_view.html)
  new "Lineage" tab between "UC mutations" and "Queries" lists each
  op that produced edges with source/target FQNs and edge count;
  links into the target's lineage card via the new `#lineage`
  anchor.
- **Added** [`pointlessql/api/runs_routes.py`](pointlessql/api/runs_routes.py)
  `_load_lineage_summary_for_run()` joins `lineage_row_edges`
  against `agent_run_operations` for the run-detail Lineage tab,
  returning `{total_edges, rows: [{ordinal, op_name, source_table,
  target_table, edge_count}]}`.

### Added — Sprint 15.3: `lineage_row_edges` shadow table + merge instrumentation (2026-04-26)

Third Phase-15 sprint.  Per-row provenance now closes the loop: a
silver row produced by `pql.merge` carries a deterministic
`_lineage_row_id` that joins to a `lineage_row_edges` row pointing
back at the bronze cell that fed it.  Sprint 15.4 will surface this
in the UI.

- **Added** Alembic migration `d4e5f6a7b8c9` creating
  [`lineage_row_edges`](pointlessql/alembic/versions/d4e5f6a7b8c9_lineage_row_edges.py)
  (`run_id` FK to `agent_runs.id`, `op_id` FK to
  `agent_run_operations.id`, `source_table`, `source_row_id`,
  `target_table`, `target_row_id`, `created_at` plus four indexes
  for the lookup patterns Sprint 15.4 needs).  No UNIQUE constraint
  — re-merges of the same rows produce fresh edges with new
  `op_id`s, preserving merge history as an audit signal.
- **Added** [`pointlessql/models/lineage.py`](pointlessql/models/lineage.py)
  `LineageRowEdge` ORM model (re-exported from `pointlessql.models`).
- **Added** [`pointlessql/services/lineage_edges.py`](pointlessql/services/lineage_edges.py)
  with the public surface used by the merge/write instrumentation
  and Sprint 15.4's UI:
  - `synth_target_row_id(source_id, target_table) ->`
    `SHA-256("<source_id>:<target_table>")` — deterministic +
    table-distinct so re-runs reuse target IDs while never
    collapsing across tables.
  - `record_edges(...)` — best-effort bulk INSERT, returns the
    underlying exception on failure for the marker hook.
  - `fetch_target_row_predecessors` / `fetch_source_row_descendants`
    / `walk_back(table, row_id, max_hops=20)` — Sprint-15.4-bound
    read API.
  - `lookup_bronze_source_file(table, row_id, storage_location)` —
    DuckDB-over-deltalake one-row probe so the deepest walkback
    step can label its bronze origin file.
  - `count_edges_for_op(op_ids)` — UI counts per operation.
- **Added** `OperationRecorder.pending_lineage_edges` (kept off
  `params_json` so 100k-row payloads don't pollute the audit row)
  on
  [`pointlessql/services/agent_runs/operations.py`](pointlessql/services/agent_runs/operations.py).
  New post-commit hook `_record_row_edges_after_commit()` reads the
  payload, calls `record_edges`, and stamps
  `[lineage_edges_partial]` onto `agent_run_operations.error_message`
  on failure (refactored marker stamping into
  `_stamp_audit_marker` shared with Sprint-15.1's emit hook).
- **Updated** [`pointlessql/pql/_merge.py`](pointlessql/pql/_merge.py)
  new `_prepare_lineage()` helper extracts source row IDs from the
  PyArrow source's `_lineage_row_id` column (when present),
  synthesises target IDs via `synth_target_row_id`, and rebuilds
  the column so the target table's row inherits the new ID.  Empty
  ID lists when the source has no lineage column — the chain just
  stops there.  `pending_lineage_edges` is set only when both the
  source carried IDs **and** the caller declared `source_table_fqn`.
- **Updated** [`pointlessql/pql/_write.py`](pointlessql/pql/_write.py)
  parallel `_stamp_lineage_for_write()` works on pandas
  DataFrames or PyArrow Tables (the two engine-native frame shapes
  the writer accepts) and threads the source/target IDs through to
  the recorder for the same post-commit edge insert.

### Added — Sprint 15.2: Bronze `_lineage_row_id` audit column (2026-04-26)

Second Phase-15 sprint.  Bronze rows now carry a stable per-row
identity that downstream silver/gold transformations can reference
to walk the trail back to the originating cell.

- **Updated** [`pointlessql/conventions/_defaults.py`](pointlessql/conventions/_defaults.py)
  the bronze `LayerConvention` gains a fourth required audit column
  `_lineage_row_id` (alongside `_ingested_at`, `_source_file`,
  `_source_system`).  Other layers stay unchanged — silver/gold
  inherit lineage IDs through the merge primitive (Sprint 15.3) and
  don't get them injected at write time.
- **Updated** [`pointlessql/pql/_autoload.py`](pointlessql/pql/_autoload.py)
  `_inject_audit_columns()` now accepts `file_sha` and computes
  `_lineage_row_id` per row as
  `SHA-256("<file_sha>:<row_offset>")`.  The new helper
  `_row_lineage_id(file_sha, offset)` exposes the same construction
  for tests and downstream tooling.  The autoload caller threads
  the file SHA it already has from the dedup checkpoint into the
  injection call — no extra hashing pass.
- The change is a **convention**, not a schema migration: existing
  bronze tables keep their schema until the next autoload appends
  to them, at which point deltalake adds the new column with NULL
  for the older rows.  Re-running an autoload over the same file is
  a no-op (existing checkpoint dedup) and the IDs are deterministic
  so any future re-ingest produces identical row IDs.

### Added — Sprint 15.1: PQL → soyuz OpenLineage emission (2026-04-26)

First Phase-15 sprint.  Every successful PQL primitive call inside an
agent run now emits one OpenLineage `RunEvent` to soyuz so the
table-level lineage graph (`lineage_runs` + `lineage_edges`) auto-
populates without the operator having to wire OpenLineage producers
manually.

- **Added** [`pointlessql/services/soyuz_lineage.py`](pointlessql/services/soyuz_lineage.py)
  `emit_event_sync(run_id, op_name, inputs, outputs, event_type)`
  builds an `OpenLineageEvent` (using the typed soyuz client's
  generated models) and POSTs it through the existing
  `make_soyuz_client(agent_run_id=...)` factory.  The PointlesSQL
  `agent_run_id` is reused verbatim as the OpenLineage `runId` —
  soyuz strips hyphens to derive `LineageRun.id`, so cross-
  referencing agent runs ↔ lineage runs needs no extra mapping
  table.  The helper is **best-effort**: any underlying exception
  (connection refused, 5xx, timeout) is returned to the caller
  rather than raised, so the write that already committed is never
  rolled back by a downstream lineage hiccup.
- **Added** [`pointlessql/services/agent_runs/operations.py`](pointlessql/services/agent_runs/operations.py)
  `_emit_lineage_after_commit()` is invoked from `operation_context`
  after the success-path `record_operation()` returns.  Inputs are
  derived per-op:
  - `autoload` — empty (filesystem source, no UC securable)
  - `merge` / `write_table` — `extra_params["source_table_fqn"]`
    when the caller declared one, otherwise empty
  - `sql` — `params_json["referenced_tables"]` from the SQL parser
  Outputs default to `recorder.target_table` (or empty for read-only
  SELECTs).  When both lists are empty the emission is skipped.
  Failures stamp `[lineage_emit_failed] <repr(exc)>` onto the just-
  inserted row's `error_message`.
- **Added** `source_table_fqn` kwarg to
  [`pointlessql/pql/_merge.py`](pointlessql/pql/_merge.py) /
  [`pointlessql/pql/_write.py`](pointlessql/pql/_write.py) and a
  `source_volume_fqn` kwarg to
  [`pointlessql/pql/_autoload.py`](pointlessql/pql/_autoload.py) so
  callers can declare upstream UC inputs.  Threaded through the
  public `PQL.merge()` / `PQL.write_table()` / `PQL.autoload()`
  facades on [`pointlessql/pql/pql.py`](pointlessql/pql/pql.py);
  `PQL.merge()` further auto-derives `source_table_fqn` when *source*
  is itself a UC `"catalog.schema.table"` string.
- **Updated** [`frontend/templates/pages/run_view.html`](frontend/templates/pages/run_view.html)
  the run-detail header gains a "View lineage graph" button that
  jumps to the lineage card on the first touched table's catalog
  page (deep-link via `#lineage`).

> from CHANGELOG.md (bucket: **Changed**)

### Changed — Sprint 15.0: Phase 15 reframed as lineage completeness (2026-04-26)

- **Updated** [`ROADMAP.md`](ROADMAP.md) Phase-15 block: title
  shortened from "Provenance Log (data + LLM signed audit)" to
  "Lineage completeness", marker flipped ⏳ → 🚧, sub-tree
  expanded with the four sprint placeholders (15.1 OpenLineage
  emission, 15.2 bronze `_lineage_row_id`, 15.3
  `lineage_row_edges`, 15.4 row-trace UI), and an explicit Out-
  of-scope block for the Shoreguard token-trail log (lives in
  shoreguard-fresh per the boundary memo), arbitrary-SQL row
  lineage, and column-level lineage.

### Changed — Sprint 14.4 follow-up: soyuz pin bumped to v0.2.0rc3 (2026-04-26)

- **Updated** `pyproject.toml` `[tool.uv.sources]` pin from
  `v0.2.0rc2` → `v0.2.0rc3` and refreshed `uv.lock`.  The new
  soyuz tag carries the audit-log infrastructure
  (table + middleware + `/audit-log` endpoint + six instrumented
  mutation routes) plus the regenerated client with the typed
  `audit` API module.
- The Sprint 14.4 PointlesSQL service `soyuz_audit.fetch_for_run`
  still uses raw httpx; switching to the typed
  `list_audit_log_audit_log_get.asyncio(...)` method is a follow-
  up cosmetic when another callsite needs the typed surface.

### Added — Sprint 14.4: soyuz UC-mutation cross-reference (2026-04-26)

Closes the fourth and final Phase-14 audit-trail gap.  PointlesSQL
now forwards `X-Agent-Run-Id` outbound on every soyuz call made
from inside an agent run; soyuz's `audit_log` table (added
in soyuz `v0.2.0rc3`) attributes the mutation; the run-detail view
gains a "UC mutations" tab that joins them back together.

- **Added** [`pointlessql/services/soyuz_client.py`](pointlessql/services/soyuz_client.py)
  `make_soyuz_client(...)` and `make_principal_client(...)` accept
  an optional `agent_run_id` kwarg that lands as the
  `X-Agent-Run-Id` request header on every UC call the returned
  client makes.
- **Added** [`pointlessql/pql/pql.py`](pointlessql/pql/pql.py)
  `PQL.__init__` resolves the run id (explicit kwarg →
  `POINTLESSQL_AGENT_RUN_ID` env) before client construction so
  every PQL primitive's outbound UC traffic is attributable.
- **Added** [`pointlessql/services/soyuz_audit.py`](pointlessql/services/soyuz_audit.py)
  `fetch_for_run(uc_client, run_id, limit)` — read-only client for
  soyuz's `GET /audit-log?agent_run_id=` cross-reference surface,
  implemented via raw httpx (`get_async_httpx_client()`) since the
  generated client has no methods for `/audit-log` yet.  404
  collapses to `[]` so older soyuz versions degrade gracefully.
- **Added** [`pointlessql/api/runs_routes.py`](pointlessql/api/runs_routes.py)
  `_load_uc_mutations_for_run(request, run_id)` helper; the
  run-detail page passes `uc_mutations` into the template context.
- **Added** New "UC mutations" tab in `run_view.html` between Tool
  calls and Queries; renders action / target / principal / detail
  / created_at columns.  Empty-state copy spells out the
  `X-Agent-Run-Id` propagation contract and the soyuz `v0.2.0rc3`
  minimum.

Soyuz pin still at `v0.2.0rc2` — bumping to `v0.2.0rc3` pending a
push of the local soyuz tag.  The PointlesSQL code works against
any soyuz version: older soyuz returns 404 on `/audit-log` and the
UC mutations tab simply renders empty.

### Added — Sprint 14.3: external-write detection (2026-04-26)

Closes the third of four Phase-14 audit-trail gaps.  Delta commits
that bypassed every PQL primitive (raw `deltalake.write_deltalake()`,
Spark, `cp` of parquet, foreign tools) now surface in a dedicated
`unattributed_writes` table with a triage queue UI.  Detection-only
by design — see `project_full_autonomous_audit_critical_path.md`.

- **Added** Alembic `c3d4f5a6b7e8` — `unattributed_writes` table
  (`table_fqn` + `delta_version` UNIQUE, plus `acknowledged_at` /
  `detected_at` indexes).  Down-revision: `b27e6ad14ead`.
- **Added** [`pointlessql/services/external_write_scanner.py`](pointlessql/services/external_write_scanner.py) —
  `scan_table()` walks `DeltaTable(path).history(limit=N)` and
  diffs against `agent_run_operations.delta_version_after`;
  `scan_all()` enumerates every UC table via the async UC client;
  `list_unattributed()` / `acknowledge()` / `count_unacknowledged()`
  back the admin UI.  Reuses the
  `services/table_stats.read_delta_log_version` deltalake pattern;
  no raw `_delta_log/` JSON parsing.
- **Added** [`pointlessql/api/admin_external_writes_routes.py`](pointlessql/api/admin_external_writes_routes.py) —
  four admin-gated routes: GET HTML page, GET JSON list, POST scan
  trigger, POST acknowledge.
- **Added** Lifespan loop in [`pointlessql/api/main.py`](pointlessql/api/main.py)
  gated by `POINTLESSQL_EXTERNAL_WRITES_SCAN_INTERVAL_SECONDS`
  (default `0` = disabled — single-node vServer keeps the
  `DeltaTable.history()` cost off the critical path until an admin
  opts in).
- **Added** New `ExternalWritesSettings` sub-model
  (`scan_interval_seconds`, `history_limit`).
- **Added** Run-detail Operations tab gains a warning banner with
  the first 5 unattributed writes on tables this run touched
  (acknowledged-status filter), linking to `/admin/external-writes`.

### Added — Sprint 14.2: read-audit for `pql.table()` (2026-04-26)

Closes the second of four Phase-14 audit-trail gaps — the DSGVO
"wer hat meine Daten gelesen?" question for direct-Delta read paths
that bypassed `/api/sql/execute` entirely.

- **Added** Alembic `b27e6ad14ead` — `query_history.read_kind`
  TEXT NOT NULL DEFAULT `sql_execute` (down-revision:
  `a1c051a7e1ab`).  Enum validation lives in
  `record_query` against `VALID_READ_KINDS = {sql_execute,
  pql_table, engine_direct}` to match the existing
  application-level validation pattern (no DB CHECK).
- **Added** [`pointlessql/services/read_audit.py`](pointlessql/services/read_audit.py)
  `record_read()` — synthesises a `SELECT * FROM <fqn>` row so the
  existing `/queries` UI keeps working without per-`read_kind`
  branches.  Best-effort: silent passthrough when the session
  factory is unbound, swallows insert errors so audit can never
  break the read path.
- **Added** [`pointlessql/pql/_read.py`](pointlessql/pql/_read.py)
  instruments `read_table()` with a `record_read` call gated on
  `POINTLESSQL_AGENT_RUN_ID` being set, mirroring how `_sql.py`
  resolves run context.
- **Added** [`pointlessql/api/queries_routes.py`](pointlessql/api/queries_routes.py)
  `?read_kind=` filter on both `/queries` (HTML) and `/api/queries`
  (JSON); unknown values silently fall back to "no filter".
- **Added** Filter dropdown on `/queries`; "Kind" column with
  badge on both `/queries` and the run-detail Queries tab; empty-
  state copy mentions `pql.table()` reads explicitly.

### Added — Sprint 14.1: cost-gate EXPLAIN snapshot (2026-04-26)

Closes the first of four Phase-14 audit-trail gaps.  When the
Sprint-13.1 cost gate denies a query, reviewers can now see the
EXPLAIN plan that produced the verdict without re-running it.

- **Added** Alembic `a1c051a7e1ab` — `agent_runs.cost_gate_trigger`
  nullable JSON-as-Text column (down-revision: `b55f1020b8a4`).
- **Added** [`pointlessql/api/sql_routes.py`](pointlessql/api/sql_routes.py)
  `api_sql_explain` returns a new `cost_gate_trigger` field
  (`{explain, estimated_cost, threshold, engine, referenced_tables}`)
  in the response body when `needs_approval` is true.
- **Added** [`pointlessql/api/agent_runs_routes.py`](pointlessql/api/agent_runs_routes.py)
  `_coerce_cost_gate_trigger` helper; finish-route accepts the
  optional `cost_gate_trigger` body field; `serialize_agent_run`
  decodes it back to a dict.
- **Added** Run-detail metadata card (`run_view.html`) renders a
  collapsible Cost-gate-trigger row with badge + estimated/threshold
  numbers + EXPLAIN-JSON `<pre>` toggle (Alpine `:class` /
  `d-block`/`d-none` per `feedback_bootstrap_modal_x_show.md`).

> from CHANGELOG.md (bucket: **Changed**)

### Changed — Sprint 14.0: Phase 14 scope split (2026-04-26)

Phase 14 in `ROADMAP.md` is now scoped exclusively to the
audit-trail completeness pass (former 14.x): cost-gate EXPLAIN
snapshot, read-audit for `pql.table()`, external-write detection,
soyuz UC-mutation cross-reference. Sprint sequence 14.1 → 14.4
fixed; cross-repo soyuz work intentionally last as the natural
synchronisation point.

The original Phase 14 public-launch track (GHCR-public flip,
PyPI publish, multi-arch builds, Helm chart, README pass) moved
to a new unscheduled `Some-day` block at the end of the roadmap
tree. License decision locked to Apache 2.0. Memory heuristic
*"Don't pre-build release engineering for one user"* (see
`feedback_release_engineering_timing.md`) gates promotion: the
block stays unscheduled until an external consumer asks.

The previously-listed *"Run-detail Tool calls UI tab"* sub-item
is dropped — already landed silently in
`frontend/templates/pages/run_view.html:235-240` during the
Sprint-13.7.4 window before the migrations squash.

Plan: `.claude/plans/plane-phase-14-komplett-floofy-nest.md`.

### Added — Sprint 13.11.11: PQL write endpoints (2026-04-26)

Closed the read-only gap on the agent's tool surface that the
2026-04-26 walkthrough surfaced — `gpt-5-mini` correctly noted
that `pql.autoload` was unreachable from the chat adapter.

- **Added** [`pointlessql/api/pql_write_routes.py`](pointlessql/api/pql_write_routes.py) —
  four `POST /api/pql/*` endpoints behind `check_privilege` +
  Sprint-13.8 forced audit trail:
  - `/autoload` — mirrors `PQL.autoload` (file → bronze).
  - `/write_table` — runs SELECT, materialises pandas, writes.
  - `/merge` — runs SELECT, upsert / SCD-2 into existing target.
  - `/drop_table` — admin-only soyuz delete passthrough.
- `write_table` + `merge` reuse `prepare_sql` +
  `register_delta_view` so SELECT-side parsing/enforcement
  stays consistent with `/api/sql/execute`.
- 9 route-level tests in
  [`tests/test_pql_write_routes.py`](tests/test_pql_write_routes.py)
  (admin happy-path, validation reject, non-admin denial per
  endpoint).

Plugin commit `hermes-plugin-pointlessql fa31742` adds the
matching four tools (`pql_autoload` / `pql_write_table` /
`pql_merge` / `pql_drop_table`) — 14 new tool tests, 80/80
pass.  Plugin tool surface now sits at 20 tools (16 + 4).

### Fixed — Sprint 13.11.5: live-Hermes hotfix

First real `hermes chat` smoke run after the Phase-13 close-out
exposed two latent bugs the unit tests couldn't catch — one
PointlesSQL-side, two on the plugin side.

- **Fixed** [`pointlessql/api/error_handlers.py`](pointlessql/api/error_handlers.py)
  `_handle_request_validation_error` — added a new `_json_safe`
  coercion helper that walks dicts/lists and decodes raw `bytes`
  to UTF-8 before returning the 422 body.  Without it a request
  posted with a JSON body but missing `Content-Type` made
  FastAPI surface the payload verbatim in the validation
  error's `input` field, and `json.dumps` then raised
  `TypeError: Object of type bytes is not JSON serializable` —
  flipping the 422 into an opaque 500.  New tests in
  [`tests/test_error_handler_json_safe.py`](tests/test_error_handler_json_safe.py)
  cover scalar pass-through, byte decoding (incl. invalid
  UTF-8 → replacement chars), nested structures, and the
  contract test that `json.dumps` round-trips cleanly.

The two plugin-side bugs (discovery shim + `Content-Type`
default + `finish_run` status default) ship in
`hermes-plugin-pointlessql 5676301`.

### Added — Sprint 13.11 walkthrough playbook

- **Added** [`docs/e2e-walkthroughs/sprint_13_11_reflexive_tools.md`](docs/e2e-walkthroughs/sprint_13_11_reflexive_tools.md)
  — API-centric replay with embedded Playwright-MCP-Befehle.
  Live-replayed 2026-04-26: all five Family-A routes return the
  expected payload, `pql_target_state(missing.table)` returns
  `exists=false` (the bug-2 catch), supervisor scope correctly
  returns `403` for the normal-key path on `/summary`, and
  `cost_gate_threshold` is **not** present in the
  supervisor-key response (anti-gaming guard verified).  The
  `/runs/{id}` UI surfaced the new tool-call-tab badge populated
  by the simulated `post_tool_call` POSTs.
