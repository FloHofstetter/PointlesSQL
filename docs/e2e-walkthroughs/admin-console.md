# Admin console walkthrough

> **Mode:** `browser` · **Surface:** /admin/* landing + 7 cards

End-to-end exercise of every page reachable from the admin landing at `/admin`: the 7-card landing index, the
`/admin/external-writes` scanner, the
`/admin/api-keys` CRUD with plaintext-secret modal,
`/admin/review-destinations`, and `/admin/system-info`. Audit
sinks have their own playbook ([audit-sinks.md](audit-sinks.md));
the workspaces page has [multi-workspace-setup.md](multi-workspace-setup.md);
the audit-log viewer has [admin-audit.md](admin-audit.md). This
playbook visits each through the landing card grid so the
nav-from-landing flow is exercised end-to-end.

## Preconditions

- E2E stack up:
  ```bash
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml up -d
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml \
    exec pointlessql python /app/scripts/seed-e2e.py
  ```
- [`auth.md`](auth.md) ran first (admin@pql.test exists and is
  signed in).
- Playwright MCP Firefox: if launch fails with `process did exit:
  exitCode=0` immediately after `<launched>`, check
  `~/.cache/ms-playwright/mcp-firefox-*/lock`. If `ps -p <pid>`
  shows no row, `rm` the symlink and retry. Use the bundled
  Playwright Firefox (`--browser firefox`).

## Walkthrough

### Part A — Landing page (3 steps)

1. **Land on the admin index**.
   - Action: `browser_navigate('http://127.0.0.1:8000/admin')`.
   - Assert: page title `Admin · PointlesSQL`. Heading reads
     "Admin". Right-aligned hint reads "Operator-only surfaces.".

2. **Verify all 20 cards in the grid** (load-bearing — the grid
   has grown card by card; the most recent additions are the
   Asset bundles and Data classification cards).
   - Action:
     ```js
     () => Array.from(document.querySelectorAll('a.pql-admin-card[data-admin-card]'))
       .map(a => ({slug: a.getAttribute('data-admin-card'), href: a.getAttribute('href')}))
     ```
   - Assert: returns an array of length 20 with these slug→href
     pairs in this order:
     - `audit-log` → `/admin/audit`
     - `external-writes` → `/admin/external-writes`
     - `workspaces` → `/admin/workspaces`
     - `domains` → `/admin/domains`
     - `glossary` → `/admin/glossary`
     - `governance` → `/admin/governance`
     - `mesh-entities` → `/admin/mesh-entities`
     - `audit-sinks` → `/admin/audit-sinks`
     - `review-destinations` → `/admin/review-destinations`
     - `api-keys` → `/admin/api-keys`
     - `secrets` → `/admin/secrets`
     - `bundles` → `/admin/bundles`
     - `classification` → `/admin/classification`
     - `sharing` → `/admin/sharing`
     - `cdf-subscriptions` → `/admin/cdf-subscriptions`
     - `policy-modules` → `/admin/policy-modules`
     - `mesh-dashboard` → `/admin/mesh-dashboard`
     - `entity-discovery` → `/admin/entity-discovery`
     - `data-product-apply` → `/admin/data-product-apply`
     - `system-info` → `/admin/system-info`

3. **Confirm active-count badges**.
   - The Workspaces card shows badge `1` from the seeded
     `default` workspace. Other badges are conditional (only
     render when a non-zero count exists), so on a freshly
     seeded stack only the workspaces badge is visible.
   - Note: the External-writes card grows a yellow "warning"
     badge whenever the unacknowledged count is non-zero — this
     is the same number that drives Sprint 18.5's home-banner
     anomaly chip. Trigger one in Part B step 5 below.

### Part B — External writes (3 steps)

1. **Click the External writes card**.
   - Action: click the card with `data-admin-card="external-writes"`.
   - Assert: lands on `/admin/external-writes`. Empty queue
     shows "External writes queue empty / 0 entries shown".

2. **Run a scan**.
   - Action: click "Run scan now".
   - Assert: scan completes synchronously (idempotent thanks to
     the `(table, version) UNIQUE` constraint); banner shows
     "No unattributed writes detected" (clean stack) OR a row
     appears for any synthetic Delta commit that bypassed PQL.

3. **Filter form**.
   - Action: type any partial FQN in the "Table FQN contains"
     input, untick "Unacknowledged only", click Apply.
   - Assert: table filters; URL grows `?fqn_contains=…`. Click
     Reset to clear.

### Part C — API keys (5 steps)

1. **Back to landing → API keys card**.
   - Action: navigate to `/admin`, click `data-admin-card="api-keys"`.
   - Assert: lands on `/admin/api-keys`. Empty state: "No API
     keys configured" + "Show revoked" link.

2. **Create a key with both scopes**.
   - Action: fill Name = `phase37-test-key`, tick `supervisor`,
     tick `auditor`, leave Workspace = `default`, click "Create
     key".
   - Assert (network): `POST /api/admin/api-keys` returns 200
     with body `{name, secret, ...}`. The `secret` field is a
     ~43-char base64-url plaintext token.
   - Assert (modal): the create-secret modal opens (`.modal.d-block`
     selector — Alpine `:class="{ 'd-block': showSecret }"`
     pattern from `feedback_bootstrap_modal_x_show.md`). The
     modal body contains a readonly `<input>` whose `.value`
     property (NOT the HTML `value=` attribute) is the
     plaintext secret.

3. **Load-bearing redaction assertion** (admin-console-class):
   - Action:
     ```js
     () => {
       const fld = document.querySelector('.modal input[readonly]');
       const html = document.documentElement.outerHTML;
       const secret = fld?.value;
       return {
         secretInDOMValue: !!secret && secret.length > 30,
         secretInOuterHTML: html.includes(secret),
       };
     }
     ```
   - Assert: `secretInDOMValue === true` (Alpine bound the
     plaintext to `.value` — admins can copy it),
     `secretInOuterHTML === false` (the plaintext is NOT
     serialised into outerHTML — page-source view doesn't leak
     it). This is a stronger redaction property than
     audit-sinks/review-destinations: secrets exist as JS state
     only, never as HTML.

4. **Copy + dismiss the modal**.
   - Action: click the clipboard button. Label flips from "Copy"
     → "Copied".
   - Note: `navigator.clipboard.writeText` may silently no-op in
     headless Playwright; the `apiKeyCreatedModal.copySecret()`
     handler has a `document.execCommand('copy')` fallback via
     `$refs.secretField.select()`.
   - Action: click "I have copied the secret".
   - Assert: modal closes; page reloads via
     `pqlApi.reloadWithToast`. The new row appears with
     `phase37-test-key`, prefix `<8-chars>…`, both scope badges
     `supervisor` and `auditor`, status `active`.

5. **Revoke the key**.
   - Action: monkeypatch `window.confirm = () => true` (or use
     the API directly: `POST /api/admin/api-keys/phase37-test-key/revoke`).
   - Assert (network): `POST` returns 200 with
     `{name: "phase37-test-key", revoked: true}`. Page reloads;
     the row's status badge flips to `revoked YYYY-MM-DD`. The
     row's Actions cell now shows just `—`.
   - Action: click "Show revoked".
   - Assert: URL grows `?include_revoked=1`; page header shows
     "1 key (incl. revoked)".

### Part D — Review destinations (3 steps)

1. **Back to landing → Review destinations card**.
   - Action: navigate to `/admin`, click `data-admin-card="review-destinations"`.
   - Assert: lands on `/admin/review-destinations`. Empty state
     placeholder visible.

2. **Create a destination with HMAC secret**.
   - Action: fill Name = `phase37-review-dest`, Webhook URL =
     `https://httpbin.org/post`, Min severity = `warn`, HMAC
     secret = `review-secret-must-not-leak`, leave Active
     ticked, click "Create destination".
   - Assert (network): `POST /api/admin/review-destinations`
     returns 200. Row appears with the configured fields; the
     HMAC column shows `set` marker (NOT the cleartext secret).

