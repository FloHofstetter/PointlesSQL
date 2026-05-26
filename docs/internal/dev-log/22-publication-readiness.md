---
title: "Cluster 22 — Phase 122–123 Publication-readiness (dev-log)"
audience: contributor
cluster_id: "22"
phases: "122-123"
closed: "2026-05-25"
---

# Cluster 22 — Phase 122–123 Publication-readiness (dev-log)

> Phase 122 (Source-Code Sanitization for Publication: 1622→260 phase refs across 4 sprints; CLAUDE.md forward-guard for templates/JS/CSS/UI strings; README outside-reader polish), Phase 123 (Frontend Master-Plan 8-wave modernisation: forward-guard W1, inline-script-exodus W2, JS-subsystem-splits W3, template-splits+macros W4, CSS-architektur W5, docs W6, JS-quality W7 (biome), A11y form-labels W8).

These entries were materialised from the pre-W3 ``CHANGELOG.md`` ``[Unreleased]`` block (Doc-Master-Plan W3, 2026-05-26).  They preserve the original phase-keyed narrative for contributors who want richer commit-level context than the auto-generated per-cluster CHANGELOG section provides.

---

> from CHANGELOG.md (bucket: **Changed**)

- **Phase 123 — Frontend Master-Plan (8-wave modernisation)
  (2026-05-25, rc138 → rc173).**  Largest single-domain wave the
  project has run: every HTML template, JS module and CSS file in
  ``frontend/`` was touched.  Extends the publication-readiness
  drive Phase 122 started in the Python tree to the frontend and
  adds the structural overhauls that make the codebase navigable
  for outside contributors + LLMs alike (no file >500 LOC, no
  phase refs in source, IDE-readable types, drift-guard hooks).
  Plan-source: ``~/.claude/plans/ich-m-chte-dass-du-joyful-
  seal.md``.

  - **W1 — Forward-Guard-Alignment** (rc138 → rc142): 50 phase
    markers stripped across 35 frontend files; new
    ``scripts/check-no-phase-refs.sh`` + pre-commit hook;
    ``CLAUDE.md`` forward-guard extended to templates / JS / CSS /
    user-facing UI strings.  Commits ``0cac177b`` + ``175013de``.
  - **W2 — Inline-Script-Exodus** (rc142 → rc150): 65 templates'
    inline ``<script>`` blocks (~6 250 LOC) extracted into
    dedicated ESM modules.  Mega-factories first (``feed.js`` /
    ``data_product.js`` / ``model.js``), then ``base.html``
    exodus (-362 LOC: HTMX bridge / theme / UI helpers / recent-
    storage), then Tier-2 + Tier-3 sweeps.  9 commits
    ``0cac177b..e86d0bfc``.
  - **W3 — JS-Subsystem-Splits** (rc150 → rc155): four largest
    notebook JS files split below 350 LOC each (``coedit.js``
    565L → facade + 3 modules; ``cell_thread.js`` 402L → factory
    + 2 helpers; ``revisions.js`` 396L → 235L + ``revision_diff``;
    ``kernel_execution.js`` 308L → 264L + ``variable_inspector``).
    New ``frontend/js/http.js`` for cookie-CSRF.  5 commits
    ``cfc8507a..6c8debe3``.
  - **W4 — Template-Splits + Reuse-Macros** (rc156 → rc162): 3
    new macros (``badge`` / ``button`` / ``state_container``) + 5
    mega-templates split (``tab_lineage`` 514 → 61 + 5× ~90;
    ``branch_detail`` 460 → 28 + 4× ~110; ``revisions_panel`` 374
    → 23 + 4× ~90; ``sql_editor`` 591 → 50 + 4 partials;
    ``meta_panel`` 826 → 38 + 8× ~98).  All wrappers ≤50 LOC, all
    sub-partials <260 LOC.  6 commits ``688865f7..708d04d9``.
  - **W5 — CSS-Architektur-Konsolidierung** (rc162 → rc164):
    ``notebook.css`` 811 → 22 thin ``@import`` index + 7
    contiguous-slice sub-files in ``frontend/css/notebook/``;
    cascade preserved byte-identical (14 976 bytes both sides
    post-normalise).  18 dead ``.pql-*`` selectors dropped.  2
    commits ``761e4e25..cc1cf10f``.
  - **W6 — Frontend-Dokumentation**: NEW
    ``docs/development/frontend-architecture.md`` (292L, 2
    mermaid diagrams) + NEW
    ``frontend/templates/_macros/README.md`` (80L catalog of all
    14 macros) + refreshed ``design-tokens.md`` /
    ``frontend-conventions.md`` / ``frontend/js/README.md`` to
    absorb W2-W5 drift.  4 commits ``74c6efd7..55488ca7``, no
    asset bump (markdown-only).
  - **W7 — JS-Qualitätsschiene** (rc164 → rc167): greenfield JS
    tooling adoption with no Node.js (Biome native binary via
    ``biomejs/pre-commit v0.6.1`` + ``biomejs/setup-biome@v2``
    CI step).  ``biome.json`` + ``jsconfig.json`` (``checkJs:
    false`` to avoid implicit-any warnings).  ``biome format
    --write`` touched 160/164 files; ``biome check --write``
    safe-fixed 45; 6 manual lint-error fixes inline.  JSDoc
    ``@typedef`` backbone for ``cellThread`` + ``sqlEditor`` +
    ``coeditCore`` + composed ``notebookEditor`` (intersection of
    5 slice typedefs).  7 commits ``07c59916..df368898``.
  - **W8 — A11y + Form-Labels-Sweep** (rc167 → rc173): 3 new
    form-macros (``labeled_input`` / ``labeled_select`` /
    ``labeled_textarea``) that pair Bootstrap form-controls with
    ``<label for>`` association for WCAG 2.1 Level A 1.3.1 + 4.1.2
    compliance.  Repo-wide unlabeled form-control count: 172 →
    56 (67% drop).  Drift-guard ``scripts/check-form-labels.sh``
    (strips Jinja + HTML comments before scanning) + pre-commit
    + CI gate at threshold 75 (baseline 56 + 20 slack).  7
    commits ``df9ed6d6..0adaca5e``.

  Wave-spanning artefacts: 17 reusable Jinja macros catalogued
  in-tree; 3 drift-guard hooks (no-phase-refs / biome /
  form-labels) wired into pre-commit + CI; 3 new top-level docs
  under ``docs/development/``; JSDoc backbone for the 4 largest
  Alpine factories.  Full pytest 3529/0 at every wave-close;
  only test-suite touch was a single substring-assertion relax
  in ``tests/test_star_buttons_dom.py`` (W7.6) to absorb Biome's
  useArrowCallback transform.

> from CHANGELOG.md (bucket: **Changed**)

- **Phase 122 — Source-Code Sanitization for Publication (2026-05-24,
  rc138 → rc142).**  Four-sprint wave that strips project-
  management references from source comments + docstrings + e2e
  walkthroughs + README in preparation for the public release.
  ROADMAP, CHANGELOG, alembic migration filenames + docstrings, and
  git history are explicitly kept (each IS the phase artefact).
  Source-tree Phase ref count: 1622 → 260 (84% reduction); Sprint:
  362 → 72; Wave: 52 → 6; BUG-NN-NN markers: 21 → 7.  Renamed 12
  phase-keyed files (11 tests + 1 notebook + 1 walkthrough); 11
  test/helper function renames; new ``CLAUDE.md`` forward guard
  block prohibits future phase refs in source comments.  Commits
  ``69c33fe`` (122.1 mechanical), ``5ca77eb0`` (122.2 manual),
  ``ee4f0777`` (122.3 walkthroughs), ``b3566ea7`` (122.4 README +
  CLAUDE).
