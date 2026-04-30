# Authentication and the API-key gate

PointlesSQL accepts two auth shapes for HTTP requests:

1. **Session cookie (default)** — issued by `/auth/login`, signed
   with `POINTLESSQL_AUTH_SECRET_KEY`, mounted by the auth
   middleware. Humans hitting the UI in a browser sit here.
2. **Bearer API key (Sprint 13.7.0.5 + Sprint 13.11.4a)** — opt-in
   gate aimed at external runtimes (the Hermes plugin, Paperclip
   ticket automations, ad-hoc curl ops) that do not hold a browser
   session. Persisted in the `api_keys` DB table; manageable via
   the admin CRUD endpoints OR seeded from the
   `POINTLESSQL_API_KEYS` env var at startup.

Both can be present on the same request — the cookie wins, the
Bearer header is ignored. This keeps a logged-in human's audit
trail clean even if a misconfigured proxy forwards a leftover
`Authorization` header.

## Where keys live

Sprint 13.11.4a moved the credential store into a real DB table
(`api_keys`). The table is the single source of truth; every
verify roundtrip hits it (with a 60-second in-memory cache for
the hot path so the verification is near-zero-cost).

The admin CRUD endpoints (gated by `require_admin`) cover the
full lifecycle:

- `GET /api/admin/api-keys` — list active keys (set
  `?include_revoked=true` to also see revoked rows).
- `POST /api/admin/api-keys` — body `{name, supervisor?}`. The
  response is the **only** time the plaintext secret is returned
  — persist it now or re-create the key.
- `POST /api/admin/api-keys/{name}/revoke` — soft-delete (sets
  `revoked_at`). Cached entries are invalidated immediately so the
  revocation takes effect on the next request.

Each key carries a `supervisor` boolean. When set, the key may
invoke the Sprint-13.11.4 Family-B routes
(`/api/agent-runs/{id}/summary`, `/api/agent-runs/diff`) — these
walk cross-run history and shouldn't be reachable from every
working agent.

## Bootstrap path: `POINTLESSQL_API_KEYS` env var

For clean-machine `docker-compose` deployments without an admin
UI mounted, the legacy env-var format still seeds the DB on
startup. `name:secret` pairs are separated by newline OR comma.
The optional third token `supervisor` opts the row into the
supervisor scope:

```bash
# legacy single key, no supervisor
export POINTLESSQL_API_KEYS="hermes:s3cr3t-ish-32-bytes-or-longer"

# multiple keys with one supervisor
export POINTLESSQL_API_KEYS="hermes:s1, paperclip:s2, sup:godkey:supervisor"
```

The startup hook is **idempotent**: a row that already exists in
the table by name is left untouched. Once a key has been
provisioned, subsequent restarts with the same env var are no-ops
— the DB wins. To rotate via the env var, revoke the old key
through the admin endpoint first (or delete the row directly),
then bootstrap a new pair.

When `POINTLESSQL_API_KEYS` is unset and the table is empty, the
gate is **disabled**: Bearer headers are ignored entirely, the
existing cookie path is the only auth shape, and the single-user
dev flow (e.g. the `agent_drift_monitor` walkthrough) keeps
working unchanged.

## Using the gate from a client

```bash
curl -H "Authorization: Bearer s3cr3t-ish-32-bytes-or-longer" \
     -H "X-Principal: alice@example.com" \
     -H "Content-Type: application/json" \
     -X POST http://127.0.0.1:8000/api/agent-runs \
     -d '{...}'
```

`X-Principal` is the standard Sprint-13.6 hop for human
attribution and is **strongly recommended** when calling on
behalf of a real user — without it audit rows fall back to
`api_key:<name>`.

## Audit attribution

Every authenticated request still leaves an audit-log row. The
schema is unchanged; the values shift:

| Field | Cookie auth | Bearer auth (no `X-Principal`) | Bearer auth (with `X-Principal`) |
| --- | --- | --- | --- |
| `user_id` | the cookie user's row id | `0` | `0` |
| `user_email` | cookie email | `api_key:<name>` | the `X-Principal` value |
| `actor_role` | `admin` / `user` | `system` | `system` |
| `detail.api_key` | absent | `<name>` | `<name>` |

The `api_key` marker in `detail` is preserved across both Bearer
shapes so the source runtime stays traceable even when a human
re-attributes the row.

## Rotation

To rotate a key without downtime via the admin endpoints:

1. Create a new key with a unique name through
   `POST /api/admin/api-keys`.
2. Roll the consumer config to use the new plaintext secret.
3. Once no in-flight request still carries the old token, call
   `POST /api/admin/api-keys/{old-name}/revoke`. Cache
   invalidation is immediate, so the revoked secret stops working
   on the next request.

The gate has no concept of token expiry; rotation is
operator-driven. Future work (Phase 15+ shoreguard provenance
log) will likely layer signed JWTs on top.

## Operational notes

- **Localhost-only by default**: PointlesSQL still binds to
  `127.0.0.1` per `POINTLESSQL_SERVER_HOST`. Even with the gate
  on, exposing the server publicly without a TLS-terminating
  reverse proxy is unsafe — Bearer secrets ride the wire in the
  clear.
- **Public endpoints stay public**: `/auth/login`, `/static/*`,
  `/healthz`, and the alert RSS feeds (`/alerts/feed.atom` /
  `.json`) skip the auth middleware entirely. The alert feeds
  carry their own opaque per-feed token.
- **Cache TTL is 60 s** for verifies that hit the DB; revocation
  invalidates the cache so a rotated key takes effect on the next
  request. Created keys also invalidate so a freshly-issued key
  works immediately.
- **No middleware-level rate limit on Bearer requests yet**:
  rate-limit middleware (Sprint 43) targets the login endpoint.
  When a future need surfaces (e.g. distributed Hermes runtimes
  flooding `/api/sql/execute`) add a per-key bucket.

## The supervisor scope

Sprint 13.11.4a introduced a boolean `supervisor` column on the
`api_keys` table. Endpoints gated by `require_supervisor` accept
either:

- a cookie session whose user is `is_admin=True`, OR
- a Bearer key whose row has `supervisor=True`.

Family-B Sprint-13.11.4 routes — run summary, run diff — sit on
that gate. The same scope is what the
`hermes-plugin-pointlessql` checks before registering the
`pql_run_summary` / `pql_diff_runs` / `pql_runs_by_principal` /
`pql_runs_by_agent` tools (set
`POINTLESSQL_SUPERVISOR_MODE=true` on the plugin process).

## Why not OAuth / OIDC?

OIDC is wired (`POINTLESSQL_OIDC_*`) but speaks the human-SSO
shape: redirect → callback → cookie. Plugging an external
*runtime* into that flow needs either client-credentials grants
or a service-account proxy, both of which are bigger than the
current consumer (one Hermes plugin) warrants. The Bearer gate
is the smallest closure of the multi-tenant auth gap recorded in
`project_phase13_audit_gaps.md`. When a second consumer arrives
the plan is to layer OIDC client-credentials on top, not to
replace this.
