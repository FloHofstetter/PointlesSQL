# Operational walkthrough

Exercises the cross-cutting operational surface: the public
`/healthz` probe, the admin-gated Prometheus `/metrics` endpoint,
the `/403` error page rendered by the central error handler, and
the `X-Request-ID` header injected by middleware on every response.

## Preconditions

- Stack up with the e2e overlay.
- `admin@pql.test` and `user@pql.test` exist (from `auth.md`).
- Currently logged in as `admin@pql.test` (the tests sign in and
 out deliberately).

## Walkthrough

1. **Anonymous `/healthz` is public**.
 - Action: log out, then
 `browser_evaluate('async () => { const r = await fetch("/healthz"); return {status: r.status, body: await r.json()}; }')`
 - Assert: `{status: 200, body: {status: "ok"}}`. No redirect to
 `/auth/login` (public path in `api/main.py:148`).

2. **Admin `/metrics` returns Prometheus text**.
 - Action: log in as `admin@pql.test`, then navigate to
 `http://127.0.0.1:8000/metrics`.
 - Assert: page text contains the `# HELP` / `# TYPE` comments
 for all three metric families (from
 `services/metrics.py:80-99`). Metric samples only appear
 after observations, so a freshly-started stack may show
 only `pointlessql_scheduler_tick_lag_seconds` as a sampled
 value — the HELP/TYPE lines are the authoritative check
 that the registry is wired:
 - `pointlessql_job_runs_total` (counter)
 - `pointlessql_job_run_duration_seconds` (histogram)
 - `pointlessql_scheduler_tick_lag_seconds` (gauge)
 - Action:
 ```js
 await fetch('/metrics').then(r => r.headers.get('content-type'))
 ```
 - Assert: starts with `text/plain`. The exact suffix depends
 on the `prometheus_client` release (`version=1.0.0` on the
 current image).

3. **Non-admin `/metrics` renders `/403`**.
 - Action: sign out, log in as `user@pql.test`.
 - Action: navigate to `/metrics`.
 - Assert: page renders `pages/403.html` with heading "Access
 Denied"; the `required_privilege` is `admin` and the
 `securable_type` is `system` (or `admin` — both acceptable;
 whatever the error handler passes from
 `AuthorizationError.privilege` and `.securable_type`). No
 raw Prometheus text reaches the browser.

4. **JSON API error envelope carries the request id**.
 - Action: as non-admin user, issue a forbidden API call:
 ```js
 await fetch('/api/connections').then(r => r.json())
 ```
 - Assert: response body shape is
 ```json
 {"error": {"code": "authorization_error", "message": "…",
 "request_id": "<uuid>"}}
 ```
 The `request_id` is a UUID-shaped string.

5. **`X-Request-ID` response header on every response**.
 - Action:
 ```js
 const r = await fetch('/healthz');
 r.headers.get('X-Request-ID')
 ```
 - Assert: returns a UUID-shaped string.
 - Harness note: `browser_network_requests()` was empty during
 the run; the `performance.getEntriesByType`
 fallback works for same-origin response headers, but
 `fetch(...).then(r => r.headers.get('X-Request-ID'))` is the
 most reliable path and is what this playbook uses.

6. **Forwarded `X-Request-ID` is preserved round-trip**.
 - Action:
 ```js
 const id = 'custom-id-' + Math.random().toString(36).slice(2);
 const r = await fetch('/healthz', {headers: {'X-Request-ID': id}});
 r.headers.get('X-Request-ID') === id
 ```
 - Assert: `true` (middleware at `api/main.py:181-199` forwards
 a client-supplied value instead of generating a new UUID).

## Playwright MCP script

```text
# Anonymous healthz
browser_evaluate('async () => { const r = await fetch("/healthz"); return {status: r.status, body: await r.json()}; }')

# Admin metrics
browser_navigate('http://127.0.0.1:8000/auth/login') # sign in as admin
browser_fill_form(...)
browser_click(...)
browser_navigate('http://127.0.0.1:8000/metrics')
browser_evaluate('() => document.body.innerText.includes("pointlessql_job_runs_total")')

# Non-admin metrics → 403
# (sign out, sign in as user@pql.test)
browser_navigate('http://127.0.0.1:8000/metrics')
browser_evaluate('() => document.querySelector("h4")?.innerText') # "Access Denied"

# Request-id header
browser_evaluate('async () => (await fetch("/healthz")).headers.get("X-Request-ID")')
browser_evaluate(`async () => {
 const id = 'custom-id-' + Math.random().toString(36).slice(2);
 const r = await fetch('/healthz', {headers: {'X-Request-ID': id}});
 return r.headers.get('X-Request-ID') === id;
}`)
```

## Found bugs

_No bugs surfaced. Live run confirmed:_

- _anonymous `/healthz` → 200 `{status:ok}` with an
 `X-Request-ID` header;_
- _admin `/metrics` → 200 `text/plain; version=1.0.0` with
 `# HELP` / `# TYPE` lines for all three metric families plus
 a sampled `pointlessql_scheduler_tick_lag_seconds` value;_
- _non-admin `/metrics` → 403 `pages/403.html` with "Access
 Denied" and `required_privilege=admin`;_
- _forbidden JSON API calls return the structured envelope
 with `code: "authorization_error"` and a UUID-shaped
 `request_id`;_
- _`X-Request-ID` is generated on every response and
 preserved round-trip when the client supplies it._
