---
title: "Cluster 19 — Phase 107–114 post-Notebook UI + Co-edit bus + Branch backend (dev-log)"
audience: contributor
cluster_id: "19"
phases: "107-114"
closed: "2026-05-23"
---

# Cluster 19 — Phase 107–114 post-Notebook UI + Co-edit bus + Branch backend (dev-log)

> Phase 107 (toolbar icon-only mode + close-all panels), Phase 108 (live-server + multi-tab Playwright CI gate + replay-worker test), Phase 109 (multi-worker co-edit bus PG LISTEN/NOTIFY + admin status endpoint), Phase 110 (Restschuld IV modularization: 9 splits), Phase 111 (Restschuld V wave: 7 splits, restschuld pipeline empty), Phase 112+113 (right meta panel + editor surface consolidation: tabbed Schedule+Run + unified right drawer), Phase 114 (Workspace navigation overhaul: tree + filter + drag-drop + inline rename).

These entries were materialised from the pre-W3 ``CHANGELOG.md`` ``[Unreleased]`` block (Doc-Master-Plan W3, 2026-05-26).  They preserve the original phase-keyed narrative for contributors who want richer commit-level context than the auto-generated per-cluster CHANGELOG section provides.

---

> from CHANGELOG.md (bucket: **Changed**)

- **Phase 113 — Editor surface consolidation (2026-05-22, rc96 →
  rc99).**  Three sub-sprints, three commits, all pushed to
  origin/main.  Continues the Phase 112.5 toolbar↔meta-panel
  content split pattern into three remaining cluttered notebook-
  editor surfaces.
  - **113.1 (commit ``74b9e6f``, asset rc96 → rc97) — cell-
    header ⋯-overflow split.**  Per-cell Type dropdown +
    History toggle + 5-button Insert / Move / Delete cluster
    collapsed into one Bootstrap ``dropdown`` opened by a single
    ``bi-three-dots`` button.  Menu sections in order: Cell type
    / View / Structure / Delete / Lineage (only rendered when
    >1 write-op).  Lineage strip capped at 1 visible badge +
    hover-tooltipped ``+N more`` overflow chip; unfolded tail
    moves into the menu's Info section.  New
    ``lineageOverflowTitle()`` helper in
    ``frontend/js/notebook/cell_lineage.js``.  No new per-cell
    Alpine scope — single ``<div class="dropdown">`` stays in
    the outer ``notebookEditor()`` scope.
  - **113.3 (commit ``879feed``, asset rc97 → rc98) — run-job
    modals merged.**  Phase-67.2 Schedule modal + Phase-67.3
    Run-Once modal folded into one Bootstrap modal with
    ``nav-pills nav-fill`` tab strip (Run now / Schedule).
    Shared block: parameter-overrides form + submit/error
    state.  Tab-specific: name + cron (Schedule), in-flight
    status badge (Run-now).  One unified ``runModal`` Alpine
    state object (``{open, tab, submitting, error, parameters,
    name, cronExpr, status}``) replaces nine legacy fields.
    ``_pollJobRun`` now short-circuits when the modal closes
    mid-poll (closes a latent leak).  Two legacy partials
    deleted outright per ``feedback_no_legacy_shim``.
  - **113.2 (commit ``f3803f7``, asset rc98 → rc99) — right-
    drawer unification.**  Three competing right-edge surfaces
    (Phase 96 chat drawer ``z=1040``, Phase 67.5 variable
    inspector ``z=1040`` overlapping chat, Phase 77.6 social
    drawer as Bootstrap offcanvas-end silently ignored by
    ``closeAllPanels()``) collapsed into one
    ``pql-right-drawer`` shell with six tabs (Chat · Variables ·
    Discussion · Endorsements · Followers · README).  One
    ``rightDrawer: { open, tab }`` Alpine state object replaces
    two booleans + the Bootstrap-offcanvas state.  All six tab
    bodies stay in the DOM via ``x-show`` (not ``x-if``) so the
    chat WebSocket subscription survives tab switches.  Social
    finally in scope for "Close all panels" — fixes the silent-
    omission bug from the initial Phase 77.6 wiring.  Legacy
    ``toggleChatPanel()`` / ``toggleInspector()`` kept as thin
    aliases delegating to ``openRightDrawer(tab)``.  Three
    legacy partials deleted.  *Surprising lesson:* the shared
    ``_endorsements_pane.html`` / ``_followers_pane.html`` ship
    as ``tab-pane fade`` without the ``show active`` modifier —
    under Alpine ``x-show`` wrapping they need a CSS override
    (``.pql-right-drawer__nested-pane > .tab-pane { display:
    block !important; opacity: 1 !important; }``) to be visible,
    since Bootstrap's CSS hides them otherwise.

  Gates clean across all three sprints (0 ruff, 0 pyright
  errors, pydoclint clean, alembic clean).  414 notebook-scoped
  pytest pass; one pre-existing failure
  (``test_save_non_admin_accessible`` returns 403, not 200)
  unrelated to Phase 113.  Browser-replay deferred — server kill
  was permission-denied during the closing session.

> from CHANGELOG.md (bucket: **Changed**)

- **Phase 112 — Right meta panel + toolbar/meta-panel content
  split (2026-05-22, rc92 → rc96).**  Single commit ``1cf29a0``.
  Reorganises the notebook toolbar so verbs (Run all, Save, …)
  stay always-visible while nouns (status, notebook metadata)
  migrate into a right-edge sticky meta panel — CSS-grid column
  on desktop, drawer on mobile.  Sprint 112.5 closes the loop
  with a toolbar/meta-panel content split: five top-bar status
  badges (kernel state, schedule presence, last-run age, peer
  count, agent presence) collapse into a single vital-signs dot
  cluster, and a new Activity accordion section in the meta
  panel aggregates kernel / peers / recent-runs from already-
  loaded reactive state (no new fetch).  Establishes the
  "always-visible = verbs + active state; hidden behind one
  click = rarely-used or fully-default state" mental model that
  Phase 113 then carries into three other cluttered surfaces.
