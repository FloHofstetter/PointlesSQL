# Changelog

All notable changes to this project will be documented in this file.

The CHANGELOG is auto-generated from Conventional Commits via
[git-cliff](https://git-cliff.org/), grouped into per-cluster release
sections.  Cluster boundaries live in ``scripts/clusters.json``;
re-generate with ``uv run python scripts/regen-changelog.py``.

The full per-rc dev-log lives under ``docs/internal/dev-log/`` for
contributors who need finer commit-level granularity.

## [Unreleased]

<!-- Future commits land here until the next cluster boundary is
defined in ``scripts/clusters.json``. -->

### Features

- DP-Canvas: auto-layout via Dagre (rc228).  Toolbar gets a Tidy
  button (Ctrl+L shortcut) that runs Dagre's layered LTR
  algorithm over the current nodes + edges, then animates each
  block to its target position with an easeInOutQuad tween over
  250ms (so blocks slide into place rather than teleporting).
  New helper module ``frontend/js/dp_canvas/_auto_layout.js``
  isolates the Dagre wrapper + tween from the editor page.
  Dagre loaded from the same jsdelivr CDN as Drawflow
  (``dagre@0.8.5``, ~30KB).

- DP-Canvas: minimap + Ctrl+F block search (rc227).  Bottom-right
  corner gets a 200×130 SVG minimap showing every block's
  position scaled to fit; the currently-selected block is
  rendered in the primary blue, the rest in secondary grey.
  Toolbar gains a Map toggle.  Ctrl+F opens a top-anchored
  search overlay that filters blocks by ``block_type`` (case-
  insensitive substring) or ``id``; arrow keys move the cursor,
  Enter pans the canvas to the match and selects it, Escape
  closes.  Minimap re-renders are rAF-coalesced and reuse the
  same drag-flush path so they never throttle the cursor.

- DP-Canvas: multi-select + bulk operations (rc226).  Shift+Click
  on a block toggles it in a parallel ``multiSelectedNodeIds``
  set (a plain click clears the set so the single-edit right
  drawer stays unsurprising).  Delete / Backspace with more than
  one block selected prompts ``Delete N blocks?`` then bulk-
  removes via ``df.removeNodeId``.  Ctrl+C copies the selected
  blocks (and the internal edges between them) into
  ``localStorage["pql-canvas-clipboard"]``; Ctrl+V pastes them
  with a +40/+40 offset and fresh PQL ids.  Rubber-band marquee
  selection deferred — collides with Drawflow's native canvas-bg
  pan handler and needs a Space-or-middle-click escape hatch
  designed in.

- DP-Canvas edges now coloured by upstream data-type family
  (rc225).  New ``_edge_types.categorize_pin_schema`` helper
  inspects each edge's upstream ``PinSchema`` and assigns one of
  six buckets (``numeric``, ``text``, ``temporal``, ``boolean``,
  ``complex``, ``mixed``).  Validate-endpoint response gains
  ``edge_categories`` mapping ``{edge_id: bucket}``; editor
  applies ``pql-edge-${bucket}`` CSS classes to each
  ``.drawflow .connection`` so a glance at the canvas reveals
  where the numeric backbone runs, where text columns flow, and
  where temporal joins fan out.  Toolbar gains an orthogonal-
  routing toggle that flips ``Drawflow.curvature`` between Bezier
  (0.5) and straight-segment (0) and re-renders all connection
  paths.

- DP-Canvas node body now shows inline schema preview, last-preview
  row-count, and validation status (rc224).  Each node renders up
  to 3 output columns (with type-icons inferred from the column's
  DuckDB type — hash for INT, calculator for DOUBLE, calendar for
  TIMESTAMP, etc.) plus a footer with the cached row-count from
  the last preview run and a check / cross / circle icon for the
  validate state.  Toolbar gains a Compact toggle that hides the
  rich body when the canvas grows wide.  The body re-renders
  after every successful validate (sourced from
  ``pinSchemas[id:out]``) and after every preview run.  No
  backend change — pure frontend over the existing validate +
  preview responses.

- DP-Canvas + Mesh-Canvas drag performance — node positions stay
  glued to the cursor during drag (rc223).  The ``nodeMoved``
  handler used to call ``_syncFromDrawflow`` on every animation
  frame, which exported the full Drawflow document, rebuilt the
  ``nodes`` + ``edges`` dicts, and queued debounced validate +
  autosave passes on each cursor tick.  Position-only mutations
  now flow through a ``requestAnimationFrame``-coalesced
  ``_onNodePositionChanged`` path that touches only
  ``nodes[id].position`` and schedules a single autosave; the
  structural sync (edges, validate) stays on the
  ``connectionCreated`` / ``connectionRemoved`` / ``nodeRemoved``
  / ``nodeDataChanged`` paths.  Mesh-Canvas dropped its
  ``nodeMoved`` listener entirely (mesh positions are not part of
  the persisted document model — they were doing a full
  ``_syncEdges`` + validate per frame for no payload change).

- API-key usage — WoW diff + 3σ anomaly heuristic (rc222).
  Closes Mega-Cluster 155-164.  ``get_usage_summary`` response
  envelope extended with three new sub-objects: ``wow`` (last-7d
  vs prev-7d totals + change_pct; ``None`` when prior window had
  zero traffic so the UI doesn't render +∞% badges), ``stats``
  (window-end rolling 7-day mean + stdev), and a per-day
  ``is_anomaly`` boolean.  Anomaly rule is layered: when the
  prior 7-day window has variance, flag |count - mean| > 3σ;
  when variance is zero but mean > 0, flag a count > 5× mean
  (so a constant-baseline burst still surfaces); otherwise no
  flag.  Five new pytest cover the envelope shape, WoW
  calculation, divide-by-zero guard, true 3σ spike on noisy
  baseline, and constant-baseline = no-flag.  Frontend Chart.js
  sparkline rendering deferred to a follow-up polish phase.

- Audit-cockpit — Saved filters + details-regex search (rc221).
  Admins can now name their favourite audit-filter combos
  (since-window + action + user-substr + target-substr + details-
  regex) and re-apply them with one click instead of re-typing
  every time.  New ``audit_saved_filters`` table is owner-private
  by default; per-row ``is_shared_workspace`` flips the filter to
  workspace-wide visibility.  Four CRUD routes under
  ``/admin/audit/saved-filters`` (list / create / update / delete)
  are admin-gated + CSRF-protected.  The audit viewer's index
  route gains a new ``?details_regex=...`` query parameter that
  filters rows server-side after the DB hit (Python re.search on
  the JSON ``detail`` column).  Invalid regexes surface a friendly
  ``regex_error`` to the template instead of crashing the viewer.
  Frontend HTML dropdown UI for the saved-filters selector is
  intentionally deferred — the API + storage are in place; the
  visible UI can land in a follow-up polish phase.

- Mesh-canvas — Cross-workspace upstream edges (rc220).  Adds a
  nullable ``source_workspace_id`` FK on
  ``data_product_input_ports`` (``ON DELETE RESTRICT``) so an
  upstream binding can point at a data product in a different
  workspace.  Backward-compatible: every existing row has the
  column NULL = "same workspace as the consumer," the historic
  semantics.  The mesh-canvas read path now exposes cross-
  workspace upstreams as ghost-nodes carrying the foreign
  workspace's slug; the write path accepts edges with
  ``source_workspace_slug``, resolves the foreign workspace and
  DP, then writes the binding.  New admin-only picker endpoint
  ``GET /api/mesh/canvas/picker/{workspace_slug}`` lists
  candidate upstream DPs in a foreign workspace.  Cross-
  workspace browse is admin-only — opens a permission surface
  general users shouldn't walk.  Frontend right-click "Create
  new DP here" + workspace picker UI deferred to a future polish
  phase.

- Visual DP Editor — Duplicate this block (rc219).  Selected
  canvas blocks gain a Duplicate button in the right drawer
  toolbar (next to the Delete trash icon) and a ``Ctrl+D`` /
  ``Cmd+D`` keyboard shortcut.  The clone lands +40px offset,
  deep-copies the source config + position, gets a fresh PQL
  node id, and auto-selects so the user can edit it without
  hunting.  Help text on every block was already wired through
  the palette tooltips + per-field ``form-text`` strings so no
  per-field info-icons added in this pass.

- Visual DP Editor — Granular per-block Y.Doc co-edit sync
  (rc218).  Co-edit Y.Doc shape upgraded from a single ``json``
  slot holding the whole serialised CanvasDoc to per-block +
  per-edge structured Y.Maps (``nodes_order`` / ``nodes_map`` /
  ``edges_order`` / ``edges_map``).  Two peers editing two
  different nodes' configs now write to different Y.Map keys and
  never conflict at the Y.js layer.  Legacy v1 single-slot Y.Docs
  are auto-migrated on first ``extract_canvas_doc`` read so any
  in-flight co-edit session re-opens cleanly under v2.  Frontend
  hub client still does a coarse full-replay on observe — granular
  client-side mutation handlers are out of scope for v1.

- Visual DP Editor — CodeMirror polish: format-on-blur + snippets
  (rc217).  The multi-line SQL block editor formats the document
  on blur using a small inhouse DuckDB-ish formatter (uppercase
  keywords + newline before SELECT/FROM/WHERE/JOIN families).  Ten
  hardcoded snippets ride the existing completion source so
  typing ``cte``+Tab expands to a CTE skeleton, ``win``+Tab to a
  window-over clause, etc.  Multi-cursor (Alt+Click) was already
  enabled in CodeMirror 6; documented in user-facing tooltip.
  Linter for unbalanced parens is intentionally deferred to keep
  the bundle small.

- Visual DP Editor — Diff-view visual canvas overlay (rc216).
  The ``/dp/{id}/canvas/diff`` page now defaults to a side-by-side
  visual diff with two read-only Drawflow editors holding the
  before + after canvases.  Added nodes get a green outline,
  removed get red (with 60% opacity on the before-pane), modified
  get yellow on both panes; added/removed edges follow matching
  stroke colours (dashed for removed).  The original 3-column
  list view is still reachable via a toggle.  Extracts a shared
  ``_drawflow_loader.js`` helper so the editor and diff pages
  reuse the same Drawflow node-add + connect dance instead of
  duplicating it.

- Visual DP Editor — Schema-flow diagnostics UX (rc215).
  Per-node error badges in the canvas editor now carry a
  hover-tooltip with the full structured diagnostic (kind, pin,
  column, expected/actual type, suggestion) instead of just a
  numeric error count, so users can read what went wrong without
  opening the validation panel.  Backend: the ``CompileError``
  envelope grows optional ``column`` / ``expected_type`` /
  ``actual_type`` / ``suggestion`` fields; Project + GroupBy +
  Join column-presence errors fill ``column``; the Cast block's
  unknown-target-type error fills ``column`` +
  ``actual_type`` + ``suggestion="UNKNOWN_DUCKDB_TYPE"``.  The
  "Insert Cast block" quick-fix is intentionally deferred until a
  future block surfaces a true expected/actual type mismatch
  with a matched column — today's validator only surfaces
  column-presence errors where inserting a Cast would not help.

- Visual DP Editor — Preview cache + truncation indicators
  (rc214).  Re-previewing the same canvas node now returns instantly
  from an in-process LRU keyed on the upstream-slice content hash;
  the `PreviewResult` envelope carries new ``row_count`` and
  ``cache_hit`` fields so the editor surfaces a "cached" badge and a
  per-call row count in the preview modal footer.  Save-graph
  automatically busts cache entries for the DP so a fresh post-save
  preview always re-executes against DuckDB.  Explicit cache
  invalidation exposed via ``?bust=1`` on the preview endpoint
  (wired to a "Bust cache" button) for the case where the upstream
  Delta location was rewritten out-of-band.  Per-worker / in-process
  only; multi-worker fan-out via Redis is explicit out-of-scope for
  v1.

- Visual DP Editor — Pin / Unpin production canvas version (rc213).
  Opens the Mega-Cluster 155-164 polish wave on top of the freshly
  shipped Mega-Cluster 147-154 surface.  Each saved canvas version
  in [data_product_canvas_graph](pointlessql/models/catalog/_data_products.py)
  now carries an ``is_production`` flag; the Versions ▾ dropdown
  shows a pin badge per row and a steward-only pin/unpin button.
  A partial unique index enforces "at most one pinned version per
  data product"; the materialise modal warns when the current
  draft would replace the pinned production version (soft warning
  only — no block).  Two new routes
  ``POST /api/dp/{id}/canvas/versions/{n}/pin`` and
  ``.../unpin`` emit ``canvas_pin`` / ``canvas_unpin`` audit-log
  events.  Alembic ``m1a3c5e7g9i1`` widens the
  ``ck_agent_run_operations_op_name`` CHECK with the same two
  values so future agent-mediated pin/unpin via plugin tools can
  reuse the enum without another migration.

- Visual Data Product editor — versioning UI + plugin MCP tools
  + cluster closure (rc212).  Wave H closes the Mega-Cluster
  147-154.  (1) Editor toolbar gains a new **Versions ▾**
  dropdown that lists all saved canvas versions newest-first;
  per-row Restore creates a fresh latest from the chosen version
  (load-then-save round-trip), and a per-row Compare link opens
  the Wave-F diff-view between that version and the current
  latest.  New
  [GET /api/dp/{id}/canvas/versions/{version}](pointlessql/api/data_products_routes/canvas.py)
  route exposes the saved document for any version so the
  restore flow can re-post it.  (2) Sibling
  [hermes-plugin-pointlessql](../hermes-plugin-pointlessql) commit
  `6047bc2` adds 5 MCP tools: `pql_canvas_load` + `pql_canvas_validate`
  in the family-A unconditional batch; `pql_canvas_add_block` +
  `pql_canvas_wire_blocks` + `pql_canvas_materialize` gated on
  `supervisor_mode` (same scope that gates `pql_promote_model`).
  PointlessClient gains 4 new methods to wrap the canvas routes.
  Together they let agents author DPs end-to-end through the same
  HTTP surface browser users use.  (3) The
  [dp-canvas-builder walkthrough](docs/e2e-walkthroughs/dp-canvas-builder.md)
  is now the full 6-wave reference (B Happy-Path, C Live-Preview +
  CodeMirror, D Compound + Mesh, F YAML round-trip + Diff, G
  Co-Edit, H Versioning + Agent flow).  2 new pytest in
  [test_data_product_canvas_routes.py](tests/test_data_product_canvas_routes.py)
  cover the version-load + diff routes; 7 new pytest in the
  plugin cover the 5 new tools.  Cluster summary: 8 commits,
  rc204 → rc212, full PointlesSQL suite 4074 / 0 / 10 green,
  full plugin suite 293 / 0 green.
- Visual Data Product editor — opt-in real-time co-edit (rc211).
  Wave G of the cluster wires a Y.Doc-backed co-edit hub to the
  canvas editor, mirroring the Phase-105 notebook pattern at a
  smaller scale.  Single-file WS endpoint at
  [dp_canvas_coedit_ws.py](pointlessql/api/dp_canvas_coedit_ws.py)
  maintains an in-memory pycrdt.Doc per data-product id (root
  Y.Map "canvas" with one "json" entry carrying the serialised
  CanvasDoc), handles the same 4-tag protocol as the notebook hub
  (SYNC_STEP1 / SYNC_STEP2 / SYNC_UPDATE + AWARENESS_UPDATE), and
  runs a 1.5 s flush_loop that calls a new service helper
  ([_coedit.py](pointlessql/services/dp_canvas/_coedit.py)) to
  persist the live Y.Doc into a fresh `data_product_canvas_graph`
  row via the existing `save_graph` path.  The hub skips
  persistence when the live doc hasn't structurally changed since
  the latest saved row — idle hubs don't flood the version ledger.
  Frontend
  [coedit.js](frontend/js/dp_canvas/coedit.js) lazy-imports yjs +
  y-protocols/sync + y-protocols/awareness from the existing
  base.html importmap and conditionally mounts only when the
  editor URL carries `?coedit=1`, so the single-user mode pays no
  Y.js download cost by default.  Local Drawflow mutations push
  the editor's current serialisation into the Y.Map; remote
  updates reload the editor through the existing `_loadIntoDrawflow`
  pipeline with a 50 ms suppression window so the editor's own
  autosave doesn't echo back upstream.  4 new pytest cover the
  service helpers (empty seed, seeded-from-DB, identical-skip,
  bump-on-change); the WS endpoint is exercised by manual browser
  replay since asyncio + uvicorn + Starlette WS testing setup is
  larger than the feature's surface justifies for v1.  Full suite
  stays green.  Single-file design (vs. the 8-file notebook
  package) is intentional — DP canvases don't need the
  cross-process bus or cell-uuid remap that the notebook hub
  ships.
- Visual Data Product editor — DP-as-Code round-trip + version
  diff-view (rc210).  Wave F gives canvases full git-tracking
  parity with the rest of the DP-as-Code spec.  (1) New
  `CanvasPipelineSpec` Pydantic model in
  [_canvas_pipeline.py](pointlessql/services/data_product_as_code/_canvas_pipeline.py)
  defines a structured YAML sub-tree (chosen over an embedded JSON
  string per the ADR call — git-diffable, human-readable) and
  exports `from_canvas_doc` / `to_canvas_doc` round-trip helpers
  that go back-and-forth with the canonical `CanvasDoc`.  The
  existing `DataProductSpec` gains an optional `pipeline` field; the
  exporter populates it from the latest `data_product_canvas_graph`
  row when present, and `POST /api/data-products/apply` calls
  `save_graph` with `to_canvas_doc(spec.pipeline)` after the
  regular plan→apply pass, surfacing the new `canvas_version`
  in the apply response.  (2) New service `_diff.py:diff_docs`
  computes the structural delta between two canvas versions
  (added/removed/modified nodes, added/removed edges); position-
  only changes are deliberately ignored so cosmetic relayout
  doesn't drown out config edits.  New
  `GET /api/dp/{id}/canvas/diff?from_version=N&to_version=M` route
  + standalone `/dp/{id}/canvas/diff` page render the result as a
  3-column added/removed/modified layout with side-by-side JSON
  trees for the modified-config case.  7 new pytest cover the
  round-trip + diff service (`test_canvas_pipeline_roundtrip.py`);
  full suite stays green.
- Visual Data Product editor — block library expansion (rc209).
  Wave E adds 10 new transform-block types so the editor covers the
  common shapes the previous 9-block set could not:
  ``Window`` (PARTITION BY / ORDER BY OVER, with the canonical 10
  DuckDB functions ROW_NUMBER/RANK/DENSE_RANK/LAG/LEAD/SUM/AVG/MIN/
  MAX/COUNT), ``Pivot`` + ``Unpivot`` (DuckDB native statements; the
  pivot output is intentionally `unknown=True` since the column set
  is data-dependent), ``Union`` (multi-input with schema-mismatch
  surfaced as a `type_mismatch` CompileError + UNION ALL toggle),
  ``Distinct`` (optional `ON ({cols})`), ``Sort`` (multi-key
  ORDER BY with per-column direction), ``Sample`` (USING SAMPLE
  N PERCENT or N ROWS), ``Cast`` (per-column `::TYPE` coercion
  with target-type allowlist), ``Rename`` (`{old: new}` map),
  ``CalcColumn`` (new column from a DuckDB expression — reuses the
  Wave-C CodeMirror predicate editor for the expression field).
  Frontend palette gains a "Transforms" group of 16 entries; the
  block-registry size goes from 9 to 19.  Union shares the
  Join two-input pin layout (left + right); the editor's
  ``inputPinName`` helper recognises both.  11 new pytest in
  ``test_blocks.py`` + a registry-size assertion covering the
  full 19-block set; full suite stays green.
- Visual Data Product editor — compound DP blocks + editable mesh
  canvas (rc208).  Wave D of the Mega-Cluster 147-154 closes the
  Simulink-style "fat block = DP" metaphor:  (1) new
  `DataProduct` block in `BLOCK_REGISTRY` whose config carries
  `{dp_id, port_name, materialized_table}`; the route layer's new
  `_resolve_dp_refs` pre-pass fills `materialized_table` from
  `DataProductOutputPort.location` on save / validate / preview /
  materialise so the compiler stays pure and emits the same
  `SELECT * FROM <fqn>` shape as `InputPort`.  Frontend BLOCK_DEFS
  gains the DP◫ entry plus a config-form with a DP-picker dropdown
  fed by a new `GET /api/dp/_picker` route and a downstream
  port-name picker driven by the chosen DP's
  `DataProductOutputPort` rows.  (2) Double-click on a DP◫ block
  navigates into that DP's canvas in place; a small localStorage-
  backed breadcrumb stack (`pql.dp_canvas.breadcrumb`) lets the
  topbar render a "◀◀ <previous-DP>" back-button that pops the
  trail.  (3) New workspace-level mesh canvas at `/mesh/canvas`
  with three thin routes (`GET/POST /api/mesh/canvas` +
  `POST /api/mesh/canvas/validate`,
  [mesh_canvas_routes.py](pointlessql/api/mesh_canvas_routes.py))
  over a new service
  ([_canvas.py](pointlessql/services/mesh/_canvas.py)) that
  converts between a Drawflow-shaped `MeshCanvasDoc` and the
  declared upstream-input-port rows: each wire is one
  `DataProductInputPort(kind=upstream_product, source_ref=...)`,
  save diffs the desired edge set against the DB and applies
  the delta via the existing `create_input_port` /
  `delete_input_port` CRUD helpers (no Delta data is moved).  4
  new pytest cover the mesh routes (load / save-creates /
  save-removes / validate-self-loop); 3 new pytest cover the
  `DataProduct` block's compile + infer paths plus the registry
  count flip from 8 to 9.  Full suite stays green.
- Visual Data Product editor — live preview + CodeMirror predicates
  + SQL schema-inference (rc207).  Three Wave-C additions on top of
  rc206:  (1) per-node preview — new
  `POST /api/dp/{id}/canvas/preview` route + service helper
  ([_preview.py](pointlessql/services/dp_canvas/_preview.py)) that
  prunes the canvas DAG to everything upstream-of-cursor via reverse
  BFS, injects a synthetic sink so the existing `compile_canvas`
  machinery keeps working unchanged, wraps the rendered CTE in
  `SELECT * FROM (…) LIMIT N`, registers Delta views the same way
  the executor does, and returns the first ≤1000 rows as plain JSON
  (read-only: no Delta write, no canvas-graph version bump).  The
  drawer-side **Preview** button opens a Bootstrap modal with a
  columns/rows table, a row-limit picker, a "Showing first N rows"
  truncation badge, and a `<details>` block for the rendered SQL.
  (2) CodeMirror DuckDB-grammar editors for Filter.predicate +
  SQL.query — new helper module
  ([codemirror_predicate.js](frontend/js/dp_canvas/codemirror_predicate.js))
  exports `mountPredicateEditor` (single-line, Enter swallowed) and
  `mountSqlEditor` (multi-line, line-numbers + history), both
  reusing the `@codemirror/lang-sql` + `@codemirror/autocomplete`
  modules already loaded by the
  [base.html importmap](frontend/templates/base.html).  Column-name
  autocomplete pulls from the cached pin-schemas via
  `upstreamColumns()` so users get live offers of upstream columns
  as they type.  (3) SQL-block schema inference — `_infer_sql` runs
  a DuckDB `DESCRIBE (rewritten_query)` against an in-memory
  connection seeded with a temp table whose columns mirror the
  upstream `PinSchema`; downstream blocks now see real columns
  flowing out of raw SQL blocks instead of opaque `unknown=True`
  pin schemas.  Five new pytest cover the preview route's happy +
  truncation + 404 + 422 paths; four new pytest cover SQL-block
  schema-inference (select-star, two-input join, invalid query
  → bad_config, no-upstream-with-placeholder → unknown).  Bonus
  fix: removed a leftover `cast(Client, uc._client)` that pyright
  strict mode flagged as unnecessary in the Phase 148 closure.
  Full suite 4042 / 0 / 10 green.
- Visual Data Product editor — frontend editor (rc206).  Standalone
  full-screen authoring surface at `/dp/{id}/canvas` that consumes
  the rc205 compiler backbone end-to-end.  Drawflow-based
  block-and-wire canvas (chosen over Rete.js v2 because the latter
  forces a Vue / React / Lit render-plugin while this codebase
  carries none of those — Drawflow is a single-file UMD that drops
  into the existing build-step-less Alpine stack); three-pane layout
  with a draggable palette of all eight Wave-A block types, the
  canvas, and a right drawer that renders per-block-type
  configuration forms (chip-inputs for column lists, dynamic
  aggregation rows, conditional merge-on for `mode=merge`).  Five
  thin HTTP routes
  ([canvas.py](pointlessql/api/data_products_routes/canvas.py))
  wrap the service-layer surface: load latest doc, save new version
  (with optimistic-concurrency `expected_base_version`), list
  versions newest-first, edit-time schema-flow validate (resolves
  each `InputPort.table_fqn` against soyuz so propagation has real
  upstream schemas), and materialise (compile → execute → write
  Delta → register output port → save version).  Auto-save debounces
  at 1.5 s after the last graph mutation; the validate round-trip
  follows ~0.8 s after edits and the editor renders per-node error
  badges + a clickable status-bar error list.  A Canvas tab on the
  data-product detail page lazy-fetches the version list and links
  to the standalone editor.  New e2e walkthrough
  ([dp-canvas-builder.md](docs/e2e-walkthroughs/dp-canvas-builder.md))
  covers the drop → wire → save → run → lineage path.  16 new pytest
  cover save / load / versions / 403-write / 404-unknown / round-trip
  with all 8 block types / optimistic-concurrency conflict /
  validate happy + bad-UC-table / materialise success + 422 +
  404; full suite 4034 / 0 / 10 green.
- Visual Data Product editor — compiler backbone (rc205).  New
  `pointlessql/services/dp_canvas/` service package that turns a
  visual block-and-wire DAG into executable DuckDB SQL and
  materialises the result into a Delta table the parent data
  product publishes through a registered output port.  Eight
  initial atom blocks (`InputPort`, `Filter`, `Project`, `Join`,
  `GroupBy`, `Limit`, `SQL`, `OutputPort`); compiler runs Kahn's
  topological sort + CTE-chain generation; schema-flow validator
  forward-propagates per-pin schemas and surfaces edit-time type
  mismatches as structured `CompileError` rows; executor wraps
  compile → execute → materialise → output-port register → graph
  versioning in a single `operation_context` so the audit trail
  records one row + emits OpenLineage with every base table the
  graph reads.  New ORM row + alembic migration
  `l9x1z3b5d7f9` for `data_product_canvas_graph` (append-only
  version ledger per product) plus a CHECK widening for the new
  `OpName.CANVAS_MATERIALIZE` enum value.  HTTP routes + the
  Rete.js editor frontend follow in sibling waves; this ships
  pure service-layer so the editor can be swapped without
  touching compile/materialise semantics.  44 new pytest covering
  per-block compile + schema-flow propagation + end-to-end Delta
  materialise + lineage capture; full suite stays green.
- Workspace-default Cost & quota form on `/admin/governance`
  (rc204).  The Phase 146 closure shipped the per-product
  Cost & quota panel on the data-product detail page but never
  added the workspace-default counterpart on the admin governance
  cockpit, even though [admin-mesh-dashboard.md](docs/e2e-walkthroughs/admin-mesh-dashboard.md)
  and the Phase 146 walkthroughs assumed both layers existed.
  Added the three rows
  ([admin_governance.html](frontend/templates/pages/admin_governance.html))
  + the load / save wiring
  ([admin_governance.js](frontend/js/pages/admin_governance.js))
  routed through the existing PUT `/api/admin/governance/policy`
  endpoint (which already accepted all POLICY_FIELDS).  Surfaced
  a pre-existing bug en route — see the matching Fixes entry.

### Fixes

- Replay buckets now classify `canvas_materialize` as unsafe
  (rc206).  The rc205 compiler backbone added the
  `OpName.CANVAS_MATERIALIZE` enum value but missed extending the
  replay dispatcher's `UNSAFE_OPS` set, so the
  `test_unrecognised_op_name_records_skip` drift-guard test fired
  after the new enum value landed.  Replaying a canvas-materialise
  onto a branch would re-execute the Delta write against the
  OutputPort-hardcoded target FQN — the same semantic class as
  `DBT_MODEL` / `TRAIN_MODEL` / `WRITE_TABLE`, so it joins them in
  `UNSAFE_OPS` and the dispatcher refuses to replay it.
- Workspace-policy save now omits empty form rows instead of
  emitting `null` (rc204).  Several columns on
  `workspace_governance_policies` are `NOT NULL` with server
  defaults (`consent_required`, `consumption_enforcement`,
  `iso8601_enforcement`, `quota_enforcement`,
  `breaking_change_policy`); the old save factory blindly sent
  `null` for every undeclared field, then
  `governance_service.set_workspace_policy` did
  `setattr(row, field, None)` and the DB rejected the UPDATE
  with `IntegrityError: NOT NULL constraint failed: …`.  The
  factory now treats `''` as "no change" and skips the key
  entirely, mirroring `set_product_policy`'s docstring contract
  ("Only keys present in *fields* are written").  Workspace
  policy is the inheritance base — `null` can never validly mean
  "clear" on a NOT NULL column.

- Mega-Cluster 135–146 admin-surface browser-replay sweep
  (rc203).  First live UI replay against the four admin pages
  shipped in the Phase 141–146 closure wave surfaced a shared
  contract slip: every Alpine factory read `res.json?.…` from a
  `window.pqlApi.fetch(...)` return, but `pqlApi.fetch` wraps the
  parsed body under `res.data`.  Result: the Cedar policy-module
  list + dry-run + decision modal (Phase 141), the contract-tests
  "Latest run" card (Phase 142), the data-product Plan / Apply
  outcome panel (Phase 143), and the entity-discovery candidate
  queue (Phase 145) were all permanently empty in the browser.
  Five JS files corrected at source; the DP-apply factory also
  had a second bug — it POSTed the YAML body under `spec`, but
  `_spec_from_body` only accepts strings under `spec_yaml`, so
  the spec was treated as the request envelope and rejected with
  four pydantic field-missing errors.  Affected files:
  [admin_policy_modules.js](frontend/js/pages/admin_policy_modules.js),
  [data_product_contract_tests.js](frontend/js/pages/data_product_contract_tests.js),
  [admin_entity_discovery.js](frontend/js/pages/admin_entity_discovery.js),
  [admin_data_product_apply.js](frontend/js/pages/admin_data_product_apply.js).
  Found-bugs entries added to the four walkthroughs that cover
  these surfaces.  No new tests — the failures lived in the
  Alpine factory's read of the pqlApi return shape, which is not
  exercised by the existing pytest suite; future regressions
  belong on the Playwright e2e gate.

### Features

- Phase 146 Cost-Attribution + Quotas + Mesh-Health-Dashboard
  Closure (rc202).  Two new `hermes-plugin-pointlessql` tools
  complete the Phase 146 plugin scope: `pql_cost_by_consumer`
  (GET per-consumer cost rollup over a window; admin-only,
  mirrors the existing `pql_cost_by_product`) and
  `pql_set_workspace_quota` (PUT workspace-default quota fields
  `max_cost_per_day` / `max_queries_per_hour` /
  `quota_enforcement`).  Per-product quota overrides ride on
  the existing `pql_set_data_product_policy` since the three
  quota fields are part of POLICY_FIELDS.  Six new plugin
  pytest in `test_cost_quota_tools.py`; the
  `test_read_tools.py` Surface-Welle expected set grows from
  twenty to twenty-two — the full Surface-Welle plugin scope
  for Phase 135–146 is now complete.  Two new agent-flow
  walkthroughs: `docs/e2e-walkthroughs/mesh-cost-dashboard.md`
  (seven-step read flow over the cost-telemetry surface) and
  `docs/e2e-walkthroughs/product-quota-enforcement.md` (eight-
  step set → breach → 429 → product-override → warn-mode →
  cross-check flow).  ROADMAP Phase 146 flips 🟦 → ✅,
  closing the Mega-Cluster 135–146 substrate wave.

- Phase 145 Auto-Discovery Entity-Links Closure (rc201).  Three
  new `hermes-plugin-pointlessql` tools close the remaining
  plugin scope from the Phase 145 deferred-block:
  `pql_accept_entity_link_candidate` (POST promotion via the
  canonical `link_entities` helper),
  `pql_reject_entity_link_candidate` (POST decision=rejected),
  and `pql_defer_entity_link_candidate` (POST decision=deferred).
  Together with the already-shipped
  `pql_list_pending_entity_link_candidates`, the four tools
  close the agent-side of the steward review queue.  Seven new
  plugin pytest in `test_entity_discovery_tools.py`; the
  `test_read_tools.py` Surface-Welle expected set grows from
  seventeen to twenty.  New agent-flow walkthrough
  `docs/e2e-walkthroughs/entity-link-discovery.md` covers the
  eight-step list → inspect → accept → re-list → reject →
  defer → 409 conflict → run-now flow.  ROADMAP Phase 145
  flips 🟦 → ✅.

- Phase 144 Schema-Contract-Versioning Closure (rc200).  Three
  new `hermes-plugin-pointlessql` tools close the remaining
  plugin scope from the Phase 144 deferred-block:
  `pql_get_schema_version_history` (GET versions newest-first),
  `pql_propose_schema_bump` (POST a new schema and surface the
  computed MAJOR / MINOR / PATCH diff), and
  `pql_compute_schema_diff` (GET diff between two registered
  versions, with optional from / to bounds).  The
  `before_write` enforcement hook already ships via the
  Surface-Welle Backend-Completion commit; these tools cover
  the agent-authoring half of the loop.  Seven new plugin
  pytest in `test_schema_versioning_tools.py`; the
  `test_read_tools.py` Surface-Welle expected set grows from
  fourteen to seventeen.  New agent-flow walkthrough
  `docs/e2e-walkthroughs/output-port-schema-versioning.md`
  covers the eight-step list → MINOR bump → MAJOR bump → diff
  → before_write block → PATCH bump flow.  ROADMAP Phase 144
  flips 🟦 → ✅.

- Phase 143 Data-Product-as-Code Closure (rc199).  One new
  `hermes-plugin-pointlessql` tool closes the remaining plugin
  scope: `pql_data_product_export` snapshots a live data
  product into `DataProductSpec` form so the round-trip flow
  (plan → apply → export → plan-noop) holds end-to-end through
  the agent surface.  `pql_data_product_plan` and
  `pql_data_product_apply` already shipped in the Surface-Welle
  Backend-Completion wave.  Three new plugin pytest in
  `test_dp_as_code_export_tool.py`; the `test_read_tools.py`
  Surface-Welle expected set grows from thirteen to fourteen.
  New agent-flow walkthrough
  `docs/e2e-walkthroughs/data-product-as-code.md` covers the
  eight-step author → plan → apply → re-apply (idempotent) →
  export → round-trip → modify → re-apply flow.  ROADMAP
  Phase 143 flips 🟦 → ✅.

- Phase 142 Synthetic-Data + Contract-Tests Closure (rc198).
  Three new `hermes-plugin-pointlessql` tools close the
  remaining plugin scope from the Phase 142 deferred-block:
  `pql_declare_contract_test` (POST per-product, idempotent by
  name), `pql_declare_synthetic_fixture` (POST Faker-driven
  fixture for an output-port table), and `pql_run_contract_tests`
  (POST sync run in `synthetic` or `live` mode).  Each wraps a
  single existing steward/admin REST endpoint; arg-validation +
  error-envelope shape matches the rest of the plugin surface.
  Seven new plugin pytest in `test_contract_test_tools.py` cover
  happy paths + arg-error gates + registry shape; the
  `test_read_tools.py` Surface-Welle expected set grows from ten
  to thirteen.  New agent-flow walkthrough
  `docs/e2e-walkthroughs/data-product-contract-tests.md` covers
  the seven-step author → fixture → synthetic run → live run →
  read history flow.  ROADMAP Phase 142 flips 🟦 → ✅.

- Phase 141 Cedar Policy-as-Code Closure (rc197).  Four new
  `hermes-plugin-pointlessql` tools close the remaining plugin scope
  from the Phase 141 deferred-block: `pql_create_policy_module`,
  `pql_test_policy_module`, `pql_link_policy_module_to_product`, and
  `pql_list_policy_decisions`.  Each wraps a single existing admin
  REST endpoint; arg-validation + error-envelope shape matches the
  rest of the plugin surface.  Seven new plugin pytest cover happy
  paths + arg-error gates + registry shape; `test_read_tools.py`
  Surface-Welle expected set grows from six to ten.  New agent-flow
  walkthrough `docs/e2e-walkthroughs/computational-policy-as-code.md`
  complements the existing browser walkthrough
  `admin-policy-modules.md` — six numbered steps that author, dry-
  run, link, surface a forbid, and read the decision ledger end-to-
  end through the agent surface.  ROADMAP Phase 141 flips 🟦 → ✅.

- Surface-Welle 135–146 Backend-Completion + Admin-Surfaces
  (rc193).  Closes the dormant-substrate gap left by Phase 141–146:
  hooks were declared but never registered, the cost meter was wired
  but no caller fed it, three scheduler kinds were defined in the
  plan but missing from `build_default_registry`, and the discovery
  envelope did not surface the five new policy fields nor the four
  new top-level blocks (`policy_modules`, `contract_tests`,
  `fixtures`, `cost`).  Two new `_bootstrap.py` modules
  (`services/cost`, `services/schema_versioning`) register the
  before-read + before-write hooks alongside the existing Cedar
  bootstrap; all three idempotent registrars now fire from
  `api/_bootstrap/_lifespan.py` next to the api-key bootstrap.
  `services/lens/tools/query.py` records a `data_product_query_cost`
  row after the gate (and a row tagged with the cost-denied class on
  rejection).  `build_default_registry` gains `cost_rollup_hourly`,
  `contract_test_evaluation`, and `entity_link_discovery` — each a
  thin executor over the existing service surface, none cron-
  scheduled by default.  Discovery envelope extends with the missing
  policy fields, per-port `version_semver` + `schema_history`, and
  the four new blocks (additively — no existing key changed).  New
  `GET /api/data-products/{c}/{s}/point-in-time-read?as_of=` is the
  query-string sibling of the POST endpoint so plugin / UI consumers
  can resolve a single product's as-of manifest without a body.
  Four new admin surfaces (`/admin/policy-modules`,
  `/admin/mesh-dashboard`, `/admin/entity-discovery`,
  `/admin/data-product-apply`) expose the substrate to operators —
  each a self-contained Alpine page + page-level JS factory + HTML
  render route, with four matching cards on `/admin`.  23 new
  pytests (3972/0 full-suite green).  rc192 → rc193.
- Cost-Attribution + Quota-Enforcement + Mesh-Health-Dashboard
  (Phase 146 — Backend-only).  Substrat-Vertiefung Welle 7 des
  Mega-Cluster 135-146.  Migration `j7v9x1z3b5d7_phase146_cost_and_quotas`
  (down_rev `h5t7v9x1z3b5`) legt zwei Tabellen an:
  `data_product_query_cost` (raw per-query meter mit Cost +
  Bytes/Rows + Attribution principal/api_key/authoring/consumer
  product + query_kind + error_class) und
  `data_product_cost_buckets_hourly` (hourly rollup mit
  UNIQUE(bucket_hour, product, consumer_user) für idempotente
  re-runs).  ALTER workspace + product policy via SQLite
  batch_alter_table fügt max_cost_per_day Numeric(10,2),
  max_queries_per_hour Integer, quota_enforcement String(8) CHECK
  in (off, warn, strict) hinzu (workspace default 'off', product
  override nullable).  POLICY_FIELDS erweitert auf 12 Felder.
  PolicySpec (Phase 143) bekommt die drei neuen Felder.  Neue
  Exception `QuotaExceededError(PointlessSQLError)` mit
  status_code=429 und ErrorCode.QUOTA_EXCEEDED; carries metric,
  limit, observed, consumer_id, data_product_id als Extension-
  Members.  Service-Paket `services/cost/` mit Meter
  (record_query_cost + MeterContext dataclass; tabular insertion
  ins ledger), Quota (check_quota + resolve_quota_mode aggregieren
  current-day + current-hour aus bucket-table mit timezone-aware
  _same_hour helper, off=no-op, warn=outcome only, strict=raise),
  Rollup (roll_up_hourly_buckets aggregiert raw rows in buckets,
  idempotent via UPSERT-pattern), Dashboard (cost_by_product +
  cost_by_consumer als window-Aggregatoren; mesh_health_full
  layered auf existing services.mesh.mesh_health mit per_domain +
  cost_trend + top_consumers + recent_deliveries).  Routes
  `api/admin/cost_routes.py`: GET /api/mesh/health/full (any-user),
  GET /api/cost/by-product (steward/admin), GET
  /api/cost/by-consumer (admin only), PUT
  /api/admin/governance/quota (admin) für Workspace-Default-Quotas.
  21 neue pytest grün (test_cost_meter ×3 für persistence +
  no-attribution + float-input; test_cost_quota ×8 für off/warn/
  strict modes, cost+queries breach, below-limit-pass, stale-hour,
  resolve-mode-default, override; test_cost_rollup ×3 für creates-
  bucket, idempotent-on-rerun, skips-no-authoring; test_mesh_health_full
  ×7 für sums-buckets, groups-by-user, base-payload, per-domain,
  time-window, empty-workspace, top-10-truncated).  ADR-0012
  dokumentiert raw+rollup split, estimated-vs-real cost trade-off,
  off/warn/strict inheritance, fail-open vs fail-closed Wahl,
  offene Follow-Ups (engine-side cost, ledger-retention, cache TTL,
  SQL-side aggregation).  Asset rc191→rc192.  Deferred für
  Surface-Welle: pql/_hooks.py before_read check_quota integration
  (Substrat steht), Scheduler-Kind `cost_rollup_hourly`
  (default-enabled, 1h interval), services/lens/cost_gate.py
  Meter-Hook, Admin-Page /admin/mesh-dashboard mit Chart.js
  Cost-Trend-Lines + Per-Domain-Stacked-Bar + Freshness-Heatmap +
  Top-Consumers-Tabelle, Plugin-Tools (`pql_mesh_health_full`,
  `pql_cost_by_product`, `pql_cost_by_consumer`,
  `pql_set_data_product_quota`), Walkthroughs
  `mesh-cost-dashboard.md` + `product-quota-enforcement.md`.

- Auto-Discovery Entity-Links (Phase 145 — Backend-only).
  Substrat-Vertiefung Welle 6 des Mega-Cluster 135-146.  Migration
  `h5t7v9x1z3b5_phase145_entity_link_candidates` (down_rev
  `f3r5t7v9x1z3`) legt `entity_link_candidates` an (source +
  target FKs auf `data_product_entities`, CHECK kind in
  (same_as, derives_from), CHECK decision NULL or in
  (accepted, rejected, deferred), confidence_score Numeric(3,2),
  evidence_json Text, UNIQUE(source, target, kind) verhindert
  Duplikate auf scheduler-Ticks, index auf (decision, confidence)
  für pending-Queue-Listings).  Service-Erweiterung von
  `services/entities/` um `_candidates.py` (score_pk_overlap via
  Jaccard-similarity der PK-column-Sets, score_column_similarity
  via Token-Overlap auf entity_name nach snake/CamelCase-Splitting,
  score_combined als 60/40-gewichtete Summe, discover_candidates
  dedupliziert gegen existing entity_links + entity_link_candidates
  via UNIQUE) und `_review_queue.py` (list_pending_candidates
  sortiert nach confidence desc, accept_candidate promoted via
  existing link_entities-Helper, reject/defer stempeln decision +
  reviewed_at, double-decision raised ValueError).  Routes
  `api/data_products_routes/entity_candidates.py`:
  GET `/api/entity-link-candidates?status=pending|accepted|...`
  (any-user), POST `.../accept/.../reject/.../defer` (admin),
  POST `/api/admin/entity-discovery/run-now` (admin sync trigger).
  19 neue pytest grün (test_entity_candidate_scoring ×11 für
  Jaccard-pk-overlap-Edge-Cases, column-similarity-tokenisation,
  combined-weighted-sum, threshold-cutoff, dedup-against-links,
  dedup-against-candidates; test_entity_review_queue ×8 für
  pending-only-list, accept-promotes, reject-no-link, defer-
  separate-filter, double-decision-ValueError, unknown-LookupError,
  sort-by-confidence, pagination).  Asset rc190→rc191.  Deferred
  für Surface-Welle: Scheduler-Kind `entity_link_discovery`
  (default-disabled toggle), Admin-Surface `/admin/entity-discovery`
  mit Pending-Queue-Tabelle, Plugin-Tools
  (`pql_list_pending_entity_link_candidates`,
  `pql_accept_entity_link_candidate`, etc.), Walkthrough
  `entity-link-discovery.md`.

- Schema-Contract-Versioning (Phase 144 — Backend-only).
  Substrat-Vertiefung Welle 5 des Mega-Cluster 135-146.  Migration
  `f3r5t7v9x1z3_phase144_schema_versioning` (down_rev
  `d1p3r5t7v9x1`) erweitert
  `data_product_output_ports.version_semver` String(16) NOT NULL
  default "0.1.0", legt `output_port_schema_versions` an (Bump-
  History mit CHECK change_kind in (major,minor,patch) + unique
  (port_id, version_semver) + index on bumped_at), und fügt
  `breaking_change_policy` String(8) CHECK ('block','warn','off')
  auf workspace + product policy mit SQLite batch_alter_table
  hinzu.  Service-Paket `services/schema_versioning/` mit Diff
  (compute_diff klassifiziert in major/minor/patch/none nach Regeln
  removed/narrowed/not-null-tightened/added-not-null=major,
  added-nullable=minor, description-change=patch), Bumper
  (propose_bump verwendet packaging.Version), Enforcer
  (assert_schema_compatibility raised SchemaBreakingChangeError als
  PermissionDeniedError-Subclass → 403 bei block+major-diff;
  warn=outcome-only; off=no-op), CRUD (bump_port_version persistiert
  History-Row, advance port.version_semver, idempotent bei no-op
  diff).  Routes auf data-products router: GET
  `.../output-ports/{port_id}/versions`, POST `.../bump`
  (steward/admin), GET `.../diff?from_version=&to_version=`.
  POLICY_FIELDS um `breaking_change_policy` erweitert (jetzt 9
  Felder mit product⇐workspace inheritance).  22 neue pytest grün
  (test_schema_diff ×12 für alle Klassifikations-Regeln + collapse-
  to-strongest + edge-cases; test_schema_enforcer ×10 für
  propose_bump kinds, block-raise, warn-outcome, off-noop, no-port,
  port-semver advance, no-op-idempotent).  Asset rc189→rc190.
  Deferred für Surface-Welle: pql/_hooks.py before_write Hook
  Integration (Substrat-Helper existiert), Output-Port-Detail
  History-Liste + Diff-Viewer, Plugin-Tools
  (`pql_get_schema_version_history`, `pql_propose_schema_bump`,
  `pql_compute_schema_diff`), Walkthrough
  `output-port-schema-versioning.md`.

- Data-Product-as-Code (Phase 143 — Backend-only).
  Substrat-Vertiefung Welle 4 des Mega-Cluster 135-146.  Keine
  Migration — alles Service + Routes.  Neues Paket
  `services/data_product_as_code/` mit strict pydantic
  `DataProductSpec` (extra=`forbid`, `protected_namespaces=()` für
  `schema` field) + `parse_spec` (YAML oder dict), Planner
  (`plan_spec` walkt jede Subentity, vergleicht gegen DB-State,
  emittiert ordered Ops `additions`/`modifications`/`removals`),
  Applier (`apply_plan` dispatcht jeden Op an existing CRUD-Helpers
  — `create_output_port`, `declare_entity`, `declare_slo`,
  `declare_contract_test`, `declare_fixture`, `set_product_policy`
  — keine direct ORM-writes), Exporter (`export_data_product`
  snapshots live state in `DataProductSpec`; round-trip
  `apply→export→plan` ist no-op).  Routes
  `api/data_products_routes/apply.py`: POST `/api/data-products/plan`
  (any-user, dry-run), POST `/api/data-products/apply`
  (steward/admin, ?dry_run=), POST
  `/api/data-products/{c}/{s}/export` (any-user).
  SLO-unit-Auto-Resolution im Planner (wenn Spec unit=None, DB-unit
  wird als desired übernommen — sonst würde KIND_META's
  Auto-Assignment jedes Apply zu modification ops machen).
  16 neue pytest grün (test_dp_as_code_spec ×6 für strict-extra,
  blank-name, YAML-parse, round-trip dump; test_dp_as_code_planner_applier
  ×10 für empty-DB add-all, apply-creates-product, dry-run-no-write,
  idempotent-on-repeat, removal-op, modification-op,
  export-round-trip-noop, export-LookupError, policies-apply,
  policies-export).  ADR-0011 dokumentiert state-vs-migration-style,
  strict-spec-rationale, applier-reuses-CRUDs.  Asset rc188→rc189.
  Deferred für Surface-Welle: CLI (`pql apply / plan / export`),
  Admin-Surface `/admin/data-product-apply` (YAML Editor +
  Plan-Diff-View + Apply-Button), Plugin-Tools, Walkthrough
  `data-product-as-code.md`.

- Synthetic-Data + Contract-Tests (Phase 142 — Backend-only).
  Substrat-Vertiefung Welle 3 des Mega-Cluster 135-146.  Migration
  `d1p3r5t7v9x1_phase142_contract_tests` (down_rev `b9n1p3r5t7v9`)
  legt drei Tabellen an: `data_product_fixtures` (Faker-Spec pro
  declared table, unique pro Produkt), `data_product_contract_tests`
  (CHECK-bounded assertion_kind in row_count_range/column_present/
  value_distribution/null_rate/referential/freshness + severity +
  enabled), `data_product_contract_test_results` (append-only Ledger
  mit CHECK status pass/fail/error + Indizes auf
  contract_test_id+run_at).  Neue Dep `Faker>=24.0`.  Service-Paket
  `services/contract_tests/` mit Generator (deterministischer Arrow-
  Table-Builder mit 8 Generator-Kinds: email/name/int/float/
  iso8601_ts/choice/uuid/bool), Assertion-Evaluator (sechs Asserter,
  jeder retourniert AssertionVerdict mit Status + Observation-Dict),
  Runner (orchestriert run_contract_tests in `synthetic` oder
  `live` mode, persistiert Result-Row, emittiert
  `contract_test.run` Audit), CRUD (idempotent declare + delete +
  list für tests + fixtures + results pagination).  Routes
  `api/data_products_routes/contract_tests.py` mit GET/POST/DELETE
  für tests + fixtures (steward/admin POST+DELETE, any-user GET),
  POST `.../contract-tests/run?mode=` synchron, GET `.../results`
  paginated.  29 neue pytest grün (test_contract_test_generator ×8,
  test_contract_test_assertions ×15, test_contract_test_runner ×6).
  Asset rc187→rc188.  Scheduler-Kind `contract_test_evaluation`
  bleibt für die Surface-Welle deferred (default-disabled toggle,
  Frontend-Tab "Contract Tests" + Plugin-Tools).

- Computational Policy-as-Code via Cedar (Phase 141 — Backend-only).
  Erste Substrat-Vertiefung des Mega-Cluster 135–146.  Migration
  `b9n1p3r5t7v9_phase141_cedar_policies` (down_rev `z7l9n1p3r5t7`)
  legt zwei neue Tabellen an (`policy_modules`,
  `policy_module_decisions`) plus `linked_policy_module_ids` JSON
  column auf `workspace_governance_policies` +
  `data_product_policies`.  Neue Dep `cedarpy>=4.8` (PyO3-Bindings
  zur Cedar-Rust-Engine).  Service-Paket
  `services/policy_as_code/` mit Engine-Wrapper (per-`(module_id,
  version)`-Cache, fail-closed bei parse + runtime + empty), Loader
  (product⇐workspace Link-Inheritance), Translator
  (Principal/Action/Resource UID-Konvention), CRUD,
  Decision-Audit-Helper, und Bootstrap, der ein idempotentes
  before-read + before-write-Paar an die zentrale `pql/_hooks.py`
  Registry hängt.  Hooks resolvieren gelinkte Module für das
  Authoring-Produkt, evaluieren via `cedarpy.is_authorized`,
  persistieren die Decision separat vom Audit-Log, und werfen
  `PermissionDeniedError` bei `forbid` — Parse-/Runtime-Errors
  collapsen identisch zu `forbid` mit `error_class` im
  `context_json`.  Admin-Routes
  (GET/POST/PUT/DELETE `/api/admin/policy-modules`,
  POST `.../test` Dry-Run, GET `.../decisions` Ledger,
  PUT `/api/data-products/{c}/{s}/policy-modules` Link).
  POLICY_FIELDS-Inheritance auf 8 Felder erweitert.  ADR-0010
  dokumentiert die Decision (Cedar vs. OPA/DSL, ABAC-Begründung,
  Fail-Closed-Rationale).  23 neue pytest grün
  (test_cedar_engine + test_cedar_translator + test_cedar_hooks),
  full suite 3842/0/10, ruff/pyright/check-no-phase-refs clean.
  Frontend (Policy-Module-Editor mit CodeMirror Cedar-Syntax,
  Test-Sandbox, Decision-Log-View), Plugin-Tools
  (`pql_create_policy_module`, `pql_test_policy_module`,
  `pql_link_policy_module_to_product`,
  `pql_list_policy_decisions`), Walkthrough
  `computational-policy-as-code.md` bleiben für die finale
  Surface-Welle.  Asset rc186→rc187.

- Data-Mesh Buch-Vollständigkeit Foundation-Welle (Phase 135–140 —
  Backend-only).  Erste Welle des Mega-Cluster 135–146.  Migration-
  Kette `q8s0u2w5y7a9` → `z7l9n1p3r5t7` (6 chained revisions).
  Phase 135 (Entities + Glossary-Knowledge-Graph): drei neue Tabellen
  (`data_product_entities`, `entity_links`, `glossary_term_relations`),
  Polysemic-Identity-Resolver via `same_as`-Graph-BFS, bounded
  term-graph BFS für Glossary-Drawer.  Phase 136 (Correlation-IDs +
  ISO-8601-Enforcement): `correlation_id` auf 3 Audit-Tabellen +
  `iso8601_enforcement` CHECK column auf Workspace + Product Policy,
  ISO-8601-Validator mit warn/strict modes, POLICY_FIELDS-Inheritance
  erweitert.  Phase 137 (D5 Graph-Queries): upstream/downstream/
  shortest-path/cluster-by-domain auf der bestehenden Mesh-Graph-
  Substrat (F2-As-of-Substrate existiert bereits; route-`?as_of=`-
  Exposure deferred).  Phase 138 (G1 Interval-of-Change): neuer
  measurable SLO-Kind misst median/p95 inter-write-intervals via
  `data_product_contract_events`-Diffs; G2 Mesh-Health-Card MVP
  bereits in `services/mesh/_health.py`.  Phase 139 (E10 Port-Identity
  + B6 PQL-Hook-Registry): `identity_requirements` JSON-Spalte auf
  Output-Ports + Assert-Helper (OIDC-aud / scopes / min-role),
  zentrale `pql/_hooks.py` Hook-Registry (before/after read/write)
  mit Test-`HookContext`.  Phase 140 (Runtime-Messung der 4 Decl-only
  SLO-Kinds): 2 neue Substrat-Tabellen (Availability-Probes,
  Query-Perf-Samples) + 4 Measurer-Module + Dispatcher; precision/
  availability/performance lesen aus existing Snapshots,
  timeliness gibt Declaration-Sentinel zurück.  103 neue pytest grün,
  ruff/check-no-phase-refs/broad-except-hook clean.  Frontend-Panels,
  Plugin-Tools, Walkthroughs, Playwright-Replay über alle 6 Phasen
  bleiben für die nächste Welle (zusammen mit Phase 141–146:
  Cedar Policy-as-Code, Contract-Tests, DP-as-Code, Schema-
  Versioning, Entity-Auto-Discovery, Cost+Quotas+Dashboard).
  Asset rc180→rc186.

- Data-Mesh Quantum-Completeness (Phase 134 — Cluster Restschuld):
  vervollständigt die 129–133-Substrate zu nutzbarer Plattform.
  Neue Authoring-Product-Dependency (Header
  `X-PointlesSQL-Authoring-Product`, Query `?as_product=`, Session-
  State) plus geteilter Hook `enforce_consumption_for_read`
  eingehängt an drei Read-Routen (Export, Tabellen-Preview,
  SQL-Editor SELECT) — `strict` blockt jetzt mit HTTP 403 +
  strukturiertem Envelope, `advisory` schreibt ein Audit-Row und
  erlaubt. Bitemporal-Validate ist jetzt im Write-Path:
  `pql/_write.py` löst per Produkt `effective_policy(...)` auf,
  validiert die event-time-Spalte (raised
  `BitemporalRequirementError` bei `require_event_time=True` +
  Fehlen / falscher Dtype) und stempelt processing-time gemäß
  Policy.  Event-Port-Runtime ist live: CDF-Reader
  (deltalake-Wrapper), in-memory WS-Hub (broadcast/release-if-empty
  mirror coedit), Pump (advance-position + ledger + broadcast,
  scheduler-driven via neuen `event_port_pump`-Executor, gated by
  `EventPortSettings.enabled`), plus vier neue Endpunkte: HTTP
  chunked NDJSON-Stream (`GET .../events`), WebSocket-Live-Push
  (`WS .../events`), Subscription-CRUD und pause/resume/rewind-
  Control.  Sechs neue Overview-Panels (lifecycle, bitemporal,
  infrastructure, use-cases + rating, consumption, event-port)
  mit sieben neuen Alpine-Factories.  Vier neue REST-Modules
  (`bitemporal_policy.py`, `infrastructure.py`, `consumer_voice.py`,
  `consumption_events.py`).  13 neue Hermes-Plugin-Tools im
  Cross-Repo (`data_mesh_extras.py`): lifecycle set/propose,
  consumption set/ack, bitemporal get/set, infrastructure set,
  use-cases add/vote, rating, event-port subscribe/read/control.
  Sechs neue Playwright-Walkthroughs (live-replay-gate deferred).
  47 neue pytest (37 Platform + 10 Plugin), full suite grün,
  ruff/pyright clean, alembic round-trip clean.  Asset bump
  rc179→rc180.
- Data-Mesh Quantum-Completeness (Cluster 129–133): backend foundation
  for the six genuinely-missing capabilities the gap analysis flagged
  after 124–128 shipped. **Phase 129 — Product Lifecycle**: a
  `lifecycle_state` (draft/active/deprecated/retired/archived) on every
  data product with a guarded state-machine, audit-driven history,
  steward/admin transitions + an any-user `propose` path for supervised
  agents, and a `lifecycle` block in the discovery envelope carrying
  the optional `replacement_uri` for retired successors. **Phase 130 —
  Consumption Enforcement**: a `consumption_enforcement`
  (off/advisory/strict, default advisory) field on the per-product +
  workspace-default policy with a `ConsumptionVerdict` service that
  resolves "is this read declared as an input port?" — route hooks at
  export/table-preview/SQL-editor deferred to a later wiring pass.
  **Phase 131 — Bitemporality Standardization**: workspace settings
  gain `enforcement` (off/opt_in/required) and `require_event_time`; a
  new `data_product_bitemporal_policy` table allows per-product
  override; a `validate_event_time_column` helper raises
  `BitemporalRequirementError` when required columns are absent or
  non-temporal. **Phase 132 — Infrastructure + Consumer Voice**: four
  new tables for producer-declared infrastructure (storage class,
  compute runtime, access methods, region) and consumer-contributed
  metadata (use cases with idempotent up/down-votes, 1-5 ratings with
  upsert and avg+count summary); all three blocks surface in the
  discovery envelope. **Phase 133 — Event-Stream Output Port (substrate)**:
  durable `data_product_event_subscriptions` with a Delta-CDF
  position cursor, a `data_product_event_deliveries` audit ledger, and
  a subscription CRUD that validates the referenced output port is
  `kind='event'`; the pump + WS hub + streaming endpoints stay
  deferred until `EventPortSettings.enabled` is flipped. Cluster
  total: 70 new pytest, full suite 3701/0/10 green, ruff clean,
  alembic 124→133 round-trips clean.
- Data-Mesh Interoperability & Mesh-Observability: closes the
  Data-Mesh maturity model. An **emergent mesh graph** built from each
  product's declared `upstream_product` input ports (products as nodes,
  declared upstreams as edges) at `/mesh` + a per-product neighbourhood
  on a new **Interop tab**. A **polysemic identifier** registry
  (admin-curated mesh entities + per-product column bindings) that powers
  a **cross-product join helper** (suggests shared-entity join keys +
  sample SQL). **Point-in-time** cross-product reads (`resolve_as_of`
  resolves each declared table's Delta version at an instant; the heavy
  read stays a PQL primitive). A **full SLO set** per product
  (freshness/timeliness/completeness/volume/statistical-shape/lineage/
  precision-accuracy/availability/performance) with live verdicts on the
  Overview SLO panel — honest split: the platform measures the ones
  derivable from the self-generated statistics + Delta history
  (freshness, volume, completeness, statistical-shape drift via z-score,
  lineage coverage) and honestly declares the rest. A **mesh-health
  dashboard** (`/mesh/health`) rolling SLO bands across all products + an
  `slo_evaluation` scheduler job (and admin "evaluate now") that flags
  failing objectives into the audit log (`slo.violation`).
  **Bitemporality** as an opt-in processing-time injection at write
  (default off — it evolves the Delta schema) plus a documented
  event/business-time convention + a `table_as_of_event_time` read
  helper. **Correlation-ids** (`X-Correlation-ID`, falling back to the
  request id) stamped on every `agent_run_operations` row, with a
  cross-product trace at `GET /api/mesh/trace/{id}`. The discovery
  envelope gains `entities` + `bitemporal` blocks, a populated
  `slos.additional`, and a `mesh` link. Agents read + propose via the
  `pql_get_mesh_graph` / `pql_get_mesh_health` /
  `pql_declare_data_product_slo` / `pql_register_mesh_entity` /
  `pql_bind_mesh_entity_column` hermes tools.
- Data-Mesh Computational Governance: per-product policy-as-code with
  workspace-default inheritance (retention, encryption class, residency,
  consent), column confidentiality classification (public/internal/
  confidential/pii/phi) that drives **read-time masking** at the
  product's access points (export port + table preview exactly; SQL
  editor best-effort — notebook-kernel SQL is a documented gap), a
  Control-Port with a **right-to-be-forgotten** operation (steward/admin
  executes immediately, agents only propose; subject value stored only
  hashed), a policy-compliance scanner (`policy_compliance` scheduler
  job + admin "scan now") that flags retention-overdue + unclassified
  PII-looking columns into the audit log with a trust-downgrade chip,
  and an aggregate-ownership suggestion.  Honest split: retention is
  monitored and PII masking + erasure are enforced, while encryption
  class / residency / consent are declarations surfaced in the discovery
  contract.  Agents propose policies + classifications via the
  `pql_get_data_product_policy` / `pql_set_data_product_policy` /
  `pql_classify_data_product_column` /
  `pql_request_right_to_be_forgotten` hermes tools.
