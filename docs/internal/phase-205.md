---
title: "Phase 205 — Accessibility (WCAG-AA) Compliance (plan)"
audience: contributor
---

# Phase 205 — Accessibility (WCAG-AA) Compliance

**Status: ⏳ planned (geplant 2026-06-06).** Detail-Sidecar; siehe
[ROADMAP.md](../../ROADMAP.md) (Differentiator-Tiefe-Cluster 197–206).

## Warum

Die UI ist nach 188 Phasen breit und über lange Strecken schon
a11y-bewusst (607 `aria-`-Vorkommen, platformweites `prefers-reduced-
motion`, ein Form-Label-Drift-Gate in CI). Aber **es gibt keine
automatisierte a11y-Verifikation** und die schwierigen interaktiven
Widgets (cytoscape-DAG, Canvas-Editor, CodeMirror) sind a11y-Lücken. Damit
ist die Plattform für Screen-Reader-/Tastatur-Nutzer in den
Differenzierungs-Surfaces (Lineage-Graph, DP-Canvas) faktisch nicht
bedienbar — und jede UI-Änderung kann a11y still verschlechtern, weil kein
Gate es fängt.

Diese Phase treibt die UI auf einen verifizierten WCAG-AA-Stand: axe-core
in CI (auf der vorhandenen Playwright-Infra), die harten Widgets
nachgerüstet, und ein Violations-Floor als Ratsche.

## Ausgangslage (Fakten)

- **Templates:** 294 HTML-Dateien, 18 Macros (`_macros/`, inkl.
  `labeled_input`/`labeled_select`/`labeled_textarea`/`help_icon`), 46
  Komponenten. **607 `aria-` + 397 `role`** über Templates. Base-Layout
  [`base.html`](../../frontend/templates/base.html) (29 `aria-`),
  Icon-Rail-Nav `components/primary_rail.html`.
- **Form-Label-Gate vorhanden**
  ([`.github/workflows/test.yml:86-97`](../../.github/workflows/test.yml)
  → `scripts/check-form-labels.sh`, Schwelle 75, Baseline ~63):
  ungelabelte `<input>/<select>/<textarea>` ohne aria-label/-labelledby/
  `<label for>`/Wrap-Label.
- **Reduced-Motion platformweit**
  ([`base.css:243-319`](../../frontend/css/base.css): globaler
  `@media (prefers-reduced-motion: reduce)`-Catch-All); reduced-transparency
  in [`components/surfaces.css:124-140`](../../frontend/css/components/surfaces.css).
  **Das Muster zum Fortschreiben.**
- **Frontend-Tooling:** Biome 2.4.15 (`biome.json`) lintet `frontend/js/`
  — **keine a11y-Regeln**. 237 `.js`-Dateien, **kein JS-Unit-Runner**.
  **Kein axe-core.**
