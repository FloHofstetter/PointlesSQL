# API key lifecycle (Phase 119)

Phase 119 adds **TTL**, **rotation**, and **soft-quarantine** to the
API-key store.  Every existing key keeps unchanged behaviour (all
lifecycle columns default to ``NULL`` = "no constraint"); admins opt
in per key by setting a TTL or rotating.

## States

A key is in exactly one of:

| State | DB shape | Auth |
|-------|----------|------|
| **active**       | ``revoked_at``/``quarantined_at``/``rotated_at`` all NULL; no TTL or TTL in the future | 200 |
| **expiring**     | ``expires_at`` ≤ now + 14 days (default warning window) | 200 (with audit warning) |
| **expired**      | ``expires_at`` ≤ now; auto-quarantined by sweep | 401 + ``api_key.auth_denied.expired`` |
| **quarantined**  | ``quarantined_at`` set + ``quarantine_reason`` set | 401 + ``api_key.auth_denied.quarantined`` |
| **rotated**      | ``rotated_at`` set; predecessor stays valid until ``grace_until`` | 200 inside grace, 401 + ``api_key.auth_denied.rotated`` after |
| **revoked**      | ``revoked_at`` set | 401 (no audit) |

## Rotation playbook

Rotation is the recommended way to roll a leaked or aging secret.
The successor inherits every scope + workspace + env from the
predecessor; clients pick up the new secret within the **24h grace
window** during which the predecessor still works.

```bash
# 1. Mint successor (admin UI: Rotate button on the row, or CLI:)
curl -X POST -H "Cookie: $ADMIN_COOKIE" \
     http://127.0.0.1:8000/api/admin/api-keys/dbt-prod/rotate
# Response:
# {
#   "predecessor": "dbt-prod",
#   "grace_seconds": 86400,
#   "successor": {
#     "name": "dbt-prod-rotated-1716536400",
#     "secret": "pql_live_v1_xK3a...",
#     ...
#   }
# }

# 2. Hand the successor secret to your dbt CI (vault, k8s secret, …).
#    Both secrets work for the next 24h.

# 3. After 24h the predecessor stops authorising.  At your leisure,
#    revoke the predecessor row for hygiene:
curl -X POST -H "Cookie: $ADMIN_COOKIE" \
     http://127.0.0.1:8000/api/admin/api-keys/dbt-prod/revoke
```

Grace window is configurable per call:

```bash
# Need a longer grace window (e.g. across a weekend)?
curl -X POST -H "Cookie: $ADMIN_COOKIE" \
     -H "Content-Type: application/json" \
     -d '{"grace_seconds": 259200}' \
     http://127.0.0.1:8000/api/admin/api-keys/dbt-prod/rotate
```

## Quarantine vs revoke

**Revoke** is permanent and final — the row is preserved (so audit
attribution keeps resolving), but there is no way back.  Use it for
keys you're certain you'll never need.

**Quarantine** is reversible.  Use it when:
- You see suspicious activity from a key and want to stop it
  immediately but aren't sure if the key is actually compromised
- You're investigating an incident and want to verify the "blast
  radius" of disabling a key before committing to revocation
- A user reports their key isn't working — quarantine first, debug,
  then unquarantine if the issue was elsewhere

```bash
curl -X POST -H "Cookie: $ADMIN_COOKIE" \
     -H "Content-Type: application/json" \
     -d '{"reason": "incident-2026-05-23: unexpected SELECT on payroll.*"}' \
     http://127.0.0.1:8000/api/admin/api-keys/suspect/quarantine

# Investigate.  If false alarm:
curl -X POST -H "Cookie: $ADMIN_COOKIE" \
     http://127.0.0.1:8000/api/admin/api-keys/suspect/unquarantine

# If confirmed compromise, rotate + revoke:
curl -X POST -H "Cookie: $ADMIN_COOKIE" \
     http://127.0.0.1:8000/api/admin/api-keys/suspect/rotate
# (hand new secret to the legitimate user out-of-band)
curl -X POST -H "Cookie: $ADMIN_COOKIE" \
     http://127.0.0.1:8000/api/admin/api-keys/suspect/revoke
```

## TTL guidance

