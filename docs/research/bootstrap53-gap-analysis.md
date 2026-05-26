# Bootstrap 5.3 Gap Analysis

> Phase 53 Sprint A — Cross-check of PointlesSQL frontend against
> Bootstrap 5.3 official examples + components docs.
> Date: 2026-05-07.

This document is **input** for the Phase 53 UI Overhaul Proposal
([`ui-overhaul-proposal.md`](ui-overhaul-proposal.md)). It is
NOT a recommendation by itself — it is the data layer.

## TL;DR

PointlesSQL uses Bootstrap 5.3 deeply (cards, modals, badges,
breadcrumbs, alerts, offcanvas all at scale) and wraps it with a
coherent design-token layer (`.pql-stack`, `.pql-cluster`,
`--pql-space-N`, `--pql-text-*`). Three concrete adoption
opportunities stand out, ranked by impact-to-effort ratio:

1. **Wire the half-finished color-modes toggle** (Bootstrap 5.3's
   flagship feature, our CSS is 95% there, only the toggle UI +
   localStorage persist is missing).
2. **Adopt `accordion` for nested detail blocks** in run-detail /
   audit-search filters / table-detail Rejects/Operations panes
   where we currently render flat stacks of `.card` elements.
3. **Replace ad-hoc offset-pagination prose with Bootstrap's
   `pagination` component** on `/audit/search`, `/audit/queries`,
   `/runs`, `/jobs/.../runs` — these pages already paginate
   server-side, but render no nav.

Two patterns are deliberately marked **out of scope** because
adopting them would create more friction than value:

- `scrollspy` — would add value on `grand-tour.md` and the
  6-tab-deep audit-cockpit pages, but our existing tab-nav (with
  `nav-tabs` + `data-bs-toggle`) is already the canonical UX. A
  scrollspy retrofit would mean reflowing tabs into stacked
  sections.
- The Bootstrap dashboard example's exact layout
  (`col-md-3 col-lg-2` sidebar + `col-md-9 col-lg-10` main) —
  Phase 17 already chose a stricter icon-rail (80px) +
  context-panel (240px) layout via custom CSS Grid because the
  Bootstrap col-grid wastes horizontal real-estate at viewport
  widths < 1280px.

## Pattern Adoption Table

| Bootstrap 5.3 pattern | Have? | Worth adopting? | Effort | Notes |
|---|---|---|---|---|
| `data-bs-theme` color-modes API | **Half** | **Yes** (high impact) | S (½ day) | CSS-vars done in [base.css](../../frontend/css/base.css). Need: toggle UI + localStorage + `prefers-color-scheme` listener. |
| `accordion` for stacked details | **No** | **Yes** | S-M | Use on `/runs/{id}` Operations/Rejects/Cells panels and `/audit/search` filter pane. |
| `pagination` component | **No** | **Yes** | S | Pages already paginate server-side; only render is missing. Audit-search, query-history, /runs, /jobs/.../runs. |
| `scrollspy` | **No** | **No** | M | Would force tab-to-section reflow; our `nav-tabs` is canonical. |
| `position-sticky top-0` table headers | **Partial** | Yes | XS | List pages already do this in custom CSS; could move to BS utility. |
| `flex-shrink-0` + `vh-100` sidebar | N/A | No | — | Phase 17 chose CSS Grid icon-rail; standard sidebar pattern is wrong fit. |
| `border-bottom` + `py-3` page headers | **Yes** | already done | — | Page-header convention is already established repo-wide. |
| `navbar-expand-lg` collapsing menu | **Partial** (offcanvas only) | Optional | M | Mobile uses offcanvas drawer. Desktop has icon-rail. No need to merge. |
| Hero / Album / Footer multi-column | N/A | No | — | Marketing-page patterns; PointlesSQL is a webapp not a brochure. |
| `card-grid` with `col-md-6 col-lg-4` | **Yes** | already done | — | `/dashboards`, `/jobs`, home page. |
| `placeholder-glow` skeletons | **Yes** | already done | — | 92 refs, well-exploited. |
| `toast` notifications | **Partial** (5 refs) | Yes (more sites) | XS-S | Could replace some in-page `.alert-success` flash patterns. |
| `progress` bars | **No** (1 ref) | Optional | XS | Run-progress card on home page might benefit. |
| Object-fit utilities (5.3 new) | **No** | No | — | No image-grid use-cases (we are not a CMS). |
| Link utilities (5.3 new) | **Partial** | Optional | XS | `.link-primary`, `.link-underline-opacity-*` could replace some inline link styling. |
| CSS-vars on every component | **Yes** | already done | — | We override `--bs-body-bg`, `--bs-border-color`, etc. via `:root` and `data-bs-theme="light"`. |
| Theme-bd-theme switcher in navbar | **No** | follows from #1 | XS | Standard Bootstrap pattern: `<div id="bd-theme">` with 3 buttons. |

## Where Each Pattern Could Fit Concretely

### 1. Color-modes toggle

- **Where:** add to `base.html`'s top-right user dropdown (next to
  user-avatar + sign-out).
- **HTML:** Bootstrap-canonical `<div id="bd-theme">` with
  `data-bs-theme-value="light|dark|auto"` buttons.
