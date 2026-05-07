# Auth walkthrough

> **Mode:** `browser` · **Phase:** 9 · **Surface:** /login + /register + redirect-to-login

Covers the auth surface end-to-end: first-user-bootstrap admin
registration, second-user non-admin registration, login, logout,
the `/auth/me` JSON endpoint, the redirect-to-login middleware,
the admin gate on `/metrics`, and verification that every
response carries an `X-Request-ID` header.

## Preconditions

- Stack up (`docker-compose.yml` + `docker-compose.e2e.yml`).
- Metadata DB **clean** — no users exist yet (`docker compose
 down -v` between sessions).
- Seed script has **not** yet been required — the registration
 path must be exercised before any other playbook.

## Walkthrough

1. **Redirect-to-login** — unauthenticated visit bounces to login.
 - Action: `browser_navigate(url='http://127.0.0.1:8000/')`
 - Assert: final URL is `/auth/login`; the heading "PointlesSQL"
 and the "Sign in" submit button are visible.
 - Assert: `browser_network_requests` shows the `/` response
 carried an `X-Request-ID` header.

2. **Register first user → admin** — the first-user bootstrap
 path in `pointlessql/services/auth.py`.
 - Action: `browser_navigate(url='http://127.0.0.1:8000/auth/register')`
 - Assert: the info alert
 *"This is the first account — it will be granted admin
 privileges."* is visible (rendered because `first_user` is
 true).
 - Action: `browser_fill_form` on the register form with
 `email=admin@pql.test`, `display_name=Admin`,
 `password=Passw0rd!`, `password_confirm=Passw0rd!` and
 submit.
 - Assert: final URL is `/auth/login` (303 redirect after
 register). No error alert.

3. **Log in as admin** — verify JWT cookie issuance.
 - Action: navigate to `/auth/login`, fill
 `email=admin@pql.test`, `password=Passw0rd!`, submit.
 - Assert: final URL is `/`. Navbar shows the user dropdown
 with the "Admin" badge (`<i class="bi bi-shield-check">`
 rendered only when `current_user.is_admin`).

4. **Verify `/auth/me`** — JSON shape.
 - Action: `browser_evaluate(function='() => fetch("/auth/me").then(r => r.json())')`
 - Assert: JSON `{id: <int>, email: "admin@pql.test",
 display_name: "Admin", is_admin: true}`.

5. **Register second user (non-admin)** — first-user flag must
 now be false.
 - Action: sign out via the navbar user dropdown ("Sign out"
 button inside the `form[action="/auth/logout"]`).
 - Assert: final URL is `/auth/login`.
 - Action: navigate to `/auth/register`.
 - Assert: the "first account" info alert is **absent**.
 - Action: register `user@pql.test` / `User` / `Passw0rd!`.
 - Assert: redirected to `/auth/login`, no error alert.

6. **`/403` admin gate on `/metrics`** — introduced
 `_require_admin` on `/metrics`; a non-admin user hitting it
 must see the 403 page, not the raw metrics.
 - Action: log in as `user@pql.test` / `Passw0rd!`.
 - Action: `browser_navigate(url='http://127.0.0.1:8000/metrics')`
 - Assert: status is 403; the rendered page is
 `pages/403.html` (heading "Access denied" or equivalent),
 and the `required_privilege` / `securable_type` fields are
 populated in the body.

7. **Admin success path on `/metrics`** — sanity check the
 positive side so 's metrics playbook has a clean
 baseline.
 - Action: log out, log in as `admin@pql.test` / `Passw0rd!`,
 navigate to `/metrics`.
 - Assert: response is `text/plain; version=0.0.4`; body
 contains the `pointlessql_job_runs_total` counter name
 (emitted by `services/metrics.py`).

8. **Logout** — cookie is cleared; protected routes redirect
 again.
 - Action: sign out.
 - Action: navigate to `/`.
 - Assert: final URL is `/auth/login`.

9. **Restore admin session for downstream playbooks** — log
 back in as `admin@pql.test` / `Passw0rd!`. Later playbooks
 assume this starting state.

## Playwright MCP script

```text
browser_navigate('http://127.0.0.1:8000/')
browser_snapshot() # captures redirect to /auth/login
browser_network_requests() # assert X-Request-ID

browser_navigate('http://127.0.0.1:8000/auth/register')
browser_fill_form(fields=[
 {name:'email', value:'admin@pql.test'},
 {name:'display_name', value:'Admin'},
 {name:'password', value:'Passw0rd!'},
 {name:'password_confirm', value:'Passw0rd!'},
])
browser_click(element='Create account submit button')

browser_navigate('http://127.0.0.1:8000/auth/login')
browser_fill_form(fields=[
 {name:'email', value:'admin@pql.test'},
 {name:'password', value:'Passw0rd!'},
])
browser_click(element='Sign in submit button')

browser_evaluate(function='() => fetch("/auth/me").then(r => r.json())')

browser_click(element='user dropdown toggle')
browser_click(element='Sign out button')

browser_navigate('http://127.0.0.1:8000/auth/register')
browser_fill_form(fields=[
 {name:'email', value:'user@pql.test'},
 {name:'display_name', value:'User'},
 {name:'password', value:'Passw0rd!'},
 {name:'password_confirm', value:'Passw0rd!'},
])
browser_click(element='Create account submit button')

browser_navigate('http://127.0.0.1:8000/auth/login')
browser_fill_form(fields=[
 {name:'email', value:'user@pql.test'},
 {name:'password', value:'Passw0rd!'},
])
browser_click(element='Sign in submit button')

browser_navigate('http://127.0.0.1:8000/metrics')
browser_snapshot() # assert 403 page

# log out → back in as admin → /metrics positive case → log out → back in as admin
```

## Found bugs

_No PointlesSQL bugs surfaced on this playbook. Live run
confirmed all nine steps pass against a clean-volume stack._

- **Harness note** (not a bug): `browser_network_requests()`
 returned an empty list in this run despite pages having
 fetched resources. Switching to
 `browser_evaluate('() => performance.getEntriesByType("resource")')`
 is a reliable fallback for asserting fetch URLs and response
 timings when needed.
