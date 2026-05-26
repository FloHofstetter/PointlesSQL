---
title: "Phase 123 — Frontend Master-Plan (8-wave modernisation) (detail)"
audience: contributor
---

# Phase 123 — Frontend Master-Plan (8-wave modernisation)

Closed 2026-05-25.  Sub-sprint detail extracted from `ROADMAP.md` in W2
of the Documentation Master-Plan (per ADR-0009 D7, phases over 100 LOC
move their detail to a per-phase sidecar; the main ROADMAP keeps a
compact summary + pointer).

> See [ROADMAP.md](../../ROADMAP.md) for the project-level context and
> the active/queued roadmap.

## Summary

**All 8 waves closed 2026-05-25.** Largest single-domain wave the project has run: every HTML template, JS module and CSS file in ``frontend/`` was touched. Asset trajectory ``rc138 → rc173`` across ~35 commits. Plan- source: ``~/.claude/plans/ich-m-chte-dass-du-joyful- seal.md``. The wave finishes the publication-r...

## Full detail

```text
│   ├── Phase 123 — Frontend Master-Plan (8-wave modernisation)    ✅ done 2026-05-25
│   │     **All 8 waves closed 2026-05-25.**  Largest single-domain
│   │     wave the project has run: every HTML template, JS module
│   │     and CSS file in ``frontend/`` was touched.  Asset
│   │     trajectory ``rc138 → rc173`` across ~35 commits.  Plan-
│   │     source: ``~/.claude/plans/ich-m-chte-dass-du-joyful-
│   │     seal.md``.  The wave finishes the publication-readiness
│   │     drive Phase 122 started in the Python tree by extending
│   │     the same discipline to the frontend + adding the
│   │     structural overhauls that make the codebase navigable for
│   │     outside contributors and LLMs alike (no file >500 LOC, no
│   │     phase refs in source, IDE-readable types, drift-guard
│   │     hooks).
│   │
│   │     Why a single bundled phase: each wave is a self-contained
│   │     pre-condition for the next (forward-guard before edits,
│   │     ESM exodus before JS splits, splits before quality
│   │     tooling, tooling before A11y).  Splitting across phase
│   │     numbers would have invented artificial scoping that the
│   │     plan-file already covered.
│   │
│   │     - **W1 — Forward-Guard-Alignment** (Phase/Wave-Strip
│   │       Frontend).  ✅ done 2026-05-25, asset rc138 → rc142.
│   │       50 phase markers stripped across 35 frontend files +
│   │       new ``scripts/check-no-phase-refs.sh`` + pre-commit
│   │       hook + ``CLAUDE.md`` forward-guard extension to cover
│   │       templates / JS / CSS / user-facing UI strings (badge
│   │       text, tooltip ``title=``, alert bodies).  Commits
│   │       ``0cac177b`` (strip) + ``175013de`` (guard + hook).
│   │     - **W2 — Inline-Script-Exodus.**  ✅ done 2026-05-25,
│   │       asset rc142 → rc150.  65 templates' inline
│   │       ``<script>`` blocks (~6 250 LOC) extracted into
│   │       dedicated ESM modules under ``frontend/js/``.  Mega-
│   │       factories first (feed 739L → ``pages/feed.js`` /
│   │       data_product 716L → ``pages/data_product.js`` /
│   │       model 357L → ``pages/model.js``), then ``base.html``
│   │       exodus (-362 LOC: HTMX bridge / theme / UI helpers /
│   │       recent-storage extracted; FOUC-critical theme-init +
│   │       importmap stay inline by design), then Tier-2 + Tier-3
│   │       sweeps.  9 commits ``0cac177b..e86d0bfc``.  Two
│   │       templates (saved_view_embed + semantic_search_embed)
│   │       keep their inline scripts as iframe-standalones.
│   │     - **W3 — JS-Subsystem-Splits.**  ✅ done 2026-05-25,
│   │       asset rc150 → rc155.  Four largest notebook JS files
│   │       split below 350 LOC each.  ``coedit.js`` 565L → 32L
│   │       facade + 3 modules (coedit_core / coedit_awareness /
│   │       coedit_cell_binding).  ``cell_thread.js`` 402L → 342L
│   │       + 2 helpers (review_decision + cell_tag_picker).
│   │       ``revisions.js`` 396L → 235L + revision_diff.js.
│   │       ``kernel_execution.js`` 308L → 264L +
│   │       variable_inspector.js.  New ``frontend/js/http.js``
│   │       extracts the cookie-CSRF ``jsonFetch`` helper (sibling
│   │       to ``api.js`` meta-tag-CSRF strategy).
│   │       ``notebook_editor.js`` + ``bootstrap.js`` + every
│   │       template unchanged at the public-API boundary.  5
│   │       commits ``cfc8507a..6c8debe3``.
│   │     - **W4 — Template-Splits + Reuse-Macros.**  ✅ done
│   │       2026-05-25, asset rc156 → rc162.  3 new macros
│   │       (``badge`` / ``button`` / ``state_container``) + 5
│   │       mega-templates split: ``tab_lineage`` 514L → 61L + 5×
│   │       ~90L; ``branch_detail`` 460L → 28L + 4× ~110L;
│   │       ``revisions_panel`` 374L → 23L + 4× ~90L;
│   │       ``sql_editor`` 591L → 50L + 4× partials (results
│   │       colocated, not x-show-refactored to preserve mount-
│   │       timing semantics 1:1); ``meta_panel`` 826L → 38L + 8×
│   │       ~98L.  All wrappers ≤50 LOC, all sub-partials <260 LOC.
│   │       6 commits ``688865f7..708d04d9``.  ``icon_label`` +
│   │       ``if_permitted`` macros deferred (audit found
│   │       insufficient consumer surface).
│   │     - **W5 — CSS-Architektur-Konsolidierung.**  ✅ done
│   │       2026-05-25, asset rc162 → rc164.  ``notebook.css``
│   │       811L → 22L thin ``@import`` index + 7 sub-files in
│   │       ``frontend/css/notebook/`` (shell / tag_pickers /
│   │       cell_meta / revisions / cells / drawer /
│   │       interactions).  Sub-files are contiguous slices of the
│   │       original, ``@import`` order matches original file-
│   │       order so CSS cascade is preserved byte-identical
│   │       (14 976 bytes both sides post-normalise).  18 dead
│   │       ``.pql-*`` selectors dropped (Jupyter-iframe-page
│   │       leftovers + retired badge variants).  2 commits
│   │       ``761e4e25..cc1cf10f``.
│   │     - **W6 — Frontend-Dokumentation.**  ✅ done 2026-05-25,
│   │       no asset bump (markdown-only).  NEW
│   │       ``docs/development/frontend-architecture.md`` (292L)
│   │       as top-level consolidator: stack + dir layout +
│   │       bootstrap.js mechanism + 4-tier CSS cascade + lazy-
│   │       load + forward-guard hook + notebook subsystem map +
│   │       2 mermaid diagrams.  NEW
│   │       ``frontend/templates/_macros/README.md`` (80L)
│   │       catalogs all 14 macros (badge / button / state_container
│   │       from W4 + 11 pre-existing) with file + signature +
│   │       1-line purpose + macro/partial/inline decision rules.
│   │       Refreshed ``design-tokens.md`` + ``frontend-
│   │       conventions.md`` + ``frontend/js/README.md`` to absorb
│   │       W2-W5 drift.  4 commits ``74c6efd7..55488ca7``.
│   │     - **W7 — JS-Qualitätsschiene.**  ✅ done 2026-05-25,
│   │       asset rc164 → rc167.  Greenfield JS tooling adoption
│   │       in a Python-only repo with no Node.js.  ``biome.json``
│   │       config (2-space, single-quote, semicolons,
│   │       trailingCommas=es5, lineWidth=100, recommended rule
│   │       set with useTemplate / useOptionalChain /
│   │       noUnusedVariables downgraded to warn/info for
│   │       visibility without blocking).  ``jsconfig.json`` with
│   │       ``checkJs: false`` for IDE-readable JSDoc without
│   │       triggering 1000+ implicit-any warnings.  Pre-commit
│   │       hook ``biomejs/pre-commit v0.6.1`` + CI step
│   │       ``biomejs/setup-biome@v2`` both scoped to
│   │       ``^frontend/js/.*\.(js|mjs)$`` with
│   │       ``--diagnostic-level=error``.  ``biome format --write``
│   │       touched 160/164 JS files (~29K lines normalised, zero
│   │       semantic edits); ``biome check --write`` safe-fixes
│   │       45 files; 6 manual lint-error fixes inline (incl.
│   │       deleting a duplicate ``loadDiff`` method that W2.2
│   │       had preserved verbatim).  JSDoc ``@typedef`` backbone
│   │       for 4 large factories: ``cellThread`` + ``sqlEditor``
│   │       + ``coeditCore`` + composed ``notebookEditor`` via
│   │       TypeScript-style intersection of 5 slice typedefs
│   │       (KernelExecution + JobsOrchestration + Revisions +
│   │       Persistence + CoeditCore).  7 commits
│   │       ``07c59916..df368898``.
│   │     - **W8 — A11y + Form-Labels-Sweep.**  ✅ done 2026-05-25,
│   │       asset rc167 → rc173.  3 new form-macros under
│   │       ``frontend/templates/_macros/`` (``labeled_input`` /
│   │       ``labeled_select`` / ``labeled_textarea``) that pair a
│   │       Bootstrap form-control with a ``<label for>``
│   │       association so screen-readers announce field names
│   │       programmatically (WCAG 2.1 Level A 1.3.1 + 4.1.2).
│   │       Repo-wide unlabeled form-control count: 172 → 56
│   │       (67% drop, ~116 fixes).  Sweep coverage: 13 search-
│   │       input aria-labels + ``ingest_sources_new.html`` (17
│   │       controls via macro) + ``admin_audit_sinks.html`` (12
│   │       controls) + 6 modal forms (credentials / connections /
│   │       external_locations / dashboards / jobs /
│   │       saved_view_new ~26 controls) + 23 tail templates
│   │       ~110 controls.  Hybrid label-strategy: ``<label for>+
│   │       <input id>`` pair for static modals, ``aria-label`` /
│   │       ``x-bind:aria-label`` for Alpine-dynamic per-row
│   │       inputs where a wrapper would duplicate the label per
│   │       row.  Drift-guard ``scripts/check-form-labels.sh``
│   │       (strips Jinja ``{# #}`` + HTML ``<!-- -->`` comments
│   │       before scanning to avoid docstring false-positives) +
│   │       pre-commit hook + CI gate; ``FORM_LABEL_THRESHOLD``
│   │       env (default 75, baseline 56 with 20-control slack).
│   │       7 commits ``df9ed6d6..0adaca5e``.
│   │
│   │     Wave-spanning artefacts (introduced + propagated):
│   │       - 17 reusable Jinja macros (3 from W4 + 3 from W8 +
│   │         11 pre-existing), catalogued in
│   │         ``frontend/templates/_macros/README.md``
│   │       - 3 drift-guard hooks (no-phase-refs / biome /
│   │         form-labels) wired into pre-commit + CI
│   │       - 3 new top-level docs under ``docs/development/``
│   │         (frontend-architecture / refreshed design-tokens /
│   │         refreshed frontend-conventions)
│   │       - JSDoc ``@typedef`` backbone for the 4 largest Alpine
│   │         factories
│   │
│   │     What did NOT happen (deferred — captured in plan-file):
│   │       - Wholesale migration of ~475 inline badge + ~552
│   │         inline btn call-sites onto the W4 macros
│   │       - "Unsafe-fix Biome sweep" (~700 useOptionalChain +
│   │         useTemplate + noUnusedVariables-on-catch-``e`` hits
│   │         downgraded to warn/info)
│   │       - 13 smaller notebook installer slice-typedefs
│   │       - Tightening the form-label drift threshold from 75 →
│   │         ~25 (would require sweeping the remaining 56
│   │         unlabeled, mostly 1-2-per-file long tail)
│   │       - Mass migration onto ``--pql-*`` CSS tokens; 1
│   │         hardcoded ``rgba(118, 185, 0, 0.15)`` in
│   │         ``layout.css`` ~L95
│   │
│   │     Verification: full pytest 3529 passed / 0 failed at every
│   │     wave-close; ruff + biome + pyright + pydoclint clean;
│   │     drift-guards green.  No e2e walkthrough or unit test was
│   │     modified beyond a single substring-assertion relax in
│   │     ``tests/test_star_buttons_dom.py`` (W7.6, ``"window.
│   │     pqlStarToggle = function"`` → ``"window.pqlStarToggle = "``
│   │     to absorb Biome's useArrowCallback transform).
│   │
```
