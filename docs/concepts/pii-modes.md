# PII modes

 closes the cleartext-at-rest gap on
`lineage_value_changes`. When `settings.audit.pii_mode` is anything
other than `store_clear`, the bulk-insert into the value-changes
table redacts `old_value` / `new_value` for columns whose name
matches a built-in PII pattern *before* the row hits SQLite.

## Three modes

| Mode | Stored value | Equality joinable? | Reversible? |
|------|--------------|-------------------|-------------|
| `store_clear` | original cleartext | yes | yes |
| `hash_only` *(default)* | first 16 hex chars of `HMAC-SHA256(secret, value)` | yes | no |
| `redact_with_audit_log` | literal `<redacted>` | no | no |

`hash_only` is the default for new installs. It satisfies the
"no cleartext PII at rest" compliance posture while keeping the
trail useful for analysts: two changes to the same email by the
same install always produce the same hash, so cohort-by-identity
queries still work.

## What counts as PII

 uses pattern-based detection at write time. A column
whose name matches
[`PII_NAME_PATTERN`](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/services/pii_redactor.py#L48)
is redacted regardless of soyuz tags. Patterns include:

- `email`, `e_mail`, `mail`
- `phone`, `mobile`, `tel`, `telephone`
- `ssn`, `social_security`, `national_id`, `tax_id`
- `passport`, `driver_licen` / `drivers_licen`
- `credit_card`, `cc_num`, `iban`, `bic`, `swift`, `account_number`
- `password`, `passwd`, `secret`, `token`, `api_key`
- `first_name`, `last_name`, `full_name`, `given_name`
- `address`, `street`, `postal`, `zipcode`, `postcode`
- `dob`, `birth`, `birthday`
- `gender`, `race`, `ethnicity`, `religion`
- any name containing the substring `pii`

False positives (non-PII column names matching the pattern) are
preferable to false negatives — masking a non-PII cell only loses
analytical convenience; leaking a PII cell is a compliance breach.

Soyuz `pii=*` tags are *not* consulted at write time. They drive
the render-time masking only; that masking still gates
cleartext on the API surface for tagged-but-non-pattern columns.

## Hash secret bootstrap

`hash_only` requires a secret. Resolution order:

1. The `POINTLESSQL_AUDIT_PII_HASH_SECRET` env var, if set.
2. The `system_keys.name = 'pii_hash'` row in the metadata DB.
3. If neither exists, the redactor lazily generates a 32-byte
 URL-safe random token at first use and INSERTs it into
 `system_keys`.

Backups of the metadata DB include the secret. Rotation: drop the
row (`DELETE FROM system_keys WHERE name='pii_hash'`); the next
PII redaction call generates a new one. Old hashes stay valid for
historical equality joins; new writes use the new secret. No
historical re-hashing.

## Migration impact

Existing `lineage_value_changes` rows are **not** rewritten. The
redaction layer activates only on new INSERTs. Operators on
earlier.1 data see a soft transition: historical clear values
stay readable to admins via the existing render-time masking; new
value-changes hash.

To opt-out (keep earlier behaviour): set
`POINTLESSQL_AUDIT_PII_MODE=store_clear` in the process env.

## Audit-log surface

Under `redact_with_audit_log`, every per-op record_value_changes
call that masked at least one cell appends one `audit_log` row:

- `actor_role = "system"`
- `user_email = "system:pii_redactor"`
- `action = "pii_redact"`
- `target = "agent_run_operations:<op_id>"`
- `detail = {"redacted_count": <int>, "mode": "redact_with_audit_log"}`

Under `hash_only` no audit-log row is appended (the lineage row
itself is the trail).

## Verification

```bash
# 1. Force-set hash_only with a deterministic secret
export POINTLESSQL_AUDIT_PII_MODE=hash_only
export POINTLESSQL_AUDIT_PII_HASH_SECRET=test-secret-please-rotate

# 2. Run the Hermes-medallion notebook (or any pql.merge with track_value_changes=True)
# against a table with a column called `customer_email` or similar PII-named column.

# 3. Inspect the lineage_value_changes table
sqlite3 pointlessql.db "SELECT target_column, old_value, new_value FROM lineage_value_changes ORDER BY id DESC LIMIT 5;"
# customer_email|<16-hex>|<16-hex>
# product_name|Widget|Gadget ← non-PII, cleartext preserved
```
