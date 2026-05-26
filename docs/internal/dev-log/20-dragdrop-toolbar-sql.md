---
title: "Cluster 20 — Phase 115–117 Drag-drop + Toolbar + SQL Statement API (dev-log)"
audience: contributor
cluster_id: "20"
phases: "115-117"
closed: "2026-05-23"
---

# Cluster 20 — Phase 115–117 Drag-drop + Toolbar + SQL Statement API (dev-log)

> Phase 115 (cell drag-drop reorder + CRDT sync + header-as-handle + live-splice FLIP), Phase 116 (notebook editor toolbar redesign: vital pills v2 + Save/Run state buttons), Phase 117 (external SQL Statement Execution API at /api/2.0/sql/statements; SELECT-only v1; Bearer-only auth).

These entries were materialised from the pre-W3 ``CHANGELOG.md`` ``[Unreleased]`` block (Doc-Master-Plan W3, 2026-05-26).  They preserve the original phase-keyed narrative for contributors who want richer commit-level context than the auto-generated per-cluster CHANGELOG section provides.

---

> from CHANGELOG.md (bucket: **Added**)

- **Phase 117 — External SQL Statement Execution API (2026-05-23,
  rc120 → rc121).**  PointlesSQL gains its first token-only public
  REST surface: a Databricks-compatible SQL Statement Execution
  API at ``/api/2.0/sql/statements`` (POST submit, GET poll, GET
  chunk, POST cancel).  External clients (curl, dbt, BI tools,
  application backends) can now run SELECT queries without
  driving the browser UI; wire shape mirrors the documented DBX
  schema so the official ``databricks-sql-python`` adapter +
  dbt-databricks runner work with a base-URL swap.  Auth is
  Bearer-only via the existing ``api_keys`` table (new
  ``sql_execute`` scope flag); per-key rate limit (60/min by
  default) and a feature-flag kill-switch
  (``POINTLESSQL_SQL_EXECUTION_API_ENABLED=0`` → 503) live
  alongside.  Execution wraps the same ``run_sql_sync`` +
  ``enforce_select_per_table`` pipeline the editor uses, so UC
  SELECT grants apply uniformly.  Slow queries (past the DBX-
  style ``wait_timeout``) return a PENDING envelope the client
  polls; results gzip-cached in a new ``sql_statements`` table
  with 24h retention.  Typed ``:name`` parameter binding via
  sqlglot AST substitution (STRING / INT / LONG / DOUBLE / FLOAT
  / BOOLEAN / DATE / TIMESTAMP / NULL) is injection-safe by
  construction.  Default ``catalog``/``schema`` body fields drive
  a sqlglot pre-pass that qualifies 1- and 2-part table refs
  before the parser.  v1 is SELECT-only; DML / DDL ships
  separately with the approval-flow integration.  39 new pytest;
  new walkthrough at
  ``docs/e2e-walkthroughs/external-sql-api.md``.

> from CHANGELOG.md (bucket: **Changed**)

- **Phase 116 — Notebook editor toolbar redesign (2026-05-23,
  rc119 → rc120).**  Replaces the decorative dot-trio with
  stateful pill chips, makes Save / Run-all carry their own
  state, and strengthens panel-toggle ``.active`` to match the
  audit active-link treatment.  Design principle: **"status
  lives on the action"** — each piece of state has a natural
  home on its action button (Save state on Save button, Run
  state on Run-all); the cluster is the at-a-glance backup when
  the action is scrolled out of view.  Co-edit pill gains an
  inline peer-count badge.  Pattern note: root-scope
  ``vitalPillClass(kind)`` delegates to mixin-defined
  ``this.coeditPillClass()`` for ``kind='coedit'`` so the
  concern split stays intact.

> from CHANGELOG.md (bucket: **Changed**)

- **Phase 115 — Cell drag-drop reorder (2026-05-23, rc115 →
  rc116).**  Notebook editor cells gain a far-left grip handle
  for VSCode-style drag-drop reordering.  Only the grip carries
  ``draggable="true"`` so CodeMirror's text-selection drag inside
  the editor body still works; the drop indicator paints an inset
  2-px accent shadow above or below the target based on cursor-Y
  vs row midpoint.  The underlying move primitive was refactored
  from ``_moveCell(cell, delta)`` to ``_moveCellTo(fromIdx,
  toIdx)`` so the existing Move-up / Move-down dropdown items
  route through the same code path.  Same sprint closes a latent
  Phase-105 multi-tab gap — ``moveCellUp/Down`` previously
  mutated only the local Alpine array and left ``cells_order``
  Y.Array untouched, so co-edit peers only converged on the next
  save round-trip.  ``_moveCellTo`` now write-throughs the
  reorder under origin ``pql-local-reorder`` and a new
  ``cells_order`` observer (installed in ``onSynced``)
  reconciles remote mutations into Alpine using ``x-for
  :key="cell.id"`` stable ordinals so CodeMirror mounts are NOT
  remounted.  Orphan-uuid cells (uuid in ``this.cells`` but
  missing from a stale ``cells_order`` seed) are preserved at
  the tail instead of being silently dropped — caught and fixed
  mid-replay.  Gates clean; multi-tab Playwright replay
  verified the Y.Array position stayed identical across two tabs
  after a programmatic move.
