# Authentication and the API-key gate

PointlesSQL accepts two auth shapes for HTTP requests:

1. **Session cookie (default)** — issued by `/auth/login`, signed
   with `POINTLESSQL_AUTH_SECRET_KEY`, mounted by the auth
   middleware. Humans hitting the UI in a browser sit here.
2. **Bearer API key (Sprint 13.7.0.5)** — opt-in gate aimed at
   external runtimes (the Hermes plugin, Paperclip ticket
   automations, ad-hoc curl ops) that do not hold a browser
   session. Configured through a single env var.

Both can be present on the same request — the cookie wins, the
Bearer header is ignored. This keeps a logged-in human's audit
trail clean even if a misconfigured proxy forwards a leftover
`Authorization` header.

## Configuring the API-key gate

Set `POINTLESSQL_API_KEYS` to one or more `name:secret` pairs.
Pairs are separated by newline OR comma — pick whichever is
easier in your secrets manager:

```bash
# single key
export POINTLESSQL_API_KEYS="hermes:s3cr3t-ish-32-bytes-or-longer"

# multiple keys
export POINTLESSQL_API_KEYS=$'hermes:abc...\npaperclip:xyz...\nbot:mno...'

# or comma-separated
export POINTLESSQL_API_KEYS="hermes:abc...,paperclip:xyz...,bot:mno..."
```

Names are arbitrary opaque labels used for audit attribution
(see below). Pick something that identifies the *runtime*, not
the human ('hermes', 'paperclip-cron', 'ops-curl').

When the variable is **unset or empty**, the gate is **disabled**:
Bearer headers are ignored entirely, the existing cookie path is
the only auth shape, and the single-user dev flow (e.g. the
`agent_drift_monitor` walkthrough) keeps working unchanged.

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

To rotate a key without downtime:

1. Append the new pair to `POINTLESSQL_API_KEYS` keeping the old
   one alive (use a unique name): `hermes:old...,hermes2:new...`.
2. Roll the consumer config to use `hermes2`.
3. Wait long enough that no in-flight request still carries the
   old token, then drop the old pair.

The gate has no concept of token expiry; rotation is
operator-driven. Future work (Phase 15+ shoreguard provenance
log) will likely layer signed JWTs on top, at which point the
flat env-var format becomes a stop-gap.

## Constant-time matching

The gate uses `hmac.compare_digest` on every comparison so a
character-by-character timing attack cannot extract the secret
byte by byte. Names are NOT secret — they appear in audit rows
unredacted.

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
- **No middleware-level rate limit on Bearer requests yet**:
  rate-limit middleware (Sprint 43) targets the login endpoint.
  When a future need surfaces (e.g. distributed Hermes runtimes
  flooding `/api/sql/execute`) add a per-key bucket.

## Why not OAuth / OIDC?

OIDC is wired (`POINTLESSQL_OIDC_*`) but speaks the human-SSO
shape: redirect → callback → cookie. Plugging an external
*runtime* into that flow needs either client-credentials grants
or a service-account proxy, both of which are bigger than the
current consumer (one Hermes plugin) warrants. The Bearer gate
is the smallest closure of the multi-tenant auth gap recorded in
`project_phase13_audit_gaps.md`. When a second consumer arrives
the plan is to layer OIDC client-credentials on top, not to
replace this — the gate's flat env shape is a developer-friendly
fast path that should keep working forever for `127.0.0.1`
deployments.
