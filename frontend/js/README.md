# `frontend/js/` — module conventions

Last reorganised in Sprint 75 (Phase 12.7 cleanup).  This directory
holds two parallel ecosystems:

1. **Notebook editor** under `notebook/`: native ES modules with an
   in-tree bootstrap-stub pattern that handles heavy lazy-loaded deps
   (Monaco, Pyright, markdown-it, KaTeX).  See `notebook/bootstrap.js`
   header for the BUG-64-02 history.

2. **Everything else** at this level: small Alpine x-data factories +
   a few utility singletons.  All native ES modules; `bootstrap.js`
   imports them and re-attaches each export to `window.<same-name>`
   so existing template `x-data="editable({...})"` lookups keep
   resolving without HTML edits.

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

## Shared helpers

`editor_base.js` exports two cross-cutting helpers extracted from the
inline editors:

- `validateRequired(value, fieldName)` returns a human error string or
  `null`.  Used by `tagsEditor.addTag`, `permissionsEditor.grant`, and
  every `federation.js` create-form's name validation.
- `createDictEditor(field, patchUrl, initial)` is the
  start/cancel/save/addRow/removeRow state machine that
  `propertiesEditor` and `optionsEditor` share (was a private
  `_makeDictEditor` helper inside properties_editor.js pre-Sprint-75).

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
`<meta name="csrf-token">` for every non-GET/HEAD/OPTIONS request
(Sprint 75 Phase 5 fix — pre-Sprint-75 `pqlApi` relied on the
server-side form-field fallback alone).  Callers may still set the
header explicitly; their value wins.  HTMX requests get the header
via the `htmx:configRequest` hook in `base.html`.

The notebook editor + its sub-modules (`notebook/main.js`,
`notebook/editor_shell.js`, `notebook/file_tree.js`) currently set the
header by hand inside their save / mutation paths — those predate
the `pqlApi.fetch` fix and could be migrated in a future sprint.

## BUG-64-02 reactivity boundary (notebook only)

Inside `notebook/`, Monaco editor / model refs, Web Worker handles,
raw WebSocket handles, save-debounce timers, and per-cell view-zone
DOM-node maps MUST live in factory closures (or in
`createClosureRefs(['editor', 'model'])`), never on `this._X` of the
returned Alpine reactive object.  Alpine's deep-reactive proxy walks
those refs and hangs Monaco's `editor.create({model})` indefinitely.
See `notebook/closure_state.js` header and commit `0af7984`.

When you add a new closure-scoped slot to a notebook module
(timer handle, DOM-node map, fetch AbortController, etc.):

1. Add the slot name to the `PATTERN` regex in
   `scripts/check-frontend-no-reactive-monaco.sh`.
2. Add a paragraph to that script's preamble explaining what the
   slot holds and why it can't escape to `this._X`.

This belt-and-suspenders approach has caught BUG-64-02 family
regressions in every sprint that touched the notebook editor.

## Vendor libraries

`vendor/` holds tarball-extracted UMD bundles for Monaco, markdown-it,
KaTeX, jsdiff (download via the `scripts/vendor-*.sh` helpers; the
directory is `.gitignore`d).  These load via plain `<script>` tags or
Monaco's internal AMD loader — they are NOT importable from
`bootstrap.js`.  CodeMirror 6 lives behind an importmap on
`sql_editor.html` and is fetched from esm.sh on demand.
