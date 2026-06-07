---
title: Threat model (STRIDE)
audience: contributor
---

# PointlesSQL threat model

A STRIDE pass over the trust boundaries PointlesSQL spans. It records the
threats per boundary and the controls already in place, so security work has
a map and reviewers can see where a change lands. Pair it with the generated
[authorization coverage matrix](authz-matrix.md) (per-route gate inventory)
and the [disaster-recovery runbook](../admin/disaster-recovery.md).

## Trust boundaries

```text
Browser / IDE / Agent
      │  (1) HTTP + cookies / Bearer API key / MCP
      ▼
PointlesSQL (FastAPI)  ──(2) HTTP──▶  soyuz-catalog (UC REST)
      │                                     │
      │ (3) SQLAlchemy                       │ (4) object store
      ▼                                     ▼
 metadata DB (SQLite/PG)            Delta Lake storage
```

1. **Client ↔ app** — untrusted clients reach authenticated surfaces.
2. **App ↔ soyuz-catalog** — the app is a privileged UC client; principal
   identity is forwarded per request.
3. **App ↔ metadata DB** — the app's own session/preference/audit store.
4. **App ↔ Delta storage** — table data read/written via the PQL bridge.

## STRIDE by boundary

### (1) Client ↔ app

| Threat | Vector | Control |
| --- | --- | --- |
| **S**poofing | Stolen session / forged JWT / leaked API key | JWT (HS256) with key-rotation grace; bcrypt password hashes; API keys hashed at rest with scoped capabilities; IP-ACL on API keys |
| **T**ampering | CSRF on state-changing HTML forms; header injection | CSRF token (cookie + form field) for non-`/api/` unsafe methods; `X-Frame-Options: DENY`; report-only CSP (collector at `/api/csp-report`) |
| **R**epudiation | Action with no attributable trail | Append-only audit log; request/correlation IDs threaded through logs (and OTel spans when enabled) |
| **I**nformation disclosure | Cross-tenant read; verbose errors; referrer leak | Per-workspace isolation + soyuz effective-permissions enforcement; structured error envelopes; `Referrer-Policy: strict-origin-when-cross-origin`; HSTS on HTTPS |
| **D**enial of service | Credential-stuffing / request floods | Fixed-window rate limiting on `/auth/*`; per-route latency metrics to spot abuse |
| **E**levation of privilege | Calling an admin route as a lesser role | `require_*` dependency gates per route; the authz-matrix generator flags any **ungated** route |

### (2) App ↔ soyuz-catalog

- **Spoofing / EoP**: the app forwards the caller's principal (`X-Principal`)
  so soyuz enforces effective permissions; the app never writes UC tables
  directly (all access via the generated client facade).
- **Tampering**: requests run over localhost / a trusted network; treat the
  soyuz endpoint as a sensitive config value.

### (3) App ↔ metadata DB

- **Tampering / Repudiation**: schema changes only via Alembic migrations;
  audit rows are append-only.
- **Information disclosure**: secrets at rest are Fernet-encrypted
  (`system_keys` master key); DR backups are written mode 0600 and carry a
  hash manifest (encryption-at-rest of backup payloads is a follow-up).

### (4) App ↔ Delta storage

- **Tampering / Repudiation**: writes flow through the PQL hook chain, which
  stamps lineage + audit provenance; row/column/value lineage is verified by
  the lineage-correctness engine.
- **EoP via agents**: agent-driven writes must carry an `AgentRunOperation`
  + CloudEvent — no MCP mutation without provenance (see the MCP write
  surface).

## Known gaps / follow-ups

- CSP is **report-only**; tighten to enforce after collected reports guide
  removal of inline-handler reliance.
- Backup payloads are not encrypted at rest.
- Secrets master-key **rotation** is described but the rotation tool is not
  yet implemented (re-encrypting all dependents needs careful old→new key
  handling).
- The per-route authorization matrix tests (route × persona × expected
  status) are scaffolded as a follow-up to the generated inventory.
