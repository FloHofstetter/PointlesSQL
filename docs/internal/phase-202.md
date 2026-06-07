---
title: "Phase 202 — Authz-Matrix & Security-Härtung (plan)"
audience: contributor
---

# Phase 202 — Authz-Matrix & Security-Härtung

**Status: ⏳ planned (geplant 2026-06-06).** Detail-Sidecar; siehe
[ROADMAP.md](../../ROADMAP.md) (Differentiator-Tiefe-Cluster 197–206).

## Warum

Die Auth-Architektur ist *tief* (JWT-Sessions + Bearer-API-Keys + OIDC +
soyuz-UC-Grants + IP-ACL + Fernet-Secrets), aber die **Durchsetzung ist
nicht systematisch verifiziert**: ~800 Endpoints über 43 Route-Module, 11
Authz-Dependencies — und keine Matrix, die beweist, dass jeder Endpoint
genau die richtige Persona verlangt. Eine vergessene
`Depends(require_admin)` auf einer neuen Route wäre heute eine stille
Rechte-Eskalation, die kein Test fängt. Dazu kommen klassische
Hardening-Lücken: **keine CSP, keine Security-Header, kein SAST in CI**
(bandit/detect-secrets liegen nur als Dev-Deps herum).

Diese Phase macht Autorisierung *beweisbar* (eine generierte, getestete
Matrix Route × Persona × erwarteter Status) und schließt die Hardening-
Lücken als CI-Ratschen — threat-model-getrieben, damit die Arbeit priorisiert
statt verstreut ist.

## Ausgangslage (Fakten)

- **Authz-Layer** ([`services/authorization.py`](../../pointlessql/services/authorization.py),
  139 LOC): `check_privilege` (54-82, Admin-Bypass), `has_privilege` (117);
  Privilegien USE_CATALOG/USE_SCHEMA/SELECT/MODIFY/MANAGE_GRANTS gegen
  soyuz-effective-permissions.
- **Session-Auth** ([`services/auth.py`](../../pointlessql/services/auth.py),
  294 LOC): JWT HS256, HttpOnly SameSite=Lax, bcrypt; Key-Rotation-Grace
  (91-123); First-User→Admin (167).
- **11 Authz-Dependencies**
  ([`api/dependencies/_roles.py`](../../pointlessql/api/dependencies/_roles.py),
  405 LOC): `require_admin` (24), `require_user` (176), `require_supervisor`
  (205), `require_auditor` (250), `require_analyst` (291),
  `require_sql_execute` (337, token-only), `require_lineage_inbound` (374),
  `require_role` (68, Factory), `admin_uc` (44).
- **Security-Middleware** ([`api/middleware.py`](../../pointlessql/api/middleware.py),
  437 LOC): request_id → csrf
  ([`csrf_middleware.py`](../../pointlessql/api/csrf_middleware.py), 136) →
  rate_limit ([`rate_limit_middleware.py`](../../pointlessql/api/rate_limit_middleware.py),
  253) → auth. **Keine CSP/Security-Header.** Public-Prefixe:
  `/auth/`,`/static/`,`/healthz`,`/alerts/feed.*`,`/webhook/git/`,`/mcp/`,
  `/share/`,`/embed/notebook_share/`.
- **~800 `@router`-Endpoints über 43 `*routes.py`-Module.**
- **WS-Auth** ([`api/ws_auth.py`](../../pointlessql/api/ws_auth.py)),
  **OIDC/PKCE** ([`services/oidc.py`](../../pointlessql/services/oidc.py),
  HMAC-State, Group→Flag-Mapping), **Secrets/Fernet**
  ([`services/secrets.py`](../../pointlessql/services/secrets.py)),
  **AWS-SigV4** ([`services/aws_sigv4.py`](../../pointlessql/services/aws_sigv4.py)).
- **Test-Fixtures** ([`tests/conftest.py:406-545`](../../tests/conftest.py)):
  `admin_client`/`non_admin_client`/`anonymous_client` +
  `supervisor_secret`/`auditor_secret`/`sql_execute_secret`/`api_key_secret`.
- **CI-Security heute** ([`.github/workflows/test.yml`](../../.github/workflows/test.yml)):
  nur `pip-audit` (271-294). **Kein SAST**; `bandit>=1.9.4` +
  `detect-secrets>=1.5` nur Dev-Deps/pre-commit. Kein Dependabot.
