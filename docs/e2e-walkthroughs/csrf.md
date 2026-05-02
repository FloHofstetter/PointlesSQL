# CSRF protection walkthrough

Exercises the double-submit-cookie CSRF protection on the
three HTML form routes (`/auth/login`, `/auth/register`,
`/auth/logout`), plus the `X-CSRF-Token` header path that HTMX
takes for every non-safe request.

## Preconditions

- [`auth.md`](auth.md) ran first. `admin@pql.test` is registered;
 the local-login form at `/auth/login` works.
- Server running on `http://127.0.0.1:8000` with
 `POINTLESSQL_OIDC_*` unset (so the `/auth/sso` button is hidden —
 the walkthrough only needs the local form).

## Walkthrough

1. **First visit issues a `pql_csrf` cookie**.
 - Action: from a fresh browser profile (or after clearing the
 `pql_csrf` cookie for `127.0.0.1`), navigate to
 `http://127.0.0.1:8000/auth/login`.
 - Assert: DevTools → Application → Cookies shows a `pql_csrf`
 cookie for `127.0.0.1`, `HttpOnly=true`, `SameSite=Lax`,
 `Max-Age ≈ 604800` (7 days). The cookie value is a 32-byte
 URL-safe random string.

2. **Form hidden input and `<meta>` tag carry the same token**.
 - Action:
 ```js
 () => {
 const meta = document.querySelector('meta[name="csrf-token"]').content;
 const input = document.querySelector('form[action="/auth/login"] input[name="csrf_token"]').value;
 return { meta, input, equal: meta === input };
 }
 ```
 - Assert: `equal === true` and both values match the cookie
 body visible in DevTools.

3. **Happy-path login rotates the cookie**.
 - Action: fill in `admin@pql.test` + `password123`, click
 "Sign in". Let the page redirect to `/`.
 - Assert: the new `pql_csrf` cookie value in DevTools differs
 from the value captured in step 1. Login succeeded (navbar
 shows the admin user menu).

4. **HTMX requests auto-attach the `X-CSRF-Token` header**.
 - Action: on `/catalogs/demo`, edit the catalog comment via
 the inline editor (same click path as
 `inline-editors.md` Part A step 1). Keep the DevTools
 Network tab open.
 - Assert: the outgoing `PATCH /api/catalogs/demo` shows a
 request header `X-CSRF-Token` whose value equals the
 current `pql_csrf` cookie (the `base.html`
 `htmx:configRequest` hook copies the meta tag into the
 header for every non-safe verb).

5. **Logout rotates the cookie again**.
 - Action: click the avatar dropdown → "Sign out".
 - Assert: redirects to `/auth/login`. The `pql_csrf` cookie
 value after the redirect differs from the one observed in
 step 3.

6. **Tampered cookie → 403 on state-changing POST**.
 - Action: while signed in again, open DevTools → Application
 → Cookies. Edit the `pql_csrf` value to any string that
 differs from the hidden input on the current page. Click
 "Sign out".
 - Assert: the response body is the
 `403 — CSRF token mismatch` stub. Reloading the page
 re-issues a fresh cookie and the next logout works.

