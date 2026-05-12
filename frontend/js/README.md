# `frontend/js/` — module conventions

Small Alpine x-data factories + a few utility singletons, all native
ES modules.  `bootstrap.js` imports them and re-attaches each
export to `window.<same-name>` so existing template
`x-data="editable({...})"` lookups keep resolving without HTML edits.

## How a new factory module lands here

1. Write the file as `export function myFactory(args) { ... }` (no
   IIFE wrapping, no top-level `window.X = ...`).
2. Add an import to `bootstrap.js` and the matching
   `window.myFactory = myFactory;` line.
3. The template's `x-data="myFactory({...})"` works as before.

## Naming conventions

- **`pql*` prefix** for utility singletons + helpers consumed via
  `window` (`pqlApi`, `pqlToast`, `pqlRelativeTime`, `pqlHumanizeCron`,
  `pqlParseServerIso`).  Avoids collision with library globals.
- **No prefix** for Alpine x-data factories that only live in
  templates (`editable`, `tagsEditor`, `permissionsEditor`,
  `propertiesEditor`, `optionsEditor`, `listTable`, `jobRowActions`,
  `sqlEditor`, `createConnectionForm`, `createExternalLocationForm`,
  `createCredentialForm`, `createForeignCatalogForm`, `deleteConfirm`).
  These names appear in HTML, not JS, so the prefix would only add
  visual noise.

## Folder layout

- **`js/` top-level** — shared utilities + infrastructure that any page
  may consume (`api.js`, `toast.js`, `tab_sync.js`, `editor_base.js`,
  `list_table.js`, `relative_time.js`, `humanize_cron.js`, etc.).
- **`js/pages/<page>/`** — page-affiliated factories that only run on
  one page or surface (e.g.
  `js/pages/federation/{connections,credentials,catalogs}.js` for the
  admin Federation pages; `js/pages/dbt_table_context.js` for the
  Table-detail dbt overlay).  Path-affiliation makes the page
  ownership obvious without grepping templates.
- **`js/components/`** — shared widgets that compose into pages but
  are not pages themselves (`command_palette.js`, `lineage_panes.js`).
  Feature-grouped sub-folders are fine — e.g. `lineage_dag/` (init +
  factory + highlights) and `sidebars/` (one `_base.js` + 6 thin
  per-section configs).
- **`js/sql_editor/`, `js/notebook/`** — large per-feature surfaces
  already split into multiple co-located files; treat as sub-folders
  of pages, but kept at top-level for path-typing brevity.

## Shared helpers

`editor_base.js` exports two cross-cutting helpers extracted from the
inline editors:

- `validateRequired(value, fieldName)` returns a human error string or
  `null`.  Used by `tagsEditor.addTag`, `permissionsEditor.grant`, and
  every `federation.js` create-form's name validation.
- `createDictEditor(field, patchUrl, initial)` is the
  start/cancel/save/addRow/removeRow state machine that
  `propertiesEditor` and `optionsEditor` share (was previously a
  private `_makeDictEditor` helper inside properties_editor.js).

What is intentionally NOT extracted: the
`if (res.ok) { ... } else { this.error = 'X: ' + res.error; }` block.
Every consumer's `onSuccess` body is unique (assign different fields,
redirect, reset different inputs); a generic wrapper would cost more
in reader-overhead than the ~3 lines per site it would save.  Per the
`simplify` skill discipline: a 5th argument to a generic helper is the
signal to abandon the abstraction for that consumer.

## Script load order (base.html)

```
htmx (CDN)
chart.js UMD (CDN)
bootstrap.js  <script type="module">    ← all factories migrated here
alpine.js     <script defer> (CDN)
inline CSRF/HTMX/toast bridge
bootstrap.bundle.min.js (CDN)
```

`type="module"` is defer-by-default and runs in document order, so
anything `bootstrap.js` registers on `window` is live before Alpine's
x-data walk begins.  This ordering is asserted by
`scripts/check-frontend-bootstrap-order.sh`, wired into CI.

## CSRF

`pqlApi.fetch` injects the `X-CSRF-Token` header from
`<meta name="csrf-token">` for every non-GET/HEAD/OPTIONS request.
Callers may still set the header explicitly; their value wins.
HTMX requests get the header via the `htmx:configRequest` hook in
`base.html`.
