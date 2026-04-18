# CSRF protection walkthrough

Exercises the Sprint 42 double-submit-cookie CSRF protection on the
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
[`CLAUDE.md`](../../CLAUDE.md), use
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
#   → expect a different value than the login-page render captured in step 2

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
#   → expect yet another fresh value

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

_No bugs surfaced in dry-run authoring. Live Playwright replay is
queued for a follow-up `docs(e2e)` commit after Sprint 42 lands._
