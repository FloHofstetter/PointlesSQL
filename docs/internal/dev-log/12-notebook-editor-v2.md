---
title: "Cluster 12 — Phase 66–68 Notebook editor v2 (dev-log)"
audience: contributor
cluster_id: "12"
phases: "66-68"
closed: "2026-05-12"
---

# Cluster 12 — Phase 66–68 Notebook editor v2 (dev-log)

> Phase 66 (notebook editor v2), Phase 67 (Notebook Operations), Phase 68 (Frontend modularization — sql_editor CSS extract + notebook.css lazy-load).

These entries were materialised from the pre-W3 ``CHANGELOG.md`` ``[Unreleased]`` block (Doc-Master-Plan W3, 2026-05-26).  They preserve the original phase-keyed narrative for contributors who want richer commit-level context than the auto-generated per-cluster CHANGELOG section provides.

---

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 69 — Vollständiger Browser-Replay der Plattform
  (2026-05-12).**  Browser-replay sweep of every UI surface across
  multiple user roles and config flips on the
  `docker-compose.e2e.yml` stack, primarily to verify Phase 68's
  structural HTML/CSS/JS reorganization landed cleanly.  Three
  bugs surfaced.  Two are deploy-hygiene cascades resolved by
  bumping `pyproject.toml` version whenever `frontend/` changes
  (BUG-69-01 + BUG-69-02 documented in
  `docs/e2e-walkthroughs/federation.md`).  One is a real Phase
  68.4 file-move regression, fixed in this commit-range:
  `frontend/js/pages/federation/{connections,credentials,
  catalogs}.js` each had a stale `import './editor_base.js'`
  pointing one directory too deep after Phase 68.4's `git mv`;
  now `from '../../editor_base.js'` (BUG-69-03).  Without the
  fix, every page-load fired a 404 + cascaded into Alpine init
  failure that left `pql-cmdk-backdrop` intercepting clicks.
  Persona matrix exercised: admin@pql.test, flo@pql.test (member
  403 sweep), supervisor + auditor + lineage_inbound Bearer key
  generated via `/admin/api-keys`, OIDC via `mock-oidc` sidecar.
  Verified: all 7 table-detail tabs, 4 run-view top tabs + 5
  Operations sub-tabs, 4 model-detail tabs, 3 federation modals,
  notebook.css absent on 6 non-notebook surfaces, sql_editor.css
  cascade @import present, "Sign in with SSO" button flips with
  OIDC env.

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 68 — Frontend modularization (2026-05-12).**  Structural
  reorganization for LLM-context efficiency and one-convention
  hygiene; behavior unchanged.  Templates: 12 single-page partials
  moved from top-level `templates/partials/` into nested
  `pages/_partials/run_view/` and `pages/_partials/notebook/output/`
  (only 2 genuinely cross-page partials remain at top-level).
  Three large templates split into per-tab partials using the Phase-38
  playbook: `pages/table.html` 786 → 228 LOC (7 partials),
  `pages/_partials/run_view/tab_operations.html` 726 → 59 LOC
  (5 sub-tab partials), `pages/model.html` 589 → 209 LOC
  (4 partials).  JS: 3 admin-only `federation_*.js` files moved
  from top-level `frontend/js/` to `frontend/js/pages/federation/`;
  `bootstrap.js` imports updated, window-attached names unchanged.
  CSS: `pages/sql_editor.html` 146-LOC inline `<style>` extracted to
  `frontend/css/components/sql_editor.css` (page 543 → 397 LOC);
  `notebook.css` (292 LOC) removed from global `@import` cascade
  and lazy-loaded via `{% block extra_css %}` in
  `pages/notebook_editor.html`, so notebook-only CSS no longer
  appears in LLM-context for non-notebook pages.  New
  `docs/development/frontend-conventions.md` codifies the
  conventions; `frontend/js/README.md` gains a folder-layout
  section.  Deferred (out of scope for Phase 68): `notebook_editor.js`
  939-LOC split (Alpine state tight-coupled across 8 seams, awaits
  feature-driven anchor); `base.html` 565 LOC (mostly critical-path
  init scripts, no splittable seams); `pages/notebook_editor.html`
  597 LOC (single-page Alpine app, no static tab boundaries).

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 67 — Notebook Operations (2026-05-12).**  Phase 66's
  live editor gains the four DBX-feel surfaces that close the
  notebook-from-the-editor gap without touching the existing
  scheduler / papermill / kernel-session stack:
  (1) **Schedule-from-Notebook** — toolbar "Schedule" button +
  modal pre-built from `papermill.inspect_notebook` posts to
  the existing `POST /api/jobs` with `kind="papermill"`;
  (2) **Parametrized runs** — papermill-canonical
  `# %% tags=["parameters"]` jupytext marker (round-trip-stable;
  ignored by `compute_content_hash` so the parameters-tag flip
  doesn't rewrite cell identity); inspect endpoint accepts `.py`
  via in-memory jupytext + nbformat conversion;
  (3) **Run-Once-with-Parameters** — `POST /api/notebooks/run-once`
  creates a paused permanent Job + fires
  `scheduler_service.execute_run` as fire-and-forget asyncio task,
  returning `{job_id, job_run_id, status}`; new
  `GET /api/jobs/{id}/runs` listing endpoint feeds browser polling;
  (4) **Variable Inspector** — kernel bootstrap learns
  `__pql_inspect__()` + `__pql_inspect_detail__()` that emit a
  custom `application/x-pql-vars+json` MIME bundle; the WS pump
  routes them to dedicated `variable_snapshot` /
  `variable_detail` notify frames (NOT persisted) so the editor
  side-pane refreshes after every cell run.  Plus a job-run
  output bridge — `_papermill_executor` post-execute persists
  per-cell outputs to `notebook_outputs` with
  `kernel_session_id = "job:<run_id>"` so the same renderer
  surfaces job artefacts and live cell outputs.  New
  `notebook_job_link` table (Alembic `i9j1k3m5o7q9`) gives the
  editor's in-context "Jobs of this notebook" panel an indexed
  look-up against `notebook_path` instead of a JSON-LIKE scan
  on `Job.config`.  Per-cell "Mark as parameters" dropdown
  action toggles `cell.tags` and triggers the autosave
  debouncer; the params-tag round-trips byte-identically
  through `load → save`.  46+ new pytest cases; 110/110 green
  on the notebook + jobs slice.  Pyright budget: pre-existing
  reportLiteralAssignment at `notebook_kernel_ws:361` carried
  forward (Sprint 66.5 SQL-cell `record_query`; unrelated to
  Phase 67).

> from CHANGELOG.md (bucket: **Notes**)

- **Phase 66 — Browser Notebook editor v2 (2026-05-10).**  The
  browser notebook editor returns, rebuilt around the marker
  grammar (`# %%` jupytext-Percent + FNV-1a-64 content_hash),
  the async kernel-bridge runtime (`KernelRegistry` +
  `KernelSession`), and the persisted-output replay tables
  that all survived the agent-first pivot.  New surface area:
  `/notebooks/edit/{path:path}` cell-by-cell editor backed by
  CodeMirror v6 instances per cell (no vendored bundles —
  esm.sh import-map only); a `/ws/notebook/kernel` JSON-RPC
  WebSocket route bridging browser → ipykernel; restored
  notebook CRUD (`POST /api/notebooks/create`,
  `POST /api/notebooks/rename`, `DELETE /api/notebooks/delete`)
  and load / save / render-markdown / cell-history routes.
  Cells render under a sandboxed iframe (text/html, image/svg)
  or as DOM (image/png/jpeg → `<img>`, JSON → `<pre>`,
  text/plain → monospace, error → red-bordered traceback).
  SQL cells (`# %% [sql] df`) are wrapped server-side via
  `__pql_sql_run(...)` after a per-table privilege check;
  every SQL execution writes a `query_history` row with
  `notebook_path` + `notebook_content_hash` so the audit
  cockpit can deep-link back to the originating cell.  Markdown
  cells switch between rendered HTML view-mode and CodeMirror
  edit-mode (Shift+Enter / Esc / click).  Keyboard model
  covers Shift+Enter (run + advance), Ctrl+Enter (run + stay),
  Cmd/Ctrl+S (save).  5-second debounced autosave + per-cell
  history popover via `GET /api/notebooks/cell-history`.  One
  Alembic migration (`hh7i9k1m3o5q` — query_history notebook
  columns) + one new walkthrough (`notebook-overview.md`).
  ~37 new pytest cases (CRUD, load, save, cell ops, SQL cell
  helpers, markdown render, cell history, kernel WS auth +
  one integration test for the real-kernel execute round-trip).
