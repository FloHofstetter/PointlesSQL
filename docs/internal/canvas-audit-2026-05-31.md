# Canvas Quality Audit — Befundbericht
**Datum:** 2026-05-31  
**Stand:** rc232 (Commits 29106de0 + e75764ef + 0dded82f — Phase 176 Edge-Politur)  
**Auditor:** Claude Code (Opus 4.7, 1M-context), AuditBot session  
**Benchmark:** n8n Vue Flow Canvas (`packages/frontend/editor-ui/src/features/workflows/canvas`)

---

## 0. Methodik

- **Tooling**: Playwright MCP gegen lokales `uv run pointlessql` (rc232).
  Login als frisch-provisionierter `audit2026@pql.local` (admin +
  supervisor, vom User explizit erlaubt). Screenshots unter
  `.playwright-mcp/audit-*.png|jpg`. Viewport 1600×1000.
- **n8n-Anchor**: Live-Fetch via `gh api` der relevanten Vue-Komponenten
  unter `…/canvas/components/elements/{edges,handles,nodes}`. Volltext-
  Extraktion via WebFetch.
- **Scope**: Drei Drawflow-basierte Canvas-Surfaces. Vierte „Surface"
  `/editor` aus User-Prompt existiert nicht (404); `/canvas` ist ein
  Listen-Prototype mit `Prototype`-Badge — **out-of-scope** für diesen
  Politur-Sweep.

| Surface | URL | Status |
|---|---|---|
| DP-Canvas | `/dp/{id}/canvas` | Drawflow, Phase 176 polish present |
| Mesh-Canvas | `/mesh/canvas` | Drawflow, kein Phase-176 polish |
| Diff-Canvas | `/dp/{id}/canvas/diff` | 2× Drawflow side-by-side, Read-only |
| ~~Editor-Canvas~~ | `/editor` | **404 — Surface existiert nicht** |
| ~~/canvas~~ | `/canvas` | Prototype, list-based, kein Drawflow |

---

## 1. n8n-Referenz (was wir uns als Ziel nehmen)

Auszüge aus `CanvasEdge.vue`, `CanvasEdgeToolbar.vue`,
`CanvasHandleMainOutput.vue` (master, Mai 2026):

- **Stroke** zoom-kompensiert: `calc(2 * var(--canvas-zoom-compensation-factor, 1))`.
  Wir nutzen `var(--pql-edge-stroke) / var(--pql-zoom)` — derselbe Effekt,
  aber n8n schreibt `--canvas-zoom-compensation-factor` synchron ins DOM
  per Vue-Flow store; bei uns landet `--pql-zoom` auf `df.on('zoom')` —
  Drawflow feuert das NUR bei Wheel-Zoom, nicht bei Pinch-Zoom oder
  programmatic `df.zoom_in/out/reset`. → Audit-Befund #5.
- **State-Klassen**: nur `hovered` und `bring-to-front`. Wir haben:
  `pql-edge-hover`, `pql-edge-selected`, `pql-edge-running`,
  `pql-edge-numeric/-text/-temporal/-boolean/-complex/-mixed`. Reicher
  als n8n — gut.
- **Hover-Delay**: n8n nutzt `delayedHovered` — die Edge geht erst nach
  einer kleinen Latenz in den Hover-State (verhindert Flicker beim
  Maus-Cross). Wir reagieren instant → Audit-Befund #6.
- **Edge-Typ**: `oklch()` mit `light-dark()` für theme-aware Farben.
  Wir nutzen `var(--bs-primary)` etc. — Bootstrap-Variablen sind
  theme-aware via `[data-bs-theme]`, equivalentes Ergebnis. OK.
- **Marker-end (Arrow)**: nur auf "main" connections, dashed
  `5,6` für non-main. Wir setzen marker-end IMMER + type-color als
  Differenzierung. OK, aber siehe Befund #2.
- **Marching-ants**: n8n hat KEINE. Wir haben sie für
  `pql-edge-running`. Wertvoll, behalten.
