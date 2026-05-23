# API key ACLs + usage (Phase 120)

Phase 120 adds three operational levers on top of the Phase-118 token
format and Phase-119 lifecycle: **per-key catalog allowlists**,
**per-key IP allowlists**, and a **30-day usage dashboard**.

Every existing key keeps unchanged behaviour — zero rows in the new
grants tables = unrestricted access, same as pre-120.  Admins opt in
per key when they want to bound blast radius.

## Catalog allowlist

A key with zero rows in `api_key_catalog_grants` can issue SELECT
queries against **any** catalog/schema the underlying UC SELECT
grants permit (the lakehouse layer enforces table-level grants
separately).

A key with ≥1 row is restricted: **every** table reference in the
statement must match at least one grant.  Two grant shapes:

| Grant | Matches |
|-------|---------|
| `catalog_name="main", schema_name=NULL` | Any table under `main.*.*` |
| `catalog_name="main", schema_name="sales"` | Only `main.sales.*` |

The check runs after Phase-117's `qualify_sql` pre-pass, so 1- and
2-part table refs are first expanded using the request's
`catalog` / `schema` body fields before being checked.

**Where it runs:** in the public SQL Statement Execution API
([pointlessql/api/external_sql_routes.py](../../pointlessql/api/external_sql_routes.py))
after parse + qualify, before dispatch.  Internal editor routes
(cookie auth) bypass — this is an API-key-only surface.

**On deny:** returns the DBX-shape FAILED envelope at HTTP 200 with
`error_code="PERMISSION_DENIED"` so it fits the same convention as
Phase 117's per-table UC denials.  Audit row
`api_key.access_denied.catalog` with `{catalog, schema, key_name}`.

### Admin walkthrough

```bash
# Restrict a key to main.sales only
curl -X POST -H "Cookie: $ADMIN_COOKIE" \
     -H "Content-Type: application/json" \
     -d '{"catalog_name":"main","schema_name":"sales"}' \
     http://127.0.0.1:8000/api/admin/api-keys/dbt-prod/grants/catalog

# Or grant the whole catalog (any schema):
curl -X POST ... \
     -d '{"catalog_name":"main"}' \
     http://127.0.0.1:8000/api/admin/api-keys/dbt-prod/grants/catalog

# List
curl -H "Cookie: $ADMIN_COOKIE" \
     http://127.0.0.1:8000/api/admin/api-keys/dbt-prod/grants

# Delete by grant id (from the list response)
curl -X DELETE -H "Cookie: $ADMIN_COOKIE" \
     http://127.0.0.1:8000/api/admin/api-keys/dbt-prod/grants/catalog/42
```

## IP allowlist

A key with zero rows in `api_key_ip_grants` accepts requests from
any source IP.  A key with ≥1 row must source from at least one
allowlisted CIDR.

**Where it runs:** in `auth_middleware` immediately after the Bearer
match.  Failure short-circuits before any state is attached to the
request, so a denied request is indistinguishable from an
unauthenticated one.

**Source IP resolution:** reuses the existing
`pointlessql.api.rate_limit_middleware._client_ip` helper.  Honours
`X-Forwarded-For` when `POINTLESSQL_RATE_LIMIT_TRUST_X_FORWARDED_FOR=true`
(default false); operators behind a reverse proxy MUST set that
flag and configure the proxy to strip client-supplied
`X-Forwarded-For` headers.

**On deny:** returns HTTP 403 with `{"error_code": "IP_NOT_ALLOWED",
"message": "..."}`.  Audit row `api_key.access_denied.ip` with
`{source_ip, key_name}`.

CIDRs are validated + canonicalised at insert time via
`ipaddress.ip_network(value, strict=False)` — so `10.5.7.3/8` stores
as `10.0.0.0/8`.  IPv4 + IPv6 both supported.

### Admin walkthrough

```bash
# Restrict to office VPN range
curl -X POST ... \
     -d '{"cidr":"10.0.0.0/8","label":"office VPN"}' \
     http://127.0.0.1:8000/api/admin/api-keys/dbt-prod/grants/ip

# IPv6 also works
curl -X POST ... \
     -d '{"cidr":"2001:db8::/32"}' \
     http://127.0.0.1:8000/api/admin/api-keys/dbt-prod/grants/ip
```

## Usage dashboard