- **JS:** ~30 LOC inline in `base.html` (the Bootstrap
  recommended pattern: read `localStorage.theme`, fall back to
  `matchMedia('(prefers-color-scheme: dark)')`, persist on
  toggle, update `<html data-bs-theme="...">`).
- **CSS:** already done — [base.css](../../frontend/css/base.css)
  has full light-mode override under
  `:root[data-bs-theme="light"]`.
- **Risk:** light-mode CSS may have visual debt (Phase 17 said
  "no toggle wired yet" — possibly because some component-level
  styles regress). Replay sweep (Sprint B) will surface these.

### 2. Accordion for detail-card stacks

Current pattern on `/runs/{id}` Operations tab:

```html
<div class="card mb-3"><h5>Added in B</h5> ...</div>
<div class="card mb-3"><h5>Removed in B</h5> ...</div>
<div class="card mb-3"><h5>Changed in B</h5> ...</div>
```

Could become:

```html
<div class="accordion" id="ops-axis">
  <div class="accordion-item">
    <h2 class="accordion-header">
      <button class="accordion-button">Added in B (12)</button>
    </h2>
    <div class="accordion-collapse collapse show">...</div>
  </div>
  ...
</div>
```

Wins: collapse-by-default for empty buckets; counts in the
header without forcing user to expand; `accordion-flush` keeps
visual density.

**Pages where this fits:** `/runs/{id}` Operations + Rejects +
Cells, `/audit/search` filters, table-detail Lineage panel
(currently 3-column-grid which doesn't collapse on narrow
viewports).

### 3. Pagination component

Current pattern on `/audit/search`:

```html
{% for row in results %}
  <tr>...</tr>
{% endfor %}
{# no nav, user must hand-edit ?offset=N in URL #}
```

Already exists server-side (offset/limit query params, total in
response). Just needs render:

```html
<nav aria-label="Audit search results">
  <ul class="pagination justify-content-center">
    <li class="page-item disabled"><a class="page-link">Previous</a></li>
    <li class="page-item active"><a class="page-link" aria-current="page">2</a></li>
    ...
    <li class="page-item"><a class="page-link" href="?offset=20">Next</a></li>
  </ul>
</nav>
```

**Pages where this fits:** `/audit/search`, `/audit/queries`,
`/runs`, `/jobs/{id}` runs table, `/data-products` (if list
grows), `/models` (post-21.5 may already have ≥ 100 entries on
demo data).

## Bootstrap 5.3 Features Status

| 5.3 feature | Status | Comment |
|---|---|---|
| Color-modes API (`data-bs-theme`) | Used | Hard-coded `dark` in `base.html`. Toggle missing. |
| CSS variables on every component | Used | Token system (`--pql-*`) maps cleanly to BS vars (`--bs-body-bg` etc). |
| Object-fit utilities (`object-fit-cover`) | Not used | No image-heavy pages. |
| Link utilities (`link-primary`, `link-underline-opacity-*`) | Not used | Could replace `.text-primary` + custom hover rules. |
| `placeholder` (skeleton loaders) | Used | 92 refs, lighthouse-quality skeletons in HTMX `hx-indicator` fallbacks. |
| `offcanvas` | Used | Mobile sidebar drawer (11 refs). |
| `toast` | Used (light) | 5 refs only — opportunity to expand. |

## Out-of-Scope Patterns (and why)

- **scrollspy** — Our long pages (`grand-tour`, audit-cockpit
  deep-dive, run-detail) all use `nav-tabs` + `data-bs-toggle`
  for section-switching. Scrollspy assumes a stack-of-sections
  layout, which we deliberately don't have. Adoption would mean
  reflowing tabs into stacks — a UX regression.
- **Bootstrap dashboard col-grid** (`col-md-3 col-lg-2` +
  `col-md-9 col-lg-10`) — Phase 17 chose CSS Grid icon-rail
  (80px) + context-panel (240px) because at 1280px viewport, the
  `col-md-3` sidebar (320px) wastes 100+px. The custom layout is
  intentional, not technical-debt.
- **Hero / album / footer marketing patterns** — wrong genre.
  PointlesSQL is a webapp, not a marketing site. The mkdocs
  documentation site is where these would live, and it already
  has the material-mkdocs theme.
- **`navbar-expand-lg` desktop collapsing menu** — we have an
  icon-rail at all viewport widths ≥ md. The mobile offcanvas
  drawer below md handles the collapse. A second collapsing
  navbar would compete with the icon-rail.
- **Object-fit + advanced image utilities** — no image-grid
  surfaces.

## Recommendation Summary

Three concrete patterns to adopt — Sprint C
([`ui-overhaul-proposal.md`](ui-overhaul-proposal.md)) maps
these to Overhaul S/M/L sizes:

1. **Color-modes toggle** (½ day) — biggest visible win for
   smallest effort.
2. **Accordion for detail-card stacks** (1-2 days) — reduces
   visual noise on dense detail pages.
3. **Pagination component** (½-1 day) — closes a known UX gap on
   audit-search + query-history.

Two patterns deliberately marked out of scope:

- scrollspy (would force tab-to-section reflow)
- Bootstrap dashboard col-grid (Phase 17 deliberately chose CSS
  Grid icon-rail instead)

Sprint B (replay sweep with screenshots) will produce the visual
debt list that complements this gap analysis.
