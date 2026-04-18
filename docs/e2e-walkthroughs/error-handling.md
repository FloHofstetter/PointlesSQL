# Error-handling walkthrough

Exercises the Sprint 44 RFC 9457 error envelope and the HTMX toast
bridge. Every non-OK response in PointlesSQL flows through one of
three renderers — `application/problem+json` JSON, an `HX-Trigger`
toast for non-boosted HTMX fragment calls, or a branded HTML error
page for regular browser navigations — all driven by the same
problem body (`type`/`title`/`status`/`detail`/`code`/`request_id`).
This playbook proves all three code paths and the AuthorizationError
extension members.

## Preconditions

- [`csrf.md`](csrf.md) and [`rate-limit.md`](rate-limit.md) ran
  first. `admin@pql.test` and a separate non-admin user
  `alice@pql.test` exist and can sign in.
- Server running on `http://127.0.0.1:8000` with `curl` + `jq` on
  `$PATH`.
- For step 6 you'll briefly stop soyuz-catalog. Expect to restart
  it at the end of the walkthrough.

## Walkthrough

1. **`/api/*` returns `application/problem+json`**.
   - Action: sign in as `alice@pql.test` (non-admin) in a browser
     and note the cookie jar. From the same profile or the
     terminal with the same cookies, run:
     ```bash
     curl -i -H "Cookie: pql_session=<alice-token>" \
          http://127.0.0.1:8000/api/connections
     ```
   - Assert: status `403`; response header
     `Content-Type: application/problem+json`; body
     ```json
     {
       "type": "about:blank",
       "title": "Access denied",
       "status": 403,
       "detail": "alice@pql.test lacks ADMIN on app 'connections'",
       "code": "authorization_error",
       "request_id": "<hex>",
       "required_privilege": "ADMIN",
       "securable_type": "app",
       "full_name": "connections"
     }
     ```
     Note the top-level fields — no nested `{"error": {...}}`
     wrapper. The three extension members (`required_privilege`,
     `securable_type`, `full_name`) come from the
     `AuthorizationError` attributes.

2. **Browser navigation → branded HTML page**.
   - Action: still signed in as `alice@pql.test`, navigate to
     `http://127.0.0.1:8000/connections` in the browser address
     bar (a plain top-level navigation, not an in-page HTMX
     click).
   - Assert: the app shell renders with the "Access denied" 403
     card. The card shows the required privilege and securable
     name. DevTools → Network → the request shows
     `Content-Type: text/html; …` and status `403`.

3. **HTMX fragment → toast without page swap**.
   - Action: sign in as `alice@pql.test`, navigate to the home
     page (`/`), open DevTools → Network, and trigger any in-page
     HTMX action that hits `/connections` as a non-boosted
     fragment. The fastest reproducer from the terminal:
     ```bash
     curl -i -H "Cookie: pql_session=<alice-token>" \
          -H "HX-Request: true" \
          http://127.0.0.1:8000/connections
     ```
   - Assert: status `403`; response body is empty; response
     contains `HX-Trigger: {"pqlToast": {"level": "error", "code":
     "authorization_error", "message": "alice@pql.test lacks
     ADMIN on app 'connections'", "request_id": "<hex>"}}`.
     Back in the browser, the in-page action should leave the
     current page untouched and surface a red Bootstrap toast in
     the bottom-right corner with the same message plus a
     `[req <hex>]` suffix.

4. **Boosted navigation still gets HTML**.
   - Action:
     ```bash
     curl -i -H "Cookie: pql_session=<alice-token>" \
          -H "HX-Request: true" -H "HX-Boosted: true" \
          http://127.0.0.1:8000/connections
     ```
   - Assert: status `403`; response header `Content-Type:
     text/html; …`; response body is the full 403 page HTML; no
     `HX-Trigger` header is present. Boosted navigations must get
     the HTML shell so htmx can swap `#main-content`.

5. **`Accept: application/json` overrides the HTML default**.
   - Action:
     ```bash
     curl -i -H "Cookie: pql_session=<alice-token>" \
          -H "Accept: application/json" \
          http://127.0.0.1:8000/connections
     ```
   - Assert: status `403`; response header `Content-Type:
     application/problem+json`; body is the same RFC 9457 shape
     from step 1. Content negotiation treats an explicit
     JSON-preferring client like an API client even on a
     non-`/api/*` route.

6. **502 problem+json when soyuz-catalog is stopped**.
   - Action: stop the soyuz-catalog container/process (`pkill -f
     soyuz-catalog` or `docker compose stop soyuz-catalog`). As
     admin:
     ```bash
     curl -i -H "Cookie: pql_session=<admin-token>" \
          http://127.0.0.1:8000/api/tree
     ```
   - Assert: status `502`; `Content-Type:
     application/problem+json`; body `code` is
     `catalog_unavailable`; `detail` contains "Connection
     refused" (or the equivalent transport error); `title` is
     "Upstream catalog unavailable"; `request_id` is present.
     Repeat the call with `-H "HX-Request: true"` (non-boosted)
     and confirm an empty body plus `HX-Trigger` with level
     `error` and code `catalog_unavailable`.
   - Cleanup: restart soyuz-catalog.

7. **`request_id` threads through the problem body**.
   - Action: any error call from steps 1–6, but with
     `-H "X-Request-ID: err-playbook-<n>"` added.
   - Assert: the response's `X-Request-ID` header echoes
     `err-playbook-<n>` exactly, the problem body's `request_id`
     field is identical, and `docker compose logs pointlessql`
     shows matching `[req=err-playbook-<n>]` lines for the
     domain-error log record and the access log.

## Expected state at the end

- Alice still signed in and can sign out normally.
- soyuz-catalog restarted and reachable.
- One or more `authorization_error` / `catalog_unavailable` log
  lines visible in `docker compose logs pointlessql` for the
  request IDs you used.

## Replay log

- 2026-04-18 — Sprint 44 landing (`<pending>`): playbook authored.
  Physical replay deferred to post-commit.