7. **Missing CSRF cookie → 403 on fresh-session POST**.
 - Action: delete the `pql_csrf` cookie entirely without
 reloading. Click "Sign out".
 - Assert: 403. The middleware rejects newly-issued cookies
 that the client could not have echoed back, so the first
 POST after a cookie deletion always fails (this is the
 attack-case: a cross-origin form submit without the
 victim's cookie).

8. **`/api/*` stays reachable without a CSRF token**.
 - Action:
 ```bash
 curl -i -X POST http://127.0.0.1:8000/api/jobs \
 -H "Content-Type: application/json" \
 -d '{}'
 ```
 (no cookies, no token)
 - Assert: response is `401` from the auth middleware, NOT
 `403` from the CSRF middleware. Confirms the `/api/*`
 prefix exemption.

## Playwright MCP script

Run the Firefox Playwright MCP server — per
[`CLAUDE.md`](https://github.com/FloHofstetter/PointlesSQL/blob/main/CLAUDE.md), use
`--browser firefox` (or the bundled `chrome-for-testing`, not
the system Chrome channel).

```text
# 1-2. Cookie + meta/input match.
browser_navigate('http://127.0.0.1:8000/auth/login')
browser_evaluate(() => {
 const cookie = document.cookie.split('; ').find(c => c.startsWith('pql_csrf=')) || '';
 const meta = document.querySelector('meta[name="csrf-token"]').content;
 const input = document.querySelector('form[action="/auth/login"] input[name="csrf_token"]').value;
 // pql_csrf is HttpOnly so document.cookie will not include it —
 // only check the meta/input agreement here; the cookie presence
 // assert uses browser_network_requests on the response below.
 return { meta, input, equal: meta === input, httpOnlyOk: !cookie };
})

# 3. Happy-path login rotates the token.
browser_fill_form({
 'form[action="/auth/login"] input[name="email"]': 'admin@pql.test',
 'form[action="/auth/login"] input[name="password"]': 'password123',
})
# hidden csrf_token input auto-fills from the server-rendered value
browser_click('form[action="/auth/login"] button[type=submit]')
browser_wait_for({ url: 'http://127.0.0.1:8000/' })
browser_evaluate(() => document.querySelector('meta[name="csrf-token"]').content)
# → expect a different value than the login-page render captured in step 2

# 4. HTMX auto-header.
browser_navigate('http://127.0.0.1:8000/catalogs/demo')
browser_evaluate(async () => {
 const host = document.querySelector('.pql-editable-input, input[x-model="draft"]').closest('[x-data]');
 const d = Alpine.$data(host);
 d.draft = 'csrf-e2e-' + Date.now();
 await d.save();
})
# Inspect the request log — the PATCH carries X-CSRF-Token equal to
# the meta tag value.
browser_network_requests()

# 5. Logout rotates again.
browser_click('.dropdown-toggle.d-flex')
browser_click('form[action="/auth/logout"] button')
browser_wait_for({ url: 'http://127.0.0.1:8000/auth/login' })
browser_evaluate(() => document.querySelector('meta[name="csrf-token"]').content)
# → expect yet another fresh value

# 6. Tamper: fetch with a bad header directly.
browser_evaluate(async () => {
 const resp = await fetch('/auth/logout', {
 method: 'POST',
 headers: { 'X-CSRF-Token': 'definitely-not-the-real-token' },
 });
 return { status: resp.status, text: (await resp.text()).slice(0, 64) };
})
# → { status: 403, text contains "CSRF" }

# 8. /api/* exemption — 401 not 403.
browser_evaluate(async () => {
 const resp = await fetch('/api/jobs', {
 method: 'POST',
 headers: { 'Content-Type': 'application/json' },
 body: '{}',
 credentials: 'omit',
 });
 return resp.status;
})
# → 401
```

## Found bugs

_No bugs surfaced. replay confirmed (live run on the
`feat(auth): ` commit `811fb5c` against soyuz-catalog
`v0.2.0rc2`, Firefox via Playwright MCP):_

- _GET `/auth/login` issues the `pql_csrf` cookie with
 `HttpOnly; SameSite=Lax; Max-Age=604800; Path=/` as advertised
 (confirmed via `curl -I` on the response headers);_
- _`<meta name="csrf-token">` and the hidden
 `<input name="csrf_token">` both carry the same 43-character
 (32 random bytes, URL-safe base64) value; `document.cookie` does
 NOT expose `pql_csrf` — the HttpOnly attribute holds;_
- _local login with `admin@pql.test` rotates the cookie (observed
 `r6XU…` → `pAyl…`) and redirects to `/` as expected;_
- _an HTMX-driven `PATCH /api/catalogs/analytics` (fired via
 `htmx.ajax` from the DevTools console) carries
 `x-csrf-token: pAyl…` matching the current `pql_csrf` cookie —
 the `base.html` `htmx:configRequest` hook picks the value up
 from the meta tag and attaches it on every non-safe verb
 without per-route edits;_
- _logout rotates again (observed `pAyl…` → `cQmT…`) and lands
 on `/auth/login`;_
- _`fetch('/auth/logout', { method: 'POST', headers: {'X-CSRF-Token': 'wrong'} })`
 returns 403 with the expected
 `<h1>403 — CSRF token mismatch</h1>` stub;_
- _`fetch('/auth/logout', { method: 'POST', credentials: 'omit' })`
 (no cookie at all) also returns 403 — the middleware's
 `issued_new` guard short-circuits the first POST after cookie
 deletion, which is exactly the attack-case for a cross-origin
 form submit;_
- _`fetch('/api/jobs', { method: 'POST', body: '{}', credentials: 'omit' })`
 returns `401` from the auth middleware, **not** `403` from
 the CSRF middleware — confirming the `/api/*` prefix exemption
 that deliberately leaves in place
 (`SameSite=Lax` + JSON content-type enforcement cover that
 surface)._

_Replay notes:_
- _HTMX ships as XHR, not `fetch`, so capturing the outgoing
 `X-CSRF-Token` header from page JS requires Playwright's
 `browser_network_requests({ requestHeaders: true })` rather
 than a `window.fetch` override — the override captured
 nothing. The playbook script above reflects that._
- _The inline-edit PATCH surfaces a pre-existing 422 because
 `htmx.ajax` serialises form-urlencoded while the route expects
 JSON. That is unrelated to CSRF — the token attached
 correctly — so it is not logged as a `BUG-42-NN`._
