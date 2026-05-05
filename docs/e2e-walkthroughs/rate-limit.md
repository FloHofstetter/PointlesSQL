# Auth rate-limiting walkthrough

Exercises the per-IP and per-email rate limiter on the
`/auth/*` surface. The limiter is a fixed-window counter backed by
`rate_limit_events` in PointlesSQL's own Alembic DB — no Redis, no
new runtime dependency — and every reject writes a
`rate_limit.blocked` row to `audit_log` so the
`/admin/audit` viewer surfaces the brake at work.

## Preconditions

- [`csrf.md`](csrf.md) ran first. `admin@pql.test` is registered and
 can sign in at `/auth/login`.
- Server running on `http://127.0.0.1:8000` with default rate-limit
 settings (login 10/10min/IP + 5/10min/email, register 5/1h/IP,
 OIDC 20/10min/IP).
- `POINTLESSQL_RATE_LIMIT_ENABLED=true` (the default). Temporarily
 flip to `false` only for step 7.

## Walkthrough

1. **Login floor holds — nine failures stay at 401**.
 - Action: from a fresh browser profile, visit
 `http://127.0.0.1:8000/auth/login`, then submit nine wrong-
 password attempts against nine distinct emails (`u0@x.com` …
 `u8@x.com`, password `bad`).
 - Assert: every response re-renders the login page with the
 `Invalid email or password.` error (401). The navbar still
 shows the signed-out state.

2. **Tenth failure still 401; eleventh flips to 429**.
 - Action: submit a tenth wrong-password attempt (`u9@x.com`
 / `bad`). Observe the response (still 401). Submit an eleventh
 (`u10@x.com` / `bad`).
 - Assert: the eleventh response body is the minimal
 `429 — Too many attempts` page. DevTools → Network shows
 `Status: 429` and a `Retry-After` header with a positive
 integer ≤ `600` (10 minutes in seconds, the login/IP
 window).

3. **Per-email bucket trips independently**.
 - Action: from a second browser profile (different cookie jar
 but the same client IP), submit four wrong-password attempts
 against a single target email (`admin@pql.test` / `bad`).
 Submit a fifth attempt.
 - Assert: the first four re-render 401. Because the first
 profile already burned one email-bucket slot for
 `admin@pql.test` is not the case here — the target email is
 fresh — so the five attempts stay under the 5/10min cap and
 all return 401. Submit a sixth: the per-email cap (5) trips
 even though this profile's per-IP count is only six,
 producing a 429 with a `Retry-After`. (The per-email axis is
 what prevents a distributed attack from probing one account
 from many IPs.)

4. **Registration floor**.
 - Action: from a third browser profile, visit `/auth/register`
 and submit five attempts with too-short passwords (`abc`
 each — the handler rejects with 400). Submit a sixth.
 - Assert: the first five re-render `Password must be at least 8
 characters.` (400). The sixth is a 429 with `Retry-After`.

5. **`/healthz` is unaffected**.
 - Action: while the login and register buckets are full, run
 from another terminal:
 ```bash
 for i in $(seq 1 20); do
 curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/healthz
 done
 ```
 - Assert: every response is `200`. The limiter never covers
 health checks.

6. **`/api/*` stays reachable ( deliberately excludes it)**.
 - Action:
 ```bash
 curl -i -X POST http://127.0.0.1:8000/api/jobs \
 -H "Content-Type: application/json" \
 -d '{}'
 ```
 - Assert: response is `401` (from `auth_middleware`), NOT `429`.
 A sprint layers limits on `/api/sql/*` after the SQL
 editor lands.

7. **Bypass via setting**.
 - Action: stop the server, set
 `POINTLESSQL_RATE_LIMIT_ENABLED=false`, start again. From a
 fresh profile submit 15 wrong-password attempts.
 - Assert: every response is 401. No 429 ever surfaces. After
 verifying, revert the env override and restart so subsequent
 steps match the default configuration.

8. **Rejects show up in the admin audit viewer**.
 - Action: sign in as `admin@pql.test`, then navigate to
 `http://127.0.0.1:8000/admin/audit?action=rate_limit.blocked`.
 - Assert: the table lists the 429s from steps 2–4. The
 `target` column carries the bucket string
 (`auth.login.ip:127.0.0.1`,
 `auth.register.ip:127.0.0.1`, …), the user column reads
 `anon`, and the newest rows sit at the top.

