# `frontend/js/` — module conventions

Small Alpine x-data factories + a few utility singletons, all native
ES modules.  `bootstrap.js` imports them and re-attaches each
export to `window.<same-name>` so existing template
`x-data="editable({...})"` lookups keep resolving without HTML edits.

For the bigger picture (stack, request lifecycle, CSS cascade,
notebook subsystem map) see
[`docs/development/frontend-architecture.md`](../../docs/development/frontend-architecture.md).
For layout discipline (where files belong, when to split) see
[`docs/development/frontend-conventions.md`](../../docs/development/frontend-conventions.md).

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
  may consume (`api.js`, `http.js`, `toast.js`, `tab_sync.js`,
  `editor_base.js`, `list_table.js`, `relative_time.js`,
  `humanize_cron.js`, etc.).
- **`js/base_*.js`** — side-effect modules imported into `bootstrap.js`
  with bare `import './base_X.js';` (no factory, no window attach).
  These wire global behaviours that just need to run once on page
  load: `base_htmx_bridge.js` (htmx:configRequest hook + CSRF +
  view-transitions config), `base_theme_toggle.js` (theme switcher
  + persistence), `base_panel_toggles.js` (icon-rail / context-panel
  open/close), `base_recent_storage.js` (localStorage writer for
  recent catalog/table visits), `base_ui_helpers.js` (tooltips,
  confirm modals, row-nav).
- **`js/pages/`** — page-affiliated factories.  Default is **flat**
  (`js/pages/feed.js`, `js/pages/data_product.js`, `js/pages/model.js`,
  `js/pages/admin_api_keys.js`); a **subfolder** is only used when
  a page family has multiple modules (e.g.
  `js/pages/federation/{connections,credentials,catalogs}.js` for the
  three admin Federation pages).
- **`js/components/`** — shared widgets that compose into pages but
  are not pages themselves (`command_palette.js`, `lineage_panes.js`,
  `notification_bell.js`, `workspace_context_menu.js`).  Feature-grouped
  sub-folders are fine — e.g. `lineage_dag/` (init + factory +
  highlights + panel + index) and `sidebars/` (one `_base.js` + 6 thin
  per-section configs).
- **`js/sql_editor/`, `js/notebook/`** — large per-feature surfaces
  already split into multiple co-located files; treat as sub-folders
  of pages, but kept at top-level for path-typing brevity.
- **`js/run_view/`, `js/table/`, `js/partials/`** — smaller per-feature
  or cross-page fragment surfaces.

### Notebook subsystem (`js/notebook/`)

The largest single surface — 34 modules grouped by concern:

| Group         | Modules                                                                 |
| ------------- | ----------------------------------------------------------------------- |
| Coediting     | `coedit.js` (facade), `coedit_core.js`, `coedit_awareness.js`, `coedit_cell_binding.js`, `coedit_client.js` |
| Execution     | `kernel_execution.js`, `variable_inspector.js`, `kernel_ws.js`          |
| Revisions     | `revisions.js`, `revision_diff.js`                                      |
| Per-cell UI   | `cell_thread.js`, `cell_tag_picker.js`, `cell_lineage.js`, `cell_facts.js`, `cell_dnd.js`, `cell_editor.js`, `cell_operations.js`, `cell_authorship.js`, `review_decision.js` |
| Drawer panels | `permissions_panel.js`, `widgets_panel.js`, `share_dialog.js`, `branch_binding.js`, `replays.js`, `sequence_proposals.js`, `notebook_tags.js` |
| Output + chat | `output_renderer.js`, `markdown_output.js`, `chat.js`, `chat_integration.js`, `discussion.js` |
| Orchestration | `jobs_orchestration.js`, `persistence.js`                               |
| Coordinator   | `notebook_editor.js` (top-level Alpine factory)                         |

The coordinator owns the Alpine state shape and instantiates the
mixin installers (coedit, kernel-execution, revisions, etc.) on a
shared `state` object — the splits preserve the single-factory
public API while keeping each concern axis editable in isolation.

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
<importmap>                            ← external ESM deps (CodeMirror, Yjs, …)
htmx (CDN)
chart.js UMD (CDN)
bootstrap.js  <script type="module">   ← factories + side-effect modules
alpine.js     <script defer> (CDN)
bootstrap.bundle.min.js (CDN)
```

`type="module"` is defer-by-default and runs in document order, so
anything `bootstrap.js` registers on `window` is live before Alpine's
x-data walk begins.  This ordering is asserted by
`scripts/check-frontend-bootstrap-order.sh`, wired into CI.

The inline CSRF / HTMX / toast bridge that used to live in
`base.html` is now a side-effect module
(`base_htmx_bridge.js`); `base.html` keeps only the FOUC-critical
theme-init block and the `<importmap>` inline, because both must
land before any other script evaluates.

## CSRF

Two helpers coexist; pick whichever matches the route's existing
CSRF contract.  Both encode JSON request bodies and route non-OK
responses identically — they differ only in the header source.

- **Meta-tag CSRF** (preferred for new code) — `pqlApi.fetch`
  injects `X-CSRF-Token` from `<meta name="csrf-token">` on every
  non-GET/HEAD/OPTIONS request.  Callers may still set the header
  explicitly; their value wins.  HTMX requests pick up the same
  token via the `htmx:configRequest` hook in
  `base_htmx_bridge.js`.
- **Cookie CSRF** — `http.js` exports `jsonFetch(url, options)`,
  which reads the `csrftoken` cookie and injects `X-CSRFToken`.
  The notebook subsystem (`cell_thread.js`) consumes this helper.
