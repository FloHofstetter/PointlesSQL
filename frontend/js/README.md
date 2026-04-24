# `frontend/js/` — module conventions

Last reorganised in Phase 12.12 (agent-first pivot).  The browser
notebook editor + its Monaco/Pyright stack were removed; what remains
is small Alpine x-data factories + a few utility singletons, all
native ES modules.  `bootstrap.js` imports them and re-attaches each
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