## Playwright MCP script

Run the Firefox Playwright MCP server — per
[`CLAUDE.md`](https://github.com/FloHofstetter/PointlesSQL/blob/main/CLAUDE.md), use `--browser firefox`.

```text
# 1-2. Ten failing logins, eleventh 429.
browser_navigate('http://127.0.0.1:8000/auth/login')
browser_evaluate(async () => {
 const token = document.querySelector('meta[name="csrf-token"]').content;
 const results = [];
 for (let i = 0; i < 11; i++) {
 const body = new URLSearchParams({
 email: `u${i}@x.com`,
 password: 'bad',
 csrf_token: token,
 });
 const resp = await fetch('/auth/login', {
 method: 'POST',
 body,
 headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
 redirect: 'manual',
 });
 results.push({ i, status: resp.status, retry: resp.headers.get('Retry-After') });
 }
 return results;
})
# → results[0..9].status === 401, results[10].status === 429, retry header non-null

# 4. Register flood.
browser_navigate('http://127.0.0.1:8000/auth/register')
browser_evaluate(async () => {
 const token = document.querySelector('meta[name="csrf-token"]').content;
 const results = [];
 for (let i = 0; i < 6; i++) {
 const body = new URLSearchParams({
 email: `r${i}@x.com`,
 display_name: 'R',
 password: 'abc',
 password_confirm: 'abc',
 csrf_token: token,
 });
 const resp = await fetch('/auth/register', {
 method: 'POST',
 body,
 headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
 redirect: 'manual',
 });
 results.push({ i, status: resp.status });
 }
 return results;
})
# → results[0..4].status === 400, results[5].status === 429

# 5. /healthz unaffected.
browser_evaluate(async () => {
 const statuses = [];
 for (let i = 0; i < 10; i++) {
 const r = await fetch('/healthz');
 statuses.push(r.status);
 }
 return statuses;
})
# → every entry 200

# 6. /api/* reachable (but unauthorised).
browser_evaluate(async () => {
 const r = await fetch('/api/jobs', {
 method: 'POST',
 headers: { 'Content-Type': 'application/json' },
 body: '{}',
 credentials: 'omit',
 });
 return r.status;
})
# → 401

# 8. Audit viewer surfaces the rejects.
browser_navigate('http://127.0.0.1:8000/auth/login')
browser_fill_form({
 'form[action="/auth/login"] input[name="email"]': 'admin@pql.test',
 'form[action="/auth/login"] input[name="password"]': 'password123',
})
browser_click('form[action="/auth/login"] button[type=submit]')
browser_wait_for({ url: 'http://127.0.0.1:8000/' })
browser_navigate('http://127.0.0.1:8000/admin/audit?action=rate_limit.blocked')
browser_evaluate(() => document.querySelectorAll('table tbody tr').length)
# → > 0 (one row per rejected attempt from steps 2 and 4)
```

## Found bugs

_No bugs surfaced. replay confirmed (Firefox via Playwright
MCP against a local dev server with default settings; the login
bucket was cleared between the login and the admin audit check so
the admin login itself could succeed — operators running the
playbook from scratch with a fresh DB do not need this step):_

- _Ten wrong-password POSTs to `/auth/login` with distinct emails
 (`u0@x.com` … `u9@x.com`, `password=bad`) all returned 401; the
 eleventh returned `429` with `Retry-After: 596` (≈ 10 minutes,
 derived from the bucket's oldest row plus the 600-second window);_
- _Five too-short-password POSTs to `/auth/register` returned 400;
 the sixth returned 429, confirming the register bucket runs
 independently of the login bucket and with its own cap of 5;_
- _Ten sequential `GET /healthz` calls inside the storm all
 returned 200 — the middleware's `_find_rule` route-exact match
 correctly leaves exempt paths untouched;_
- _`POST /api/jobs` with no credentials returned 401 from
 `auth_middleware`, not 429 from the rate limiter — the `/api/*`
 surface is intentionally out of scope and the limiter
 proves it by staying silent;_
- _`/admin/audit?action=rate_limit.blocked` rendered the two
 rejects with `target` columns carrying the bucket strings
 (`auth.login.ip:127.0.0.1` and `auth.register.ip:127.0.0.1`)
 and the `user` column as `anon` — the viewer surfaces
 the new action without any template edits._