- **Mid-toolbar**: feste flex-row mit add+delete buttons, gap
  `var(--spacing--2xs)`, `subtle` button variant. KEIN Fade-in.
  Pointer-events:all. Wir haben dieselbe Struktur + 600 ms exit-delay.
  Layout match, aber siehe Befund #7.
- **Plus-handle**: Vue `<Transition>` mit `scale(0)→(1)` 200 ms ease.
  Wir machen 120 ms opacity. → Befund #9.

---

## 2. DP-Canvas Befunde

### Severity-Bucket: **Critical**

#### Befund #1 — Stage-Real-Estate katastrophal
**Screenshot:** `.playwright-mcp/audit-dp-canvas-01-loaded.png`,
`audit-dp-canvas-10-asloaded.png`  
Bei 1600 px Viewport verbraucht das Chrome: Primary nav 220 px +
Section nav 239 px + Palette 220 px + Drawer 320 px = **999 px** chrome,
bleiben **~537 px Canvas-Stage** (33.5%). n8n in derselben Viewport
gibt ~85% an die Canvas. **Das ist der dominante Grund warum sich alles
"klein, gedrungen, übersehen" anfühlt.**

#### Befund #2 — Output-Plus überlappt existierende Edge
**Screenshot:** `audit-dp-canvas-11-stage-loaded.png` — der "+"-Kreis
zwischen Input-port und Filter sitzt genau ON der bezier-curve.  
Wenn ein Output-Pin bereits eine ausgehende Edge hat, rendert das
always-on `pql-output-plus` (opacity 0.75) trotzdem direkt auf dem
Pin — User-Intent ambig: ist das "edge ändern" oder "neue edge"?  
**n8n löst das**: Plus-handle wird unsichtbar wenn outgoing edge
existiert (`isHandlePlusVisible` checkt run-data + connection-state).

#### Befund #3 — Sticky-Note Default-Position überlappt Input-Node
**Screenshot:** `audit-dp-canvas-01-loaded.png` — gelbe sticky-note bei
(280, 80) verdeckt halb das erste Node.  
DP 4 hat 1 sticky-note bei (280, 80), Input-port-Node bei (100, 200)
mit width ~190 + position-translate. Bei Drawflow-default-pan landet
das sticky-note exakt im Anbiet-Bereich. → Default-Position-Heuristik
fehlt: niemals ON-TOP eines Nodes platzieren.

### Severity-Bucket: **High**

#### Befund #4 — Edge-Hover/Select bei Default-Zoom kaum sichtbar
**Screenshots:** `audit-dp-canvas-12-edge-hover.png`,
`audit-dp-canvas-13-edge-selected.png`  
Edge-Länge ~75 px (Standard-Spacing 280 px zwischen Nodes minus Node-
Width 190 px = 90 px sichtbare Edge). Stroke 2.5 px Default → 4 px
Hover → 5 px Selected. Bei der kurzen Edge ist das Glow-Filter (0,0,4
px) breiter als die Edge selbst — überstrahlt den Stroke-Effekt.  
**Fix-Hint**: Glow-Radius dynamisch von Edge-Länge ableiten, ODER
Edge-Color in Hover/Select kontrastreicher (z.B. komplementärfarbe
des Type-color statt fixed bs-warning).

#### Befund #5 — `--pql-zoom` CSS-Var staled bei programmatic zoom
**Code-Inspektion:** `dp_canvas_editor.js` setzt `--pql-zoom` nur in
`df.on('zoom', …)`. Drawflow 0.0.59 dispatched `zoom` NUR bei
mousewheel, nicht bei programmatic `df.zoom_in()`, `df.zoom_reset()`,
oder direktem `df.zoom = X`.  
Resultat: Stroke-Width bei programmatic zoom (z.B. Toolbar
Zoom-In/Out-Buttons, fit-to-screen, minimap-click) wird NICHT
zoom-kompensiert → Strokes werden bei zoom-out dünn, bei zoom-in dick.  
**Fix-Hint**: `MutationObserver` auf `.parent-drawflow .drawflow` (das
ist das transform-target) → parse `transform: scale(X)` → update
`--pql-zoom`. ODER monkey-patch `df.zoom_refresh()` um custom event.