- **Risiko-Widgets:** cytoscape-DAG
  ([`frontend/js/components/lineage_dag/`](../../frontend/js/components/lineage_dag/),
  5 Dateien, keine aria-Labels), Canvas-Editor
  ([`frontend/js/canvas/`](../../frontend/js/canvas/) + `dp_canvas/editor/`,
  Ansatz „Enter/Space auf fokussiertem Node" in `codemirror_predicate.js`),
  CodeMirror-SQL-Editor (kein a11y-Wrapper), HTMX-Partial-Swaps (79 `hx-`),
  Alpine-Dropdowns (4464 `x-`).
- **Tastatur:** [`frontend/js/list_keyboard.js`](../../frontend/js/list_keyboard.js)
  (Gmail-Style j/k/x/Esc/Enter), `canvas/_focus_mode.js` (Shift+F),
  `permission_link.html` `tabindex=0`.
- **CI-Frontend-Gates:** Biome, Form-Label-A11y, no-reactive-monaco,
  bootstrap-order, no-phase-refs. **Kein axe-core.** Playwright
  ([`e2e/conftest.py`](../../e2e/conftest.py)) **kann axe-core hosten**
  (page.evaluate) — Infra steht.
- **UI-Perf-Regel:** kein backdrop-filter/Animation (software-composited),
  [[ui-perf-no-backdrop-filter]] — a11y-Fokus-Ringe/Kontrast müssen ohne
  Filter funktionieren.

## Scope (Wellen)

### W1 — axe-core-Harness (auf Playwright)
- axe-core in die e2e-Infra: Helper, der je Seite `axe.run()` über
  `page.evaluate` fährt und Violations nach Impact (critical/serious/
  moderate/minor) sammelt. Läuft im e2e-Job (Phase 198 teilt die
  Surface-Liste — jede automatisierte Journey kriegt einen axe-Scan
  „gratis").
- Baseline aller aktuellen Violations als Floor (Muster der vorhandenen
  Budgets), pro Welle gesenkt.

### W2 — Globale Primitive (größter Hebel)
- Base-Layout, Icon-Rail-Nav, Skip-Link, Landmark-Rollen, Fokus-
  Management bei HTMX-View-Transitions (Fokus nach Swap setzen),
  Live-Regions für Toasts/Async-Status. Behebt Violations über *alle*
  Seiten auf einen Schlag.

### W3 — Formulare, Modals, Popover
- Macros (`labeled_*`, `help_icon`) als kanonische a11y-Quelle härten;
  Modals (Fokus-Trap + -Restore), Bootstrap-Popover (`trigger=focus` →
  Fokus-Restore nach Dismiss), Disclosure/Dropdown-`aria-expanded`.
  Form-Label-Schwelle Richtung 0 senken.

### W4 — Tastatur-Navigation vervollständigen
- Konsistente Tab-Order + sichtbare Fokus-Ringe (ohne CSS-filter) über
  alle interaktiven Elemente; `list_keyboard`/`_focus_mode`-Muster
  verallgemeinern; keine Keyboard-Traps in Canvas/CodeMirror/Modals.

### W5 — Risiko-Widgets nachrüsten
- **cytoscape-DAG:** Tastatur-Navigation der Knoten/Kanten + Text-
  Alternative (eine zugängliche Tabellen-/Listen-Repräsentation des
  Graphen daneben), aria-Labels, Live-Region für Selektion.
- **Canvas-Editor:** Knoten fokus-/tastaturbedienbar (Ansatz ausbauen),
  zugängliche Beschreibung der Pipeline.
- **CodeMirror:** Label + Anweisungen + Status-Live-Region; Escape-Hatch
  aus dem Editor-Fokus.

### W6 — Biome-a11y-Regeln + Doku
- a11y-Lint-Regeln aktivieren, wo Biome sie bietet (sonst ein leichter
  Template-Linter im Stil von `check-form-labels.sh` für `role`/`alt`/
  `aria-*`-Hygiene). Kontrast-Audit der Farb-Tokens (`base.css`) gegen
  AA (4.5:1 Text). a11y-Checkliste in CLAUDE.md/Doku + e2e-axe-Gate scharf.

## Akzeptanzkriterien
- axe-core läuft je automatisierter Journey; **0 critical/serious**
  Violations; moderate/minor unter dokumentiertem, sinkendem Floor.
- Jede Kern-Journey (Katalog → Tabelle → Lineage → DP-Canvas → SQL-Editor)
  ist rein per Tastatur durchführbar (e2e-Tastatur-Pfad grün).
- cytoscape-DAG + Canvas haben eine Text-/Tabellen-Alternative + Tastatur-
  Bedienung.
- Form-Label-Schwelle auf 0 (oder dokumentierter Rest mit Begründung);
  Kontrast-Tokens erfüllen AA.
- Ein bewusst eingebauter a11y-Regress (entferntes Label, falsche Rolle)
  lässt das axe-Gate failen.

## Risiken / Notizen
- **Canvas/SVG-Graphen sind inhärent schwer a11y** — die Text-Alternative
  (Tabelle/Liste) ist der pragmatische AA-Weg, nicht „SVG screenreaderbar
  machen".
- Fokus-Ringe ohne `filter`/`box-shadow`-Blur (UI-Perf-Regel) — `outline`
  + Kontrast nutzen.
- Floor großzügig starten (viele moderate aus Third-Party-Widgets);
  an der Quelle fixen, keine pauschalen Suppressions.
- Verwandt: Phase 23 (Help-Popover), Phase 184 (Canvas Reduced-Motion —
  Vorlage), Phase 198 (e2e teilt Surface-Liste), [[ui-perf-no-backdrop-filter]].