Every successful Bearer auth is recorded into an in-process
`collections.Counter` keyed on `(api_key_id, bucket_minute,
source_ip)`.  The flusher loop drains the counter every 30 s into
`api_key_usage_buckets`.

**Trade-off:** a worker crash loses up to 30 s of usage events.
Acceptable for a monitoring surface (not a billing source);
documented here so operators don't double-count manually.

**Retention:** the retention loop runs once per day and prunes
buckets older than `usage_retention_days` (default 30).

**Surface:** the per-key detail page at `/admin/api-keys/{name}`
shows a 30-day bar chart + top-10 source IPs + total request count.
Pure server-rendered + Alpine + `<canvas>` 2D context — no Chart.js
dependency.

JSON access for tooling:

```bash
curl -H "Cookie: $ADMIN_COOKIE" \
     http://127.0.0.1:8000/api/admin/api-keys/dbt-prod/usage
# → {
#   "name": "dbt-prod",
#   "days": [{"date":"2026-04-24","count":0}, ...30 entries...],
#   "top_ips": [{"ip":"10.0.0.42","count":1234}, ...]
# }

# Custom window
curl -H "Cookie: $ADMIN_COOKIE" \
     "http://127.0.0.1:8000/api/admin/api-keys/dbt-prod/usage?days=7"
```

## Settings reference

| Env var | Default | Description |
|---------|---------|-------------|
| `POINTLESSQL_API_KEY_ACL_ENFORCE_CATALOG_GRANTS` | `true` | Global kill-switch for catalog ACL |
| `POINTLESSQL_API_KEY_ACL_ENFORCE_IP_GRANTS` | `true` | Global kill-switch for IP ACL |
| `POINTLESSQL_API_KEY_ACL_USAGE_FLUSH_INTERVAL_SECONDS` | `30` | Counter flush cadence |
| `POINTLESSQL_API_KEY_ACL_USAGE_RETENTION_DAYS` | `30` | Bucket retention window |

The two `enforce_*` flags are escape hatches for incident response:
flip to `false` to bypass the ACL while you debug a misconfigured
grant locking out a critical integration.  No redeploy needed —
the flag is read per-request.

## Layered enforcement model

Per-key ACLs are a **coarse pre-filter** that runs before the
existing Unity Catalog SELECT enforcement:

```
Bearer auth → IP allowlist → SQL parse → catalog allowlist → UC SELECT grants → query
```

- **IP allowlist** ("can this source talk to this key at all?")
- **catalog allowlist** ("can this key even ask about this catalog?")
- **UC SELECT grants** ("can this principal read this specific table?")

A key with `analyst` scope + a catalog grant to `main` will still
get blocked on `main.payroll.salaries` if soyuz-catalog hasn't
granted SELECT to `api_key:<name>` on that table.  Both layers fail
independently with distinct audit rows.

## Audit events catalogue

| Action | Source |
|--------|--------|
| `api_key.grant.added` | Admin POST `…/grants/catalog` |
| `api_key.grant.removed` | Admin DELETE `…/grants/catalog/{id}` |
| `api_key.ip_grant.added` | Admin POST `…/grants/ip` |
| `api_key.ip_grant.removed` | Admin DELETE `…/grants/ip/{id}` |
| `api_key.access_denied.catalog` | Request-time catalog mismatch |
| `api_key.access_denied.ip` | Request-time IP mismatch |

The `access_denied.*` rows include the offending value so admins
can quickly debug missing grants — search the audit cockpit by
`target = api_key:<name>` to see the full picture.

## Known limitations

- **In-process usage buffer.**  A crash loses up to 30 s of events.
  Multi-worker deployments need each worker to flush independently;
  the rows don't conflict on the unique key thanks to per-source-IP
  separation, but a single worker pinning all requests will dominate
  the dashboard.  Acceptable for v1; document if it becomes a
  problem.
- **Proxy-trust contract.**  IP allowlisting assumes the reverse
  proxy strips client-supplied `X-Forwarded-For` headers.  If you
  can't guarantee that, set
  `POINTLESSQL_API_KEY_ACL_ENFORCE_IP_GRANTS=false` and rely on
  network-level firewalling.
- **Per-key catalog ACL doesn't replace UC grants.**  It's a coarser
  pre-filter — UC's SELECT grants are still enforced per-table.
- **No webhook on `access_denied.*`.**  Operators poll the audit
  cockpit.  Wiring this through Phase 102 Track-H is a follow-up.
