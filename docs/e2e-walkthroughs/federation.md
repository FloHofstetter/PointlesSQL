# Federation walkthrough

> **Mode:** `browser` · **Phase:** 1 · **Surface:** /connections + /external-locations + /credentials

Exercises the Lakehouse Federation pages (connections, external
locations, credentials): list + detail + create modal + the
`deleteConfirm` component. All federation routes are
admin-only ( restriction via `_require_admin`), so the
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
 d.credentialName = 'walkthrough_cred'; // required — see BUG-22-02
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

- **BUG-22-02** — fixed in the same sprint commit that added
 this playbook. `_wrap_catalog_errors` in
 `pointlessql/services/unitycatalog.py` now catches the
 `KeyError` / `TypeError` raised by a generated
 `Create*.from_dict()` (missing required field) and re-raises
 `ValidationError`. `POST /api/external-locations` with no
 `credential_name` now returns
 `422 validation_error: "Invalid request body:
 'credential_name'"` instead of a 500 leaking the KeyError.

- **BUG-22-03** — fixed in the same sprint commit.
 `createExternalLocationForm.submit()` in
 `frontend/js/federation.js` now rejects an empty
 `credentialName` with a clear inline error message before
 issuing the request, matching the spec requirement surfaced
 by BUG-22-02.

## BUGs — Phase 69 replay (2026-05-12)

### BUG-69-01: asset_version not bumped on Phase 68 rebuild
- **Surface**: every page after rebuilding the image with Phase 68
 source on top of a pinned `0.1.0rc3` version.
- **Symptom**: Firefox's ES-module cache served the **pre-Phase-68**
 `bootstrap.js` (cache key = `?v=0.1.0rc3`, content unchanged from
 cache perspective). The cached bootstrap.js still referenced the
 old `/static/js/federation_*.js` paths, which now return 404 →
 37 console errors per page + cascading Alpine init regression
 (command palette backdrop intercepted clicks; see BUG-69-02).
- **Expected**: `pyproject.toml` version bump as part of the Phase 68
 commit-range so all asset URLs gain a fresh `?v=` cache buster
 on deploy.
- **Actual**: Phase 68 was committed without bumping the version
 string, even though the "Bekannte Stolperfallen" section of its
 plan explicitly called this out for `notebook.css`.
- **Fix in**: `pyproject.toml` (bump to `0.1.0rc4` next time
 frontend assets change). For ad-hoc dev rebuilds, the Phase-69
 replay used `0.1.0rc5` temporarily, then reverted.

### BUG-69-02: command-palette backdrop intercepts clicks when Alpine init fails
- **Surface**: any page after BUG-69-01 caused a module-load
 failure.
- **Symptom**: `<div class="pql-cmdk-backdrop">` with
 `x-show="open"` stayed visible (or at least pointer-event-active)
 because Alpine never finished initializing the
 `commandPalette()` factory; clicks on legitimate buttons were
 swallowed by the invisible backdrop.
- **Repro**: open `/sql` after a stale-module cache state, try to
 click Run — Playwright reports `pql-cmdk-backdrop subtree
 intercepts pointer events`.
- **Cause**: cascading from BUG-69-01 — when bootstrap.js fails to
 import federation modules, the surrounding Alpine init chain
 throws and the palette's `open` initializer never runs.
- **Fix in**: resolve BUG-69-01 (asset_version bump). No
 separate code change required; the cascade disappears once
 module imports succeed.

### BUG-69-03: federation JS imports broken after Phase 68.4 file-move
- **Surface**: every page (`bootstrap.js` imports the three
 federation modules unconditionally at startup).
- **Symptom**: `/static/js/pages/federation/editor_base.js` → 404
 because the three moved files
 (`connections.js`, `credentials.js`, `catalogs.js`) still had
 `import { validateRequired } from './editor_base.js';`.
 With the move from `/js/` to `/js/pages/federation/`, the
 relative `./editor_base.js` now resolves to
 `/static/js/pages/federation/editor_base.js` (404), not the
 actual file at `/static/js/editor_base.js`.
- **Expected**: relative import rewritten to `../../editor_base.js`
 as part of Phase 68.4's `git mv`.
- **Actual**: imports were missed in the move sweep; only
 `bootstrap.js`'s import path got updated.
- **Fix in**: this Phase-69 commit-range —
 `frontend/js/pages/federation/{connections,credentials,catalogs}.js`
 each now use `from '../../editor_base.js'`. Verified by
 reloading `/connections` → 0 console errors, all 3 federation
 modals open + submit correctly.
