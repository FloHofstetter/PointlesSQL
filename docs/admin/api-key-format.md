# API key token format (Phase 118)

## Wire format

```
pql_{env}_v1_{body40}_{crc8}
```

| Segment | Length | Description |
|---------|-------:|-------------|
| `pql`        | 3  | Issuer prefix.  Constant lowercase.  Matches the project name; used by secret-scanners as the family discriminator. |
| `{env}`      | 4  | One of `live` or `test`.  Embedded so test keys are visually distinct in audit logs, git leaks, and CI output. |
| `v1`         | 2  | Format-version literal.  Parsers key off this exact token; a future v2 bump will not break v1 verification. |
| `{body40}`   | 40 | Base62 (`A-Za-z0-9`) random.  ≥235 bits of entropy (well over the 128-bit "computationally infeasible" threshold). |
| `{crc8}`     | 8  | Lowercase hex CRC32 of everything before the final `_`.  Allows offline secret-scanners to validate authenticity without a server roundtrip. |

Underscores separate segments.  Total length: **61 characters**.

Example:

```
pql_live_v1_xK3aB7nQ2mP8fL1jR4tY6wZ9cN0sH5dG7eU2vI4o_a3f7c1b9
```

## Regex for secret scanners

```regex
pql_(live|test)_v1_[A-Za-z0-9]{40}_[0-9a-f]{8}
```

This regex is exported as `pointlessql.services.api_keys._token_format.V1_REGEX`
so the format spec and the GitHub Secret Scanning Partner Program
registration form pull from one source of truth.

## CRC validation (offline)

Servers and scanners can validate the integrity of a token without
any DB roundtrip:

```python
import zlib

def is_valid_pql_token(token: str) -> bool:
    parts = token.split("_")
    if len(parts) != 5:
        return False
    issuer, env, version, body, crc = parts
    if issuer != "pql" or env not in {"live", "test"} or version != "v1":
        return False
    if len(body) != 40 or not body.isalnum():
        return False
    expected = f"{zlib.crc32(f'{issuer}_{env}_{version}_{body}'.encode()) & 0xFFFFFFFF:08x}"
    return expected == crc
```

A non-matching CRC means the token was typo'd, truncated, or tampered
with — never a valid leaked secret.  `verify_bearer` exploits this to
short-circuit malformed tokens before the database lookup.

## Backward compatibility

Legacy keys minted by `secrets.token_urlsafe(32)` (pre-Phase 118) keep
working **forever**.  Two coexisting formats:

| `token_format` column | Shape | Created by |
|-----------------------|-------|------------|
| `legacy` | 43-char base64-url, no envelope | Pre-118 admin/CLI/env-var bootstrap |
| `v1`     | `pql_{env}_v1_…_{crc8}` | Post-118 admin/CLI bootstrap |

`verify_bearer` first checks for the v1 envelope shape; on any miss
(legacy prefix, malformed v1, bad CRC) it falls through to the
existing SHA-256-of-raw-string lookup.  There is no forced rotation.
Admins choose when (or never) to rotate.

To rotate a legacy key to v1, revoke it in the admin UI and create a
replacement.  Issue the new plaintext to the client out-of-band.

## Why not JWT?

API keys are **long-lived integration credentials** (dbt, BI tools,
CI bots, plugin runtimes).  JWTs are well-suited to short-lived
session tokens where:

- The server is OK trusting claims without a DB lookup
- Revocation latency = TTL is acceptable
- The payload is meant to be transparently inspected by the holder

For long-lived integration keys we want the opposite:

- Instant revocation (DB row update, no waiting for token TTL)
- Opaque secrets that don't leak scope information when copied to a
  pastebin
- The ability to rotate scope independently of the secret

This is why every major integration-key vendor uses **opaque secrets
with DB lookup**: Stripe (`sk_live_…`), GitHub (`ghp_…` / `ghs_…`),
OpenAI (`sk-…`), Anthropic (`sk-ant-api03-…`), Slack (`xoxb-…`).
PointlesSQL's `pql_…` format follows the same playbook.

PointlesSQL **does** use JWTs — for short-lived cookie sessions
([pointlessql/api/auth/_jwt.py](../../pointlessql/api/auth/_jwt.py)),
which is the correct place for them.

## Why SHA-256 (not bcrypt / Argon2)?

API keys are mint-by-the-server, ≥235-bit random tokens.  bcrypt and
Argon2 are slow on purpose to defend against brute-force on
**low-entropy human passwords**.  Brute-forcing a 235-bit random token
takes longer than the heat death of the universe regardless of the
hash function; the slow-hash cost would buy nothing and would
significantly hurt verify-bearer latency on the hot path.

If you ever need to harden cookie-login passwords, that's a separate
discussion (and PointlesSQL already uses pwdlib[bcrypt] for that — see
`pyproject.toml`).

## GitHub Secret Scanning Partner Program registration

Once you deploy this format at any meaningful scale and PointlesSQL
is reachable from the public internet, register with GitHub's Secret
Scanning Partner Program so leaked keys in public repos trigger an
automatic webhook to your revocation endpoint:

1. Build a webhook endpoint at e.g. `POST /api/security/secret-scan`
   that accepts GitHub's signed payload, finds the matching `ApiKey`
   row by hash, and revokes it (and audits the source URL).
2. Submit the partnership application at
   <https://github.com/secret-scanning>.  The form asks for:
   - The token regex (see above)
   - The webhook URL
   - A public RSA key for signature verification
3. GitHub will verify your webhook, then enable scanning on every
   public commit pushed to GitHub.com.  Leaked v1 keys are revoked
   automatically; legacy keys (no envelope shape) won't be detected.

This is free, takes about a day to wire end-to-end, and gives you
real defence-in-depth against accidental leaks.  Wire it as a
follow-up phase once Phase 118 is in production and you've stopped
minting legacy-format keys for new integrations.

## Operator notes

- The `secret_prefix` column was widened from `VARCHAR(8)` →
  `VARCHAR(32)` in [migration `d3e5f7g9b1c4`](../../pointlessql/alembic/versions/d3e5f7g9b1c4_phase118_token_format_v1.py).
  Legacy rows keep their 8-char prefix unchanged.
- A bootstrapped key from `POINTLESSQL_API_KEYS` env var is auto-tagged
  `token_format='v1'` if its secret matches the new envelope shape,
  otherwise `'legacy'`.  Existing deployments need no env-var change.
- The `env` field in the admin POST body defaults to `'live'`.  CI
  pipelines should pass `env: 'test'` so the resulting tokens are
  obviously non-production when they show up in build logs.
