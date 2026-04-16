# Inline-editors walkthrough

Exercises every interactive editing Alpine component on the
catalog / schema / table detail pages: `editable`,
`properties_editor`, `tags_editor`, `permissions_card`
(Assigned + Effective tabs, grant + revoke), and the read-only
`lineage_card`.

## Preconditions

- [`auth.md`](auth.md) and [`catalog-browsing.md`](catalog-browsing.md)
  ran first. `admin@pql.test` is logged in; `user@pql.test`
  exists as a non-admin principal.
- Seed script ran (demo catalog + schemas + tables present).

## Privilege cheat sheet

soyuz-catalog enforces a per-type allow-set for privileges
(``DIVERGENCES.md`` in that repo). The playbook exercises the
valid privilege at each level — using a mismatched privilege
surfaces ``BUG-22-01`` below:

| Securable level      | Privilege tested by playbook |
| -------------------- | ---------------------------- |
| catalog (``demo``)   | `USE CATALOG`                |
| schema (``demo.sales``) | `USE SCHEMA`              |
| table (``demo.sales.orders``) | `SELECT`            |

## Walkthrough

### Part A — catalog level (`/catalogs/demo`)

1. **`editable` component (comment field)** — click, edit, save,
   reload, confirm persistence.
   - Action: navigate to `/catalogs/demo`.
   - Action: click the comment value span (class
     `pql-editable-view`).
   - Assert: the inline text input (`input[x-model="draft"]`)
     and the Save / Cancel buttons appear.
   - Action: via `browser_evaluate`, set
     `Alpine.$data(card).draft = 'edited by e2e walkthrough'`
     and call `Alpine.$data(card).save()`.
   - Assert: the view reverts to the span, showing the new
     comment.
   - Action: `browser_navigate` to the same URL.
   - Assert: comment still reads `edited by e2e walkthrough`.

2. **`properties_editor`** — add, save.
   - Action: drive Alpine directly:
     ```js
     const d = Alpine.$data(document.querySelector('[x-data*="propertiesEditor"]'));
     d.start(); d.addRow();
     d.rows[0].key = 'team'; d.rows[0].value = 'walkthrough';
     await d.save();
     ```
   - Assert: `d.editing === false`, `d.error === null`, `d.rows`
     contains the saved pair.

3. **`tags_editor`** — add, remove.
   - Action: `const d = Alpine.$data(document.querySelector('[x-data*="tagsEditor"]'));`
   - Action: `d.newKey = 'smoke'; await d.addTag();`
   - Assert: `d.tags` contains an entry with `key === 'smoke'`.
   - Action: `await d.removeTag('smoke');`
   - Assert: `d.tags === []`.

4. **`permissions_card` — Effective tab lazy-load**.
   - Action: `const d = Alpine.$data(document.querySelector('[x-data*="permissionsEditor"]'));`
   - Action: `d.tab = 'effective'; await d.loadEffective();`
   - Assert: `d.effective` is an array (may be empty for a fresh
     install).

5. **`permissions_card` — grant + revoke**.
   - Action: `d.grantPrincipal = 'user@pql.test';`
     `d.grantPrivilege = 'USE CATALOG'; await d.grant();`
   - Assert: `d.assignments` contains an entry with
     `principal === 'user@pql.test'` and `privileges` including
     `USE CATALOG`. `d.error === null`.
   - Action: `await d.revoke('user@pql.test', 'USE CATALOG');`
   - Assert: `d.assignments === []`.

### Part B — schema level (`/catalogs/demo/schemas/sales`)

6. Repeat steps 1–5 against the schema detail page. PATCH
   targets are `/api/catalogs/demo/schemas/sales`,
   `/api/tags/schema/demo.sales`,
   `/api/permissions/schema/demo.sales`,
   `/api/effective-permissions/schema/demo.sales`. For
   step 5 use `USE SCHEMA` instead of `USE CATALOG`.

### Part C — table level (`/catalogs/demo/schemas/sales/tables/orders`)

7. Repeat steps 1–3 on the table page.

8. **`permissions_card`** on the table — grant + revoke
   cycle as Part A step 5 but using `SELECT` via
   `/api/permissions/table/demo.sales.orders`.

9. **`lineage_card`** — read-only render.
   - Action: locate the card via
     `document.querySelector('.card-header')` containing
     "Lineage".
   - Assert: the card renders without error. For a freshly
     seeded table soyuz reports the node as its own upstream
     *and* downstream (a soyuz quirk, not a PointlesSQL bug);
     the text "1 upstream · 1 downstream" shows with the table's
     own three-part name as the target. No JS console errors.

## Playwright MCP script

```text
browser_navigate('http://127.0.0.1:8000/catalogs/demo')

# editable comment
browser_click(element='comment editable view span (pql-editable-view)')
browser_evaluate(async () => {
    const c = document.querySelector('.pql-editable-input, input[x-model="draft"]').closest('[x-data]');
    const d = Alpine.$data(c);
    d.draft = 'edited by e2e walkthrough';
    await d.save();
})
browser_navigate('http://127.0.0.1:8000/catalogs/demo')   // reload

# properties
browser_evaluate(async () => {
    const d = Alpine.$data(document.querySelector('[x-data*="propertiesEditor"]'));
    d.start(); d.addRow();
    d.rows[0].key = 'team'; d.rows[0].value = 'walkthrough';
    await d.save();
    return d.error;
})

# tags
browser_evaluate(async () => {
    const d = Alpine.$data(document.querySelector('[x-data*="tagsEditor"]'));
    d.newKey = 'smoke'; await d.addTag();
    await d.removeTag('smoke');
    return d.tags;
})

# permissions (USE CATALOG at catalog level)
browser_evaluate(async () => {
    const d = Alpine.$data(document.querySelector('[x-data*="permissionsEditor"]'));
    d.tab = 'effective'; await d.loadEffective();
    d.tab = 'assigned';
    d.grantPrincipal = 'user@pql.test';
    d.grantPrivilege = 'USE CATALOG';
    await d.grant();
    await d.revoke('user@pql.test', 'USE CATALOG');
    return { assignments: d.assignments, error: d.error };
})

# Part B — same at /catalogs/demo/schemas/sales, grant privilege = 'USE SCHEMA'
# Part C — same at /catalogs/demo/schemas/sales/tables/orders, grant privilege = 'SELECT'
```

## Found bugs

- **BUG-22-01** — fixed in the same sprint commit that added
  this playbook. `_wrap_catalog_errors` in
  `pointlessql/services/unitycatalog.py` now branches on
  `UnexpectedStatus.status_code`: `404` becomes
  `CatalogNotFoundError` (404), other `4xx` become
  `ValidationError` (422), and only `5xx` / transport errors
  stay `CatalogUnavailableError` (502). Sending `SELECT` at
  catalog level now returns a `422 validation_error` with the
  soyuz message passed through, instead of a misleading
  `502 catalog_unavailable`.
  - The privilege cheat sheet above is still the right thing
    to follow — the fix just stops the server from lying about
    the failure mode.
