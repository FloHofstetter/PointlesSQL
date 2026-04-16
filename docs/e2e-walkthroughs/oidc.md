# OIDC walkthrough

Exercises the OAuth2 authorization-code + PKCE flow against the
`ghcr.io/navikt/mock-oauth2-server` sidecar added to
`docker-compose.e2e.yml`. Two passes: off (SSO button absent) and
on (full round-trip, auto-user-creation, claim mapping).

## Preconditions

- Stack up with the e2e overlay (Sprint 22 + Sprint 23 additions).
  The `mock-oidc` container is always up but only activates when
  the host env exports `POINTLESSQL_OIDC_*`.
- `admin@pql.test` exists (from `auth.md`).
- Pass 2 requires restarting the `pointlessql` container with the
  OIDC env exported; see step 5.

## Walkthrough

### Pass 1 — OIDC disabled (default)

1. **Navigate to `/auth/login`** without any OIDC env set.
   - Action: `browser_navigate('http://127.0.0.1:8000/auth/login')`
   - Assert: no "Sign in with SSO" button is present on the page
     (`pages/login.html:34` only renders it when
     `settings.oidc_enabled === true` — the computed property that
     requires both discovery_url and client_id).

2. **Direct hit on `/auth/sso`** should degrade gracefully.
   - Action: `browser_navigate('http://127.0.0.1:8000/auth/sso')`
   - Assert: redirects to `/auth/login?error=…` (the route in
     `auth_routes.py` returns a 303 with an error query when OIDC
     is not configured).

### Pass 2 — OIDC enabled (happy path)

3. **Verify the mock issuer is reachable** from the host.
   - Action (shell):
     ```bash
     curl -s http://127.0.0.1:9090/default/.well-known/openid-configuration \
         | jq .issuer
     ```
   - Assert: output is a JSON-encoded string ending in `/default`
     (the mock creates issuers on demand; `/default` is the
     default one).

4. **Verify the mock's discovery URL from inside the pointlessql
   container** (the container sees `mock-oidc:8080`, not
   `127.0.0.1:9090`).
   - Action (shell):
     ```bash
     docker compose -f docker-compose.yml -f docker-compose.e2e.yml \
         exec pointlessql python -c \
         "import httpx; print(httpx.get('http://mock-oidc:8080/default/.well-known/openid-configuration').json()['issuer'])"
     ```
   - Assert: same issuer string as step 3.

5. **Restart the pointlessql container with OIDC configured**.

   Docker networking constraint: the browser runs on the host and
   can't resolve the internal DNS name ``mock-oidc``; meanwhile the
   PointlesSQL container can't resolve the host's loopback
   ``127.0.0.1:9090``. The navikt mock echoes the request host into
   the discovery document ``issuer`` field, so whichever URL you use
   for discovery is the same URL the browser later has to reach.

   The reliable workaround that does **not** require editing
   ``/etc/hosts``: use the mock's **bridge IP**, which both the host
   (via docker0) and the PointlesSQL container (via the internal
   network) can reach. The IP is stable for the lifetime of the
   container but changes on ``docker compose up -d`` recreation, so
   capture it at runtime:

   ```bash
   MOCK_IP=$(docker inspect pql_mock_oidc \
       --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')

   POINTLESSQL_OIDC_DISCOVERY_URL=http://$MOCK_IP:8080/default/.well-known/openid-configuration \
   POINTLESSQL_OIDC_CLIENT_ID=pql-e2e \
   POINTLESSQL_OIDC_CLIENT_SECRET=secret \
   POINTLESSQL_BASE_URL=http://127.0.0.1:8000 \
   docker compose -f docker-compose.yml -f docker-compose.e2e.yml \
       up -d --force-recreate pointlessql
   ```

   Alternative for a more stable setup: add
   ``127.0.0.1 mock-oidc`` to ``/etc/hosts`` (needs sudo) and use
   ``http://mock-oidc:9090/default/.well-known/openid-configuration``
   as the discovery URL — then both sides resolve it to the mock.

   Wait for the pointlessql container to report ``(healthy)``.

6. **SSO button renders on the login page**.
   - Action: `browser_navigate('http://127.0.0.1:8000/auth/login')`
   - Assert: the "Sign in with SSO" button is present (anchor to
     `/auth/sso`, outline-secondary class).

