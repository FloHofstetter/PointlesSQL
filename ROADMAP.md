# Roadmap

Single source of truth for *what is done*, *what is in progress*, and
*what is next* in PointlesSQL. Read this before starting work so you
pick up where the previous session left off.

The phases below break the project down into milestones (`M0`) and
sprints (`Sprint N`). When a sprint lands, flip it to ✅ and append
the short commit hash. When the scope of a planned sprint becomes
clearer, expand its bullet list in place — do not create a separate
planning document. This mirrors the roadmap discipline established
in [`soyuz-catalog/ROADMAP.md`](../soyuz-catalog/ROADMAP.md).

Older closed phases that are no longer load-bearing for follow-up
conversations are *collapsed*: a one-line summary stays in this
file (in tabular form), and the full per-sprint detail moves to
[`docs/internal/roadmap_archive.md`](docs/internal/roadmap_archive.md).  See "How to update
this file" at the bottom for the collapse trigger.  Phase numbers
are preserved across the collapse so cross-references in
`CHANGELOG.md`, memory entries, and commit messages remain valid.

Status legend: ✅ done · 🟦 backbone shipped (deferred UI/wiring follow-ups) · 🔜 next · ⏳ planned · ⏳ partial · 🧊 on ice

## Current state

```text
PointlesSQL
│
├── Phases 0–47 — completed, collapsed                    ✅ done
│   │
│   │   Full per-sprint detail in
│   │   [`docs/internal/roadmap_archive.md`](docs/internal/roadmap_archive.md).  Phases 0-12.8
│   │   were collapsed in commit `3a90354` (2026-04-27); Phases
│   │   12.10-13.5 in the same commit; Phases 12.9 + 14-47 rolled
│   │   2026-05-12 to bring this file back under 2500 lines.
│   │
│   │   ```
│   │   Phase  Closed       Sprint range  What shipped
│   │   ─────  ───────────  ────────────  ─────────────────────────────────────
│   │     0    2026-01      M0–M1         Repo skeleton, hand-rolled httpx UC client, catalog browser prototype
│   │     1    2026-02      S1–S4         MVP: catalog UI + Notebook tab + pql Pandas/Delta helper
│   │     2    2026-02      S5            Catalog UI cards: tags, permissions, lineage, federation
│   │     3    2026-02      S6–S8         Auth: login, JWT sessions, grant enforcement (PointlesSQL = enforcement layer)
│   │     4    2026-03      S9–S10        `docker compose up` packaging, soyuz-client wheel, single-image flow
│   │     5    2026-03      S11–S12       Pluggable compute engines (DuckDB + Polars alongside Pandas)
│   │     5.5  2026-03      S13–S15       Quality pass: strict pyright, exception hierarchy, structured logs
│   │     6    2026-03      S16–S20       Foreign Postgres mirror, scheduler/jobs, cron mgmt UI
│   │     7    2026-03      S21–S22       Playwright-MCP live UI walkthroughs (every HTML route exercised)
│   │     8    2026-03      S23–S30       Notebook-as-job: Papermill execution, schedule, params, output
│   │     9    2026-03      S31–S40       UX overhaul: nav, search, toasts, breadcrumbs, dark mode, empty states
│   │    10    2026-03      S41–S43       Private GHCR + git-tag pinning, dual-auth Dockerfile
│   │    11    2026-03      S44–S47       CSRF, rate-limiting, JWT key rotation, in-app audit viewer, OIDC
│   │    12    2026-04      S48–S53       SQL editor (CodeMirror) + query history + audit-log hardening
│   │    12.5  2026-04      S54–S57       Charts, alerts (HMAC/CloudEvents/Atom/JSON-Feed), column stats, UC Volumes
│   │    12.6  2026-04      S58–S64       Native Monaco notebook editor (replaces JupyterLab iframe)
│   │    12.7  2026-04      S65–S80       Notebook editor UX overhaul (variable explorer, Marimo-grade)
│   │    12.8  2026-04      S81–S86       Frontend cleanup: ESM modules, CSS split, `pqlApi.fetch` CSRF wrapper
│   │    12.9  2026-05-05   S76–S95       LLM-friendly modularization (frontend 99.3% ESM, 28 modules / 5852 LOC)
│   │   12.10  2026-04      S96–S98       Notebook format hardening (UUID-free percent grammar, FNV-1a-64 hash)
│   │   12.11  2026-04      S99           Notebook visual polish (toolbar+badges only; S100–S102 cancelled)
│   │   12.12  2026-04-24   S103–S106     Agent-first pivot: delete browser editor, build read-only run-view
│   │    13    2026-04-26   S107–S128     Agent-run supervision + analytical memory; 13.11 = 10 reflexive tools
│   │    13.5  2026-04-26   S129–S140     Medallion + DuckDB-first opinion: pql.autoload/merge/aggregate
│   │    14    2026-04-26   —             Audit-trail completeness: cost-gate EXPLAIN + read-audit + soyuz cross-ref
│   │    15    2026-04-26   —             Lineage completeness: PQL→soyuz OpenLineage + lineage_row_edges + row-trace UI
│   │    15.5  2026-04-26   —             Aggregate Lineage + Rejects (walk_back tree + lineage_row_rejects + Rejects tab)
│   │    15.6  2026-04-26   —             Column-Level Lineage (lineage_column_map + sqlglot AST + column-trace UI)
│   │    15.7  2026-04-26   —             Value-Level Lineage (lineage_value_changes + CDF bootstrap + value-changes API)
│   │    15.8  2026-04-30   —             Lineage Wiring Audit (1 root cause: silver SELECT drops _lineage_row_id)
│   │    16    2026-04-27   —             First-Class Rollback (pql.rollback + RollbackError + /runs/{id}/rollback UI)
│   │    16.5  2026-04-29   —             Delta-Branching (tags + pql.branch/discard/promote/preview + control-room)
│   │    17    2026-04-29   —             UI Overhaul: icon-rail sidebar + 4-tab run-detail + cytoscape DAG + 6-tab table
│   │    18    2026-04-29   —             Audit Cockpit: inbox+badge + FTS + reverse-index + deeper-diff
│   │    19    2026-04-29   —             Audit-Reviewer Agent + Grafana: 3 personas + agent_reviews + 5 audit routes
│   │    20    2026-04-29   —             Forensics + Retention: stream-fwd (webhook/S3/CloudTrail) + PII hash + TTLs
│   │    21    2026-04-30   —             ML Registry: MLflow subprocess + UC MODEL securable + 5-tab + autolog
│   │    22    2026-04-30   —             Documentation site (mkdocs-material, ~30 pages, ADR-0004 launch-flip)
│   │    23    2026-05-05   23.0–23.5     Contextual help-popovers (5 hero + models/runs/branches/audit anchors)
│   │    28    2026-05-05   —             Workspace isolation (Databricks-style soft, per-workspace audit-sink)
│   │    29    2026-05-05   —             Workspace polish: OIDC group→workspace mapping + Grafana $workspace var
│   │    30    2026-05-05   —             Postgres production-readiness (PG FTS + sqlite→pg migration CLI + pool tune)
│   │    31    2026-05-05   31.0–31.4     Test-suite speed: SQLite 30min→68s (bcrypt rounds=4 + session-scope schema)
│   │    32    2026-05-05   —             PG test quality: 45 failures → 0 (session.flush adds + dialect-aware seeds)
│   │    33    2026-05-05   —             Admin Console: /admin/{audit-sinks,review-destinations,api-keys,system-info}
│   │    34    2026-05-05   —             Cross-Workspace Observability: 8 new Grafana panels
│   │    35    2026-05-06   —             Targeted modularization: _branch 1310→branch/, lineage_edges 1137→lineage/
│   │    36    2026-05-06   —             Declarative Pipelines + Expectations
│   │    37    2026-05-06   —             Playwright coverage refresh (44→48 walkthroughs, 6 BUG-37 fixed in 37.1)
│   │   37.1   2026-05-06   —             Phase-37 BUG sweep (HTMX 2.0.6, dbt chrome, admin x-data escape)
│   │    38    2026-05-06   —             Sprint-Sweep: 35.4 (run_view→8 partials) + 36.7 unblocked via mashumaro 3.17
│   │    39    2026-05-06   —             Agent EXPLAIN-driven self-rewrite loop (structured envelope rewrite)
│   │    40    2026-05-06   —             Lakehouse Federation reads (OpenLineage POST + table-detail merged graph)
│   │   40.5   2026-05-06   —             Foreign-Delta CDF tail (pull-modell, deferred from 40.2 at plan time)
│   │   40.6   2026-05-06   —             CDF Tail UI integration
│   │   40.7   2026-05-06   —             Row-Trace fold-in of CDF events
│   │    41    2026-05-07   —             Sprint 17.6 promoted: 3 lineage sub-pills (Row/Column/Value) in run-detail
│   │    42    2026-05-07   —             Anomaly-Inbox System-Errors band
│   │    43    2026-05-07   —             Error envelope + exception hierarchy unification
│   │    44    2026-05-07   —             Structured logging + traceback preservation
│   │    45    2026-05-07   —             Pyright Hot-Spot Cleanup (559→497 warnings)
│   │    46    2026-05-07   —             Test-Auth-Fixture Centralization (admin_client/non_admin_client/anonymous_client)
│   │    47    2026-05-07   —             NewType ID Hardening (RunId/OpId/QueryHistoryId, ~36 consumer signatures)
│   │   ```
│   │
│
├── Phase 71 — Data-Product Marketplace polish  ✅ archived (2026-05-12)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-71-data-product-marketplace-polish`](docs/internal/roadmap_archive.md#phase-71-data-product-marketplace-polish) in W2.
│
├── Phase 72 — Agent-Aware Social Layer  ✅ archived (2026-05-13)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-72-agent-aware-social-layer`](docs/internal/roadmap_archive.md#phase-72-agent-aware-social-layer) in W2.
│
├── Phase 73 — Agent-authored data products  ✅ archived ((date n/a))
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-73-agent-authored-data-products`](docs/internal/roadmap_archive.md#phase-73-agent-authored-data-products) in W2.
│
├── Phase 74 — Reviewer-Agent v2 (Active steward delegate)  ✅ archived (2026-05-15)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-74-reviewer-agent-v2-active-steward-delegate`](docs/internal/roadmap_archive.md#phase-74-reviewer-agent-v2-active-steward-delegate) in W2.
│
├── Phase 77 — Social-as-Connective-Tissue across the platform  ✅ archived (2026-05-15)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-77-social-as-connective-tissue-across-the-platform`](docs/internal/roadmap_archive.md#phase-77-social-as-connective-tissue-across-the-platform) in W2.
│
├── Phase 78 — Polish bundle  ✅ archived (2026-05-16)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-78-polish-bundle`](docs/internal/roadmap_archive.md#phase-78-polish-bundle) in W2.
│
├── Phase 79 — Code-quality + modularisation bundle  ✅ archived (2026-05-15)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-79-code-quality--modularisation-bundle`](docs/internal/roadmap_archive.md#phase-79-code-quality--modularisation-bundle) in W2.
│
├── Phases 82-85 — Strategic axes (post-81 horizon)  ✅ archived (2026-05-17)
│   │
│   │   Detail moved to [`roadmap_archive.md#phases-82-85-strategic-axes-post-81-horizon`](docs/internal/roadmap_archive.md#phases-82-85-strategic-axes-post-81-horizon) in W2.
│
├── Phase 86 — Modularisierungs- & Dedup-Welle  ✅ archived (2026-05-16)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-86-modularisierungs---dedup-welle`](docs/internal/roadmap_archive.md#phase-86-modularisierungs---dedup-welle) in W2.
│
├── Phase 87 — Restschuld I: config + repo_assets + audit  ✅ archived (2026-05-16)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-87-restschuld-i-config--repoassets--audit`](docs/internal/roadmap_archive.md#phase-87-restschuld-i-config--repoassets--audit) in W2.
│
├── Phase 88 — Restschuld II: SQL/dbt cluster  ✅ archived (2026-05-16)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-88-restschuld-ii-sqldbt-cluster`](docs/internal/roadmap_archive.md#phase-88-restschuld-ii-sqldbt-cluster) in W2.
│
├── Phase 89 — Restschuld III: endgame  ✅ archived (2026-05-16)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-89-restschuld-iii-endgame`](docs/internal/roadmap_archive.md#phase-89-restschuld-iii-endgame) in W2.
│
├── Phases 90-92 — Agent-native lakehouse axis (post-Lakebase)  ✅ archived (2026-05-19)
│   │
│   │   Detail moved to [`roadmap_archive.md#phases-90-92-agent-native-lakehouse-axis-post-lakebase`](docs/internal/roadmap_archive.md#phases-90-92-agent-native-lakehouse-axis-post-lakebase) in W2.
│
├── Phase 93 — Notebook-Editor UX quick wins  ✅ archived (2026-05-19)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-93-notebook-editor-ux-quick-wins`](docs/internal/roadmap_archive.md#phase-93-notebook-editor-ux-quick-wins) in W2.
│
├── Phase 94 — Notebook-Editor UX polish  ✅ archived (2026-05-19)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-94-notebook-editor-ux-polish`](docs/internal/roadmap_archive.md#phase-94-notebook-editor-ux-polish) in W2.
│
├── Phases 95–105 — Notebook v3 (DBX-parity + agent-native lift)  🟦 backbone shipped 2026-05-20
│       Multi-phase axis to bring notebooks to Databricks-parity on
│       the basics (cell-level UX, revision history, widget cells,
│       permissions, dashboard view) and surpass on the
│       agent-native + provenance axes where shoreguard, Phase-90
│       memory and the delta-branching idea give us infrastructure
│       DBX doesn't have.  Notebooks are already polymorphic-social
│       at notebook-level since Phase 77.6; the natural next step
│       is cell-level granularity.  Phase scoping is intentionally
│       narrow — exact specs land in dedicated plan files before
│       each sprint.  Order respects dependencies (cell-level
│       social + revision history land before reviewer-per-cell +
│       replay mode).
│
│   ├── Phase 95 — Cell-level social                              ✅ shipped (local, 2026-05-19)
│   │   │
│   │   │   Extends the Phase-77.6 polymorphic-social schema down to
│   │   │   single cells.  A user (or a Phase-101 reviewer agent) can
│   │   │   now drop a comment on the specific cell that broke, react
│   │   │   to the chart in cell 7, follow that one cell, and tag it
│   │   │   with ``#etl`` / ``#draft`` / ``#prod`` for light
│   │   │   categorisation.  Closest analog: Google Colab
│   │   │   cell-comments (DBX has no real cell-social surface).
│   │   │
│   │   │   The hard part — stable cell identity that survives source
│   │   │   edits while keeping the ``.py`` file IDE-agnostic — gets
│   │   │   solved by a new ``notebook_cells`` mapping table + a
│   │   │   three-pass reconciler at save time (exact-hash, then
│   │   │   similarity-gated ordinal fallback, then fresh UUID).
│   │   │   See [`docs/concepts/cell-level-social.md`](docs/concepts/cell-level-social.md)
│   │   │   for the conceptual model and the known limitation.
│   │   │
│   │   ├── 95.0 — Schema + polymorphic plumbing                  ✅ shipped
│   │   │     Two Alembic migrations (``s7u9w1y3b5d7`` creates
│   │   │     ``notebook_cells``; ``t8v0x2z4c6e8`` extends
│   │   │     ``ck_social_targets_kind`` with ``notebook_cell``,
│   │   │     line-by-line mirror of Phase 90's ``p4r6t8v0x2z4``).
│   │   │     ``NotebookCellIdentity`` model in
│   │   │     [`pointlessql/models/notebook.py`](pointlessql/models/notebook.py)
│   │   │     (named ``Identity`` to avoid collision with the doc-
│   │   │     level dataclass).  ``EntityKindSpec(key='notebook_cell',
│   │   │     supports_reviews=False, …, tab_keys=('discussion',
│   │   │     'followers'))`` in
│   │   │     [`entity_registry.py`](pointlessql/services/social/entity_registry.py).
│   │   │     Workspace-resolver arm in
│   │   │     [`_target_resolver.py`](pointlessql/services/social/_target_resolver.py).
│   │   │     ``{uuid36}:{uuid36}`` composite-ref shape validator in
│   │   │     [`_kind_dispatch.py`](pointlessql/api/social_routes/_kind_dispatch.py).
│   │   ├── 95.1 — Save-path reconciliation                       ✅ shipped
│   │   │     Three-pass reconciler in
│   │   │     [`pointlessql/services/notebook/cell_reconciliation.py`](pointlessql/services/notebook/cell_reconciliation.py):
│   │   │     (1) exact-hash with same-hash ordinal-proximity tiebreak,
│   │   │     (2) similarity-gated ordinal fallback (3-char Jaccard
│   │   │     shingles, 0.5 threshold) — the gate that prevents
│   │   │     "delete + insert at same position steals UUID",
│   │   │     (3) fresh UUID for genuinely new cells.  Unmatched
│   │   │     existing rows get soft-deleted via ``removed_at``.
│   │   │     Wired into [`io.py`](pointlessql/api/notebooks_routes/io.py)
│   │   │     at the post-``save_document`` hook; load route emits
│   │   │     ``cell_uuid`` per cell + ``notebook_uuid`` at top level.
│   │   │     11 unit tests cover scenarios (a)–(h) from the plan
│   │   │     plus reformat-all + no-op + empty-save.
│   │   ├── 95.2 — Frontend chip + inline thread + bulk-counts    ✅ shipped
│   │   │     New ``cellThread()`` Alpine factory in
│   │   │     [`frontend/js/notebook/cell_thread.js`](frontend/js/notebook/cell_thread.js)
│   │   │     mounted per cell.  The ``💬 N`` chip lives in the
│   │   │     cell-header right cluster; the collapsible thread
│   │   │     region renders below the output zone via
│   │   │     [`_partials/notebook_editor/cell_thread.html`](frontend/templates/pages/_partials/notebook_editor/cell_thread.html).
│   │   │     Lazy-loaded on first open; comments / 6-emoji reactions
│   │   │     / follow ride the existing polymorphic
│   │   │     ``/api/social/notebook_cell/{ref}/...`` routes.  New
│   │   │     bulk-counts endpoint at
│   │   │     [`_notebook_cell_counts.py`](pointlessql/api/social_routes/_polymorphic_handlers/_notebook_cell_counts.py)
│   │   │     aggregates comments + reactions + followers for one
│   │   │     notebook in a single query (notebook-load + post-save
│   │   │     refresh).  Asset-version bump to ``0.1.0rc15``.
│   │   ├── 95.3 — Cell-tags hybrid picker                        ✅ shipped
│   │   │     Curated vocabulary (``etl``, ``draft``, ``prod``,
│   │   │     ``wip``, ``verified``, ``broken``) in
│   │   │     [`pointlessql/services/notebook/cell_tags.py`](pointlessql/services/notebook/cell_tags.py);
│   │   │     ``cellTagPicker()`` Alpine factory in
│   │   │     [`frontend/js/notebook/cell_tag_picker.js`](frontend/js/notebook/cell_tag_picker.js)
│   │   │     mounted in the cell-header LEFT cluster.  Hybrid:
│   │   │     dropdown of curated tags plus a "Custom…" escape for
│   │   │     free-text entries.  Mutates ``cell.tags`` in place
│   │   │     (memory rule ``feedback_alpine_nested_object_replace``);
│   │   │     dispatches ``pql:cell-tag-changed`` so the parent
│   │   │     editor's autosave debouncer picks up the change.  No
│   │   │     schema work — the marker grammar already round-trips
│   │   │     arbitrary tag lists losslessly.
│   │   └── 95.4 — Walkthrough + concept doc + nav                ✅ shipped
│   │         [`docs/concepts/cell-level-social.md`](docs/concepts/cell-level-social.md)
│   │         explains the reconciliation algorithm + the documented
│   │         limitation + the forward-compat contract Phase 101 keys
│   │         off.  [`docs/e2e-walkthroughs/notebook-cell-social.md`](docs/e2e-walkthroughs/notebook-cell-social.md)
│   │         covers the 8-step Playwright playbook with step 5 as
│   │         the headline identity-survival test.  Concept nav entry
│   │         after ``Agent memory``; walkthrough entry in the
│   │         Notebook cluster.
│   │
│   ├── Phase 96 — Inline AI-Assistant in notebook                ✅ shipped (local, 2026-05-19)
│   │     Lifted the Phase-91 NL→SQL hermes-agent chat panel into
│   │     the notebook editor.  Three new hermes-plugin tools:
│   │     ``pql_propose_cell`` (code or markdown),
│   │     ``pql_fix_cell``, ``pql_explain_cell``.  Provenance
│   │     trail records which agent proposed which cell version
│   │     in the append-only ``notebook_cell_provenance`` table
│   │     (separate from ``notebook_cell_identity`` so Phase 97
│   │     revision history can render the full agent chain).
│   │     Direct counter to DBX-Assistant's commercial pitch.
│   │
│   │     Sub-phases:
│   │       * **96.A** — refactor(editor-chat): rename
│   │         ``sql_chat`` → ``editor_chat`` services + models +
│   │         settings (no shim).  Env prefix
│   │         ``POINTLESSQL_SQL_CHAT_*`` →
│   │         ``POINTLESSQL_EDITOR_CHAT_*``.  Generic substrate
│   │         (session table, broker, agent factory, turn runner)
│   │         is shared between the SQL-editor chat (Phase 91)
│   │         and the notebook AI assistant.  Commit ``52d2f1e``.
│   │       * **96.B** — new ORM tables
│   │         ``notebook_cell_proposals`` (polymorphic
│   │         propose/fix/explain with status lifecycle) and
│   │         ``notebook_cell_provenance`` (append-only audit).
│   │         New WS endpoint ``/ws/notebook/chat/{editor_session_id}``
│   │         (fork of ``sql_chat_ws``; drops ``refine``).  New
│   │         REST routes ``/api/notebook/chat/...``: propose-cell,
│   │         fix-cell, explain-cell, accept, discard, plus
│   │         ``GET /api/notebook/chat/cell/{cell_uuid}/explanations``.
│   │         Agent factory gains a ``surface`` arg (``"sql"``
│   │         vs ``"notebook"``) so the plugin's env-var split
│   │         registers the right propose-tool family per turn.
│   │         ``/api/notebooks/save`` extended to flush
│   │         ``proposal_acceptances`` into provenance rows after
│   │         the cell-reconciliation pass mints the final
│   │         ``cell_uuid``.  Alembic migration
│   │         ``u9w1y3a5d7f9_phase96_notebook_chat_proposals``.
│   │       * **96.C** — three new ``hermes-plugin-pointlessql``
│   │         tools (``pql_propose_cell`` / ``pql_fix_cell`` /
│   │         ``pql_explain_cell``), three matching
│   │         :class:`PointlessClient` methods, ``PluginConfig``
│   │         gains ``notebook_chat_session_id``, ``register_all``
│   │         wires them.  Plugin commit ``1ddf587``.
│   │       * **96.D** — frontend: new
│   │         ``notebookChatPanel`` Alpine factory (forked from
│   │         the SQL chat panel), ``chat_drawer.html`` partial
│   │         with three proposal banner variants
│   │         (propose=Insert / fix=Apply / explain=auto-attach),
│   │         ``chat_integration.js`` mixin that bridges accepted
│   │         proposals back to the editor via a
│   │         ``pql:cell-proposal-accepted`` window event,
│   │         ``cell_operations.js`` gains
│   │         ``insertCellFromProposal`` /
│   │         ``updateCellSourceByUuid``, ``persistence.js``
│   │         threads ``proposal_acceptances`` through save,
│   │         toolbar AI button beside Variables/Jobs, social
│   │         drawer's per-cell view gains an "AI Explanations"
│   │         section.  Asset version bumped to ``0.1.0rc29``.
│   │       * **96.E** — pytest: 14 tests across
│   │         ``test_notebook_chat_routes.py`` (model + route
│   │         lifecycle + idempotency + rename guard) +
│   │         ``test_notebook_chat_ws.py`` (4 WS smoke tests
│   │         incl. surface routing assertion) +
│   │         ``test_notebook_save_provenance.py`` (save-path
│   │         flush round-trip for both propose + fix).  Plugin
│   │         side adds 10 tests in ``tests/test_cell_tools.py``.
│   │         Markdown walkthrough
│   │         [`docs/e2e-walkthroughs/notebook-assistant.md`](docs/e2e-walkthroughs/notebook-assistant.md)
│   │         + seed notebook
│   │         [`notebooks/phase96_walkthrough.py`](notebooks/phase96_walkthrough.py).
│   │
│   │     Deferred to Phase 96.1: per-cell inline Fix/Explain
│   │     header buttons that pre-fill the chat panel with a
│   │     templated prompt referencing the focused cell.
│   │
│   ├── Phase 97 — Revision history + Diff + Pin-to-memory          ✅ done 2026-05-21
│   │     Save-snapshots in our own metadata DB (not the on-disk
│   │     ``.py`` file).  New ``NotebookRevision`` table + migration
│   │     ``47832b8d57ca``; canonical JSON encoding + SHA-256 in
│   │     ``services/notebook/revisions.py``; idempotent on the
│   │     canonical hash so a re-save with identical content collapses
│   │     to the existing row.  Cell-by-cell diff via the stable
│   │     ``content_hash`` identity emits ``added`` / ``removed`` /
│   │     ``changed`` / ``moved`` / ``unchanged`` envelopes the front-
│   │     end can hand to Monaco's diff editor.  REST: POST + GET on
│   │     ``/api/notebooks/revisions``; ``GET .../{uuid}`` for full
│   │     payload; ``GET .../diff?left=…&right=…``.  14 new pytest.
│   │     Asset 0.1.0rc35.  Shipped 2026-05-20.
│   │
│   │     **97.X.1 — Pin-to-memory backend** ✅ shipped 2026-05-21,
│   │     commit ``36dc878``, asset rc69.  ``notebook_revision_facts``
│   │     table + migration ``d8f1a3b5c7e9``; ``OpName.PIN_FACT`` in
│   │     the agent-ops enum; new ``services/notebook/facts.py``
│   │     primitive idempotent on ``(workspace_id, revision_id,
│   │     cell_content_hash)`` partial-UNIQUE; four REST endpoints
│   │     under ``/api/notebooks/facts`` (POST + GET list + GET
│   │     detail + DELETE soft-unpin); ``pql.facts`` PQL facade with
│   │     agent env-bridge via ``POINTLESSQL_AGENT_RUN_ID``;
│   │     ``social_targets.entity_kind`` CHECK widened with two new
│   │     kinds (``notebook_revision`` + ``notebook_cell_output``)
│   │     plus matching ``entity_registry`` URL builders; best-effort
│   │     ``fanout_event(event_type='notebook_revision_pinned', …)``
│   │     wired so pins land in the Phase-81 inbox.  18 new pytest.
│   │
│   │     **97.X.2 — Pin-to-memory UI** ✅ shipped 2026-05-21, commit
│   │     ``cfaad5c``, asset rc70.  📌 button in the Phase-97
│   │     revisions panel + cell-header chip (lit
│   │     ``btn-outline-warning`` when a fact exists) reusing the
│   │     outer-scope mixin pattern (no nested-x-data trap); new
│   │     ``frontend/js/notebook/cell_facts.js`` + extension of
│   │     ``revisions.js``; bulk lookup at ``/api/notebooks/facts/bulk``
│   │     for per-cell hot-paths; ``/library/facts`` browse page
│   │     wired through ``library_facts.html`` + Alpine factory in
│   │     ``bootstrap.js``; cell-output pin auto-snapshots a fresh
│   │     revision before pinning so the fact always points at a
│   │     concrete row.  2 new pytest.
│   │
│   │     **97.X.3 — Pin feed-card closure** ✅ shipped 2026-05-21,
│   │     asset rc72.  Dedicated ``render_kind = "fact"`` branch in
│   │     ``classify_notification`` + SSE ``_classifyEvent`` mirror +
│   │     new Alpine ``<template x-if="r.render_kind === 'fact'">``
│   │     block in ``activity_pane.html`` showing
│   │     ``bi-pin-angle-fill`` + summary text.  5 new pytest
│   │     covering classify + envelope + e2e fanout + null-actor
│   │     agent path.  Playwright-MCP playbook extended with Part P
│   │     in ``notebook-editor.md`` + new ``library-facts.md``.
│   │
│   │     **Deferred (genuine blocker):**
│   │     * **Shoreguard signing** — Phase 97's cryptographic verify
│   │       leg is paused.  The shoreguard-fresh checkout exposes
│   │       webhook + OIDC + auth signing helpers but no public
│   │       "sign-this-revision" API yet; ``signature_alg`` and
│   │       ``signature`` columns are reserved on the row so a
│   │       follow-up sprint can populate them once the API ships.
│   │       Every snapshot still records its deterministic SHA-256.
│   │     * **Monaco diff UI** — backend envelope is ready and
│   │       Wave-D-1 lit up the side-by-side panel; the Monaco
│   │       editor-mode renderer is a follow-up (gated by the
│   │       nested-x-data trap, same reason 98.C's chip render was
│   │       deferred — re-eval once Phase 105 awareness layer lands
│   │       and the outer-scope mixin pattern is dominant).
│   │
│   ├── Phase 98 — DBX-parity quick wins bundle                   ✅ done 2026-05-20
│   │     Single sprint covering four small DBX-parity items:
│   │     magic commands (``%sql``, ``%md``, ``%fs ls``,
│   │     ``%timeit``) as a thin pre-processor; notebook-tags +
│   │     template gallery (``/notebooks/new from template``);
│   │     cell-level lineage badges in the cell header reading
│   │     existing ``agent_run_operations`` write events;
│   │     notebook → static HTML/PDF export.
│   │       * 98.A ✅ done 2026-05-20 — magic-command pre-processor.
│   │         New ``services/notebook/magic_commands.py``: %sql / %md
│   │         (line + block) / %fs ls / %timeit.  Bootstrap helpers
│   │         (``__pql_magic_md__`` / ``__pql_magic_fs_ls__`` /
│   │         ``__pql_magic_timeit__``) added to the kernel session.
│   │         WS execute handler now runs the pre-processor before
│   │         kernel dispatch, resolving SQL approval server-side per
│   │         %sql line.  13 new pytest covering line/block parsing,
│   │         placeholder splicing, and indent preservation.
│   │       * 98.D ✅ done 2026-05-20 — static HTML / PDF export.
│   │         New ``services/notebook/export.py`` builds a self-
│   │         contained HTML document (inline CSS, no external assets,
│   │         ``@page`` print stylesheet) from the parsed ``.py`` doc +
│   │         the latest-session ``notebook_outputs`` rows.  Output
│   │         frames reuse the existing
│   │         ``services.output_rendering.render_output_frame``
│   │         pipeline.  Optional ``render_notebook_pdf`` produces real
│   │         ``application/pdf`` via WeasyPrint when importable; falls
│   │         back to the HTML body + diagnostic header
│   │         ``X-PointlesSQL-Export-Fallback`` so the UI can suggest
│   │         the browser's *Save as PDF*.  Routes
│   │         ``GET /api/notebooks/export.html`` and ``/export.pdf``.
│   │         9 new pytest.
│   │       * 98.C ✅ done 2026-05-20 — cell-level lineage badges.
│   │         New ``services/notebook/cell_lineage.py`` joins
│   │         ``notebook_cell_runs`` (filtered to rows with
│   │         ``agent_run_id`` set) → ``agent_run_operations``
│   │         (filtered to the 13 WRITE op_names) and collapses
│   │         duplicate ``(op_name, target_table)`` pairs to the most
│   │         recent occurrence.  REST ``GET
│   │         /api/notebooks/cell/lineage`` surfaces the badges to a
│   │         future cell-header UI; backend-only ship (UI affordance
│   │         deferred to a follow-up to avoid the x-data + |tojson
│   │         playbook-gate cost).  8 new pytest.
│   │       * 98.B ✅ done 2026-05-20 — notebook tags + template
│   │         gallery.  New ``NotebookTag`` ORM table + migration
│   │         ``b185acda50d7`` for notebook-level lifecycle tags
│   │         (distinct from the marker-grammar cell tags); curated
│   │         vocabulary (``etl`` / ``draft`` / ``prod`` / etc.) plus
│   │         free-text with ``[a-z0-9_-]`` validation, 16-tag cap
│   │         per notebook.  New ``services/notebook/tags.py``
│   │         service + ``api/notebooks_routes/tags.py`` routes
│   │         (GET / POST / DELETE ``/api/notebooks/tags``).
│   │         Template gallery ships four starter ``.py`` files
│   │         under ``pointlessql/data/notebook_templates/`` driven
│   │         by ``_manifest.json``: blank, sql_exploration,
│   │         etl_pipeline, ml_quickstart.  New
│   │         ``services/notebook/templates.py`` + routes
│   │         ``GET /api/notebooks/templates`` and ``POST
│   │         /api/notebooks/from-template``.  13 new pytest.
│   │         **Wave-B UI 2026-05-20 (asset 0.1.0rc47):** notebook-
│   │         level tag picker shipped in the editor toolbar
│   │         (next to Variables/AI), driven by new
│   │         ``installNotebookTags`` mixin + ``notebookTagPicker``
│   │         inline panel.  Curated chips + custom-tag input +
│   │         pill-list of active tags with one-click removal +
│   │         count badge on the button.  Workspace-list tag-pills
│   │         still deferred.
│   │
│   ├── Phase 99 — Widget-cells + Notebook permissions            ✅ done 2026-05-21
│   │     Backend shipped 2026-05-20.  Two new tables (migration
│   │     ``b944b9be7e03``):
│   │     * ``notebook_widgets`` — parameter widgets keyed
│   │       ``(notebook_id, name)`` with ``widget_kind`` ∈
│   │       ``dropdown`` / ``slider`` / ``text``; JSON-encoded
│   │       ``config`` + ``default_value``.
│   │     * ``notebook_permissions`` — per-notebook share grants
│   │       (``view`` / ``run`` / ``edit`` lattice); layered on top
│   │       of workspace membership.
│   │     Services: ``services/notebook/widgets.py``
│   │     (``upsert_widget`` / ``list_widgets`` /
│   │     ``resolve_widget_values`` / ``delete_widget``) and
│   │     ``services/notebook/permissions.py`` (``grant_permission``,
│   │     ``revoke_permission``, ``get_effective_role``,
│   │     ``role_satisfies``).  REST: ``GET|PUT|DELETE
│   │     /api/notebooks/widgets``, ``POST .../widgets/resolve``,
│   │     ``GET|PUT|DELETE /api/notebooks/permissions``.  12 new
│   │     pytest.  Asset 0.1.0rc37.
│   │
│   │     **Wave-C UI 2026-05-20 (asset 0.1.0rc56):** Widgets-CRUD
│   │     panel + per-notebook permission grants both shipped.
│   │     Toolbar buttons "Widgets" / "Access" open inline panels
│   │     with full CRUD on ``GET|PUT|DELETE /api/notebooks/widgets``
│   │     and ``GET|PUT|DELETE /api/notebooks/permissions``.  The
│   │     widgets panel surfaces resolved values via
│   │     ``POST /widgets/resolve`` so the user sees what the
│   │     kernel would receive.  The permissions panel exposes the
│   │     ``view < run < edit`` lattice with inline role editing.
│   │
│   │     **Closure 2026-05-21:** ``pql.widgets()`` kernel shim
│   │     landed.  The kernel session already stamps
│   │     ``POINTLESSQL_NOTEBOOK_ID`` via
│   │     ``services/notebook/kernel_session/session.py``;
│   │     ``PQL.widgets()`` reads the active notebook id from
│   │     :mod:`pointlessql.pql.context`, lazy-bootstraps the
│   │     metadata DB if the subprocess hasn't already, and
│   │     calls ``resolve_widget_values``.  Outside the editor
│   │     (interactive REPL / unbound context) the method
│   │     returns an empty dict so ``params = pql.widgets()``
│   │     is safe to write unconditionally.  Route-layer
│   │     enforcement (``actor_has_role``) was already wired
│   │     into the load (``api_load_notebook``), save
│   │     (``api_save_notebook``), kernel WS open, and co-edit
│   │     WS open paths at Wave-C ship — nothing further was
│   │     needed there.
│   │
│   ├── Phase 100 — Publish notebook (external share + dashboard) ✅ done 2026-05-21
│   │     Two orthogonal pieces shipped together because they share
│   │     a route + rendering pipeline:
│   │     (a) **Public share via UUID** — ChatGPT-shared-chat
│   │     pattern: clicking "Publish" mints an unguessable v4 UUID
│   │     under ``/share/notebook/{uuid}``.  No auth required,
│   │     read-only.  Two share modes (publisher picks at publish
│   │     time, switchable later):
│   │       * **Snapshot** *(default — safer)* — freezes the
│   │         current notebook state (cells + outputs + exec
│   │         counts) as a tagged Phase-97 revision; later in-place
│   │         edits don't leak.  Re-publish updates the snapshot
│   │         under the same UUID (link stays stable); Unpublish
│   │         revokes entirely.  Reproducible / audit-friendly.
│   │       * **Live** *(opt-in, with warning)* — link always
│   │         reflects the current ``.py`` + last-known outputs.
│   │         For team dashboards / stakeholder views where you
│   │         want auto-update without re-publishing.  Higher risk
│   │         (an accidental secret-push lands publicly the moment
│   │         you save) so the toggle ships behind an explicit
│   │         confirm dialog and a persistent "LIVE share" badge
│   │         in the editor toolbar while active.
│   │     Snapshot storage piggybacks on Phase 97 revision history.
│   │     Common to both modes: admin-gated, (optional) expiry,
│   │     outputs scrubbed for secrets, "public share" watermark,
│   │     iframe-embed-friendly analog to Phase-92.2's
│   │     ``/embed/semantic_search/{fqn}`` surface.
│   │     (b) **Dashboard rendering mode** — strips code cells,
│   │     renders only markdown + outputs as a clean read-only
│   │     view; re-uses ``output_rendering.py``.  Available both
│   │     under the public share UUID and under
│   │     ``/notebooks/dashboard/{path}`` for workspace-internal
│   │     consumption.  DBX-parity (and ChatGPT-parity) for the
│   │     "publish a notebook" flow.
│   │
│   │     Backend shipped 2026-05-20.  New ``notebook_shares`` table
│   │     + migration ``8c7c6eb5add5``.  Share-mode lattice
│   │     (``snapshot`` / ``live``) plus a ``dashboard_mode`` flag
│   │     persisted per-share.  Snapshot publishes mint a fresh
│   │     Phase-97 :class:`NotebookRevision` and pin the share to
│   │     it; live shares carry no revision pin.  Service in
│   │     ``services/notebook/shares.py`` (``create_share``,
│   │     ``update_share``, ``revoke_share``, ``get_active_share``,
│   │     ``list_shares_for_notebook``, ``render_dashboard_html``).
│   │     Admin REST: ``GET|POST /api/notebooks/shares``,
│   │     ``PATCH|DELETE /api/notebooks/shares/{share_uuid}``.
│   │     Public viewer: ``GET /share/notebook/{share_uuid}`` —
│   │     no auth required; 410 Gone for revoked / expired /
│   │     unknown share UUIDs.  Dashboard render keeps markdown
│   │     cells, replaces code cells with placeholder slots so
│   │     their outputs still surface in original order, prepends
│   │     a "DASHBOARD" banner.  8 new pytest.  Asset 0.1.0rc38.
│   │
│   │     **Wave-B UI 2026-05-20:** Share-Dialog shipped (asset
│   │     0.1.0rc49 → rc51).  Toolbar Share-button opens a modal
│   │     with Snapshot/Live mode toggle, Dashboard-mode checkbox,
│   │     optional snapshot-note input, and a list of existing
│   │     shares with Open-in-new-tab / Copy-URL / Toggle-Dashboard
│   │     / Revoke actions per row.  Replay caught + fixed a
│   │     latent backend bug: ``/share/`` was missing from the
│   │     auth middleware's ``PUBLIC_PREFIXES`` allowlist, so the
│   │     public viewer had been 303-redirecting every visitor
│   │     to ``/auth/login`` since initial Phase-100 ship.
│   │
│   │     **Wave-D-4 closure 2026-05-21:** iframe-embed analog of
│   │     Phase-92.2's ``/embed/semantic_search/{fqn}`` shipped as
│   │     ``GET /embed/notebook_share/{share_uuid}`` (commit
│   │     ``e91da74``); same content + scrub as the public viewer
│   │     with ``compact=True`` so the iframe parent owns the
│   │     chrome.  Secret-scrub pass landed alongside —
│   │     ``services/notebook/shares.scrub_outputs`` regex-redacts
│   │     AWS / GCP / GitHub / Slack tokens + ``password=``-style
│   │     keys-in-values across every output frame before render.
│   │     Both the public viewer and the embed route consume the
│   │     scrubbed copy so a publisher who forgets to vet outputs
│   │     gets defence-in-depth instead of a leak.  ``/embed/`` is
│   │     in the auth middleware's ``PUBLIC_PREFIXES`` allowlist
│   │     so unauthenticated iframes resolve without a redirect.
│   │
│   ├── Phase 101 — Agent-co-authored cells + Reviewer-per-cell   ✅ done 2026-05-22
│   │     Per-cell attribution backbone (Phase 101) shipped 2026-05-20:
│   │     new ``NotebookCellAuthorship`` ORM + migration
│   │     ``805d36938963``, 1:1 with :class:`NotebookCellIdentity`.
│   │     Tracks ``first_author_*`` (user email or ``agents.id`` +
│   │     ``agent_run_id``) and ``last_modifier_*`` separately so the
│   │     header chip can render "minted by agent A • last edited by
│   │     user B".  Service in
│   │     ``services/notebook/cell_authorship.py``;
│   │     :func:`upsert_cell_authorship` is the save-path /
│   │     proposal-acceptance hook.  REST: ``GET
│   │     /api/notebooks/cell/attribution?cell_uuid=…`` +
│   │     ``GET /api/agents/{id}/authored-cells``.  13 new pytest.
│   │     Asset 0.1.0rc36.
│   │
│   │     Save-path wiring landed 2026-05-20 (asset 0.1.0rc42):
│   │     ``api/notebooks_routes/io.py``'s save handler now calls
│   │     ``upsert_cell_authorship`` for every reconciled cell with
│   │     the saver's email as ``first_author``/``last_modifier``.
│   │     Cells start filling the table from the next save.
│   │
│   │     **Wave-B UI 2026-05-20:** cell-header chip shipped
│   │     (asset 0.1.0rc48).  Each cell shows a small person/robot
│   │     chip between the dirty-dot and the tag-picker with the
│   │     saver's email local-part and the full attribution
│   │     envelope (created / last-modified) on hover.  Nested-
│   │     x-data trap dodged by exposing the methods on the outer
│   │     notebook scope via a new ``installCellAuthorship`` mixin
│   │     (DOM-walk-free).  New bulk endpoint
│   │     ``GET /api/notebooks/attribution/bulk?path=…`` returns
│   │     ``{cell_uuid: envelope}`` so a 50-cell notebook costs one
│   │     HTTP request instead of 50; 2 new pytest (15 total).
│   │
│   │     **AI-acceptance hook landed 2026-05-20 (asset 0.1.0rc52):**
│   │     ``upsert_cell_authorship`` relaxed to accept ``kind="agent"``
│   │     with ``agent_id=None`` when ``agent_run_id`` is set;
│   │     ``_write_proposal_provenance`` in ``io.py`` now upserts
│   │     agent authorship before the user-authorship loop runs.  A
│   │     proposal-accepted cell now reads "minted by AI assistant •
│   │     last edit by <saver>" on the chip.  One new pytest (16
│   │     total).
│   │
│   │     **Reviewer-per-cell flow closed 2026-05-22 (asset 0.1.0rc84):**
│   │     The polymorphic ``POST /api/social/{kind}/{ref}/comments``
│   │     handler now honours ``?as_agent=<slug>`` for every entity
│   │     kind (was Phase-76.5 DP-only).  Cell-level review decisions
│   │     authored via the new ``pql_review_cell`` plugin tool carry
│   │     the Phase 76.5 presentation envelope into the row — the
│   │     review badge in the cell thread renders "decision by agent
│   │     X on behalf of <principal>" with the existing principal-or-
│   │     admin gate intact.  ``pql_review_cell`` self-gates on
│   │     ``POINTLESSQL_NOTEBOOK_ID`` (the editor-chat env-var seam
│   │     wired in Phase 105.6), so SQL chat sessions never see it.
│   │     The decision is prepended as a deterministic prefix line
│   │     (``review-decision: approved`` / ``changes-requested`` /
│   │     ``commented``) that the Wave-D ``cellThread`` renderer
│   │     already extracts back into the badge.  3 new PointlesSQL
│   │     pytest + 7 new plugin pytest; no UI change needed.
│   │
│   ├── Phase 102 — Branch-aware notebooks                        ✅ done 2026-05-22
│   │     Backend shipped 2026-05-20.  New
│   │     ``notebook_branch_bindings`` table + migration
│   │     ``095e6a40fa0e`` records which Delta-branch a notebook
│   │     writes to (or ``None`` for ``main``).  Lifecycle columns
│   │     (``created_at`` / ``promoted_at`` / ``discarded_at`` /
│   │     ``superseded_at``) keep history while keeping at most one
│   │     "current" binding per notebook — every fresh bind /
│   │     promote / discard supersedes the prior row.
│   │     Service ``services/notebook/branch_bindings.py``:
│   │     ``bind_branch`` / ``get_current_binding`` /
│   │     ``promote_binding`` / ``discard_binding`` /
│   │     ``list_bindings``.  REST: ``GET|POST|DELETE
│   │     /api/notebooks/branch``, ``POST
│   │     /api/notebooks/branch/promote``, ``GET
│   │     /api/notebooks/branch/history``.  11 new pytest.
│   │     Asset 0.1.0rc39.
│   │
│   │     **Wave-C UI 2026-05-20 (asset 0.1.0rc56):** Toolbar
│   │     "Branch" button opens an inline binding panel with
│   │     three states (none / pending / promoted), a bind form
│   │     (branch_name + optional base_revision_uuid), promote +
│   │     discard actions, and an expandable history list.  Wires
│   │     the existing REST surface; no backend change needed.
│   │
│   │     **Track-H promote-reviewer webhook landed 2026-05-22
│   │     (asset 0.1.0rc85):** ``promote_binding`` now POSTs the
│   │     intent to ``POINTLESSQL_BRANCH_PROMOTE_WEBHOOK_URL``
│   │     before flipping the lifecycle row — HTTP 2xx approves,
│   │     4xx denies (the ``ValidationError`` carries the reviewer's
│   │     body so the UI can surface the reason), and any transport
│   │     failure denies-by-default so the gate stays closed.  When
│   │     ``POINTLESSQL_BRANCH_PROMOTE_WEBHOOK_SECRET`` is also set
│   │     the request carries a GitHub/Stripe-shape
│   │     ``X-PointlesSQL-Signature: sha256=<hex>`` over the raw
│   │     JSON body so shoreguard (or any standard verifier) can
│   │     validate the intake without bespoke code.  Payload now
│   │     includes ``base_revision_uuid`` + ``promoted_by_user_email``
│   │     + ``promote_intent_at`` ISO timestamp so the reviewer can
│   │     resolve the exact diff and contact the requester without
│   │     joining back to PointlesSQL.  5 new pytest cover the
│   │     unset-skip path, happy-path-with-HMAC, signature-omitted-
│   │     when-secret-unset, denial-blocks-promote, and
│   │     network-failure-denies-by-default.  Shoreguard adapter
│   │     remains config-only — point the env var at shoreguard's
│   │     approval intake.
│   │
│   │     **Track-I env-bridge audit + tests landed 2026-05-22
│   │     (asset 0.1.0rc86):** the env-bridge had actually been
│   │     wired throughout Wave-D (``pql.read_table`` /
│   │     ``pql.write_table`` already call ``PQL._branch_remap``,
│   │     which consults ``current_branch()`` from
│   │     ``pointlessql.pql.context``; ``KernelSession.start()``
│   │     injects ``POINTLESSQL_BRANCH`` into the subprocess env;
│   │     ``KernelRegistry.get_or_start`` accepts and forwards
│   │     ``branch_name``).  What was missing was test coverage
│   │     proving the chain end-to-end.  Closed with 9 new pytest:
│   │     ``TestPQLBranchRemap`` in ``test_pql.py`` covers the
│   │     routing layer (no-branch passthrough, schema rewrite,
│   │     two-part-name passthrough, env-var-seeds-context-at-
│   │     import, mid-session ``_set_context`` updates routing on
│   │     next call) and ``test_kernel_session_branch_env.py``
│   │     covers the kernel start-path (env var forwarded; absent
│   │     when ``branch_name=None`` so context falls back; works
│   │     without a notebook id for replay-mode spawns; registry
│   │     propagates the value end-to-end).  Closes Phase 102.
│   │
│   ├── Phase 103 — Replay / Scenario-mode                        ✅ done 2026-05-21
│   │     Backend shipped 2026-05-20.  New ``notebook_replays``
│   │     table + migration ``311c87f25421`` records one row per
│   │     replay attempt of a Phase-97 :class:`NotebookRevision`.
│   │     Lifecycle column ``status`` ∈ ``{pending, running, ok,
│   │     error, cancelled}``; outputs land in ``outputs_json``
│   │     and a digest of ``{stable, changed, missing, new}`` cell
│   │     counts lives in ``diff_summary_json`` for the list page.
│   │     Optional ``branch_name`` routes writes to a Phase-102
│   │     branch so the replay does not corrupt production.
│   │     Service ``services/notebook/replay.py`` (``start_replay``,
│   │     ``mark_running``, ``record_finished``, ``get_replay``,
│   │     ``list_replays``, ``compute_replay_diff``).  REST:
│   │     ``POST /api/notebooks/replay``,
│   │     ``POST .../replay/{uuid}/finish``,
│   │     ``GET .../replay/{uuid}``,
│   │     ``GET .../replay/{uuid}/diff``,
│   │     ``GET /api/notebooks/replays``.  8 new pytest.
│   │     Asset 0.1.0rc40.
│   │
│   │     **Wave-C UI 2026-05-20 (asset 0.1.0rc56):** Toolbar
│   │     "Replays" button opens an inline list with status pill
│   │     + base-revision UUID + branch + per-row diff expand
│   │     (lazy GETs ``/api/notebooks/replay/{uuid}/diff``).  A
│   │     "Start replay" form lets the user mint a fresh ``pending``
│   │     row; the kernel re-execution worker stays deferred so
│   │     the row just sits until that lands.
│   │
│   │     **Wave-D-5 closure 2026-05-21:** kernel-driven re-execution
│   │     worker landed as ``services/notebook/replay_worker.py``
│   │     (commit ``b9d67d8``).  ``ReplayWorker`` is a small async
│   │     loop wired into the FastAPI lifespan next to the scheduler;
│   │     each tick picks at most one ``pending`` row, marks it
│   │     ``running``, spins up a fresh ``AsyncKernelManager``,
│   │     re-runs every code/sql cell from the pinned revision under
│   │     ``POINTLESSQL_BRANCH`` (when bound) +
│   │     ``POINTLESSQL_PRINCIPAL``, captures stream / display /
│   │     execute_result / error frames in the Phase-96 output shape,
│   │     and writes them via ``record_finished``.  Short-circuits on
│   │     the first cell error so the diff surface immediately shows
│   │     the failure cause.  Disabled in fast-test lifespan and
│   │     opt-out via ``POINTLESSQL_REPLAY_WORKER_DISABLED=1`` for
│   │     CI installs that never replay.  10 pytest cover the lifecycle.
│   │
│   ├── Phase 104 — NL→Notebook (full cell-sequence generation)   ✅ done 2026-05-21
│   │     Backend shipped 2026-05-20.  New
│   │     ``notebook_cell_sequence_proposals`` table + migration
│   │     ``d737762ace76``.  One row carries the full proposed
│   │     sequence (``imports → DataFrame → plot → markdown``) as
│   │     ``cells_json`` so insertion is atomic — the user picks
│   │     "Insert all" or "Discard" without ever landing in a
│   │     half-applied state.  Status lifecycle ``pending →
│   │     {accepted, discarded, expired}``; the existing Phase-96
│   │     :class:`NotebookCellProvenance` fans out per-cell
│   │     provenance after acceptance.  Service
│   │     ``services/notebook/cell_sequence_proposals.py``:
│   │     ``propose_sequence`` (validates cell_type ∈
│   │     ``{code, markdown, sql}``, sorts by ``position``),
│   │     ``accept_sequence``, ``discard_sequence``,
│   │     ``get_sequence``, ``list_pending_for_session``.  REST:
│   │     ``POST /api/notebook/chat/{chat_session_id}/propose-sequence``,
│   │     ``GET|accept|discard /api/notebook/chat/sequences/{proposal_id}``,
│   │     ``GET .../sequences/pending``.  10 new pytest.
│   │     Asset 0.1.0rc41.
│   │
│   │     **Wave-C UI 2026-05-20 (asset 0.1.0rc56):** Toolbar
│   │     "Proposals" button opens a passive inbox listening for
│   │     ``pql:cell-sequence-proposed`` window events.  Each
│   │     pending proposal shows prompt + rationale + cell preview
│   │     + Accept-all / Discard.  Accept iterates the cells via
│   │     ``insertCellFromProposal`` then POSTs the accept route;
│   │     Discard hits the discard route.  Inbox auto-opens the
│   │     first time a proposal arrives so the user doesn't miss
│   │     it.
│   │
│   │     **Wave-D-6 closure 2026-05-21:** hermes-plugin
│   │     ``pql_propose_cell_sequence`` LLM tool shipped (plugin
│   │     commit ``0147d29``).  Registered under
│   │     ``POINTLESSQL_NOTEBOOK_CHAT_SESSION_ID`` like the other
│   │     three cell tools; validates each cell entry's
│   │     ``{cell_type, source, position}`` shape locally so a
│   │     drifting LLM gets a 422 with an example instead of a
│   │     server 500, then POSTs the ``{prompt, cells, rationale}``
│   │     payload to ``/api/notebook/chat/{nb}/propose-sequence``.
│   │     The Wave-C inbox listens for ``pql:cell-sequence-proposed``
│   │     and renders Accept-all / Discard for the human; on Accept
│   │     the editor iterates ``insertCellFromProposal`` for every
│   │     ordered cell then POSTs the accept route, fanning out
│   │     per-cell Phase-96 provenance.  5 new plugin pytest cover
│   │     gating, schema rejection, empty-cells, bad cell_type, and
│   │     the happy-path URL + headers shape.
│   │
│   └── Phase 105 — Real-time co-edit                              ✅ done 2026-05-21
│   │
│   │     **Closed 2026-05-21.** Full track shipped in one session: 105.1 (CRDT sidecar storage) + 105.2 (WS hub) + 105.3 (passive Y.Doc client + live pill) + 105.4 (awareness + peer rail) + 105.5 (save-path barrier) + 105.3b (per-cell y-codemirror.next binding) + 105.6 (agent-presence RES...
│   │
│   │     Sub-sprint detail: [`docs/internal/phase-105.md`](docs/internal/phase-105.md).
│   │
│   └── Phase 106 — Hygiene-Wave nach Phase 95–105            ✅ done 2026-05-21
│         **Closed 2026-05-21.**  Post-notebook-blitz code-quality
│         pass.  Two commits, no behaviour change, no asset bump.
│         - **106.1 (pydoclint clean).** Migrated the last 30 route
│           docstrings off the legacy ``HTTPException`` Raises-section
│           onto the actual domain-exception hierarchy
│           (``ResourceNotFoundError`` / ``ValidationError`` /
│           ``ConflictError`` / ``PermissionDeniedError``) — the
│           global handler at ``pointlessql/api/error_handlers.py``
│           already mapped these to RFC-9457 Problem+JSON; only the
│           docstrings lagged.  Removed three stale Raises sections
│           whose bodies no longer raised; added 4 missing
│           ``Args:`` blocks.  pydoclint 30 → 0.
│         - **106.2 (pyright 0 errors).**  Pre-init ``verb`` outside
│           the try-block in ``social_routes/issues.py`` so the
│           except-clause logger has a bound name even on import
│           failure.  Two ``pyright: ignore`` with why-comments for
│           the ``jupyter_client`` stub gaps in ``replay_worker.py``.
│           Excluded ``pointlessql/data/notebook_templates/`` from
│           Pyright in ``pyproject.toml`` — templates are
│           intentionally incomplete plain-Python snippets resolved
│           at kernel-runtime, not library code.  Pyright 10 → 0.
│         - **106.3 (models/notebook.py split).**  Phase 95–105
│           stacked 18 ORM classes into a single 1343-LOC file.
│           Split into per-phase subpackage with re-exports in
│           ``__init__.py`` so existing
│           ``from pointlessql.models.notebook import …`` imports
│           stay valid — no compat shim (Memory
│           ``feedback_no_legacy_shim``).  ``alembic check``
│           confirms schema unchanged.  Files: ``_core`` (Notebook +
│           cells) / ``_provenance`` (96) / ``_revisions`` (97) /
│           ``_tags`` (98.B) / ``_share`` (99/100) / ``_authorship``
│           (101) / ``_branch`` (102) / ``_replays`` (103) /
│           ``_proposals`` (104) / ``_coedit`` (105).
│         - **106.5 (typed proposal bodies, 2026-05-22 asset
│           0.1.0rc87).**  The four chat-proposal routes
│           (notebook-chat ``propose`` / ``fix`` / ``explain`` +
│           sql-chat ``propose``) parsed JSON bodies as
│           ``dict[str, Any]`` and reached for fields via
│           ``body.get(...)`` with hand-rolled isinstance guards
│           — a typo on the agent side (``rationael`` for
│           ``rationale``) would silently drop the value and
│           persist a half-filled proposal row.  Replaced with
│           Pydantic ``BaseModel``s (``ProposeCellBody`` /
│           ``FixCellBody`` / ``ExplainCellBody`` /
│           ``ProposeSqlBody`` with a ``sql_text`` alias model-
│           validator so legacy plugin clients still work).
│           Body-validation errors now surface as 422 via the
│           existing ``RequestValidationError`` handler; the old
│           400-raising guard layer dropped.  7 new pytest cover
│           the typo class.  Lineage inbound facets stay
│           ``dict[str, Any]`` (OpenLineage 2.x vendor-extension
│           forward-compat; explicit parser comment); admin
│           console has no mutation routes to tighten.
│         - **Deferred sub-phases (tracked).**  106.4 (PQL mixin
│           extraction) — 24 methods all need ``self._client``;
│           ``PQL`` is already a thin parameter-forwarding facade
│           to ``_vector.py`` / ``_merge.py`` / etc., so a Mixin
│           would shuffle 74 LOC without reducing the
│           ``self._client`` coupling.  106.6 (missing module
│           docstrings) collapsed to no-op for content but a
│           ruff-baseline hygiene amendment landed 2026-05-22 —
│           two stray ``logger = getLogger(__name__)`` placements
│           left by the 106.1 sweep tripped E402, plus three
│           E501s and a per-file-ignore for
│           ``pointlessql/data/notebook_templates`` (jupytext
│           starter snippets reference kernel-runtime variables
│           the user fills in via ``%sql -o`` magics in earlier
│           cells); ``uv run ruff check pointlessql/`` 28 errors
│           → 0.  106.7 (lifespan-loops reorg) deferred until a
│           concrete new init step demands it — current 33-step
│           complexity is structural, not a smell.
│
│   ├── Phase 121 — Code Quality Wave VI (error-envelope unification)  ✅ done 2026-05-24
│   │
│   │     **All 12 sub-sprints closed 2026-05-24.** Three-axis quality pass after the Restschuld I–V modularization waves drained the >700-LOC backlog. Plan-source: ``/home/flo/.claude/plans/ich- denke-es-ist-squishy-pnueli.md``. Wave ran in three batches: 121.1 (error envelope) shipped fi...
│   │
│   │     Sub-sprint detail: [`docs/internal/phase-121.md`](docs/internal/phase-121.md).
│   │
│   ├── Phase 122 — Source-Code Sanitization for Publication        ✅ done 2026-05-24
│   │     **Closed LOCAL 2026-05-24.**  Four-sprint wave that strips
│   │     project-management references (Phase / Sprint / Wave-X /
│   │     BUG-NN-NN) from source comments + docstrings + e2e
│   │     walkthroughs + README in preparation for the in-aspect public
│   │     release of the stack.  ROADMAP, CHANGELOG, alembic migrations,
│   │     and git history are explicitly kept as historical record —
│   │     they ARE the phase artefact.
│   │
│   │     Goal: source comments + docstrings stop reading as
│   │     "cryptic insider language" for outside contributors.  A
│   │     "Phase 99 Wave-D tightened the save gate" comment carries
│   │     zero value for someone with no ROADMAP mapping in their
│   │     head and signals "private hobby repo".
│   │
│   │     - **122.1 — Mechanical regex sweep.**  ✅ done 2026-05-24.
│   │       Per-pattern strip across ``pointlessql/`` + ``tests/`` +
│   │       ``frontend/`` + ``e2e/`` + ``notebooks/``:
│   │       parenthetical ``(Phase X)``, line-start comment prefixes
│   │       (``# Phase X — `` / ``// Phase X — `` / ``<!-- Phase X — `` /
│   │       ``/* Phase X — `` / ``{# Phase X — ``), docstring openers,
│   │       JSDoc body lines, multi-line block-comment openers,
│   │       inline ``BUG-NN-NN`` markers, ``Sprint X`` / ``Wave-X``
│   │       standalone tokens.  Source-tree Phase hits: 1622 → 855
│   │       (−47%); Sprint: 362 → 194; Wave: 52 → 11; BUG: 21 → 7.
│   │       Commit ``69c33fe``, asset rc138 → rc139.
│   │     - **122.2 — Manual woven cleanup + test renames.**  ✅ done
│   │       2026-05-24.  Strips the woven-into-prose references that
│   │       122.1's regex couldn't touch (temporal prefixes ``in/since/
│   │       from/to/for/per Phase X``, possessive ``Phase X's noun``,
│   │       cross-ref ``see Phase X``, modifier ``the Phase X feature``,
│   │       sentence-start subject drops).  Plus ``git mv`` renames
│   │       for 11 phase-keyed test + notebook filenames (e.g.
│   │       ``test_phase158_lineage_wiring.py`` →
│   │       ``test_lineage_wiring_contract.py``) and 11 test/helper
│   │       function-name renames.  20 manual long-line rewrites for
│   │       sentences the strip broke grammatically.  Phase hits:
│   │       855 → 260 (−70%; 88% overall vs pre-wave).  Commit
│   │       ``5ca77eb0``, asset rc139 → rc140.
│   │     - **122.3 — e2e-walkthroughs feature-rename + content-clean.**
│   │       ✅ done 2026-05-24.  Renamed
│   │       ``sprint_13_11_reflexive-tools.md`` → ``reflexive-tools.md``;
│   │       cross-references in ``mkdocs.yml`` / ``docs/guides/`` /
│   │       walkthrough README updated.  Dropped the ``| Phase |``
│   │       column from the 4 walkthrough-mode tables in the README.
│   │       Bulk-strip patterns applied to all 65 walkthrough markdowns:
│   │       parenthetical phase suffixes, sentence-internal temporals,
│   │       ``BUGs — Phase 69 replay`` headers, modifier drops.
│   │       ~190 substitutions; remaining ~50 unique sentence-internal
│   │       references are the long tail.  Commit ``ee4f0777``, asset
│   │       rc140 → rc141.
│   │     - **122.4 — README outside-reader polish + CLAUDE.md forward
│   │       guard.**  ✅ done 2026-05-24.  Rewrote ``## Status`` section
│   │       of ``README.md`` from "Phase 21 closed" to a feature-
│   │       focused capability list; stripped 3 phase refs in the
│   │       "Why" block; collapsed "Sprint 63 retired JupyterLab"
│   │       footnote.  New ``CLAUDE.md`` convention block under
│   │       ``## Conventions``: *Source comments + docstrings MUST NOT
│   │       reference Phase / Sprint / Wave numbers or BUG-NN-NN
│   │       markers.*  Exception explicitly documented for
│   │       ``pointlessql/alembic/versions/*.py`` (the migration IS
│   │       the schema-change identity).  Commit ``b3566ea7``, asset
│   │       rc141 → rc142.
│   │
│   │     Final counts: Phase 1622 → 260 (84% reduction; 173 non-alembic);
│   │     Sprint 362 → 72 (80%); Wave 52 → 6 (88%); BUG 21 → 7 (67%).
│   │     Long-tail of ~250 non-alembic hits is unique sentence-
│   │     internal prose that survives as feature context; further
│   │     reduction would need bespoke per-site rewrite.
│   │
│   │     Verification: full pytest 3529 passed / 0 failed; ruff
│   │     check 0 errors; pyright + pydoclint unchanged.
│   │
│   ├── Phase 123 — Frontend Master-Plan (8-wave modernisation)    ✅ done 2026-05-25
│   │
│   │     **All 8 waves closed 2026-05-25.** Largest single-domain wave the project has run: every HTML template, JS module and CSS file in ``frontend/`` was touched. Asset trajectory ``rc138 → rc173`` across ~35 commits. Plan- source: ``~/.claude/plans/ich-m-chte-dass-du-joyful- seal.md``...
│   │
│   │     Sub-sprint detail: [`docs/internal/phase-123.md`](docs/internal/phase-123.md).
│   │
│   ├── Phase 120 — API-key ACLs + usage dashboard               ✅ done 2026-05-23
│   │     **Closed 2026-05-23.**  Seven sub-phases bundled in one
│   │     session, asset 0.1.0rc124 → rc125.  Final wave of the
│   │     three-phase API-key upgrade (118+119+120).  Adds the
│   │     coarse-pre-filter layer below UC SELECT grants: per-key
│   │     catalog/schema allowlist + per-key IP allowlist + 30-day
│   │     usage dashboard.  Every existing key keeps unchanged
│   │     behaviour (zero rows = unrestricted, same as pre-120).
│   │     - **120.1 — Schema.**  Alembic migration
│   │       ``f7h9j1k3l5n7`` adds three tables: ``api_key_catalog_grants``
│   │       (composite unique on ``api_key_id+catalog_name+schema_name``;
│   │       ``schema_name=NULL`` is wildcard), ``api_key_ip_grants``
│   │       (composite unique on ``api_key_id+cidr``),
│   │       ``api_key_usage_buckets`` (composite unique on
│   │       ``api_key_id+bucket_minute+source_ip`` for UPSERT
│   │       efficiency).  All FK to ``api_keys.id`` with
│   │       ``ondelete='CASCADE'``.
│   │     - **120.2 — Pure-function checks.**
│   │       ``services/api_keys/_acl.py`` with
│   │       ``check_catalog_allowed(grants, sql, *, default_catalog,
│   │       default_schema)`` (walks the sqlglot AST via
│   │       ``parse_one + find_all(exp.Table)`` — same pattern as
│   │       Phase 117's ``qualify_sql``) and
│   │       ``check_ip_allowed(grants, source_ip)`` (CIDR matching
│   │       via the stdlib ``ipaddress`` module, IPv4 + IPv6
│   │       support, fails-closed when source_ip is None and grants
│   │       are non-empty).  ``validate_cidr`` canonicalises +
│   │       rejects garbage at insert time.
│   │     - **120.3 — Route wiring.**  IP gate in
│   │       ``auth_middleware`` runs immediately after
│   │       ``verify_bearer`` — denied requests get 403 +
│   │       ``IP_NOT_ALLOWED`` + ``api_key.access_denied.ip``
│   │       audit row, never reaching the route.  Catalog gate in
│   │       ``external_sql_routes`` runs after parse + qualify —
│   │       denied requests get the DBX-shape FAILED envelope with
│   │       ``PERMISSION_DENIED`` + ``api_key.access_denied.catalog``
│   │       audit.  Both gated on ``api_key_acl.enforce_*`` config
│   │       flags so operators can switch off either side during
│   │       incident response without a redeploy.
│   │     - **120.4 — Grants CRUD.**  Five endpoints under
│   │       ``/api/admin/api-keys/{name}/grants[…]``: list
│   │       (catalog + ip combined), add catalog, delete catalog,
│   │       add ip, delete ip.  Each mutation audits with the
│   │       relevant detail.  Duplicate inserts translate the unique
│   │       constraint violation to 422.
│   │     - **120.5 — Usage tracking.**  New
│   │       ``services/api_keys/_usage.py`` with ``record_use`` (hot
│   │       path enqueues into in-process ``Counter`` on
│   │       ``app.state``), ``flush_buffer`` (drain → INSERT-or-update
│   │       per ``(key, minute, ip)`` tuple),
│   │       ``cleanup_stale_usage`` (retention sweep),
│   │       ``get_usage_summary`` (30-day daily aggregate +
│   │       top-10 source IPs).  Two new lifespan loops
│   │       (``_api_key_usage_flush_loop`` 30s,
│   │       ``_api_key_usage_retention_loop`` daily).
│   │       ``GET /api/admin/api-keys/{name}/usage`` returns the
│   │       JSON shape for tooling.
│   │     - **120.6 — Detail page.**  ``GET /admin/api-keys/{name}``
│   │       renders ``admin_api_key_detail.html``: metadata card +
│   │       30-day bar chart (drawn via plain
│   │       ``<canvas>`` 2D context — no Chart.js dependency for
│   │       a single 60-line histogram) + top-source-IPs table +
│   │       grants editor (add/list/delete for both grant types).
│   │       List page row gets a "Manage" link.
│   │     - **120.7 — Doc + asset.**  New walkthrough
│   │       ``docs/admin/api-key-acls.md`` covering catalog +
│   │       IP allowlists, usage dashboard, settings reference,
│   │       layered enforcement model (IP → catalog → UC), audit
│   │       event catalogue, known limitations.  Asset rc124 →
│   │       rc125.
│   │
│   │     **Verification.**  56 new pytest across 4 files (20
│   │     pure-function ACL + 6 route-gate + 9 grants CRUD + 10
│   │     usage + 11 lifecycle gates from 119 still passing in
│   │     this surface).  156 api-key + admin + external-sql tests
│   │     pass.  Ruff + pyright + pydoclint clean across the new
│   │     code surface.
│   │
│   ├── Phase 119 — API-key lifecycle (TTL+rotation+quarantine) ✅ done 2026-05-23
│   │     **Closed 2026-05-23.**  Six sub-phases bundled in one
│   │     session, asset 0.1.0rc123 → rc124.  Adds the three
│   │     operational primitives that turn the Phase-118 token format
│   │     into a credentials story you can run incident-response on:
│   │     TTL with 14-day warning, rotation with 24h grace window,
│   │     soft quarantine that's reversible.  Every existing key
│   │     keeps unchanged behaviour — all seven new columns default
│   │     NULL = "no constraint", and admins opt in per key.
│   │     - **119.1 — Schema.**  Alembic migration
│   │       ``e5g7h9j1k3l5`` adds 7 nullable columns to ``api_keys``:
│   │       ``expires_at``, ``rotated_from_id`` (self-FK,
│   │       ``ondelete='SET NULL'``), ``rotated_at``, ``grace_until``,
│   │       ``quarantined_at``, ``quarantine_reason`` (max 200),
│   │       ``expiry_warned_at`` (dedup marker).
│   │     - **119.2 — verify_bearer gates.**  Quarantine check, expiry
│   │       check, post-grace rotation check — each rejection emits a
│   │       distinct ``api_key.auth_denied.*`` audit row (audit
│   │       failures swallowed so a broken audit table can never
│   │       break auth).  Helper ``_as_aware_utc`` normalises naive
│   │       SQLite TZ reads to UTC-aware so comparisons work on both
│   │       dialects without branching.
│   │     - **119.3 — Admin endpoints.**  ``POST …/rotate`` (mints
│   │       successor, sets predecessor grace), ``POST …/quarantine``
│   │       (soft-disable + reason), ``POST …/unquarantine``,
│   │       ``PATCH …`` (update ``expires_at``).  Service-layer
│   │       additions ``rotate_api_key`` / ``quarantine_api_key`` /
│   │       ``unquarantine_api_key`` / ``update_api_key_ttl`` —
│   │       each calls ``invalidate_cache()`` so user-visible
│   │       latency is ~0 in the single-worker case.
│   │     - **119.4 — Sweep + lifespan.**  New
│   │       ``services/api_keys/_lifecycle_sweep.py`` with
│   │       ``run_lifecycle_sweep`` — per tick auto-quarantines
│   │       expired keys (or audit-only if flag off) + emits one
│   │       ``api_key.expiry_warning`` per key entering the window.
│   │       ``update_api_key_ttl`` clears ``expiry_warned_at`` so a
│   │       TTL bump re-arms the warning naturally.  Wired as
│   │       ``_api_key_lifecycle_sweep_loop`` next to the
│   │       audit-retention loop in lifespan.  New
│   │       ``ApiKeyLifecycleSettings`` group (env prefix
│   │       ``POINTLESSQL_API_KEY_LIFECYCLE_``) with 5 tunables.
│   │     - **119.5 — Admin HTML.**  Status column gains four new
│   │       pills (revoked / quarantined / rotated / expiring /
│   │       active) with tooltip context.  Actions column becomes
│   │       a button-group with Rotate / Quarantine /
│   │       Unquarantine / Revoke; rotate replays through the
│   │       existing "API key created" modal so operators get 24h
│   │       to copy the new secret.  Create modal gains a TTL
│   │       chooser (None / 30d / 90d / 180d / 1 year) — non-zero
│   │       fires a follow-up PATCH to set ``expires_at``.
│   │     - **119.6 — Doc + asset.**  New walkthrough
│   │       ``docs/admin/api-key-lifecycle.md`` covers states,
│   │       rotation playbook, quarantine-vs-revoke decision,
│   │       TTL guidance, sweep behaviour, audit-event catalogue,
│   │       settings reference, known limitations.  Asset
│   │       rc123 → rc124.
│   │
│   │     **Verification.**  19 new pytest across two files (11 in
│   │     test_api_key_lifecycle.py covering gates + sweep + dedup,
│   │     8 in test_admin_api_keys_routes.py covering all four new
│   │     admin endpoints).  Existing 66 api-key tests pass.  Ruff
│   │     + pyright + pydoclint clean across the new surface.
│   │
│   ├── Phase 118 — API-key token format aufwertung             ✅ done 2026-05-23
│   │     **Closed 2026-05-23.**  Five sub-phases bundled in one
│   │     session, asset 0.1.0rc122 → rc123.  Replaces the
│   │     ``secrets.token_urlsafe(32)`` opaque blob with a
│   │     professional Stripe + GitHub PAT v2 style envelope:
│   │     ``pql_{env}_v1_{body40}_{crc8}``.  Two coexisting
│   │     formats — legacy keys never need rotation.
│   │     - **118.1 — Schema.**  Alembic migration
│   │       ``d3e5f7g9b1c4`` adds ``token_format`` + ``token_env``
│   │       VARCHAR(8) columns (server_default ``'legacy'``) and
│   │       widens ``secret_prefix`` from VARCHAR(8) → VARCHAR(32)
│   │       so the 24-char v1 visible prefix fits.
│   │     - **118.2 — Format module.**  Promoted the single-file
│   │       ``services/api_keys.py`` to a package and added
│   │       ``_token_format.py`` with ``generate_v1_token(env)``
│   │       (≥235-bit body entropy), ``parse_v1_token`` (regex +
│   │       CRC32 validation), ``display_prefix_for`` (24-char v1 /
│   │       8-char legacy), and a ``V1_REGEX`` constant shared with
│   │       the GitHub Secret Scanning Partner Program form.
│   │     - **118.3 — Wire create + verify.**  ``create_api_key``
│   │       accepts ``env: Literal["live", "test"] = "live"``;
│   │       ``verify_bearer`` short-circuits v1-shaped tokens with
│   │       a bad CRC before any DB lookup.  Legacy tokens flow
│   │       through unchanged — ``parse_v1_token`` returns ``None``
│   │       and the existing SHA-256 lookup runs.  Env-var
│   │       bootstrap auto-tags rows ``'v1'`` or ``'legacy'`` based
│   │       on the secret it sees.
│   │     - **118.4 — Admin surface.**  POST body accepts ``env``;
│   │       list + create responses include ``token_format`` +
│   │       ``token_env``.  HTML row shows a coloured badge after
│   │       the secret prefix (``live`` green / ``test`` yellow /
│   │       ``legacy`` grey with tooltip).  Create modal gains an
│   │       Environment chooser.
│   │     - **118.5 — Doc + asset.**  New walkthrough
│   │       ``docs/admin/api-key-format.md`` covering format spec,
│   │       CRC validation, why-not-JWT, why-SHA-256, and the
│   │       GitHub Secret Scanning Partner Program registration
│   │       steps.  Asset rc122 → rc123.
│   │
│   │     **Why.**  After Phase 117 shipped the public SQL surface,
│   │     the user inspected the resulting keys and asked whether
│   │     they could look more professional (à la Stripe / GitHub
│   │     / OpenAI / Anthropic).  Phase 118 is the answer: visible
│   │     prefix discriminates env at-a-glance, CRC enables offline
│   │     secret-scanner validation, regex is GitHub-scanning-
│   │     compatible so a leaked v1 key in a public repo can be
│   │     auto-revoked once we register with the partner program.
│   │
│   │     **Verification.**  18 new pytest (12 format module + 4
│   │     gate + 4 admin route).  Existing 57 admin + workspace +
│   │     legacy + page tests unaffected.  Ruff + pyright +
│   │     pydoclint clean across the new code surface.
│   │
│   ├── Phase 117 — External SQL Statement Execution API       ✅ done 2026-05-23
│   │     **Closed 2026-05-23.**  Six sub-phases bundled in one
│   │     session, asset 0.1.0rc120 → rc121.  PointlesSQL's first
│   │     **token-only public REST surface** — a Databricks-compat
│   │     SQL Statement Execution API at
│   │     ``/api/2.0/sql/statements`` that lets external clients
│   │     (curl, dbt, BI, application backends) run SELECT queries
│   │     against the lakehouse without driving the browser UI.
│   │     Wire shape mirrors the documented DBX schema so the
│   │     official ``databricks-sql-python`` adapter + dbt-databricks
│   │     runner can swap base URLs.  v1 SELECT-only; DML / DDL
│   │     ships separately (needs approval-flow integration).
│   │     - **117.1 — DB schema + scope.**  New
│   │       ``api_keys.sql_execute`` boolean column (Alembic
│   │       migration ``c2d4e6f8a0b2``).  New ``sql_statements``
│   │       table storing per-submission lifecycle (PENDING →
│   │       RUNNING → SUCCEEDED / FAILED / CANCELED) + gzipped DBX
│   │       envelope payload for polling clients.  New
│   │       ``require_sql_execute`` FastAPI dependency that rejects
│   │       cookie-only callers — this surface is for external
│   │       integrations, not in-browser humans.  KeyEntry
│   │       extended with the new scope flag + the key id (needed
│   │       for per-key rate limiting); ``parse_keys`` /
│   │       ``bootstrap_from_env`` learned the new
│   │       ``name:secret:sql_execute`` env-var form.
│   │     - **117.2 — Route + executor.**  New router
│   │       ``external_sql_routes.py`` with four endpoints (POST
│   │       submit, GET poll, GET chunk, POST cancel).  New service
│   │       package ``services/sql_statements/`` with the executor
│   │       coroutine + in-process task registry so cancel can both
│   │       ``task.cancel()`` and call ``conn.interrupt()`` on the
│   │       DuckDB handle.  Wraps the existing
│   │       ``enforce_select_per_table`` + ``run_sql_sync`` pipeline
│   │       — soyuz UC SELECT grants apply uniformly across the
│   │       editor and the public surface.
│   │     - **117.3 — Poll + cancel + retention.**  GET endpoints
│   │       gunzip the stored envelope; POST cancel sets the
│   │       persistent ``cancel_requested`` flag and best-effort
│   │       interrupts the live DuckDB conn.  Retention sweeper
│   │       ``cleanup_stale_statements`` registers a
│   │       ``sql_statements_retention`` scheduler executor for
│   │       periodic pruning (default 24h).
│   │     - **117.4 — Qualify + parameter binding.**  Default
│   │       ``catalog``/``schema`` body fields drive a sqlglot AST
│   │       rewrite that fills in 1- and 2-part table refs before
│   │       the existing 3-part-strict parser sees them.  Typed
│   │       ``:name`` parameter binding (STRING / INT / LONG /
│   │       DOUBLE / FLOAT / BOOLEAN / DATE / TIMESTAMP / NULL) via
│   │       sqlglot literal substitution — injection-safe by
│   │       construction.  ``format=ARROW_STREAM`` /
│   │       ``disposition=EXTERNAL_LINKS`` rejected with 400 +
│   │       ``INVALID_PARAMETER_VALUE`` (deferred to v2).
│   │     - **117.5 — Rate limit + feature flag.**  Per-API-key-id
│   │       fixed-window bucket via the existing rate-limit DB
│   │       table (no new infra dep).  Defaults 60/min/key, tunable
│   │       via ``POINTLESSQL_RATE_LIMIT_SQL_STATEMENTS_APIKEY_*``.
│   │       Exceeded → 429 with DBX-shape
│   │       ``REQUEST_LIMIT_EXCEEDED`` + ``Retry-After`` header.
│   │       New ``SqlExecutionApiSettings`` group with
│   │       ``enabled=False`` kill-switch (503 +
│   │       ``WORKSPACE_TEMPORARILY_UNAVAILABLE``) for incident
│   │       response.
│   │     - **117.6 — Docs + asset bump.**  New walkthrough
│   │       ``docs/e2e-walkthroughs/external-sql-api.md`` covering
│   │       sync / async / cancel / parameter / default-catalog /
│   │       failure paths.  Asset rc120 → rc121.
│   │
│   │     **Custom error envelope.**  The global FastAPI handler
│   │     stringifies ``HTTPException.detail``, which would mangle
│   │     the DBX JSON shape.  Routes raise a private
│   │     ``_DbxApiError`` short-circuit exception that a per-route
│   │     ``_wrap_dbx`` decorator catches and ships as
│   │     ``JSONResponse({"detail": body})`` with the headers
│   │     preserved.  Failure envelopes (parse / permission /
│   │     non-SELECT) land at HTTP 200 with
│   │     ``status.state="FAILED"`` to match DBX exactly; only body
│   │     validation / auth / rate-limit / disabled go via HTTP
│   │     status codes.
│   │
│   │     **Verification.**  39 new pytest across 4 files (envelope
│   │     mapping + type translation, default-catalog qualify,
│   │     parameter binding incl. injection round-trip, full route
│   │     lifecycle incl. cancel + rate-limit + 503).  Ruff +
│   │     pyright + pydoclint clean.  Hand-curl smoke via the
│   │     walkthrough playbook covers the DBX-shape happy path.
│   │     ``databricks-sql-python`` client end-to-end verification
│   │     deferred (tracked).
│   │
│   ├── Phase 116 — Notebook editor toolbar redesign            ✅ done 2026-05-23
│   │     **Closed 2026-05-23.**  Single sprint, commit
│   │     ``12fa00c``, pushed to origin/main.  Asset 0.1.0rc119 →
│   │     rc120.  Replaces decorative dot-trio with stateful pill
│   │     chips, makes Save / Run-all carry their own state, and
│   │     strengthens panel-toggle ``.active`` to match the audit
│   │     active-link treatment.  Design principle:
│   │     **"status lives on the action"** — each piece of state has
│   │     a natural home on its action button (Save state on Save
│   │     button, Run state on Run-all); the cluster is the
│   │     at-a-glance backup when the action is scrolled out of
│   │     view.  Vital-pills v2: 3 rounded 1.6×1.25rem chips
│   │     (``pql-vital-pill``) with state-tinted icons (floppy /
│   │     cpu / person / people-fill).  Co-edit pill gains an
│   │     inline peer-count badge.  Meta-panel keeps using the old
│   │     dot-classes so the verbose mirror surface stays
│   │     untouched.  Pattern note: root-scope
│   │     ``vitalPillClass(kind)`` delegates to mixin-defined
│   │     ``this.coeditPillClass()`` for ``kind='coedit'`` — the
│   │     concern split stays intact.
│   │
│   ├── Phase 115 — Cell drag-drop reorder                      ✅ done 2026-05-23
│   │     **Closed 2026-05-23.**  Single sprint, one commit,
│   │     pushed to origin/main.  Asset 0.1.0rc115 → rc116.
│   │     Adds VSCode-style grip-handle drag-drop reorder to
│   │     notebook cells, and incidentally closes a latent
│   │     multi-tab co-edit gap that the existing Move-up/down
│   │     buttons had quietly left open since Phase 105.
│   │     - **Track A — Grip-handle DnD.**  New
│   │       ``installCellDnd(state)`` mixin
│   │       (``frontend/js/notebook/cell_dnd.js``); only the new
│   │       far-left grip button on each cell header is
│   │       ``draggable="true"`` so CodeMirror's native text-
│   │       selection drag inside the editor body keeps working.
│   │       Drop indicator computed from cursor-Y vs row midpoint
│   │       (``above`` / ``below``); rendered via two
│   │       ``pql-notebook-cell--drop-{above,below}`` classes that
│   │       paint an inset 2-px accent shadow — inset (not border)
│   │       to avoid layout jitter between rows during a drag.
│   │       The Move-up / Move-down dropdown items keep working
│   │       unchanged because the underlying primitive was
│   │       refactored from ``_moveCell(cell, delta)`` to
│   │       ``_moveCellTo(fromIdx, toIdx)`` with the old
│   │       signatures preserved as thin wrappers.
│   │     - **Track B — CRDT sync of cells_order.**  Before this
│   │       sprint, ``moveCellUp/Down`` mutated only the local
│   │       Alpine ``this.cells`` array; the Y.Array
│   │       ``cells_order`` was never touched (no observer either
│   │       side, confirmed by ``grep``).  Co-edit peers only
│   │       converged on the next save round-trip.  Now
│   │       ``_moveCellTo`` write-throughs the reorder via
│   │       ``ydoc.transact`` under origin ``pql-local-reorder``;
│   │       a new ``cells_order`` observer (installed in
│   │       ``onSynced``) fires ``_reconcileCellsFromOrder`` on
│   │       remote mutations, which rebuilds the Alpine array
│   │       using ``x-for :key="cell.id"`` stable ordinals so
│   │       CodeMirror mounts are NOT remounted.  Orphan-uuid
│   │       cells (uuid present in ``this.cells`` but not yet in
│   │       ``cells_order``, e.g. when a stale notebook seed
│   │       diverges) are preserved at the tail instead of being
│   │       silently dropped — caught during the multi-tab
│   │       replay below.
│   │
│   │     Gates clean (0 ruff, 0 pyright errors, pydoclint
│   │     clean, alembic no-op — no Python touched).  Playwright-
│   │     MCP replay covered: programmatic ``_moveCellTo`` reorder
│   │     (Alpine + Y.Array stay in sync), synthetic
│   │     dragstart/dragover/drop on grip + target cell (full DnD
│   │     lifecycle + drop-indicator + dragging classes verified),
│   │     ``moveCellUp/Down`` regression via the underlying
│   │     wrapper, and a real two-tab session where tab A's
│   │     reorder propagated to tab B without a save round-trip
│   │     (Y.Array yPos stayed identical 11 across both tabs).
│   │     Surfaced + fixed during replay: the first reconcile
│   │     draft only preserved cells whose uuids were in
│   │     ``cells_order``, which silently dropped 5/12 cells in
│   │     tab B on legacy notebooks where the server seed mixes
│   │     dashless-hex and dashed UUID formats.
│   │
│   ├── Phase 114 — Workspace navigation overhaul              ✅ done 2026-05-23
│   │     **Closed 2026-05-23.**  Three sub-sprints, three
│   │     commits, all pushed to origin/main.  Asset 0.1.0rc112
│   │     → rc115.  Brings the workspace tree to VSCode-Explorer
│   │     parity on both surfaces (sidebar + ``/notebooks/workspace``
│   │     full page) — fixing four concrete defects in one phase.
│   │     - **114.1 (commit ``1ea7220``, asset rc112 → rc113).**
│   │       Sidebar rebuilt from a flat 30-item list into a
│   │       nested folder tree (mirrors the full-page UX in a
│   │       denser column).  Filename filter input at the top,
│   │       ancestor auto-expansion for matches, edit-route
│   │       active highlight (``/notebooks/edit/{path}``) — the
│   │       sidebar finally shows which file is currently open
│   │       in the editor.  New "+ New" button mounts the create-
│   │       notebook modal inside the sidebar's own scope via a
│   │       refactor of ``notebookDialogs()`` from
│   │       ``getElementById`` to scope-local ``$refs.pathInput``
│   │       so the workspace-page modal and the sidebar modal can
│   │       coexist on the same DOM.  Shared CRUD helpers
│   │       extracted into ``notebook_modal_apis.js`` mixin so the
│   │       sidebar and page factory both spread the same
│   │       implementation.  CustomEvent
│   │       ``pql:workspace:tree-changed`` keeps both surfaces in
│   │       sync after any mutation.
│   │     - **114.2 (commit ``3132940``, asset rc113 → rc114).**
│   │       Right-click context menu + keyboard navigation.
│   │       Single shared ``installWorkspaceContextMenu()`` mixin
│   │       wires a floating menu (z-index 1050, above the right
│   │       drawer, below modals) on both factories.  Notebook
│   │       items: Open in editor · Open in new tab · Schedule… ·
│   │       Rename… (F2) · Copy path · Delete… (Del).  Folder
│   │       items: Expand/Collapse · New notebook here · Copy
│   │       path.  Keyboard from the tree body: ↑/↓ move focus,
│   │       →/← expand/collapse folders, Enter opens or toggles,
│   │       F2 renames, Delete deletes, ``/`` focuses the filter
│   │       input, Escape closes.  Menu closes on outside click,
│   │       scroll, window resize, or Escape.
│   │     - **114.3 (commit ``d1415ec``, asset rc114 → rc115).**
│   │       Drag-drop move + inline rename.  New
│   │       ``installWorkspaceDnd()`` mixin spread on both
│   │       factories — reuses ``_renameNotebookApi`` (move =
│   │       rename with a different parent prefix); zero backend
│   │       changes.  Notebook rows draggable (folders not — the
│   │       backend rename helper only handles files); folder
│   │       rows accept drops with an accent-dashed outline; the
│   │       panel root accepts drops too (move to workspace
│   │       root).  Drop guards: same-parent, descendant-of-self,
│   │       non-folder target.  Inline rename via F2 OR double-
│   │       click; Enter commits, Escape cancels, blur commits
│   │       (matches VSCode).  Auto-selects the basename so the
│   │       suffix doesn't need re-typing.
│   │
│   │     Gates clean across all three sprints (0 ruff, 0
│   │     pyright errors, pydoclint clean, alembic clean).
│   │     Playwright-MCP replay confirmed: 0 console errors on
│   │     both ``/notebooks/edit/...`` and
│   │     ``/notebooks/workspace`` paths; the create-modal $refs
│   │     refactor verified by both sidebar and page modals open
│   │     independently without ID-collision side effects.
│   │
│   ├── Phase 113 — Editor surface consolidation                ✅ done 2026-05-22
│   │     **Closed 2026-05-22.**  Three sub-sprints, three
│   │     commits, all pushed to origin/main.  Asset 0.1.0rc96
│   │     → rc99.  Continues the Phase 112.5 toolbar↔meta-panel
│   │     content split pattern ("verbs left, status right,
│   │     rarely-used hidden behind one click") into three
│   │     remaining cluttered editor surfaces: cell-header
│   │     overload, three competing right-edge drawers, two
│   │     near-identical run-job modals.
│   │     - **113.1 (commit ``74b9e6f``, asset rc96 → rc97).**
│   │       Cell-header ⋯-overflow split.  Per-cell Type
│   │       dropdown + History toggle + 5-button Insert / Move /
│   │       Delete cluster collapsed into one Bootstrap
│   │       ``dropdown`` opened by a single ``bi-three-dots``
│   │       button.  Menu sections in order: Cell type / View /
│   │       Structure / Delete / Lineage (only rendered when
│   │       >1 write-op).  Lineage strip capped at 1 visible
│   │       badge + a hover-tooltipped ``+N more`` overflow
│   │       chip; the unfolded tail moves into the menu's Info
│   │       section.  New ``lineageOverflowTitle()`` helper in
│   │       ``frontend/js/notebook/cell_lineage.js`` joins the
│   │       tail with ``\n``.  No new per-cell Alpine scope —
│   │       the single ``<div class="dropdown">`` stays in the
│   │       outer ``notebookEditor()`` scope (avoiding the
│   │       nested-x-data trap captured in
│   │       ``feedback_alpine_root_inside_nested_xdata``).
│   │     - **113.3 (commit ``879feed``, asset rc97 → rc98).**
│   │       Run-job modals merged.  Phase-67.2 Schedule modal +
│   │       Phase-67.3 Run-Once modal folded into one Bootstrap
│   │       modal with a ``nav-pills nav-fill`` tab strip
│   │       (Run now / Schedule).  Shared block: parameter-
│   │       overrides form + submission/error state.  Tab-
│   │       specific blocks: name + cron (Schedule), in-flight
│   │       status badge (Run-now).  One unified ``runModal``
│   │       Alpine state object (``{open, tab, submitting,
│   │       error, parameters, name, cronExpr, status}``)
│   │       replaces nine legacy fields.  ``_pollJobRun`` now
│   │       short-circuits when the modal closes mid-poll
│   │       (closes a latent leak where the polling loop kept
│   │       running after a manual Cancel).  Two legacy partials
│   │       deleted outright per ``feedback_no_legacy_shim``.
│   │     - **113.2 (commit ``f3803f7``, asset rc98 → rc99).**
│   │       Right-drawer unification.  Three competing right-
│   │       edge surfaces (Phase 96 chat drawer ``z=1040``,
│   │       Phase 67.5 variable inspector ``z=1040`` — which
│   │       overlapped chat, Phase 77.6 social drawer as
│   │       Bootstrap offcanvas-end silently ignored by
│   │       ``closeAllPanels()``) collapsed into one
│   │       ``pql-right-drawer`` shell with six tabs: Chat ·
│   │       Variables · Discussion · Endorsements · Followers ·
│   │       README.  One ``rightDrawer: { open, tab }`` Alpine
│   │       state object replaces two booleans + the Bootstrap-
│   │       offcanvas state.  All six tab bodies stay in the
│   │       DOM via ``x-show`` (not ``x-if``) so the chat
│   │       WebSocket subscription survives tab switches.
│   │       Social finally in scope for the "Close all panels"
│   │       button — fixes the silent-omission bug from the
│   │       initial Phase 77.6 wiring.  Legacy
│   │       ``toggleChatPanel()`` / ``toggleInspector()`` kept
│   │       as thin aliases delegating to
│   │       ``openRightDrawer(tab)``.  Three legacy partials
│   │       deleted.
│   │
│   │     **Surprising lesson (113.2).**  The shared social-tab
│   │     partials (``_endorsements_pane.html`` /
│   │     ``_followers_pane.html``) ship as ``tab-pane fade``
│   │     Bootstrap markup *without* the ``show active``
│   │     modifier.  Under Alpine-driven visibility they need a
│   │     CSS override —
│   │     ``.pql-right-drawer__nested-pane > .tab-pane {
│   │     display: block !important; opacity: 1 !important; }``
│   │     — otherwise Bootstrap's CSS would hide them
│   │     unconditionally.  The Discussion + README panes are
│   │     inline so they can take ``:class="{ 'show active': … }"``
│   │     directly and need no override.
│   │
│   │     Gates clean across all three sprints (0 ruff, 0
│   │     pyright errors, pydoclint clean, alembic clean).  414
│   │     notebook-scoped pytest pass; one pre-existing failure
│   │     (``test_save_non_admin_accessible`` returns 403, not
│   │     200) unrelated to Phase 113.  Browser-replay deferred
│   │     — server kill was permission-denied during the closing
│   │     session and the visual replay is on the human user.
│   │
│   ├── Phase 112 — Right meta panel + toolbar/meta-panel split  ✅ done 2026-05-22
│   │     **Closed 2026-05-22.**  Single commit ``1cf29a0``.
│   │     Asset 0.1.0rc92 → rc96.  Reorganises the notebook
│   │     toolbar so verbs (Run all, Save, …) stay always-
│   │     visible while nouns (status, notebook metadata)
│   │     migrate into a right-edge sticky meta panel — CSS-grid
│   │     column on desktop, drawer on mobile.  Sprint 112.5
│   │     closes the loop with a toolbar/meta-panel content
│   │     split: five top-bar status badges (kernel state,
│   │     schedule presence, last-run age, peer count, agent
│   │     presence) collapse into a single vital-signs dot
│   │     cluster, and a new Activity accordion section in the
│   │     meta panel aggregates kernel / peers / recent-runs
│   │     from already-loaded reactive state (no new fetch).
│   │     Establishes the mental model — "always-visible =
│   │     verbs + active state; hidden behind one click =
│   │     rarely-used or fully-default state" — that Phase 113
│   │     then carries into three other cluttered surfaces.
│   │
│   ├── Phase 111 — Restschuld V (modularization wave)  ✅ done 2026-05-22
│   │     **Closed 2026-05-22.**  Seven commits, no behaviour change,
│   │     no asset bump.  Continuation of the Phase 110 trim line —
│   │     every > 700-LOC module landed under a per-concern package.
│   │     - **111.1 (commit ``46c282c``).** ``pql/sql_parser.py``
│   │       (762 LOC) → ``sql_parser/`` package per concern (types /
│   │       parse / prepare / refs / column_lineage / limit).
│   │     - **111.2 (commit ``d04cbf3``).** ``pql/_merge.py``
│   │       (770 LOC) → ``_merge/`` package per concern (constants /
│   │       resolve / strategies / lineage / stats / main).  Originally
│   │       framed as a Py2-syntax bug fix on
│   │       ``_merge_rows_affected``'s ``except TypeError, ValueError:``;
│   │       the user corrected that framing — Python 3.14 (PEP 758)
│   │       legalises unparenthesised ``except`` tuples, so the change
│   │       is cosmetic only.
│   │     - **111.3 (commit ``1673579``).** ``services/run_diff.py``
│   │       (724 LOC) → ``run_diff/`` package per concern (serialize /
│   │       align / detail / lineage / column).
│   │     - **111.4 (commit ``0e24c97``).** ``runs_routes/_loaders.py``
│   │       (733 LOC) → ``_loaders/`` package per axis (runs / outputs /
│   │       operations / audit / lineage).
│   │     - **111.5 (commit ``1e42413``).** ``services/social/
│   │       entity_registry.py`` (729 LOC) → ``entity_registry/``
│   │       package per concern (spec / url_builders / registry_data /
│   │       api).  Data-heavy: the 17-entry ``REGISTRY`` dict made up
│   │       most of the file.
│   │     - **111.6 (commit ``869daf5``).** ``api/notebook_coedit_ws.py``
│   │       (779 LOC) → ``notebook_coedit_ws/`` package per layer
│   │       (constants / state / seed / hub / broadcast / remap /
│   │       endpoint).  Six external private-name references (``_HUBS``
│   │       in five tests + the coedit_compaction executor) preserved
│   │       via ``__init__.py`` re-export.
│   │     - **111.7 (commit ``230a709``).** ``pql/pql.py`` (1060 LOC)
│   │       → ``PQLBase`` + ``_DataOpsMixin`` + ``_GovernanceMixin`` +
│   │       slim ``PQL(``mixins``)``.  Public API surface unchanged;
│   │       ``make_soyuz_client`` / ``make_principal_client`` /
│   │       ``make_engine`` re-exported from ``pql.py`` so the
│   │       documented ``patch("pointlessql.pql.pql.make_soyuz_client")``
│   │       test pattern keeps working.  ``PQLBase`` uses call-time
│   │       facade lookup so monkeypatches are honoured.
│   │     - **Follow-up (commit ``bf6bd1c``).** ``_merge/__init__.py``
│   │       re-export missed ``_detect_rejects`` in 111.2 → fixed
│   │       (regression sweep at 111.7 close caught it).
│   │
│   │     All seven splits: ruff / pyright (0 errors) / pydoclint
│   │     clean.  Pyright warnings stable at 655.  351 / 352 focused
│   │     regression tests green (1 pre-existing
│   │     ``TestReplayUnknownOpName`` failure unrelated to this trim).
│   │
│   │     Restschuld pipeline now drained: every previously > 700 LOC
│   │     module across pql/ + api/ + services/ has been split.  The
│   │     largest file in pointlessql/ post-111 is ``api/admin/console/
│   │     _legacy_pages.py`` (~600 LOC after 110.3).
│   │
│   │     Side note from this phase: corrected my own mistaken framing
│   │     of ``except A, B:`` as a Py2-syntax bug.  PEP 758 in Python
│   │     3.14 legalises the form — both 110.4 and 111.2 "drive-by
│   │     fixes" were cosmetic only; 15 other occurrences across the
│   │     codebase are valid syntax and left untouched.  Memory entry
│   │     ``feedback_pep758_except_syntax`` documents the rule so it
│   │     does not recur.
│   │
│   ├── Phase 110 — Restschuld IV (modularization wave for files > 700 LOC)  ✅ done 2026-05-22
│   │     **Closed 2026-05-22.**  Nine commits, no behaviour change,
│   │     no asset bump.  Continuation of the Phase 87 / 88 / 89
│   │     "Restschuld" trim line.  Every previously > 700-LOC module
│   │     touched in this phase landed under ~430 LOC per per-axis
│   │     file with its public surface preserved through the new
│   │     package's ``__init__.py`` re-exports.
│   │     - **110.1 (commit ``848bd26``).** ``services/scheduler/
│   │       executors.py`` (879 LOC) → ``executors/`` package with
│   │       six per-kind files (pg_sync / python / papermill /
│   │       alert_check / coedit_compaction / branch_cleanup).
│   │     - **110.2 (commit ``2fefb34``).** ``services/scheduler/
│   │       runs.py`` (860 LOC) → ``runs/`` package along the
│   │       per-concern axes: ``_db`` / ``_tasks`` / ``_telemetry`` /
│   │       ``_execute``.  ``_sleep`` test hook moved into the
│   │       package ``__init__`` with a call-time lookup so
│   │       ``monkeypatch.setattr(runs, "_sleep", ...)`` keeps
│   │       reaching the retry-backoff site in ``_tasks``.
│   │     - **110.3 (commit ``c0f44bf``).** ``api/admin/console.py``
│   │       (830 LOC) → ``console/`` package with one file per HTML
│   │       surface (landing / review-destinations / audit-sinks /
│   │       api-keys / system-info / sources / audit-trio).
│   │     - **110.4 (commit ``38c387e``).** ``api/lineage/views.py``
│   │       (784 LOC) → ``views/`` package per route family
│   │       (row-trace / column-trace / value-changes / index) on
│   │       top of one shared ``_helpers`` module.  Drive-by fix:
│   │       latent ``except A, B:`` Python-2 syntax in
│   │       ``_enrich_with_source_file`` now reads ``except (A, B):``.
│   │     - **110.5 (commit ``f72b1a4``).** ``api/data_products_routes/
│   │       comments.py`` (883 LOC) → ``comments/`` package per CRUD
│   │       verb with separate ``_constants`` / ``_mentions`` /
│   │       ``_helpers`` modules.  Four route handlers re-exported
│   │       so ``social_routes.comments`` (polymorphic dispatcher)
│   │       keeps its import path.
│   │     - **110.6 (commit ``c357215``).** ``api/notebook_kernel_ws.py``
│   │       (835 LOC) → ``notebook_kernel_ws/`` package per layer
│   │       (``_protocol`` / ``_pump`` / ``_handlers`` / ``_route``).
│   │     - **110.7 (commit ``8afd04f``).** ``api/social_routes/
│   │       issues.py`` (749 LOC) → ``issues/`` package per CRUD verb
│   │       (open / list / detail / state).
│   │     - **110.8 (commit ``a514aa9``).** ``services/data_products/
│   │       active_reviewer.py`` (760 LOC) → ``active_reviewer/``
│   │       package per concern (verdict / prompt / config / writers /
│   │       run).
│   │     - **110.9 (commit ``2f49c14``).** ``api/sql/write.py``
│   │       (730 LOC) → ``write/`` package per route family
│   │       (``_helpers`` / ``_autoload`` / ``_table`` / ``_dml``).
│   │       Route bodies look up ``_build_pql`` +
│   │       ``_materialise_select_to_pandas`` via the write package
│   │       at call time so existing tests that monkeypatch
│   │       ``pql_write_routes._build_pql`` keep reaching the route
│   │       call site.
│   │
│   │     Verified after every sub-phase: ``ruff check`` 0,
│   │     ``pyright`` 0 errors / 655 warnings stable, ``pydoclint``
│   │     0 violations, ``alembic check`` 0 drift, all per-area test
│   │     suites green (87 scheduler + 58 dag/scheduler + 33 admin
│   │     console + 38 lineage + 64 comment + 3 kernel-ws + 37 issue
│   │     + 15 active-reviewer + 12 pql-write).
│   │
│   ├── Phase 109 — Multi-worker co-edit hub (PG LISTEN/NOTIFY bus)  ✅ done 2026-05-22
│   │     **Closed 2026-05-22.**  Four commits, no asset bump.
│   │     Forward-looking infrastructure that closes the single-
│   │     process limit Phase 105.2 explicitly punted on (see
│   │     ``notebook_coedit_ws.py:145-147`` pre-109 comment).
│   │     Multiple uvicorn workers serving the same notebook now
│   │     exchange CRDT updates via Postgres LISTEN/NOTIFY — no
│   │     Redis / RabbitMQ dep.
│   │     - **109.1 (scaffold, commit ``d64722c``).**  New ORM
│   │       ``CoeditBusMessage`` outbox + alembic migration
│   │       ``b1a3c5e7f9a1``.  ``services/notebook/coedit_bus.py``
│   │       ``CoeditBus`` class: one long-lived psycopg async
│   │       connection in autocommit ``LISTEN coedit_bus``,
│   │       reconnect ladder ``(1, 2, 5, 10, 30) s``, sync publish
│   │       via ``asyncio.to_thread`` (INSERT + ``pg_notify`` in
│   │       one transaction so the row is visible by the time
│   │       remote workers ``SELECT``).  Source-PID stamp +
│   │       listener-side gate suppress self-loops.  Cleanup loop
│   │       drops rows older than ``ttl_seconds`` (default 60 s)
│   │       every ``cleanup_interval_seconds`` (default 30 s).
│   │       New ``CoeditSettings`` with
│   │       ``POINTLESSQL_COEDIT_BUS_ENABLED`` (default off).
│   │       Lifespan exposes ``app.state.engine`` so the bus can
│   │       avoid sessionmaker-internals digging.  4 PG-marked
│   │       integration tests in ``tests/test_coedit_bus.py``.
│   │     - **109.2 (hub wiring, commit ``b832567``).**  Module-
│   │       level ``_bus_ref`` set by ``bind_coedit_bus`` from
│   │       lifespan.  Publish sites: WS receive loop (sync_update
│   │       + awareness after local broadcast),
│   │       ``apply_save_remap`` (cell_uuid_remap after local
│   │       broadcast, publishes even when no local hub since
│   │       another worker may host the same notebook), and
│   │       ``broadcast_agent_presence`` (agent_presence same
│   │       behaviour).  Receive side: ``apply_remote_bus_frame``
│   │       callback looks up ``_HUBS[nb]``, replays the frame
│   │       into the local hub for tags 0x02-0x05, never
│   │       re-publishes (publish-exactly-once invariant).  New
│   │       ``_apply_remap_locked`` helper shared between
│   │       ``apply_save_remap`` and the bus-receive path.
│   │       Handshake tags 0x00/0x01 stay strictly local — pre-
│   │       client and the local hub has the authoritative state.
│   │     - **109.3 (admin status, commit ``fbc40ee``).**
│   │       ``GET /api/admin/coedit-bus/status`` returns
│   │       ``{enabled: false}`` on single-worker / SQLite
│   │       installs; on PG with the bus active it carries
│   │       ``own_pid``, ``listener_alive``, ``listener_ready``,
│   │       ``cleanup_alive``, ``inflight_outbox_rows`` for
│   │       operator diagnostics.  2 pytest covering the
│   │       disabled-default + admin-only-access paths.
│   │     - **109.4 (docs, this commit).**  New section in
│   │       ``docs/admin/postgres-deployment.md`` documenting the
│   │       env vars, the multi-worker startup command, the
│   │       diagnostic endpoint, and the explicit out-of-scope
│   │       list (cross-region, sticky routing, bus-level auth).
│   │     Trade-offs deliberately accepted:
│   │     * NOTIFY payload is row-id only (sidesteps the 8 KB
│   │       limit); the real frame lives in the BYTEA column.
│   │     * Single-worker behaviour unchanged.  Operators flip
│   │       the env var to opt in — no surprise extra DB writes
│   │       on existing PG installs.
│   │     * 60 s TTL trades brief durability for a bounded
│   │       outbox; longer outages re-converge through the CRDT
│   │       sync_step1/2 handshake on reconnect.
│   │     * No new dependency.  psycopg3 (already a core dep)
│   │       carries the async LISTEN/NOTIFY surface.
│   │
│   └── Phase 108 — Multi-tab co-edit CI gate + Phase 103 worker test  ✅ done 2026-05-22
│         **Closed 2026-05-22.**  Three commits, test-only (no
│         asset bump).  Adds the first headless-browser test job
│         to the PointlesSQL CI plus the missing kernel-execution
│         coverage for Phase 103's replay worker.
│         - **108.1 (e2e fixtures, commit ``3eea7d4``).**  Adds a
│           sibling ``e2e/`` test tree (outside ``tests/`` to escape
│           the autouse-fixture cascade that short-circuits the
│           FastAPI lifespan).  ``e2e/conftest.py`` provides
│           ``live_server_url`` (free port + tempfile SQLite +
│           alembic upgrade + seeded admin + uvicorn in background
│           thread + ``/healthz`` probe), ``admin_session_cookies``
│           (CSRF + form-encoded login flow), ``playwright_browser``
│           (headless bundled Chromium), and ``playwright_context``
│           (function-scope, auth cookies pre-injected).  ``playwright
│           >=1.50`` added to the dev group; ``e2e`` pytest marker
│           registered + auto-deselected from the default lane.
│         - **108.2 (multi-tab gate, commit ``ec6b5a4``).**
│           ``e2e/test_notebook_coedit_multi_tab.py`` asserts three
│           regression guards for the 2026-05-22 bug class:
│           ``[data-testid="notebook-coedit-pill"]`` reaches "Live"
│           in two tabs (Y.Doc sync handshake intact); peer rail
│           populates after both tabs nudge their awareness state
│           (regression guard for coedit.js ``user.id`` vs
│           ``clientID`` self-filter); zero script-level console
│           errors AND ``window.notebookChatPanel`` remains a
│           callable factory (regression guard for chat_drawer.html
│           ``|tojson`` attribute-quoting class).  New
│           ``e2e-browser`` CI job runs after ``gate``, installs
│           Playwright Chromium with ``--with-deps``, executes
│           ``pytest e2e/ -m e2e``.  ``continue-on-error: true``
│           for the first wave of green runs — flip once ≈10
│           successive greens collected.  Deferred from the
│           original 11-assertion plan: cell-level text propagation,
│           save-no-reset timing, fresh-tab ytext hydration (Phase
│           107 hotfix).  Too brittle without the human pacing of
│           the manual Phase 105.7 playbook; reopens as a follow-up
│           sub-phase once the basic gate is observed stable in CI.
│         - **108.3 (replay-worker happy-path, commit ``c05c94a``).**
│           ``test_replay_worker_executes_cell_and_records_output``
│           seeds a NotebookRevision with a single ``print(2 + 2)``
│           cell, inserts a pending replay row, drives one tick of
│           ``run_pending_replays`` directly, and asserts the row
│           settles to ``ok`` with ``"4"`` in its captured stream
│           frames.  This was the last untested path for Phase 103;
│           service / REST / lifespan / lifecycle were already
│           covered.  Bounded by ``asyncio.wait_for(60s)`` so a
│           stuck ipykernel surfaces as a test timeout.
│         - **Latent bug surfaced (not fixed in this phase).**  In
│           ``coedit.js`` line 88–98 the initial ``awareness.
│           setLocalState(...)`` fires before ``_wireAwarenessUplink``
│           attaches the WS push listener — the initial broadcast
│           is silently lost.  In real interactive use the next user
│           action (cursor move, keystroke) re-emits and peers see
│           each other; in headless tests we explicitly nudge the
│           awareness layer via ``setLocalState`` in page-evaluate.
│           Reorder the lines (uplink BEFORE first setLocalState)
│           in a follow-up.
│


├── Phases 124–127 — Data-Mesh-Plattform-Initiative           ⏳ planned
│       Strategische Achse: PointlesSQL zur erstklassigen
│       Implementierungs-Plattform für Data Meshes (nach Dehghani)
│       ausbauen.  Vollständige Gap-Analyse + Capability-Mapping in
│       [`docs/internal/data-mesh-requirements.md`](docs/internal/data-mesh-requirements.md);
│       die ROADMAP führt hier nur die grobe Phasenfolge — die
│       detaillierte Ausplanung jeder Phase folgt als eigenes Plan-/
│       ADR-Dokument vor Sprintbeginn.  Drei strukturelle Kernlücken
│       treiben die Reihenfolge: (1) keine Domänen-/Team-Entität
│       (Ownership nur user-skopiert), (2) Datenprodukt ist passive
│       Metadaten statt aktivem Architektur-Quantum (keine Ports/
│       Sidecar), (3) Governance ist zentral statt Policy-as-Code pro
│       Produkt.  Leitprinzip: agent-nativ — Agenten *schlagen*
│       Domänen-Zuschnitt, Contracts, Ports und Policies vor, Owner
│       geben frei (knüpft an die Agent-Supervision-Ebene + die
│       AI-native-Lakehouse-Vision an).
│
│   ├── Phase 124 — Data-Mesh: Domänen-Fundament              ✅ 2026-05-29
│   │     Grundstein (A1–A3, B5).  Neue `Domain` + `domain_members`
│   │     Entität (Archetyp source/aggregate/consumer-aligned am
│   │     Domain; Owner/Developer-Rollen); `domain_id` am Datenprodukt
│   │     (kein Katalog-Cache existiert → N/A); Transformation
│   │     (Notebook-FK oder dbt-Model-Name) per
│   │     `data_product_transformations` ans Produkt gebunden.  Admin-
│   │     CRUD `/admin/domains` + read-only Browse `/domains` +
│   │     `/domains/{slug}`; Produkt-Detail-Panel für Zuweisung +
│   │     Binding.  Agent-nativ: hermes-Tools `pql_list_domains` +
│   │     `pql_assign_data_product_domain` (steward/admin-gated).
│   │     A4 (Aggregat-Ownership-Heuristik) verschoben nach Phase 126.
│   │
│   ├── Phase 125 — Data-Mesh: Quantum-Ports & Discovery      ✅ 2026-05-29
│   │     Datenprodukt vom passiven Metadaten-Cache zum aktiven
│   │     Architektur-Quantum (B1–B3, B7, C-discoverable/addressable/
│   │     understandable, F4-Anfang).  DB-backed + UI-editierbar (nicht
│   │     YAML): neue Tabellen `data_product_output_ports` /
│   │     `data_product_input_ports` (deklarierte Upstreams →
│   │     deklarierte Lineage), `data_product_semantic_concepts` +
│   │     `data_products.sample_sql`, `data_product_statistics`,
│   │     `glossary_terms` + `glossary_term_columns`.  Discovery-Port
│   │     `GET .../discovery` (maschinenlesbar) + stabile URI
│   │     `urn:pointlessql:product:{ws}:{cat}:{schema}` mit Copy-Button.
│   │     B7: Shape + Row-Count beim Write am Produkt gestempelt
│   │     (Post-Commit-Hook, analog contract_events; in-memory light-
│   │     profile, kein Delta-Re-Scan; Reuse des table_stats-Cache).
│   │     B1: funktionierender Parquet-File-Export-Port
│   │     `GET .../export?table=` (SELECT-gated).  F4: Business-Glossar
│   │     (Admin-CRUD `/admin/glossary` + Browse `/glossary` +
│   │     Term→Spalte-Bindung → Badges auf dem Contract-Tab).  Overview-
│   │     Panels (Ports / Semantic / Statistics / Discovery), Nav.
│   │     Agent-nativ: hermes-Tools `pql_get_data_product_discovery` +
│   │     `pql_add_data_product_output_port` +
│   │     `pql_add_data_product_input_port` (steward/admin-gated).
│   │
│   ├── Phase 126 — Data-Mesh: Computational Governance       ✅ 2026-05-29
│   │     Von zentralen Checks zu Policy-as-Code pro Produkt
│   │     (E1–E9, B4, B6 + A4).  DB-backed + UI-editierbar (wie 124/125):
│   │     neue Tabellen `workspace_governance_policies` (E8-Defaults),
│   │     `data_product_policies` (Produkt-Override, vererbt sonst den
│   │     Workspace-Default), `data_product_column_classifications`
│   │     (PII/PHI-Klasse → Read-Time-Masking) und
│   │     `data_product_forget_requests` (Right-to-be-forgotten-Ledger,
│   │     Subjektwert nur gehasht).  **Sidecar (B6)**: gemeinsamer
│   │     `services/governance/`-Layer führt die Klassifizierungs-
│   │     Policy am Zugriffspunkt aus — Read-Time-Masking am Export-Port
│   │     + Table-Preview (exakte Spalten-Zuordnung) + best-effort im
│   │     SQL-Editor (Notebook-Kernel-SQL bleibt bewusst eine
│   │     dokumentierte Lücke).  **Control-Port (B4)**: `GET/PUT .../policy`,
│   │     `GET/POST/DELETE .../classifications`, `POST .../control/forget`
│   │     (Steward/Admin-direkt, sofortige Löschung über die deklarierten
│   │     Tabellen, auditiert + Governance-Event) und
│   │     `POST .../control/forget-requests` (Agent-Vorschlag, nur
│   │     `proposed`).  **Ehrliche Trennung**: Retention wird überwacht,
│   │     PII-Masking + Right-to-be-forgotten werden erzwungen;
│   │     Encryption-Klasse/Residency/Consent sind Deklarationen
│   │     (im Discovery-Vertrag + Compliance-Scan sichtbar).  **E9**:
│   │     Scheduler-Job `kind="policy_compliance"` + Admin-„scan now"
│   │     flaggen Retention-Überzug + unklassifizierte PII-Spalten ins
│   │     Audit-Log (Trust-Downgrade-Chip am Produkt).  E8 Workspace-
│   │     Default unter `/admin/governance`.  A4: Aggregat-Ownership-
│   │     Heuristik (Mehrheits-Domäne der deklarierten Upstreams) als
│   │     Hinweis auf dem Governance-Tab.  Discovery-Envelope um einen
│   │     `policies`-Block erweitert.  Agent-nativ: hermes-Tools
│   │     `pql_get_data_product_policy` + `pql_set_data_product_policy`
│   │     + `pql_classify_data_product_column` +
│   │     `pql_request_right_to_be_forgotten` (Agenten schlagen vor,
│   │     Steward/Admin führt aus).
│   │
│   └── Phase 127 — Data-Mesh: Interoperabilität & Mesh-Observability  ✅ 2026-05-29
│         Querschnitt + Reifegrad-Abschluss — schließt den 124–127
│         Data-Mesh-Cluster (volles δ, ehrliche Trennung; D1-bitemporal,
│         D5-Graph, F1–F3/F5, G1–G5).  DB-backed (wie 124–126): neue
│         Tabellen `data_product_slos` (voller SLO-Satz) + `mesh_entities`
│         / `mesh_entity_bindings` (polysemer Identifikator) +
│         `agent_run_operations.correlation_id` (Cross-Produkt-Trace).
│         **G5 Emergenter Mesh-Graph**: `services/mesh/_graph.py` baut den
│         Abhängigkeitsgraphen aus den deklarierten `upstream_product`-
│         Input-Ports (Phase 125) — Produkte = Knoten, deklarierte
│         Upstreams = Kanten; `GET /api/mesh/graph` + Browse `/mesh` +
│         Produkt-Interop-Tab-Nachbarschaft (cytoscape).  **F3 Polysemer
│         Identifikator**: Mesh-Entitäten (Admin-CRUD `/admin/mesh-entities`
│         + Browse `/mesh/entities`) + Spalten-Bindungen am Produkt-
│         Interop-Tab → **D5 Join-Helfer** (`/joinable` schlägt
│         gemeinsame-Entität-Join-Keys + Sample-SQL vor).  **F2 Point-in-
│         time**: `resolve_as_of` löst je Produkt-Tabelle die Delta-
│         Version zum Zeitpunkt auf (`POST .../point-in-time-read` → Manifest;
│         schwerer Read bleibt PQL-Primitive).  **G1 Voller SLO-Satz**:
│         `services/slo/` deklariert alle Arten, misst die berechenbaren
│         (Freshness/Volume/Completeness/Statistical-Shape-Drift/Lineage-
│         Coverage), Rest = ehrliche Deklarationen; Live-Verdikte am
│         Overview-SLO-Panel.  **G3 Drift**: Baseline aus der
│         `data_product_statistics`-Historie (z-Score).  **G2 Mesh-Health**:
│         `/mesh/health` rollt SLO-Bänder über alle Produkte; Scheduler-Job
│         `kind="slo_evaluation"` + Admin-„evaluate now" flaggen `fail` ins
│         Audit-Log (`slo.violation`).  **F1/D1/F5 Bitemporalität**:
│         opt-in Processing-Time-Injektion beim Write (default off —
│         Schema-Evolution; `services/bitemporal/`), Event-Time bleibt
│         Konvention + `table_as_of_event_time`-Read-Helfer.  **G4
│         Correlation-IDs**: `X-Correlation-ID` (Middleware) → auf jeder
│         `agent_run_operations`-Zeile gestempelt; `GET /api/mesh/trace/{id}`
│         als produktübergreifende Timeline.  Discovery-Envelope um
│         `entities` + `bitemporal`-Blöcke + `slos.additional` + `mesh`-Link
│         erweitert.  Agent-nativ: hermes-Tools `pql_get_mesh_graph` +
│         `pql_get_mesh_health` + `pql_declare_data_product_slo` +
│         `pql_register_mesh_entity` + `pql_bind_mesh_entity_column`.
│


├── Phase 128 — Data-Mesh-Cluster Browser-Replay & Walkthroughs  ✅ 2026-05-29
│       Retroaktives Anlegen des Playwright-Gates für den 124–127-
│       Cluster, der über zwei Commits ohne Browser-Replay + ohne
│       e2e-Playbooks gelandet war.  Vollständiger Firefox-Replay aller
│       Mesh-/Domänen-/Quantum-/Governance-Flächen (admin-domains/
│       domains/glossary/mesh-graph/health/entities + Produkt-Overview-
│       Panels + Contract-Badge + Governance-Tab + Interop-Tab + SLO-
│       Panel) — jede Fläche gerendert, Primäraktion ausgeführt, Konsole
│       cluster-fehlerfrei.  **Gefundener Bug (BUG-128-01, gefixt):**
│       `_partials/data_product/tab_contract.html` fehlte das schließende
│       `</div>` — dadurch waren Diff/Lineage/Compliance/**Governance**/
│       **Interop**/Activity-Panes als Kinder des Contract-Panes
│       verschachtelt und beim direkten Anwählen unsichtbar
│       (`display:none` über das Eltern-Pane).  Der Governance-Tab (126)
│       und der Interop-Tab (127) rendern erst nach dem Fix.  Zusätzlich
│       `mesh_health.html` x-data auf Single-Quote normalisiert
│       (Konsistenz; boolescher tojson war benigne).  Neuer idempotenter
│       `scripts/seed-mesh-demo.py` (2 Produkte + Upstream-Kante +
│       Statistiken + 1 pass/1 fail SLO) als Replay-Substrat.  4 neue
│       hybrid-Playbooks: `data-domains.md`, `data-product-discovery.md`,
│       `data-governance.md`, `data-mesh.md` (+ README-Index 69→73).
│       Asset rc177→rc178.
│


├── Phase 81 — Feed overhaul + help surface + entity ⋯-menu  ✅ archived (2026-05-16)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-81-feed-overhaul--help-surface--entity--menu`](docs/internal/roadmap_archive.md#phase-81-feed-overhaul--help-surface--entity--menu) in W2.
│
├── Phase 80 — Navigation & UX overhaul  ✅ archived (2026-05-15)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-80-navigation--ux-overhaul`](docs/internal/roadmap_archive.md#phase-80-navigation--ux-overhaul) in W2.
│
├── Phase 76 — Full Social Network for Data Products  ✅ archived (2026-05-13)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-76-full-social-network-for-data-products`](docs/internal/roadmap_archive.md#phase-76-full-social-network-for-data-products) in W2.
│
├── Phase 75 — Verifiable audit export + SIEM sinks  ✅ archived (2026-05-15)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-75-verifiable-audit-export--siem-sinks`](docs/internal/roadmap_archive.md#phase-75-verifiable-audit-export--siem-sinks) in W2.
│
├── Phase 66 — Browser Notebook editor v2  ✅ archived (2026-05-10)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-66-browser-notebook-editor-v2`](docs/internal/roadmap_archive.md#phase-66-browser-notebook-editor-v2) in W2.
│
├── Phase 67 — Notebook Operations (Schedule / Parametrize / Inspect)  ✅ archived (2026-05-12)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-67-notebook-operations-schedule--parametrize--inspect`](docs/internal/roadmap_archive.md#phase-67-notebook-operations-schedule--parametrize--inspect) in W2.
│
├── Phase 68 — Frontend modularization (HTML + JS + CSS hygiene)  ✅ archived (2026-05-12)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-68-frontend-modularization-html--js--css-hygiene`](docs/internal/roadmap_archive.md#phase-68-frontend-modularization-html--js--css-hygiene) in W2.
│
├── Phase 69 — Vollständiger Browser-Replay der Plattform  ✅ archived (2026-05-12)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-69-vollstndiger-browser-replay-der-plattform`](docs/internal/roadmap_archive.md#phase-69-vollstndiger-browser-replay-der-plattform) in W2.
│
├── Phase 70 — Notebook track (member-access + JS-split)  ✅ archived (2026-05-12)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-70-notebook-track-member-access--js-split`](docs/internal/roadmap_archive.md#phase-70-notebook-track-member-access--js-split) in W2.
│
├── Hygiene wave H.1-H.7 — (title n/a)  ✅ archived (2026-05-12)
│   │
│   │   Detail moved to [`roadmap_archive.md#hygiene-wave-h1-h7-title-na`](docs/internal/roadmap_archive.md#hygiene-wave-h1-h7-title-na) in W2.
│
├── Phase 65 — Lens (read-only Q&A surface, MCP + Browser parallel)  ✅ archived (2026-05-10)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-65-lens-read-only-qa-surface-mcp--browser-parallel`](docs/internal/roadmap_archive.md#phase-65-lens-read-only-qa-surface-mcp--browser-parallel) in W2.
│
├── Phase 64 — Permission-locked nav-link UX  ✅ archived (2026-05-10)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-64-permission-locked-nav-link-ux`](docs/internal/roadmap_archive.md#phase-64-permission-locked-nav-link-ux) in W2.
│
├── Phase 63 — Writeable SQL Editor (AST-dispatch refactor)  ✅ archived (2026-05-10)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-63-writeable-sql-editor-ast-dispatch-refactor`](docs/internal/roadmap_archive.md#phase-63-writeable-sql-editor-ast-dispatch-refactor) in W2.
│
├── Phase 62 — MLflow slim-down + catalog hand-off  ✅ archived (2026-05-09)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-62-mlflow-slim-down--catalog-hand-off`](docs/internal/roadmap_archive.md#phase-62-mlflow-slim-down--catalog-hand-off) in W2.
│
├── Phase 61 — dbt tab slim-down + catalog hand-off  ✅ archived (2026-05-09)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-61-dbt-tab-slim-down--catalog-hand-off`](docs/internal/roadmap_archive.md#phase-61-dbt-tab-slim-down--catalog-hand-off) in W2.
│
├── Phase 59 — Comprehensive UX-tour quality sweep  ✅ archived (2026-05-08)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-59-comprehensive-ux-tour-quality-sweep`](docs/internal/roadmap_archive.md#phase-59-comprehensive-ux-tour-quality-sweep) in W2.
│
├── Phase 58 — Phase-57 carve-out trio  ✅ archived (2026-05-08)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-58-phase-57-carve-out-trio`](docs/internal/roadmap_archive.md#phase-58-phase-57-carve-out-trio) in W2.
│
├── Phase 57 — Phase-56 carve-outs + route-test coverage  ✅ archived (2026-05-08)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-57-phase-56-carve-outs--route-test-coverage`](docs/internal/roadmap_archive.md#phase-57-phase-56-carve-outs--route-test-coverage) in W2.
│
├── Phase 56 — UX-polish + bug-hunt + semantic-content review  ✅ archived (2026-05-08)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-56-ux-polish--bug-hunt--semantic-content-review`](docs/internal/roadmap_archive.md#phase-56-ux-polish--bug-hunt--semantic-content-review) in W2.
│
├── Phase 55 — UI polish nachzug (post-Phase-54)  ✅ archived (2026-05-08)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-55-ui-polish-nachzug-post-phase-54`](docs/internal/roadmap_archive.md#phase-55-ui-polish-nachzug-post-phase-54) in W2.
│
├── Phase 54 — UI overhaul implementation (M = Modernize)  ✅ archived (2026-05-08)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-54-ui-overhaul-implementation-m--modernize`](docs/internal/roadmap_archive.md#phase-54-ui-overhaul-implementation-m--modernize) in W2.
│
├── Phase 53 — Full replay sweep + Bootstrap UI overhaul evaluation  ✅ archived (2026-05-07)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-53-full-replay-sweep--bootstrap-ui-overhaul-evaluation`](docs/internal/roadmap_archive.md#phase-53-full-replay-sweep--bootstrap-ui-overhaul-evaluation) in W2.
│
├── Phase 52 — Playwright walkthrough completion pass  ✅ archived (2026-05-07)
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-52-playwright-walkthrough-completion-pass`](docs/internal/roadmap_archive.md#phase-52-playwright-walkthrough-completion-pass) in W2.
│
├── Phase 51 — Git-backed workspaces  ✅ archived ((date n/a))
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-51-git-backed-workspaces`](docs/internal/roadmap_archive.md#phase-51-git-backed-workspaces) in W2.
│
├── Phase 50 — Native Data-Product support  ✅ archived ((date n/a))
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-50-native-data-product-support`](docs/internal/roadmap_archive.md#phase-50-native-data-product-support) in W2.
│
├── Phase 48 — Primitive-Obsession StrEnum Sweep  ✅ archived ((date n/a))
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-48-primitive-obsession-strenum-sweep`](docs/internal/roadmap_archive.md#phase-48-primitive-obsession-strenum-sweep) in W2.
│
├── Phase 49c — TableFqn validation type  ✅ archived ((date n/a))
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-49c-tablefqn-validation-type`](docs/internal/roadmap_archive.md#phase-49c-tablefqn-validation-type) in W2.
│
├── Phase 49b — Service-File Splits  ✅ archived ((date n/a))
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-49b-service-file-splits`](docs/internal/roadmap_archive.md#phase-49b-service-file-splits) in W2.
│
├── Phase 49a — Repo-wide Lint-Sweep  ✅ archived ((date n/a))
│   │
│   │   Detail moved to [`roadmap_archive.md#phase-49a-repo-wide-lint-sweep`](docs/internal/roadmap_archive.md#phase-49a-repo-wide-lint-sweep) in W2.
│
├── Some-day — Public launch + external distribution      💤 unscheduled
│   │
│   │   This is the moment the stack goes from "my project" to
│   │   "something strangers can try" — and importantly, from
│   │   "code on my laptop" to "verifiable trust infrastructure
│   │   in the EU AI Act / SOC2 / GDPR sense".  Apache 2.0 is
│   │   locked (UC-compatible, no ethical-use-clause drama).
│   │
│   │   Strategic framing (from the Phase-15.7-close strategy
│   │   conversation):
│   │
│   │   - Audit infrastructure ≠ ordinary OSS.  Compliance
│   │     buyers REQUIRE source-availability — closed-source
│   │     audit tools fail the third-party-auditor test.  OSS
│   │     here is an asset, not a giveaway.
│   │   - Empirical OSS-infra track record: Sentry, dbt, Grafana,
│   │     HashiCorp, Confluent all spent 2-4 years OSS-only
│   │     before commercial offering.  "Sales platform first"
│   │     is the wrong move for solo-founder infra.
│   │   - The commercial wedge is NOT the OSS code.  Candidates:
│   │     hosted SaaS (PointlesSQL Cloud), enterprise edition
│   │     (SSO/SAML/multi-tenant audit storage), cryptographic
│   │     anchor service (closed/hosted, the shoreguard
│   │     Provenance Log angle), certified compliance reports.
│   │     None of these compete with Apache-2.0 community edition.
│   │
│   ├── Pre-OSS-release hygiene (1 week of work)         ⏳
│   │   ├── EUIPO trademark filings for ``PointlesSQL``,
│   │   │   ``soyuz-catalog``, ``shoreguard``.  Classes 9
│   │   │   (software), 42 (SaaS), 41 (consulting).  ~€2550 total,
│   │   │   10-year protection.  DE-only fallback at ~€290 each
│   │   │   if EU-wide too costly upfront.  Trademark is
│   │   │   non-optional for any future commercial wedge.
│   │   ├── ``NOTICE.txt`` in each core repo establishing
│   │   │   author + Apache 2.0 + Copyright 2026 Florian
│   │   │   Hofstetter.  Anchors solo-author copyright record
│   │   │   for any future Founder Resolution / IP-transfer to
│   │   │   incorporated entity.
│   │   ├── ``CONTRIBUTING.md`` + ``CODE_OF_CONDUCT.md`` +
│   │   │   ``SECURITY.md`` per repo.  Defines governance
│   │   │   *before* community arrives.
│   │   ├── CLA-Bot (CLA-Assistant or EasyCLA) on every PR.
│   │   │   CNCF-CLA template adapted.  Without CLA, third-party
│   │   │   contributions fragment copyright and block any
│   │   │   future dual-licensing option.
│   │   ├── Domain ownership: pointlessql.dev/.io/.com,
│   │   │   shoreguard.io, soyuz-catalog.io.  ~€50/year each.
│   │   └── Private STRATEGY.md (NOT in repo): commercial-wedge
│   │     decision document.  "Hosted PointlesSQL Cloud +
│   │     cryptographic anchor as the closed wedge" or whatever
│   │     it is.  Clarity for founder, signal for investors
│   │     later.  NOT public until commercial offering ships.
│   │
│   ├── Big-bang launch day (1 day, coordinated)         ⏳
│   │   ├── ``Show HN: PointlesSQL — per-cell lineage for Delta
│   │   │   Lake via CDF`` posted Mon/Tue 8-10 UTC for European
│   │   │   prime time + US morning.  Demo screenshot, link to
│   │   │   blog post #1, mention soyuz + shoreguard as siblings.
│   │   ├── Twitter / Mastodon thread (10-12 tweets) with
│   │   │   architecture diagrams.  Tag data-eng-Twitter
│   │   │   gravity (Benn Stancil, Tristan Handy, Pedram Navid,
│   │   │   Chad Sanderson, Julien Le Dem).
│   │   ├── Reddit posts: r/dataengineering + r/programming.
│   │   ├── LinkedIn long-form post.
│   │   ├── Blog post #1: *"Why we built per-cell lineage on
│   │   │   Delta CDF"* — published same day, linked from HN.
│   │   └── Hacker News frontpage hit-rate target: 30%.  Even a
│   │       moderate showing (~50 upvotes, 200 visitors) creates
│   │       the "Sarah saw this in our internal Slack" pathway
│   │       that converts to recruiter / engineer outreach.
│   │
│   ├── Conference circuit (3-12 month lead time)        ⏳
│   │   ├── DataCouncil — "How per-cell lineage closes the
│   │   │   EU-AI-Act audit gap".  Springs 2026 / Falls 2027.
│   │   ├── Subsurface — "Building Z3-verified policies for
│   │   │   agent sandboxes" (shoreguard angle).
│   │   ├── dbt Coalesce — "Comparing PointlesSQL audit-substrate
│   │   │   to Unity Catalog Lineage".
│   │   ├── Berlin Buzzwords — DE local, easier to land first
│   │   │   slot, builds CFP-pipeline credibility.
│   │   ├── Big Data LDN — UK enterprise audience, compliance
│   │   │   buyer-aligned.
│   │   └── KubeCon EU (longer shot) — shoreguard / OpenShell
│   │       angle if maturity allows.
│   │
│   ├── Sustained visibility (months 1-12 post-launch)   ⏳
│   │   ├── Blog post series, 1 every 3 weeks: per-cell lineage
│   │   │   for EU AI Act, Delta CDF deep-dive, comparing to UC
│   │   │   Lineage, Z3-verified policies, cross-tool lineage.
│   │   ├── Twitter daily: 3-5 substantive posts/week.  Reply
│   │   │   to Data-Eng-Twitter threads with substance not spam.
│   │   ├── LinkedIn updated: headline "Building open-source
│   │   │   data audit + governance — PointlesSQL, soyuz,
│   │   │   shoreguard".  About-section + skills tuned for
│   │   │   recruiter sourcing tools (HireEZ / Gem / SeekOut
│   │   │   scrape LinkedIn keywords, not GitHub).
│   │   └── Office Hours outbound: 1:1 calls with engineering
│   │       managers at target acquirers (Snowflake, Atlan,
│   │       Acryl Data, OneTrust, Drata, Vanta, Snowplow,
│   │       Microsoft Purview team) once first-run substance
│   │       is shipped (Phase 18+ done).
│   │
│   ├── Packaging + distribution (the original Some-day)  ⏳
│   │   ├── GHCR packages flipped private → public for both
│   │   │   ``pointlessql`` and ``soyuz-catalog`` images; the
│   │   │   Phase-10-deferred ``docs/e2e-walkthroughs/packaging.md``
│   │   │   dogfood replay finally runs end-to-end without the
│   │   │   PAT dance
│   │   ├── Multi-arch (amd64 + arm64) image builds via docker
│   │   │   buildx — the single-sprint work that Phase 10
│   │   │   couldn't justify for an audience of one
│   │   ├── Public PyPI publish of ``soyuz-catalog-client``
│   │   │   (first) and the ``pointlessql`` wheel (second);
│   │   │   replaces Phase 10's private git-tag pin for the
│   │   │   general audience while keeping the tag-pin option
│   │   │   available for consumers who prefer reproducible
│   │   │   git-based installs
│   │   ├── Optional: Helm chart for K8s deployments,
│   │   │   generalising "runs on a €15/month vServer" to
│   │   │   "runs on a cluster"
│   │   └── README / docs pass: swap the "functional Databricks
│   │       clone" alpha framing for the post-15.7 honest
│   │       positioning: *"per-cell auditable lakehouse for
│   │       agent-driven data engineering, EU-AI-Act-native"*.
│   │
│   └── Commercial offering (12-24 months post-OSS)      ⏳
│       ├── Identify 3-5 paying design partners from the
│       │   community (mid-cap retailer with EU-AI-Act compliance
│       │   pressure, healthcare-data-engineering, financial
│       │   reporting under ASC 606).  €500-2k/month each as
│       │   willingness-to-pay validation.
│       ├── Co-design the commercial wedge with design partners
│       │   — what they actually want to pay for vs what they
│       │   get free.  Likely: hosted SaaS, certified
│       │   compliance reports, multi-tenant audit retention,
│       │   SSO/SAML, cryptographic anchor service.
│       ├── UG/GmbH incorporation (~€500 + Notar) once a
│       │   contract template + 2 verbal-LOIs exist.  Founder
│       │   Resolution transfers pre-incorporation IP to entity.
│       └── First commercial offering live, based on what design
│           partners actually paid for — not what was guessed
│           upfront.  Expected revenue trajectory: €0 → €60k ARR
│           year 1 → €200-500k year 2 → €1-3M year 3 (typical
│           OSS-infra commercial-bootstrap curve).
│
├── Icebox — enterprise-audit follow-ups                  🧊 on ice
│   │
│   │   Sprint 48 ported six of nine shoreguard-fresh audit
│   │   patterns.  Two of the three remaining items landed in
│   │   Phase 75 (2026-05-15) — verifiable export and SIEM
│   │   sinks.  Only the action-string rename stays parked here.
│   │
│   ├── Audit export with sha256 digest + manifest  ✅ promoted to Phase 75.1
│   │   └── See Phase 75.1 above for the shipped implementation.
│   │
│   ├── Audit-to-SIEM export sinks                  ✅ promoted to Phase 75.2
│   │   └── See Phase 75.2 above for the shipped stdout_json +
│   │       syslog implementations.
│   │
│   └── Retroactive action-string rename to ``resource.verb``  🧊 on ice
│       └── Churn-only refactor of the 25 pre-Sprint-48 action
│           strings (``update_catalog`` → ``catalog.updated``, …)
│           to fully align with the convention Phase 12 adopts
│           for new events. Pure ergonomics for the
│           ``/admin/audit`` dropdown — no behavioural change —
│           so only worth doing the day the whole fleet gets
│           rewired (e.g. a release-notes-worthy version bump)
│
└── Explicitly out of scope (probably ever)
    ├── Reimplementing the Unity Catalog REST API — that is
    │   soyuz-catalog's job; PointlesSQL is a consumer
    ├── Building a query engine — PointlesSQL starts engine
    │   kernels (Pandas/Polars/Spark/DuckDB) and delivers UC
    │   config; it does not parse SQL or plan queries itself
    ├── Running the JVM upstream UC server — soyuz-catalog is
    │   the spec-compatible replacement
    └── Federated query planning across multiple foreign
        catalogs — that is a query-engine concern
```

## How to update this file

- **When a sprint lands:** flip its marker to ✅, append
  `(<short-sha>)`, and add a one-line `CHANGELOG.md` entry under
  `## [Unreleased]`.
- **When a new sprint is planned:** add it under the current phase
  with ⏳ and a short bullet list of the concrete scope. Keep it
  short — this is a tracker, not a design doc. Design details go
  in ADRs under `docs/adr/`.
- **When scope shifts:** edit the bullet list in place rather than
  adding a "scope change" section. The git history of this file
  *is* the scope-change log.
- **When a phase completes:** flip the phase marker to ✅ and
  move on. Do not delete completed phases — they are the record
  of what "done" meant.
- **When closed phases stack up:** roll older completed phases
  out of `ROADMAP.md` into [`docs/internal/roadmap_archive.md`](docs/internal/roadmap_archive.md)
  using the existing collapse pattern (one-line summary in a
  table, full detail moved verbatim to the archive). Both
  conditions must hold before a phase qualifies for the roll:
  1. **Line-count trigger:** `ROADMAP.md` exceeds ~2000 lines —
     a soft "consider rolling" signal, not an automatic roll.
  2. **Staleness trigger:** the phase has been closed for
     **≥30 days** *and* no subsequent phase has actively
     referenced it for >3 months. Recently-closed phases
     stay full-detail because they're still load-bearing for
     follow-up conversations, even when the file is long.

  Example (2026-05-12): `ROADMAP.md` is 7068 lines (line-count
  trigger fires) but Phases 12.9–20 closed 2026-04-29 to
  2026-05-05 are all <30 days old → no roll yet. Reassess once
  a follow-up phase has shipped on top of each and stayed
  stable for 30 days.

This file is read first by every new Claude Code session (see
[`CLAUDE.md`](CLAUDE.md)).