- Data-Mesh Quantum-Ports & Discovery: data products gain declared
  output/input ports (with declared-upstream lineage), a per-product
  semantic model + sample query, self-generated statistics stamped at
  write time, a machine-readable discovery contract with a stable
  `urn:pointlessql:product:…` URI, a working Parquet file-export port,
  and a workspace business glossary (term→column bindings surfaced as
  Contract-tab badges).  Agents propose ports + read discovery via the
  `pql_get_data_product_discovery` / `pql_add_data_product_*_port`
  hermes tools (steward/admin-gated).
- Data-Mesh Domänen-Fundament: `Domain` / `domain_members` entities,
  product↔domain assignment, and notebook/dbt transformation binding,
  with admin CRUD + read-only browse and the `pql_list_domains` /
  `pql_assign_data_product_domain` hermes tools.

### Fixes

- Data-product detail tabs: the **Governance** and **Interop** tabs
  (and Diff / Lineage / Compliance / Activity) rendered blank when
  selected — the Contract-tab partial was missing a closing `</div>`, so
  every tab pane declared after it was parsed as a child of the Contract
  pane and hidden whenever Contract was the inactive (hidden) tab. Added
  the missing close so the panes are siblings again. Surfaced by the
  first browser-replay of the Data-Mesh UI cluster.

