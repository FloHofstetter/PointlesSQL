---
title: "Cluster 01 — Bootstrap — Sprint 1–23 (dev-log)"
audience: contributor
cluster_id: "01"
phases: "0-7"
closed: "2026-04-17"
---

# Cluster 01 — Bootstrap — Sprint 1–23 (dev-log)

> Initial project scaffolding through Phase 7 (DAG engine + Playwright orchestration). Catalog browser, PQL helper, embedded JupyterLab, auth (Sprint 5-7), Postgres sync, foreign-catalog UI, logging/observability, docstrings + pydoclint, exception hierarchy, papermill executor, MCP walkthrough harness.

These entries were materialised from the pre-W3 ``CHANGELOG.md`` ``[Unreleased]`` block (Doc-Master-Plan W3, 2026-05-26).  They preserve the original phase-keyed narrative for contributors who want richer commit-level context than the auto-generated per-cluster CHANGELOG section provides.

---

> from CHANGELOG.md (bucket: **Refactored**)

- **Phase 1 — notebook/main.js carve-up** (247e271).
  [main.js](frontend/js/notebook/main.js) drops 1547 → 1204 LOC.
  Five new sibling modules:
  [output_zone_manager.js](frontend/js/notebook/output_zone_manager.js),
  [cell_introspector.js](frontend/js/notebook/cell_introspector.js),
  [autosave_scheduler.js](frontend/js/notebook/autosave_scheduler.js),
  [commands.js](frontend/js/notebook/commands.js); plus
  ``createOutlineRecomputer`` factory in
  [outline.js](frontend/js/notebook/outline.js).  Grep gate
  [check-frontend-no-reactive-monaco.sh](scripts/check-frontend-no-reactive-monaco.sh)
  extended with the new closure-state slot names.

> from CHANGELOG.md (bucket: **Refactored**)

- **Phase 2 — ESM bridge entrypoint** (87f03a7).  New
  [frontend/js/bootstrap.js](frontend/js/bootstrap.js) loaded as
  ``<script type="module">`` from
  [base.html](frontend/templates/base.html) before the Alpine CDN
  script.  New CI gate
  [check-frontend-bootstrap-order.sh](scripts/check-frontend-bootstrap-order.sh)
  asserts the script-tag ordering.

> from CHANGELOG.md (bucket: **Refactored**)

- **Phase 3 — editor_base + small editors to ESM** (410f144).  New
  [editor_base.js](frontend/js/editor_base.js) exports
  ``validateRequired`` and ``createDictEditor``; four inline editors
  migrated to native ES modules.

> from CHANGELOG.md (bucket: **Refactored**)

- **Phase 4 — federation / list_table / sql_editor / helpers to ESM**
  (2d9e1e2).  Last legacy files migrated.  Removed all 11 individual
  ``<script src="/static/js/X.js">`` tags from base.html +
  sql_editor.html — only bootstrap.js + Alpine + vendor CDN scripts
  load via raw ``<script>`` now.

> from CHANGELOG.md (bucket: **Refactored**)

- **Phase 5 — CSRF in pqlApi + frontend README** (a5a7a20).
  ``pqlApi.fetch`` now injects ``X-CSRF-Token`` for non-safe verbs.
  New [frontend/js/README.md](frontend/js/README.md) documents the
  post-Sprint-75 conventions.

> from CHANGELOG.md (bucket: **Refactored**)

- **Phase 6 — style.css split** (e0ae139).  1066-line single file
  carved into ten purpose-scoped sheets that the master
  [style.css](frontend/css/style.css) ``@import``s in cascade order:
  base / primitives / layout / responsive plus six under
  components/.

Hard constraints honoured: no build step, no bundler, no
``package.json``.  Static gates green: ruff, pyright, alembic,
``node --check`` on every modified file, both frontend grep gates.