#### Befund #6 — Kein Hover-Delay → Edge-Flicker beim Maus-Cross
**Beobachtung:** Mouse-Pfad über mehrere Edges hintereinander triggert
schnelles Hover-On/Off-Flackern (Edge wird abwechselnd blau dick mit
Glow, dann normal). Bei 4-Node-Pipeline kaum kritisch, bei 20-Node-
Mesh nervig.  
**Fix-Hint**: 80-120 ms Hover-Delay (à la n8n's `delayedHovered`).

#### Befund #7 — Mid-Edge-Toolbar Click-Latenz fühlt sich kaputt an
**Code:** `dp_canvas_editor.js` setzt 600 ms exit-delay — der Mauszeiger
muss 600 ms außerhalb der Toolbar bleiben bevor sie verschwindet.
**UX-Effekt**: Schnelles Hovern → Edge A hover → Toolbar A erscheint
→ Maus zu Edge B → Toolbar A bleibt 600 ms sichtbar, Toolbar B
erscheint ON TOP. **Race-Condition während des delay-Windows**.  
**Fix-Hint**: Single shared Toolbar (DOM-recycling) → re-position
statt show/hide.

### Severity-Bucket: **Medium**

#### Befund #8 — Node-Body Code-Style rosa-pink lesbar als Error
**Screenshot:** `audit-dp-canvas-09-no-backdrop.png` —
"main.canvas_walk_demo.orders" + "amount > 50" + "n = 10" in
Bootstrap-Default `<code>` color #d63384 (rose-pink).  
User-Erstwirkung: "ist das ein Fehler?" Erst zweiter Blick erkennt
das Code-Styling. **Fix-Hint**: in `.pql-node-body code` explizit
neutralere Farbe setzen (`var(--bs-secondary)` oder
`var(--bs-emphasis-color)`).

#### Befund #9 — Output-Plus Hover-Transition zu instant
**Code:** `pql-output-plus` Transition 120 ms opacity. n8n nutzt
scale(0)→(1) 200 ms ease. Sieht weicher aus.  
**Fix-Hint**: combine opacity + transform: scale(0.85→1.0) 180 ms.

#### Befund #10 — Minimap visuell-positioniert konkurriert mit Output-Port
**Screenshot:** `audit-dp-canvas-08-stage-only.png` — Minimap fest
bei `bottom: 12px; right: 12px`. Wenn User Output-Port-Node nach
unten-rechts zieht (z.B. autolayout), klebt Minimap drauf.  
**Fix-Hint**: Minimap collapsible + verschiebbar (n8n hat sie default-
off).

#### Befund #11 — Edge-Type-Coloring nur am Source-Schema, nicht propagiert
**Code:** `pql-edge-numeric` etc. ist vom upstream-Pin abgeleitet.
Aber wenn ein Filter auf den input zu typ-mixed wird, bleibt die
ausgehende edge "numeric" (vom upstream). Inkonsistent vs. echte
Schema-Propagierung.  
**Fix-Hint**: Nach `_compile`-Pass das edge-class vom downstream-port
re-computen.

### Severity-Bucket: **Polish**

#### Befund #12 — Save-Indicator-Text "Saved · HH:MM:SS" zu prominent
**Screenshot:** `audit-dp-canvas-10-asloaded.png` — bei jedem auto-save
flackert die Zeit. Konsole-Print-Style. Subtle "✓ Saved" mit relative-
time-tooltip wäre n8n-stil.

#### Befund #13 — Topbar-Button-Cluster ohne Tooltips/Gruppierung
**Screenshot:** `audit-dp-canvas-10-asloaded.png` — 8 ungelabelte
Icon-Buttons zwischen "no errors" und "Save". Müsste auseinandergerückt
mit btn-group + tooltips.

#### Befund #14 — Versionen-Dropdown "Versions ▾" pinned-state nicht visualisiert
**Code:** Phase 155 hat is_production pin/unpin gebracht. Im Dropdown
sieht man nur ein "v17 pinned" badge im topbar — der pin-State der
ANDEREN versions im Dropdown nicht erkennbar bis man auf-klickt.

---

## 3. Mesh-Canvas Befunde

### Severity-Bucket: **Critical**

#### Befund #M1 — Phase 176 Polish komplett fehlt
**Screenshot:** `audit-mesh-canvas-01-loaded.jpg`  
Edges: kein fat hit-area, kein hover-state, kein select-state, keine
arrowheads, kein mid-toolbar, kein type-coloring, kein zoom-compensation.
Plain default Drawflow style (1 px stroke, grey, no marker-end).  
**Effekt**: Mesh-Canvas fühlt sich wie 5 Jahre älter an als DP-Canvas.

### Severity-Bucket: **High**

#### Befund #M2 — Edge-Routing macht S-Curves mit Z-Knick
**Screenshot:** `audit-mesh-canvas-01-loaded.jpg` — Edge von
`demo.sales` (rechts-pin) → `main.canvas_walk_demo` (links-pin)
loop-back-down-left-then-right statt smooth bezier. Drawflow's
default-curve assumtion ist horizontaler Layout.

#### Befund #M3 — `<code>` rendering identisch problematisch
"id 1", "id 2", "id 4", "id 5" — Pink-Rose. Selber Befund wie #8.

### Severity-Bucket: **Medium**

#### Befund #M4 — Linke Spalte 250 px Hilfetext nimmt Stage-Platz
**Screenshot:** ditto. Hilfetext "Each node is a data product. Drag
from the right pin…" könnte in tooltip / banner gehen.

#### Befund #M5 — Rechte Spalte "Validation runs whenever…" auch
240 px für 3 Zeilen Erklärtext.

---

## 4. Diff-Canvas Befunde

### Severity-Bucket: **Critical**

#### Befund #D1 — Node-Skin komplett anders als Editor (Cyan-Türkis)
**Screenshot:** `audit-diff-canvas-01-loaded.jpg`  
Nodes sind cyan/turquoise gefüllt, vs. weiß/light-grey im DP-Editor.
User-Erkennungs-Disconnect: das sind DIESELBEN Blöcke, sehen aber
wie ein anderes Produkt aus.  
**Fix-Hint**: Diff-Editor soll Editor-Skin re-use mit overlay-tint
(green/red/yellow added/removed/modified) per box-shadow inset oder
border.

#### Befund #D2 — Side-by-Side rechte Hälfte fällt aus Viewport
**Screenshot:** rechtes "After"-Panel fängt bei x≈840 px an,
Filter-Node endet bei x≈1430, die Edge danach läuft ins Off-Screen.  
2 × Drawflow + alle Sidebars = > Viewport. **Fit-to-View-per-Panel
fehlt**, kein zoom-to-fit-button pro Seite.

### Severity-Bucket: **High**

#### Befund #D3 — Keine Node-Body-Details
Block-name + type-label, das war's. Schema columns, config (predicate,
limit), table-fqn fehlen alle. "Was hat sich GENAU geändert?" muss
über List-View beantwortet werden.  
**Fix-Hint**: Compact-Body variant (3 Zeilen max) im Diff zeigen.