### Documentation

- Four end-to-end walkthrough playbooks covering the Data-Mesh UI
  cluster (`data-domains`, `data-product-discovery`, `data-governance`,
  `data-mesh`) plus an idempotent `scripts/seed-mesh-demo.py` that seeds
  the replay substrate (two products with an upstream edge, statistics,
  and one passing / one failing SLO).

## [Cluster 22 — Phase 122–123 Publication-readiness] - 2026-05-25

> Phase 122 (Source-Code Sanitization for Publication: 1622→260 phase refs across 4 sprints; CLAUDE.md forward-guard for templates/JS/CSS/UI strings; README outside-reader polish), Phase 123 (Frontend Master-Plan 8-wave modernisation: forward-guard W1, inline-script-exodus W2, JS-subsystem-splits W3, template-splits+macros W4, CSS-architektur W5, docs W6, JS-quality W7 (biome), A11y form-labels W8).



### Bug Fixes

- Update coedit live-pill class to pql-vital-pill--success (da61519)

### Chores

- W1.2 — extend forward-guard rule + add frontend pre-commit hook (175013d)
- W7.0 — biome.json + jsconfig.json scaffold (no source touch) (07c5991)
- W7.1 — biome format --write sweep over frontend/js/ (rc164→rc165) (b0b1925)
- W7.2 — biome check --write safe lint fixes (rc165→rc166) (89b899e)
- W7.3 — biome pre-commit hook + CI gate (rc166→rc167) (7bf1419)

