# Workspace management

The workspace admin runbook.  Every action below requires
**tenant-wide admin** (`users.is_admin = True`) — workspace-local
admins (`workspace_members.role = 'admin'`) get the
membership-management subset only.

## Onboarding a new tenant team

The most common day-one flow when a second team joins a previously
single-tenant install.

### 1. Create the workspace

```bash
curl -sS -X POST http://localhost:8000/api/admin/workspaces \
  -H 'Content-Type: application/json' \
  -H 'Cookie: pql_session=<your admin cookie>' \
  -H 'X-CSRF-Token: <csrf token>' \
  -d '{"slug": "team-pricing", "name": "Pricing team", "description": "ML + dashboard work"}'
```

Or use the [`/admin/workspaces`](http://localhost:8000/admin/workspaces)
HTML page.  Slug rules: `[a-z0-9_-]`, max 64 chars, must not
start or end with a separator.

### 2. Add members

`POST /api/admin/workspaces/{id}/members`:

```json
{"user_email": "alice@example.com", "role": "admin"}
```

Roles:

* `member` — read/write within the workspace.  Default.
* `admin` — workspace-local admin.  Can manage members + pins
  but cannot create new workspaces (that requires tenant admin).

The audit log records every membership change with action
`workspace.member_added` / `workspace.member_role_changed` /
`workspace.member_removed`.

### 3. (Optional) Pin a default catalog

If the team's data lives mostly under one UC catalog, pin it
`primary` so the sidebar tree pre-expands to it on first load:

```bash
curl -sS -X POST http://localhost:8000/api/admin/workspaces/3/pins \
  -H 'Content-Type: application/json' \
  -d '{"catalog_name": "team_pricing", "mode": "primary"}'
```

Pins are **cosmetic only** — the workspace can still query any
catalog.  Promoting a second catalog to `primary` auto-demotes
the previous one to `pinned`.

### 4. Mint API keys

If the team uses Hermes / agent-driven flows, mint each api_key
pinned to their workspace:

```bash
pointlessql admin issue-auditor-key --name=pricing-daily-review
# Note the printed plaintext, then update the api_keys row's
# workspace_id via the admin UI (Sprint 28.6).
```

The plugin's `POINTLESSQL_WORKSPACE` env var (Sprint 28.5) lets
one shared api_key target multiple workspaces; without it the
api_key's pin IS the workspace.

## Common operations

### Switch workspace as a user

The topbar switcher dropdown writes the `pql_workspace` cookie.
The cookie carries the slug; the middleware reads it on every
request and resolves to the workspace's id.

When a user belongs to ≤1 workspace, the switcher hides itself
and the cookie tier of the resolver doesn't fire — the install
behaves identically to pre-Phase-28.

### Cross-workspace audit query (super-admin lens)

Tenant admins can query the audit data lake across workspaces:

```bash
curl -sS 'http://localhost:8000/api/audit/summary?workspace=all' \
  -H 'Cookie: pql_session=<admin cookie>'
```

The response gains `"lens_mode": "all"` and the audit-of-audit
trail records the call with `read_kind = "audit_api_cross_workspace"`
so the cockpit can flag the escalation.

Non-admins asking for `?workspace=all` (or any workspace other
than their resolved one) get a 403.

### Archive a workspace

Soft-delete via `POST /api/admin/workspaces/{id}/archive`.
Archived workspaces hide from the switcher and from default
listings but keep all their data so historical audit rows still
resolve.

The seeded `default` workspace (id=1) **cannot** be archived —
the resolver's fallback floor depends on it always being live.

## Troubleshooting

### `audit_log` entries with `workspace.context_mismatch`

Written by the middleware whenever an authenticated caller
sends an `X-Workspace` header for a workspace they're not a
member of (or whose API key isn't pinned to).  The 403 response
short-circuits the request before any handler runs.

Common causes:

* Stale browser tab open after an admin removed the user.
  Re-login; the cookie / JWT will resolve to a workspace the
  user is still in.
* Plugin `POINTLESSQL_WORKSPACE` env var pointing at a workspace
  the api_key isn't pinned to.  Either update the env var or
  rotate the api_key to the right workspace via the admin UI.
* Cross-workspace probe by a non-member.  The audit row is the
  evidence — investigate the request_id in the cockpit.

### "Why doesn't workspace A see workspace B's audit data?"

Working as designed.  See
[ADR-0008](../decisions/0008-workspace-soft-isolation.md) for
the soft-isolation contract.  Tenant admins can opt into the
cross-workspace lens via `?workspace=all`; everyone else sees
their workspace only.

### "Why CAN workspace A read workspace B's tables?"

Working as designed.  Catalogs are global per
[ADR-0008](../decisions/0008-workspace-soft-isolation.md) decision 1.
UC privileges decide who can read what.  PointlesSQL only
isolates the **audit / job / saved-query** state.

If you want hard isolation per-table, that's enterprise-edition
territory; file an issue describing the use case.

## See also

* [Workspaces concept](../concepts/workspaces.md)
* [ADR-0008 — workspace soft isolation](../decisions/0008-workspace-soft-isolation.md)
* [Sprint 28.5 — workspace env var for the plugin](../integrations/hermes-jobs/README.md#workspace-scoping-sprint-285)