- **SECURITY.md** existiert (Disclosure, Scope). **Kein Threat-Model-Doc.**

## Scope (Wellen)

### W1 — Authz-Inventar (generiert, nicht handgepflegt)
- Test/Skript, das aus der FastAPI-App alle Routen + ihre
  `Depends(...)`-Authz-Gates introspiziert → `docs/internal/authz-matrix.md`
  (Route × Methode × erwartete Persona/Scope). Generiert, damit es nicht
  rottet. Lücken (Route ohne erkennbares Gate) explizit markiert.

### W2 — Authz-Matrix-Tests (die Beweis-Schicht)
- Parametrisierter Test über das Inventar: jede Route × {anonymous,
  non_admin, admin, supervisor, auditor, analyst, sql_execute} → erwarteter
  Status (401/403/2xx-or-other) gegen die vorhandenen Fixtures. Eine
  fehlende/falsche Persona-Erwartung failt.
- Public-Prefix-Allowlist explizit + getestet (kein versehentliches
  Öffnen).

### W3 — Security-Header + CSP
- Header-Middleware: `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY` (bzw. `frame-ancestors`), `Referrer-Policy`,
  `Strict-Transport-Security`, `Content-Security-Policy`. CSP iterativ:
  zuerst **Report-Only** (Verstöße sammeln, Inline-Scripts/Styles
  identifizieren — Alpine/HTMX/CodeMirror prüfen), dann enforce.
- e2e-Smoke (Phase 198), dass CSP keine Surface bricht.

### W4 — SAST + Dependency- + Secret-Scanning in CI
- bandit (severity high) als CI-Gate scharf schalten (Dev-Dep existiert);
  detect-secrets-Baseline + CI-Check; pip-audit bleibt. Optional
  semgrep/CodeQL. Dependabot/Renovate-Config.
- Frozen-Floor-Muster für bandit-Findings (analog pyright-Budget), damit
  Bestand nicht blockiert, aber Neues gefangen wird.

### W5 — Secrets-Lifecycle + Rotation
- CLI: Master-Fernet-Key rotieren (alle Workspace-Secrets re-
  verschlüsseln) — heute existiert der Key, aber kein Rotationspfad.
  Secrets nie geloggt (detect-secrets + Code-Review-Check).

### W6 — Threat-Model + Pen-Test-Playbook
- `docs/internal/threat-model.md` (STRIDE über die Auth-Surface,
  Trust-Boundaries: Browser↔App↔soyuz↔Storage↔Agent-Runtime). Priorisiert
  die Restarbeit.
- e2e-Security-Playbook (Phase 198): non-admin-403-Sweep, CSRF-Reject,
  Rate-Limit-Block, IP-ACL, expired-API-Key.

## Akzeptanzkriterien
- Die generierte Authz-Matrix deckt 100 % der Routen; keine Route ohne
  klassifiziertes Gate.
- Der Matrix-Test failt, wenn eine Route ihre erwartete Persona ändert
  oder ein Gate verliert (bewusst eingebauter Regress beweist es).
- CSP ist enforced; keine Surface bricht (e2e grün); Security-Header auf
  jeder Nicht-Public-Response vorhanden.
- bandit + detect-secrets + pip-audit sind blockierende CI-Gates mit
  dokumentiertem Floor.
- Key-Rotations-CLI re-verschlüsselt alle Secrets verifizierbar.
- Threat-Model + Security-Playbook in der mkdocs-Site.

## Risiken / Notizen
- **CSP zuerst Report-Only** — Alpine.js (4464 `x-`-Attribute) + HTMX +
  CodeMirror nutzen ggf. Inline-Handler; harte CSP würde sie brechen.
- Die Authz-Matrix ist nur so gut wie die Introspektion — Routen, die
  Gates *im Body* statt per `Depends` prüfen, müssen erkannt/annotiert
  werden (sonst false-negative).
- bandit-Floor großzügig setzen (viele Findings sind Test-/Tooling-
  Rauschen); an der Quelle fixen statt pauschal ignorieren.
- Verwandt: Phase 3 (Auth), Phase 11 (CSRF/Rate-Limit/OIDC), Phase 28/29
  (Workspace-Isolation), Phase 46 (Auth-Fixtures), `/security-review`-Skill.
