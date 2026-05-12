# Frontend conventions

PointlesSQL ships a thin FastAPI + Jinja2 + Bootstrap 5 + HTMX + Alpine.js
frontend.  The conventions below codify the structural decisions taken
in Phase 68 (2026-05-12) so future contributors — human or LLM — can
land changes without rediscovering them every time.

## Templates

```
frontend/templates/
├── base.html                       # layout skeleton + topbar + critical init scripts
├── _layouts/                       # alternate page layouts (auth + error pages)
├── _macros/                        # shared Jinja macros (cross-page only)
├── components/                     # shared chrome (sidebars, breadcrumbs, empty state)
├── partials/                       # genuinely cross-page partials (rare; 2 today)
└── pages/
    ├── *.html                      # one file per route
    └── _partials/<page>/           # page-scoped fragments
```

### Pages

One template per HTTP-visible route, extending `base.html`.  Keep page
files thin — when one passes ~250 LOC, split per-tab content into
**page-scoped partials**.  Phase 38 set the precedent (`run_view.html`
1467→229 LOC) and Phase 68 propagated it to `table.html`, `model.html`,
and `_run_tab_operations.html`.

### Partials

Two locations, two intents:

- **`pages/_partials/<page>/...`** — page-scoped fragments.  Nested
  per page so a `grep`/`ls` on one folder lists all sub-views of a
  page.  This is the **default** location for any new partial.
- **`partials/`** — only for partials genuinely included by **two or
  more pages**.  Today this folder holds exactly two files
  (`_cdf_change_type_pill.html`, used by `table.html` + `row_trace.html`;
  `_query_row.html`, used by `queries.html` + its HTMX append fragment).

If you are about to create a new file under top-level `partials/`,
double-check that it is consumed by ≥2 pages.  Otherwise it belongs
in `pages/_partials/<page>/`.

### Macros vs partials vs components

- **Macros** (`_macros/<topic>.html`) — small Jinja2 macros imported via
  `{% from "_macros/foo.html" import bar %}`.  Truly reusable across
  many pages (e.g. `truncate_cell`, `detail_drawer`, `info` help-icon).
- **Partials** — chunks of markup `{% include %}`-d into a page,
  inheriting the parent's Alpine `x-data` scope.
- **Components** (`components/<name>.html`) — shared **chrome** (sidebars,
  breadcrumbs, empty-state, command palette).  Like partials, but
  loaded from base.html or its descendants — they are the visual
  skeleton.

## JavaScript

```
frontend/js/
├── bootstrap.js                    # import + window-attach entry
├── api.js, toast.js, list_table.js # shared utilities (top-level)
├── components/                     # shared widgets (lineage_dag/, sidebars/, …)
├── pages/<page>/<name>.js          # page-affiliated factories
├── notebook/                       # large per-feature surface
└── sql_editor/                     # large per-feature surface
```

- All files are native **ES modules**.  Each exports a single factory
  or singleton.
- `bootstrap.js` imports each and re-attaches it to `window.<name>` so
  templates' `x-data="myFactory({...})"` keep resolving without
  per-page `<script>` tags.
- **`pql*` prefix** for utility singletons surfaced via `window`
  (`pqlApi`, `pqlToast`, `pqlRelativeTime`).  No prefix for Alpine
  x-data factories — they appear only in HTML.
- Page-only factories live under `js/pages/<page>/` so the path encodes
  the affiliation (e.g.
  `js/pages/federation/{connections,credentials,catalogs}.js`).
  Shared widgets live in `js/components/`.

## CSS

```
frontend/css/
├── style.css                       # master @import cascade
├── base.css, primitives.css, layout.css, responsive.css
├── components/<feature>.css        # per-feature styles
└── notebook.css                    # lazy-loaded by notebook editor
```

- One master `style.css` `@import`s every component CSS in cascade
  order; CI checks the order.
- New per-feature CSS goes under `components/<feature>.css` and gets
  appended to the cascade.
- **Lazy-load** a feature CSS via `{% block extra_css %}` when its
  rules are only relevant to one page — `notebook.css` (~300 LOC)
  is the canonical example.  Saves the LOC on every other page-load.

## When in doubt

Default to the smaller, more locally-scoped option:

- New partial?  `pages/_partials/<page>/`, not `partials/`.
- New JS for one page?  `js/pages/<page>/`, not top-level `js/`.
- New CSS for one feature?  `css/components/<feature>.css` +
  `@import`, not inline `<style>` in a template.
