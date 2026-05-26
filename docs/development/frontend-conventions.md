# Frontend conventions

PointlesSQL ships a thin FastAPI + Jinja2 + Bootstrap 5 + HTMX + Alpine.js
frontend.  The conventions below codify the established structural
decisions so future contributors — human or LLM — can land changes
without rediscovering them every time.

For the stack overview, the CSS cascade tiers, and the bootstrap.js
attachment mechanism, see
[frontend architecture](frontend-architecture.md) first.  This file
focuses on layout disciplines (where files belong, when to split,
when to macro vs partial vs inline).

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
**page-scoped partials**.  Canonical examples are `run_view.html`,
`table.html`, `model.html`, and the notebook editor's `meta_panel.html`
(826 LOC → 38-LOC wrapper + 8 sub-partials in
`pages/_partials/notebook_editor/meta_panel/`).

For pages with multiple top-level tabs that each have their own
Alpine `x-data` scope — `branch_detail.html`, `sql_editor.html`,
`tab_lineage.html` — the partials can also live in a sibling
subfolder directly under `pages/` (e.g. `pages/branch_detail/`)
rather than under `pages/_partials/`.  Either location is fine;
the choice is a readability call — pages with many short partials
benefit from `_partials/` namespacing, pages with a handful of
big tabs read well as a sibling folder.

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
  many pages.  The current catalog (14 macros: `badge`, `button`,
  `copy_button`, `csrf`, `detail_drawer`, `entity_actions`,
  `filter_collapsible`, `help_icon`, `metadata`, `pagination`,
  `permission_link`, `state_container`, `timestamps`, `truncate`)
  is documented in
  [`frontend/templates/_macros/README.md`](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/_macros/README.md).
- **Partials** — chunks of markup `{% include %}`-d into a page,
  inheriting the parent's Alpine `x-data` scope.  This is the
  preferred way to pass state from a parent factory to nested
  markup: never pass through `{% include … with foo=bar %}` —
  put the value on the Alpine scope and let the partial read it
  via Alpine, so Jinja stays pure-presentation.
- **Components** (`components/<name>.html`) — shared **chrome** (sidebars,
  breadcrumbs, empty-state, command palette).  Like partials, but
  loaded from base.html or its descendants — they are the visual
  skeleton.

Subfolder partials (those nested under `pages/_partials/<page>/` or
`pages/<page>/`) **do not use a `_` filename prefix**.  Only the
flat top-level `partials/` folder uses underscores (`_query_row.html`,
`_cdf_change_type_pill.html`) — the prefix flags them as "rendered
as a fragment" against the flat namespace.  Once a partial lives
inside a per-page subfolder, the subfolder *is* the scope marker,
and the prefix would be noise.

## JavaScript

```
frontend/js/
├── bootstrap.js                    # import + window-attach entry
├── api.js, http.js, toast.js, …    # shared utilities (top-level)
├── base_*.js                       # side-effect bridges (htmx, theme, panels, recent)
├── components/                     # shared widgets (lineage_dag/, sidebars/, …)
├── pages/                          # one file per page (flat) or per-page subfolder
├── notebook/                       # large per-feature surface (34 modules)
└── sql_editor/                     # large per-feature surface (7 modules)
```

- All files are native **ES modules**.  Each exports a single factory
  or singleton.
- `bootstrap.js` imports each and re-attaches it to `window.<name>` so
  templates' `x-data="myFactory({...})"` keep resolving without
  per-page `<script>` tags.  See
  [`frontend/js/README.md`](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/README.md) for the
  attach pattern.
- **`pql*` prefix** for utility singletons surfaced via `window`
  (`pqlApi`, `pqlToast`, `pqlRelativeTime`).  No prefix for Alpine
  x-data factories — they appear only in HTML.
- Page factories live under `js/pages/`.  The default is **flat**
  (`js/pages/feed.js`, `js/pages/data_product.js`, `js/pages/model.js`);
  use a **subfolder** only when a page family has multiple modules
  (e.g. `js/pages/federation/{connections,credentials,catalogs}.js`
  for the three admin Federation pages).  Shared widgets that
  compose into multiple pages live in `js/components/`.
- **Side-effect modules** (htmx CSRF bridge, theme toggle, panel
  toggles, recent-storage writer, etc.) are named `base_*.js` and
  imported into `bootstrap.js` via bare `import './base_X.js';`
  (no factory, no window attach — the module runs on eval).

## CSS

```
frontend/css/
├── style.css                       # master @import cascade
├── base.css, primitives.css, layout.css, responsive.css
├── components/<feature>.css        # per-feature styles (17 files)
├── notebook.css                    # lazy-loaded index for notebook editor
└── notebook/                       # 7 sub-files behind notebook.css
```

- One master `style.css` `@import`s every component CSS in cascade
  order.  Cascade matters — later imports override earlier ones at
  equal specificity — so refactors that move rules between files
  must keep the order stable.
- New per-feature CSS goes under `components/<feature>.css` and gets
  appended to the cascade.
- **Lazy-load** a feature CSS via `{% block extra_css %}` when its
  rules are only relevant to one page.  `notebook.css` is the
  canonical example: 22-LOC index that itself `@import`s 7
  sub-files in `notebook/`.  The sub-files inherit the lazy-load —
  the browser only fetches them when the parent is requested,
  saving ~800 LOC on every non-notebook page.
- **Contiguous-slice splitting**: for files >500 LOC that have
  natural section banners (the pre-W5 `notebook.css` had seven of
  them), split as contiguous line-range slices of the original,
  with `@import`s in original file-order.  This preserves the
  cascade byte-identical without specificity refactoring.  The
  trade-off is occasional concern-impurity (e.g. `cells.css` ends
  up holding `.pql-notebook-cell__history*` rows that conceptually
  belong with the cell-thread rules in `interactions.css`) —
  accept it for cascade safety.

## When in doubt

Default to the smaller, more locally-scoped option:

- New partial?  `pages/_partials/<page>/`, not `partials/`.
- New JS for one page?  `js/pages/<page>.js` flat, not top-level `js/`.
- New CSS for one feature?  `css/components/<feature>.css` +
  `@import`, not inline `<style>` in a template.

## See also

- [Frontend architecture](frontend-architecture.md) — stack overview,
  cascade tiers, bootstrap.js attachment patterns, notebook subsystem map
- [Design tokens](design-tokens.md) — the `--pql-*` token catalog
- [`frontend/js/README.md`](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/README.md) — JS module conventions
- [`frontend/templates/_macros/README.md`](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/_macros/README.md) —
  Jinja macro catalog
