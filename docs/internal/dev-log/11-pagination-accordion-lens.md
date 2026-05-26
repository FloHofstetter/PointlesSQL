---
title: "Cluster 11 — Phase 56–65 (Pagination + accordion + lens) (dev-log)"
audience: contributor
cluster_id: "11"
phases: "56-65"
closed: "2026-05-10"
---

# Cluster 11 — Phase 56–65 (Pagination + accordion + lens) (dev-log)

> Phase 56 (BUG-53 closure + Alpine regression tests), Phase 57-58 (mid-wave), Phase 59 (7 sub-sprints), Phase 65 (Lens read-only Q&A surface).

These entries were materialised from the pre-W3 ``CHANGELOG.md`` ``[Unreleased]`` block (Doc-Master-Plan W3, 2026-05-26).  They preserve the original phase-keyed narrative for contributors who want richer commit-level context than the auto-generated per-cluster CHANGELOG section provides.

---

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 65 — Lens read-only Q&A surface (2026-05-10).**  New
  analyst-facing chat-style surface that exposes read-only data
  Q&A over two transports: a browser chat UI at `/lens` (BYO LLM
  key per workspace, Fernet-encrypted at rest) and an MCP server
  on stdio for IDE consumers (Claude Desktop, Cursor, Hermes).
  Both transports share one Pydantic-typed tool registry covering
  `provenance` (unified row/column/value lineage trace —
  Phase 65's signature tool), `query` (SELECT-only, EXPLAIN-cost-
  gated, auto-LIMIT), `list_catalogs` / `_schemas` / `_tables`,
  `describe_table`, and `lineage_neighbors`.  New `analyst` scope
  on `api_keys` (auditor passes too as superset).  Pure read-only
  enforcement at the AST validator; per-query cost cap +
  per-session budget cap; pinned-answer flow lets analysts
  bookmark assistant answers for stable-URL re-rendering at
  `/api/lens/pinned/<slug>/view`.  Phase 13/39 power-mode write
  tools stay parallel as the engineering story; Lens is the new
  default analyst surface.  hermes-plugin-pointlessql gains
  `pql_lens_ask` + `pql_lens_get_pinned` for cron-bot consumption.
  Two new walkthroughs (`lens-overview.md` + `lens-mcp.md`).
  Adds `mcp[cli]`, `openai`, `anthropic` deps.  Two Alembic
  migrations (`ff5g7i9k1m3o` lens tables, `gg6h8j0l2n4p`
  query_history.lens_session_id FK).  77 new pytest cases.