### Documentation

- Phase 122.3 — e2e-walkthroughs feature-rename + content-clean (rc140→rc141) (ee4f077)
- Phase 122.4 — README outside-reader polish + CLAUDE.md forward guard (rc141→rc142) (b3566ea)
- Phase 122 close-out (f9def75)
- Frontend W6.1 — new docs/development/frontend-architecture.md (74c6efd)
- Frontend W6.2 — refresh design-tokens.md post-W5 (9b3ca83)
- Frontend W6.3 — refresh frontend-conventions.md post-W2/W3/W4/W5 (330670c)
- Frontend W6.4 — refresh js/README + new templates/_macros/README (55488ca)
- W7.4 — JSDoc @typedef backbone for 3 mid-size factories (7b96a44)
- W7.5 — composed @typedef for notebookEditor + 4 slice typedefs (fcabec0)
- Phase 123 — Frontend Master-Plan 8-wave close-out (05ceed0)

### Features

- W4.0 — badge/button/state_container macros (rc156→rc157) (688865f)
- W8.0 — labeled_input/select/textarea macros for A11y (df9ed6d)
- W8.1 — aria-label on remaining 4 unlabeled search inputs (258ea40)
- W8.2 — migrate ingest_sources_new.html to labeled_input macro (124918b)
- W8.3 — migrate admin_audit_sinks.html create-form to macros (fc944d3)
- W8.4 — modal-form sweep migrates 6 page-forms to A11y macros (fe7c52e)
- W8.5 — tail-sweep adds aria-label / for/id pairs across 23 templates (f76c672)
- W8.6 — form-label A11y drift guard (script + pre-commit + CI) (0adaca5)

### Refactor

- Phase 122.1 — mechanical strip of phase/sprint/wave refs (rc138→rc139) (69c33fe)
- Phase 122.2 — manual cleanup of woven references + test renames (rc139→rc140) (5ca77eb)
- W1.1 — Phase/Sprint/Wave strip from frontend source (0cac177)
- W2.1 — extract feed page factory into ESM module (7fbe83d)
- W2.2 — extract data_product detail factory into ESM module (7cee5f0)
- W2.3 — extract model.html six factories into ESM module (1388291)
- W2.4 — split base.html into five side-effect ESM modules (abe6a57)
- W2.5 — extract three notebook-editor-adjacent factories (cbd0768)
- W2.6 — extract six admin/dashboard page scripts (b60aba1)
- W2.7 — extract ten Tier-3 page factories (91319f8)
- W2.8 — final Tier-3 sweep, 31 inline scripts extracted (e86d0bf)
- W3.3c — split variable_inspector out of kernel_execution.js (rc150→rc151) (cfc8507)
- W3.3d — split revision_diff out of revisions.js (rc151→rc152) (aa2f206)
- W3.3e — extract jsonFetch into frontend/js/http.js (rc152→rc153) (fa70835)
- W3.3b — split review_decision + cell_tag_picker out of cell_thread.js (rc153→rc154) (62bdbf4)
- W3.3a — split coedit.js into core + awareness + cell_binding (rc154→rc155) (6c8debe)
- W4.1 — split tab_lineage.html into 5 sub-partials (rc157→rc158) (41471fe)
- W4.2 — split branch_detail.html into 4 sub-partials (rc158→rc159) (edefc7d)
- W4.3 — split revisions_panel.html into 4 sub-partials (rc159→rc160) (8eb8bb1)
- W4.4 — split sql_editor.html into 4 sub-partials (rc160→rc161) (22b8615)
- W4.5 — split meta_panel.html into 8 sub-partials (rc161→rc162) (708d04d)
- W5.1 — split notebook.css into 7 sub-files (rc162→rc163) (761e4e2)
- W5.2 — drop 18 dead CSS selectors (rc163→rc164) (cc1cf10)

### Tests

- Relax source-substring assertion to tolerate Biome arrow fn (df36889)

## [Cluster 21 — Phase 118–121 API-Key family + Restschuld V tail] - 2026-05-24

> Phase 118 (token format pql_{env}_v1_{body40}_{crc8} + admin surface), Phase 119 (API-key lifecycle: TTL + rotation + soft-quarantine), Phase 120 (API-key ACLs + usage dashboard: 3 CASCADE tables + 6 admin endpoints), Phase 121 (Restschuld V: 9 sub-sprints — error-envelope unification, pagination service-layer rollout, soyuz facade completion, pydoclint tightening, settings cache, micro-extractions, PII redaction in audit details).



### Bug Fixes

- Surface analyst + sql_execute scopes on the API-keys page (709ba91)
- Phase 120 replay-pass — 3 UX bugs surfaced + fixed (94a8b73)
- Phase 121.9a — close 7 pre-existing test failures (a285165)

### Chores

- Phase 121.5 — pydoclint tightening + D401 imperative-mood sweep (96bd4c2)
- Phase 121.9b — working-tree hygiene + .gitignore phase-replay (b92442a)

### Documentation

- Phase 118.5 — close-out, walkthrough, asset bump rc122→rc123 (4e95151)
- Phase 119.6 — close-out, walkthrough, asset bump rc123→rc124 (ebccc22)
- Phase 120.7 — close-out, walkthrough, asset bump rc124→rc125 (55dd864)
- Phase 121.2 + 121.5 + 121.3 + 121.6 close-out (842559a)
- Phase 121.7 + 121.4 close-out (4d3f37c)
- Phase 121.8 close-out + Phase 121 done (9516c1d)
- Phase 121.9 close-out (475bb72)

### Features

- Phase 118.1 — schema columns for token format v1 (9b6c2e8)
- Phase 118.2 — pql_{env}_v1_{body40}_{crc8} token format (d1097e7)
- Phase 118.3 — wire v1 format into create + verify (ea33030)
- Phase 118.4 — admin JSON + HTML surface v1 token env (386f2da)
- Phase 119.1 — lifecycle schema (TTL/rotation/quarantine) (31652bb)
- Phase 119.2 — lifecycle gates in verify_bearer (01b102e)
- Phase 119.3 — rotate/quarantine/unquarantine/TTL endpoints (44f7643)
- Phase 119.4 — lifecycle sweep + lifespan wiring (831da96)
- Phase 119.5 — admin HTML TTL chooser + lifecycle actions (c4a1f9e)
- Phase 120.1 — ACL + usage schema (3 tables) (eb29d43)
- Phase 120.2 — _acl.py pure-function checks (8dfec6d)
- Phase 120.3 — wire IP gate + catalog gate into routes (9d67c3c)
- Phase 120.4 — grants CRUD admin endpoints (043e0b7)
- Phase 120.5 — usage record + flush + retention (1d5cc54)
- Phase 120.6 — per-key detail page + grants editor (4ce9d61)
- Phase 121.1 — error-envelope unification (201→13 sites) (e1e9054)
- Phase 121.2 — Settings cache + pagination dep (a54f95c)
- Phase 121.3 — Soyuz facade completion (ml_routes + TID251 ban) (782c7dd)
- Phase 121.7c — PII redaction in audit log details (67f4e64)
- Phase 121.4 — require_role factory + PrivilegeSettings scaffold (be0a838)

### Refactor

- Phase 121.6 — four micro-extractions (37d35dc)
- Phase 121.7a — admin_uc rollout to final candidate (6432829)
- Phase 121.7b — pagination dep rollout (6 routes) (6128cd6)
- Phase 121.8a — tests/ + admin_uc lint baseline (5462b46)
- Phase 121.8b — pagination service-layer rollout (85a4a42)

## [Cluster 20 — Phase 115–117 Drag-drop + Toolbar + SQL Statement API] - 2026-05-23

> Phase 115 (cell drag-drop reorder + CRDT sync + header-as-handle + live-splice FLIP), Phase 116 (notebook editor toolbar redesign: vital pills v2 + Save/Run state buttons), Phase 117 (external SQL Statement Execution API at /api/2.0/sql/statements; SELECT-only v1; Bearer-only auth).



### Bug Fixes

- Phase 115.2 — manual drag works + live-splice FLIP animation (5d68fdb)

### Features

- Phase 115 — cell drag-drop reorder + CRDT sync (df513f2)
- Phase 116 — toolbar redesign with vital pills + Save/Run state buttons (12fa00c)
- Phase 117 — external SQL Statement Execution API (9f18e63)

### Refactor

- Phase 115.1 — header-as-drag-handle (desktop window style) (08713a4)
- Phase 115.3 — workspace sidebar matches audit/lens panel breathing room (265b224)

## [Cluster 19 — Phase 107–114 post-Notebook UI + Co-edit bus + Branch backend] - 2026-05-23

> Phase 107 (toolbar icon-only mode + close-all panels), Phase 108 (live-server + multi-tab Playwright CI gate + replay-worker test), Phase 109 (multi-worker co-edit bus PG LISTEN/NOTIFY + admin status endpoint), Phase 110 (Restschuld IV modularization: 9 splits), Phase 111 (Restschuld V wave: 7 splits, restschuld pipeline empty), Phase 112+113 (right meta panel + editor surface consolidation: tabbed Schedule+Run + unified right drawer), Phase 114 (Workspace navigation overhaul: tree + filter + drag-drop + inline rename).



### Bug Fixes

- Phase 106.6 — restore ruff baseline after 106.1 cleanup (2da45b2)
- Two replay-surfaced editor bugs (rc87 → rc88) (a4a87b2)
- Phase 107 hotfix — cellEditor seeds from populated ytext on mount (rc90 → rc91) (1461a08)
- Phase 108 follow-up — coedit awareness initial broadcast (56fa203)
- Re-export _detect_rejects from _merge package facade (bf6bd1c)
- Add 'show' class to run modal binding for opacity transition (8ae1551)
- Contain wheel-scroll inside sticky side panels + thin scrollbar (75f0607)
- Shell-locked layout — side panels no longer 'lift' at scroll end (c2638fb)

### Documentation

- Close Phase 100 + 103 + 104 status flip (Wave-D shipped earlier) (3461b18)
- Phase 108 closure — multi-tab CI gate + Phase 103 worker test (2ca880b)
- Phase 109 closure — multi-worker co-edit bus (d78fac8)
- Phase 110 closure — Restschuld IV modularization wave (3ffdd40)
- Phase 111.1 partial — sql_parser modularization (aa7bd3a)
- Phase 111.2 + 111.3 — _merge + run_diff modularization (8bf4c69)
- Phase 111 closed — Restschuld V wave complete (6a8c219)
- Phase 112 + Phase 113 closure entries (7de34c5)
- Phase 114 closed — Workspace navigation overhaul (d689b2d)

### Features

- Close Phase 99 widgets shim + 105.6 agent-presence + sync-timing rebind (b8468ce)
- Phase 101 closure — agent-as-reviewer on polymorphic comments (aa3ae98)
- Phase 102 Track-H — HMAC-signed promote-reviewer webhook (808f5d6)
- Phase 102 Track-I — env-bridge end-to-end tests, closes Phase 102 (5331855)
- Phase 107.3 — workspace row edit-slot alignment (rc88 → rc89) (3d05658)
- Phase 107.1+107.2 — toolbar icon-only mode + close-all panels (rc89 → rc90) (c977ea7)
- Phase 108.1 — live-server + Playwright e2e fixtures (3eea7d4)
- Phase 108.2 — multi-tab co-edit CI gate (ec6b5a4)
- Phase 109.1 — coedit_bus PG LISTEN/NOTIFY scaffold (d64722c)
- Phase 109.2 — wire coedit_hub to cross-worker bus (b832567)
- Phase 109.3 — coedit-bus status endpoint (fbc40ee)
- Phase 112 + Sprint 112.5 — right meta panel & content split (1cf29a0)
- Sprint 113.1 — collapse cell-header verbs into one ⋯ menu (74b9e6f)
- Sprint 113.3 — unify Schedule + Run-Once into one tabbed modal (879feed)
- Sprint 113.2 — unify Chat + Variables + Social into one tabbed right drawer (f3803f7)
- Phase 113 polish — drawer/meta coexistence, self-author chip suppression, cleaner schedule name (8f69c24)
- Add Run all + Run all above + Run this and below (0921bf5)
- Run-all toolbar becomes Bootstrap split-button (67fd367)
- Per-cell Run split-button + scroll-past-end (a8de796)
- Per-cell Run split-button + cell-flush scroll-past-end (dca77f2)
- Phase 114.1 — workspace sidebar tree + search + edit-route highlight (1ea7220)
- Phase 114.2 — workspace right-click menu + keyboard nav (3132940)
- Phase 114.3 — workspace drag-drop move + inline rename (d1415ec)

### Refactor

- Phase 106.5 — typed Pydantic bodies on 4 chat-proposal routes (eb79725)
- Phase 110.1 — split executors.py into per-kind package (848bd26)
- Phase 110.2 — split runs.py into per-axis package (2fefb34)
- Phase 110.3 — split console.py into per-route package (c0f44bf)
- Phase 110.4 — split views.py into per-surface package (38c387e)
- Phase 110.5 — split comments.py into per-surface package (f72b1a4)
- Phase 110.6 — split notebook_kernel_ws.py per layer (c357215)
- Phase 110.7 — split issues.py per CRUD verb (8afd04f)
- Phase 110.8 — split active_reviewer.py per concern (a514aa9)
- Phase 110.9 — split sql/write.py per route family (2f49c14)
- Phase 111.1 — split sql_parser.py per concern (46c282c)
- Phase 111.2 — split _merge.py per concern (d04cbf3)
- Phase 111.3 — split run_diff.py per concern (1673579)
- Phase 111.4 — split _loaders.py into per-axis package (0e24c97)
- Phase 111.5 — split entity_registry.py into per-concern package (1e42413)
- Phase 111.6 — split notebook_coedit_ws.py into per-concern package (869daf5)
- Phase 111.7 — split PQL class into base + 2 mixins (230a709)

### Style

- Bump context-row typography for breathable file list (c053ac4)

### Tests

- Phase 108.3 — replay worker happy-path test (c05c94a)

## [Cluster 18 — Phase 95–106 Notebook v3 (Cell-social + Co-edit composite)] - 2026-05-21

> Largest single cluster: Phase 95 (cell-level social), Phase 96 (inline AI-Assistant + sql_chat→editor_chat rename), Phase 97 (revision history + cell-diff), Phase 98 (notebook tags + magic + cell-lineage + export), Phase 99 (widgets + permissions), Phase 100 (publish/snapshot), Phase 101 (per-cell authorship + AI-acceptance hook), Phase 102 (branch-aware notebooks), Phase 103-104 (replay/scenario + NL→Notebook sequence proposals), Phase 105 (real-time co-edit via Y.Doc + awareness + agent-presence + compaction scheduler), Phase 106 hygiene close.



### Bug Fixes

- Drop $root. prefix — Alpine 3 resolves it to inner factory (a08e369)
- Revision-diff UX polish + duplicate-:key crash (2012ae1)
- Phase 97.X.3 pin fanout — resolve notebook-level followers (eba6923)
- Phase 97.X.3.2 pin-card UX polish + Welcome banner above empty-state (a494644)

### Documentation

- Flip parent-tree markers + expand status legend (6f31e84)
- Wave-D close-out — CHANGELOG entries + ROADMAP burn-down summary (10ea450)
- Phase 105.7 — multi-tab co-edit Playwright playbook (62fd58b)
- Record Phase 105 open follow-ups so they're not lost (486c6d1)
- Close Phase 106 hygiene-wave (106.1+106.2+106.3 landed; 106.4-106.7 deferred) (177dd8a)

### Features