3. **Load-bearing redaction assertion**:
   - Action:
     ```js
     () => document.documentElement.outerHTML.includes('review-secret-must-not-leak')
     ```
   - Assert: `false`. The cleartext HMAC is never in DOM. Same
     contract as `audit-sinks.md` step 3 — the `_redact_config`
     helper is shared across these admin pages.

### Part E — System info (2 steps)

1. **Back to landing → System info card**.
   - Action: navigate to `/admin`, click `data-admin-card="system-info"`.
   - Assert: lands on `/admin/system-info`. Page renders 4
     read-only sections:
     - **PII mode** — current redaction policy
     - **API keys** — scope counts + last-used timestamps
     - **OIDC group → workspace + scope mapping** — env-var
       configuration table
     - **System keys** — internal `system_keys` table inventory
       (HMAC keys, signing secrets, etc.)

2. **Load-bearing redaction assertion** (highest-stakes — this
   page reads the `system_keys` table where every row is a
   secret value):
   - Action:
     ```js
     () => {
       const html = document.documentElement.outerHTML;
       return {
         hasSha256Hash: /[a-f0-9]{64}/.test(html),
         hasBase64Secret: /[A-Za-z0-9_\-]{40,}/.test(html.replace(/[\/=]/g, '')),
       };
     }
     ```
   - Assert: `hasSha256Hash === false`. No raw 64-char hex
     SHA-256 hashes from the `api_keys.secret_hash` or
     `system_keys.value` columns may appear in the rendered DOM.
     The page should display only counts, prefixes, and labels.