| Use case | Recommended TTL |
|----------|-----------------|
| Long-running production integration (dbt, BI tool, application backend) | No expiry (rotate on schedule via cron) |
| CI bot / staging integration | 90 days |
| Incident-response / debug key | 30 days |
| Tied to a specific person who may leave | 1 year |
| External contractor | Match contract duration, max 1 year |

The TTL is **opt-in**: leaving it as "No expiry" keeps the pre-119
behaviour intact.  The auto-warning runs 14 days before expiry by
default (configurable via ``POINTLESSQL_API_KEY_LIFECYCLE_EXPIRY_WARNING_DAYS``).

## Sweep behaviour

The background sweep runs once per hour by default (configurable via
``POINTLESSQL_API_KEY_LIFECYCLE_SWEEP_INTERVAL_SECONDS``):

1. For every active key with ``expires_at <= now``:
   - Auto-quarantine with reason ``"auto:expired"`` (unless
     ``POINTLESSQL_API_KEY_LIFECYCLE_QUARANTINE_ON_EXPIRY=false``)
   - Emit ``api_key.expired`` audit row
2. For every active key with ``expires_at`` within the warning window
   that hasn't been warned yet:
   - Emit ``api_key.expiry_warning`` audit row with ``days_remaining``
   - Stamp ``expiry_warned_at`` so the sweep doesn't re-warn

Updating a TTL via PATCH (``expires_at`` in the body) clears
``expiry_warned_at`` so a TTL extension naturally re-arms the warning
for the new deadline.

## Audit events

Every lifecycle state change writes an audit row.  Filter by action:

| Action | Source |
|--------|--------|
| ``api_key.created`` | Admin POST or env-var bootstrap (pre-existing) |
| ``api_key.revoked`` | Admin POST (pre-existing) |
| ``api_key.rotated`` | Admin POST ``…/rotate`` |
| ``api_key.quarantined`` | Admin POST ``…/quarantine`` |
| ``api_key.unquarantined`` | Admin POST ``…/unquarantine`` |
| ``api_key.ttl_updated`` | Admin PATCH ``…`` |
| ``api_key.expired`` | Lifecycle sweep |
| ``api_key.expiry_warning`` | Lifecycle sweep |
| ``api_key.auth_denied.quarantined`` | verify_bearer (per failed auth) |
| ``api_key.auth_denied.expired`` | verify_bearer (per failed auth) |
| ``api_key.auth_denied.rotated`` | verify_bearer (per failed auth) |

The ``auth_denied.*`` family is rate-limited by the 60s in-memory
verify-bearer cache: subsequent failed auth attempts within 60s use
the cached "missing" result and don't emit a fresh audit row.

## Settings reference

| Env var | Default | Description |
|---------|---------|-------------|
| ``POINTLESSQL_API_KEY_LIFECYCLE_DEFAULT_TTL_DAYS`` | None | Suggested TTL pre-fill for the admin UI form |
| ``POINTLESSQL_API_KEY_LIFECYCLE_ROTATION_GRACE_SECONDS`` | 86400 | Default predecessor grace window |
| ``POINTLESSQL_API_KEY_LIFECYCLE_EXPIRY_WARNING_DAYS`` | 14 | How far in advance to warn |
| ``POINTLESSQL_API_KEY_LIFECYCLE_QUARANTINE_ON_EXPIRY`` | true | Auto-quarantine expired keys (vs. audit-only) |
| ``POINTLESSQL_API_KEY_LIFECYCLE_SWEEP_INTERVAL_SECONDS`` | 3600 | Sweep cadence |

## Known limitations

- **Cache TTL of 60s on revocation latency.**  Quarantine and
  unquarantine call ``invalidate_cache()`` so the auth gate flips
  immediately on the same process.  Passive expiry (no admin
  action) takes up to 60s to land via cache TTL — acceptable for
  the TTL surface, documented here for clarity.
- **No multi-process cache coherence.**  Multi-worker deployments
  may show different cache states for ~60s after a mutation.  The
  sweep + auth-gate both consult the DB authoritatively, so the
  worst case is a transient bypass, not indefinite divergence.
- **No external notification yet.**  The sweep audits ``api_key.expiry_warning``
  but doesn't email / Slack / webhook.  Operators poll the audit
  log.  Wiring this through the Phase 102 Track-H webhook
  infrastructure is a one-sprint follow-up.