- Phase 95 — cell-level social (comments / reactions / follows / tags) (d5b01a6)
- Phase 96 — inline AI-Assistant in notebook editor (5e486f0)
- Phase 98.A — magic-command pre-processor (%sql/%md/%fs ls/%timeit) (a239918)
- Phase 98.B — notebook tags + template gallery (a325ca9)
- Phase 98.C — cell-level lineage badges (backend) (554b6f3)
- Phase 98.D — static HTML / PDF export (43d6d0c)
- Phase 97 — revision history + cell-diff (backend) (fda02a0)
- Phase 101 — per-cell authorship attribution (backend) (cd531b2)
- Phase 99 — widget-cells + per-notebook permissions (backend) (f90581d)
- Phase 100 — publish notebook (share + dashboard, backend) (30b0ab0)
- Phase 102 — branch-aware notebooks (backend) (e809004)
- Phase 103 — replay / scenario-mode (backend) (a23be57)
- Phase 104 — NL→Notebook cell-sequence proposals (backend) (adbcfa8)
- Phase 101 follow-up + Phase 105 on-ice decision (d9d2166)
- Wave B (Tags / Author-Chip / Share) + Phase 105 fixes (443b314)
- Phase 101 AI-acceptance authorship hook (19faebc)
- Wave-C + Phase 99 UI — four deferred backends wired (6f685a0)
- Wave-D-1 — workspace tag-pills + reviewer-per-cell affordance (0960e79)
- Wave-D-2 — cell-lineage chip + revision-history panel (20530ff)
- Wave-D-3 — pql.widgets + pql.context + Phase-99 role enforcement (058f038)
- Wave-D-4 — share secret-scrub + iframe-embed route (e91da74)
- Wave-D-5 — replay re-execution worker (Phase 103) (b9d67d8)
- Wave-D-6a — sign-revision receive + branch-promote webhook (8c5249a)
- Public share viewer now extends a stripped base layout (9c1b4ac)
- Phase 97 Rest backend — pin-to-memory facts (36dc878)
- Phase 97 Rest UI — pin-as-fact buttons + facts library (cfaad5c)
- Phase 105.1 backend — pycrdt sidecar persistence (389f023)
- Phase 97 closure — pin feed-card + ROADMAP flip (bfec45c)
- Phase 105.2 — co-edit WS hub with sync + awareness relay (59c06e2)
- Phase 105.3 — co-edit Y.Doc client scaffold + live pill (db5be5d)
- Phase 105.4 — co-edit awareness layer (0211153)
- Phase 105.5 — co-edit save-path barrier (01f634d)
- Phase 105.3b — per-cell CodeMirror co-edit binding (6a60551)
- Phase 105.6 — agent presence on co-edit (c65a221)
- Phase 105.8 — coedit compaction executor (closes Phase 105) (d2560e8)

### Refactor

- Rename sql_chat → editor_chat (Phase 96 preamble) (52d2f1e)
- Phase 106.3 — split notebook.py into per-phase subpackage (fef6d68)
- Phase 106.1+106.2 — domain-exception migration + docstring sync (28db246)

### Style

- Theme revision-diff card with --pql-color-* tokens (74315da)
- Theme + brand the public share / export viewer (2ffc374)
- Cell-card chrome + status footer + Read-only pill (c3dff4c)

## [Cluster 17 — Phase 90–94 NL→SQL + Memory + Vector-Search] - 2026-05-19

> Phase 90 (pql.memory facade + /memory/<agent-id> brain browser), Phase 91 (NL→SQL chat panel via in-process hermes-agent), Phase 92 (vector-search compute primitive + 5 follow-ups).



### Bug Fixes

- Wire workspace_repos field into Settings root (cde1e7b)
- Phase 92 walkthrough fixes — file:// + Alpine race (79f2522)

### Chores

- Drop closed-phase audit artefacts (7b70fc6)

### Documentation

- Move stale ROADMAP_ARCHIVE.md + QUALITY_FINAL.md into docs/internal/ (fa0cb80)

### Features

- Phase 90 — pql.memory facade + /memory/<agent-id> brain browser (e05cf30)
- Phase 91 — NL→SQL chat panel via in-process hermes-agent (dea6278)
- Phase 92 — vector-search compute primitive (1c8a302)
- Five Phase 92 follow-ups (UI + cleanup + docs) (612cf07)

### Refactor

- Consolidate docker files into docker/ folder (d99d7a5)
- Consolidate dbt_project + grafana + yaml.example into examples/ (c350732)

## [Cluster 16 — Phase 87–89 Restschuld I–III] - 2026-05-16

> Phase 87 (config/_settings + repo_assets + audit/_legacy splits), Phase 88 (SQL/dbt cluster: _dispatcher + editor + dbt/routes), Phase 89 (Restschuld III endgame: _polymorphic_handlers 9-axis split + main.py lifespan extraction).



### Documentation

- Close Phase 87 — Restschuld I (config + repo_assets + audit) (e2c1e13)
- Close Phase 88 — Restschuld II (SQL/dbt cluster) (8c41fd0)
- Close Phase 89 — Restschuld III endgame (7e551e9)

### Refactor

- Split _settings.py into topical sub-package (Phase 87.1) (1c4d337)
- Delete orphaned dashboards/saved-queries loader (Phase 87.2) (f3c7e07)
- Split _legacy.py monolith into 7 axis modules (Phase 87.3) (6d2ac2d)
- Split _dispatcher.py into 7-module package (Phase 88.1) (ef837c3)
- Split editor.py into 7-module package (Phase 88.2) (05ea3d2)
- Split routes.py helpers into 5 sibling modules (Phase 88.3) (517a4b6)
- Split _polymorphic_handlers.py into 9-axis package (Phase 89.1) (d1716ce)
- Extract lifespan from main.py to _bootstrap/_lifespan.py (Phase 89.2) (76e6941)

## [Cluster 15 — Phase 82–86 Ingest UI + Modularisation] - 2026-05-16

> Phase 82 (Ingest UI: 6 sub-phases, 7 connectors, 60 new pytest), Phase 83-85 (Saved Views + VQB + DP GitHub-polish + dataflow canvas), Phase 86 (modularisation + dedup wave: feed/jobs/alerts/governance routes split, get_templates centralization, star.js extract).



### Bug Fixes

- Two Playwright-surfaced bugs in Phase 83/84 hero pages (9731bef)
- Dark-mode unreadable code blocks on Consume/Canvas/View (b93c0a3)
- Catalog sidebar entry double-highlighted on /ingest /views /canvas (d750759)
- Drop ``table-light`` from embed thead in dark mode (068408f)

### Documentation

- Close Phase 82 — Ingest UI shipped (84851c6)
- Close Phases 83–85 — strategic axes shipped (fd2785f)
- Close Phase 86 — modularisation + dedup wave (4edf6a3)

### Features

- 82.0 foundation — model, migration, service skeleton, job-kind (94c41f9)
- 82.1 probe + create form (all 7 connector kinds) (ca82455)
- 82.2 table-picker + target-FQN mappings (bdde2d8)
- 82.3 manual pull + scheduled pull + fanout (f61c425)
- 82.5 health monitor + DP health-band (3dac01a)
- Phase 83.1 — Saved Views (parameterised SELECT-only) (1da0fd8)
- Phase 83.2 — Visual Query Builder toggle (55c0029)
- Phase 84 — GitHub-feel polish bundle (624f5e0)
- Phase 85.1 — Dataflow canvas prototype (2d18302)

### Refactor

- Centralize get_templates() and HTMX-detection helpers (Phase 86 C.1+C.2) (d26ed10)
- Split 3 mega-templates into page-scoped partials (Phase 86 A1-A3) (e7d0a78)
- Split feed_routes.py into per-axis sub-package (Phase 86 B1) (469e3a4)
- Split home_routes.py into per-axis sub-package (Phase 86 B2) (fd07577)
- Split jobs_routes.py into per-axis sub-package (Phase 86 B3) (00ce745)
- Extract Jinja filters + context wrapper from main.py (Phase 86 B4 partial) (68dbdf1)
- Split alerts_routes.py into per-axis sub-package (Phase 86 B5) (7f65aec)
- Split governance_routes.py into per-axis sub-package (Phase 86 B6) (c637888)
- Extract starred-items factory from base.html into star.js (Phase 86 D) (9696608)
- Remove duplicate anonymous_client fixtures (Phase 86 C.4) (0f999c3)

### Tests

- 82.4 end-to-end fixture coverage for all 7 connectors (dd57b26)

## [Cluster 14 — Phase 78–81 (Hygiene + Phase 81 feed/launchpad)] - 2026-05-16

> Phase 78-79 (stale-comment + broad-except sweep), Phase 80 (phase-80.9 close-out), Phase 81 (large feed/launchpad wave: 81.G inline-edit, 81.H /new launchpad, 81.K Activity/Discover tabs, 81.L /help reference, 81.M entity action menus).



### Bug Fixes

- Close pydoclint baseline (Phase 79.3) (5075e5f)
- Retarget Phase 80 quick-create + sidebar /new links to list pages (a3fe212)
- Phase 80 click-walk polish (initialChip / bare operators / ?new=1) (024329c)
- Collapse double rail highlight on /models, route workspace/settings pages (ca828df)
- Apply page-specific rail highlight on htmx boost-nav (ac899c2)
- Bulk_actions getters lost across spread (c5fad19)
- Issue title x-text attribute quote conflict (fc4e2ff)
- Consistent UTC timestamp rendering across the app (7a998f9)
- Catch remaining time-format leaks the first sweep missed (af3ee03)
- Three small bugs + route UC epoch_ms through relative_time_epoch (113f487)
- "+ New" rail CTA pill keeps solid fill in active state (ec59719)
- /new — Catalog falsely active + accent strip persists at rest (91cf61c)
- Item dropdown menus float above subsequent cards (3210a84)
- Topbar breadcrumbs match brand size (1.25 rem) (2ce7a29)
- Topbar breadcrumbs refresh on boost-driven navigation (b0417d0)
- Hide first-run welcome card outside the For-you filter (0f7d8b8)

### Chores

- Close-out CHANGELOG + ROADMAP + stale-comment sweep (4980564)
- Screenshot housekeeping after Phase 79 walkthrough (89b3727)
- Close-out CHANGELOG + ROADMAP + broad-except markers (Phase 80.9) (ec922e0)
- Allowlist home_routes.py with split rationale (deb4618)

### Documentation

- Close-out CHANGELOG + ROADMAP entries (b0063cf)
- Write navigation IA contract (Phase 80.0) (cda8f5c)
- Close Phase 81 + queue Phases 82–85 strategic axes (a3e524d)

### Features

- Full-body FTS + entity_kind column on audit_search (4fcdaf9)
- Consolidate data_product_follows into social_follows (e983b40)
- Rename data_product_readmes to entity_readmes (1dddd93)
- Consolidate reactions + drop legacy review UNIQUE (048179d)
- Generalise badges + add 3 per-kind thresholds (8471bd0)
- Typing Protocols for pyarrow / duckdb / deltalake boundaries (Phase 79.1) (9ffece9)
- Expandable grouped primary sidebar (Phase 80.1) (5e351de)
- Context-panel partials for 11 new sections (Phase 80.2) (643cfd4)
- Supervisor Today digest (Phase 80.3) (fa6f518)
- /users + /lineage index pages (Phase 80.4) (ceb58d7)
- /me consolidated hub (Phase 80.5) (5b8fb2b)
- Index every entity kind in Cmd+K (Phase 80.6) (568cd5a)
- Ambient status footer bar (Phase 80.7) (5e54d6e)
- Quick-create + menu (Phase 80.8) (db668b3)
- Phase 80.10.1 — branded focus, link hover, form-control accent (72b1541)
- Phase 80.10.2 — pql-hover-lift on every clickable card grid (23bc5a8)
- Phase 80.10.3 — auto-init tooltips on icon-only buttons (1b87b8d)
- Phase 80.10.4 — toast every mutation, submit-button spinner (0e77bd7)
- Phase 80.10.5 — skeleton loaders + empty-state polish (89b8e94)
- Phase 80.10.6 — confirm modal, badge pulse, active-item check (03ff025)
- Phase 80.10.5 nachzügler — skeletons on models / audit / notebooks (c6f56fe)
- Phase 81.A — per-user primary-rail customisation (localStorage MVP) (6468d5f)
- Phase 81.D + 81.E — view transitions + footer shortcuts wire-up (12ecda0)
- Phase 81.F.1 — table.html social drawer (12 → 7 tabs) (ce50df7)
- Phase 81.F.2-5 — social drawer sweep across detail pages (42e736b)
- Phase 81.G.A — instant-feel bundle (df1c1cc)
- Phase 81.G.B — multi-select + bulk actions (ac04c46)
- Phase 81.G.C — inline-edit across detail pages (3bdfabe)
- Phase 81.G.D — toast stack-limit, keynav, empty-state CTAs (bc4d88a)
- Phase 81.H — quick-create as primary-rail "+ New" entry (7844c44)
- Phase 81.H.2 — /new launchpad page, rail "+ New" → link (55df072)
- Boost-navigation loading skeleton (9692ac4)
- Phase 81.K.1 — layout shell, sticky filter bar, day grouping (377c93a)
- Phase 81.K.2 — per-kind rich item cards + actor names (174e419)
- Phase 81.K.3 — SSE live updates + new-activity banner (92b2902)
- Phase 81.K.4 — action menu, mute, snooze, mark-all-read (48e86ec)
- Phase 81.K.5 — right column (trending + people + saved) (898be4e)
- Phase 81.K.6 — wire agent_run + issue lifecycle into feed (30ce06b)
- Phase 81.K.7 — keyboard navigation, help modal, focus ring (91f6611)
- Phase 81.K.8 — per-filter empty states + first-run nudge (076c5d6)
- Phase 81.K.9 — Activity / Discover tabs, full-width feed (988c826)
- Phase 81.K.10 — drop redundant heading, tighter breadcrumbs (6dcc39e)
- Phase 81.K.11 — breadcrumbs in topbar, ~50 px tighter pages (85cc8a3)
- Phase 81.K.12 — layout toggles into the topbar (2e3c4aa)
- Phase 81.K.13 — Discover sub-tabs (trending / people / saved) (2792f43)
- Phase 81.L — /help reference page + topbar ?-button (67cda6b)
- Phase 81.M — entity ⋯-action menu on DP / Model / Run pages (5e2a790)

### Refactor

- Drop fanout_dataproduct_event wrapper (053792e)
- Remove DP-kind guard on comment reactions (85c07f8)
- Extract model.html social-tab inline blocks into partials (6e2fcbc)
- Split notebooks_routes into subpackage (Phase 79.0) (aa5ea78)
- Apply ArrowTable / ArrowArray / DeltaSchema casts (Phase 79.1) (d23a607)
- Extract shared agent_payload helper (Phase 79.4) (770cb52)
- Rename 10 phase-77 transitional test files to topic names (Phase 79.2, part 1) (18ab4c9)
- Rename remaining 17 phase-77 test files to topic names (Phase 79.2, part 2) (98f3902)

## [Cluster 13 — Phase 70–77 Lens + Social + Data products] - 2026-05-15

> Phase 70 (member-access + 5-submodule JS-split), Phase 71-72 (Session B closures), Phase 73 (agent-authored data products), Phase 74-75 (social network primitives), Phase 76 (Full Social Network for Data Products), Phase 77 (workspace landing + pin CRUD + 11 sub-sprints).



### Bug Fixes

- Sprint H.1 — clear 8 pre-existing pytest + 14 ruff failures (9aae419)
- Ruff I001 import-sort drift in seed scripts (6ab23a3)
- Close pydoclint gaps in Phase 71/72 + pre-existing drift (94983b5)
- Data_product_yaml_drafts.created_by_agent_run_id type (a345ef2)
- Phase 76.6.2 — Alpine x-data SyntaxError on DP detail + Discussion tab race (a7383ba)
- Phase 76.6.3 — mention picker response-key drift (ffd44ad)
- Phase 76.6.4 — Alpine x-data SyntaxError across 6 social pages (54dfc27)
- Phase 76.6.5 — close fresh-drift gate on Phase 76 inheritance (2849fde)
- Empty-state for Contract + Diff tabs when contract has no tables (9bb9b11)

### CI

- Sprint H.5 — pip-audit CI gate + 11-CVE dep bump (f940eb9)
- Sprint H.4 — PG autogen-drift gate + deeper drift script (db61793)
- Refresh stale allowlist paths from package splits (32d26d6)
- Docstring-parser-fork explicit dep + force-reinstall in CI (571e3af)

### Chores

- Sprint H.2 — clear 28 pre-existing errors, raise budget 497 → 585 (69e7fe8)
- Pre-OSS hygiene files (f8dbe2e)
- Gitignore replay diagnostic logs (a4ca908)
- Pyright budget 614 → 609 (16b8885)
- Phase 77.1 + 77.3 close-out (53c2192)
- Phase 77.2 close-out (c4942cb)
- Phase 77.4 close-out (5d2335d)
- Phase 77.8 close-out (4a59a80)
- Phase 77.7 close-out (ce8bef8)

### Documentation

- Sprint 68.7 — Phase 68 close (Frontend modularization ✅) (f4e860d)
- Sprint H.7 — clarify archive trigger requires both line-count AND staleness (5272e79)
- Sprint H.3 — refresh notebook selectors + routes (b17432c)
- Archive Phases 12.9 + 14-47 — ROADMAP.md 7077 → 2361 lines (66dc4f6)
- Queue Phase 71 (Marketplace polish) + Phase 72 (Agent-Aware Social) (67345d9)
- Flip 71.1 + 71.2 + 71.3 ✅ done; Session A closed (d262052)
- Flip Phase 71 ✅ done; Session B closed (ecd069c)
- Sprint B close — Phase 71 loose ends landed (c13c607)
- Flip 72.1 + 72.2 + 72.3 ✅ done; Session A closed (84a619c)
- Flip Phase 72 ✅ done; Session B closed (1ba3892)
- Queue Phase 73 (Agent-authored data products) + Phase 74 (Reviewer-Agent v2) (6041195)
- Phase 73 Session A — flip 73.1 / 73.4 / 73.5 to ✅ done (af633b1)
- Phase 73 fully closed — agent-authored data products (7d6ffad)
- Phase 74 + 75 closed — ROADMAP + CHANGELOG flip (bc7fd2f)
- Phase 76 closed — Full Social Network for Data Products (bb2958d)
- Phase 76.7 — capture social walkthrough as deterministic playbook (f3f36e3)
- Phase 77.0 ✅, 77.1/77.3 partial (8d1d0a2)
- Docs(phase-77) + chore(roadmap): Phase 77.11 + Phase 77 close-out (9cb9e05)

### Features