7. **Click SSO → mock login form**.
   - Action: click the "Sign in with SSO" button.
   - Assert: browser navigates to the mock's issuer — the URL
     host is `127.0.0.1:9090` or `localhost:9090` (depending on
     `POINTLESSQL_BASE_URL` resolution), the page contains a form
     with `username` and `claims` fields.
   - Action: fill the mock's form with a test subject:
     `username=oidc-user-1`, and (via the claims textarea)
     `{"sub":"oidc-user-1","email":"oidc@pql.test","name":"OIDC User"}`.
     Submit.
   - Assert: browser redirects back to
     `http://127.0.0.1:8000/auth/callback?code=…&state=…`, which
     in turn redirects to `/`.

8. **New user auto-created + logged in**.
   - Assert: navbar shows "OIDC User" (the display name from the
     `name` claim).
   - Action: `fetch('/auth/me').then(r => r.json())`
   - Assert: `{id: <int>, email: 'oidc@pql.test',
     display_name: 'OIDC User', is_admin: false}`.

9. **OIDC bind fields recorded in the DB**.
   - Action (shell):
     ```bash
     docker compose -f docker-compose.yml -f docker-compose.e2e.yml \
         exec pointlessql sqlite3 /app/data/pointlessql.db \
         "SELECT email, oidc_provider, oidc_subject FROM users WHERE email='oidc@pql.test';"
     ```
   - Assert: `oidc_provider` is the discovery URL from step 5,
     `oidc_subject` equals `oidc-user-1` (the `sub` claim from
     step 7).

10. **Sign out and log back in via SSO** — same user, no
    duplicate row.
    - Action: sign out, click SSO again, re-submit the same
      subject.
    - Assert: `fetch('/auth/me')` returns the same `id` as in
      step 8 (the OIDC flow matched `(provider, subject)` and
      reused the existing user; `find_or_create_oidc_user` in
      `services/oidc.py:300+`).

11. **Restore the non-OIDC stack** (so downstream playbooks'
    preconditions hold):
    ```bash
    POINTLESSQL_OIDC_DISCOVERY_URL= POINTLESSQL_OIDC_CLIENT_ID= \
    POINTLESSQL_OIDC_CLIENT_SECRET= POINTLESSQL_BASE_URL= \
    docker compose -f docker-compose.yml -f docker-compose.e2e.yml \
        up -d --force-recreate pointlessql
    ```

## Playwright MCP script

```text
# Pass 1 — OIDC off
browser_navigate('http://127.0.0.1:8000/auth/login')
browser_evaluate('() => !!document.body.innerText.match(/Sign in with SSO/)')

# (shell — restart pointlessql with OIDC env set)

# Pass 2 — OIDC on
browser_navigate('http://127.0.0.1:8000/auth/login')
browser_click(element='Sign in with SSO button')
# — mock-oauth2-server login form —
browser_fill_form(...)   # username = oidc-user-1, claims JSON
browser_click(element='Submit')
browser_evaluate('async () => await fetch("/auth/me").then(r => r.json())')

# (shell — verify oidc_provider + oidc_subject in sqlite)
```

## Found bugs

- **BUG-23-01** — fixed in the same sprint commit. The
  `oidc_enabled` computed property in
  [`pointlessql/settings.py`](../../pointlessql/settings.py) used
  `is not None` to gate the SSO button. That treated the empty
  strings produced by the compose overlay's
  `${POINTLESSQL_OIDC_DISCOVERY_URL:-}` fallback as *configured*
  — the SSO button rendered and clicking it hit a
  `401 Failed to fetch OIDC discovery document: URL missing
  'http://' or 'https://' protocol`. Fix: truthy check
  (`bool(self.oidc_discovery_url) and bool(self.oidc_client_id)`).
  Live verification: after the fix, Pass 1 correctly leaves the
  SSO button off the login page with all four OIDC env vars
  empty.

Live Pass 2 results (with the bridge-IP workaround in step 5):

- PointlesSQL discovers the mock issuer, redirects browser to the
  authorize endpoint, form submit round-trips back to
  `/auth/callback`, session cookie set, new user auto-created
  with `is_admin=false` (first user bootstrap does not apply
  since `admin@pql.test` already exists).
- DB confirms the bind: `oidc_provider` equals the discovery URL,
  `oidc_subject` equals the `sub` claim (`oidc-user-1`).
- A second sign-in with the same subject reuses the existing row
  (no duplicate) — `find_or_create_oidc_user` in
  [`pointlessql/services/oidc.py`](../../pointlessql/services/oidc.py)
  match-on-provider-subject path works.