## Playwright MCP script

Replay through the 7-card admin landing + the four sub-pages:

1. `browser_navigate('http://127.0.0.1:8000/admin')`
   — `browser_evaluate('() => document.querySelectorAll(".admin-card").length')` ≥ 7.
2. `browser_click("API keys")`
   — URL becomes `/admin/api-keys`.
3. `browser_click("Generate new key")`
   — `browser_wait_for(".modal.show")`;
   `browser_fill_form([{name:"label", value:"phase41-test"}])`,
   `browser_click("Save")`.
4. `browser_evaluate('() => document.querySelector(".plaintext-secret").innerText.length')`
   — assert ≥ 32 (base64 secret visible exactly once).
5. `browser_evaluate('() => document.body.outerHTML.indexOf("<the-plaintext-secret>")')`
   after a reload — assert `=== -1` (load-bearing: secret is NOT
   in any subsequent page render).
6. `browser_navigate('http://127.0.0.1:8000/admin/external-writes')`
   — assert page renders and has a settings form.
7. `browser_navigate('http://127.0.0.1:8000/admin/review-destinations')`
   — assert page renders the destinations table.
8. `browser_navigate('http://127.0.0.1:8000/admin/system-info')`
   — `browser_evaluate('() => document.querySelector(".info-row[data-key=\"db_revision\"]").innerText')`
   — assert it returns a 12-char alembic hash.

## Found bugs

- **BUG-37-02** ✅ Fixed — admin sidebar in
  [`components/context_panel.html`](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/components/context_panel.html)
  now lists nine entries: Overview, Audit log, Audit cockpit,
  External writes, Workspaces, Audit sinks, Review
  destinations, API keys, System info. Active highlighting
  driven by `request.url.path` so each admin sub-page lights
  the correct entry without backend route changes.

- **BUG-37-03** ✅ Fixed — the lone duplicate Admin link with
  `href="#"` lived in
  [`components/nav_links.html`](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/components/nav_links.html)
  (rendered in the mobile offcanvas drawer). Replaced the
  dropdown shell with a direct link to `/admin`. The
  desktop icon-rail's footer-list Admin link already points
  at `/admin`; both surfaces now agree.

## Cleanup

```bash
# Revoke the test key + delete the test destination
curl -sS -X POST http://127.0.0.1:8000/api/admin/api-keys/phase37-test-key/revoke -b cookies.txt
# Delete-by-id is API-only (UI is soft-revoke only):
# curl -sS -X DELETE http://127.0.0.1:8000/api/admin/review-destinations/<id> -b cookies.txt
```