- Sprints 68.0 + 68.2 — partials convention + run_view sub-tab split (d51138a)
- Sprint 68.1 — split pages/table.html into 7 tab partials (fe8c7bb)
- Sprint 68.3 — split pages/model.html into 4 tab partials (e3a2f1b)
- Sprint 68.4 — move federation_*.js into js/pages/federation/ (5ee1378)
- Sprints 68.5 + 68.6 — CSS hygiene (sql_editor extract + notebook.css lazy-load) (d60074c)
- Sprint 70.1 — require_user dep + notebook routes member-accessible (4b0561e)
- Sprint 70.2 — notebook nav unconditional for members (6bd2c20)
- Phase 70 ✅ closed — member-access + 5-submodule JS-split (2123b81)
- Sprint 70.9 — Phase 70 ✅ replay verified (e545006)
- Sprint 71.1 — comment threads + routes-package split (fd97802)
- Sprint 71.2 — star ratings + text reviews (970479a)
- Sprint 71.3 — follow / subscribe (a28782c)
- Sprint 71.4 — per-user inbox + fan-out for DP events (4d65e05)
- Sprint 71.5 — versioned per-DP README (50cb495)
- Sprint 71.6 — browse-page rework (1d538f3)
- Sprint B.1 — schema_changed emit on yaml reload (e3c34bd)
- Sprint B.2 — contract_violated streaming emit (81c0db0)
- Sprint B.3 — daily marketplace-digest loop (3ffdc64)
- Sprint 72.1 — Activity feed per DP (1391b87)
- Sprint 72.2 — auto-computed endorsement badges (d14a583)
- Sprint 72.3 — trending board + Grafana panel (64c0b72)
- Sprint 72.4 — typed manual endorsements (159cac4)
- Sprint 72.5 — audit-bound discussions mirror (bc9c3f3)
- Sprint 72.6 — per-user CloudEvent webhook subscriptions (2c44388)
- Sprint 73.1 — promote-to-DP candidate scanner (ed075cc)
- Sprint 73.4 — auto-generated DP passport (bb2c2aa)
- Sprint 73.5 — cross-DP cooccurrence + recommendations (b879b40)
- Sprint 73.2 — pql.contract() inline DSL + draft routes (2aa3047)
- Sprint 73.3 — schema-change proposal flow (96202da)
- Phase 74 Active Reviewer v2 (74.0+74.1+74.2) (e723688)
- Phase 75 — verifiable audit export + SIEM sinks (2d6498e)
- Phase 76.1 — deeper conversations (511df5e)
- Phase 76.2 — user profiles, user-to-user follows, sticky badges (037ccc8)
- Phase 76.3 — topics taxonomy + topic-follows (cc6e1c4)
- Phase 76.4 — per-user /feed + notification preferences (2629011)
- Phase 76.5 — agents as first-class social actors (a573e37)
- Phase 76.6 — SSE notification stream + cross-DP citations (9c6534f)
- Phase 76.5.1 — as_agent on endorsements + reviews + hygiene (1f6a090)
- Phase 76.6.1 — comments_collapse.js + mention_autocomplete.js (17eebb1)
- Phase 76.7 — render citations + agent author badge on comments / reviews / endorsements (b08e35a)
- Phase 77.0.A — polymorphic social_target anchor + entity registry (2052220)
- Phase 77.0.B — social_target_id columns on 7 DP-social tables (f85bd56)
- Phase 77.0.C — mirror_social_to_audit helper (065ea80)
- Phase 77.0.D — polymorphic fanout_event dispatcher (a5e6163)
- Phase 77.0.F.2 — /api/social/{kind}/{ref} router pkg (cfb4950)
- Phase 77.0.G — polymorphic-write enablement (3d6606b)
- Phase 77.1 — register UC table entity kind (d6a6cb6)
- Phase 77.3 — branch promote-gate opt-in (cb1ada3)
- Phase 77.1.5 — polymorphic backend handlers (a9852e0)
- Phase 77.1.5 — socialTabs Alpine factory + 2 new partials (9717074)
- Phase 77.1.5 — table.html social tabs (f847ab3)
- Phase 77.3.B — branch_detail.html social tabs + promote-gate UI (abc3c2f)
- Phase 77.2 — register model entity kind (2a6a5af)
- Phase 77.2 — model.html social tabs (4ea200e)
- Phase 77.2.1 — polymorphic UNIQUE on data_product_reviews (168a068)
- Phase 77.2.1 — polymorphic review handlers + model reviews on (2b93e3e)
- Phase 77.2.1 — Reviews tab on model.html + close-out (fe85392)
- Phase 77.4.A — run kind in entity_registry + citation + dispatch (982edcd)
- Phase 77.4.B — run_view.html Social top-tab + 3 sub-tabs (971e971)
- Phase 77.8.A — social_stars polymorphic bookmark table (cf00b34)
- Phase 77.8.B — social_follows polymorphic follow table (da11f2d)
- Phase 77.8.C — polymorphic UNIQUE on data_product_reactions (ad3769b)
- Phase 77.8.D — polymorphic stars + follow/reaction handlers (8e72fb6)
- Phase 77.8.E — pqlStarToggle server-backed + detail-page star buttons (ba02cca)
- Phase 77.7.A — issues + labels + milestones schema (a7109de)
- Phase 77.7.B — issue routes + registry + citation + dispatch (9c7df0d)
- Phase 77.7.C — /issues HTML pages (3bd3779)
- Phase 77.7.D — Issues tab partial + wired into 4 detail pages (b04dfc1)
- Phase 77.5.A — schemas + catalogs registry + dispatch + citations (87f82de)
- Phase 77.5.B/C — schemas.html + tables.html social tabs (7602d97)
- Phase 77.6.A — notebooks UUID identity table (c2ecd61)
- Phase 77.6.B — notebook + saved_query registry + citations + dispatch (13fa29c)
- Phase 77.6.C — notebook editor side-drawer + UUID alias route (ddfee75)
- Feat(feed) + test(feed): Phase 77.9 — cross-entity feed (a0548da)
- Phase 77.10.A — workspace_pinned_entities + workspace kind (555f145)
- Feat(workspace) + test: Phase 77.10 — workspace landing + pin CRUD (c2413e3)

### Refactor

- Sprint 70.4 — extract jobs_orchestration submodule (6e39c9d)
- Sprint 70.5 — extract kernel_execution submodule (2623a88)
- Sprint 70.6 — extract cell_operations submodule (a449e98)
- Sprint 70.7 — extract markdown_output + persistence submodules (c75db7d)
- Phase 77.0.E — citations.py registry pattern (1a410ac)
- Phase 77.0.I — feed URL builder via entity registry (f87ad46)
- Phase 77.0.F.1 — DP-route call-site swap (4b878bb)
- Phase 77.0.H — social-pane Jinja partial extraction (e691195)
- Phase 77.0.F.3 — active-reviewer service populates social_target_id (d198b69)

### Tests

- Sprint 70.3 — flip non-admin tests to member-accessible (eca83aa)
- Sprint 70.8 — flip remaining 7 non-admin notebook tests (d40467e)
- Sprint H.6 — pytest-xdist enabled on the Postgres lane (cf17824)
- Phase 77.7.E — issues tests + helper/taxonomy split (564ee89)
- Test(social) + chore(roadmap): Phase 77.5.D — tests + close-out (c9884dc)
- Test(notebooks) + chore(roadmap): Phase 77.6.E — tests + close-out (e3b8f7d)

## [Cluster 12 — Phase 66–68 Notebook editor v2] - 2026-05-12

> Phase 66 (notebook editor v2), Phase 67 (Notebook Operations), Phase 68 (Frontend modularization — sql_editor CSS extract + notebook.css lazy-load).



### Documentation

- Sprint 66.8 — phase close (notebook editor v2 ✅) (7935eaa)
- Sprint 67.8 — Phase 67 close (Notebook Operations ✅) (bf19a65)

### Features

