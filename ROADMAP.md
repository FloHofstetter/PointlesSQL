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


├── Phase 129–133 — Data-Mesh-Quantum-Completeness (Cluster)  ✅ 2026-05-30
│       Schließt die sechs *echt-fehlenden* Capabilities der Mesh-
│       Gap-Analyse [`docs/internal/data-mesh-requirements.md`](docs/internal/data-mesh-requirements.md)
│       ab.  Backend-vollständig (Migrations + Models + Services +
│       Discovery + Tests); UI-Panels, Hermes-Plugin-Tools und Playwright-
│       Walkthroughs werden im Folge-Replay-Phase nachgezogen — der
│       Gegenwert dieses Clusters ist die strukturelle Grundlage.
│
│   ├── Phase 129 — D6 Produkt-Lebenszyklus
│   │       `lifecycle_state` (draft/active/deprecated/retired/archived)
│   │       am DataProduct + state-machine guards + Audit-getriebene
│   │       History + `/api/data-products/{c}/{s}/lifecycle{,/propose,
│   │       /{target}}` (steward/admin direct + agent propose). Discovery
│   │       erhält `lifecycle`-Block mit Replacement-URN (für retired
│   │       Successors). Migration `k2m4o6q8s0u2`. 16 pytest grün.
│   │
│   ├── Phase 130 — D2 Input-Port-Consumption-Enforcement
│   │       Neues `consumption_enforcement` Feld auf
│   │       `data_product_policies` + `workspace_governance_policies`
│   │       (off/advisory/strict, default advisory).  Service
│   │       `services/governance/_consumption.py` mit
│   │       `evaluate_consumption` + `assert_declared_consumption` +
│   │       `ConsumptionVerdict` (ALLOW/WARN/BLOCK).  Discovery
│   │       `policies.consumption_enforcement`.  Migration
│   │       `l3n5p7r9t1v3`. 13 pytest grün.  Route-Hooks an Export-Port +
│   │       Table-Preview + SQL-Editor: deferred (Authoring-Product-
│   │       Context-Pipeline kommt im Wrap-up).
│   │
│   ├── Phase 131 — F1/F5 Bitemporalität-Standardisierung
│   │       Workspace-Settings `BitemporalSettings.enforcement` (off/
│   │       opt_in/required) + `require_event_time`.  Neue Tabelle
│   │       `data_product_bitemporal_policy` (per-Produkt-Override).
│   │       Service `services/bitemporal/_policy.py` Inheritance-Resolver
│   │       (`EffectiveBitemporal`) + `_validate.py`
│   │       `validate_event_time_column` mit
│   │       `BitemporalRequirementError`.  Discovery `bitemporal`-Block
│   │       um `enforcement` + `require_event_time` erweitert.  Migration
│   │       `m4o6q8s0u2w5`. 14 pytest grün.
│   │
│   ├── Phase 132 — B8 Infrastructure-Declarations + C Consumer-Voice
│   │       Vier neue Tabellen — `data_product_infrastructure`
│   │       (storage_class/compute_runtime/access_methods/region/notes,
│   │       1:1), `data_product_use_cases` (1:N, votes-cache),
│   │       `data_product_use_case_votes` (1:1 pro (uc,user)),
│   │       `data_product_ratings` (1:1 pro (product,user), 1-5 score).
│   │       Services `services/infrastructure/` +
│   │       `services/consumer_voice/` (upvote-idempotent,
│   │       rating-upsert, avg-aggregate).  Discovery `infrastructure`,
│   │       `use_cases` (top 5), `rating` ({avg,count}).  Migration
│   │       `o6q8s0u2w5y7`. 13 pytest grün.
│   │
│   └── Phase 133 — B1/D1 Event-Stream-Output-Port (Substrat)
│           Honest "Delta-CDF + WS/SSE Fan-out"-Variante.  Neue Settings
│           `EventPortSettings` (POINTLESSQL_EVENT_*, default OFF).
│           Migration `q8s0u2w5y7a9`: `data_product_event_subscriptions`
│           (durable Subscription mit Position-Cursor) +
│           `data_product_event_deliveries` (Per-Pump-Audit).  Service
│           `services/event_port/_subscription_crud.py` —
│           Subscription-CRUD, Pause/Resume, Forward-Only-Advance +
│           Backward-Rewind, Delivery-Ledger.  Validiert dass referenced
│           output port `kind='event'` ist.  Pump + WS-Hub + Streaming-
│           Endpunkte: deferred (Substrat ohne Runtime ist startfähig).
│           14 pytest grün.
│
│       Asset rc178→rc179.  Komplettes pytest: 3701/0/10 grün.
│       ruff sauber, alembic round-trips 124→133.
│
├── Phase 134 — Quantum-Completeness-Cluster Restschuld (Wiring + UI + Plugin-Tools + Walkthroughs)  ✅ (2026-05-29)
│   │
│   │   Vervollständigt die 129–133-Substrate zu nutzbarer Plattform-
│   │   Oberfläche.  Keine eigene Migration — alle Tabellen aus dem
│   │   vorigen Cluster reichen.
│   │
│   ├── 134.1 — D2 Konsumtions-Enforcement-Route-Hooks
│   │       Neue FastAPI-Dependency `get_authoring_product` (Header
│   │       `X-PointlesSQL-Authoring-Product` / Query `?as_product=` /
│   │       Session-State).  Shared Hook `enforce_consumption_for_read`
│   │       (Service `_consumption_hook.py`) eingehängt an Export
│   │       (`export.py`), Tabellen-Preview (`catalog_routes.py`) und
│   │       SQL-Editor-SELECT (`sql/_dispatcher/_select.py`).  WARN
│   │       schreibt Audit + erlaubt; BLOCK raised
│   │       `ConsumptionViolation` (jetzt
│   │       `PermissionDeniedError`-Subklass → 403 Envelope mit
│   │       strukturierten Extras).  13 neue pytest.
│   │
│   ├── 134.2 — F1 Bitemporal-Validate-Wiring in pql/_write.py
│   │       Neuer Helper `_maybe_validate_and_stamp_bitemporal` ruft
│   │       `effective_policy(...)` für das (factory, data_product_id)-
│   │       Paar auf, validiert event-time-Spalte (raised
│   │       `BitemporalRequirementError` bei `require_event_time=True`
│   │       + fehlend / wrong dtype), stempelt processing-time wenn
│   │       Policy es verlangt.  Existing `_maybe_stamp_processing_time`
│   │       ersetzt; alte Test-Imports umbenannt.  8 neue pytest.
│   │
│   ├── 134.3 — B1 Event-Port-Runtime (CDF + Hub + Pump + Endpunkte)
│   │       `services/event_port/_cdf_reader.py` (deltalake load_cdf-
│   │       Wrapper, bounded), `_ws_hub.py` (per-(product,table)
│   │       Lazy-Init + Lock + broadcast/release-if-empty, mirror
│   │       coedit-Hub Pattern), `_pump.py` (advanced position +
│   │       ledger + broadcast; injizierbarer reader für Tests).
│   │       Scheduler-Executor `event_port_pump` registriert in
│   │       `build_default_registry()` (gated by
│   │       `EventPortSettings.enabled`).  Neue Routen-Datei
│   │       `data_products_routes/event_port.py`: CRUD
│   │       (GET/POST/DELETE event-subscriptions),
│   │       pause/resume/rewind, HTTP-Chunked NDJSON-Stream
│   │       (`GET .../events`), WebSocket (`WS .../events`).
│   │       16 neue pytest.
│   │
│   ├── 134.4 — UI-Panels (5 neue + 1 erweitert) + Asset-Bump rc179→rc180
│   │       Sechs neue Partials in
│   │       `frontend/templates/pages/_partials/data_product/`:
│   │       lifecycle (state-badge + history + transition-buttons),
│   │       bitemporal (read-only badge card), infrastructure (steward
│   │       edit-form), consumer-voice (use-cases list + rating
│   │       widget), consumption (mode-badge + recent-undeclared feed),
│   │       event-port (port info + subscriptions table +
│   │       curl/WS-snippets).  Sieben neue Alpine-Factories in
│   │       `frontend/js/pages/data_product_overview_panels.js`,
│   │       registriert in `bootstrap.js`.  Drei neue REST-Routes
│   │       (`infrastructure.py`, `consumer_voice.py`,
│   │       `consumption_events.py`, `bitemporal_policy.py`).
│   │
│   ├── 134.5 — Hermes-Plugin-Tools (13 neue Tools)
│   │       Cross-Repo (`hermes-plugin-pointlessql`):
│   │       13 neue Client-Methoden auf `PointlessClient` + 13
│   │       Tool-Register-Funktionen in `tools/data_mesh_extras.py`
│   │       (lifecycle set/propose, consumption set/ack, bitemporal
│   │       get/set, infrastructure set, use-cases add/vote, rating
│   │       upsert, event-port subscribe/read/control).  Registriert
│   │       in `register_all()` via Schleife über `REGISTER_FUNCTIONS`.
│   │       10 neue pytest auf Plugin-Seite.
│   │
│   └── 134.6 — Playwright-Walkthroughs (6 .md authored)
│           Neue Walkthroughs in `docs/e2e-walkthroughs/`:
│           `data-product-lifecycle.md`,
│           `data-product-consumption-enforcement.md`,
│           `data-product-bitemporal-enforcement.md`,
│           `data-product-infrastructure.md`,
│           `data-product-consumer-voice.md`,
│           `data-product-event-port.md`.  README-Index erweitert.
│           Live-Replay-Gate deferred (autonomer Lauf ohne
│           Browser-Setup).
│
│       Asset rc179→rc180 (Plattform).  Plugin eigener Versionsraum.
│       47 neue pytest gesamt (37 Platform + 10 Plugin), full suite
│       grün, alembic 124→133 round-trip clean, ruff/pyright clean.
│
├── Phase 135-140 — Buch-Lücken-Foundation-Wave (Backend-only)  🟦 (2026-05-29)
│   │
│   │   Erste Welle des Mega-Cluster 135–146 (Buch-Vollständigkeit).
│   │   Backend-Substrat für sechs Phasen landet als ein cohesiver
│   │   Commit; Frontend / Plugin-Tools / Walkthroughs für alle sechs
│   │   bleiben für eine spätere Welle deferred.  Migration-Kette
│   │   q8s0u2w5y7a9 → z7l9n1p3r5t7 (6 neue Revisions chained).
│   │   103 neue pytest grün, ruff/pyright/check-no-phase-refs/
│   │   broad-except-hook clean.
│   │
│   ├── 135 — F3 Polysemic Entity-ID + F4 Glossary-Knowledge-Graph
│   │       Drei neue Tabellen (`data_product_entities`,
│   │       `entity_links`, `glossary_term_relations`); Service-Layer
│   │       `services/entities/_crud.py` + `_resolver.py` (BFS über
│   │       `same_as`-Graph für globale polysemische Identität);
│   │       `services/glossary/_relations.py` (Term-Relationen +
│   │       bounded knowledge-graph BFS).  Routen-Module
│   │       `data_products_routes/entities.py` +
│   │       `glossary_relations_routes.py`.  24 pytest.
│   │
│   ├── 136 — G4 Correlation-IDs + F5 ISO-8601-Enforcement
│   │       Additive Migration: `correlation_id` String(40) auf
│   │       `audit_log`, `data_product_contract_events`,
│   │       `data_product_event_deliveries` (agent_run_operations
│   │       hatte die Spalte bereits aus Phase 127); plus
│   │       `iso8601_enforcement` CHECK('off','warn','strict') auf
│   │       workspace + product policy.  `services/tracing/_context.py`
│   │       wrappt die ContextVars.  `services/governance/_iso8601.py`
│   │       parst Timestamp-Spalten gegen die ISO-8601-Grammatik;
│   │       strict-mode raised `Iso8601Violation` (PermissionDenied →
│   │       403).  POLICY_FIELDS um `iso8601_enforcement` erweitert.
│   │       8 pytest.
│   │
│   ├── 137 — D5 Graph-Queries + F2 As-of (substrate-deferred)
│   │       `services/lineage/_graph_query.py`:
│   │       find_upstream/find_downstream/find_shortest_path/
│   │       cluster_by_domain.  Routen `api/lineage_query_routes.py`
│   │       (GET upstream/downstream/path/clusters).  F2-As-of-
│   │       Substrate existiert bereits in
│   │       `pql/_time_travel.py`+`services/mesh/_point_in_time.py`
│   │       — `?as_of=`-Query-Exposure auf Routes bleibt deferred.
│   │       9 pytest.
│   │
│   ├── 138 — G1 Interval-of-Change + G2 Mesh-Health-MVP
│   │       SLO-Kind CHECK auf `data_product_slos.slo_kind`
│   │       erweitert um `interval_of_change`.  Modell-Tupel
│   │       SLO_KINDS + MEASURABLE_SLO_KINDS sync.
│   │       `services/slo/_interval_of_change.py` misst Median/p95
│   │       der Zeit zwischen aufeinanderfolgenden Writes via
│   │       `data_product_contract_events`.  G2-Mesh-Health
│   │       (`services/mesh/_health.py`) bereits MVP-vorhanden.
│   │       10 pytest.
│   │
│   ├── 139 — E10 Per-Output-Port Identity + B6 PQL-Hook-Registry
│   │       Migration: `identity_requirements` Text/JSON nullable
│   │       auf `data_product_output_ports`.
│   │       `services/governance/_port_identity.py`:
│   │       `assert_port_identity(req_json, principal)` validiert
│   │       OIDC-audiences (any-match), required scopes (all-match),
│   │       min-role rank (admin bypass).  Failure raised
│   │       `PortIdentityViolation` (PermissionDenied → 403).
│   │       `pql/_hooks.py` neue zentrale Hook-Registry
│   │       (before/after read/write) mit Test-`HookContext`
│   │       Snapshot/Restore-Helper.  19 pytest.
│   │
│   └── 140 — Runtime-Messung der 4 Decl-only SLO-Kinds
│           Migration: `last_measured_at` +
│           `last_measurement_detail_json` auf `data_product_slos`;
│           zwei neue Substrat-Tabellen
│           (`data_product_availability_probes`,
│           `data_product_query_perf_samples`).
│           `services/slo/_runtime.py` mit
│           measure_timeliness/precision_accuracy/availability/
│           performance + dispatcher.  precision/availability/
│           performance measure aus existing Snapshots/Probes;
│           timeliness gibt `unmeasured` mit Declaration-Sentinel
│           zurück (engine-side scan noch nicht gewired).
│           MEASURABLE_SLO_KINDS bleibt unverändert
│           (precision/availability/performance bekommen
│           Runtime-Messer, aber nicht alle Verdicts erreichen pass
│           ohne weitere Wiring).  12 pytest.
│
│       Asset rc180→rc186 (Plattform).  Deferred bis späterer
│       Welle: Frontend-Panels für alle 6 Phasen, Plugin-Tools,
│       Walkthroughs, Playwright-Replay, F2-`?as_of=`-Route-Exposure.
│       Phase 141–146 (Cedar Policy-as-Code, Contract-Tests,
│       DP-as-Code, Schema-Versioning, Entity-Auto-Discovery,
│       Cost+Quotas+Dashboard) bleiben für nächste Session offen.
│
├── Phase 141 — Computational Policy-as-Code via Cedar  ✅ (2026-05-30)
│   │
│   │   Substrat-Vertiefung Welle 2 des Mega-Cluster 135–146.
│   │   Cedar (AWS-Ursprung, Rust-Engine über PyO3-Bindings als
│   │   `cedarpy>=4.8`) als Policy-as-Code-Engine wegen
│   │   ABAC-Nativ-Support, Single-Process-Tauglichkeit, und
│   │   Buch-Alignment (Dehghani nennt Cedar namentlich).
│   │
│   ├── 141.1 — Migration + Models (`b9n1p3r5t7v9_phase141_cedar_policies`)
│   │       Zwei neue Tabellen `policy_modules` (workspace-scoped,
│   │       name unique, version+enabled flags, cedar_source Text)
│   │       und `policy_module_decisions` (per-eval Ledger mit
│   │       module FK, principal, action, resource_type+id, effect
│   │       CHECK('permit','forbid'), context_json, latency_ms,
│   │       indices auf module+time + principal+time).  ALTER
│   │       `workspace_governance_policies` + `data_product_policies`
│   │       add `linked_policy_module_ids` JSON-Text nullable.
│   │       POLICY_FIELDS-Tuple um neunten Eintrag erweitert
│   │       (linked_policy_module_ids inheritance product⇐workspace).
│   │
│   ├── 141.2 — Service-Paket `services/policy_as_code/`
│   │       Engine-Wrapper (cedarpy.is_authorized,
│   │       per-(module_id, version) AST-Cache mit explicit
│   │       invalidation, fail-closed bei Parse-Error
│   │       (`cedar_parse_error`) + Runtime-Error
│   │       (`cedar_runtime_error`) + Empty-Set).  Loader
│   │       (workspace-Modul-Listing + linked-modules-Resolver mit
│   │       product⇐workspace-Override-Order, disabled rows
│   │       filtered).  Translator (User::"id" Principal-UID,
│   │       Action::"verb", DataProduct::"catalog.schema" /
│   │       OutputPort::"pk" Resource-UID-Konvention).  Audit
│   │       (persist Decision + emit `policy.evaluation` Audit-Log-
│   │       Row in einem Helper).  CRUD (create+update+delete+list
│   │       Module mit IntegrityError → ValueError translation,
│   │       cedar_source-Edit bumpt version, link_modules_to_product
│   │       + _to_workspace mit JSON-Encoding).
│   │
│   ├── 141.3 — Hook-Bootstrap (Linksverschiebung)
│   │       `register_cedar_hooks(factory)` idempotent, registriert
│   │       je einen before_read + before_write hook an der
│   │       zentralen `pql/_hooks.py` Registry (Phase 139).  Beide
│   │       Hooks resolvieren `load_linked_modules_for_product`,
│   │       skippen wenn kein Modul gelinkt, sonst evaluieren via
│   │       cedar_evaluate (Action::"read" / Action::"write",
│   │       DataProduct::"<catalog>.<schema>" Resource).  Decision
│   │       wird per-Modul persistiert (emit_audit=False auf hot
│   │       read-path).  forbid raised PermissionDeniedError mit
│   │       error_class im Detail.
│   │
│   ├── 141.4 — Admin-Routes `api/admin/policy_modules.py`
│   │       GET/POST/PUT/DELETE `/api/admin/policy-modules` für
│   │       Modul-CRUD; POST `.../test` für Dry-Run mit
│   │       principal+action+resource+context Body; GET
│   │       `.../decisions` Ledger-Listing mit Pagination; PUT
│   │       `/api/data-products/{c}/{s}/policy-modules` für
│   │       Link/Unlink (steward/admin guard via load_one+role check).
│   │       Audit-Aktionen `policy_module.created/updated/deleted/
│   │       linked_to_product`.
│   │
│   └── 141.5 — Verifikation + Dokumentation
│           23 neue pytest (test_cedar_engine ×8 für
│           parse/permit/forbid/cache/empty-set/fail-closed,
│           test_cedar_translator ×6 für Principal/Action/Resource
│           UID-Helper, test_cedar_hooks ×9 für Idempotenz, unlinked-
│           passthrough, permit/forbid hook-paths, write-action,
│           parse-error fail-closed, workspace-default-link).  Full
│           suite 3842/0/10, ruff/pyright/check-no-phase-refs/
│           bare-broad-except/bare-http clean.  Alembic head
│           `b9n1p3r5t7v9`, down→up round-trip clean.  ADR-0010
│           dokumentiert die Cedar-vs-OPA/DSL-Entscheidung,
│           Fail-Closed-Rationale, und offene Follow-Ups
│           (Schema-basiertes ABAC, Cross-Workspace-Inheritance).
│
│       Asset rc186→rc187 (backbone) → rc193 (admin-surface in
│       commit `b5f5de29`) → rc197 (this closure).  Surface-Welle
│       commit `b5f5de29` shipped /admin/policy-modules (plain
│       textarea editor + dry-run dialog + decision-log dialog —
│       CodeMirror Cedar-Mode not bundled, vendor-add deferred).
│       Closure 2026-05-30: four plugin tools
│       (`pql_create_policy_module`, `pql_test_policy_module`,
│       `pql_link_policy_module_to_product`,
│       `pql_list_policy_decisions`) plus the agent-flow
│       walkthrough `computational-policy-as-code.md`
│       complementing the existing browser walkthrough
│       `admin-policy-modules.md`.
│
├── Phase 142 — Synthetic-Data + Contract-Tests  ✅ (2026-05-30)
│   │
│   │   Substrat-Vertiefung Welle 3 des Mega-Cluster 135–146.
│   │   Per-Produkt Contract-Tests + Faker-driven synthetic
│   │   fixtures als Consumer-Smoke-Test.
│   │
│   ├── 142.1 — Migration `d1p3r5t7v9x1_phase142_contract_tests`
│   │       Drei neue Tabellen: `data_product_fixtures` (Generator-
│   │       Spec pro declared Table, unique pro Produkt),
│   │       `data_product_contract_tests` (CHECK-bounded
│   │       assertion_kind in 6 Werten + severity + enabled, unique
│   │       (data_product_id, name)),
│   │       `data_product_contract_test_results` (append-only Ledger
│   │       mit CHECK status in (pass, fail, error) + Index auf
│   │       contract_test_id + run_at).  Faker>=24.0 als neue Dep.
│   │
│   ├── 142.2 — Service-Paket `services/contract_tests/`
│   │       Generator (deterministischer Arrow-Table-Builder mit 8
│   │       Generator-Kinds: email/name/int/float/iso8601_ts/choice/
│   │       uuid/bool; seed-reproducible).  Assertion-Evaluator
│   │       (row_count_range/column_present/value_distribution/
│   │       null_rate/referential/freshness; AssertionVerdict mit
│   │       status + observation dict; spec-error → status=error).
│   │       Runner (orchestriert run_contract_tests in
│   │       `synthetic`/`live` mode; live nimmt table_provider als
│   │       Closure; result row persistiert; `contract_test.run`
│   │       Audit emittiert).  CRUD (idempotente declare-by-name +
│   │       delete + paginated list für tests + fixtures + results).
│   │
│   ├── 142.3 — Routes `api/data_products_routes/contract_tests.py`
│   │       GET/POST/DELETE `.../contract-tests` + GET/POST/DELETE
│   │       `.../fixtures` mit steward/admin guard via load_one,
│   │       POST `.../contract-tests/run?mode=synthetic|live`
│   │       synchron, GET
│   │       `.../contract-tests/{id}/results?limit=&offset=`.
│   │
│   └── 142.4 — Verifikation
│           29 neue pytest (test_contract_test_generator ×8 für
│           Determinismus, kind-Coverage, JSON-spec, empty-spec;
│           test_contract_test_assertions ×15 für alle 6
│           Asserter-Pfade + error-cases; test_contract_test_runner
│           ×6 für synthetic-pass, synthetic-fail, live-no-provider,
│           live-with-provider, unknown-mode, disabled-skip).  Full
│           suite grün, alembic head `d1p3r5t7v9x1`, round-trip
│           clean.  ruff/pyright/check-no-phase-refs clean.
│
│       Asset rc187→rc188 (backbone) → rc198 (closure).  Closure
│       2026-05-30: 3 plugin tools (`pql_declare_contract_test`,
│       `pql_declare_synthetic_fixture`, `pql_run_contract_tests`)
│       wrap the per-product declare + sync-run REST surface.
│       Agent-flow walkthrough `data-product-contract-tests.md`
│       complements the Contract-Tests browser tab.  Scheduler-Kind
│       `contract_test_evaluation` already shipped via the Surface-
│       Welle Backend-Completion commit `9f9d5d32`.
│
├── Phase 143 — Data-Product-as-Code  ✅ (2026-05-30)
│   │
│   │   Substrat-Vertiefung Welle 4 des Mega-Cluster 135–146.
│   │   State-style YAML-Spec → plan → apply Reconciler ohne neue
│   │   Migration; alles Service + Routes + ADR.
│   │
│   ├── 143.1 — Spec-Model `services/data_product_as_code/_spec.py`
│   │       Strict pydantic mit `extra=forbid` auf jedem nested
│   │       Model.  `DataProductSpec` ist die Top-Wurzel mit
│   │       `protected_namespaces=()` damit `schema` als domain-Field
│   │       überlebt.  Sub-Specs: InputPortSpec, OutputPortSpec
│   │       (mit identity_requirements dict), SloSpec, PolicySpec
│   │       (alle 8 POLICY_FIELDS), EntitySpec, ContractTestSpec,
│   │       FixtureSpec, GlossaryBindingSpec.  `parse_spec` akzeptiert
│   │       YAML-text oder dict; YAML-Fehler werden zu ValueError.
│   │
│   ├── 143.2 — Planner `_planner.py`
│   │       `plan_spec(factory, spec, workspace_id) -> Plan`.
│   │       Lädt DB-State der Subentitäten, vergleicht shallow gegen
│   │       discovery-shaped dicts, emittiert ordered `Op`-Records
│   │       (additions / modifications / removals).  Op-Felder:
│   │       kind (product / output_port / input_port / slo / entity
│   │       / contract_test / fixture / policies), action (add /
│   │       update / remove), target, before, after.  SLO-unit
│   │       Auto-Resolution: wenn Spec unit=None, DB-unit wird in
│   │       desired übernommen (sonst würde KIND_META's Auto-
│   │       Assignment jeden Apply zu modification ops machen).
│   │
│   ├── 143.3 — Applier `_applier.py`
│   │       `apply_plan(factory, spec, plan, dry_run=False) ->
│   │       ApplyOutcome` mit Idempotenz-Garantie.  Top-Level
│   │       `_ensure_product` upsertet `DataProduct`-Row.  Pro Op
│   │       eine `_apply_<kind>` Routine, die existierende CRUD-
│   │       Helpers nutzt: `create_output_port`,
│   │       `create_input_port`, `declare_slo`, `declare_entity`,
│   │       `declare_contract_test`, `declare_fixture`,
│   │       `set_product_policy`.  Keine direct ORM-writes.
│   │       Fehler werden in outcome.errors gesammelt, keine
│   │       partial-failure-Rollback (idempotent-on-retry ist die
│   │       Recovery-Story).
│   │
│   ├── 143.4 — Exporter `_exporter.py`
│   │       `export_data_product(factory, catalog, schema) ->
│   │       DataProductSpec`.  Snapshots live DB-State in Spec für
│   │       Round-Trip `apply → export → plan` ergibt no-op Plan.
│   │       LookupError bei unbekanntem Produkt.
│   │
│   ├── 143.5 — Routes `api/data_products_routes/apply.py`
│   │       POST `/api/data-products/plan` (any-user, dry-run only).
│   │       POST `/api/data-products/apply?dry_run=` (steward/admin
│   │       guard auf existing product; admin bypass).  POST
│   │       `/api/data-products/{c}/{s}/export` (any-user).
│   │       Body akzeptiert `{spec_yaml: "..."}` oder
│   │       `{spec: {...}}` oder direct dict.  Audit:
│   │       `data_product.apply` mit `{dry_run, op_count, applied,
│   │       errors}`.
│   │
│   └── 143.6 — Verifikation + ADR
│           16 neue pytest (test_dp_as_code_spec ×6 für strict-
│           extra-rejection, blank-name, YAML-parse, round-trip-
│           dump; test_dp_as_code_planner_applier ×10 für empty-DB-
│           add-all, apply-creates-product-and-subentities, dry-run-
│           no-write, idempotent-on-repeat, removal-op-emit,
│           modification-op-emit, export-round-trip-noop, export-
│           unknown-raises-LookupError, policies-apply-writes-row,
│           policies-export).  ruff/pyright/check-no-phase-refs
│           clean.  ADR-0011 dokumentiert state-vs-migration-style-
│           Wahl, strict-spec-Rationale, applier-reuses-CRUDs-
│           Prinzip, offene Follow-Ups (CLI, glossary bindings als
│           eigene op-kind).
│
│       Asset rc188→rc189 (backbone) → rc199 (closure).  Closure
│       2026-05-30: `pql_data_product_plan` + `pql_data_product_apply`
│       shipped via Surface-Welle batch; this closure lands the
│       missing `pql_data_product_export` so the round-trip story
│       (plan → apply → export → plan-noop) holds end-to-end.
│       Agent-flow walkthrough `data-product-as-code.md` replays
│       the eight-step authoring flow.  Admin-Surface
│       `/admin/data-product-apply` already shipped in commit
│       `b5f5de29`.  CLI (`pql apply / plan / export` via Typer)
│       stays deferred — agents prefer the tool surface, the
│       browser surface covers humans, and a CLI duplicates both.
│
├── Phase 144 — Schema-Contract-Versioning  ✅ (2026-05-30)
│   │
│   │   Substrat-Vertiefung Welle 5 des Mega-Cluster 135–146.
│   │   Output-Ports bekommen MAJOR.MINOR.PATCH-Versionierung +
│   │   automatische Breaking-Change-Erkennung; Migration wechselt
│   │   für die zwei Policy-Tabellen auf SQLite batch_alter_table.
│   │
│   ├── 144.1 — Migration `f3r5t7v9x1z3_phase144_schema_versioning`
│   │       Add `version_semver` String(16) NOT NULL default
│   │       "0.1.0" auf `data_product_output_ports`.  Neue Tabelle
│   │       `output_port_schema_versions` (port FK + version_semver
│   │       + schema_json + CHECK change_kind in (major,minor,patch)
│   │       + change_summary + bumped_at + unique (port_id,
│   │       version_semver) + index port+bumped_at).  ALTER
│   │       workspace + product policy add `breaking_change_policy`
│   │       String(8) CHECK ('block','warn','off') via
│   │       batch_alter_table (SQLite).
│   │
│   ├── 144.2 — Service-Paket `services/schema_versioning/`
│   │       Diff (`compute_diff` mit deterministischen Regeln:
│   │       removed/narrowed/not-null-tightened/added-not-null →
│   │       MAJOR; added-nullable → MINOR; description-only → PATCH;
│   │       no-op → NONE; NARROWING_PAIRS Tabelle listet die
│   │       erkannten Type-Narrowings).  Bumper
│   │       (`propose_bump(current, diff) -> (next_semver, kind)`
│   │       via packaging.Version, no-op gibt current zurück).
│   │       Enforcer (`assert_schema_compatibility` resolved port,
│   │       lädt prior schema, computed diff, raised
│   │       `SchemaBreakingChangeError` (PermissionDeniedError →
│   │       403) bei block+major; warn gibt EnforcementOutcome zurück;
│   │       off skippt sofort).  CRUD (`bump_port_version` persistiert
│   │       History-Row + advanced port.version_semver in einer
│   │       Transaction; no-op-diff = kein Insert).
│   │
│   ├── 144.3 — Models + POLICY_FIELDS
│   │       `OutputPortSchemaVersion` Model + Konstanten
│   │       `CHANGE_KINDS` (major/minor/patch) + `BREAKING_CHANGE_POLICIES`
│   │       (block/warn/off).  POLICY_FIELDS um `breaking_change_policy`
│   │       erweitert (jetzt 9 Felder, product⇐workspace inheritance
│   │       unverändert).  `version_semver` Column auf
│   │       DataProductOutputPort.
│   │
│   ├── 144.4 — Routes `api/data_products_routes/schema_versions.py`
│   │       GET `.../output-ports/{port_id}/versions` (any-user)
│   │       History-Listing newest-first.  POST `.../bump`
│   │       (steward/admin) Body `{schema, change_summary}` →
│   │       bumped row + diff.  GET `.../diff?from_version=&to_version=`
│   │       für beliebige Version-Paar-Diffs.
│   │
│   └── 144.5 — Verifikation
│           22 neue pytest (test_schema_diff ×12 für alle
│           Klassifikations-Regeln + collapse-to-strongest +
│           edge-cases; test_schema_enforcer ×10 für propose_bump
│           kinds, block-raise, warn-outcome, off-noop, no-port,
│           port-semver advance, no-op-idempotent).  Alembic head
│           `f3r5t7v9x1z3`, down→up round-trip clean.
│           ruff/pyright/check-no-phase-refs clean.
│
│       Asset rc189→rc190 (backbone) → rc200 (closure).  Closure
│       2026-05-30: 3 plugin tools (`pql_get_schema_version_history`,
│       `pql_propose_schema_bump`, `pql_compute_schema_diff`) wrap
│       the per-port history + bump + diff REST surface.  Agent-flow
│       walkthrough `output-port-schema-versioning.md` covers the
│       MINOR / MAJOR / PATCH classification flow.  before_write
│       Hook-Integration already shipped via the Surface-Welle
│       Backend-Completion commit `9f9d5d32`.  Output-Port-Detail
│       History-Liste + Diff-Viewer + Workspace-Governance-Selektor
│       remain a future browser-surface follow-up.
│
├── Phase 145 — Auto-Discovery Entity-Links  ✅ (2026-05-30)
│   │
│   │   Substrat-Vertiefung Welle 6 des Mega-Cluster 135–146.
│   │   Auto-Discovery von Entity-Link-Candidates plus
│   │   Steward-Review-Queue auf dem Phase-135-Substrat.
│   │
│   ├── 145.1 — Migration `h5t7v9x1z3b5_phase145_entity_link_candidates`
│   │       Neue Tabelle `entity_link_candidates` mit source +
│   │       target FKs auf `data_product_entities`, CHECK kind in
│   │       (same_as, derives_from), CHECK decision NULL or in
│   │       (accepted, rejected, deferred) (NULL = pending),
│   │       confidence_score Numeric(3,2), evidence_json Text NOT
│   │       NULL, discovered_at + optional reviewed_at +
│   │       reviewed_by_user_id FK.  UNIQUE(source, target, kind)
│   │       verhindert Duplikate auf scheduler-Ticks; Index auf
│   │       (decision, confidence) für pending-Queue-Sortierung.
│   │
│   ├── 145.2 — Service-Erweiterung von `services/entities/`
│   │       `_candidates.py`: score_pk_overlap via Jaccard auf
│   │       PK-Column-Set, score_column_similarity via
│   │       Token-Overlap nach snake/CamelCase-Splitting,
│   │       score_combined als 60/40 gewichtete Summe, NumPy-frei.
│   │       discover_candidates(workspace, threshold=0.7) scant
│   │       alle Entity-Paare desselben Workspace, persistiert
│   │       Candidates über Threshold, dedup gegen existing
│   │       entity_links + bestehende entity_link_candidates via
│   │       UNIQUE-Constraint.  `_review_queue.py`:
│   │       list_pending_candidates sortiert nach confidence desc;
│   │       accept_candidate promotes via existing link_entities-
│   │       Helper (single source of truth); reject/defer stempeln
│   │       decision + reviewed_at; double-decision raised
│   │       ValueError.
│   │
│   ├── 145.3 — Routes `api/data_products_routes/entity_candidates.py`
│   │       GET `/api/entity-link-candidates?status=pending|...&limit=&offset=`
│   │       (any-user), POST `.../accept`, `.../reject`, `.../defer`
│   │       (admin), POST `/api/admin/entity-discovery/run-now`
│   │       (admin) → synchron-trigger.  Conflict-Mapping: 409 für
│   │       already-decided, 404 für unknown candidate.
│   │
│   └── 145.4 — Verifikation
│           19 neue pytest (test_entity_candidate_scoring ×11 für
│           Jaccard-pk-overlap edge-cases incl. disjoint+partial,
│           column-similarity tokenisation, combined-weighted-sum,
│           threshold-cutoff, dedup-against-links, dedup-against-
│           candidates; test_entity_review_queue ×8 für pending-
│           only-list, accept-promotes-to-EntityLink, reject-no-
│           link, defer-separate-filter, double-decision-ValueError,
│           unknown-LookupError, sort-by-confidence, pagination).
│           Alembic head `h5t7v9x1z3b5`, down→up round-trip clean.
│           ruff/pyright/check-no-phase-refs clean.
│
│       Asset rc190→rc191 (backbone) → rc201 (closure).  Closure
│       2026-05-30: 3 plugin tools (`pql_accept_entity_link_candidate`,
│       `pql_reject_entity_link_candidate`,
│       `pql_defer_entity_link_candidate`) close the agent-side of
│       the steward review queue.  `pql_list_pending_entity_link_candidates`
│       already shipped via the Surface-Welle batch.  Agent-flow
│       walkthrough `entity-link-discovery.md` covers the eight-
│       step list → inspect → accept → re-list → reject → defer →
│       409-conflict → run-now flow.  Scheduler-Kind
│       `entity_link_discovery` + Admin-Surface
│       `/admin/entity-discovery` already shipped in commits
│       `9f9d5d32` / `b5f5de29`.
│
├── Phase 146 — Cost-Attribution + Quotas + Mesh-Health-Dashboard  ✅ (2026-05-30)
│   │
│   │   Substrat-Vertiefung Welle 7 + finale Substrat-Phase des
│   │   Mega-Cluster 135–146.  Per-product/per-consumer cost-
│   │   attribution + 429-style quota-enforcement + voll
│   │   mesh-health-dashboard auf einer cohesiven Substrat-Welle.
│   │
│   ├── 146.1 — Migration `j7v9x1z3b5d7_phase146_cost_and_quotas`
│   │       Zwei neue Tabellen: `data_product_query_cost` (raw
│   │       per-query meter mit started/completed/duration, cost
│   │       Numeric, bytes/rows BigInt, table_list_json,
│   │       attribution principal_user/api_key/authoring_product/
│   │       consumer_product, query_kind, error_class; Indices auf
│   │       started_at, authoring+started, principal+started) und
│   │       `data_product_cost_buckets_hourly` (hourly rollup mit
│   │       UNIQUE(bucket_hour, data_product, consumer_user) für
│   │       idempotente re-runs; Index auf bucket_hour).  ALTER
│   │       workspace + product policy via SQLite batch_alter_table
│   │       add max_cost_per_day Numeric(10,2), max_queries_per_hour
│   │       Integer, quota_enforcement String(8) CHECK in
│   │       (off,warn,strict).  Workspace default 'off'; product
│   │       override nullable.
│   │
│   ├── 146.2 — Models + Exception + POLICY_FIELDS
│   │       `DataProductQueryCost` + `DataProductCostBucketHourly`
│   │       Models mit Konstanten `QUERY_KINDS` + `QUOTA_ENFORCEMENT_MODES`.
│   │       Neue Exception `QuotaExceededError(PointlessSQLError)` mit
│   │       status_code=429 und ErrorCode.QUOTA_EXCEEDED; carries
│   │       metric, limit, observed, consumer_id, data_product_id
│   │       als Extension-Members für strukturierte Envelope.
│   │       POLICY_FIELDS um die drei neuen Felder erweitert (jetzt
│   │       12 Felder, product⇐workspace inheritance unverändert).
│   │       PolicySpec (Phase 143) bekommt die drei neuen Felder.
│   │
│   ├── 146.3 — Service-Paket `services/cost/`
│   │       Meter (record_query_cost + MeterContext dataclass mit
│   │       allen Attribution-Feldern; tabular row insert).  Quota
│   │       (check_quota + resolve_quota_mode aggregieren current-
│   │       day + current-hour aus bucket-table mit
│   │       timezone-aware `_same_hour` helper für SQLite-Read-Path;
│   │       off=no-op, warn=outcome only, strict=raise
│   │       QuotaExceededError).  Rollup (roll_up_hourly_buckets
│   │       aggregiert raw rows in buckets; idempotent via
│   │       UPSERT-pattern, skippt rows ohne authoring_product).
│   │       Dashboard (cost_by_product + cost_by_consumer als
│   │       window-Aggregatoren mit configurable since/until; sort
│   │       nach cost desc / query_count desc; mesh_health_full
│   │       layered auf existing services.mesh.mesh_health mit
│   │       per_domain SLO-Bänder + cost_trend last-7d + top_consumers
│   │       cap 10 + recent_deliveries shape).
│   │
│   ├── 146.4 — Routes `api/admin/cost_routes.py`
│   │       GET `/api/mesh/health/full` (any-user) für comprehensive
│   │       Dashboard payload.  GET `/api/cost/by-product?since=&until=`
│   │       (steward/admin guard) für per-product rollup.  GET
│   │       `/api/cost/by-consumer?since=&until=` (admin only).
│   │       PUT `/api/admin/governance/quota` (admin) für Workspace-
│   │       Default-Quotas mit Audit `governance.workspace_quota_set`.
│   │       Window-parameter best-effort ISO-8601 parse mit
│   │       BadRequestError bei malformed input.
│   │
│   └── 146.5 — Verifikation + ADR
│           21 neue pytest (test_cost_meter ×3 für persistence +
│           no-attribution + float-input; test_cost_quota ×8 für
│           off/warn/strict modes, cost+queries breach, below-
│           limit-pass, stale-hour-skip, resolve-mode-default,
│           override-respect; test_cost_rollup ×3 für creates-
│           bucket, idempotent-on-rerun, skips-no-authoring;
│           test_mesh_health_full ×7 für sums-buckets, groups-by-
│           user, base-payload-shape, per-domain-bucket-shape,
│           time-window, empty-workspace, top-consumers-truncated-
│           to-ten).  Alembic head `j7v9x1z3b5d7`, down→up round-
│           trip clean.  ruff/pyright/check-no-phase-refs clean.
│           ADR-0012 dokumentiert raw+rollup split, estimated-vs-
│           real cost trade-off, off/warn/strict inheritance,
│           offene Follow-Ups (engine-side cost integration,
│           ledger-retention, cache TTL, SQL-side aggregation).
│
│       Asset rc191→rc192 (backbone) → rc202 (closure).  Closure
│       2026-05-30: 2 plugin tools (`pql_cost_by_consumer`,
│       `pql_set_workspace_quota`) close the cost + quota agent
│       surface.  `pql_mesh_health_full` + `pql_cost_by_product`
│       already shipped via the Surface-Welle batch; the per-product
│       quota field-set rides on the existing
│       `pql_set_data_product_policy` since the three quota fields
│       are part of POLICY_FIELDS.  Two agent-flow walkthroughs
│       `mesh-cost-dashboard.md` (read flow) and
│       `product-quota-enforcement.md` (set → breach → 429 flow).
│       `pql/_hooks.py` before_read check_quota integration,
│       Scheduler-Kind `cost_rollup_hourly`, and Admin-Page
│       `/admin/mesh-dashboard` already shipped in commits
│       `9f9d5d32` / `b5f5de29`.  services/lens/cost_gate.py
│       meter-hook also wired via the Backend-Completion commit.
│
├── Surface-Welle 135–146 Backend-Completion + Admin-Surfaces  ✅ (2026-05-30)
│   │
│   ├── Backend-Completion — `9f9d5d32`.  Schließt die Dormant-
│   │   Substrate-Lücke aus Phase 141–146: zwei neue `_bootstrap.py`
│   │   (`services/cost`, `services/schema_versioning`) registrieren
│   │   die before-read + before-write Hooks; alle drei
│   │   `register_*_hooks(factory)` werden idempotent aus
│   │   `api/_bootstrap/_lifespan.py` neben dem api-keys Bootstrap
│   │   aufgerufen.  `services/lens/tools/query.py` schreibt
│   │   `data_product_query_cost` nach dem Cost-Gate (und auf
│   │   Gate-Rejection mit `error_class`).  `build_default_registry`
│   │   bekommt `cost_rollup_hourly`, `contract_test_evaluation`,
│   │   `entity_link_discovery` — jeweils dünne Executors über die
│   │   bestehende Service-Surface, keiner default-cron-scheduled.
│   │   Discovery-Envelope ergänzt: 5 Policy-Felder
│   │   (`iso8601_enforcement`, `linked_policy_module_ids`,
│   │   `breaking_change_policy`, `quota_enforcement`,
│   │   `max_cost_per_day`, `max_queries_per_hour`),
│   │   per-port `version_semver` + `schema_history`, und 4 Top-
│   │   Level-Blöcke (`policy_modules`, `contract_tests`,
│   │   `fixtures`, `cost`).  Neu:
│   │   `GET /api/data-products/{c}/{s}/point-in-time-read?as_of=`
│   │   als Query-String-Pendant zum POST.  15 neue pytests.
│   │
│   ├── Admin-Surfaces — `b5f5de29`.  Vier neue Admin-Seiten exposen
│   │   das Substrat operativ.  Jede ist Alpine-Page + page-level JS
│   │   Factory + HTML-Render-Route auf dem existierenden Admin-
│   │   Router + Karte auf `/admin`:
│   │   * `/admin/policy-modules` — Cedar Module CRUD + Dry-Run
│   │     Dialog + Decision-Log Dialog (plain textarea, kein
│   │     CodeMirror).
│   │   * `/admin/mesh-dashboard` — Vital-Signs Cards (Products /
│   │     Green / Red / Total Cost) + Cost-by-Product + Top-
│   │     Consumers für 7-Tage-Window.
│   │   * `/admin/entity-discovery` — Pending Same-As Queue mit
│   │     Accept / Reject / Defer + Run-Now-Button.
│   │   * `/admin/data-product-apply` — YAML-Textarea + Plan /
│   │     Apply Buttons + Plan-Diff + Outcome-Viewer.
│   │   8 neue pytests (Render-Smoke + Non-Admin-Gate).
│   │
│   │   Asset rc192→rc193.  Full pytest 3972/0/10.
│   │
│   │   Deferred (separate Commits): ~28 Plugin-Tools im
│   │   hermes-plugin-pointlessql, 16 Walkthroughs für die einzelnen
│   │   Phase-Surfaces, Frontend-Detail-Polish (Chart.js Cost-Trend-
│   │   Line, Cytoscape Term-Graph-Drawer, CodeMirror Cedar-Mode,
│   │   F2 `?as_of=` Picker im SQL-Editor + Preview + Export).
│
├── Mega-Cluster 147–154 — Visual Data Product Editor  ✅ shipped (local, 2026-05-31)
│   │
│   │   KNIME / Simulink / STEP-7-FUP-style Block-and-Wire-Editor
│   │   zum Authoring von Data Products. Jeder Block hat typisierte
│   │   Input-/Output-Pins, Compound-Blöcke (= DPs) verschachteln
│   │   sich Simulink-Subsystem-Stil, Graph kompiliert zu DuckDB-SQL
│   │   auf der existierenden Query-Engine.
│   │
│   │   Vision: Domänen-Teams legen DPs visuell selbst an, ohne
│   │   Notebook oder Roh-SQL. Schließt das Phase-85-Decision-Gate
│   │   ("KEIN 2D-Canvas bis User-Pain real") — Pain ist mit der
│   │   Mesh-Initiative (Phase 124-140) explizit geworden.
│   │
│   │   Stack-Entscheidung: Rete.js (TypeScript, MIT, framework-
│   │   agnostisch — Alpine-mount-Pattern wie CodeMirror im
│   │   Notebook-Editor). Co-Edit Wave G recycelt Phase-105 Y.js-
│   │   Infrastruktur. Detail-Plan unter
│   │   `~/.claude/plans/lege-die-phasen-f-r-immutable-oasis.md`.
│   │
│   │   Jede Wave A-H bekommt vor Implementation eigenen Plan-File
│   │   mit detaillierten Sub-Phase-Plänen.
│
├── Phase 147 — Visual DP Editor: Compiler Backbone (Wave A)  ✅ shipped (local, 2026-05-31)
│   │
│   │   Backend-Foundation für den visuellen DP-Editor. Block-Graph
│   │   → DuckDB-SQL via topologischer Sort + CTE-Chain-Compiler.
│   │   Backend zuerst, damit Wave B gegen echte Compile-Execute-
│   │   Pipeline arbeitet statt Mocks. Neues
│   │   `pointlessql/services/dp_canvas/` Service-Package
│   │   (`_types` + `_blocks` + `_compiler` + `_schema_flow` +
│   │   `_executor` + `_storage`), 8 Atom-Blöcke, neue
│   │   Alembic-Rev `l9x1z3b5d7f9` (Tabelle `data_product_canvas_graph`
│   │   + CHECK-Erweiterung um `canvas_materialize`),
│   │   neuer `OpName.CANVAS_MATERIALIZE` Enum-Wert mit Lineage-
│   │   Branch in `emit_lineage_after_commit` (multi-input via
│   │   `params["referenced_tables"]`). Executor: compile → DuckDB-
│   │   Execute → Delta-Materialize → UC-OutputPort-Register →
│   │   Graph-Version. 44 neue pytest (compile + schema-flow +
│   │   per-Block-spec + end-to-end Executor mit echtem Delta +
│   │   Lineage-Captures). Asset rc204→rc205.
│   │
│   ├── 147.1 — Alembic-Migration `data_product_canvas_graph`
│   │       Neue Tabelle `dp_id` FK auf data_products, `version` int,
│   │       `document` JSON, `author_user_id`, `created_at`. Eine
│   │       Zeile pro gespeicherter Graph-Version (Versioning-
│   │       Substrat für Phase 154.1).
│   │
│   ├── 147.2 — Block-Type-Registry + Pin-Type-System
│   │       `services/dp_canvas/_blocks.py` mit initialen 8 Atom-
│   │       Blöcken: InputPort, Filter, Project, Join, GroupBy,
│   │       Limit, SQL (escape-hatch), OutputPort. Pin-Type-System
│   │       v1: nur TableRef (Schema = [(col, duckdb_type, nullable),
│   │       ...]). Erweiterungspunkte für ScalarValue/ModelRef/etc.
│   │       in v2+ vorgesehen.
│   │
│   ├── 147.3 — Compiler v1
│   │       `services/dp_canvas/_compiler.py` mit topologischem Sort
│   │       + CTE-Kettengenerierung. Jeder Block hat `compile(inputs,
│   │       cfg) → SQLFragment`. Pattern-Referenz (nicht reused):
│   │       existierender linearer Compiler
│   │       `services/canvas/_compiler.py:compile_nodes`.
│   │
│   ├── 147.4 — Schema-Flow-Validator
│   │       `services/dp_canvas/_schema_flow.py` propagiert Output-
│   │       Pin-Schemas vorwärts durch den Graph, gibt Edit-Zeit-
│   │       Typfehler als strukturiertes Payload zurück. Wird in
│   │       148.3 als rote Wires + Validierungs-Badges gerendert.
│   │
│   └── 147.5 — Executor + Materialize-Wiring + Verifikation
│           `services/dp_canvas/_executor.py` orchestriert: Compile
│           → reuse `api/sql/editor/_helpers.py:run_sql_sync` für
│           Query-Exec → reuse `pql/_write.py:write_table` für
│           Materialize → reuse
│           `services/data_product_ports/_crud.py:create_output_port`
│           für Port-Registration → reuse
│           `services/agent_runs/operations/_lineage.py:emit_lineage_after_commit`
│           für Lineage. 25+ neue pytest für compile+execute round-
│           trip; lineage edges emittiert; OutputPort registriert
│           in soyuz; alembic upgrade/downgrade clean.
│
├── Phase 148 — Visual DP Editor: Frontend Editor (Wave B)  ✅ shipped (local, 2026-05-31)
│   │
│   │   Standalone full-screen editor at `/dp/{id}/canvas` mit Drawflow-
│   │   block-and-wire-Canvas, 8 Block-Palette + Drag-to-Canvas + Auto-
│   │   Save + Edit-Zeit-Validierung + Per-Block-Config-Forms + Run-
│   │   Modal mit Materialize-Pipeline. Library-Choice deviation:
│   │   Drawflow statt Rete.js v2 (Rete v2 fordert Vue/React/Lit-Render-
│   │   Plugin; Drawflow ist single-file UMD + vanilla DOM, passt
│   │   sauber in den build-step-losen Alpine-Stack).
│   │
│   ├── 148.1 — Routes + Drawflow-Mount + Empty Editor Page
│   │       Neuer `data_products_routes/canvas.py` mit 5 Routes
│   │       (GET/POST/versions/validate/materialize) unter
│   │       `/api/dp/{dp_id}/canvas`. Neuer HTML-Router
│   │       `api/dp_canvas_html_routes.py` rendert
│   │       `frontend/templates/pages/dp_canvas_editor.html`. Alpine-
│   │       Factory `dpCanvasEditor()` in `frontend/js/pages/`.
│   │       Canvas-Tab im DP-Detail-Page lazy-loadet die Version-
│   │       Liste und linkt auf das standalone Editor-Page.
│   │
│   ├── 148.2 — Block-Palette + Drag-to-Canvas + Save Round-Trip
│   │       Sidebar-Palette mit den 8 Atom-Blöcken aus Wave A.
│   │       HTML5-drag/drop API von der Palette auf das Drawflow-
│   │       Canvas. Auto-Save (debounced 1500 ms) + manuelles
│   │       Save-Button mit optimistic-concurrency expected_base_
│   │       version. Connection-Drawing via Drawflow built-in.
│   │
│   ├── 148.3 — Pin-Type-Rendering + Edit-Zeit-Validierung
│   │       `POST /api/dp/{id}/canvas/validate` resolved jede
│   │       InputPort-FQN gegen soyuz, propagiert Pin-Schemas durch
│   │       den DAG, retourniert pin_schemas + CompileError-Liste.
│   │       Editor rendert Per-Node-Error-Badges + Status-Bar mit
│   │       klickbarer Error-Liste. Debounced 800 ms nach Mutation.
│   │
│   ├── 148.4 — Per-Block-Config-Forms
│   │       Rechte Drawer mit block-type-spezifischen Alpine-Forms
│   │       für alle 8 Block-Types (InputPort/Filter/Project/Join/
│   │       GroupBy/Limit/SQL/OutputPort). Project + Join + GroupBy
│   │       mit chip-input für Spalten-Listen; GroupBy mit dynamic
│   │       aggregation-rows; OutputPort mit conditional merge_on
│   │       wenn mode=merge.
│   │
│   └── 148.5 — Materialize-Button + Skeleton-Walkthrough
│           "Run ▶"-Button öffnet Modal mit Target-Preview, ruft
│           `POST /api/dp/{id}/canvas/materialize` (compile → execute_
│           canvas → write Delta → register OutputPort → save graph
│           version). Erfolg-Banner zeigt rows_written + target_fqn
│           + graph_version. Neuer Walkthrough
│           `docs/e2e-walkthroughs/dp-canvas-builder.md` mit Setup-
│           Block (2 UC-Tabellen + leerer DP) + Browser-Flow-Tabelle
│           + Agent-Flow (httpx-Snippet).
│
├── Phase 149 — Visual DP Editor: Live Preview + Expression Editor (Wave C)  ✅ shipped (local, 2026-05-31)
│   │
│   │   Per-Node-Preview macht Edit-Loop konkret; CodeMirror mit
│   │   DuckDB-Grammar + Spalten-Autocomplete macht Filter und
│   │   SQL-Blöcke produktiv editierbar; SQL-Block schema-inference
│   │   per DuckDB DESCRIBE entlockt downstream Pin-Typen.
│   │
│   ├── 149.1 — Per-Node-Preview-Endpoint
│   │       `POST /api/dp/{id}/canvas/preview` (Body trägt aktuell
│   │       editiertes Document; POST statt GET damit der dirty in-
│   │       memory Doc ohne URL-Encoding mitkommt). Service-helper
│   │       `_preview.preview_until` macht Doc-Slice via reverse-BFS
│   │       upstream-of-upto-node, injiziert synthetischen OutputPort,
│   │       compiliert über bestehendes `compile_canvas`, rendert SQL
│   │       gewrappt in `SELECT * FROM (…) LIMIT N`, registriert Delta-
│   │       Views via existing `register_delta_view`, fetcht rows. Read-
│   │       only — kein Delta-write, kein Version-bump. Frontend:
│   │       "Preview"-Button im config-drawer + Modal mit
│   │       columns/rows-Tabelle + truncation-Badge + "Compiled SQL"
│   │       details. Bonus-fix: pyright `reportUnnecessaryCast` error
│   │       in `_raw_soyuz_client` (Phase 148 closure miss).
│   │
│   ├── 149.2 — CodeMirror DuckDB-Grammar-Editor
│   │       Neues `frontend/js/dp_canvas/codemirror_predicate.js` mit
│   │       `mountPredicateEditor` (single-line, Enter swallowed) +
│   │       `mountSqlEditor` (multi-line, line-numbers, history).
│   │       Beide nutzen den existing `@codemirror/lang-sql` +
│   │       `@codemirror/autocomplete` aus dem base.html-importmap.
│   │       Spalten-Autocomplete via custom CompletionSource +
│   │       `upstreamColumns(nodeId)` aus 148.4. Filter und SQL
│   │       config-forms wechseln von `<textarea>` auf `<div>`-mounts.
│   │
│   └── 149.3 — Schema-Inferenz für raw SQL-Block
│           `_infer_sql` in `_blocks.py` macht jetzt einen DuckDB
│           DESCRIBE round-trip: temp-table mit upstream-Spalten +
│           {{in}}→table-name rewrite + `DESCRIBE (rewritten)`. Fail-
│           graceful: ohne upstream → unknown schema; DuckDB-parse-
│           error → `CompileError(kind="bad_config")`. Downstream
│           Blöcke (Project chip-input z.B.) sehen jetzt SQL-Output-
│           Spalten und können autocomplete bedienen.
│
├── Phase 150 — Visual DP Editor: Hierarchy / Compound-Blocks (Wave D)  ✅ shipped (local, 2026-05-31)
│   │
│   │   Simulink-Subsystem-Level. Closes-the-loop für die "fetter
│   │   Block = DP"-Metapher. Mesh-Canvas wird editierbar.
│   │
│   ├── 150.1 — DataProduct compound block
│   │       Neuer `"DataProduct"` Block im `BLOCK_REGISTRY` mit config
│   │       `{dp_id, port_name, materialized_table}`. Compiler emittiert
│   │       `SELECT * FROM <materialized_table>` (gleiche shape wie
│   │       InputPort). Route-Layer hat einen Save/Validate/Materialize
│   │       pre-pass `_resolve_dp_refs` der die `materialized_table` aus
│   │       `DataProductOutputPort.location` ableitet — Compiler bleibt
│   │       pure. Frontend BLOCK_DEFS mit eigenem Icon (DP◫), config-
│   │       form mit DP-Picker-Dropdown + Port-Picker (gefüttert von
│   │       neuer `GET /api/dp/_picker` Route).
│   │
│   ├── 150.2 — Drill-in-Navigation + Breadcrumb
│   │       Doppelklick auf DP◫ → `window.location.href = /dp/{id}/canvas`.
│   │       Breadcrumb-Trail im localStorage (`pql.dp_canvas.breadcrumb`,
│   │       max 6 Einträge), Topbar zeigt "◀◀ <previous-DP>"-Button der
│   │       den Stack pop't.
│   │
│   ├── 150.3 — Editierbarer Mesh-Level-Canvas
│   │       Neue Routes `GET/POST /api/mesh/canvas` + `POST /validate`
│   │       (`pointlessql/api/mesh_canvas_routes.py`) + Service
│   │       `pointlessql/services/mesh/_canvas.py` mit MeshCanvasDoc
│   │       (nodes = DPs, edges = upstream-bindings). Save macht einen
│   │       Diff gegen aktuelle ``upstream_product``-Port-Rows: neue
│   │       Edges → `create_input_port`, fehlende → `delete_input_port`.
│   │       Eigene Editor-Seite `/mesh/canvas` mit Drawflow-mount,
│   │       links Status-Panel mit Last-Diff-Summary, rechts Issues-
│   │       Liste. Nur Edges sind editierbar; Nodes read-only (DP-
│   │       Katalog wird auf eigener Surface authored).
│   │
│   └── 150.4 — Zwei-Level-Walkthrough + Verifikation
│           Walkthrough-Sektion in `dp-canvas-builder.md` deckt: Leaf-DP
│           bauen → materialise → Mesh-Canvas öffnen → DP◫ in zweitem
│           DP wiren → save → run. Playwright-MCP Browser-Replay als
│           Gate für Wave-D-Commit.
│
├── Phase 151 — Visual DP Editor: Block Library Expansion (Wave E)  ✅ shipped (local, 2026-05-31)
│   │
│   │   10 neue Transform-Primitiven dazu (BLOCK_REGISTRY 9 → 19):
│   │   Window, Pivot, Unpivot, Union, Distinct, Sort, Sample, Cast,
│   │   Rename, CalcColumn.
│   │
│   ├── 151.1 — Window
│   │       `{partition_by, order_by, function, target_alias, args}`,
│   │       Funktionen ROW_NUMBER/RANK/DENSE_RANK/LAG/LEAD/SUM/AVG/MIN/
│   │       MAX/COUNT. Compiler emittiert OVER-Klausel; Schema-Inferenz
│   │       fügt alias-Spalte mit BIGINT (für ranks/count) sonst DOUBLE.
│   │
│   ├── 151.2 — Pivot + Unpivot
│   │       DuckDB PIVOT-Statement-Wrapping (sum/avg/min/max/count/
│   │       count_distinct). Unpivot mit NAME/VALUE-labels.  Pivot
│   │       gibt Dynamic-Column-Set zurück (unknown=True downstream);
│   │       Unpivot weiß die exakte Spaltenliste nach dem unpivot.
│   │
│   ├── 151.3 — Union + Distinct + Sort + Sample
│   │       Union: 2-input (`left`+`right`) + UNION ALL toggle +
│   │       schema-mismatch error. Distinct: SELECT DISTINCT mit
│   │       optional `ON ({cols})`. Sort: ORDER BY mit list[OrderSpec]
│   │       (strings oder `{column, direction}` objects). Sample:
│   │       USING SAMPLE N PERCENT oder USING SAMPLE N ROWS.
│   │
│   └── 151.4 — Cast + Rename + CalcColumn
│           Cast: pro-Spalte `::TYPE`-coercion (validate target_type ∈
│           DuckDB-types). Rename: `{old: new}` mapping. CalcColumn:
│           `{expression, target_alias}` mit CodeMirror-mount aus
│           149.2 reused. Tests: 11 neue pytest.
│
├── Phase 152 — Visual DP Editor: DP-as-Code Round-Trip (Wave F)  ✅ shipped (local, 2026-05-31)
│   │
│   │   Bridge Visual-Editor ↔ YAML-DP-Spec. Macht Canvas-DPs
│   │   vollständig Git-fähig + zeigt Diffs zwischen gespeicherten
│   │   Versionen.
│   │
│   ├── 152.1 — Serializer Canvas → YAML (structured sub-tree)
│   │       Neues `CanvasPipelineSpec` Pydantic-Model in
│   │       `services/data_product_as_code/_canvas_pipeline.py` mit
│   │       `{version: 1, nodes: [...], edges: [...]}` shape.
│   │       Optionales `pipeline:` Feld auf `DataProductSpec`.
│   │       Export-Pfad (`_exporter.py`) ruft `from_canvas_doc` mit
│   │       der latest saved `data_product_canvas_graph` Row.
│   │       **ADR-Entscheidung:** structured YAML statt embedded-JSON-
│   │       String — git-diffable + human-readable.
│   │
│   ├── 152.2 — Deserializer YAML → Canvas
│   │       `POST /api/data-products/apply` erkennt `spec.pipeline`
│   │       und ruft nach dem `apply_plan` Pfad `save_graph()` mit
│   │       `to_canvas_doc(spec.pipeline)`. Response trägt jetzt
│   │       `canvas_version` Feld. Audit-Eintrag protokolliert.
│   │       Round-trip-Test garantiert idempotenz.
│   │
│   └── 152.3 — Diff-View
│           Neuer Service `_diff.py:diff_docs(before, after) →
│           CanvasDiff` mit added/removed/modified nodes + edges
│           (position-only changes ignoriert). Neuer Route
│           `GET /api/dp/{id}/canvas/diff?from_version=N&to_version=M`
│           + standalone Page `/dp/{id}/canvas/diff` mit 3-Spalten-
│           Layout (added/removed/modified), JSON-tree-diff im
│           "modified" Bereich.
│
├── Phase 153 — Visual DP Editor: Real-time Co-Edit (Wave G)  ✅ shipped (local, 2026-05-31)
│   │
│   │   Single-file WS hub (vs. Phase-105's 8-module split) — same
│   │   wire-format (SYNC_STEP1/2/UPDATE + AWARENESS_UPDATE) but
│   │   minus the cross-process bus + cell-uuid remap (DPs don't
│   │   need those v1). Conditional client mount via `?coedit=1`
│   │   so single-user mode pays no Y.js cost by default.
│   │
│   ├── 153.1 — Y.Doc-Binding für Canvas-Graph
│   │       `pointlessql/api/dp_canvas_coedit_ws.py` (one file): WS-
│   │       Endpoint `/ws/dp-canvas/{dp_id}` + in-memory hub per dp_id
│   │       + flush_loop. Service-Helper
│   │       `pointlessql/services/dp_canvas/_coedit.py` (4 funktionen):
│   │       `get_or_init_canvas_ydoc` seedet aus latest saved graph,
│   │       `persist_canvas_ydoc` minted neue version row via
│   │       existing `save_graph` (skipped wenn dokument unchanged).
│   │       Y.Map-Root `canvas` mit einem `json`-Slot der die
│   │       serialisierte CanvasDoc trägt.
│   │
│   ├── 153.2 — Awareness-Layer
│   │       Frontend `frontend/js/dp_canvas/coedit.js` instantiate
│   │       `y-protocols/awareness` Awareness und sendet
│   │       `TAG_AWARENESS_UPDATE` (0x03) frames. Server-Hub relayed
│   │       das verbatim ohne zu persistieren.
│   │
│   └── 153.3 — Save-Path-Barrier
│           Hub-`flush_loop` ruft alle 1.5s `persist_canvas_ydoc`
│           wenn `dirty=True`. Last-subscriber-leave triggert finalen
│           sync-flush vor hub-teardown. Idempotent: identical-doc-
│           skip vermeidet eine flood von version-rows wenn ein hub
│           idle ist.
│
├── Phase 154 — Visual DP Editor: Operations + AI-Author-Surface (Wave H)  ✅ shipped (local, 2026-05-31)
│   │
│   │   Closure-Wave: Versioning-UI im Editor-Toolbar, 5 MCP-Tools
│   │   im hermes-plugin-pointlessql, voller Walkthrough mit allen
│   │   8 Sub-Surfaces, Cluster-Closure.
│   │
│   ├── 154.1 — Versioning-UI
│   │       Toolbar-Dropdown "Versions ▾" listet alle saved canvas-
│   │       versions newest-first. Per-Version Restore-Button
│   │       (creates new latest from chosen version) + Compare-Link
│   │       in 152.3 diff-view. Pin/Unpin deferred (no
│   │       is_production column yet).
│   │       Neuer Route `GET /api/dp/{id}/canvas/versions/{version}`
│   │       liefert das gespeicherte CanvasDoc einer beliebigen
│   │       Version (vorher nur die latest via load_latest_graph).
│   │
│   ├── 154.2 — Plugin / MCP-Tools für AI-Agent-Authoring
│   │       Im `hermes-plugin-pointlessql` (commit `6047bc2`):
│   │       `pql_canvas_load` (any-user), `pql_canvas_validate`
│   │       (any-user), `pql_canvas_add_block` (supervisor),
│   │       `pql_canvas_wire_blocks` (supervisor),
│   │       `pql_canvas_materialize` (supervisor).
│   │       Write/run-tools gegated auf `client._config.supervisor_mode`
│   │       — gleiche Schiene wie `pql_promote_model`.
│   │       PointlessClient erweitert um `get_dp_canvas`,
│   │       `save_dp_canvas`, `validate_dp_canvas`,
│   │       `materialize_dp_canvas`. 7 neue pytest im plugin
│   │       (full suite 293/0 green).
│   │
│   ├── 154.3 — Full Walkthrough-Doc
│   │       `docs/e2e-walkthroughs/dp-canvas-builder.md` enthält
│   │       jetzt sechs Wave-Sektionen (B Happy-Path, C Live-Preview
│   │       + CodeMirror, D Compound-Blocks + Mesh, F YAML round-
│   │       trip + Diff, G Co-Edit, H Versioning + Agent-Authoring).
│   │
│   └── 154.4 — Cluster-Closure + Push
│           ROADMAP Mega-Cluster 147-154 ⏳→✅; CHANGELOG
│           konsolidiert; Memory-Index aktualisiert; single push
│           `git push origin main` für 8+ lokale commits.
│
└── Mega-Cluster 147-154 — Visual Data Product Editor  ✅ shipped (local, 2026-05-31)
   PointlesSQL grew a KNIME-style block-and-wire authoring surface
   for data products. 19 atom blocks (8 sources/sinks + 10
   transforms + 1 DP◫ compound), live preview through DuckDB,
   CodeMirror DuckDB-grammar editors with column autocomplete,
   editable workspace mesh-canvas, DP-as-Code YAML round-trip with
   version diff, opt-in Y.Doc real-time co-edit, and 5 MCP plugin
   tools so agents can author canvases through the same path
   browser users use. 8 commits, rc204→rc212, ALL LOCAL until
   final push.
│
├── Self-Service Access & Export — request → grant for consumers  ✅ shipped (local, 2026-06-03)
│   │   A consumer who lacks SELECT requests access from the Data tab;
│   │   the steward / admin approves from a pending-requests panel on
│   │   the same page, and the app issues a real UC SELECT grant through
│   │   the soyuz client (best-effort per table — a rejected table is
│   │   reported, the rest still grant; PointlesSQL never writes
│   │   lakehouse permissions directly).  Requests live in an
│   │   own-metadata ``data_product_access_requests`` ledger (alembic
│   │   ``t8h0j2l4n6p8``); the new request notifies steward + admins, the
│   │   decision notifies the requester, both via the existing fanout.
│   │   Glossary badges on the Data tab now deep-link to
│   │   ``/glossary/{slug}``.  New routes + model + 7 pytest.  ALL LOCAL.
│
├── Ask this Data Product — DP-scoped NL→data panel for consumers  ✅ shipped (local, 2026-06-03)
│   │   A new "Ask" tab on the DP detail page opens a Lens chat session
│   │   pre-seeded with this product's tables / columns / business
│   │   concepts, so a non-technical user can ask in plain language and
│   │   get real figures back.  The previously-stubbed Lens ``query``
│   │   tool now genuinely executes: it reads each referenced Delta
│   │   table from its resolved location, masks classified columns at
│   │   the source (so masking survives joins / aggregations), registers
│   │   the masked frame into in-process DuckDB, runs the gated SELECT,
│   │   and returns rows — after a per-table SELECT-privilege check; the
│   │   chat loop wires a principal-scoped UC client, unmask is
│   │   admin-only.  Gated ``require_user`` (the SELECT gate protects the
│   │   data, not the scope).  New ask routes + tab + 7 pytest, 4570/0.
│   │   ALL LOCAL.
│
├── Consumer Data View — DP detail page made readable for business domains  ✅ shipped (local, 2026-06-03)
│   │   The former Contract tab is now a meaning-first "Data" view for
│   │   domain consumers who don't know the platform: each column leads
│   │   with its plain-language description + a friendly type label (raw
│   │   type on hover), bound glossary-term badges, a trust strip
│   │   (freshness / refresh SLA / owning domain / owner contact mailto),
│   │   per-table CSV + Parquet download, and an inline governance-masked
│   │   sample-rows panel that degrades gracefully when storage is gone.
│   │   Backend: ``GET …/export`` gains ``format=csv`` (shared masking).
│   │   Frontend + 1 route + 2 pytest, full suite 4559/0.  ALL LOCAL.
│
├── Marketplace Discovery View — product-centric "find a data product"  ✅ shipped (local, 2026-06-03)
│   │   The flat ``/data-products`` list gains a card-grid marketplace
│   │   view (new default) for business users: cards show the owning
│   │   domain, endorsement / certification badges, a freshness chip, and
│   │   the business-glossary terms a product speaks.  Discovery facets
│   │   filter by domain / lifecycle / "certified only", and search now
│   │   matches description + domain + bound glossary terms, not just the
│   │   name.  Table + card views stay as toggles.  Backend: ``GET
│   │   /api/data-products`` carries each product's active ``endorsements``
│   │   + ``glossary_terms`` via two bulk loaders; +4 pytest, 4563/0.
│   │   ALL LOCAL.
│
├── Mega-Cluster 155-164 — Visual DP Editor + Platform Polish  ✅ shipped (local, 2026-05-31)
│   │   10 improvement phases on top of the Mega-Cluster 147-154
│   │   surface and on adjacent platform surfaces (audit log,
│   │   API-key dashboard).  No new features — UX polish,
│   │   performance, deferred-but-needed gaps.
│   │   1 commit per phase, single push at end.  rc212→rc222.
│
├── Phase 155 — Visual DP Editor: Pin/Unpin Production-Version  ✅ shipped (local, 2026-05-31)
│   │
│   │   Per-version production-pin flag on
│   │   ``data_product_canvas_graph``.  Versions ▾ dropdown shows
│   │   pin badge + pin/unpin button per row; "v{N} pinned" badge
│   │   in toolbar; materialise modal warns when current draft
│   │   replaces the pinned production version.  Partial unique
│   │   index enforces "at most one production version per DP".
│   │   New ``canvas_pin`` / ``canvas_unpin`` audit actions.
│   │   Alembic ``m1a3c5e7g9i1`` widens the op_name CHECK so
│   │   future agent-mediated pin/unpin can reuse the same enum
│   │   values.
│
├── Phase 156 — Visual DP Editor: Preview Cache + Truncation Indicators  ✅ shipped (local, 2026-05-31)
│   │
│   │   In-process LRU memoises ``preview_until`` results keyed on
│   │   the upstream-slice content hash so re-preview returns
│   │   instantly.  ``save_graph`` busts the cache for the DP
│   │   automatically; ``?bust=1`` query param exposes manual
│   │   busting from the editor UI.  PreviewResult envelope gains
│   │   ``row_count`` + ``cache_hit`` fields; the preview modal
│   │   shows a "cached" badge + a "≥N rows" / "N rows" count
│   │   badge + a "Bust cache" button.  Per-process only; multi-
│   │   worker fan-out is out of scope for v1.
│
├── Phase 164 — API-Key Usage: WoW diff + 3σ anomaly heuristic  ✅ shipped (local, 2026-05-31)
│   │
│   │   ``get_usage_summary`` response envelope extended with
│   │   ``wow`` (last-7d-vs-prev-7d totals + change_pct, ``None``
│   │   when prior window had zero traffic to avoid divide-by-
│   │   infinity badges), ``stats`` (mean_7d + std_7d), and a
│   │   per-day ``is_anomaly`` flag.  Anomaly rule: rolling 7-day
│   │   mean of the *prior* 7 days; if std > 0 flag when
│   │   |count - mean| > 3σ, else if mean > 0 flag when count >
│   │   5× mean (constant-baseline burst), else no flag (no
│   │   signal).  Frontend Chart.js sparkline rendering deferred —
│   │   today the admin API-key detail page already paints a
│   │   raw-canvas bar chart; the v2 colour-by-anomaly + WoW-badge
│   │   render can land separately.
│   │
│   └── Mega-Cluster 155-164 closed below.
│
├── Mega-Cluster 165-174 — Canvas Quality Cluster (DP + Mesh + Diff)  ✅ shipped (local, 2026-05-31)
│   │
│   │   10-phase improvement wave targeting the three canvas
│   │   surfaces: DP-Canvas editor at ``/dp/{id}/canvas``,
│   │   Mesh-Canvas at ``/mesh/canvas``, Diff-Canvas at
│   │   ``/dp/{id}/canvas/diff``.  Scope picks: drag-performance
│   │   (165), richer node body (166), connector visual upgrade
│   │   (167), multi-select + bulk ops (168), minimap + search
│   │   (169), auto-layout via dagre (170), mesh polish closing
│   │   deferred-162 (171), diff polish closing deferred-158
│   │   (172), block-config UX closing deferred-161 (173),
│   │   granular Y.Doc client + sticky notes closing deferred-160
│   │   (174).  Each phase one commit; rc222→rc232.  ALL LOCAL
│   │   until single final push.
│   │
├── Feed-as-Home: Unified Social/Operational Stream  ✅ shipped (local, 2026-06-02)
│   │
│   │   Aus User-Feedback ("der Feed sollte die zentrale Startseite sein,
│   │   nicht das Overview-Dashboard … jedes relevante Ding als Feed,
│   │   mit sinnvollen Filtern und direkten Aktionen — wie LinkedIn / X,
│   │   optimiert für unsere Datenplattform").  Fünf Wellen:
│   │   • W1 Feed wird Home — ``/`` rendert den Aktivitätsstream (Overview-
│   │     Dashboard ``home.html`` + ``build_home_summary`` + ``/api/home/
│   │     summary`` gelöscht, kein Shim); ``/feed`` bleibt Alias.  Rechte
│   │     Meta-Panel-Spalte (x-teleport in feedPage-Scope): „Needs your
│   │     attention“ (Approvals/Alerts/Unread → klickbar) + Trending +
│   │     People + Saved searches.  Single-Stream statt Activity/Discover-Tabs.
│   │   • W2 Kategorie-Taxonomie — zentrales ``services/notifications/
│   │     categories.py`` leitet (category, severity) aus dem event_type ab
│   │     (keine Schema-Spalte).  Chips All · Approvals · Data health · Social
│   │     · Pipeline · Governance über der Audience-Filterleiste; stabile
│   │     ``category_counts`` (vor dem Slice gezählt).
│   │   • W3 Approvals-Lane — Live-Union ``agent_runs WHERE needs_approval``
│   │     in den Feed (nie als Notification gespeichert → Karte veraltet nie,
│   │     verschwindet sobald irgendein Admin entscheidet).  Inline Approve/
│   │     Deny (optimistisch, collapse-in-place).  Terminal approved/denied
│   │     fanned out an den Principal.
│   │   • W4 Data-Health/Pipeline-Ledger — neue ``actionable_signals``-Tabelle
│   │     (alembic ``p4d6f8h0j2l4``) mit Partial-Unique-Index WHERE status=
│   │     'open' → genau eine Karte pro Problem (Storm-Guard).  Service
│   │     ``emit_signal``/``resolve_signal`` (Transition-only, best-effort,
│   │     SSE-Nudge an Admins).  Emit-Sites: alert_check (fire/clear),
│   │     job-run-Telemetry (failed/succeeded), ingest-executor (PullError/
│   │     success).  Live-Union offener Signals admin-gegated; Inline
│   │     Acknowledge (resolve) + Snooze + Retry.
│   │   • W5 Gate + Docs.  103+ neue pytest grün; pyright/pydoclint/biome/
│   │     phase-ref sauber.  rc256 → rc257.  ALL LOCAL.
│   │   Deferred (gleicher emit_signal-Einzeiler, wenn die Scanner reifen):
│   │   SLO-/Contract-/Freshness-Signale; per-recipient Sichtbarkeit für
│   │   Nicht-Admin-Owner; consecutive-similar Roll-up (Ledger-Dedup deckt
│   │   den Storm-Fall bereits).
│   │
├── Feed Social-Quality Polish — von „holprig" zu X/LinkedIn-Niveau  ✅ shipped (local, 2026-06-02)
│   │
│   │   Aus User-Feedback nach Screenshot-Review ("der Feed muss wirklich
│   │   die Qualität von X / Facebook / LinkedIn haben … momentan sieht das
│   │   noch sehr holprig aus").  Scope: Craft + full social.
│   │   • Visual craft — neues geteiltes ``frontend/js/avatars.js``
│   │     (``initials``/``avatarColor``/``avatarFor``; coedit_awareness +
│   │     coedit_core importieren es jetzt, Dup gelöscht): farbige Initial-
│   │     Avatare pro Person vs. lane-getönte Glyphen für System-Events.
│   │     Satz-Grammatik (System-Zeilen „DATA HEALTH · demo.hr" mit Eyebrow
│   │     statt Fake-Name); Run-UUIDs → ``run a13200…``, opake Refs versteckt;
│   │     Inline-Markdown gerendert (neues ``inline_md.js``, escape-first);
│   │     „view logs/details/run" zu leisem muted Deep-Link degradiert; Chrome
│   │     beruhigt (Audience-Filter → kompaktes Dropdown); Welcome-Karte in den
│   │     Empty-State gefaltet.  Approval-Card löst Principal-E-Mail → Name auf;
│   │     Trending-Rail mit menschlichen Labels.
│   │   • Engagement — ``frontend/js/feed_social.js``: Emoji-Reaktionen (lazy-
│   │     load, Chips mit Counts, optimistischer Toggle), Inline-Reply, Composer
│   │     („share an update" → postet Kommentar an ausgewähltes Data Product,
│   │     optimistic-prepend, Pills serverseitig gerendert), Follow-from-Card —
│   │     alles gegen die bestehenden polymorphen ``/api/social/{kind}/{ref}/…``
│   │     Endpoints (kein neues Backend).
│   │   • Gotchas: Alpine 3.14 ``<template x-for>`` verliert seinen Anchor in
│   │     ``<select>``/``<ul>`` UND in einem getoggelten ``x-if``/initial-
│   │     hidden ``x-show`` Subtree → Composer-Pills serverseitig (Jinja) statt
│   │     x-for.  8 neue pytest, Full-Suite grün.  rc257 → rc258.  ALL LOCAL.
│   │   Deferred: „who reacted"-Popover mit Namen (kein Reactor-Identity-
│   │   Endpoint; Count-Chips bleiben); JS-Unit-Tests (kein JS-Test-Runner im
│   │   Repo — renderInlineMd nur browser-verifiziert).
│   │
├── Feed Cards — „phenomenale UX" Karten-Pass (20 Phasen)  ✅ shipped (local, 2026-06-02)
│   │
│   │   Aus User-Feedback („schau dir speziell die Karten im Feed an, ich will
│   │   eine fenomenale UX … plane es als ~20 Phasen mit je 10 Todos").  Scope:
│   │   Karten + leichter Chrome-Pass; Backend-Bits erlaubt (nur PointlesSQL).
│   │   • Craft (frontend-only, P1–9/11–15): neuer ``--pql-feed-*`` Token-Layer
│   │     (Spacing-Rhythmus, 40px-Avatare, Rail, 3 Dichten aus einer Stelle);
│   │     Severity-Badges auf gemeinsamer Baseline als Icon+Label Status-Chip;
│   │     Pipeline/Health-Detail im inset, kopierbaren Code-Panel; Run-id +
│   │     Notebook-Pfad als Monospace-„ref"-Pills; Kommentar-Body als eine
│   │     Quote-Bubble (kein Doppel-Rand mehr); Unread/Mention von Karten-Wash
│   │     → Rail+Dot; „Show more/less" für lange Bodies; Reaktions-Palette als
│   │     elevated, keyboard-navigierbares Popover mit Caret; Mikro-Motion
│   │     (Chip-Pop, Resolve-Collapse, Fresh-Slide; reduced-motion-safe);
│   │     Card-Skeletons beim ersten Paint; per-Karte ``aria-label`` +
│   │     focus-visible Ringe.  User-Korrektur mittendrin: die „👍❤️ N"-Summary
│   │     über den Chips war redundant → entfernt, „wer reagiert" wandert in
│   │     Chip-Hover-Tooltip.
│   │   • Backend (3 Features, no soyuz): **Review-Reaktionen** — neue Tabelle
│   │     ``data_product_review_reactions`` (key = ``review_id``, alembic
│   │     ``q5e7g9i1k3m5``) + Handler/Routes gespiegelt vom Comment-Pfad, damit
│   │     Schwester-Reviews eines Produkts unabhängige Counts behalten;
│   │     **who-reacted-by-name** via opt-in ``?with_names=1`` auf der
│   │     Reaction-List (geteilte ``aggregate_reactions``/``reactor_names``);
│   │     **reply_count + Inline-Thread** („View N replies", gebatchte Count-
│   │     Query, Replies als sichere HTML-Strings statt x-for).
│   │   • Gotcha-Disziplin: jeder neue hidden-at-init Listen-Render meidet
│   │     ``<template x-for>`` (Reactor-Tooltip + Thread als JS-String, Skeleton
│   │     serverseitig).  6 neue pytest (Review-Reaktionen inkl. Sibling-
│   │     Independence + with_names).  Full-Suite 4483 → 4489 grün.  Browser-
│   │     verifiziert light + dark, 0 Konsolenfehler.  rc258 → rc259.  ALL LOCAL.
│   │
├── Feed-Triage — „abarbeiten" ohne den Stream zu verlieren (9 Phasen)  ✅ shipped (local, 2026-06-02)
│   │
│   │   Aus User-Frage („wie kann jemand den Feed *abarbeiten*, aber trotzdem
│   │   alte Sachen sehen — soll man fertig werden können oder geht er unendlich
│   │   weiter?").  Antwort: **beides** — ein endlicher Inbox-Teil + eine
│   │   unendliche Historie, die schon getrennt in den Daten liegen.  Gewählt:
│   │   ein Stream + Focus-Modus; „fertig" = Handeln + Für-dich.
│   │   • Attention-Achse (P1): nullable ``user_notifications.attention`` (alembic
│   │     ``r6f8h0j2l4n6``), am Fan-out gestempelt — ``for_you`` für gerichtete
│   │     Empfänger (``extra_recipients``: Mentions / geroutete Fakten), sonst
│   │     ``ambient``.  Drei Tiers: ``act`` (Approvals/Signals), ``for_you``,
│   │     ``ambient``.  Legacy-NULL fällt per Event-Typ zurück.
│   │   • Seen-Cursor (P2): neue ``feed_read_markers``-Tabelle (alembic
│   │     ``s7g9i1k3m5o7``) + ``POST /api/feed/seen`` (forward-only, future-clamp);
│   │     ``/api/feed`` stempelt ``is_new`` pro Row + ``unseen_count`` +
│   │     ``caught_up`` + ``needs_action_count`` + ``unread_for_you_count``.
│   │   • „Needs you"-Zone (P3): gepinnte Sektion (act + ungelesen-for_you), draint
│   │     live; Stream zeigt den Rest.  Karte als shared ``_card.html``-Partial,
│   │     in Zone + Stream wiederverwendet (kein Duplikat).  Kopf als leichter
│   │     Separator im Stil der Datums-Header (kein umrahmtes Panel — User:
│   │     „wird zu wuchtig"), accent-getönt + Count rechts.
│   │   • Caught-up-Divider + Endstate (P4): ``display:contents``-Cell rendert den
│   │     Divider zwischen neu/gesehen; „Mark all as seen"-Bar; celebratory
│   │     „You're all caught up"-Panel.
│   │   • Auto-Advance (P5): Scroll-Scan (DOM-frisch, forward-only, tab-focused)
│   │     schiebt den Cursor auf die neueste gesehene Row; SSE-Rows sind
│   │     ``is_new``.
│   │   • Focus-Modus (P6): Toggle (localStorage) blendet den Stream aus → reine
│   │     Inbox; Kategorie-Chips werden gedimmt (nicht display:none — x-for-Anchor).
│   │   • Für-dich-Inbox (P7): ``mark-all-read`` auf den for_you-Tier begrenzt;
│   │     Unread-Dot nur noch für for_you (Ambient-Neuheit = Cursor, nicht read_at).
│   │   • Globale Badges (P8): ``audit_unread`` = for_you-Inbox überall;
│   │     Home-Hub-Rail-Badge + live ``(N)``-Browser-Tab-Titel.
│   │   • 15 neue pytest (attention + seen-cursor + scoping); ruff/pyright/biome/
│   │     phase-ref clean; einzelner Alembic-Head ``s7g9i1k3m5o7``.  Browser-
│   │     verifiziert light + dark, 0 Konsolenfehler (Zone, „Mark all as seen" →
│   │     Divider, Focus-Modus, ``(8)``-Titel).  rc259 → rc261.  ALL LOCAL.
│   │
├── Sidebar Hub-and-Spoke Redesign — declutter the primary rail  ✅ shipped (local, 2026-06-02)
│   │
│   │   Aus User-Feedback ("die linke Seitenleiste ist etwas überlaufen,
│   │   zu viele Optionen") nach dem Overnight-Hardening-Lauf.  Die
│   │   primäre Navigationsleiste hatte 27 flache Links in 6 Gruppen
│   │   (DATA allein 12) und scrollte.  Lösung ohne Feature-Verlust:
│   │   • Rail schrumpft 27 → 6 Hubs (Home · Watch · Build · Data ·
│   │     Community + Admin-Footer).  Jeder Hub besitzt eine Spoke-Liste
│   │     seiner Unter-Features, die in der zweiten Sidebar (context_panel)
│   │     über dem bestehenden kontextuellen Inhalt rendert.
│   │   • Neue Ebene ``active_hub`` (``_hub_map`` in base.html) eine Stufe
│   │     über dem unveränderten ``_section_map``; Rail-Highlight keyt auf
│   │     den Hub, der Spoke-Highlight weiter auf ``active_section`` /
│   │     ``active_page``.  5 Spoke-Partials unter components/sidebars/.
│   │   • Watch-Hub trägt ein summiertes Badge (pending + unread + firing);
│   │     Einzel-Badges bleiben auf den Spokes.  Delta-branches-Spoke jetzt
│   │     via permission_link admin-gegated (schließt eine latente Lücke —
│   │     die alte Rail-Zeile war ungated trotz require_admin).
│   │   • Panel öffnet sich beim Hub-Klick automatisch wieder (außer im
│   │     Focus-Mode); afterSwap-Sync vergleicht jetzt gegen den Hub.
│   │     Mobile-Offcanvas bleibt bewusst flach (kein Fixed-Rail-Druck).
│   │   Browser-verifiziert (alle 6 Hubs, Firefox).  test_nav_rail.py auf
│   │   den Hub-Vertrag umgeschrieben; navigation_ia.md + contextual-panels
│   │   Walkthrough aktualisiert.  rc255 → rc256.  ALL LOCAL.
│   │
├── Code-Quality + Reorganization Pass — gates green, dedup, splits  ✅ shipped (local, 2026-06-04)
│   │
│   │   Aus User-Auftrag ("die Code-Basis auf Qualitätsverbesserungen und
│   │   Reorganisation ansehen, planen, implementieren").  One commit per
│   │   logical chunk, full gate green at each boundary, no push:
│   │   • CI baseline restored: ruff back to clean, the file-size budget
│   │     green (vestigial allowlist emptied), pyright errors → 0 and the
│   │     warning budget honestly re-baselined to its irreducible third-
│   │     party-stub floor (a true 0 needs multi-week .pyi authoring for
│   │     pyarrow/pandas/deltalake — out of scope) with one de-rotted note.
│   │   • Dedup: 56 identical ``_SessionFactory`` protocol copies → one
│   │     canonical ``pointlessql.types.SessionFactory``; slug helper →
│   │     ``services/_slug.py``; ISO-8601 parser → the audit module's.
│   │   • Backend splits behind re-export facades (import paths unchanged):
│   │     ``api/dependencies.py`` → a ``dependencies/`` package (the split
│   │     the overnight run had reverted — done here by also retargeting
│   │     the 9 monkeypatch test sites); ``api_keys`` service ``__init__``
│   │     → _cache/_verify/_crud; ``_bootstrap/_loops.py`` → a per-domain
│   │     ``_loops/`` package; ``pql/_autoload.py`` → an ``_autoload/``
│   │     package.
│   │   • Frontend mega-components → mixin installers (canvas-editor
│   │     pattern): the 1219-line ``pages/feed.js`` and 1143-line
│   │     ``pages/data_product.js`` factories are now ~130-line composition
│   │     roots over focused mixins (``pages/feed/`` + ``pages/data_product/``).
│   │     Structural-equivalence harness held every property's kind +
│   │     normalized body identical across the split.
│   │   • Flat mega-routes → per-axis packages (the data_products_routes
│   │     template): ``admin/api_keys.py`` → keys/grants/usage,
│   │     ``catalog_routes.py`` → browse/preview, ``volumes_routes.py`` →
│   │     files/convert/pages, ``external_sql_routes.py`` → submit/lifecycle;
│   │     plus the pure YAML-diff engine lifted out of
│   │     ``data_products_routes/proposals.py``.  Handler bodies unchanged;
│   │     every prior import path still resolves.
│   │   Excluded by design (verification disproved or against-grain): the
│   │   151-file api↔session decouple (the "never write directly" rule is
│   │   about soyuz tables, not our own metadata DB), a phantom BLE001 noqa
│   │   finding, and a 458-file test reorg.  ALL LOCAL.
│   │
├── Canvas Code Modularization Refactor — split the editor + backend monoliths  ✅ shipped (local, 2026-06-02)
│   │
│   │   Aus User-Auftrag ("den Canvas-Code refaktorieren, modularisieren,
│   │   wartbar für LLMs").  Two disjoint tracks, one commit per wave, no
│   │   push (left for review alongside the in-flight feed work):
│   │   • Frontend: the 3.7k-line ``dp_canvas_editor.js`` Alpine factory is
│   │     now a ~180-line composition root that spreads 21 single-concern
│   │     method bundles under ``frontend/js/dp_canvas/editor/`` (lifecycle,
│   │     drawflow_sync, node_render, node_ops, edges, edge_routing,
│   │     edge_toolbar, connect, context_menu, output_plus, viewport,
│   │     clipboard, preview, run, versions, navigation, annotations,
│   │     history, config_form, ghost_review).  Block metadata unified into a
│   │     single ``_block_catalog.js``; node creation across all nine flows
│   │     funnels through one ``_spawnNode`` helper.
│   │   • Backend: shared Kahn topo-sort → ``_graph.py``; soyuz table lookups
│   │     → ``_uc_lookup.py``; block compile/infer folded onto ``BlockSpec``
│   │     behind one ``register_block``; the 830-line ``canvas.py`` route
│   │     module split into a ``canvas/`` package by concern.
│   │   Behaviour-preserving throughout — a method-equivalence harness held
│   │   144 method bodies byte-identical across the split, and every bundle
│   │   was browser-replayed (0 console errors on editor/mesh/diff).  Per-
│   │   block Pydantic config (the planned B4) was deliberately NOT done: no
│   │   consumer exists and it would add a no-op validation layer against the
│   │   simplify goal — revisit when an agent-facing config-validation surface
│   │   needs it.  13 commits ``1d3e33bc``..``10c1edb8``.  ALL LOCAL.
│   │
├── Canvas Settings-Panel Overhaul + Broad New Block Set  ✅ shipped (local, 2026-06-03)
│   │
│   │   Aus User-Auftrag ("die rechten side-panel einstellungen verbessern,
│   │   Catalog als Freitextfeld … sind alle Blocks vollständig und sinvoll,
│   │   auch die Anzahl der Ein- und Ausgänge").  Two tracks on the
│   │   modularization branch, one commit per wave, no push:
│   │   • Settings panel (existing 19 blocks): the right drawer now shows each
│   │     block's one-line help plus its own validation errors inline; UC table
│   │     names are entered as three catalog / schema / table fields; the
│   │     Sort / Cast / Rename JSON textareas became structured row editors;
│   │     one-click upstream-column suggestions appear on every list field; and
│   │     the Sample / Window / CalcColumn affordances were clarified.  All
│   │     forms route through a new Alpine-bound macro library (chip_list,
│   │     comma_list, row_editor, available_columns, fqn_fields, cm_field) so
│   │     the 19+ per-block forms stop drifting.  Pin counts of the 19 audited —
│   │     all correct, unchanged.
│   │   • Seven new blocks: Except, Intersect, SemiJoin, AntiJoin (set / EXISTS
│   │     ops over two inputs), Unnest (explode a LIST column), and sandboxed
│   │     FileInput / FileOutput (CSV · Parquet · JSON under a configured
│   │     ``POINTLESSQL_CANVAS_FILE_ROOT``).  File paths are fenced by a layered
│   │     defence — a pure shape check in the block, then ``resolve()`` +
│   │     ``is_relative_to(root)`` containment at the executor / preview
│   │     boundary — and FileOutput is gated behind the default-off
│   │     ``allow_output`` because it writes outside UC governance.  ``SinkSpec``
│   │     gained a ``sink_kind``; ``prepare_sql`` now tolerates table-valued
│   │     functions.
│   │   Browser-verified on /dp/1/canvas (0 console errors on realistic flows),
│   │   full pytest 4555/0 green.  10 commits ``0a4f3251``..``87f2eea4``.  ALL LOCAL.
│   │
├── Canvas Full-Feature Pipeline Demo + UX Audit  ✅ shipped (local, 2026-06-03)
│   │
│   │   From user-Auftrag: build full-feature pipelines, screenshot the UX,
│   │   run them with real data so the data flow is confirmed, then improve
│   │   the UX.  Drove the Drawflow editor on /dp/1/canvas to build AND
│   │   materialise five pipelines against a fresh ``demo.canvas_demo`` schema
│   │   (order-summary join+agg+sort; set-ops + semi/anti-join two-sink
│   │   fan-out; HR window + cast/rename/calc reshape; pivot/unpivot/union/SQL/
│   │   unnest; and a three-sink parquet+Delta+CSV file round-trip + compound-DP
│   │   ref) — every block type exercised, each node previewed AND the canvas
│   │   materialised with real ``rows_written`` read back from the written
│   │   Delta tables / files.  Running real data surfaced two shipped bugs,
│   │   fixed at source:
│   │   • SemiJoin / AntiJoin / Except / Intersect mirrored both incoming edges
│   │     onto a single ``in`` pin (only Join / Union were special-cased) → a
│   │     duplicate-pin compile error the preview showed only as "0 rows".  The
│   │     target pin name now reads off the block's ``inPins`` (shared
│   │     ``inputPinName`` helper used by both ``_syncFromDrawflow`` and the
│   │     drop-target highlighter).  Every use of the four new blocks was broken.
│   │   • Cast / Rename appended a duplicate column instead of editing in place
│   │     (``col`` + phantom ``col_1``; ``old`` kept beside ``new``),
│   │     contradicting their own schema inference → now compile through DuckDB
│   │     ``* REPLACE`` / ``* RENAME``.
│   │   Plus three UX fixes from the screenshot audit: the run-results panel
│   │   docks along the bottom edge of the stage (was a centred card over the
│   │   graph head + palette; from a user question); fit-to-view floors at 0.5
│   │   zoom and left-anchors a too-wide graph (was an illegible ~0.4); and the
│   │   preview modal titles by block label with the run target column renamed
│   │   neutrally for file sinks.  The drawer forms themselves audited clean.
│   │   A later look at the mesh canvas (user report) found its nodes dropped in
│   │   a raw top-left grid with no fit/layout — top row clipped under the
│   │   topbar, less tidy than the editor; it now Dagre-arranges left-to-right
│   │   and fits-to-view on load via a shared ``fitDrawflowToView`` helper.
│   │   Full pytest 4557/0 green.  Pushed.  Canvas-audit commits
│   │   ``b563585a``..``6b279427`` on ``origin/refactor/canvas-modularization``.
│   │
├── Overnight Hardening Cluster — coverage + refactor + types + a11y  ✅ shipped (local, 2026-06-02)
│   │
│   │   Autonomous overnight run hardening the existing codebase — no new
│   │   product features.  Four threads, one commit per phase, full pytest
│   │   green gate before each, no push (left for review):
│   │   • Test coverage: ~300 new tests (29 files) across previously-thin
│   │     pure-logic / mockable modules — output_rendering, aws_sigv4,
│   │     lineage (graph-builder/pruner/row-edge store), conformance, pql
│   │     (time-travel/merge/aggregate/pql_read/embedders), sql-statements
│   │     retention, external-write scanner, UC model/catalog/metadata
│   │     mixins, agent-run stats, social target-resolver, Cedar policy
│   │     CRUD, contract-test CRUD, audit-sink decoders + soyuz reader,
│   │     canvas block modules (columns/reshape), visual SQL builder,
│   │     editor-chat factory, review dispatcher, ingest pull.  Coverage-
│   │     map-guided (two --cov passes).  Suite 4131 → 4435.
│   │   • Refactor: the 1546-line dp_canvas ``_blocks.py`` split into a
│   │     ``_blocks/`` package (``_base`` + 5 category modules, largest
│   │     454); public surface unchanged.  A ``dependencies.py`` split was
│   │     attempted and reverted — splitting a test-monkeypatched module
│   │     changes patch-target semantics.
│   │   • Type-debt: db.py engine listeners typed with ``DBAPIConnection``
│   │     (9 → 2 ignores, precision gain not ``Any`` erasure).
│   │   • A11y: global ``prefers-reduced-motion`` catch-all (WCAG 2.3.3).
│   │   Per-phase record in docs/internal/overnight-hardening-log.md.
│   │   ALL LOCAL.
│   │
├── Canvas Run UX — inline run dock + materialise version fixes  ✅ shipped (local, 2026-06-02)
│   │
│   │   Aus User-Feedback ("Warum sollte da ein neues Popup aufgehen?
│   │   Fehler sollten am Canvas stehen") nach dem Multi-Sink-Cluster.
│   │   Der Toolbar-**Run** materialisiert jetzt direkt statt ein
│   │   Bestätigungs-Modal zu öffnen; Fortschritt, die Per-Senke-
│   │   Ergebnistabelle (Port/Ziel/Zeilen/ok|failed) und Fehler stehen
│   │   in einem Status-Dock *oben am Canvas* (zuerst unten platziert,
│   │   auf User-Hinweis nach oben in den Sichtbereich verschoben),
│   │   und jeder OutputPort-Block bekommt einen grünen (geschrieben) /
│   │   roten (fehlgeschlagen) Ring direkt im Graph.  Run mit offenen
│   │   Validierungsfehlern sackt nicht mehr ab, sondern nennt die
│   │   Anzahl + fokussiert den ersten Block.  Das alte Materialize-
│   │   Modal ist entfernt.  Dazu zwei Bugs an der Quelle gefixt:
│   │   (a) die Route speicherte das Doc *vor* der Ausführung und der
│   │   Executor nochmal danach → Doppel-Bump bei Erfolg, und bei einem
│   │   Fehl-Run blieb eine gebumpte Version zurück, die der Client nie
│   │   sah (Phantom-Konflikt beim Retry); der einzige autoritative Save
│   │   liegt jetzt nur noch am Ende eines erfolgreichen Laufs
│   │   (+1 je Lauf, Fehl-Lauf bumpt nicht).  (b) Eine Quelle, die im
│   │   Katalog auflöst aber keine Delta-Dateien hat, meldet jetzt einen
│   │   klaren Fehler mit Tabellennamen statt eines opaken 500.  Zwei
│   │   neue Regressions-pytest; volle Suite 4135/0/10.  Browser-Replay
│   │   (Firefox) verifiziert: Fan-out-Canvas (Input→Filter→2 OutputPorts)
│   │   läuft grün mit "2 of 2 sink(s) succeeded", Fehlerfall zeigt klare
│   │   Meldung, Retry ohne Konflikt.  rc252→rc254.  ALL LOCAL.
│   │
├── Quality-Consolidation Cluster — Phasen 189–191  🔜 next (geplant 2026-06-05)
│   │   Die Juni-1–5-Welle (Mutation-Killing + Pure-Seam-Extraktion)
│   │   war Einmal-Aufwand ohne Schutz.  Dieser Cluster *verstetigt*
│   │   sie: aus „ist der Code korrekt" wird „bleibt der Code korrekt".
│   │   Drei Ratschen — Mutation-Gate (189), E2E-in-CI (190),
│   │   Pyright-Floor-Senkung (191).  Tiefe statt Breite; keine neue
│   │   Oberfläche.  Volle Specs in den per-Phase-Sidecars.
│   │
├── Phase 189 — Mutation-Testing-Gate (mutmut committen + CI-Ratsche)  🔜 next
│   │   Detail: [`docs/internal/phase-189.md`](docs/internal/phase-189.md).
│   │   - mutmut-Harness committen: `setup.cfg [mutmut]` +
│   │     `scripts/mutation/run_mutmut.py` (kapselt Trampoline-Patch +
│   │     die 4 Setup-Blocker) + README.  pyproject bleibt sauber.
│   │   - Baseline einfrieren (`baseline.json`) + Äquivalent-Mutant-
│   │     Allowlist (`equivalent.txt`, analog file-size-budget).
│   │   - CI-Gate: PR-inkrementell auf geänderte `pql/`+`services/`-
│   │     Module (failt bei *neuem* Survivor), Nightly-Full (~2 h,
│   │     non-blocking, Artifact).  Kein pre-commit (zu langsam).
│   │   - Restliche killbare Orchestrator-Hotspots schließen (Pure-Seam
│   │     extrahieren + integration-covern; Memory-Frontier abarbeiten).
│   │
├── Phase 190 — E2E-CI-Automatisierung (Top-Journeys aus den Playbooks)  🔜 next
│   │   Detail: [`docs/internal/phase-190.md`](docs/internal/phase-190.md).
│   │   - Heute: 188 Phasen UI hinter genau 2 Playwright-Tests; 92
│   │     deterministische Playbooks nur manuell replaybar.
│   │   - Entscheidung vorab: soyuz-catalog als CI-Service booten
│   │     (empfohlen, hinter `requires_soyuz`-Marker) → Katalog-/
│   │     Lineage-Journeys erreichbar.
│   │   - Seed-Fixture (`seed-e2e.py`) + `e2e/pages/`-Page-Objects +
│   │     `_journeys.py`-Registry (Test → Quell-Playbook).
│   │   - Tier-1 (~8: catalog/sql-editor/writes/audit/branches/rollback/
│   │     dp-canvas/data-products) + Tier-2 (~6: lineage/federation/
│   │     policy/non-admin-403/error-envelope).
│   │   - CI-Verdrahtung + Flake-Kontrollen (rerun×1, screenshot-on-fail)
│   │     + Coverage-Ledger (welche Playbooks noch nicht automatisiert).
│   │   - Non-Scope: Journeys mit Jupyter/MLflow/dbt (Subprozesse im
│   │     e2e-Job aus); Visual-Regression.
│   │
├── Phase 191 — Pyright-Warning-Floor-Sweep (962 → Ratsche)  🔜 next
│   │   Detail: [`docs/internal/phase-191.md`](docs/internal/phase-191.md).
│   │   - Ist (2026-06-05): 0 errors, 962 warnings (Budget am Anschlag).
│   │     ~894 sind `reportUnknown*`; 55 `reportUnnecessaryIsInstance`
│   │     bewusst (out of scope).
│   │   - Methode: typisierte Grenzen an den Unknown-Quellen
│   │     (TypedDict/pydantic an json/yaml/OpenLineage-Nähten; typed
│   │     Wrapper an pyarrow/duckdb-Seams) — bewiesenes Muster.
│   │   - Wellen nach Hotspot: W1 Lineage/OpenLineage (inbound_parser 31
│   │     + _merge/_lineage 24), W2 contract_tests/_assertions 47 +
│   │     DP-as-Code-YAML, W3 notebook-io/coedit-remap, W4 lens/query +
│   │     catalog/browse + Tail.  BUDGET je Welle senken (inline notiert).
│   │   - Ziel ~650–700 Rest-Floor (irreduzible Third-Party-Stubs);
│   │     keine pauschalen `# type: ignore`, keine stillen Caps.
│   │
├── Phase 192 — Differentiator-Tiefe (Lineage-Korrektheit + Agent/MCP-Surface)  ⏳ planned (vorgemerkt)
│   │   Vorgemerkt für *nach* dem Quality-Cluster — Tiefe statt Breite
│   │   auf den DBX-Differenzierern, keine 16. Oberfläche.  Spec landet
│   │   in einem eigenen `docs/internal/phase-192.md` bevor sie startet.
│   │   - DBX-Moat härten: Value-/Column-Level-Lineage, Delta-Branching,
│   │     agent-native Provenance + MCP-Reflexive-Tools, Audit-Cockpit.
│   │   - Konkreter Aufhänger: der Lineage-Wiring-Audit (Phase 15.8) fand
│   │     einen echten Korrektheits-Bug (silver SELECT droppt
│   │     `_lineage_row_id`).  End-to-End-Lineage-Korrektheit über *alle*
│   │     PQL-Pfade ist verifizierbar + hochwertig.
│   │   - Strategische Wette: die Agent/MCP-Oberfläche (passt zum
│   │     Agent-first-Pivot, Phase 12.12).
│   │
├── Mega-Cluster 193–196 — Reusable Canvas Core + Two New Consumers  ✅ shipped (local, 2026-06-06)
│   │   Der Canvas-Editor war an Data Products gekettet.  Extrahiere den
│   │   Kern in drei Schichten — ein consumer-agnostischer Graph-Kernel
│   │   (`canvas_core`) → die DataFrame/SQL-Schicht (`canvas_df`) →
│   │   per-Consumer-Layer — und baue zwei neue Consumer darauf: einen
│   │   visuellen Scheduler-Task-Chain-Editor und einen Notebook-
│   │   DataFrame-Builder.  Data Products bleiben verhaltensgleich; die
│   │   Scheduler-topo-sort wird auf den geteilten Kern vereinheitlicht;
│   │   der tote lineare `services/canvas/`-Prototyp wird stillgelegt.
│   │
│   ├── Phase 193 — Canvas-Core-Extraktion (canvas_core + canvas_df)  ✅ shipped (local, 2026-06-06)
│   │   │   - PR1 ✅ (local): `canvas_core`-Kernel — Envelope (CanvasDoc/
│   │   │     Node/Edge/CompileError), `topo_sort` mit pluggbarem
│   │   │     `sort_key`, Struktur-Validierung, struktureller Diff,
│   │   │     `NodeKindRegistry`.  `dp_canvas` re-exportiert via Shims, kein
│   │   │     Aufrufer ändert sich.  Scheduler `_topological_order` auf den
│   │   │     geteilten `topo_sort(sort_key=int)` vereinheitlicht —
│   │   │     numerische Tie-Breaks bit-identisch erhalten.  Paritäts-Test
│   │   │     deckt die int-vs-lexikal-Sortierfalle ab.  Full pytest
│   │   │     5967/0/10.
│   │   │   - PR2 ✅ (local): `canvas_df`-Schicht — reine Blocks
│   │   │     (`_base`/`_relational`/`_reshape`/`_columns`/`_sql`), Compiler,
│   │   │     schema_flow, edge_types verschoben; `_types` gesplittet
│   │   │     (ColumnSpec/PinSchema/SinkSpec/SQLFragment → `canvas_df`,
│   │   │     SinkResult/MultiExecuteResult bleiben in `dp_canvas`).  Die
│   │   │     DP-Source/Sink-Blocks (`_io`/`_files`) registrieren in die
│   │   │     *geteilte* `BLOCK_REGISTRY`.  `dp_canvas` re-exportiert via
│   │   │     Shims — kein Aufrufer ändert sich (1 sanktionierte Test-Import-
│   │   │     Pfadänderung).  `canvas_df` ist soyuz-/config-/storage-rein.
│   │   │     Full pytest 5967/0/10, pyright 0 Fehler.  Verschoben: die
│   │   │     `NodeKindRegistry`-Generalisierung (Registry bleibt vorerst ein
│   │   │     geteiltes `BLOCK_REGISTRY`-Dict) und `compile_to_select` →
│   │   │     PR7, weil ein sink-freier Compile-Pfad nötig ist (der
│   │   │     synthetische OutputPort koppelte `canvas_df` sonst zurück an
│   │   │     `dp_canvas`); `_preview_cache` bleibt in `dp_canvas` (kein
│   │   │     `canvas_df`-Consumer).
│   │   │   - PR3a/PR3b ✅ (local): `frontend/js/canvas/`-Shell-Verzeichnis;
│   │   │     12 consumer-agnostische Module per `git mv` verschoben — 7
│   │   │     generische Bundles (viewport/history/annotations/context_menu/
│   │   │     edge_routing/edge_toolbar/config_form_structured) + 5 Helfer
│   │   │     (_canvas_helpers/_auto_layout/_focus_mode/_sql_format/
│   │   │     _codemirror_snippets).  Alle Importer (inkl. mesh-Editor +
│   │   │     Diff-Seite) umgebogen.
│   │   │   - PR3c ✅ (local): Katalog-Entglobalisierung — die 7
│   │   │     katalog-gekoppelten Kern-Bundles (drawflow_sync/node_render/
│   │   │     node_ops/clipboard/output_plus/connect/edges) + der geteilte
│   │   │     `_drawflow_loader` + die generischen `_render_helpers` lesen
│   │   │     jeden Block-Shape-Lookup (BLOCK_DEFS/blockDef/pinIndexFor/
│   │   │     inputPinName/nodeHtml/describeConfig) jetzt über ein
│   │   │     injiziertes `this.catalog` statt `dp_canvas/_block_catalog` zu
│   │   │     importieren; alle nach `frontend/js/canvas/` verschoben.
│   │   │     `assembleCanvasEditor(adapter, ctx)` (canvas/compose.js) ist
│   │   │     die Compose-Naht: sie besitzt die geteilten Bundles + die 3
│   │   │     abgeleiteten Graph-Getter; der Consumer-Adapter liefert
│   │   │     Katalog + eigene Bundles + State.  Die DP-Seite schrumpft von
│   │   │     einem 190-Zeilen-Kompositionsroot auf einen dünnen Adapter
│   │   │     (DP_CATALOG + 8 DP-Bundles + dpEditorState).  Gegen den
│   │   │     laufenden Editor verifiziert: identisches State-Feld-Set,
│   │   │     233 Keys / 161 Methoden, alle Bundles gemerged, Getter als
│   │   │     Live-Accessoren, der de-globalisierte Katalog-Pfad
│   │   │     (nodeHtml/describeConfig/_spawnNode) löst über `this.catalog`
│   │   │     auf, 0 Konsolen-Fehler beim eager Bootstrap-Import, biome
│   │   │     2.4.15-rein.  Schließt Phase 193.  Aufgeschoben (eine
│   │   │     Verifikation): der volle interaktive dp-canvas-builder-Replay
│   │   │     (6 Wellen) braucht ein frisch geseedetes Canvas-Datenprodukt —
│   │   │     wird beim nächsten Seed (PR6/PR8-e2e) mitgenommen; das
│   │   │     Komponenten-Äquivalenz-Proof deckt das Relokations-/
│   │   │     Entglobalisierungs-Risiko ab.
│   │   │
│   ├── Phase 194 — Scheduler-Task-Chain-Visual-Editor  ✅ shipped (local, 2026-06-06)
│   │   │   - PR4 ✅ (local): JobTask ⇄ CanvasDoc-Bridge
│   │   │     (`services/scheduler/_canvas.py`) + Read-Routes unter
│   │   │     `/api/jobs/{id}/canvas` — build_job_dag_doc (node
│   │   │     `task-{pk}`, block_type=Kind, config={name,params,
│   │   │     max_retries,retry_backoff_seconds}, Kante A→B ⇒ B hängt von
│   │   │     A ab), validate (Envelope+Cycle+Kind+Name), run-status-
│   │   │     Overlay, `/_kinds`-Palette aus `KindRegistry.kinds()`.
│   │   │     12 Service-Tests, keine Schema-Änderung.
│   │   │   - PR5 ✅ (local): Diff-Save (`apply_job_dag_doc` + POST
│   │   │     `/canvas`) — `task-{pk}`-Update vs. neue Knoten (Editor-Id →
│   │   │     `task-{pk}`-Remap), depends_on aus Kanten neu berechnet,
│   │   │     Lösch-Guard für Tasks mit laufendem `TaskRun`,
│   │   │     `validate_dag`-Gate vor Commit (Zyklus → Rollback).
│   │   │     8 Tests inkl. Guard + Cycle-Rollback + validate_dag-Parität.
│   │   │   - PR6 ✅ (local): Frontend-Editor `/jobs/{id}/dag` als dünner
│   │   │     Adapter auf `assembleCanvasEditor` — eigener Katalog
│   │   │     (`makeCatalog` aus den `/_kinds`), eigene Bundles
│   │   │     (lifecycle/persistence/config_form/run_status), die
│   │   │     geteilten Graph-Bundles unverändert wiederverwendet.
│   │   │     „Edit DAG"-Button im Job-Detail.  Generischer
│   │   │     `canvas/catalog_factory.js` (auch für Studio nutzbar).
│   │   │     Gegen den laufenden Stack mit einem geseedeten 3-Task-Job
│   │   │     verifiziert: 3 Knoten + 2 Kanten gerendert, 13-Kind-Palette,
│   │   │     Save-Round-Trip, neuer Knoten → `task-4`-Remap, validate
│   │   │     (clean + unknown-kind), 0 Konsolen-Fehler.  e2e-Walkthrough
│   │   │     `scheduler-dag-editor.md` (6 Wellen).  Schließt Phase 194.
│   │   │
│   ├── Phase 195 — Notebook-DataFrame-Studio  ✅ shipped (local, 2026-06-06)
│   │   │   - PR7 ✅ (local): Studio-Backend auf einem sink-freien
│   │   │     `canvas_df.compile_to_select(doc, terminal_node_id)` (die aus
│   │   │     der canvas_df-Extraktion vertagte Primitive) — schneidet den
│   │   │     DAG bis zum Zielknoten und rendert `WITH … SELECT * FROM
│   │   │     <terminal_cte>` ohne OutputPort-Sink; die CTE-Ketten-/Edge-/
│   │   │     Base-Table-Logik in geteilte Helfer gehoben, `compile_canvas`
│   │   │     verhaltensgleich (109 Canvas-Acceptance-Tests grün).
│   │   │     `services/dataframe_studio` (Disallowed-Block-Guard +
│   │   │     compile-Wrapper) + Routen `/api/dataframe-studio/{compile,
│   │   │     preview,validate}`, die die DP-Canvas-Helfer (soyuz-Client,
│   │   │     Schema-Seeding) + `preview_until` wiederverwenden.  Live:
│   │   │     validate+compile flaggen einen Sink sauber.  10 Tests.
│   │   │   - PR8 ✅ (local): Seite `/dataframe-studio` als dünner Adapter
│   │   │     auf `assembleCanvasEditor` — Katalog = DP-Katalog ohne Sinks
│   │   │     (`buildStudioCatalog`), die DP-Config-Form-Bundles + Partials
│   │   │     unverändert wiederverwendet, Studio-Persistenz
│   │   │     (compile/preview/validate + Copy SQL / Copy `pql.sql(…)`).
│   │   │     Gegen den laufenden Stack verifiziert: 23-Block-Palette ohne
│   │   │     Sinks, Drop+Wire, Config-Formen + CodeMirror-Predicate mounten,
│   │   │     compile/preview/validate verdrahtet mit sauberer
│   │   │     Fehlerbehandlung, 0 Konsolen-Fehler.  e2e-Walkthrough
│   │   │     `dataframe-studio.md`.  Schließt Phase 195.  Aufgeschoben:
│   │   │     der volle „Send to notebook"-Round-Trip (Notebook-Picker +
│   │   │     Zell-Insert) — Copy-SQL/Copy-pql sind die Emit-Aktionen;
│   │   │     Studio-Graph-Persistenz via Notebook-Zell-Metadaten ist
│   │   │     bewusst client-seitig (kein neues Schema/Migration).
│   │   │
│   └── Phase 196 — Legacy-Linear-Canvas-Retirement  ✅ shipped (local, 2026-06-06)
│       │   - PR9 ✅ (local): der tote lineare `/canvas`-Prototyp
│       │     stillgelegt — `GET /canvas` → 308 auf `/dataframe-studio`;
│       │     gelöscht: `services/canvas/` (compile_nodes/SUPPORTED_NODE_
│       │     KINDS), `api/canvas_routes.py` (+ Router-Include),
│       │     `pages/canvas.js` (+ bootstrap-Import/`window.canvasEditor`),
│       │     `templates/pages/canvas.html`, `tests/test_canvas_compiler.py`.
│       │     Sidebar-Link → `/dataframe-studio`.  Grep-sauber; App
│       │     importiert (817 Routen), pytest sammelt 5996 ohne
│       │     Import-Fehler.  Schließt Phase 196 + den 193–196-Cluster.
│   │
├── Differentiator-Tiefe-Cluster — Phasen 197–206  ⏳ planned (geplant 2026-06-06)
│   │   Zehn lang laufende Tiefen-Phasen *nach* dem Quality-Cluster
│   │   (189–191) und dem Canvas-Mega-Cluster (193–196).  Bewusst auf
│   │   *autonome Remote-Ausführung* zugeschnitten: objektive Abnahme,
│   │   stark dekomponierbar in Wellen, intern (kein externes Publizieren,
│   │   keine ständigen Produktentscheidungen) — damit ein Remote-Confirm
│   │   pro Phase reicht.  Tiefe statt Breite auf den DBX-Differenzierern +
│   │   Produktreife (Korrektheit, Test-Infra, Betrieb, Sicherheit,
│   │   Agent-Surface, Reichweite); keine 16. Oberfläche.  Volle Specs in
│   │   den per-Phase-Sidecars.  Reihenfolge ist Vorschlag, nicht
│   │   Abhängigkeit — 197/202/203 sind die Differenzierer-Kerne, 198/199
│   │   die Infra-Hebel, auf denen mehrere andere aufsitzen.
│   │
│   │   **Backbone-Landung 2026-06-07 (lokal, code-only, halbfertig).**
│   │   Phasen 198–206 in einem autonomen Durchgang als halbfertige
│   │   Backbones gelandet: der wiederverwendbare Kern-Code jeder Phase ist
│   │   da und import-/ruff-sauber, während Test-Ausführung, DB-Migrationen,
│   │   App-Startup-Verdrahtung und sämtliche Frontend-Arbeit bewusst
│   │   aufgeschoben wurden (kein Test-Run / keine speicherintensiven Ops im
│   │   Durchgang — auf Anweisung).  Je Phase (Commit · gelandet · Hauptauf-
│   │   schub):
│   │   - 198 e2e (`58b0541f`): Page-Objects + Journey-Registry + 93-Playbook-
│   │     Coverage-Ledger-Ratsche + conftest soyuz/mobile/screenshot.
│   │     Aufgeschoben: die Browser-Journey-Module (brauchen Playwright-Runs).
│   │   - 199 Perf (`4a47dfaf`): per-Route-Latenz-Middleware + DB-query_span +
│   │     Metriken + check-perf-budget.sh.  Aufgeschoben: Perf-Harness +
│   │     Fixtures + Nightly.
│   │   - 200 Observability (`2f56be60`): opt-in OTel-Bridge + RED-Counter +
│   │     SLO-Burn-Rate + RED-Dashboard.  Aufgeschoben: Verdict-History-
│   │     Tabelle, synthetische Probes, Lifespan-Wiring, USE/SLO-Dashboards.
│   │   - 201 DR (`37a75fb6`): Backup/Restore-Service + Manifest-Schema-Guard
│   │     + CLI + DR-Runbook.  Aufgeschoben: Scheduler-Executors, Snapshot-
│   │     Tabelle, S3, dr-gameday-CI.
│   │   - 202 Security (`4a666e7b`): Security-Header + report-only-CSP +
│   │     Collector + Authz-Matrix-Generator + bandit/SAST + STRIDE.  Die
│   │     Matrix flaggte **111 /admin-Routen ohne erkannte Rollen-Gate** (zu
│   │     prüfen).  Aufgeschoben: Matrix-Tests, CSP-enforce, Secrets-Rotation-
│   │     CLI.
│   │   - 203 MCP (`d851abfe`): Tool-Spec + Scope-Enforcement + provenance-
│   │     gegateter Write-Base + 4 Write-Tool-Skelette + Tool-Matrix +
│   │     Conformance.  Aufgeschoben: ApiKey-Scope-Spalten/Migration,
│   │     Registry+Server-Wiring, echte Write-Executors.
│   │   - 204 Data-Quality (`2e2270ef`): 6 neue Expectations + gewichtete
│   │     Scorecard + off/warn/block-Pre-Write-Gate (pure compute).
│   │     Aufgeschoben: Tabellen/Migration, Dispatcher+Hook-Wiring,
│   │     Anomalie-Emission, UI-Tab.
│   │   - 205 a11y (`5d8c8ac5`): axe-core-e2e-Harness + Violations-Floor-
│   │     Ratsche.  Aufgeschoben: alle W2–W6-Frontend-Fixes (WIP-Kollision).
│   │   - 206 FinOps (`2596fcad`): Chargeback-Pivots + Budget-Schwellen +
│   │     Cost-Forecast (pure compute).  Aufgeschoben: Budget/Forecast-
│   │     Tabellen, Routes, Quota-Hook, FinOps-Dashboard.
│   │   Vollständige Fertigstellung (Tests, Migrationen, Wiring, Frontend) je
│   │   Phase ist der nächste Schritt, sobald Test-Runs wieder erlaubt sind.
│   │
│   ├── Phase 197 — Lineage-Korrektheits-Verifikations-Engine  ✅ shipped (local, 2026-06-07)
│   │   │   Detail: [`docs/internal/phase-197.md`](docs/internal/phase-197.md).
│   │   │   Property-based (Hypothesis) + Golden-Corpus-Verifikation von
│   │   │   Row-/Column-/Value-Lineage über *alle* PQL-Pfade.  Aufhänger:
│   │   │   der echte 15.8-Bug (silver SELECT droppt `_lineage_row_id`).
│   │   │   Invarianten formalisieren → reine Checker → Operator-Wellen
│   │   │   (sql/merge/aggregate/update/autoload/branch/federation) →
│   │   │   Golden-Corpus + OpenLineage-Differential → CI-Marker.
│   │   │   - W1 ✅ (local): Die 6 harten Invarianten formalisiert
│   │   │     (`docs/internal/lineage-invariants.md`) + als reine Checker
│   │   │     `(OperationFacts) -> list[Violation]` ohne I/O implementiert
│   │   │     (`services/lineage/verify/_invariants.py`): Row-Edge-Closure
│   │   │     (inkl. 15.8 dropped-`_lineage_row_id`), Target-Id-Determinismus
│   │   │     (`synth_target_row_id`), Edge-Endpunkte, Column-Map-Coverage,
│   │   │     Value-Changes-real, Reject-Reason-Gültigkeit.  16 Unit-Tests
│   │   │     inkl. der absichtlich wieder eingebauten 15.8-Regression, die
│   │   │     jetzt die *Suite* (nicht nur den INFO-Log) rot macht.
│   │   │   - W2 ✅ (local): Hypothesis (dev-group) + `lineage_verify`-Marker;
│   │   │     reiner `facts_from_rows`-Adapter (`verify/_adapter.py`, ORM-
│   │   │     geformte Zeilen → `OperationFacts`); Offline-Harness
│   │   │     (`tests/lineage_verify/`) das echte PQL-Primitive gegen einen
│   │   │     Wegwerf-Delta-Root mit gemockten soyuz-Syncs laufen lässt + die
│   │   │     4 Lineage-Tabellen per `op_id` zurückliest; Property-Test, der
│   │   │     beliebige gültige `write_table`-Pipelines erzeugt und
│   │   │     `verify_operation` grün beweist (ci/dev/nightly-Profile).
│   │   │   - W3a ✅ (local): Der echte 15.8-Source-Fix.  `PQL.sql`
│   │   │     auto-projiziert `_lineage_row_id` auf zeilenerhaltenden
│   │   │     Single-Source-SELECTs (kein GROUP BY/DISTINCT/Aggregat/Set-Op)
│   │   │     via sqlglot-AST (`sql_parser/_lineage_project.py`), damit der
│   │   │     nachgelagerte Write seine Row-Edges behält; kollabierende
│   │   │     SELECTs bleiben bewusste Grenzen + werden explizit geflaggt
│   │   │     (`preserve_lineage_row_id=False` als Opt-out).  Write/Merge
│   │   │     stempeln `lineage_row_id_absent_at_write`, wenn eine deklarierte
│   │   │     Quelle ohne Id-Spalte 0 Edges erzeugt — nie mehr still.
│   │   │     Property-Test fährt bronze→SELECT→silver und beweist, dass das
│   │   │     absichtlich abgeschaltete Auto-Project als INV-1-Drop *die Suite*
│   │   │     rot macht.  Negativ-Test retargetet.
│   │   │   - W3b ✅ (local): Operator-Wellen merge (Upsert-Edges + Rejects
│   │   │     on_key_null/duplicate_in_source + CDF-Value-Changes), aggregate
│   │   │     (N:1-Group-Key-Synthese, INV-2 korrekt übersprungen) und
│   │   │     update (In-Place-Value-Changes, INV-5) als Hypothesis-
│   │   │     Property-Klassen — jede fährt echte PQL-Primitive + prüft
│   │   │     `verify_operation` grün.  INV-4 verfeinert: nur
│   │   │     spalten-etablierende Ops schulden Column-Map-Coverage (In-Place-
│   │   │     update/delete ausgenommen).  delete/autoload/branch-governance/
│   │   │     federation werden im Coverage-Ledger (W5) explizit geführt
│   │   │     (keine stillen Lücken).
│   │   │   - W4 ✅ (local): OpenLineage-Differential — fängt das emittierte
│   │   │     Event ab (ohne Live-Server) und beweist, dass columnLineage- +
│   │   │     valueChange-Facets exakt den lokalen Lineage-Tabellen
│   │   │     entsprechen (kein Drift interne Wahrheit ↔ exportierter Graph).
│   │   │     Golden-Corpus (`tests/lineage_verify/corpus/*.json`):
│   │   │     deterministische Pipelines (Unicode-Spalten, NULL-/Dup-Merge-
│   │   │     Keys, Multi-Column-Group-By) mit eingefrorenen, sortiert-
│   │   │     diffbaren Edge-/Column-/Value-Snapshots; Regen via
│   │   │     `LINEAGE_CORPUS_UPDATE=1`.
│   │   │   - W5 ✅ (local): CI-Verdrahtung — der `lineage_verify`-Marker läuft
│   │   │     im PR-Gate (lean `ci`-Profil) und in einem neuen
│   │   │     `nightly.yml`-Cron-Job mit großem `nightly`-Budget.
│   │   │     Coverage-Ledger (`test_coverage_ledger.py`): klassifiziert jeden
│   │   │     PQL-Operator (property/deferred/n-a) und schlägt fehl, wenn ein
│   │   │     neuer Operator ohne Lineage-Coverage-Entscheidung erscheint —
│   │   │     keine stillen Lücken.  Schließt Phase 197.
│   │   │
│   ├── Phase 198 — E2E-in-CI Vollabdeckung  🟦 backbone (local, 2026-06-07; tests deferred)
│   │   │   Detail: [`docs/internal/phase-198.md`](docs/internal/phase-198.md).
│   │   │   Fortsetzung von Phase 190 (Tier-1/2 ≈14): alle 92
│   │   │   deterministischen Playbooks → Playwright-in-CI mit
│   │   │   Coverage-Ledger bis 100 %.  soyuz-catalog als CI-Service +
│   │   │   `requires_soyuz`-Marker, Page-Objects, Browser-/Hybrid-/curl-/
│   │   │   Hermes-Wellen, Gate scharf (kein `continue-on-error`).
│   │   │
│   ├── Phase 199 — Performance- & Skalierungs-Härtung  🟦 backbone (local, 2026-06-07; harness deferred)
│   │   │   Detail: [`docs/internal/phase-199.md`](docs/internal/phase-199.md).
│   │   │   Per-Route-Latenz + Query-Dauer instrumentieren → Benchmark-
│   │   │   Harness (1M-Audit, 10k-Lineage-DAG) → Latenz-Budget-Gate
│   │   │   (`check-perf-budget.sh`, Floor-Ratsche wie file-size/pyright) →
│   │   │   Hot-Path-Optimierung (FTS/Lineage/Query-History) unter der
│   │   │   software-composited-UI-Regel (kein backdrop-filter/Animation).
│   │   │
│   ├── Phase 200 — Observability- & SLO-Vollständigkeit  🟦 backbone (local, 2026-06-07; wiring deferred)
│   │   │   Detail: [`docs/internal/phase-200.md`](docs/internal/phase-200.md).
│   │   │   OpenTelemetry-Tracing (Bridge zu vorhandenen Correlation-IDs,
│   │   │   default-off) + RED/USE-Metriken (teilt 199) + SLO-Burn-Rate /
│   │   │   Error-Budget auf dem `slo/`-Kern + synthetische Probes scharf
│   │   │   (Tabellen existieren) + RED/SLO-Grafana-Dashboards + Burn-Rate-
│   │   │   Alerts über `alert_dispatcher`.
│   │   │
│   ├── Phase 201 — Disaster-Recovery & Daten-Lebenszyklus  🟦 backbone (local, 2026-06-07; executors deferred)
│   │   │   Detail: [`docs/internal/phase-201.md`](docs/internal/phase-201.md).
│   │   │   Konsistentes Backup/Restore der eigenen Metadaten-DB (SQLite +
│   │   │   PG) + Schema-Kompat-Gate + Cross-Domain-Konsistenz (DB ↔ Delta ↔
│   │   │   Branches) + vereinheitlichter `retention_sweep` + Restore-
│   │   │   Game-Day als CI-Job + DR-Runbook.
│   │   │
│   ├── Phase 202 — Authz-Matrix & Security-Härtung  🟦 backbone (local, 2026-06-07; matrix-tests deferred)
│   │   │   Detail: [`docs/internal/phase-202.md`](docs/internal/phase-202.md).
│   │   │   Generiertes Authz-Inventar (~800 Endpoints × 11 `require_*`) →
│   │   │   parametrisierte Matrix-Tests (Route × Persona × Status) →
│   │   │   CSP + Security-Header (Report-Only → enforce) → SAST/Secret/
│   │   │   Dep-Scanning in CI (bandit/detect-secrets/pip-audit als Gate) →
│   │   │   Secrets-Key-Rotation-CLI → STRIDE-Threat-Model.
│   │   │
│   ├── Phase 203 — Vollständige MCP-Agent-Oberfläche  🟦 backbone (local, 2026-06-07; executors+wiring deferred)
│   │   │   Detail: [`docs/internal/phase-203.md`](docs/internal/phase-203.md).
│   │   │   Strategische Wette (Agent-first-Pivot).  Heute: 7 read-only
│   │   │   Lens-Tools über FastMCP-Wrapper.  Ausbau zu read **+ governtem
│   │   │   Schreiben** über dieselbe Hook-/Provenance-Kette wie Menschen
│   │   │   (keine MCP-Mutation ohne `AgentRunOperation` + CloudEvent),
│   │   │   versionierte Tool-Coverage-Matrix + Conformance-Suite (stdio +
│   │   │   SSE).  Eng mit 202 (Scopes/Authz).
│   │   │
│   ├── Phase 204 — Data-Quality- & Expectations-Tiefe  🟦 backbone (local, 2026-06-07; wiring deferred)
│   │   │   Detail: [`docs/internal/phase-204.md`](docs/internal/phase-204.md).
│   │   │   Aus verstreuten Checks (Phase 36 Contract-Tests, Drift, Mesh-
│   │   │   Health) ein Bild: reichere Profilierung + erweitertes
│   │   │   Expectation-Vokabular + Anomalie als Signal + per-Product
│   │   │   Quality-Scorecard (neuer Tab) + Quality-Gate vor dem Write
│   │   │   (off/warn/block, wie schema-versioning `_enforcer`).
│   │   │
│   ├── Phase 205 — Accessibility (WCAG-AA) Compliance  🟦 backbone (local, 2026-06-07; frontend fixes deferred)
│   │   │   Detail: [`docs/internal/phase-205.md`](docs/internal/phase-205.md).
│   │   │   axe-core auf der Playwright-Infra (Violations-Floor-Ratsche) +
│   │   │   globale Primitive (Landmarks/Skip-Link/Fokus nach HTMX-Swap) +
│   │   │   Formulare/Modals/Popover + Tastatur-Nav + Risiko-Widgets
│   │   │   (cytoscape-DAG/Canvas/CodeMirror mit Text-Alternative) +
│   │   │   Biome-a11y/Kontrast.  `prefers-reduced-motion` (Phase 184) als
│   │   │   Vorlage.  0 critical/serious.
│   │   │
│   └── Phase 206 — Cost/FinOps- & Kapazitäts-Tiefe  🟦 backbone (local, 2026-06-07; tables+dashboard deferred)
│       │   Detail: [`docs/internal/phase-206.md`](docs/internal/phase-206.md).
│       │   Auf Phase 146 (Attribution/Quotas) aufbauend: Chargeback-Reports
│       │   (Pivot über consumer/product/workspace) + Budgets mit Burn-
│       │   Vorwarnung (warn 80 % / block 100 %, Signals) + Forecast/
│       │   Kapazität („Budget erreicht in N Tagen") + Cost am Agent-Run +
│       │   FinOps-Grafana-Panels.  estimated_cost = Schätzung, kein $.
│   │
├── Phase 212 — UX-Loop: interaktions-getriebener Klickpfad-Sweep  🔄 laufend (local, 2026-06-13)
│   │
│   │   Anders als Phase 211 (statischer Screenshot-Audit) werden hier
│   │   die Klickpfade *live* begangen (Playwright + a11y-Snapshot),
│   │   jede Fläche sofort bewertet und schlechte UX an der Quelle
│   │   gefixt.  Befunde + Fixes landen pro Iteration.
│   │
│   ├── 212.1 — Default-Workspace-Beschreibung entjargonisiert  ✅ shipped (local, 2026-06-13, `b43a14b0`)
│   │       Die Seed-Beschreibung des Default-Workspace zeigte „Auto-
│   │       created by Sprint 28.0 bootstrap … pre-dates Phase 28's
│   │       workspace isolation" direkt im Header — Release-Jargon, das
│   │       die no-phase-refs-Gate nicht greift (Daten-Zeile, kein
│   │       Template-String).  Forward-Daten-Migration schreibt die
│   │       Beschreibung um, geschützt auf den alten Seed-Text (Hand-
│   │       Edits bleiben unangetastet).
│   │
│   ├── 212.2 — Workspace-Pin per Suche statt Roh-ID  ✅ shipped (local, 2026-06-13, `4d265073`)
│   │       Das „Pin entity"-Modal verlangte eine numerische
│   │       social_target_id, nachzuschlagen „via the entity's detail
│   │       page network panel" (= Browser-DevTools); kein Entity-Page
│   │       bietet eine Pin-Aktion → Feature praktisch unbenutzbar +
│   │       literale Doppel-Backticks (kein Markdown im Template).
│   │       Jetzt Typeahead über `/api/search`: Name tippen, Catalog/
│   │       Schema/Table/Data-Product wählen, fertig.  POST nimmt ein
│   │       `{kind, ref}`-Paar und löst es serverseitig über denselben
│   │       `get_or_create_target`/`resolve_dp_target`-Resolver auf wie
│   │       der Rest des Social-Stacks; `{social_target_id}` bleibt
│   │       kompatibel.  Dup/unresolvable → klare 409/400 inline.
│   │
│   ├── 212.3 — Data-Product-Titel nicht doppelt  ✅ shipped (local, 2026-06-13, `0b5b21da`)
│   │       Der DP-Header zeigte Name + gemuteten Ref; da Name meist =
│   │       Ref (catalog.schema), las er „demo.sales demo.sales".  Ref
│   │       jetzt nur sichtbar, wenn er sich vom Namen unterscheidet.
│   │
│   ├── 212.4 — Mesh-Graph hing auf „Loading…"  ✅ shipped (local, 2026-06-13, `404927b4`)
│   │       Die Graph-Card ist `x-show="!loading"`-gegated; render()
│   │       lief im `$nextTick` direkt nach `loading=false` und feuerte
│   │       cytoscapes synchrone Canvas-/Layout-Arbeit im selben Alpine-
│   │       Zyklus wie das noch ausstehende show-Effect → cytoscape maß
│   │       einen 0×0-Container, das x-show-Effect blieb hängen, die Card
│   │       wurde nie sichtbar.  render() jetzt im Makrotask: Alpine deckt
│   │       die Card (600 px) erst auf, dann misst+zeichnet cytoscape.
│   │
│   ├── 212.5 — DP-Interop-Graph blieb leer  ✅ shipped (local, 2026-06-13, `2eb5e0b5`)
│   │       Gleiche Klasse, anderer Auslöser: der Neighbourhood-Graph
│   │       liegt in einem Bootstrap-Tab (display:none bis geöffnet),
│   │       render() lief im init-`$nextTick` → cytoscape maß 0×0, blieb
│   │       leer auch nach Tab-Klick.  Render jetzt hinter einem
│   │       IntersectionObserver: erst wenn der Container sichtbar wird.
│   │
│   ├── 212.6 — `.ipynb`-Notebooks führten in den 422-Editor  ✅ shipped (local, 2026-06-13, `0fefeb93`/`1b31cb9b`)
│   │       Der In-Browser-Editor akzeptiert nur `.py` (jupytext); ein
│   │       `.ipynb`-Pfad 422t mit „Something went wrong".  Sidebar-Tree
│   │       UND Rechtsklick-Menü verlinkten aber jedes Notebook (auch
│   │       `.ipynb`) in den Editor → toter Klickpfad auf
│   │       getting_started.ipynb + den Smoke-Notebooks.  `.ipynb` zeigt
│   │       jetzt auf den Workspace-Browser (Schedule/Run); `.py` weiter
│   │       in den Editor — wie die Edit-Button-Gating im Haupt-Tree.
│   │       Verifiziert nicht-Bugs (kein Fix): Lineage-DAG rendert korrekt
│   │       (Synthetik-Test), Runs-Tabelle ist responsiv (Card-Collapse),
│   │       Create/Rename erzwingen `.py`.
│   │
│   ├── 212.7 — Canvas-Drops gingen am Leer-Hinweis ins Leere  ✅ shipped (local, 2026-06-13, `2cf4d04d`)
│   │       Der zentrierte „Block hierher ziehen"-Hinweis liegt als Overlay
│   │       über dem Drawflow-Drop-Target und behielt pointer-events → der
│   │       erste Block, genau auf den Hinweis gedroppt, kam nie an (nur
│   │       Drops daneben zählten).  `pe-none` auf den Hinweis; betrifft
│   │       alle vier Canvas-Editoren (DataFrame Studio, DP-Canvas, Mesh-
│   │       Canvas, Job-DAG).  Auf Nutzerwunsch am Studio gefunden.
│   │
│   ├── 212.8 — Canvas-Compile 500te bei kaputtem Tabellennamen  ✅ shipped (local, 2026-06-13, `699fb4c4`)
│   │       Ein Input-Port mit nicht-dreiteiligem FQN (z. B. `demo` oder
│   │       `demo.sales`, leicht beim Tippen) ließ den Schema-Seed-Pass
│   │       soyuz mit dem kaputten `full_name` fragen; die nicht-404-Antwort
│   │       wurde reausgeworfen → Studio Compile/Preview + DP-Canvas-
│   │       Validate/Preview lieferten 500 „An unexpected error occurred."
│   │       Seed überspringt jetzt nicht-dreiteilige FQNs (wie der Block-
│   │       Compiler selbst); der meldet das `bad_config` graziös.  Gültiger
│   │       FQN kompiliert weiter.  Happy-Path (Drag→Tabelle→Compile→SQL)
│   │       end-to-end verifiziert.
│   │
│   └── 212.9 — Lineage-Explorer-Traces 404ten  ✅ shipped (local, 2026-06-13, `b5cbb40a`)
│   │       „Trace a row"/„Trace a column" auf `/lineage` navigierten zu
│   │       `/tables/<fqn>/rows|columns/…/trace` — eine Route, die es nicht
│   │       gibt → „Page not found".  Die echten Seiten liegen unter dem
│   │       gesplitteten FQN-Pfad (`/catalogs/<c>/schemas/<s>/tables/<t>/
│   │       rows|columns/…/trace`).  `goRow`/`goColumn` splitten den
│   │       dreiteiligen Namen jetzt korrekt; `pattern` auf den Tabellen-
│   │       Inputs gibt nativen Validierungs-Hinweis statt stillem No-op.
│   │       Audit-Inbox + Alerts in dieser Iteration verifiziert (kein Fix).
│   │
├── Phase 211 — Bootstrap-UI-Audit: Fixes aus dem 169-Screenshot-Sweep  ✅ shipped (local, 2026-06-13)
│   │
│   │   Umsetzung der Befunde aus `ui-audit/IMPROVEMENT-PLAN.md` (voller
│   │   Headful-Sweep: 774 API-Routen + 169 Screenshots, jede Fläche
│   │   A–F gegen Bootstrap 5.3 bewertet).  Beim Abgleich gegen den
│   │   echten Code waren ~40 % der „bestätigten Bugs" Fehllesungen des
│   │   Screenshot-Audits (Edit-Profile-Gate, Query-History-Badges,
│   │   Social-Tabs erreichbar, Toast-Container vorhanden, DP-Detail
│   │   bereits getabbt, Mesh-Save bereits primary) und blieben bewusst
│   │   unangetastet; umgesetzt wurde das Reale.
│   │
│   ├── 211.1 — Light-Theme-Aurora gezähmt  ✅ shipped (local, 2026-06-13, `30fc15b3`)
│   │       Light-Mode-Aurora-Blobs zu kräftig (Indigo 34 % → Lila-Band
│   │       hinter dem Header), Surfaces zu transluzent.  Blob-Opazität
│   │       in base.css gesenkt, Panels nahezu opak, Border kräftiger;
│   │       Brand-Gradient-Button auf dark gescoped (white-on-bright-
│   │       green-Kontrast in light).  Eine Token-Änderung, ~alle
│   │       Light-Flächen.
│   ├── 211.2 — feed.css backdrop-filter entfernt  ✅ shipped (local, 2026-06-13, `3fd103b3`)
│   │       Zwei Live-Blur-Sticky-Bars → opakes rgba-Fallback (Software-
│   │       Compositor-Perfregel).
│   ├── 211.3 — Geteilte Macros + Adoption  ✅ shipped (local, 2026-06-13, `0653f116`/`9ebe82e3`/`b681b80a`)
│   │       Neu: alert_box / data_table / page_help / stat_tiles in
│   │       `_macros/`.  empty.html über 21 Listen-Leerzustände adoptiert
│   │       (Header-über-Void → Icon+Titel+Message); page_help dedupt 6
│   │       Admin-„What is this page?"-Accordions.
│   ├── 211.4 — Fehler-/Disabled-Rendering  ✅ shipped (local, 2026-06-13, `d0a69f9a`)
│   │       BI-Widget-Fehler amber→danger+Icon; Pipeline-Roh-JSON →
│   │       `<details>`; Chat-Konfig-aus (4503/LLM) als amber-gear statt
│   │       Hart-Rot; README-404 nicht mehr als Error-Toast (silent GET).
│   ├── 211.5 — Tabellen-Chrome  ✅ shipped (local, 2026-06-13, `c8b845cb`)
│   │       ~40 Datentabellen in `.table-responsive` (Inline-Key/Value-
│   │       Editoren bewusst ausgenommen).
│   ├── 211.6 — Mobile-Nav-Doppelmenü  ✅ shipped (local, 2026-06-13, `90c90f26`)
│   │       Offcanvas stapelte Hub-Spokes (Kontext) + nav_links (Hub) →
│   │       Spokes desktop-only gescoped; Wrapper-Klasse trägt die
│   │       First-Header-Ausrichtung am Icon-Rail.
│   ├── 211.7 — Command-Palette als echtes BS-Modal  ✅ shipped (local, 2026-06-13, `6fc9870f`)
│   │       Custom-Overlay → bootstrap.Modal (Focus-Trap, Scroll-Lock,
│   │       Return-Focus); Alpine behält Suche + ↑↓↵; Backdrop-Sweep-
│   │       Sicherheitsnetz; gesättigte Lime-Auswahl → dezenter Akzent.
│   ├── 211.8 — Social-Sub-Tabs deep-linkbar  ✅ shipped (local, 2026-06-13, `6a11c987`)
│   │       `#social-<tab>`-Hash öffnet die Offcanvas-Panes; Öffnen/
│   │       Tab-Wechsel spiegelt zurück (replaceState).
│   ├── 211.9 — Mesh-Graph-Label-Kontrast + BI-Leerzustand  ✅ shipped (local, 2026-06-13, `3cdcccc2`)
│   │       Cytoscape-Node-Labels theme-aware + Text-Outline (waren
│   │       dark-on-dark unsichtbar); BI-„no widgets" → empty.html.
│   ├── 211.10 — Badge-Auto-Kontrast  ✅ shipped (local, 2026-06-13, `9f84ea58`)
│   │       370 `badge bg-*` → `text-bg-*` über 128 Templates (Bootstrap-
│   │       Auto-Kontrasttext); `-subtle`-Varianten + dynamische `:class`
│   │       unangetastet; zwei String-Assert-Tests retargeted.
│   ├── 211.11 — Readable-Width-Cap (opt-in)  ✅ shipped (local, 2026-06-13, `e163c42b`)
│   │       `pql-content--readable`-Modifier (via `content_class`-Block)
│   │       cappt Prosa/Formular-Seiten auf 64rem; Help/Me-settings/
│   │       Governance opt-in.  Datentabellen-Seiten bewusst NICHT (Cap
│   │       würde Tabellen nur schmaler machen — Audit-Übergeneralisierung).
│   └── 211.12 — Einmal-Secrets maskiert + Reveal-Toggle  ✅ shipped (local, 2026-06-13, `4370dc86`)
│   │       API-Key-Plaintext + Sharing-Bearer-Token default `type=password`
│   │       mit Auge-Toggle; Copy nutzt weiter den Rohwert.
│   │
│   │   Nicht umgesetzt (Audit-Übergeneralisierung / Design-Urteil):
│   │   flächendeckende Button-Hierarchie-Recolors („ein Primary pro
│   │   Region") — die konkreten Audit-Beispiele (warning-Save 078) waren
│   │   Fehllesungen; Form-Grid-Retrofit (A11y-Labels per Gate schon
│   │   erzwungen, sichtbare-Label-Politur niedrigwertig).  Stat-tiles-
│   │   Macro liegt einsatzbereit, noch ohne Konsumenten.
│   │
├── Phase 210 — Databricks-Parität Runde 2: Top-10 aus der Juni-Recherche  ✅ shipped (local, 2026-06-11)
│   │
│   │   Zweites Deep-Research-Programm (offizielle Databricks-Blogs/
│   │   Docs DAIS 2024/2025, Community-Stimmen HN/Foren/G2, eigenes
│   │   Codebasis-Inventar): die zehn wirkungsstärksten verbliebenen
│   │   Lücken, wieder nativ auf dem Stack (DuckDB-Pragmas, sqlglot,
│   │   Scheduler-Backing-Jobs, Subprozess-Manager, UC-Tags) — null
│   │   neue Python-Runtime-Deps.  Gewichtung: Community-Killer-QoL
│   │   (Query Profile, Debugger, Repair Run) + DAIS-2025-Welle
│   │   (DQ-Monitoring, AI Functions, Apps, ABAC) + Workflow-as-Code
│   │   (Asset Bundles).
│   │
│   ├── 210.1 — Query Profile (Runtime-Profiling)  ✅ shipped (local, 2026-06-11)
│   │       Profile-Button neben Explain: der SELECT läuft normal
│   │       und DuckDBs JSON-Profil wird aus derselben Ausführung
│   │       gefangen (profiling-to-tempfile, Ergebnis unangetastet).
│   │       Summarizer flacht den Baum defensiv über Key-Drift
│   │       (operator_type/name, operator_timing/timing) in eine
│   │       slowest-first Operator-Liste; Panel über der Ergebnis-
│   │       tabelle (Balken = Zeitanteil); Roh-Baum persistiert auf
│   │       query_history.profile_json.  Policies greifen exakt wie
│   │       beim normalen SELECT.  Playbook query-profile.md.
│   │
│   ├── 210.2 — AI Functions in SQL  ✅ shipped (local, 2026-06-11)
│   │       ai_query/ai_classify/ai_extract/ai_translate (LLM) +
│   │       ai_mask (deterministisch, pii-Masker) als DuckDB-UDFs,
│   │       registriert pro Query in run_sql — SQL-Editor, Notebook-
│   │       SQL-Zellen, BI-Widgets, Metric Views und Pipelines erben
│   │       dieselbe Vokabel.  Pro-Query-Runner mit Distinct-Args-
│   │       Dedup-Cache und hartem max_calls_per_query-Budget;
│   │       Credentials wie Genie (Workspace-Lens-Creds, Env-Key-
│   │       Fallback); POINTLESSQL_AI_FUNCTIONS_*-Settings.
│   │       Playbook ai-functions.md.
│   │
│   ├── 210.3 — Jobs v2 (Orchestrierung)  ✅ shipped (local, 2026-06-11)
│   │       Repair Run (neuer Run reused erfolgreiche DAG-Tasks,
│   │       führt nur Fehlgeschlagenes/Übersprungenes aus;
│   │       trigger="repair" + repair_of_run_id-Kette), run_if pro
│   │       Task (all_success-Default unverändert, all_done für
│   │       Cleanup, at_least_one_failed für Error-Handler — unmet
│   │       Conditions landen im neuen benignen "excluded"-Status),
│   │       for_each pro Task (Item-Liste, sequenziell, item in die
│   │       Config gemerged), Event-Trigger file_arrival (Glob-
│   │       Fingerprint) + table_update (Delta-Version-Poll als
│   │       Run-as-Principal) mit stiller Baseline + Cursor-
│   │       Persistenz, notify_on (In-App-Notification an den
│   │       Run-as-User).  Playbook jobs-v2.md.
│   │
│   ├── 210.4 — Tag Policies + Auto-PII-Klassifikation (ABAC)  ✅ shipped (local, 2026-06-11)
│   │       Deployment-globale Regeln auf UC-Tags: mask-Regeln
│   │       maskieren jede getaggte Spalte, row_filter-Regeln ANDen
│   │       ihr Prädikat (current_user()-Substitution) in Reads
│   │       getaggter Tabellen — enforced an beiden SELECT-Choke-
│   │       Points, Admin/Owner exempt, explizite Properties
│   │       gewinnen pro Spalte, fail-closed bei kaputtem Prädikat,
│   │       TTL-Caches + Null-Overhead-Fastpath ohne Regeln.
│   │       PII-Scanner (Namens- + Sample-Regex-Heuristiken: email/
│   │       phone/iban/card/birthdate/address) taggt pii=<kind>
│   │       additiv-only; /admin/classification-Konsole (Regeln-CRUD
│   │       + Scan-Panel) + Executor-Kind pii_classification.
│   │       Playbook data-classification.md.
│   │
│   ├── 210.5 — Data Quality Monitoring  ✅ shipped (local, 2026-06-11)
│   │       Monitore auf Tabelle oder Schema, Profil-Snapshots über
│   │       die table-stats-Engine (+ Delta-Version + Freshness),
│   │       Anomalie-Regeln gegen den Vorgänger-Snapshot:
│   │       volume_drop (<50% critical / <80% warn, 100-Zeilen-
│   │       Floor), null_spike (+0.2/+0.5 absolut), schema_change,
│   │       freshness (>24h).  Offene Anomalien dedupen auf
│   │       (table, column, kind) und resolven automatisch;
│   │       Backing-Job-Muster (kind quality_monitor), Creator-
│   │       Notification, /quality-Cockpit + Nav.
│   │       Playbook quality-monitoring.md.
│   │
│   ├── 210.6 — Access Requests + Zertifizierungen  ✅ shipped (local, 2026-06-11)
│   │       UC-Discover-Schleife: ohne SELECT rendert die Tabellen-
│   │       seite eine Metadaten-Ansicht (USE SCHEMA als Render-
│   │       Gate; effective=[] bleibt 403) + Request-access-Button
│   │       mit Justification; /access-requests mit My-requests- und
│   │       To-decide-Tabs (Admins alle, Owner ihre — Owner-Snapshot
│   │       beim Anlegen); Approve führt den echten UC-Grant über
│   │       die Facade aus, jede Transition fanout-benachrichtigt.
│   │       Zertifizierungen migrationsfrei auf UC-Tags
│   │       (pointlessql.certification + _note): certified-Badge,
│   │       deprecated-Badge + Banner, Owner/Admin-Verwaltung am
│   │       Tabellen-Header.  Playbook access-requests.md.
│   │
│   ├── 210.7 — Hosted Apps  ✅ shipped (local, 2026-06-11)
│   │       Databricks-Apps-förmig: Admins deklarieren eine App aus
│   │       Inline-Source (fastapi via Projekt-uvicorn, streamlit
│   │       falls installiert — sauberes Gate, oder command),
│   │       AppsManager nach Serving-Muster (Port-Range 9200+,
│   │       Health-Poll <500, stderr-Tail, reset_states_on_boot,
│   │       stop_all im Teardown), Env mit {{secrets/...}}-
│   │       Auflösung, authentifizierter Reverse-Proxy
│   │       /apps/{slug}/proxy/ inkl. bidirektionaler WS-Bridge
│   │       (Close-Codes 4401/4404/4503) und eng begrenzter CSRF-
│   │       Exemption (Begründung in csrf_middleware.py); /apps-
│   │       Liste + Detail (Quellcode-Editor, Log-Tail, iframe).
│   │       Playbook hosted-apps.md.
│   │
│   ├── 210.8 — Dashboard-Schedules + Snapshots  ✅ shipped (local, 2026-06-11)
│   │       Ein Schedule pro BI-Dashboard als Backing-Job (kind
│   │       bi_snapshot, Alert-Muster); Renderer führt alle Widgets
│   │       serverseitig unter den Privilegien des Schedule-
│   │       Erstellers aus (Widget-Fehler → error-Feld statt
│   │       Abbruch), Snapshots frieren die Payloads ein und rendern
│   │       read-only unter /bi/{slug}/snapshots/{id} (Lesen Owner/
│   │       Admin-gated — Snapshots tragen die Sicht des Erstellers,
│   │       nicht des Viewers); Zustellung in-app + optional HMAC-
│   │       CloudEvents-Webhook; Dashboard-Delete räumt Schedule
│   │       (inkl. Job) + Snapshots.  Playbook dashboard-snapshots.md.
│   │
│   ├── 210.9 — Notebook-Debugger  ✅ shipped (local, 2026-06-11)
│   │       Step-Through über das Jupyter Debug Protocol (debugpy in
│   │       ipykernel 7): KernelSession.debug_request über den
│   │       Control-Channel (session-eigener seq-Zähler — mehrere
│   │       Tabs teilen einen Kernel; Server bleibt dummer DAP-
│   │       Proxy), debug_events als WS-Notify an alle Tabs,
│   │       Debug-Panel (Paused-Badge, klickbare Frames, Variablen,
│   │       Continue/Next/Step/Stop), Breakpoints per Zeilenfeld
│   │       (Gutter-Marker unter Co-Edit bewusst verworfen — Zeilen
│   │       verschieben sich), Debug-Lauf nutzt den normalen
│   │       execute-Pfad (Outputs/Run-History identisch); Stop/
│   │       Close disconnecten immer (kein geparkter Kernel).
│   │       Integrationstest gegen echten ipykernel.
│   │       Playbook notebook-debugger.md.
│   │
│   ├── 210.10 — Asset Bundles  ✅ shipped (local, 2026-06-11)
│   │       Workspace-as-Code nach DAB-Vorbild: ein YAML deklariert
│   │       Jobs (inkl. DAG-Tasks, run_if/for_each, Trigger,
│   │       notify_on), Pipelines und BI-Dashboards; Planner difft
│   │       per name/slug in create/update/unchanged mit Feld-Notes
│   │       (Orphans nur informativ, nie Deletes), Applier
│   │       idempotent (Re-Apply konvergiert; Task-Abgleich per
│   │       Name, Widgets gehören dem Bundle (kind+title-Match,
│   │       Überzählige gelöscht), validate_dag vor Commit,
│   │       Fehler pro Ressource isoliert), Export→Parse→Plan ist
│   │       Fixpunkt (getestet; einzige Abweichung: Saved-Query-
│   │       Widgets exportieren mit Inline-SQL).  /admin/bundles
│   │       (20. Karte) + CLI `pointlessql bundle
│   │       validate|plan|apply|export` (in-process, --run-as).
│   │       Playbook asset-bundles.md.
│   │
│   ├── Offene Folge-Tranchen (geplant)
│   │       Profile-Replay aus der Query-History-UI (profile_json
│   │       liegt schon); ai_*-Batch-Vektorisierung + Kosten-Spalte
│   │       in der History; Repair-Run für Pipeline-Runs; ABAC auf
│   │       Schema-/Catalog-Tags (heute Tabelle/Spalte); DQ-Monitore
│   │       mit konfigurierbaren Schwellen + Webhook-Zustellung;
│   │       Access-Requests für Schemas/Volumes; Apps mit
│   │       Requirements-Installation (heute Projekt-Env) + Public-
│   │       Token-Apps; Snapshot-Read-Zugriff für Viewer (bewusste
│   │       Gating-Entscheidung, s. 210.8); Debugger-Gutter-Marker
│   │       via CodeMirror-StateField; Bundles: TaskRun-FK-Verhalten
│   │       beim Task-Delete auf Postgres prüfen + Alerts/Monitore
│   │       als Bundle-Ressourcen.  Pyright-Floor 1073 → derselbe
│   │       Stub-Pass wie bei 209.
│   │
├── Phase 209 — Databricks-Parität: Top-10-Features  ✅ shipped (local, 2026-06-11)
│   │
│   │   Deep-Research-Programm (Web + beide Codebasen): die zehn
│   │   wirkungsstärksten noch fehlenden Databricks-Features, nativ
│   │   gebaut auf dem vorhandenen Stack (sqlglot/duckdb/deltalake/
│   │   Scheduler/LLM-Verdrahtung) statt Framework-Einbettung —
│   │   null neue Python-Runtime-Deps als Designziel.  Reihenfolge:
│   │   Secrets → Metric Views → Dashboards → Genie → Serving →
│   │   Delta Sharing → Synced Tables → Pipelines → Row Filters →
│   │   Auto Loader.  soyuz-Anteile (Metric-View-Ressource +
│   │   Delta-Sharing-Server) laufen als eigener soyuz-Sprint.
│   │
│   ├── 209.1 — Secret Scopes  ✅ shipped (local, 2026-06-11)
│   │       Databricks-förmige Secret Scopes auf dem bestehenden
│   │       Fernet-Vault (system_keys-Masterkey): drei Tabellen
│   │       (Scopes/Secrets/ACLs, workspace-scoped), ACL-Leiter
│   │       READ < WRITE < MANAGE (Admins implizit MANAGE,
│   │       Creator-Grant, '*'-Wildcard), /api/secrets mit
│   │       Write-only-Werten (ungranted Scopes antworten 404 —
│   │       Existenz ist selbst ein Geheimnis), auditierter
│   │       Runtime-Getter (Browser + via:kernel getrennt),
│   │       Admin-Cockpit als 17. Karte (+ Playbook
│   │       admin-secrets.md; admin-console.md von stale 8 auf
│   │       real 17 Karten korrigiert), pql_secrets.get() im
│   │       Kernel-Bootstrap (POINTLESSQL_WORKSPACE_ID neu
│   │       injiziert) und {{secrets/<scope>/<key>}}-Auflösung
│   │       just-in-time im Ingest-Executor.
│   │
│   ├── 209.2 — AI/BI Dashboards  ✅ shipped (local, 2026-06-11)
│   │       Lakeview-förmige Widget-Dashboards, getrennt von den
│   │       Notebook-Dashboards: bi_dashboards/bi_dashboard_widgets
│   │       (chart|counter|table|markdown; Inline-SQL oder Saved
│   │       Query; gridstack-Rechteck + ECharts-Spec als Client-
│   │       interpretiertes JSON), typgeprüfte Parameter-
│   │       Substitution ({{param}} → escaptes Literal, Zahlen
│   │       re-emittiert), Widget-Daten durch dieselbe SELECT-
│   │       Enforcement wie der SQL-Editor (Viewer-Principal;
│   │       Public-Token-Pfad läuft als Owner = Embedded
│   │       Credentials), /bi-Liste + Grid-Editor (Drag/Resize,
│   │       Widget-Drawer, Layout-Autosave) + /bi/public/{token}
│   │       auf dem Share-Layout.  ECharts + gridstack via
│   │       Importmap (esm.sh, gepinnt) mit sichtbarer Degradation
│   │       bei CDN-Ausfall.  Playbook bi-dashboards.md.
│   │
│   ├── 209.3 — Metric Views (Semantic Layer)  ✅ shipped (local, 2026-06-11)
│   │       soyuz speichert die Definitionen (Über-Spec-Ressource,
│   │       dortiges ADR-0014); PointlesSQL kompiliert: sqlglot-
│   │       Compiler (Dimensionen/Measures/Filter → ein DuckDB-
│   │       SELECT; jedes Fragment muss als einzelner Ausdruck
│   │       parsen, Statements/Subqueries abgelehnt), Ausführung
│   │       durch SELECT-Enforcement + Read-Policies wie der
│   │       SQL-Editor, /metric-views-Browser (Picker,
│   │       Definitions-Editor, Query-Panel mit kompilierter SQL
│   │       als Provenance) + Nav.  Playbook metric-views.md.
│   │
│   ├── 209.4 — Row Filters + Column Masks  ✅ shipped (local, 2026-06-11)
│   │       Governance auf dem Lesepfad als Table-Properties
│   │       (pointlessql.row_filter mit current_user()-
│   │       Substitution; pointlessql.mask.<col> = redact|hash|null
│   │       oder {col}-Template) — heute schon editierbar über die
│   │       bestehende Properties-Card.  Enforcement an der
│   │       Engstelle, durch die jeder PQL-Read muss:
│   │       register_delta_view bindet den gepunkteten Namen an
│   │       eine Policy-View über der internen Basis-Relation —
│   │       keine Query-Form erreicht Rohdaten (Aggregate
│   │       inklusive).  Die Enforcement-Hops sammeln Policies
│   │       neben approved_tables (SQL-Dispatcher, Notebook-SQL-
│   │       Zellen inkl. repr-Kerneltransfer, BI-Widgets, Metric
│   │       Views, Pipelines); Admins + Table-Owner sind exempt.
│   │
│   ├── 209.5 — Model Serving  ✅ shipped (local, 2026-06-11)
│   │       Registry-Modelle als REST-Inference-Endpoints:
│   │       serving_endpoints-Lifecycle (stopped/starting/ready/
│   │       failed; Boot-Reset, Worker überleben den Prozess nie),
│   │       ServingManager mit einem `mlflow models serve`-Child
│   │       pro gestartetem Endpoint auf konfiguriertem Loopback-
│   │       Portbereich (Health-Poll, stderr-Tail bei Fehlstart,
│   │       Lifespan-Teardown), auditierter /invocations-Proxy im
│   │       MLflow-Scoring-Protokoll hinter PointlesSQL-Auth;
│   │       ohne [ml]-Extra antworten die Lifecycle-Gates 503.
│   │       POINTLESSQL_SERVING_* dimensioniert den Pool.
│   │       /serving-Konsole: Status-Badges, Start/Stop mit
│   │       Poll-until-ready, Try-it-Drawer für /invocations.
│   │       Playbook model-serving.md.
│   │
│   ├── 209.6 — Delta Sharing (PointlesSQL-Seite)  ✅ shipped (local, 2026-06-11)
│   │       Provider: admin-gated /api/sharing-Proxies über die
│   │       Facade (Shares, Objects, Grants, Recipients mit
│   │       Einmal-Token + Rotate), alles auditiert.  Consumer:
│   │       sharing_providers-Profile (Endpoint + Fernet-
│   │       verschlüsseltes Bearer-Token), minimaler synchroner
│   │       Protokoll-Client (NDJSON-Query → vorsignierte
│   │       Parquet-Downloads → pandas; Größen-Cap; kein
│   │       Bearer-Leak an fremde File-Hosts),
│   │       /api/sharing/providers für Registrierung, Browsing
│   │       und auditierte Previews.  Die Server-Seite lebt in
│   │       soyuz-catalog (dortiges ADR-0015).  UI: /admin/sharing
│   │       (18. Admin-Karte; Einmal-Token-Modal mit Copy +
│   │       Nie-wieder-Warnung) + /shared-with-me (Profile,
│   │       Browsing, gecappte Previews).  Playbook
│   │       delta-sharing.md.
│   │
│   ├── 209.7 — Deklarative Pipelines  ✅ shipped (local, 2026-06-11)
│   │       Lakeflow-Idiom nativ auf dem vorhandenen Stack:
│   │       Datasets als validiertes JSON-Dokument (Target-FQN,
│   │       materialized_view|streaming_table, SELECT,
│   │       Expectations), DAG aus sqlglot-Refs (Zyklen abgelehnt),
│   │       MVs rechnen voll neu (Arrow-Pfad ohne Row-Cap),
│   │       Streaming Tables lesen das CDF der einzigen Quelle ab
│   │       Cursor (Batch als Temp-Delta unter dem Quellnamen
│   │       gebunden → das gespeicherte SQL läuft wortwörtlich;
│   │       erster Lauf = Backfill, leerer Feed = Skip),
│   │       Expectations warn/drop/fail mit Metriken am Run.
│   │       Routen machen die async-Vorarbeit (Enforcement +
│   │       Policies je externer Ref als Caller), Engine via
│   │       run_sync; Scheduler-Kind pipeline_run als Run-as-User.
│   │       /pipelines-Editor + Run-Historie mit Violation-Badges;
│   │       Playbook pipelines.md.
│   │
│   ├── 209.8 — Genie-Spaces  ✅ shipped (local, 2026-06-11)
│   │       Kuratierte NL-Datenräume auf der Lens-LLM-Verdrahtung:
│   │       ein Space kuratiert Tabellen + Metric Views +
│   │       Instructions + Trusted-Q→SQL-Beispiele; Fragen laufen
│   │       durch einen Kontext-Builder (kompakte DDL aus dem
│   │       Catalog, Metric-View-Specs, Few-Shots, harter
│   │       Zeichen-Cap) zu EINEM LLM-generierten DuckDB-SELECT,
│   │       das parsen muss, nur kuratierte Tabellen referenzieren
│   │       darf und dann durch SELECT-Enforcement + Read-Policies
│   │       läuft.  Antworten persistieren mit SQL als Provenance;
│   │       Daumen-Feedback, Owner-Promote → Trusted Asset.
│   │       /genie-Liste + Space-Raum (Chat, Asset-Chips,
│   │       Config-Drawer); fehlende BYO-Credential → 503 mit
│   │       eigenem Error-Code.  Playbook genie-spaces.md.
│   │
│   ├── 209.9 — Synced/Online Tables  ✅ shipped (local, 2026-06-11)
│   │       Lakebase-lite Reverse-ETL: synced_tables mappen eine
│   │       UC-Quelle auf ein SQLAlchemy-Ziel (URL darf
│   │       {{secrets/…}}-Platzhalter tragen); full = Truncate-
│   │       Load, cdf = Change-Feed ab Versions-Cursor als portable
│   │       Per-PK-Upserts (erster Lauf = Backfill).  Lookup-API
│   │       nur über deklarierte PK-Spalten, Werte gebunden.
│   │       /online-tables-Seite mit Status, Sync-now,
│   │       Lookup-Tester; Scheduler-Kind table_sync.  Playbook
│   │       online-tables.md.
│   │
│   ├── 209.10 — Auto Loader + Direct-Write-Streams  ✅ shipped (local, 2026-06-11)
│   │       Auto Loader: Processed-Files-Registry macht File-Glob-
│   │       Pulls inkrementell (Discover minus Verarbeitet, Append
│   │       je Datei at-least-once); Mappings opt-in via
│   │       pull_mode="auto_loader", Default-Pfad byte-identisch.
│   │       Zerobus-lite: POST /api/ingest/streams/{c}/{s}/{t}
│   │       puffert JSON-Rows in-process (Flush nach Größe/Alter,
│   │       Force-Flush-Endpoint) und appended Micro-Batches mit
│   │       additivem Schema-Merge; MODIFY-Enforcement wie der
│   │       SQL-Dispatcher, auditiert, Drain im Lifespan-Teardown.
│   │       Playbook ingest-streaming.md.
│   │
│   ├── Offene Folge-Tranchen (geplant)
│   │       Dashboard-Refresh-Schedules + E-Mail-Abos (Scheduler/
│   │       Alerts-Unterbau steht); Metric-Views als Genie-/BI-
│   │       Datenquelle erster Klasse (heute: Tabellen + manuelle
│   │       Specs); SQL-Editor-Makro metric_view(<name>); Kafka-
│   │       Quelle für Streams (heute Direct-Write + Auto Loader);
│   │       S3-Discovery für den Auto Loader; Row-Filter/Mask-
│   │       Editor-Card an der Tabellenseite (heute Properties-
│   │       Card); Stream-Buffer-Settings-ifizierung
│   │       (POINTLESSQL_INGEST_STREAM_*); Serving-Endpoint-
│   │       Metriken (Latenz-Histogramme); Sharing: CDF-/
│   │       Zeitreise-Queries (soyuz antwortet 501) + Cloud-
│   │       Schemes.  Pyright-Floor 1027 → Stub-Pass für die
│   │       pandas/pyarrow-Seams.
│   │
├── Phase 208 — Infrastruktur-Redesign (Querschnitt + CI-Grün)  ✅ shipped (local, 2026-06-11)
│   │
│   │   "Wenn wir die Codebasis heute neu designen würden" als
│   │   verhaltenserhaltende Refactors umgesetzt — plus die Entdeckung,
│   │   dass CI seit Wochen rot war (Lint-Job starb am Ruff-Step und
│   │   maskierte alles dahinter) und die komplette Altlasten-Tilgung.
│   │
│   ├── CI erstmals grün (Altlasten-Tilgung)
│   │       222 Dateien ruff-formatiert, 24 pyright-Errors auf 0, alle
│   │       271 pydoclint-Verstöße über 139 Dateien bereinigt (12
│   │       parallele Agents), OpenAPI-Snapshot deterministisch
│   │       (explizite operation_id auf den Multi-Method-Proxies),
│   │       Form-Label-Schwelle auf gemessene Baseline (170/175;
│   │       Label-Backlog siehe unten), ORM↔Migrations-Drift behoben
│   │       (correlation_id ×3, SLO-Messspalten, Canvas-Partial-Index),
│   │       CVE-Locks aktualisiert (aiohttp/idna/pip/pyjwt/starlette;
│   │       transformers-Advisory mit Drop-when-Note ignoriert).
│   │
│   ├── Test-Schulden
│   │       12 stale CI-Deselects entfernt (Fixes waren längst da),
│   │       Seam-Fixtures in conftest (uc_client_stub ersetzt ~180 rohe
│   │       app.state-Zuweisungen + ~50 _patch_for_principal-Kopien;
│   │       settings_override, jupyter_workspace, llm_stub),
│   │       test_table_stats als Template migriert, uc_client-Mock pro
│   │       Test frisch (Leak-Fix), node:test-Harness für frontend/js
│   │       (21 Tests: inline_md-Security, humanize_cron, formatSql;
│   │       package.json nur als ESM-Marker, kein npm).
│   │
│   ├── Backend-Infrastruktur
│   │       App-eigener, settings-dimensionierter Executor hinter
│   │       run_sync (ContextVar-treu; 105 Route-Sites migriert,
│   │       Background-Loops bewusst auf to_thread; Gate
│   │       check-sync-bridge.sh).  Typisierter Principal:
│   │       get_optional_user (None-erhaltend für nullable
│   │       actor-Spalten) + 21 rohe request.state.user-Sites migriert
│   │       (Gate check-typed-principal.sh; Pyright-Floor 1029→1013).
│   │       Shared-WS-Gerüst: authenticate_or_close für vier Handler
│   │       (Wire-Bytes je Konsument erhalten) + _editor_chat_ws-Engine
│   │       fürs ~85%-identische Chat-Paar (sql 450→136 LOC, notebook
│   │       400→67; String-Patch-Ziele unverändert).  Kernel-WS,
│   │       Coedit-Loop-Paar und Hermes-Proxy bewusst NICHT vereinheitlicht
│   │       (falsche Seams: anderes Wire-Verhalten).  Error-Registry
│   │       war bereits deklarativ (Klassenattribute) — nur verifiziert.
│   │
│   ├── Frontend-Infrastruktur
│   │       Inline-Script-Exodus: theme_boot.js + layout_boot.js
│   │       (klassisch, render-blocking, vor dem ersten Stylesheet;
│   │       Gate check-theme-boot-order.sh), CDF-Tail-Shims + beide
│   │       Embeds extern, Social-Drawer-IIFE → Jinja-Flag.
│   │       Per-Page-Entries: {% block page_entry %} + entries/-Module;
│   │       Full-Loads laden das Entry als statisches module-<script>
│   │       NACH der Importmap und VOR Alpine (Dokumentreihenfolge =
│   │       deterministisch), Boost-Swaps über x-ignore +
│   │       page_entry_loader (afterSwap/historyRestore).  Gelernte
│   │       Falle: Alpine 3 deferred beim Start ALLE Direktiven-Handler
│   │       — x-ignore greift im Initial-Walk NICHT (Flag wird erst
│   │       nach dem Walk gesetzt); und ein Modul-Load vor der
│   │       Importmap annulliert sie ("Import maps are not allowed
│   │       after a module load").  bootstrap.js 154→139 window-Globals
│   │       (Ratchet check-frontend-bootstrap-budget.sh): Admin-Konsole
│   │       (9 Seiten), Agent-Profil, Hermes, 3 Listen-Piloten.
│   │       pqlApi-Migration: DP-Overview/Social/Content (44 Sites,
│   │       silent:true, Fehlertexte identisch); Raw-fetch-Ratchet
│   │       200→156 (check-frontend-raw-fetch-budget.sh).
│   │       Live-verifiziert (Firefox): Cold-Loads, Boost-Kette,
│   │       History-Restore; DP-Detail rendert die migrierten Panels.
│   │
│   ├── Offene Folge-Tranchen (geplant)
│   │       Restliche DP-Detail-/Browse-Entries; topics/issues/glossary/
│   │       domains-Entries; lens/catalog_tree/feed-Fetch-Migration;
│   │       mention_autocomplete (braucht aborted-Flag) und
│   │       Text-Response-Sites (braucht parse:'text') in pqlApi;
│   │       http.js-Löschung (toter Cookie-CSRF-Wrapper, Bugfix-
│   │       Charakter, via notebook-cell-social.md verifizieren);
│   │       Form-Label-Backlog abtragen (170 → Schwelle schrittweise
│   │       senken); services/-to_thread-Sites bei Bedarf auf einen
│   │       eigenen Background-Pool.  Known Issue (vorbestehend):
│   │       htmx-History-Snapshots konservieren Alpine-gerenderte
│   │       x-for-Klone des Chromes (Command-Palette, Footer) — beim
│   │       Restore re-initialisiert der Observer die Waisen und flutet
│   │       die Konsole mit Expression-Warnings (funktional + visuell
│   │       folgenlos); Fix-Kandidat: Klone in htmx:beforeHistorySave
│   │       strippen.
│   │
├── Phase 207 — DP-Canvas Replay-Polish (Playwright-Sweep)  ✅ shipped (local, 2026-06-09)
│   │
│   │   Live-Replay des dp-canvas-builder-Playbooks (Playwright/Firefox,
│   │   headful) mit gezielter Fehlersuche; ein Commit, nur Frontend.
│   │
│   ├── Fixes
│   │       Minimap-Klick-Pan war tot (`pointer-events: none` am Host
│   │       blockte den pointerdown-Handler).  Ctrl+S war im Save-Tooltip
│   │       beworben, aber nie gebunden (öffnete den Browser-Dialog).
│   │       Preview-Modal schloss nicht auf Escape.  Palette-Drop
│   │       ignorierte Pan/Zoom — der Block landete abseits des Cursors.
│   │       Verwaiste "+"-Handles nach Node-Delete (Prune-Pass im Sync).
│   │       Kontextmenü ballonte per shrink-to-fit auf Restbreite und
│   │       lief unter den Config-Drawer (width: max-content + Clamp an
│   │       den Stage-Rand); Tastatur-Kontextmenü (clientX/Y 0,0) ankert
│   │       jetzt am Element statt an der Fensterecke.  Canvas-Popovers
│   │       (Kontextmenü / Quick-Peek / Block-Picker) sind wechselseitig
│   │       exklusiv; der Picker hat eine Titelzeile + Close-Button und
│   │       liest sich nicht mehr als "doppelte Palette".
│   │
│   ├── Robustheit
│   │       CodeMirror-Mounts im Config-Drawer zeigen einen Lade-
│   │       Platzhalter und degradieren bei CDN-Ausfall zu einem nativen
│   │       Eingabefeld (Block bleibt konfigurierbar).  `sql_viewer.js`
│   │       importiert CodeMirror jetzt lazy — die vorherigen Top-Level-
│   │       Imports saßen im statischen Importgraph von `bootstrap.js`,
│   │       sodass ein esm.sh-Ausfall den kompletten Frontend-Bootstrap
│   │       jeder Seite abriss.  Offene Flanke (separater Sweep): die
│   │       Notebook-Coedit-Kette (`coedit_client` / `coedit_awareness`)
│   │       importiert yjs weiterhin top-level.
│   │
│   └── UX
│           Palette-Filterfeld (Label/Hilfe-Suche über 26 Blöcke);
│           Doppelklick oder Enter auf ein Palette-Item setzt den Block
│           kaskadierend in die Bühnenmitte (Undo-fähig, Items sind
│           fokussierbar); Empty-State mit "Add an input port"-Quick-
│           Action; einmaliger, dismissbarer Fokusmodus-Hinweis auf
│           schmalen Bühnen (536 px → 932 px Stage-Gewinn bei 1600 px
│           Viewport); Fokus-Toggle refittet den Viewport.  Gelernte
│           Falle dokumentiert: Bootstraps `d-flex` (`!important`)
│           schlägt Alpines `x-show`-inline-`display:none` — gefilterte
│           Items/Hinweis tragen ihr Flex-Layout jetzt per eigener
│           CSS-Klasse ohne `!important`.
│
├── Phase 188 — Echte Write-Modes (merge / append)  ✅ shipped (local, 2026-06-01)
│   │
│   │   Schließt den latenten Bug, dass der Executor ``mode='merge'`` still
│   │   auf ``overwrite`` abbildete, obwohl die UI Merge + Merge-Keys anbot.
│   │   Neuer ``_write_arrow_to_target``-Helper wendet ``mode`` je Sink korrekt
│   │   an: ``overwrite`` / ``append`` → ``write_deltalake``; ``merge`` → echtes
│   │   Delta ``MERGE INTO`` auf den ``merge_on``-Keys
│   │   (``when_matched_update_all`` + ``when_not_matched_insert_all``),
│   │   ``rows_written`` = inserted + updated aus den Merge-Metriken.  Beim
│   │   *ersten* Materialisieren eines Merge-Sinks existiert die Ziel-Tabelle
│   │   noch nicht — dann degeneriert Merge ohnehin zu Insert-all, also
│   │   seedet der Helper per ``overwrite``-Create und upsertet erst ab dem
│   │   zweiten Lauf.  ``merge_on`` fließt über ``SinkSpec`` durch; der
│   │   Compiler erzwingt es weiterhin bei ``mode='merge'`` (``bad_config``).
│   │   Drei neue pytest mit echtem Delta (append akkumuliert, merge upsertet
│   │   matched+inserted, merge-on required); volle Suite 4132/0/10.
│   │   Backend-only; rc249→rc250.  ALL LOCAL.  Cluster 186–188 komplett.
│   │
├── Fan-out / Multi-Sink Cluster — Phasen 186–188  ✅ shipped (local, 2026-06-01)
│   │   "Aus einer Quelle zwei Tabellen": ein Datenprodukt darf mehrere
│   │   OutputPort-Blöcke (= mehrere UC-Output-Ports) tragen.  Zwischen-
│   │   Fan-out (ein Output → mehrere Ketten) war im Compiler schon frei;
│   │   diese Welle hebt das Ein-OutputPort-Limit auf (186 Backend), zieht
│   │   das Frontend + Plugin nach (187) und implementiert echte
│   │   Write-Modes merge/append (188, schließt den merge→overwrite-Bug).
│   │
├── Phase 187 — Multi-Sink Frontend + Plugin-Lockstep  ✅ shipped (local, 2026-06-01)
│   │
│   │   Das Materialize-Modal trägt jetzt die ``{sinks: [...]}``-Antwort:
│   │   ``openMaterializeModal`` sammelt *alle* OutputPort-Knoten (statt nur
│   │   ``.find``) und zeigt eine Vorschau-Tabelle (Port / Ziel-Tabelle /
│   │   Mode) je Senke; das Ergebnis rendert eine Per-Senke-Tabelle mit
│   │   ok/failed-Badge + Fehlertext + "N von M Senken erfolgreich"-Banner
│   │   (gelb bei Teil-Erfolg).  Plugin-Lockstep in
│   │   ``hermes-plugin-pointlessql``: ``pql_canvas_materialize``-Docstring +
│   │   ``materialize_dp_canvas``-Docstring auf die ``sinks[]``-Form,
│   │   ``test_canvas_tools`` auf die neue Antwort umgestellt (Client gibt
│   │   JSON unverändert durch — kein Code-Change).  Browser-Replay (Firefox)
│   │   verifiziert: Fan-out (ein Filter-Output → zwei OutputPorts) rendert
│   │   sauber mit "no errors", 0 Konsolen-Fehler; Modal listet beide Senken;
│   │   Ergebnis-Tabelle zeigt ok+failed korrekt.  rc248→rc249.  ALL LOCAL.
│   │
├── Phase 186 — Multi-Sink Backbone (Compiler + Executor + Route)  ✅ shipped (local, 2026-06-01)
│   │
│   │   Der Compiler baute schon *eine* gemeinsame CTE-Kette für den
│   │   ganzen DAG und wählte nur *einen* ``final_cte``.  Jetzt trägt
│   │   ``SQLFragment`` eine ``sinks: list[SinkSpec]`` (ein Sink je
│   │   OutputPort, gemeinsame ``ctes``); ``render_sql(fragment, sink)``
│   │   rendert je Sink ``WITH <shared ctes> SELECT * FROM <final_cte_i>``.
│   │   ``_collect_output_nodes`` ersetzt die "exactly one"-Wache (nur noch
│   │   "mindestens eine"); neue ``duplicate_sink``-Diagnose bei doppeltem
│   │   Ziel-FQN / Port-Namen; und die latente Lücke "ein Input-Pin doppelt
│   │   verdrahtet" wird jetzt als ``duplicate_pin`` gemeldet statt still
│   │   die zweite Kante zu verschlucken.  Der Executor löst alle Sink-Ziele
│   │   + Basistabellen vorab auf (fail-fast vor jedem Write), registriert
│   │   die DuckDB-Views einmal und materialisiert dann jeden Sink
│   │   best-effort: ein Laufzeit-Schreibfehler an einem Sink wird als
│   │   ``SinkResult(status="failed", error=…)`` zurückgegeben (+
│   │   ``logger.exception``), die übrigen Sinks laufen weiter.  Jeder Sink
│   │   bekommt seinen eigenen ``operation_context`` (saubere Per-Tabelle-
│   │   Lineage) + ``DataProductOutputPort``-Upsert; alle Sinks teilen eine
│   │   Graph-Version.  ``execute_canvas`` → ``MultiExecuteResult``;
│   │   ``POST /canvas/materialize`` antwortet ``{sinks: [...],
│   │   graph_version}`` (HTTP 200 auch bei Teil-Erfolg).  Keine Alembic-
│   │   Migration (``CanvasDoc``-JSON war schon multi-sink-fähig).  Backend-
│   │   only; volle pytest 4128/0/10.  rc247→rc248.  ALL LOCAL.
│   │
├── Canvas Depth Cluster — Phasen 179–185  ✅ shipped (local, 2026-06-01)
│   │   Sieben-Wellen-Roadmap auf der Phase-178-Basis: A Perf/Edge-Index,
│   │   B Navigation (Minimap-Viewport/Zoom-UI/Space-Pan), C Kontextmenü +
│   │   Inline-Preview, D hindernis-umgehendes Orthogonal-Routing, E Agent-
│   │   Ghost-Diff-Overlay (Differenzierer), F A11y/Reduced-Motion, G Live-
│   │   Drag-Validierung.  Je Welle ein Commit + rc-Bump + Browser-Replay.
│   │
├── Phase 185 — Canvas Depth G: Live-Drag-Validierung  ✅ shipped (local, 2026-06-01)
│   │
│   │   Schließt den Canvas Depth Cluster.  Drawflow hat kein Drag-Start-
│   │   Event → eigener ``pointerdown``-Listener auf den ``.output``-Sockets
│   │   (parallel zu Drawflows eigenem Wire-Drag) highlightet beim Ziehen die
│   │   gültigen Input-Drop-Targets: ``_highlightDropTargets`` markiert jeden
│   │   Input-Pin grün (``pql-pin-ok``), wenn er frei ist (``_isInputPinFree``)
│   │   und keinen Zyklus erzeugt (``_wouldCycle`` BFS), sonst gedimmt
│   │   (``pql-pin-no``); ``pointerup`` räumt auf.  Drawflows
│   │   ``connectionCreated`` bleibt die Quelle der Wahrheit fürs tatsächliche
│   │   Anlegen.  Höchstes Risiko (versionsabhängiges Pointer-Tracking);
│   │   Fallback auf Drop-Validierung dokumentiert.  Frontend-only,
│   │   rc246→rc247.  ALL LOCAL.  Cluster 179–185 komplett.
│   │
├── Phase 184 — Canvas Depth F: Accessibility & Reduced-Motion  ✅ shipped (local, 2026-06-01)
│   │
│   │   Keyboard + Screenreader + Motion.  Jeder Knoten wird via
│   │   ``_applyNodeA11y`` zu ``role=group`` + ``aria-label`` („<Block>
│   │   block") + ``tabindex=0``; Canvas-Region ``role=application`` +
│   │   tabindex + Anleitungs-Label.  Keydown auf ``df.container``:
│   │   Enter/Space auf fokussiertem Knoten öffnet dessen Config,
│   │   Pfeiltasten pannen (wenn nicht in Knoten/Formularfeld).
│   │   ``prefers-reduced-motion`` jetzt vollständig — Edge-Transitions/
│   │   Glow, Socket-Transitions und Output-Plus-Hover werden zusätzlich
│   │   zur Marching-Ants-Animation abgeschaltet; ``:focus-visible``-Ring
│   │   auf Knoten.  Frontend-only, rc245→rc246.  ALL LOCAL.
│   │
├── Phase 183 — Canvas Depth E: Agent-Ghost-Diff-Overlay  ✅ shipped (local, 2026-06-01)
│   │
│   │   Differenzierer „Agent schlägt Pipeline vor → Mensch supervised am
│   │   Canvas".  Neue read-only Route ``POST /api/dp/{id}/canvas/ghost-diff``
│   │   ([canvas.py](pointlessql/api/data_products_routes/canvas.py)): lädt
│   │   den gespeicherten Doc, nimmt ein ``proposed_document``, ruft das
│   │   bestehende ``diff_docs(current, proposed)`` +
│   │   ``validate_schema_flow`` + ``categorize_pin_schema`` — kein Save,
│   │   kein Version-Bump.  Frontend: Review-Drawer (Robot-Toolbar-Button)
│   │   lädt ein Proposal (Paste oder ``?propose=<base64>``), zeigt
│   │   added/removed/modified Blöcke + Connections mit Per-Item-Accept +
│   │   Validierungsfehler; „Apply accepted" merged die akzeptierten Deltas
│   │   (Knoten/Kanten aus dem Proposal, Positionen erhalten) auf den
│   │   aktuellen Doc und speichert.  Translucentes Live-Canvas-Overlay
│   │   bewusst deferred (riskant gegen Drawflow) — das Accept/Reject-Panel
│   │   liefert die Supervision robust.  2 neue pytest.  Backend+Frontend,
│   │   rc244→rc245.  ALL LOCAL.  (Plugin-Tool ``pql_canvas_propose``
│   │   als Folge-Schritt offen.)
│   │
├── Phase 182 — Canvas Depth D: Obstacle-aware Orthogonal-Routing  ✅ shipped (local, 2026-06-01)
│   │
│   │   Im Orthogonal-Modus (opt-in Toggle) routet ein Post-Pass die Kanten
│   │   um die anderen Knoten-Boxen herum statt mittig durch sie hindurch.
│   │   ``createCurvature`` sieht nur Endpunkte → neuer
│   │   ``_rerouteOrthogonalEdges`` liest je Connection die Endpunkte aus
│   │   dem ``d``, holt die Knoten-AABBs (``offsetLeft/Top/Width/Height``,
│   │   ohne Quelle/Ziel) und baut über ``_orthogonalPath`` den Pfad: plain
│   │   H-V-H-Mittelsplit wenn alle drei Segmente frei, sonst Über/Unter-
│   │   Detour um das blockierende Band.  Gehängt an Toggle / Decorate /
│   │   Drag-rAF / Fit / Resize (setTimeout-gebatcht); Bézier-Modus
│   │   unberührt.  Frontend-only, rc243→rc244.  ALL LOCAL.
│   │
├── Phase 181 — Canvas Depth C: Kontextmenü + Inline-Preview  ✅ shipped (local, 2026-06-01)
│   │
│   │   Rechtsklick-Kontextmenü, zielsensitiv (``_onCanvasContextMenu`` →
│   │   ``ctxMenu`` kind=node/edge/canvas): leere Fläche → „Add block here"
│   │   (droppt einen Standalone-Knoten an der Cursor-Canvas-Position über
│   │   eine neue Branch in ``_pickOutputPlusBlock``); Knoten → Quick peek /
│   │   Preview… / Duplicate / Delete (reuse ``openPreviewForSelected``,
│   │   ``duplicateSelectedNode``, ``deleteSelectedNode``); Kante → Insert
│   │   block / Delete connection (reuse ``insertBlockOnEdge``,
│   │   ``deleteEdgeById``).  Inline-Preview-Peek (``openInlinePeek``):
│   │   kompaktes Popover am Knoten mit den ersten 5 Zeilen über denselben
│   │   ``/canvas/preview``-Endpoint, behandelt Preview-Fehler graceful.
│   │   Frontend-only, rc242→rc243.  ALL LOCAL.
│   │
├── Phase 180 — Canvas Depth B: Navigation & View-Polish  ✅ shipped (local, 2026-06-01)
│   │
│   │   Minimap bekommt ein **Viewport-Rechteck** (aus precanvas-Transform,
│   │   origin 0 0) + **Klick/Drag-zum-Pannen** (``minimapPointerDown`` →
│   │   ``_minimapPanTo``, invertiert die gespeicherte
│   │   ``_minimapTransform``; Pan = reiner Translate → kein Connection-
│   │   Recompute).  Topbar: **Zoom-%-Anzeige** (trackt via Zoom-Observer-
│   │   Callback) als Button = **Reset auf 100%** (``zoomReset100``, hält die
│   │   Viewport-Mitte).  Space-Drag-Pan bewusst weggelassen — Drawflow
│   │   pannt im ``editor_mode='edit'`` bereits nativ per Hintergrund-Drag.
│   │   Frontend-only, rc241→rc242.  ALL LOCAL.
│   │
├── Phase 179 — Canvas Depth A: Perf-Hotspots + Edge-Index  ✅ shipped (local, 2026-06-01)
│   │
│   │   Drei O(n²)-Stellen entschärft, damit spätere Wellen (Routing,
│   │   Ghost-Diff) auf größeren Graphen tragen.  Neuer ``_edgeByDfIds``-
│   │   Index (``"<srcDf>|<tgtDf>" → edgeId``), einmal je ``_syncFromDrawflow``
│   │   gebaut → ``_edgeIdForSvg`` von O(edges·nodes) je SVG auf O(1);
│   │   ``_selectEdge``/``_clearSelectedEdge`` profitieren mit.
│   │   ``_refreshEdgeCategoryStyles`` als Single-Pass über die Connections
│   │   (statt ``querySelectorAll`` je Kante).  ResizeObserver aktualisiert
│   │   nur die tatsächlich resizten Knoten (``_scheduleResizeConnUpdate``)
│   │   statt Full-Graph-Sweep.  Frontend-only, rc240→rc241.  ALL LOCAL.
│   │
├── Phase 178 — Canvas connection-rendering overhaul (double-init root-cause)  ✅ shipped (local, 2026-06-01)
│   │
│   │   User-reported: wires not smooth, gap to the node, not landing
│   │   on the connectors, canvas not centred on open.  A Playwright
│   │   measurement pass found the shared root cause: the canvas
│   │   component initialised twice (Alpine auto-``init()`` plus a
│   │   redundant ``x-init="init()"``), so two Drawflow precanvases
│   │   lived in one container.  ``fitToView`` / zoom / the zoom
│   │   observer all targeted ``container.querySelector('.drawflow')``
│   │   — the empty, DOM-first one — while the real graph stayed
│   │   unpositioned, so wires drifted off their pins and the view
│   │   never centred.  Fix: idempotent init guard on all three
│   │   surfaces (editor, mesh, diff) + retarget every
│   │   ``querySelector('.drawflow')`` to the authoritative
│   │   ``df.precanvas``.  Verified pixel-exact (measured pin↔path
│   │   gap 0,0 on output and input).  Plus, on the same pass:
│   │   ``installSmoothCurvature`` prototype patch in the shared
│   │   ``_drawflow_loader`` (floored-offset cubic bézier that never
│   │   collapses on close / stacked / backward edges; ``curvature===0``
│   │   now renders true right-angle step routing for the orthogonal
│   │   toggle instead of a degenerate diagonal); a per-node
│   │   ResizeObserver so wires follow nodes that grow a schema /
│   │   row-count body; ``fitToView`` centres the bounding box (real
│   │   DOM rects) with a one-shot re-fit after the async bodies
│   │   settle; a slimmer arrow-head marker; and a larger transparent
│   │   pin grab-target.  Frontend only; rc237→rc238.  ALL LOCAL.
│   │
├── Phase 177 — Canvas Quality Push (cross-surface audit close-out)  ✅ shipped (local, 2026-05-31)
│   │
│   │   Phase 176 polished the DP-Canvas edge layer; the mesh and
│   │   diff surfaces still read as 2017-Drawflow demos.  A full
│   │   Playwright + n8n-source audit
│   │   ([`docs/internal/canvas-audit-2026-05-31.md`](docs/internal/canvas-audit-2026-05-31.md))
│   │   logged 27 findings.  This wave lands them all in five
│   │   sub-commits (refactor → critical → high → medium → polish):
│   │   shared CSS / helper extraction (Wave A), focus-mode
│   │   `Shift+F` toggle that lifts canvas real-estate from ~33 %
│   │   to ~58 % of viewport, output-plus hide-when-connected,
│   │   sticky-note collision-avoid, mesh + diff edge decoration
│   │   parity, diff skin reuse with 4-px side-bands instead of
│   │   3-px gold rings, dynamic glow that scales with edge length,
│   │   live MutationObserver-driven `--pql-zoom` (fixes
│   │   programmatic-zoom stale-stroke regression), 80 ms hover
│   │   debounce, diff per-panel fit + zoom + compact body, mesh
│   │   help-text → dismissible banner (stage grows ~600 px →
│   │   ~1080 px on 1600 px wide), minimap visibility persistence,
│   │   subtle "✓ Saved" with tooltip-timestamp, topbar btn-groups
│   │   with aria-labels.  Mesh smart-routing (#M2) and Drawflow→
│   │   Vue-Flow swap deferred to a future library-migration phase
│   │   per audit recommendation.  ~1080 LOC frontend, 0 backend;
│   │   full pytest 4121/0/10 still green.  rc236→rc237.
│   │
├── Phase 176 — Canvas connection UX overhaul (n8n-level)  ✅ shipped (local, 2026-05-31)
│   │
│   │   After Phase 175 the wires rendered correctly but still
│   │   looked like raw Drawflow defaults — 2 px Béziers, no
│   │   hover, no click affordance, no toolbar, no arrows.  This
│   │   wave lifts the connection layer to n8n parity without
│   │   swapping the underlying library.  Eight features land in
│   │   one commit: fat 22 px invisible hit-area sibling path
│   │   (hover/click work along the whole wire); hover + select
│   │   states with stroke + drop-shadow glow; mid-edge insert/
│   │   delete toolbar anchored to the path midpoint via
│   │   `getPointAtLength` with 600 ms exit-delay; directional
│   │   arrows via shared `<defs><marker stroke="context-stroke">`
│   │   inherited per edge; `--pql-zoom` CSS custom property fed
│   │   from `df.on('zoom')` keeps stroke widths legible from
│   │   50 %–160 %; marching-ants animation on edges upstream of
│   │   the running preview (respects prefers-reduced-motion);
│   │   click + `Delete` deletion shortcut for selected edges;
│   │   always-on "+" handle to the right of every output pin
│   │   that opens the block-picker and auto-wires the new block
│   │   220 px right.  ~485 LOC frontend, 0 backend; full pytest
│   │   4121/0/10 still green.  rc233→rc234.
│   │
├── Phase 175 — Canvas bug-fix sweep (post 165-174 browser-replay)  ✅ shipped (local, 2026-05-31)
│   │
│   │   Playwright-MCP browser-replay of the 165-174 cluster
│   │   surfaced 12 bugs across DP / Mesh / Diff surfaces; this
│   │   sweep closes them all in one commit.  Highlights:
│   │   Mesh-Picker modal no longer stuck open; diff-page edge
│   │   overlays now paint stroke (CSS selector was wrong); DP
│   │   edge type-coloring works (frontend key matches backend
│   │   tuple); column type-icons render via the correct
│   │   `duckdb_type` field; Alpine no longer console-errors on
│   │   load; undo-stack now covers paste/sticky/delete/dup;
│   │   visual toggles no longer bump the canvas version;
│   │   minimap re-renders on every structural change; sticky-
│   │   notes spawn viewport-centred; canvas auto-fits on first
│   │   load + manual Fit-to-view toolbar button; Drawflow
│   │   drag-noise silenced via defensive wrapper.  Pure
│   │   frontend; full pytest 4121/0/10 still green.  rc232→rc233.
│   │
├── Phase 174 — DP-Canvas: sticky-note annotations + CanvasDoc.metadata field  ✅ shipped (local, 2026-05-31)
│   │
│   │   Closes Mega-Cluster 165-174.  ``CanvasDoc`` Pydantic
│   │   gains a default-factory ``metadata: dict[str, Any]``
│   │   field; sticky-notes live in
│   │   ``metadata.annotations[]``.  Frontend renders notes as
│   │   absolute-positioned yellow ``div``s above the Drawflow
│   │   canvas (NOT Drawflow nodes — they never enter the
│   │   compile pipeline).  Toolbar adds a sticky-note button;
│   │   click to drop, drag from the body to move, type to
│   │   edit, click × to remove.  Granular Y.Doc remote-apply
│   │   improvements (the rest of Phase 160's deferred
│   │   frontend) explicitly postponed.  3 new pytest covering
│   │   roundtrip + isolation from nodes/edges.  rc231→rc232.
│   │
├── Phase 173 — DP-Canvas: undo/redo + sensible defaults on wire  ✅ shipped (local, 2026-05-31)
│   │
│   │   Closes Phase-161 deferred items.  Ctrl+Z pops the last
│   │   add-block / drop command and reverses it; Ctrl+Y or
│   │   Ctrl+Shift+Z re-applies.  Stack capped at 50; position-
│   │   only drags intentionally not recorded.  When a wire
│   │   completes its target, if the target is Sort / Project
│   │   / GroupBy and its config is empty, the editor auto-
│   │   populates ``order_by`` / ``columns`` / ``keys`` from the
│   │   upstream pin's first column(s).  Y.UndoManager
│   │   integration for co-edit mode + per-field help-tooltip
│   │   icons deferred.  rc230→rc231.
│   │
├── Phase 172 — Diff-Canvas: modified-edge overlay + "Only changed" filter + sync-scroll  ✅ shipped (local, 2026-05-31)
│   │
│   │   Closes the Phase-158 deferred edge-overlay item.
│   │   ``CanvasDiff`` Pydantic gains ``modified_edges`` (edges
│   │   touching a node in ``modified_nodes``); visual diff
│   │   colours them yellow.  Toolbar adds Only-changed toggle
│   │   that dims unchanged nodes + edges to ~15% opacity so
│   │   the eye snaps to the delta.  Before / after panes
│   │   mirror scroll via a guarded ``_syncingScroll`` flag.
│   │   1 new pytest in test_canvas_pipeline_roundtrip.
│   │   rc229→rc230.
│   │
├── Phase 171 — Mesh-Canvas: cross-workspace picker UI + auto-layout  ✅ shipped (local, 2026-05-31)
│   │
│   │   Closes the Phase-162 frontend-deferred.  Right-click on
│   │   the canvas background opens a context menu with three
│   │   actions: **Create new DP here** (navigates to
│   │   ``/dp/new``), **Add cross-workspace upstream…** (two-
│   │   stage picker modal — first ``/api/admin/workspaces``,
│   │   then ``/api/mesh/canvas/picker/{slug}``; selecting a DP
│   │   mints a ghost-node carrying the foreign workspace slug),
│   │   and **Auto-layout** (reuses Phase 170's Dagre helper
│   │   with rankdir=TB).  Ghost nodes get a dashed warning-
│   │   coloured header + ``ws: <slug>`` badge.  Dagre CDN added
│   │   to the mesh template.  rc228→rc229.
│   │
├── Phase 170 — DP-Canvas: auto-layout via Dagre  ✅ shipped (local, 2026-05-31)
│   │
│   │   Toolbar gets a Tidy button (Ctrl+L) that runs Dagre's
│   │   layered LTR algorithm over the current nodes + edges,
│   │   then animates each block to its target position with an
│   │   easeInOutQuad tween over 250ms (blocks slide into place
│   │   rather than teleporting).  New helper module
│   │   ``frontend/js/dp_canvas/_auto_layout.js`` isolates the
│   │   Dagre wrapper + tween from the editor page; Dagre loaded
│   │   via jsdelivr CDN (``dagre@0.8.5``, ~30KB).  Pure
│   │   frontend.  rc227→rc228.
│   │
├── Phase 169 — DP-Canvas: minimap + Ctrl+F block search  ✅ shipped (local, 2026-05-31)
│   │
│   │   Bottom-right 200×130 SVG minimap shows every block's
│   │   scaled-to-fit position; selected block painted in primary
│   │   blue, rest in secondary grey.  Toolbar gets a Map toggle.
│   │   Ctrl+F opens a top-anchored search overlay that filters
│   │   blocks by ``block_type`` (case-insensitive substring) or
│   │   ``id``; arrow keys move the cursor, Enter pans canvas
│   │   to the match + selects, Escape closes.  Minimap re-
│   │   renders are rAF-coalesced through the same flush path
│   │   the drag fix introduced — never throttles the cursor.
│   │   Pure frontend.  rc226→rc227.
│   │
├── Phase 168 — DP-Canvas: multi-select + bulk delete + copy/paste  ✅ shipped (local, 2026-05-31)
│   │
│   │   Shift+Click on a block toggles it in
│   │   ``multiSelectedNodeIds``; plain click clears the set.
│   │   Delete / Backspace with >1 selected prompts
│   │   ``Delete N blocks?`` then bulk-removes.  Ctrl+C copies
│   │   selected blocks + internal edges to
│   │   ``localStorage["pql-canvas-clipboard"]``; Ctrl+V pastes
│   │   with a +40/+40 offset and fresh PQL ids.  Rubber-band
│   │   marquee deferred (collides with Drawflow native pan
│   │   handler — needs Space-or-middle-click escape hatch).
│   │   Pure frontend.  rc225→rc226.
│   │
├── Phase 167 — DP-Canvas: connector visual upgrade (type-coloring + orthogonal toggle)  ✅ shipped (local, 2026-05-31)
│   │
│   │   New ``pointlessql/services/dp_canvas/_edge_types.py``
│   │   maps a ``PinSchema`` to one of six dominant-type buckets
│   │   (``numeric``, ``text``, ``temporal``, ``boolean``,
│   │   ``complex``, ``mixed``).  Validate route response gains
│   │   ``edge_categories: {edge_id: bucket}``; editor applies
│   │   ``pql-edge-${bucket}`` CSS classes to every
│   │   ``.drawflow .connection`` so the canvas reveals at a
│   │   glance which edges carry numeric vs text vs temporal
│   │   payloads.  Toolbar adds an orthogonal-routing toggle that
│   │   flips ``Drawflow.curvature`` between Bezier (0.5) and
│   │   straight-segments (0) and re-renders all paths.
│   │   Pin-label hover tooltip deferred (Drawflow's per-pin
│   │   socket DOM is awkward to enrich; defer until socket
│   │   render is owned by us).  8 new pytest, full canvas-routes
│   │   suite green.  rc224→rc225.
│   │
├── Phase 166 — DP-Canvas: richer node display (schema + row-count + status)  ✅ shipped (local, 2026-05-31)
│   │
│   │   Each DP-Canvas block-node now shows up to 3 output columns
│   │   inline (with type-icons inferred from the DuckDB type:
│   │   hash for INT, calculator for DOUBLE, calendar for
│   │   TIMESTAMP, etc.) plus a footer with the row-count from the
│   │   last preview call and a status badge (check / cross /
│   │   circle for validated / error / pending).  Body re-renders
│   │   after every successful validate (sourced from
│   │   ``pinSchemas[id:out]``) and after each preview run.
│   │   Toolbar gains a Compact toggle that hides the rich body
│   │   when the canvas grows wide.  Pure frontend over existing
│   │   validate + preview responses.  rc223→rc224.
│   │
├── Phase 165 — DP-Canvas + Mesh-Canvas: drag-performance fix  ✅ shipped (local, 2026-05-31)
│   │
│   │   Opens Mega-Cluster 165-174.  Root-cause: the
│   │   ``nodeMoved`` handler on the DP-Canvas editor invoked
│   │   ``_syncFromDrawflow`` on every animation frame of the
│   │   mouse-move stream — a full Drawflow export, ``nodes`` +
│   │   ``edges`` dict rebuild, debounced validate + autosave
│   │   queue per cursor tick.  Mesh-Canvas had the same anti-
│   │   pattern (``nodeMoved`` → ``_syncEdges`` → validate)
│   │   despite never persisting node positions.  Fix splits
│   │   position-only mutations onto a
│   │   ``requestAnimationFrame``-coalesced
│   │   ``_onNodePositionChanged`` path that touches only
│   │   ``nodes[id].position`` and schedules a single autosave;
│   │   structural sync (edges, validate) stays on
│   │   ``connectionCreated`` / ``connectionRemoved`` /
│   │   ``nodeRemoved`` / ``nodeDataChanged``.  Mesh-Canvas
│   │   dropped its ``nodeMoved`` handler entirely.  Diff-Canvas
│   │   read-only — no change.  Pure-frontend; full pytest
│   │   4109/0/10 green.  rc222→rc223.
│   │
├── Mega-Cluster 155-164 — Visual DP Editor + Platform Polish  ✅ shipped (local, 2026-05-31)
│   │
│   │   10-phase improvement wave on top of the freshly shipped
│   │   147-154 Visual DP Editor surface and adjacent platform
│   │   surfaces (mesh-canvas, audit cockpit, API-key dashboard).
│   │   Backend-first scope: pinned production canvas versions,
│   │   preview cache, hover-tooltip diagnostics, side-by-side
│   │   visual diff overlay, CodeMirror format-on-blur + snippets,
│   │   granular per-block Y.Doc co-edit, duplicate-block action,
│   │   mesh cross-workspace edges, saved audit filters + regex on
│   │   details, API-key WoW + 3σ anomaly heuristic.  Each phase
│   │   landed as one commit; rc212→rc222.  ALL LOCAL until single
│   │   final push.
│
├── Phase 163 — Audit-Log Filters UX: saved-filters + regex on details  ✅ shipped (local, 2026-05-31)
│   │
│   │   Alembic ``o3c5e7g9i1k3`` adds ``audit_saved_filters``
│   │   (owner-private by default; per-row ``is_shared_workspace``
│   │   flips it to workspace-visible).  4 new CRUD routes under
│   │   ``/admin/audit/saved-filters`` for list / create / update /
│   │   delete — admin-gated + CSRF-protected.  Admin audit
│   │   viewer's index route gains a ``?details_regex=...`` query
│   │   param that filters rows server-side post-DB-query (Python
│   │   ``re.search`` on the JSON detail column).  Invalid regex
│   │   surfaces a ``regex_error`` to the template without
│   │   crashing the viewer.  Frontend HTML changes for the dropdown
│   │   UI deferred — the API + storage are in place; users can
│   │   already POST saved filters via the REST surface.
│   │
├── Phase 162 — Mesh-Canvas: Cross-Workspace Edges  ✅ shipped (local, 2026-05-31)
│   │
│   │   Alembic ``n2b4d6f8h0j2`` adds a nullable
│   │   ``source_workspace_id`` FK on ``data_product_input_ports``
│   │   (``ON DELETE RESTRICT``).  ``NULL`` = same workspace as
│   │   the consuming DP (status quo).  Non-null = cross-workspace
│   │   binding.  Mesh-canvas service now reads + writes the
│   │   field: ``build_mesh_canvas_doc`` exposes cross-workspace
│   │   upstreams as ghost-nodes carrying the foreign workspace's
│   │   slug; ``apply_mesh_canvas_doc`` accepts edges with
│   │   ``source_workspace_slug``, looks up the foreign workspace
│   │   and DP, then writes a cross-workspace input-port row.
│   │   New admin-only ``GET /api/mesh/canvas/picker/{slug}`` lists
│   │   candidate upstream DPs in a foreign workspace.  Frontend
│   │   right-click "Create new DP here" context menu intentionally
│   │   deferred — out of scope for v1.
│   │
├── Phase 161 — Visual DP Editor: Block-Library Config-UX Polish  ✅ shipped (local, 2026-05-31)
│   │
│   │   Adds a "Duplicate this block" action: toolbar button next
│   │   to delete + ``Ctrl+D`` / ``Cmd+D`` keyboard shortcut.  The
│   │   clone lands +40px offset, deep-copies config, gets a fresh
│   │   PQL id, and becomes the new selection so the user can edit
│   │   it immediately.  Help text on every block already lived in
│   │   ``BLOCK_DEFS[type].help`` + ``form-text`` below each config
│   │   field — surfaced via existing palette tooltips, so no
│   │   per-field info icons added (would be noise).
│   │   Sensible-defaults pre-fill (Sort.order_by / Project.columns
│   │   from upstream schema) + Undo/Redo intentionally deferred —
│   │   each is a phase-sized scope of its own.
│   │
├── Phase 160 — Visual DP Editor: Granular per-block Y.Doc Sync  ✅ shipped (local, 2026-05-31)
│   │
│   │   Co-edit Y.Doc shape upgraded from "one slot holding the
│   │   whole serialised CanvasDoc" to per-block + per-edge
│   │   structured Y.Maps: ``nodes_order`` / ``nodes_map`` /
│   │   ``edges_order`` / ``edges_map``.  Per-block configs +
│   │   positions are JSON-encoded strings inside the per-node
│   │   sub-map (full per-key Y.Map nesting deferred).  Two
│   │   peers editing two different nodes' configs now hit
│   │   different Y.Map keys and never conflict at the Y.js
│   │   layer.  Legacy v1 single-slot Y.Docs are auto-migrated
│   │   on first ``extract_canvas_doc`` read so in-flight co-
│   │   edit sessions don't break.  Frontend hub client still
│   │   does a coarse full-replay on observe — granular client-
│   │   side mutation handlers are out of scope for v1.
│   │
├── Phase 159 — Visual DP Editor: CodeMirror Polish  ✅ shipped (local, 2026-05-31)
│   │
│   │   SQL block editor (multi-line) gains format-on-blur (inhouse
│   │   ~140-line DuckDB-ish formatter — uppercase keywords +
│   │   newline before SELECT/FROM/WHERE/JOIN-family) and ten
│   │   hardcoded snippets (cte / win / agg / case / ljoin / ijoin
│   │   / gbh / olim / unnest / cast).  Snippets ride the same
│   │   completion source the column-autocomplete already uses, so
│   │   typing 3 letters + Tab expands the pattern.  Multi-cursor
│   │   (Alt+Click) was already on by default in CodeMirror 6 —
│   │   noted in user-facing docs.  Linter for unbalanced parens
│   │   intentionally deferred (DOM-level squiggle would need
│   │   ``@codemirror/lint`` which we don't currently load).
│   │
├── Phase 158 — Visual DP Editor: Diff-View Visual Canvas-Overlay  ✅ shipped (local, 2026-05-31)
│   │
│   │   ``/dp/{id}/canvas/diff`` gains a side-by-side visual mode
│   │   (default) where two read-only Drawflow editors paint the
│   │   before + after canvases with colour overlays: added nodes
│   │   green, removed red, modified yellow.  Edges added/removed
│   │   get matching stroke colours.  The legacy 3-column list
│   │   view remains as a toggle.  New shared
│   │   ``_drawflow_loader.js`` helper extracted so editor + diff
│   │   pages reuse the same Drawflow node-add / connect dance.
│   │
├── Phase 157 — Visual DP Editor: Schema-Flow Diagnostics UX  ✅ shipped (local, 2026-05-31)
│   │
│   │   CompileError envelope grows optional ``column`` /
│   │   ``expected_type`` / ``actual_type`` / ``suggestion``
│   │   fields.  Project + GroupBy + Join column-presence errors
│   │   now fill ``column``; the Cast block's unknown-type
│   │   ``bad_config`` fills ``column`` + ``actual_type`` +
│   │   ``suggestion="UNKNOWN_DUCKDB_TYPE"``.  The editor's
│   │   per-node error-badge renders a hover-tooltip with the
│   │   structured detail so users see "[type_mismatch]
│   │   column=ghost ..." instead of just a numeric badge.
│   │   The "insert Cast block" quick-fix is explicitly deferred:
│   │   today's validator doesn't surface a type-mismatch with
│   │   matched expected/actual columns where Cast would fix the
│   │   problem — wait for a future block that does (DuckDB-level
│   │   type-checked Filter, e.g.) before wiring the quick-fix UI.
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