#### Befund #D4 — Modified-State Box-Shadow zu fett (8 px gold)
Visuelles Gewicht überstrahlt den eigentlichen "added"-grünen Edge.
Heuristik: subtle border-left 4 px + leichter glow.

### Severity-Bucket: **Medium**

#### Befund #D5 — Kein Zoom, kein Minimap, kein Fit
Keine Zoom-Controls. Nodes sind im current viewport entweder fit
oder eben nicht. Für Diffs > 6 Nodes pro Seite: useless.

---

## 5. Cross-Surface Befunde

#### Befund #X1 — `--pql-zoom` ist DP-only
CSS-Var nur auf `.pql-dp-canvas-drawflow`. Mesh + Diff drawflow-instances
haben sie nicht → zoom-kompensierte stroke-widths existieren dort
nicht. Aber Phase 176 hat sie nur DP-spezifisch eingeführt — bewusst.
Should be promoted to a shared `.pql-canvas` base class.

#### Befund #X2 — Phase-176 CSS-Patterns nicht extrahiert
Die ~250 LOC neue CSS-Regeln (hit-area, state-classes, marker-end,
zoom-vars) sitzen in `dp_canvas_editor.css`. Bei Cross-Surface-Politur
copy/paste-Risiko hoch.  
**Fix-Hint**: extrahiere zu neuem `frontend/css/canvas_shared.css` mit
`.pql-canvas` Basis-Klasse, alle 3 Surfaces erben.