- **UX — permission-locked navigation links visible instead of
  hidden (2026-05-10).**  Admin-only links in the icon-rail
  (Workspace, Admin), the catalog sidebar (Branches), and the
  mobile nav drawer (Workspace, Admin) now render for every user.
  Non-admins see the entry greyed out with a trailing lock icon
  and `aria-disabled="true"`; click / Enter / Space surface a
  toast naming the missing role ("Requires admin role — contact
  your workspace admin.").  This restores discoverability — a
  regular user can now see *that* a Branches page exists and ask
  the admin for access — without weakening backend authorisation
  (the routes still 403 if the dead `href="#"` is bypassed).
  Added `frontend/templates/_macros/permission_link.html` (single
  re-usable macro across icon-rail / sidebar / nav-links) +
  `frontend/js/permission_link.js` (delegated click + keyboard
  listener registered once via `bootstrap.js`) +
  `.permission-locked` CSS in `frontend/css/layout.css`.  Five
  inline `{% if current_user.is_admin %}` wrappers replaced by
  one macro call each; user-menu admin badge stays unchanged
  (status indicator, not a link).

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 63 — Writeable SQL Editor (AST-dispatch refactor) ✅
  closed (2026-05-10).**  Turns the SELECT-only SQL editor into
  an AST-classifying dispatcher that routes each statement
  family to its correct typed primitive.  Every editor write now
  lands in the same audit trail as agent-driven writes
  (`agent_run_operations` row, `lineage_row_edges` /
  `lineage_value_changes` where applicable, and a
  `query_history` row with `agent_run_id` populated).

  The structural gap that motivated Phase 63 was **not** an
  audit / safety stance — the SELECT-only constraint at
  [pointlessql/pql/sql_parser.py:385-391](pointlessql/pql/sql_parser.py#L385-L391)
  fell out of the DuckDB rewriter's scope (DuckDB reserves
  `main` as a catalog name and refuses to bind 3-part UC refs
  natively, so the parser has to extract + rewrite source
  tables; the rewrite logic only made sense for SELECTs).  The
  audit infrastructure was already ready for write traffic;
  the only structural gap was that interactive editor writes
  did not populate `query_history.agent_run_id`.

  - 63.1 — `pointlessql/pql/sql_parser.py`: new `StmtType`
    StrEnum, `classify(ast) -> StmtType`,
    `extract_write_target`, `extract_source_refs`,
    `parse_and_classify`, and `parse_batch` for multi-statement
    input (Phase 63.6).  `_parse_root` no longer rejects
    non-SELECT — `prepare_sql` keeps the SELECT-only behaviour
    via an explicit guard and points the dispatcher at
    `parse_and_classify` for everything else.  `CREATE CATALOG`
    / `DROP CATALOG` parse as `exp.Command` in sqlglot and are
    deliberately rejected (admin UI handles catalog
    management).  Bare `CREATE TABLE foo (a INT, b TEXT)`
    rejects with a "use the table-detail UI's New Table form"
    message.  42 new pytest cases in
    `tests/test_sql_parser.py` (parametric coverage of every
    StmtType + write-target extraction + source-ref dedup).
  - 63.2 — `pointlessql/pql/_update_delete.py` (new) +
    `pointlessql/pql/pql.py` extended: `pql.update(target, *,
    set_clause, where=None, track_value_changes=False)` and
    `pql.delete(target, *, where=None)` wrapping
    `DeltaTable.update` / `DeltaTable.delete` (delta-rs accepts
    SQL-string predicates natively).  Both emit
    `agent_run_operations` rows; `pql.update` reuses the merge
    path's CDF-based `_capture_value_changes` for the opt-in
    `lineage_value_changes` capture.  New HTTP routes
    `POST /api/pql/update` + `POST /api/pql/delete` mirror the
    write-table / merge auth pattern (`MODIFY` privilege on
    target).  Alembic migration `ee3f6h8j0l2n` extends
    `ck_agent_run_operations_op_name` with six new op names
    (update / delete / drop_table / create_schema / drop_schema
    / alter_table) in one shot so Phase 63 needs only one
    migration.  ORM CHECK constraint in
    `pointlessql/models/agent_run_audit.py` widened in lockstep.
    13 new pytest cases in `tests/test_update_delete.py`.
  - 63.3 — soyuz `update_table` facade for ALTER TABLE COMMENT:
    **deferred** per plan rationale.  Cross-repo soyuz tag bump
    + client regen is out of scope; the editor's table-detail
    UI (Phase 17.4) already handles ALTER TABLE COMMENT /
    properties.  The dispatcher's `ALTER_TABLE` branch returns a
    structured "use the table-detail UI" error so the parser
    path stays live for a future Phase 63.5 to wire in.
  - 63.4 — `pointlessql/api/sql_dispatcher.py` (new): one
    `dispatch(stype, ast, …)` entry point + per-StmtType
    branches.  SELECT keeps the existing DuckDB rewriter path
    (no agent_run created — matches today's behaviour).  Write
    branches (INSERT FROM SELECT, CREATE TABLE AS SELECT,
    UPDATE, DELETE, MERGE, DROP TABLE, CREATE SCHEMA, DROP
    SCHEMA) start a one-shot `agent_run` with
    `agent_id='sql-editor'` BEFORE invoking the primitive; the
    PQL primitives' `operation_context` then emits
    `agent_run_operations` against that run id automatically.
    DDL branches emit their own op row directly via SQL since
    the soyuz client has no operation_context wrapper.
    [pointlessql/api/sql_routes.py:202-440](pointlessql/api/sql_routes.py#L202-L440)
    shrinks dramatically: parse → classify → dispatch →
    serialize.  EXPLAIN ANALYZE keeps its inline path
    (SELECT-only).  Per-branch privilege checks reuse
    `check_privilege` (SELECT on source refs + MODIFY /
    USE_SCHEMA on target).  10 new pytest cases in
    `tests/test_sql_dispatcher.py`.
  - 63.5 — `pointlessql/pql/sql_merge_translator.py` (new):
    translates `exp.Merge` → `MergeCallSpec` for the
    dispatcher's MERGE branch.  Supports the `WHEN MATCHED
    THEN UPDATE` (+ optional `WHEN NOT MATCHED THEN INSERT`)
    upsert subset of `pql.merge`; everything outside that
    raises `SQLMergeUnsupportedError` with structured guidance
    pointing the user at `POST /api/pql/merge` (which accepts
    JSON for elaborate scenarios).  Conditional WHEN clauses,
    `WHEN MATCHED THEN DELETE`, `WHEN NOT MATCHED BY SOURCE`,
    multiple WHEN MATCHED branches, and complex non-EQ ON
    predicates are all rejected.  9 new pytest cases in
    `tests/test_sql_merge_translator.py`.
  - 63.6 — `POST /api/sql/execute_batch` (new): runs `;`-
    separated statements via the same dispatcher.  `atomic=True`
    opens a single per-batch agent_run and calls
    `pql.rollback` (Phase 16) on the prior write ops on
    failure.  `atomic=False` (default) makes each write its
    own run; failures stop the batch but earlier writes stay.
    Frontend toggle deferred to a polish Sprint 63.6.1 — the
    server-side route is callable today.
  - 63.7 — `frontend/js/sql_editor/execute.js` +
    `frontend/templates/pages/sql_editor.html`: statement-type
    badge above the result widget (colour-coded SELECT /
    INSERT / UPDATE / DELETE / DROP); destructive-statement
    confirmation modal (regex heuristic for `DROP TABLE/SCHEMA`
    and `DELETE` without `WHERE` — false positives are
    acceptable since the modal is a UX speed-bump, not a
    security gate); new `dml`/`ddl` result-render branch
    showing `<rows_affected> on <target>` + a "View op trace"
    button deep-linking to `/runs/<run_id>`; existing SELECT
    rows-table branch unchanged.
  - 63.8 — Audit-FK wiring: `pointlessql/api/_audit_helpers.py`
    `record_query_async` accepts `agent_run_id` + `read_kind`
    kwargs; dispatcher passes both so editor writes land in
    `query_history` with the originating agent_run_id and
    `read_kind='sql_dml'` / `'sql_ddl'`.  `pointlessql.enums.ReadKind`
    extended with `SQL_DML` and `SQL_DDL` values.
    `/runs/<id>` already joins `query_history` by
    `agent_run_id` (Phase 13.10) so editor writes show up
    in the run's queries panel without further work.
  - 63.9 — Tests + close: 31 new pytest cases overall.
    `feedback_skip_pytest` rule applies to old tests but
    Phase-63 surfaces are merge-blocking — full suite run
    confirms 147 pass across the touched paths
    (test_sql_parser + test_sql_execute + test_sql_dispatcher
    + test_sql_merge_translator + test_update_delete +
    test_pql + test_merge_value_changes + test_merge_rejects).
    `ruff check` / `pyright` / `pydoclint` clean on every new
    or modified file.

  **Why this matters:** Phase 14's external-write scanner
  treats writes that have no `agent_run_operations` row as
  "unattributed" anomalies.  Pre-Phase-63, an editor write
  (had it been allowed) would have triggered that scanner
  every time.  Now editor writes flow through the same audit
  trail as Hermes-driven writes and the scanner correctly
  skips them as attributed.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 62 — MLflow slim-down + catalog hand-off ✅ closed
  (2026-05-09).**  Symmetric application of the Phase-61 dbt
  pattern to MLflow.  Both embedded MLflow iframes (the `/ml`
  rail page and the model-detail "MLflow" tab) removed; `/ml`
  becomes a slim cockpit (Recent model registrations + Recent
  training runs + "Open in MLflow UI" external link), and the
  truly integrative pieces (which UC tables are model-prediction
  destinations, which recent registrations live in a given
  schema) hoist into the catalog flow.  Subprocess + reverse-
  proxy stay alive so the deep-links still resolve.

  - 62.F-Server-1:
    ``pointlessql/services/models_lineage.py`` gains
    ``aggregate_table_ml_relations()`` — single-query reverse
    index over ``lineage_row_edges.source_model_uri``,
    grouped by ``(target_table, source_model_uri)`` and parsed
    through ``models:/<full>/<version>``.  Exposed via the new
    ``GET /api/ml/table-relations?catalog=&schema=`` route in
    ``pointlessql/api/models_routes.py`` — analog of
    ``/api/dbt/manifest`` for the dbt side.  One pytest case
    in ``tests/test_models_lineage.py`` covers grouping +
    catalog/schema scoping.  Phase-62 reverse index covers only
    the *scoring* direction; "trained from this table"
    attribution would need a soyuz cross-reference per request
    and is deferred.
  - 62.A: ``frontend/templates/pages/mlflow.html`` — drop
    iframe + the inline "MLflow not running" alert (hoisted to
    a top-level card).  Header gains an "Open in MLflow UI"
    external button when subprocess is running.  Body becomes
    two cockpit cards driven by the new
    ``frontend/js/pages/mlflow_cockpit.js`` Alpine factory:
    Recent model registrations (10 latest from ``/api/models``)
    + Recent training runs (5 latest agent_runs filtered
    client-side by ``mlflow_run_id``).
    ``pointlessql/api/agent_runs_routes/_serializers.py``
    adds ``mlflow_run_id`` to the run-serialization output so
    the cockpit can filter + render deep-links.
  - 62.B: ``frontend/templates/pages/model.html`` — drop the
    iframe-bearing 4th tab ("MLflow") entirely; page is now
    4 tabs (Overview / Versions / Lineage / Promotion).
    Header gains an "Open in MLflow UI" external button
    deep-linking to the model registry.  Each Versions-table
    row's ``mlflow_run_id`` cell is now a deep-link to
    ``/mlflow/#/runs/<id>``.
  - 62.C: ``frontend/js/pages/dbt_schema_context.js`` extended
    with ML state (``mlAvailable``, ``mlModelByTable``,
    ``mlModels``, ``mlModelsLoading``).  ``init()`` fans out two
    parallel fetches (``/api/ml/table-relations`` scoped to the
    schema + ``/api/models`` filtered by catalog/schema).
    ``frontend/templates/pages/tables.html`` gains an inline
    "ml" badge on table-name rows that are model-prediction
    destinations (next to the existing dbt badge) plus a
    "Recent ML registrations" mini-card after the dbt card.
    Single-quoted Alpine attributes per BUG-64-01.
  - 62.D: New ``frontend/js/pages/ml_table_context.js`` Alpine
    factory (registered through ``bootstrap.js``).
    ``frontend/templates/pages/table.html`` wraps the existing
    ``dbtTableContext`` div in an outer ``mlTableContext`` div
    and renders a ``<template x-if="hasMl">`` "ML models" card
    next to the dbt card listing scoring models with edge
    counts + deep-links to ``/mlflow/#/models/<full>/versions/<v>``.
  - 62.E: ``frontend/js/pages/catalog_tree.js`` extended with
    ``mlRelations: Set`` + ``isMlTable(c, s, t)`` helper,
    populated via ``fetchMlRelations()`` in ``load()``.
    ``frontend/templates/components/sidebar.html`` table loop
    wraps both pills in a single ``ms-auto`` flex container so
    dbt + ml badges sit side-by-side without layout breakage.
  - All five surfaces silently no-op on installs without
    inference edges (empty response from ``/api/ml/table-relations``
    → empty ``mlRelations`` / no badge).  Only one new Python
    route; everything else reuses the existing ``/api/models/*``
    + ``/api/runs`` endpoints client-side.  No DB-schema
    changes — all data lives in
    ``lineage_row_edges.source_model_uri`` (Phase 21.7).

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 61 — dbt tab slim-down + catalog hand-off ✅ closed
  (2026-05-09).**  Embedded dbt-docs iframe removed and the
  truly integrative pieces (which UC tables are dbt-managed,
  recent dbt runs while browsing the catalog) hoisted into the
  catalog flow.  Subprocess + reverse-proxy stay alive so the
  new "Open dbt-docs" external-tab link still resolves.
  Established the pattern: **link out for tool-internal
  features, keep cross-tool integrative views first-class** —
  applies symmetrically to MLflow next.

  - 61.A: ``frontend/templates/pages/dbt.html`` — drop "Pipeline
    docs" tab + iframe; default-active flips to "Recent runs"
    (auto-loads); header-row "Open dbt-docs" external button
    when subprocess is running; setup-instructions alert hoists
    above the tab strip when subprocess isn't.
  - 61.B: New ``frontend/js/pages/dbt_schema_context.js`` Alpine
    factory (registered through ``bootstrap.js``).
    ``frontend/templates/pages/tables.html`` (schema-detail)
    gains an inline "dbt" badge on table rows that match a dbt
    model (deep-links to ``/dbt-docs/#!/model/<unique_id>``)
    plus a "Recent dbt runs" mini-card after the Tables card.
    Quoting bug caught in browser playbook: outer ``x-if=""``
    collided with ``|tojson`` double quotes; fixed by
    single-quoting the Alpine attributes.
  - 61.C: ``frontend/js/pages/catalog_tree.js`` extended with
    ``dbtRelations: Set`` + ``isDbtTable(c, s, t)`` helper,
    populated via ``fetchDbtManifest()`` in ``load()``.
    ``frontend/templates/components/sidebar.html`` table loop
    renders a tiny "dbt" pill in the tree.
  - 61.D: New ``frontend/js/pages/dbt_table_context.js``
    resolves the manifest model for the current table.
    ``frontend/templates/pages/table.html`` gains a
    ``<template x-if="dbtModel">`` card after Metadata showing
    unique_id, materialization badge, test count, and an
    "Open in dbt-docs" deep link.
  - All four surfaces silently no-op on installs without a
    dbt manifest (404 from ``/api/dbt/manifest`` → empty
    ``dbtRelations`` / null ``dbtModel``).  No new Python
    routes; everything reuses the existing ``/api/dbt/*``
    endpoints client-side.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 59 — Comprehensive UX-tour quality sweep ✅ closed
  (2026-05-08).**  60 implementable findings (out of 71 total,
  11 DESIGN deferred to Phase 60+) landed across 7 sub-sprints
  in one autonomous run + an 8th close commit, clearing all 8
  cross-cutting patterns.

  - 59.1 (``c0d93ae``): CONTENT-jargon sweep + ANSI-strip + 4
    isolated logic fixes.  /queries label rewrites, /audit/by-table
    description, /admin/system-info "Phase 29.3" jargon dropped,
    DuckDB ANSI-escape codes stripped, "Pull-modell" / "push-modell"
    German typo fixed, Source-card SHA-256 sentinel hidden when
    bytes ARE captured, Lineage-tab self-node duplication
    eliminated.
  - 59.2 (``2fc3e36``): Bootstrap-tab URL-state global helper.
    New ``frontend/js/tab_sync.js`` reads ``?tab=&subtab=`` on
    load and mirrors active-tab state back via
    history.replaceState.  Eleven templates gained
    ``data-pql-tab-key="<key>"``; 7 page-level + 4 run-detail
    sub-pane partials.
  - 59.3 (``4be934f``): Auth/error chromeless layout +
    ``pages/429.html``.  Login, register, 403, 404, 500 migrated
    away from full-app chrome.  Rate-limit middleware now
    renders the new template instead of a bare ``<h1>`` body.
  - 59.4 (``5a68258``): ``_macros/filter_collapsible.html`` —
    Bootstrap-collapse wrapper for dense filter rows.  Applied
    default-collapsed to /audit/inbox (6 fields), default-
    expanded to /queries (3 fields).
  - 59.5 (``70981b1``): Icon-rail re-mapping.  New AUDIT and
    REVIEWS top-items between ALERTS and PRODUCTS.  FEDERATION
    label/icon/href updated to CATALOG (section key
    ``federation`` kept internally).  Admin footer icon swapped
    bi-shield-check → bi-tools to free the icon for AUDIT.
    context_panel grew AUDIT + REVIEWS branches.
  - 59.6 (``a7cf5b6``): Sub-pane helper-text dual-mode sweep —
    /dashboards and /alerts sidebar helpers now reference both
    a UI path and an agent tool.  /connections, /volumes, /dbt
    skipped (share the catalog tree, no per-page sidebar to
    update).
  - 59.7 (``d1d90db``): Empty-state quality sweep on /volumes
    (3-step Docker / Python / Hermes), /models (3-step MLflow
    / Hermes / Docs), /branches (dual-mode notebook + agent).
  - 59.9 (this entry): Phase close — ROADMAP, CHANGELOG, memory.

  Tour artefacts:
  ``docs/internal/phase59_audit_findings.md`` (555 lines)
  + ``docs/internal/phase59_screenshots/`` (65 PNGs across 8
  themed folders).  Pattern P-2 was user-confirmed mid-tour
  (memory: ``feedback_auth_pages_chromeless.md``).

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 58 — Phase-57 carve-out trio closed.**  Three small
  deferred items from Sprint 57.8 land in one autonomous pass
  (single commit) post the user-prompt "mache die sofort follo
  up und pahse 58 noch ferig".  (1) admin_workspaces "Create"
  form → Bootstrap modal — closes the one DESIGN finding from
  the 57.1 audit.  (2) admin_audit_sinks empty-state icon
  ``bi-broadcast`` → ``bi-broadcast-pin`` — closes the one
  CONTENT finding.  (3) Query-card "View full SQL" drawer
  trigger via the Phase-56.8 ``detail_drawer`` macro — surfaces
  only when SQL > 700 chars so short queries stay clean.  Alpine
  listTable re-add on the queries card-grid stays parked (no
  user signal yet).  17 query-history + 12 admin_workspaces
  tests green.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 57 — Phase-56 carve-outs + route-test coverage closed.**
  Nine sub-sprints in one autonomous session post the user-prompt
  "plane aus!" on (1) ``queries.html`` Tables→Cards, (2) DESIGN-
  tagged findings from the 56.1 audit, (3) test-coverage sweep on
  admin_api_keys / federation / jobs / dashboards.  Plan-phase
  audit again reduced the set: the "DESIGN-tagged findings" carve-
  out turned out to be effectively empty (Section 4 of the
  ``phase56_audit_findings.md`` declared ``[DESIGN]`` as a
  tag-category but no individual finding actually carried the tag
  — all CONTENT/STRUCTURAL and folded into Sprint 56.10).  Sprint
  57.1 was repurposed as an audit-Ersatz on the ~15 surfaces the
  56.1 audit had never covered, producing 10 STRUCTURAL findings
  + 1 CONTENT + 1 DESIGN.  Net delta: ``/queries`` is now a
  card-grid with hljs SQL syntax-highlighting + server-side
  offset Load-More analog Phase 55.1 ``/runs``;  ``filter_kind``
  / ``status`` / ``since`` move to server-side Form-GET selects;
  ~85 new pytest cases across federation_routes (26),
  dashboards_routes (16), jobs_routes (14), admin_api_keys
  edge-cases (8), query history offset (5), card render (2);
  mobile data-label sweep on 7 more surfaces (admin_audit_sinks,
  admin_review_destinations, admin_workspaces dual tables,
  volumes, volume_detail, job_detail dual tables, branch_detail
  audit-log).  124 tests green across the touched test files.
  Carve-outs deferred to Phase 58: admin_workspaces "Create" form
  → modal (DESIGN), admin_audit_sinks empty-state icon swap
  (CONTENT-cosmetic), Alpine listTable re-add on queries-cards
  (only if user-replay calls for it).  Browser-replay verification
  for the queries cards + hljs render is left for the user post-
  rebuild — same handling as 54 / 55 / 56.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 56 — UX-polish + bug-hunt + semantic-content review
  closed.**  Three-wave audit-first sweep post the user-prompt
  "wir machen bug-hunting … und auch hunting von schlechter
  visualisierung … die *richtigen*, semantisch korrekten Inhalte".
  12 sub-sprints in one autonomous session.  Plan-phase audit
  collapsed the implementation set substantially: all 9
  BUG-53-NN markers turned out to be already-fixed-but-not-closed
  (closed in 56.2 with a per-marker evidence trail in
  ``_notes.md``); the worried-about Alpine x-data quoting risk
  on 10 templates turned out to be already-safe via Jinja's
  default ``|tojson`` ``\\uXXXX``-escape (regression test pins
  it); four of the Phase-53 visual-debt patterns (#1
  outline-button-opacity, #2 errors-no-sidebar, #6 UUID format,
  #8 tab-badges) were already-fixed-but-not-closed by earlier
  phases.  Net surface changes: 8 empty-states standardised
  on ``components/empty.html`` with action-oriented messages;
  7 list-tables get ``data-label`` for mobile-collapse; new
  display-layer Jinja filters ``format_uuid`` + ``format_hash``;
  three new reusable macros (``truncate_cell``, ``copy_btn``,
  ``detail_drawer``) applied across 13 surfaces; tables→cards
  conversion on ``agent_reviews_list`` + ``alerts``; semantic-
  content rewrites on three high-traffic descriptions
  (audit-inbox, audit-queries, run-source).  The user's
  emphasis on "die richtigen Inhalte" (semantically correct
  content) added Sub-Sprint 56.10 as a dedicated content-
  rewrite pass distinct from the layout-debt Wave-2/3
  mechanical sweeps.
