# Federation walkthrough

Exercises the Lakehouse Federation pages (connections, external
locations, credentials): list + detail + create modal + the
`deleteConfirm` component. All federation routes are
admin-only (Sprint 7 restriction via `_require_admin`), so the
walkthrough includes a non-admin negative pass.

## Preconditions

- [`auth.md`](auth.md), [`catalog-browsing.md`](catalog-browsing.md),
  and [`inline-editors.md`](inline-editors.md) ran first.
- Seed script ran. The `pg_e2e` Connection is present (seeded
  by `scripts/seed-e2e.py` step 4).
- Currently logged in as `admin@pql.test`.

## Ordering note: credential first, then external location

The UC spec requires a bound `credential_name` on every external
location (`soyuz-catalog-client.CreateExternalLocation` declares
it as required). The walkthrough creates the credential **before**
the external location so the bind resolves. Creating an external
location without a credential surfaces `BUG-22-02` below.

## Walkthrough

### Part A — Connections

1. **List page renders with the seeded connection**.
   - Action: `browser_navigate(url='http://127.0.0.1:8000/connections')`
   - Assert: table row for `pg_e2e` with `connection_type ==
     POSTGRESQL`.

2. **Seeded connection detail page**.
   - Action: click the `pg_e2e` row link.
   - Assert: URL is `/connections/pg_e2e`. The page shows the
     connection options (host `postgres-e2e`, database
     `ecommerce`, user `e2e`, `POSTGRESQL`) and embeds a
     `deleteConfirm` component.

### Part B — Credentials (full create → delete cycle)

3. **Open the create modal** on `/credentials`.
   - Action: navigate to `/credentials`, click the create button.
   - Assert: `#createCredentialModal` is visible.

4. **Fill and submit**.
   - Action: drive Alpine directly (the form uses
     `createCredentialForm` in `federation.js`):
     ```js
     const d = Alpine.$data(document.querySelector('[x-data*="createCredentialForm"]'));
     d.name = 'walkthrough_cred';
     d.awsRoleArn = 'arn:aws:iam::000000000000:role/walkthrough';
     d.comment = 'created by federation.md';
     await d.submit();
     ```
   - Assert: browser navigates to
     `/credentials/walkthrough_cred`. The detail page renders
     the role ARN and comment.

### Part C — External locations (full create → delete cycle)

5. **Create with credential bound** on `/external-locations`.
   - Action: drive Alpine directly:
     ```js
     const d = Alpine.$data(document.querySelector('[x-data*="createExternalLocationForm"]'));
     d.name = 'walkthrough_loc';
     d.url = 's3://walkthrough/bucket/';
     d.credentialName = 'walkthrough_cred';   // required — see BUG-22-02
     d.comment = 'created by federation.md';
     await d.submit();
     ```
   - Assert: browser navigates to
     `/external-locations/walkthrough_loc`. The detail page
     renders the URL, the bound credential name, and the
     comment.

6. **Delete via `deleteConfirm`**.
   - Action: find the delete card
     (`document.querySelector('[x-data*="deleteConfirm"]')`),
     set `confirming = true`, call `doDelete()`.
   - Assert: browser navigates away to
     `/external-locations`. The `walkthrough_loc` row is gone
     from the list.

### Part D — Credential cleanup

7. Navigate to `/credentials/walkthrough_cred`, delete via the
   same `deleteConfirm` flow. Assert the row is gone from
   `/credentials`.

### Part E — Non-admin negative

8. **Log in as non-admin** and hit each federation page —
   expect `/403`.
   - Action: sign out, log in as `user@pql.test` / `Passw0rd!`.
   - Action: `browser_navigate('http://127.0.0.1:8000/connections')`.
   - Assert: status 403 and the 403 page is rendered
     (`Access Denied` heading, `required_privilege` /
     `securable_type` populated by
     `pointlessql/api/error_handlers.py`).
   - Repeat for `/external-locations` and `/credentials`.

9. **Restore admin session** — sign out, log back in as
   `admin@pql.test`. The next playbook picks up from there.

## Playwright MCP script

```text
browser_navigate('http://127.0.0.1:8000/connections')
browser_snapshot()
browser_click(element='row link for connection pg_e2e')

# Credential first
browser_navigate('http://127.0.0.1:8000/credentials')
browser_click(element='New Credential button')
browser_evaluate(async () => {
    const d = Alpine.$data(document.querySelector('[x-data*="createCredentialForm"]'));
    d.name = 'walkthrough_cred';
    d.awsRoleArn = 'arn:aws:iam::000000000000:role/walkthrough';
    d.comment = 'created by federation.md';
    await d.submit();
})

# External location (needs credentialName set)
browser_navigate('http://127.0.0.1:8000/external-locations')
browser_click(element='New External Location button')
browser_evaluate(async () => {
    const d = Alpine.$data(document.querySelector('[x-data*="createExternalLocationForm"]'));
    d.name = 'walkthrough_loc';
    d.url = 's3://walkthrough/bucket/';
    d.credentialName = 'walkthrough_cred';
    d.comment = 'created by federation.md';
    await d.submit();
})

# Delete ext location
browser_evaluate(async () => {
    const d = Alpine.$data(document.querySelector('[x-data*="deleteConfirm"]'));
    await d.doDelete();
})

# Delete credential (repeat on /credentials/walkthrough_cred)

# Non-admin negative — log in as user@pql.test, hit each page
```

## Found bugs

- **BUG-22-02**: `POST /api/external-locations` with a body that
  omits `credential_name` returns `500 Internal Server Error`
  leaking a `KeyError: 'credential_name'` from the generated
  `CreateExternalLocation.from_dict()` (attrs rejects missing
  required fields). The field is required by the UC spec, so
  the correct response is `422 Unprocessable Entity` with a
  structured error body.
  - TODO: in `pointlessql/services/unitycatalog.py` line 701,
    wrap `CreateExternalLocation.from_dict(data)` (and the
    handful of other `Create*.from_dict(data)` calls in the
    facade) in `try/except KeyError as e: raise
    ValidationError(f"missing required field: {e}")`. The broader
    fix is to add a validation-error branch in
    `_wrap_catalog_errors` that catches `KeyError`/`TypeError`
    originating from `*.from_dict()` and re-raises
    `ValidationError`.
  - Work-around in this playbook: always set
    `createExternalLocationForm.credentialName` to a real
    credential name before calling `submit()`, and create the
    credential first (see ordering note at the top).

- **BUG-22-03**: the frontend form in
  `frontend/templates/pages/external_locations.html` /
  `frontend/js/federation.js:createExternalLocationForm()` only
  checks `name` and `url`; it submits an empty `credentialName`
  as `undefined`, which JSON.stringify drops. The form should
  validate that `credentialName` is non-empty (required per UC
  spec) and either pull its value from a `<select>` populated
  by `/api/credentials` or error out inline. Dependent on
  BUG-22-02 — the server-side fix alone surfaces a clearer
  error; the client-side fix prevents the bad request from
  leaving the browser in the first place.