- Sprint 66.0 — kernel WebSocket route + notebook CRUD restored (b02c62f)
- Sprint 66.1 — frontend skeleton + load route (8f04aaf)
- Sprint 66.2 — save round-trip + dirty tracking (071b406)
- Sprint 66.3 — cell execution via WebSocket + output rendering (dcfcc50)
- Sprint 66.4 — cell management ops + per-cell toolbar (fa093da)
- Sprint 66.5 — SQL cells (# %% [sql] df) (695a3b1)
- Sprint 66.6 — markdown cells with edit/view toggle (4c49785)
- Sprint 66.7 — keyboard model + autosave + run history popover (3c96d95)
- Sprint 67.0 — marker grammar `tags=[...]` parsing + roundtrip (4aaaee5)
- Sprints 67.1–67.7 — Notebook Operations (schedule / params / inspector / bridge) (32f12d5)

## [Cluster 11 — Phase 56–65 (Pagination + accordion + lens)] - 2026-05-10

> Phase 56 (BUG-53 closure + Alpine regression tests), Phase 57-58 (mid-wave), Phase 59 (7 sub-sprints), Phase 65 (Lens read-only Q&A surface).



### Bug Fixes

- Sprint 56.2 — close all 9 BUG-53-NN markers + Alpine x-data regression test (e6166c9)

### Chores

- Roll-up of unpushed Phase 61/62 + UX polish + sidebar starred refactor (c7a8655)

### Documentation

- Sprint 56.1 — UX audit consolidation + per-page semantic review (d336234)
- Sprint 56.12 — close Phase 56 (ROADMAP + CHANGELOG) (488f82a)
- Sprint 57.9 — close Phase 57 (b7ebcfc)
- Sprint 58.4 — close Phase 58 (3c00d3a)
- Phase 59 — comprehensive UX tour findings + screenshots (2568603)
- Phase 59 ✅ closed — 7 sub-sprints + close (2026-05-08) (61817b3)
- Sprint 65.7 — walkthroughs + plugin tools + docs (d3b71ea)
- Phase 65 closed — Lens read-only Q&A surface (c6d8a13)

### Features

- Sprint 56.3 — empty-state component sweep on 8 templates (bb4ff24)
- Sprint 56.4 — mobile data-label sweep on 7 list-table templates (dfc316f)
- Sprint 56.5 — display-layer Jinja filters (format_uuid + format_hash) (61a08ed)
- Sprint 56.6 — truncate-with-tooltip macro + apply 6 surfaces (3317f92)
- Sprint 56.7 — copy-button macro + apply 4 surfaces (326854a)
- Sprint 56.8 — Bootstrap Offcanvas drawer macro + apply 3 surfaces (d7a5ced)
- Sprint 56.9 — Tables→Cards conversion: agent_reviews + alerts (cd83332)
- Sprint 56.10 — semantic-content corrections (action-orientation) (a9c5928)
- Sprint 56.11 — UX polish bundle (action-discovery + a11y + spinner-text) (40c1f3d)
- Sprint 57.2 — server-side offset pagination on /queries (d3138be)
- Sprint 57.3 — /queries table → card-grid + hljs SQL highlighting (3bee706)
- Sprint 57.8 — apply Phase 57.1 mobile data-label sweep (ad23f2b)
- Phase 58 — finish Phase-57 carve-out trio (918ab8f)
- Sprint 59.1 — CONTENT-jargon sweep + ANSI-strip + isolated logic fixes (c0d93ae)
- Sprint 59.2 — Bootstrap-tab URL-state global helper (2fc3e36)
- Sprint 59.3 — chromeless auth/error layout + 429 template (4be934f)
- Sprint 59.4 — filter_collapsible macro applied to audit-inbox + queries (5a68258)
- Sprint 59.5 — icon-rail re-mapping (AUDIT + REVIEWS, FEDERATION → CATALOG) (70981b1)
- Sprint 59.6 — sub-pane dual-mode helper-text sweep (a7cf5b6)
- Sprint 59.7 — empty-state quality sweep on volumes / models / branches (d1d90db)
- Phase 63 — Writeable SQL Editor (AST-dispatch refactor) (49656d5)
- Phase 64 — permission-locked nav-link UX (4130e3a)
- Sprint 65.0 — Foundation (DB + scope + service skeleton) (42fe057)
- Sprint 65.1 — unified provenance trace (signature feature) (4a56b6f)
- Sprint 65.2 — tool registry (shared backbone) (9129d71)
- Sprint 65.3 — auto-LIMIT + cost-gate hardening + query tool (0dccca9)
- Sprint 65.4 — MCP server (stdio + introspection routes) (92410ac)
- Sprint 65.5 — browser chat UI + LLM provider adapters (e6f0d39)
- Sprint 65.6 — pinned answers (snapshot + standalone view) (9210228)

### Refactor

- Sprint A.1 — pointlessql/web/ facade re-exports (2b520fa)
- Sprint A.2 — pointlessql/types/ facade package (8b58fc6)
- Sprint A.3 — pointlessql/config/ facade package (d890291)
- Sprint A.4 — public surface tightening on pql/__init__.py (5139cd6)
- Sprint B.1 — api/audit/ package (5 audit_*_routes consolidation) (470210e)
- Sprint B.2 — api/admin/ package (8 admin_*_routes consolidation) (943b49a)
- Sprint B.3 — api/sql/ package (4 SQL route files consolidation) (d6b7c29)
- Sprint B.4 — api/lineage/ package (read + ingest split) (30e6e41)
- Sprint B.5 — api/dbt/ package (3 dbt route files consolidation) (dcc56cf)
- Sprint B.6 — api/main.py splitting (loops + router-includes extracted) (22f562d)
- Sprint C.1 — services/dbt/ package (3 dbt service files) (c63122f)
- Sprint C.2 — services/notebook/ umbrella consolidation (35a0b6c)
- Sprint C.3 — services/pii/ package (3 PII service files) (33bdf2a)
- Sprint C.4 — services/lineage/ expansion (5 flat files) (a7ef17d)
- Sprint C.5 — services/audit/ package (6 audit service files) (7f36dc8)
- Sprint C.6 — services/workspace/ package (4 workspace cluster files) (4e89ea3)
- Sprint D.1 — models/agent/ package (4 agent model files) (7f339de)
- Sprint D.2 — models/audit/ package (4 audit model files) (5697939)
- Sprint D.3 — models/lineage/ package (4 lineage model files) (ee2e449)
- Sprint D.4 — models/workspace/ package (3 workspace model files) (9a53faa)
- Sprint D.5 — models/catalog/ package (4 catalog model files) (6264ce2)
- Home branch_audit + sync into existing packages (af5d62c)

### Tests

- Sprint 57.4 — comprehensive route smoke-tests (3b9b1e5)
- Sprint 57.5 — route smoke-tests for dashboards_routes.py (a681284)
- Sprint 57.6 — coverage extension for jobs_routes.py (dadc6e5)
- Sprint 57.7 — admin_api_keys edge-case extension (ed32205)

## [Cluster 10 — Phase 51–55 (UI exploration + Bootstrap 5.3 research)] - 2026-05-08

> Phase 51 (concept page + walkthrough), Phase 53 UI overhaul research (bootstrap53-gap-analysis + ui-overhaul-proposal), Phase 54 (Bootstrap 5.3 modernize wave), Phase 55 (UI polish nachzug).



### Bug Fixes

- Sprint 54.1 — error pages keep the sidebar (34c9106)
- Sprint 54.5 — small bugs + compare-runs badges (3a59a65)

### Chores

- Phase 44.5 — enable ruff BLE001 + close two missing-noqa sites (f6e63f5)
- Sprint 45.1 — narrow audit_sinks_routes.py JSON boundaries (638a6de)
- Sprint 45.2 — cost_estimator.py narrowing + parenthesise except (153f118)
- Sprint 45.3 — narrow governance_routes.py UC dict boundaries (8d602df)
- Sprint 45.4 — narrow volumes_routes.py UC + soyuz boundaries (d136809)
- Sprint 45.5 — narrow home_routes.py UC tree + search casts (e3f38d1)
- Add NewType ID aliases (Phase 47.1) (5443e3b)
- Wire RunId / OpId / QueryHistoryId at boundaries (Phase 47.2) (0cf908a)
- Add StrEnum registry at pointlessql/enums.py (Phase 48.1) (f385558)
- RunStatus + QueryStatus consumer migration (Phase 48.2 batch 1) (0a4a3f5)
- OpName + BranchAction consumer migration (Phase 48.2 batch 2) (646b72e)
- ReadKind consumer migration (Phase 48.2 batch 3) (5324af6)
- AuditSinkType + EventOutcome + ReviewSeverity migration (Phase 48.2 batch 4) (33db5ba)
- Add unified CloudEvents constant registry (Phase 48.3) (57e8fa9)
- Repo-wide ruff format sweep (Phase 49a) (51b9c3a)
- Clear pydoclint DOC502/DOC503/DOC601/DOC603 violations (Phase 49a) (e532e27)
- Split services/agent_runs/operations.py into 6-file subpackage (Phase 49b.1) (cc792e8)
- Split services/audit_aggregator.py into 4-file subpackage (Phase 49b.2) (ba12d35)
- Migrate producers + key consumers to TableFqn (Phase 49c.2) (c865d51)

### Documentation

- Close Phase 40.6 — CDF Tail UI integration (636cb22)
- Close Phase 43 — error envelope + exception hierarchy (4cfdeb9)
- Close Phase 44 — structured logging completeness (c98ad1d)
- Close Phase 45 — pyright budget 559 → 497 (8be1862)
- Close Phase 46 — test-auth-fixture centralization (192f937)
- Close Phase 47 — NewType ID Hardening (7fed680)
- Close Phase 48 — Primitive-Obsession StrEnum Sweep (14ea07a)
- Close Phase 49a — repo-wide lint-sweep (423f721)
- Close Phase 49b — service-file splits (28f987f)
- Close Phase 49c — TableFqn validation type (59b3717)
- Close Phase 50 — Native Data-Product support (bc56c2d)
- Close — concept page + walkthrough + ROADMAP entry (bad3b94)
- Phase 52 — completion pass (3991365)
- Full replay sweep + Bootstrap UI overhaul evaluation (21f72a8)
- Sprint 54.6 — close Phase 54 (e455556)
- Close Phase 55 — UI polish nachzug (4de128b)

### Features

- Phase 40.7 — fold CDF events into row-trace walkback (2caca34)
- Phase 42 — System-errors band on /audit/inbox (c236eab)
- Phase 43.1 — central ErrorCode StrEnum (1302fa5)
- Phase 43.2 — reparent orphan exception families (698d3f7)
- Phase 43.3+43.4 — eliminate bare HTTPException + ErrorEnvelope OpenAPI (79fa87a)
- Phase 44.1+44.4 — extra={} propagation + third-party quieting (6de47af)
- Phase 44.2+44.3 — traceback-preserving broad-except + extra= retrofit (e73ff74)
- Add TableFqn validation type at pointlessql/table_fqn.py (Phase 49c.1) (d3dcd19)
- Sprint 50.1 — yaml-loader + DB-cache foundation (1fac689)
- Sprint 50.3 — contract enforcement at pql.write/merge (ef7a04f)
- Sprint 50.4 — freshness-SLA scanner + CloudEvent (efe40d3)
- Sprint 50.2 — JSON API + HTML index/detail pages (99f075b)
- Phase 51.1 — workspace-repos foundation (d79e358)
- Phase 51.2 — yaml-loader integration (b512f5e)
- Phase 51.3 — notebook + dashboard + saved-query bridges (79c1ae3)
- Phase 51.4 — webhook receiver + cron sync loop (2601707)
- Phase 51.5 — admin JSON API for workspace repos (bace561)
- Sprint 54.2 — color-modes toggle (Bootstrap 5.3) (ce2f964)
- Sprint 54.3 — pagination component on /admin/audit (16a339b)
- Sprint 54.4 — accordion on four admin info-headers (85d3459)
- Sprint 55.1 — accordion-flush on 2 admin info-blocks (fd57dd9)
- Sprint 55.2 — /audit/queries server-side pagination (e360e03)
- Sprint 55.3 — /runs infinite-scroll Load-More (0c2f594)
- Sprint 55.4 — /audit/search infinite-scroll Load-More (7f1d278)
- Sprint 55.5 — sticky table headers on long-list surfaces (9719470)

### Tests

- Sprint 46.1 — central admin / non_admin / anonymous + ApiKeyFixture fixtures (14f5a81)
- Sprint 46.2 batch 1 — migrate admin route tests to admin_client fixture (32dbbcc)
- Sprint 46.2 batch 2 — migrate audit route tests to centralized fixtures (8681923)
- Sprint 46.2 batch 3 — migrate rollback / promotion tests to centralized fixtures (70466b7)
- Sprint 46.2 batch 4 — migrate models / ML route tests to centralized fixtures (ee262a1)
- Sprint 46.2 batch 5 — migrate supervisor / scheduler tests to centralized fixtures (1196ea4)
- Sprint 46.2 batch 6 — migrate remaining test files to centralized fixtures (5362426)

## [Cluster 09 — Phase 23–44 (Admin + Federation + DBT + CDF)] - 2026-05-07

> Long span covering admin landing + audit-sinks + API-Keys UI (Phase 33), Grafana governance panels (Phase 34), DBT integration (Phase 36 Stream A + auto-rollback), and Sprint 40.6 CDF events tab + subscriptions admin.



### Bug Fixes

- Move CodeMirror importmap to base.html (BUG-grand-03) (3f73b5d)
- Separate lineage-emit warnings from operation errors (BUG-grand-08) (af19432)
- Anchor default sqlite paths to project root (BUG-grand-09) (75123c2)
- Swap entire .pql-shell on HTMX boost so icon-rail active state + context-panel update on navigation (ed16040)
- Extract soyuz error message from JSON envelope so SQL editor shows friendly text (48c3979)
- Humanise table-preview error when storage path is missing on disk (4270de7)
- Restore catalog tree on deep paths; sync rail active-state via JS instead of shell-swap (453e22a)
- TablePreview Alpine factory + missing-storage hint copy (7fa5edc)
- Lift tablePreview factory into bootstrap.js to fix Alpine/HTMX race (d3ebe3b)
- Remove redundant Alpine.initTree on htmx:afterSwap (was crashing init for the whole boosted page) (64a15d6)
- Clip SQL results table inside the results card (flex min-width: 0) (fd37880)
- Readable rail labels + reliable context-panel swap on rail clicks (6c0a210)
- Sprint 36.D — capture Delta versions for rollback anchors (b9562dd)
- Escape Alpine x-data attribute on admin row templates (BUG-37-01) (a744b52)
- Close BUG-37-02/03/04/05 (Phase 37.1 sweep) (0238462)
- Default app.state.uc_client to MagicMock in autouse fixture (3cd956d)

### Chores

- Bump soyuz-catalog-client v0.2.0rc5 → v0.3.0rc3 (1752ef7)
- Strip sprint refs from html/css/js (235625e)
- Strip sprint refs from docstrings (c4ed5c9)
- Defer route-file split + ruff cleanups (65692cf)
- Unstale four pre-existing test fixtures (Phase 26.0) (e0b57a6)
- Repo-wide ruff format + pydoclint + detect-secrets cleanup (876af2c)
- Sprint 35.8 — file-size + pyright warning budget gates (202c59c)
- Strip phase/sprint/ADR/BUG cruft from docstrings + comments (7aeda6d)
- Land uv.lock for the mashumaro 3.17 override (70b33a6)

### Documentation

- Grand-tour 14-act playbook + first-replay closure (2e36290)
- Strip sprint refs from public site (1a300f9)
- Phase 18.6+ closed — 18.10 deferred per plan (cabcdd2)
- Sprint 28.8 — concept doc + admin runbook + ADR-0008 + e2e walkthrough (f44c5b1)
- Close stale Sprint 19.2 + Phase 12.9 markers (aadff76)
- Defer Sprint 35.4 (run_view.html) — needs browser playbook session (6e3abcc)
- Add why-body to federation/jobs/run-diff docstrings (21f16d1)
- Record docstring overhaul (Stream A + B) (f00261b)
- Record Sprint 36.6 plugin tools (75cdaa8)
- Rewrite audit-sinks.md against the admin UI (Phase 37 Wave 0a) (d5600a5)
- Refresh grand-tour for Phase 28 + 33 drift (Wave 0b) (8f24a1b)
- New admin-console.md (Phase 37 Wave 1) (dc283ac)
- New audit-cockpit-deep.md (Phase 37 Wave 2) (c977440)
- New run-comparisons.md (Phase 37 Wave 3) (d1c63aa)
- New alerts.md (Phase 37 Wave 4) (bcd45f5)
- New dbt-pipeline.md (Phase 37 Wave 5, D3b path) (13c227d)
- Close Phase 37 — Playwright coverage refresh (Wave 6) (9937b6e)
- Close Phase 37.1 — Phase-37 BUG sweep (3af7d7f)
- Defer Sprint 36.7 on upstream mashumaro/Py3.14 (Phase 38.2) (c81ae50)
- Verify audit-cockpit-deep data path (Phase 38.3) (4119d44)
- Close Phase 38 — sprint-sweep (9caff9d)
- Queue Phase 39/40/41 — three feature pillars (79f0315)
- Explain-rewrite playbook + Grafana panel 21 (Phase 39.4) (305d9e4)
- Close Phase 39 — explain-first rewrite loop ✅ (40b4f77)
- Close Phase 40 — Lakehouse Federation reads ✅ (a9150cb)
- Close Phase 41 — Lineage sub-pills ✅ (9a46b1b)
- Close Phase 40.5 — foreign-Delta CDF tail ✅ (2979eed)

### Features

- Close Phase 15.8 lineage wiring + CDF ordering (a2982c5)
- Allow branch_* op_names in agent-run audit (66e2f66)
- Phase-2 full-stack seed-demo + walkthrough (71ca8dd)
- Emit lineage edge from training_context (BUG-grand-05) (5144c09)
- Contextual help-popover infrastructure + 5 hero anchors (Phase 23.0) (afb9d63)
- Structured EXPLAIN plan tree (replaces raw ASCII) (335698d)
- Polish EXPLAIN plan tree (badges, µs timing, hide wrapper, tree lines) (e598393)
- Surface every DuckDB plan field in the EXPLAIN tree (9cea98b)
- Inline volumes + models in the catalog tree, drop their rail icons (7452ad4)
- GitHub-style 8-char short IDs in the runs table + breadcrumb (51defa4)
- Runs context-panel with status grouping (Phase 24.0) (d4d5141)
- Branches context-panel with active/promoted/discarded split (Phase 24.1) (c6f66bd)
- Workspace context-panel with flat notebook list (Phase 24.2) (79279f6)
- Jobs context-panel with active/paused split (Phase 24.3) (77c8127)
- Alerts context-panel with enabled/disabled split (Phase 24.4) (49087b7)
- Mlflow context-panel + Phase 24 wrap-up (Phase 24.5) (98a20da)
- Help-icons in every Phase-24 panel + walkthrough doc (24.6) (d7efa21)
- Unify asset cache-bust via __version__ (5de515d)
- Sprint 18.6 — anomaly inbox + run-list badge (9cf4e74)
- Sprint 18.7 — full-text search across the audit lake (5710a78)
- Sprint 18.8 — runs-by-table reverse index (8ed0a1d)
- Sprint 18.9 — cell + column-lineage diff in run-vs-run (71cb2fc)
- Sprint 28.0 — workspace foundation + middleware + api_keys pin (b671f9f)
- Sprint 28.1a — workspace_id on audit-trail core + FTS5 surgery (01e662a)
- Sprint 28.1b — workspace_id on lineage / audit_log / governance / queries (9d3dc51)
- Sprint 28.2 — workspace_id on user-owned + scheduler tables (d66c10b)
- Sprint 28.3 — workspace catalog pins (cosmetic) + tree filter (07bdc7e)
- Sprint 28.4 — UI workspace switcher + base.html plumbing (9656c45)
- Sprint 28.5 — audit-wake-gate workspace scoping + cross-workspace 403 round-trip (79368a7)
- Sprint 28.6 — admin workspace CRUD + member management (560d74c)
- Sprint 28.7 — cross-workspace super-admin lens (89dd80b)
- Phases 29-32 — workspace polish + PG production + test-suite speed + PG test quality (dee6796)
- Sprint 33.1 — admin landing card-grid + nav chrome (176f914)
- Sprint 33.2 — audit-sinks management UI (a2d8b52)
- Sprint 33.3 — review-destinations management UI + Phase 33 close (1a550f0)
- Sprint 33.4 — API-Keys UI + System-Info read-only panel + Phase 33 close (58034b2)
- Sprint 34.1 — operator-pain MVP (4 cross-workspace panels) (563136d)
- Sprint 34.2 — governance + compliance panels + Phase 34 close (545e7b1)
- Sprint 36.1 — dbt-docs subprocess + reverse-proxy (95b5296)
- Sprint 36.2 — on-demand CLI + manifest bridge (2317082)
- Sprint 36.3 — test-failure rejects + expectation axis (fbd239b)
- Sprint 36.5 — severity enforcement + dbt CloudEvents (6962fa9)
- Sprint 36.A — sample dbt project + integration test (663247d)
- Sprint 36.B — read-only manifest API (1832075)
- Sprint 36.C — auto-rollback + Phase 36 Stream A close (f105997)
- Sprint 36.4 cockpit chrome (BUG-37-06) (a112f8c)
- Unblock + close Sprint 36.7 via mashumaro 3.17 override (Phase 36 close) (bceca0a)
- Per-run sql_explain row when agent calls /api/sql/explain (Phase 39.1) (e413f42)
- Rewrite_attempts table + run-detail Rewrites sub-tab (Phase 39.2) (49aba6c)
- Nullable run/op FKs + producer column + lineage_inbound scope (Phase 40.0) (0a23222)
- Inbound OpenLineage POST route + parser (Phase 40.1) (83b3e37)
- Table-detail "External producers" block (Phase 40.3) (28eb537)
- Expected-producer registry + freshness compute (Phase 40.4) (20400f0)
- Sprint 41.1 — Lineage sub-pills (Row / Column / Value) (5a487d8)
- Foreign-Delta CDF tail worker (Phase 40.5) (c6fb850)
- CDF subscriptions admin page (Sprint 40.6.1) (3ed76e9)
- CDF events tab on table-detail page (Sprint 40.6.2) (f68429d)
- Auditor-scope CDF read endpoints (Sprint 40.6.3) (6402b44)

### Refactor

- Extract sidebar base factory (31b7fbb)
- Centralize status badge styles (89ad0c7)
- Split lineage_dag into focused modules (e821524)
- Coordinator pattern for sql_editor (9abff17)
- Split runs_routes into per-axis package (Phase 26.1) (b93701f)
- Split agent_runs_routes into per-axis package (Phase 26.2) (a6e648c)
- Sprint 35.1 — split _branch.py into branch/ subpackage (b503985)
- Sprint 35.2 — split lineage_edges into rows/columns/values (f402721)
- Sprint 35.3 — split audit_fts.py per dialect (b632606)
- Sprint 35.5 — module-level deltalake imports (76161e2)
- Sprint 35.6 — annotate value_change_capture locals (05a72f4)
- Split run_view.html into 8 partials (Sprint 35.4 / Phase 38.1) (8364faf)

## [Cluster 08 — Phase 21–22 Audit-Foundation + Docs] - 2026-04-30

> Phase 21 audit-foundation (cross-repo agent-ml-registry walkthrough), Phase 22 (docs landing page + quickstart + concepts overview).



### Documentation

- Close Sprint 21.8 cross-repo + agent-ml-registry walkthrough (22e1a75)

### Features

- Phase 21 audit-foundation — MLflow subprocess + cross-link (21.0/21.1/21.2) (100e1b4)
- Sprint 21.5 — Models catalog tab + model-detail + compare-view (4ab468b)
- Sprint 21.6 — Champion/Challenger model promotion-hop (a777e4c)
- Sprint 21.7 — Inference-Lineage (model → predictions) (85cc2a0)
- Sprint 21.3 — Forced autolog (training param/metric capture) (8cf57e0)
- Sprint 21.4 — Hardware/library fingerprint (Phase 21 closure) (b2a8c0b)
- Sprint 21.8 — training-log endpoint + source_model_uri HTTP (5919c63)
- Sprint 22.0 — mkdocs-material tooling foundation (266ad56)
- Sprint 22.1 — landing page + quickstart + concepts overview (e5c9768)
- Sprint 22.2 — architecture + concepts deep-dives (5cbdebd)
- Sprint 22.3 — reference manual (Python + REST + CLI + config + events + permissions) (2378fe9)
- Sprint 22.4 — guides + cookbook (5bbfea8)
- Sprint 22.5 — polish + launch-ready (closes Phase 22) (7d88be5)

## [Cluster 06 — Phase 17 UI Overhaul] - 2026-04-29

> Phase 17 UI Overhaul — icon-rail + context-panel + tab-aware run-detail + 6-tab table-detail. Five sub-sprints + 17.3.1/17.5.1 polish.



### Chores

- Bump soyuz-catalog-client v0.2.0rc3 → v0.2.0rc5 (3dae193)

### Documentation

- Close Sprint 17.3.1 + 17.5.1 polish (9b50cf8)

### Features

- Sprint 17.3.1 — lazy-load cytoscape on the Graph sub-tab (168960b)
- Sprint 17.5.1 — server-side tree search + DB-backed recents (eb4d4c4)

## [Cluster 05 — Phase 16 + 16.5 Delta-Branching spike] - 2026-04-29

> Phase 16 (lineage cockpit) + Phase 16.5 Delta-Branching ADR-0003 spike — zero-copy Delta shallow-clone branches per agent-run. E2E walkthrough included.



### Bug Fixes

- BUG-17.2-01 — single-quote x-data so |tojson "‎" don't terminate the attr (fc940be)

### Documentation

- Close Phase 17 — UI Overhaul (5 sub-sprints landed) (3cc200c)
- Queue Sprint 17.3.1 / 17.5.1 / 17.6 — Phase-17 follow-ups (fc1943f)
- Sprint 16.5.0 — Delta-Branching shallow-clone spike (bd15265)
- Sprint 16.5.7 — close Phase 16.5 with e2e walkthrough (88ee7db)

### Features

- Sprint 17.1 — Two-column sidebar (icon-rail + contextual panel) (d64b609)
- Sprint 17.2 — Run-detail tab consolidation (10 → 4 top-tabs) (e60975e)
- Sprint 17.3 — Lineage-DAG view + GET /api/runs/{run_id}/graph (dc2a7fe)
- Sprint 17.4 — Table-detail tab refactor (4823dec)
- Sprint 17.5 — Catalog-Browser search + recent tables (b3ff06d)
- Sprint 16.5.1 + 16.5.2 — branch tag schema + pql.branch primitive (64a7d31)
- Sprint 16.5.3 — pql.branch_discard + branch_audit_log (3b72261)
- Sprint 16.5.4 — pql.branch_promote (pointer-swap) (36baac1)
- Sprint 16.5.5 — Control-Room UI for branches (ac9d18a)
- Sprint 16.5.6 — auto-cleanup loop (opt-in) (7cf3743)

## [Cluster 07 — Phase 18–20 Audit Cockpit] - 2026-04-29

> Phase 18 (Audit Cockpit), Phase 19 (Audit-Reviewer Agent + Grafana), Phase 20 (Forensics + Retention).



### Bug Fixes

- Repair SQLite autoincrement + run-view header URL (749ed49)
- Sprint 18.4 — render run-diff charts lazily on tab activation (b7dc2b6)
- Sprint 18.5 — anomaly banner button overflow + empty-baseline wording (4c4f5bc)
- Bug-hunt sweep — 7 bugs found via walkthrough replay (a912c56)

### Chores

- Bump soyuz-catalog-client pin to v0.2.0rc3 (772f13c)

### Documentation

- Split Phase 15 lineage from shoreguard provenance (ee43feb)
- Open Phase 15.5 (Aggregate Lineage + Reject Visibility) (72ab44f)
- Flip Phase 15.5 sprints to done (67bcd2d)
- Open Phase 15.6 in ROADMAP / CHANGELOG (834f30e)
- Flip Phase 15.6 sprints to done (e1c384a)
- Open Phase 15.7 in ROADMAP / CHANGELOG (7b42369)
- Expand Phase 17-20 + Some-day rewrite from post-15.7 strategy (bf58b87)
- Compress completed phases 0-12.8 + 12.10-13.5 into archive (3a90354)
- Open Phase 16 (rollback-only); add op_name='rollback' (0d35cb1)
- Close Phase 18 — Audit Cockpit (6 sub-sprints landed) (7ca2e1f)
- Close Phase 19 — Audit-Reviewer Agent + Grafana (6 sub-sprints landed) (995490b)
- Close Phase 20 — Forensics + Retention (5 sub-sprints landed) (19ea595)

### Features

- Emit OpenLineage events to soyuz on every PQL write (1e97a38)
- Inject _lineage_row_id on bronze autoload (fe54102)
- Record per-row merge edges in lineage_row_edges (a3badae)
- Row-trace UI + run-detail lineage tab (fec56e6)
- Aggregate() primitive with fan-in lineage emission (9ed099f)
- Walk_back exposes fan-in predecessors + UI renders them (f4992bc)
- Pql.merge(track_rejects=True) + lineage_row_rejects table (0908f84)
- Rejects tab on run-detail surfaces dropped source rows (89c67d2)
- Hermes_medallion uses pql.aggregate + track_rejects (7d44415)
- Lineage_column_map table + service helpers (52bc740)
- Instrument aggregate/merge/write/autoload with column edges (907a41a)
- Pql.sql column lineage via sqlglot AST walk (aa8ce4d)
- Column-trace API + UI + table/run badges (b2d3a86)
- Hermes_medallion declares aggregate derivations (81a2459)
- Add lineage_value_changes table + service helpers (6641ed2)
- Bootstrap Change Data Feed on new Delta writes (acb9954)
- Pql.merge(track_value_changes=True) opt-in via CDF (31847dd)
- GET /api/lineage/value-changes + row-trace surface (fb8fcb2)
- Hermes_medallion captures value changes (6edac59)
- Pql.rollback primitive with fail-loud staleness (dc9bda4)
- /api/runs/{id}/rollback-preview + cascade helper (474279f)
- /runs UI button + CloudEvent + e2e replay (5ab9b16)
- Sprint 19.0 audit dashboard + compose overlay (5c760db)
- Sprint 18.0+18.2 — cockpit backbone (read-API + PII masking) (82c3649)
- Sprint 18.3 — saved audit queries (allow-list + CSV/JSON export) (af286c7)
- Sprint 18.1+18.4+18.5 — cross-axis filter + run-diff + anomaly chips (4cf17de)
- Sprint 19.1 — auditor scope + run-scoped audit endpoints (8927ba7)
- Sprint 19.2.0 — daily-review Hermes job + auditor key bootstrap (57ec67c)
- Sprint 19.2.1 — review persistence + CloudEvents fan-out + cockpit card (8d6de75)
- Sprint 19.2.2 — wake-gate skips the LLM call on clean days (fe5d26d)
- Sprint 19.3 — Compliance-Bot persona + principal-summary route (4735b76)
- Sprint 19.4 — Incident-Responder persona + broken-run fixture (51659b6)
- Sprint 20.0 — Audit-Stream forwarder (3 sink types) (1072170)
- Sprint 20.1 — PII detection + masking write-hook (b715f3f)
- Sprint 20.2 — Lineage retention TTLs (ca07013)
- Sprint 20.3 — Time-travel value queries in UI (f06ba97)
- Sprint 20.4 — emit columnLineage + valueChange facets to soyuz (8050c2f)

## [Cluster 04 — Phase 14–15 audit-trail + lineage] - 2026-04-26

> Phase 14 (audit-trail close + public-launch defer split), Phase 15.5 + 15.6 sprints (lineage backend foundation).



### Bug Fixes

- Sprint 13.11.5 — error-handler bytes-safe coercion (74c786e)
- Sprint 13.11.10 — propagate X-Principal into check_privilege (40bcf0a)
- Sprint 13.11.11.1 — engine overwrite must replace schema (094964c)

### CI

- Add pytest+coverage gate and pre-commit config (3ef7e03)

### Documentation

- Sprint 13.11 — reflexive supervision tools playbook (9d686ef)
- Record Sprint 13.11.11 plugin write tools (c286a6c)
- Strip Sprint/Phase/ROADMAP refs and externalise OIDC HTTP timeout (1c86c24)
- Add quality-sweep final report (141bf62)
- Split Phase 14 audit-trail closer from public-launch defer (8d1bb85)
- Mark Sprint 14.1 done (30ba03d)
- Mark Phase 14 closed (45f6584)

### Features

- Sprint 13.11.11 — PQL write endpoints (autoload/write_table/merge/drop_table) (155cdc8)
- Add cost-gate EXPLAIN snapshot column (c625e9f)
- Record pql.table reads in query_history (a127c2a)
- Detect unattributed Delta writes (5731ab6)
- Cross-reference UC mutations into run detail (38438db)

### Refactor

- Squash 25 historical migrations into single initial schema (82c4508)

### Style

- Apply ruff format to existing migrations (26f5bd6)

## [Cluster 03 — Foundation Phases 11–13] - 2026-04-25

> Phase 11 (notebook persistence), Phase 12 (notebook editor v1 + settings drawer + keymap overlay), Phase 13 (Medallion core + DuckDB-first opinion + agent registry/store; Hermes-first integration; Drift-Monitor demo).



### Bug Fixes

- Phase-12 replay fixes — Alpine race, CM dedup, 9457 detail (b830300)
- Exempt /alerts/feed.{atom,json} from session auth (d6544a2)
- Chart Y-dropdown re-sync + Delta→UC type mapping (b9431d2)
- Correct chart-axis dropdown sync — drop x-model, use :selected (369cd22)
- BUG-64-01 — editor x-data root used double quotes (aa0439d)
- BUG-64-02 + 03 — closure-scope Monaco state, scope reload watcher (0af7984)
- Phase 12.7 tail — BUG-71-02 + BUG-72-01 root fix + replay completion (e592566)
- Sprint 75 Phase 5 — csrf header in pqlApi + frontend README (a5a7a20)
- Flush AgentRun parent before AgentRunSource child insert (b1c3a00)
- Sprint 13.10 — Hermes-Medallion live-replay fixups (47a7018)

### Chores

- Mirror migration-015 ix_users_feed_token (1fc4ae5)
- Ignore + lint-exclude scratch notebooks (87157f6)
- Ruff autofix import order in test_jupyter (72d6dfb)

### Documentation

- Phase 10 close-out retrospective + defer packaging replay (6d823a4)
- Open Phases 11-14 — hardening, SQL, agents, launch (020a7eb)
- Record Sprint 41 landing sha (e4c69f2)
- Record clean Sprint 41 admin-audit replay (7481ec7)
- Record Sprint 42 landing sha (a850f60)
- Record clean Sprint 42 csrf replay (6041b52)
- Record Sprint 43 landing sha (24dff44)
- Record Sprint 44 landing sha (329d30f)
- Record Sprint 45 landing sha (1b4ef1c)
- Record clean Sprint 44 error-handling replay (12f212d)
- Rename lingering POINTLESSQL_* env-var references (35e8c49)
- Record Sprint 46 landing sha (4768e20)
- Record Sprint 47 landing sha + close Phase 11 (6862fa8)
- Record Sprint 48 landing sha (eba06b1)
- Icebox Sprint 48's three skipped audit patterns (74c581f)
- Record Sprint 49 landing sha (97c2f97)
- Record Sprint 50 landing sha (55aaa93)
- Record Sprint 51 landing sha (4847cf4)
- Record Sprint 52 landing sha (43c1d7d)
- Record Sprint 53 landing sha (Phase 12 complete) (310d63b)
- Anchor Phase-13 EXPLAIN-agent optimiser loop (6c5d159)
- Open Phase 12.5 + record Sprint 54 landing sha (88898d2) (951a8cc)
- Record Sprint 55 landing sha (832087c) (20e708a)
- Record Sprint 56 landing sha (1ff3c90) (b190e0e)
- Close Phase 12.5 + record Sprint 57 landing sha (7662c29) (565fe2e)
- Explain why Sprint-57 still uses raw httpx post-regen (e2cd032)
- Record Sprint 58 commit hash (a7801ab)
- Record Sprint 59 commit hash (5eb792b)
- Record Sprint 60 commit hashes (7345391)
- Record Sprint 61 commit hash (5a31f9f)
- Record Sprint 62 commit hash (8d982ca)
- Record Sprint 63 commit hash (15a1108)
- Sprint 64 — Phase 12.6 close + editor E2E playbook (2ab5df1)
- Record Sprint 64 commit hash (4f5e3ce)
- Record Sprint 67 commit hash (61c0858)
- Record Sprint 68 commit hash (0fb0cce)
- Record Sprint 69 commit hash (2bae09e)
- Record Sprint 70 commit hash (c1cdd93)
- Record Sprint 71 commit hash (9846ab3)
- Record Sprint 72 commit hash (ed523bb)
- Record Sprint 73 commit hash (2703aa3)
- Record Sprint 74 commit hash + Phase 12.7 close hashes (69a9239)
- Record Sprint 75 + Phase 12.8 close (9260b83)
- Record Sprint 90 commit hash (3dcc5f4)
- Record Sprint 91 commit hash (429b44a)
- Record Sprint 92 commit hash (df2ffc8)
- Record Sprint 94 commit hash (cd18d6c)
- Record Sprint 95 commit hash (9b6095e)
- Record Sprint 96 commit hash (6e939a8)
- Record Sprint 97 commit hash (17907eb)
- Record Sprint 98 commit hash (178fa5c)
- Record Sprint 99 commit hash (cfa3af0)
- Record Sprint 12.12.2 commit hash (285e1cb)
- Phase 13 scope revision — registry+store, Hermes first, Drift-Monitor demo (c109f79)
- Add Phase 13.5 — Medallion core + DuckDB-first opinion (bcb2004)
- Record critical path to Hermes-Medallion demo (207d742)
- Record Sprint 13.5.1 commit hash (08974ac)
- Record Sprint 13.3 commit hash (014b84b)
- Record Sprint 13.1 commit hash (f93b17f)
- Record Sprint 13.5.2 commit hash (eff426b)
- Record Sprint 13.5.3 commit hash (e10581b)
- Record Sprint 13.4 commit hash (f33017e)
- Record Sprint 13.5.4 commit hash (f0a4e25)
- Record Sprint 13.6 commit hash (98ba756)
- Record Sprint 13.5 commit hash (53f2af8)
- Add Sprint 13.8 + 13.9 + cells-vs-operations design opinion (06e0dab)
- Record Sprint 13.8 commit hash (039988d)
- Record Sprint 13.9 commit hash (63c6787)
- Add raw_to_gold notebook for live walkthrough (5f7fa3d)
- Sprint 13.5.5 — Hermes-Medallion playbook (ba54476)
- Record Phase 13.7 + 13.5.5 closing hashes (05ff4e8)
- Record Sprint 13.10 closing hash 47a7018 (df68bcb)
- Close Phase 13 — Sprint 13.11.1-13.11.4b landed (4f6e56e)

### Features

- Sprint 41 — audit-log viewer + /admin/audit (2b25b89)
- Sprint 42 — CSRF protection for HTML form routes (811fb5c)
- Sprint 43 — rate limit /auth/* against DB-backed counter (ad4d768)
- Sprint 44 — RFC 9457 error envelope + HTMX toast bridge (f6f327c)
- Sprint 46 — graceful JWT signing-key rotation (fc2cc99)
- Sprint 48 — audit-log hardening (shoreguard port) (14b1249)
- Sprint 49 — SQL editor MVP (b0f705d)
- Sprint 50 — Query history + /queries page (639d7ae)
- Sprint 51 — Saved queries + drawer + share model (0f93345)
- Sprint 52 — Export + timeout + cancel (b4bfee5)
- Sprint 53 — EXPLAIN + autocomplete + mobile + playbook (b718839)
- Sprint 54 — chart toolbar + chart_config persistence (88898d2)
- Sprint 55 — query alerts (CloudEvents + Atom/JSON Feed) (832087c)
- Sprint 56 — column statistics + sparkline UI (1ff3c90)
- Sprint 57 — volume upload + convert-to-Delta (7662c29)
- Sprint 58 — native editor skeleton + jupytext round-trip (513fd68)
- Sprint 58 follow-up — Databricks-style autosave (dae03a8)
- Sprint 59 — kernel + WebSocket proxy + basic execution (f672564)
- Sprint 60 — output persistence + rich mimes + ANSI (5a17c0a)
- Sprint 60 follow-up — markdown preview with source-collapse (9d03ca0)
- Sprint 61 — pyright LSP (completion/hover/diagnostics) (027ac66)
- Sprint 62 — Variable Explorer + catalog insert + rich scripts (95b4a2b)
- Sprint 63 — retire JupyterLab iframe + papermill .py bridge (accbeca)
- Sprint 65 — Phase 12.7 opener: editor JS module split (43cded2)
- Sprint 66 — cell-type registry + per-cell affordances (4a7fc82)
- Sprint 67 — file-tree sidebar inside the editor (d41a4eb)
- Sprint 68 — multi-notebook tab bar (400670c)
- Sprint 69 — markdown-it + KaTeX + pencil pin (d3c7df7)
- Sprint 70 — outline / TOC panel + cell jump (b6fe0e2)
- Sprint 71 — SQL cell (DuckDB via PQL.sql) (e0043dc)
- Sprint 72 — ipywidgets minimal placeholder (b8ef7dc)
- Sprint 73 — per-cell run history + diff (Alembic 018) (dc530eb)
- Sprint 74 — settings drawer + keymap overlay + Phase 12.7 close (a184ef3)
- Sprint 13.2 — agent_runs Alembic table + HTTP registry (2a3fe34)
- Sprint 13.5.1 — Medallion defaults + ADR 0002-duckdb-first (03726fe)
- Sprint 13.3 — CloudEvents agent_run envelope (e4b2a01)
- Sprint 13.1 — EXPLAIN gate + cost estimator (a9e34f4)
- Sprint 13.5.2 — pql.merge() upsert + scd2 (29dda17)
- Sprint 13.5.3 — pql.autoload() exactly-once file ingest (7b974d0)
- Sprint 13.4 — filter bar + approval panel (9e3a496)
- Sprint 13.5.4 — conformance check on detail view (7a6b2c9)
- Sprint 13.6 — X-Principal forwarded into PQL session + audit (c1c9d4e)
- Sprint 13.5 — Drift-Monitor agent + walkthrough (0447ec1)
- Sprint 13.8 — Forced audit trail for agent runs (3f19c3d)
- Sprint 13.9 — Run-scoped query history (237890d)
- Sprint 13.7.0.5 + 13.7.3 — API-key gate + plugin enablers (a0922bf)
- Sprint 13.7.4 — agent_run_tool_calls + post_tool_call route (8a18375)
- Sprint 13.11.1 — pql_describe_primitive + pql_my_run (722eaa0)
- Sprint 13.11.2 — target-state + recent-failures (75ea87e)
- Sprint 13.11.3 — pql_lineage (9fd7a4c)
- Sprint 13.11.4a — DB-backed API keys + supervisor scope (c3b1af8)
- Sprint 13.11.4b — detailed run diff (ops + tool calls) (90eefaa)

### Refactor

- Sprint 45 — nested BaseSettings with per-sub-model env_prefix (c3cae8c)
- Sprint 75 Phase 1 — carve up main.js (247e271)
- Sprint 75 Phase 2 — ESM bridge entrypoint (87f03a7)
- Sprint 75 Phase 3 — editor_base + small editors to ESM (410f144)
- Sprint 75 Phase 4 — federation/list_table/sql_editor + helpers to ESM (2d9e1e2)
- Sprint 75 Phase 6 — split style.css into component files (e0ae139)
- Sprint 76 — notebook/main.js → 4 sub-modules + toast helper (dbc18d2)
- Sprint 77 — kernel_session.py → 3-module package (54a6436)
- Sprint 78 — pql.py → 5 sibling helpers (31fda97)
- Sprint 79 — notebook_outputs.py → 2-module package (7802f30)
- Sprint 80 — models.py → 8-module package (804b4aa)
- Sprint 81 — alerts.py → 4-module package (b076333)
- Sprint 82 — pg_sync.py → 5-module package (c535b70)
- Sprint 83 — unitycatalog.py → mixin package (57a2a46)
- Sprint 84 — scheduler.py → 5-module package (8127b13)
- Sprint 85 — main.py middleware + helpers extract (7ddac5a)
- Sprint 86 — extract catalog tree routes from api/main.py (dbb3821)
- Sprint 86b — extract SQL editor routes from api/main.py (231b786)
- Sprint 86c — extract queries + saved-queries routes from api/main.py (51f6691)
- Sprint 87 — extract alerts + feed routes from api/main.py (c45f4a5)
- Sprint 87b — extract UC volumes routes from api/main.py (9047785)
- Sprint 87c — extract governance routes from api/main.py (c975f9e)
- Sprint 88a — extract notebook HTTP routes from api/main.py (e621c44)
- Sprint 88b — extract notebook WS endpoints from api/main.py (7687f5e)
- Sprint 89a — extract federation routes from api/main.py (08a7298)
- Sprint 89b — extract jobs + scheduler routes from api/main.py (ecd5702)
- Sprint 89c — extract dashboards routes from api/main.py (f501c4e)
- Sprint 90 — endgame, lift admin/home/catalog-html out of api/main.py (9c8e997)
- Sprint 91 — split frontend sql_editor.js into 4 modules (0d5700d)
- Sprint 92 — split federation.js + lift command_palette inline script (47cfdad)
- Sprint 93 — extract notebook_editor.html modals into partial (d14f4e7)
- Sprint 94 — lift 4 page-template inline scripts into ESM (33a0a6c)
- Sprint 95 — CSS feinschliff + cache-busting parity (close Sprint 77-95) (90d40b8)
- Sprint 96 — drop UUID markers, content-hash cell identity (4c59b85)
- Sprint 97 — parser hardening against manual edits (ac6958e)
- Sprint 98 — browser walkthrough + two output-zone regressions (a50df3a)
- Sprint 99 — toolbar Bootstrap-native (badges + btn-groups + a11y) (529aa57)
- Sprint 12.12.1 — delete browser notebook editor, add server-side run-view skeleton (bc2ad07)
- Sprint 12.12.2 — delete notebook editor backend, stub /runs supervision (ac5207e)
- Make papermill runs_dir a first-class setting (25dc6dd)

### Tests

- Sprint 47 — fix pre-existing test-suite regressions (b6381a6)

## [Cluster 02 — Release-Engineering — Sprint 24–40] - 2026-04-18

> Phase 10 closes the original 10-phase MVP plan. Release-engineering: bump-version.sh, cliff.toml, release.yml workflow, GHCR docker.yml, soyuz-catalog-client path-dep to git-tag pin, v0.1.0rc1/rc2/rc3 tags.



### Bug Fixes

- Sprint 26 same-sprint — surface BUG-26-01 + BUG-26-02 from live replay (9b7146b)
- Sprint 27 same-sprint — surface BUG-27-01 from live replay (78a8bd9)
- Sprint 28 same-sprint — surface BUG-28-01 from live replay (23022f5)
- BUG-28-02 — anchor notebooks_dir against startup CWD (733919d)
- BUG-33-01 — quote cron + last-run x-data attrs with single quotes (cae5515)
- BUG-33-02 — parse UTC-naive server timestamps as UTC, not local (bf656f6)
- Mirror migration-created indexes in model __table_args__ (94c8580)
- Use token-as-username URL form for private soyuz-catalog pull (87b908c)
- Use `gh auth setup-git` for private soyuz-catalog dep (64b6b32)
- Hoist GH_TOKEN to job-level env so uv sync inherits it (afc5d44)
- Use http.extraheader Bearer auth instead of gh setup-git (8ff59b3)
- Inject Bearer extraheader via GIT_CONFIG_COUNT env (99d78bc)
- Narrow extraheader scope to soyuz-catalog URL only (0e5f33a)
- Broad extraheader + persist-credentials:false (7fc2a31)
- Move extraheader env from job-level to uv-sync step (19cfdb6)
- Persist-credentials:false AND step-local extraheader env (c547f34)
- File-based global git config + persist-credentials:false (225a47f)
- Switch to sibling-checkout pattern for soyuz-catalog-client (fd38601)
- Raw git clone for soyuz-catalog instead of actions/checkout (9ed27e0)
- Sprint 38 follow-on — drop broken uv.toml override, replace with in-place swap (1923749)
- Replace auth-triangulation probes with a tight preflight check (33b9cff)
- Alembic needs a migrated target, not an empty sqlite file (bcdaf9f)

### Build

- Sprint 38 — swap soyuz-catalog-client path-dep to git-tag pin (41868bc)

### CI

- Retrigger with classic PAT secret (3e1656c)
- Retrigger after secret fix (0ae3e9a)

### Documentation

- Add Phase 8 — Notebook-as-job (5 sprints planned) (97688f8)
- Record Sprint 24 commit hash (fff9bc7)
- Record Sprint 25 commit hash (095795b)
- Record Sprint 26 commit hash (4035665)
- Record Sprint 27 commit hash (4a96642)
- Record Sprint 28 commit hash (d166b9a)
- Sprint 28 live-replay — 52/52 green, refine Part C (6e1a7f1)
- Add Phase 9 — UX overhaul & discoverability (8 sprints planned) (b8d7d73)
- Record Sprint 30 commit hash (981ea75)
- Record Sprint 31 commit hash (93fcc22)
- Record Sprint 32 commit hash (75f03d0)
- Record Sprint 33 commit hash (0834138)
- Record Sprint 34 commit hash (972c7bf)
- Record Sprint 34 live-run playbook result (3f321b7)
- Record Sprint 35 commit hash (e7c676b)
- Record Sprint 36 commit hash (025ebbc)
- Open Phase 10 and record Sprint 37 landing (774b419)
- Record Sprint 37 commit hash (3459e11)
- Record Sprint 38 commit hash (3301d18)
- Record Sprint 39 commit hash + v0.1.0rc1 tag (f02311b)
- Record preflight + alembic-upgrade CI fixes landed after the main Sprint 38 follow-on (3d1a95f)
- Point Sprint 39 at the landed v0.1.0rc2 release (ed9dc85)
- Record Sprint 40 landing sha (aa814a5)

### Features

- Sprint 24 — Papermill executor + JupyterLab viewer (062bb18)
- Sprint 25 — typed parameters UI for papermill jobs (d15e7ef)
- Sprint 26 — inline papermill run render + output artifacts card (6652869)
- Sprint 27 — workspace file browser for notebooks (72a1438)
- Sprint 28 — dashboards + run-compare; close Phase 8 (5f73115)
- Sprint 29 — design-token foundation + Inter (75b4dd8)
- Sprint 30 — app shell, error pages, toast system (8d939fe)
- Sprint 31 — command palette + global search (c9f0198)
- Sprint 32 — home dashboard + fix BUG-32-01/02 (7a313fc)
- Sprint 33 — list-page polish (c26b9e5)
- Sprint 34 — catalog/schema/table experience (f970fce)
- Sprint 35 — mobile + responsive (59cf50c)
- Sprint 36 — shared utilities + shortcuts + Phase-9 close (ec3facc)
- Sprint 39 — PointlesSQL release engineering (9f73dc3)
- Sprint 40 — docker.yml GHCR publish + clean-machine install (c242464)

### Other

- Probe GIT_CONFIG_* propagation before uv sync (599015c)
- Verify SOYUZ_READ_TOKEN length + auth over curl (3ceaf45)
- Add non-leaking SOYUZ_READ_TOKEN length check (8b2ecb7)
- Triangulate why SOYUZ_READ_TOKEN is rejected for git ops (3a00579)

### Tests

- Seed smoke_papermill.ipynb and record Sprint 24 live-run (c9709c8)

## [Cluster 01 — Bootstrap — Sprint 1–23] - 2026-04-17

> Initial project scaffolding through Phase 7 (DAG engine + Playwright orchestration). Catalog browser, PQL helper, embedded JupyterLab, auth (Sprint 5-7), Postgres sync, foreign-catalog UI, logging/observability, docstrings + pydoclint, exception hierarchy, papermill executor, MCP walkthrough harness.



### Bug Fixes

- Bypass broken list_tables parser for soyuz response mismatch (2b0ba01)
- Clear X-Frame-Options so JupyterLab loads in iframe (3f9bef7)
- Escape breaks x-data attribute in New DAG modal (e09a661)
- Map soyuz 4xx + Create*.from_dict errors to ValidationError; guard ext-loc credential in UI (3f1da76)

### Documentation

- Record Sprint 1 commit hash (8190a57)
- Record Sprint 2 commit hash (753a099)
- Record Sprint 3 commit hash (b0e6fbd)
- Record Sprint 4 commit hash (9e28e9b)
- Record Sprint 5 commit hash (dd7b9ae)
- Plan Phase 3 sprints — auth & multi-user (8ce37f5)
- Record Sprint 6 commit hash (8f7f6d8)
- Record Sprint 7 commit hash (9affe6e)
- Record Sprint 8 commit hash (cca4d58)
- Plan Phase 4–5 sprints — packaging + compute engines (0a5777e)
- Record Sprint 9 commit hash (d2c0cbf)
- Record Sprint 10 commit hash (03bf174)
- Record Sprint 11 commit hash (9b50789)
- Record Sprint 12 commit hash (453dd5f)
- Record Sprint 13 commit hash (5eaf5f5)
- Record Sprint 14 commit hash (ff531c8)
- Record Sprint 15 commit hash (5f3cca1)
- Record Sprint 16 commit hash (8257935)
- Plan Phase 6 — Infrastructure & orchestration (e146cce)
- Record Sprint 17 commit hash (484a3d2)
- Record Sprint 18 commit hash (f295bff)
- Record Sprint 19 commit hash (5d3df07)
- Record Sprint 20 commit hash (ceaef78)
- Record Sprint 21 commit hash, flip Phase 6 to done (b7d0859)
- Record Sprint 22 commit hash (ca3a7fc)
- Record Sprint 23 commit hash, close Phase 7 (9a2f0d2)

### Features

- Initial project with catalog browser and generated client (M0–Sprint 1) (3a596e1)
- Add PQL helper library for Delta table read/write via UC metadata (Sprint 2) (2442dc3)
- Add embedded JupyterLab tab with subprocess lifecycle (Sprint 3) (eee7ade)
- Add Sprint 4 polish — E2E tests, error handling, UX, docs (c419f92)
- Add Sprint 5 — tags, permissions, lineage, federation UI (8354fec)
- Add Sprint 6 — Alembic + local users + JWT auth (5c346cd)
- Add Sprint 7 — principal forwarding + enforcement (9046793)
- Add Sprint 8 — OIDC / OAuth2 provider login (f6551eb)
- Add Sprint 9 — Dockerfiles + docker-compose (1bf34e8)
- Add Sprint 10 — Postgres option + env polish (8c660d3)
- Add Sprint 11 — Engine abstraction + DuckDB (814e992)
- Add Sprint 12 — Polars engine (8588ad0)
- Add Sprint 13 — Exception hierarchy + strict pyright (5511871)
- Add Sprint 14 — Centralized API error handling (d766136)
- Add Sprint 15 — Docstrings + pydoclint config (33b97ef)
- Add Sprint 16 — Logging and observability (e520c51)
- Add Sprint 17 — Foreign catalog UI (83a024c)
- Add Sprint 18 — Postgres sync worker (b9a36ae)
- Add Sprint 19 — DAG engine: data model + single-task (eab27a8)
- Add Sprint 20 — DAG engine: multi-task DAGs (34bfcc8)
- Add Sprint 21 — DAG engine: observability + docs (e97c105)
- Add Sprint 22 — Playwright MCP walkthrough harness + 5 data-surface playbooks (7b837db)
- Add Sprint 23 — Playwright MCP orchestration + operational playbooks; close Phase 7 (72a50bc)