#### Befund #X3 — Drawer/Sidebar-Pattern uneinheitlich
DP: rechter 320 px Drawer mit Block-Config-Form.
Mesh: linker 250 px + rechter 240 px Hilfetext-Spalten.
Diff: kein Drawer, full-width 2-Panel-Split.
Drei verschiedene Layout-Strategien für drei sehr ähnliche Surfaces.

---

## 6. Empfohlene Priorisierung für Welle Phase 177

**Welle ~600 LOC** (User-Budget):

### MUST (Critical bucket)
- **#1** Stage-Real-Estate**: Add `focus-mode` toggle der Primary-Nav +
  Section-Nav per CSS auf 0 px collapsed. Drawer collapsible.
- **#2** Output-Plus hide-when-connected (read connection-state in
  `_drawOutputPlus()`).
- **#3** Sticky-note collision-avoid: auf save, check overlap mit jedem
  Node → shift down/right by 40 px max 4 attempts.
- **#M1** Mesh-Canvas Phase-176-Pattern adopten: hit-area + hover/select
  state + marker-end arrows (NICHT type-color — mesh-edges sind alle
  "DP-binding" type).
- **#D1** Diff-Canvas Node-Skin re-use vom Editor + add/removed/modified
  als overlay-class (`.pql-diff-added`, `.pql-diff-removed`,
  `.pql-diff-modified`).

### SHOULD (High bucket)
- **#4** Edge-Hover/Select Glow-Filter dynamisch von Edge-Länge.
- **#5** MutationObserver auf `.drawflow` transform → `--pql-zoom` live.
- **#6** Hover-delay 100 ms via timeout-debounce in
  `_attachEdgeInteraction()`.
- **#D2** Diff-Canvas per-panel fit-to-view button + auto-fit on load.
- **#X2** Extrahiere shared CSS → `canvas_shared.css` + `.pql-canvas`
  base-class. Mesh + Diff erben.

### COULD (wenn Zeit; sonst Phase 178)
- **#7** Single shared mid-toolbar mit reposition.
- **#8** Node-body `<code>` color override.
- **#9** Output-plus scale-Transition.
- **#D3** Diff-Canvas compact-body variant.
- **#13** Topbar btn-group + tooltips.

### WON'T (deferred / out-of-scope)
- **#10** Minimap re-positioning (separate UX-decision).
- **#11** Edge-Type-Coloring post-compile-pass (touches compiler).
- **#14** Versions-Dropdown pin-badges (Phase 155 surface).
- **#X3** Drawer/Sidebar pattern unification (architectural,
  Phase 178+).

---

## 7. Test-Plan für Welle

1. `uv run pointlessql` + Playwright-replay aller 11 oben referenzierter
   Screenshots → `after-*` Pendants.
2. Visual-diff `before-*` vs. `after-*` per `compare` tool oder
   manuell-side-by-side.
3. `biome check frontend/js/pages/ frontend/css/`
4. `bash scripts/check-no-phase-refs.sh`
5. `uv run pytest -x` (4121 passed expected).
6. `?coedit=1` smoke: Y.Doc co-edit darf NICHT regressen.
