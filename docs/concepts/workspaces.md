# Workspaces

PointlesSQL ships with **soft workspace isolation** modeled after
Databricks Unity Catalog: catalogs stay global so any workspace
can read any table subject to UC privileges, but every PointlesSQL-
owned audit / job / saved-query / lineage row carries a
`workspace_id` filter.  A user in workspace A cannot see workspace
B's runs, jobs, or audit log — even though both can query the same
global catalog.

Phase 28 introduced the model.  Single-workspace installs are
unaffected: every existing audit / job / saved-query row backfilled
to a seeded `default` workspace at `id=1`, and the topbar switcher
hides itself when only one workspace exists.

## What's isolated

* **Audit data** — `agent_runs`, `agent_run_operations`,
  `agent_run_events`, `agent_run_tool_calls`, `agent_run_sources`,
  the four `lineage_*` tables, `query_history`, `audit_log`,
  `governance_events`, `unattributed_writes`, `anomaly_acks`.
* **User-owned objects** — `jobs` (and the four scheduler child
  tables: `job_runs`, `job_tasks`, `task_runs`, `job_logs`),
  `dashboards`, `saved_queries`, `saved_audit_queries`,
  `recent_tables`, `alerts`, `alert_events`, `notebook_outputs`,
  `notebook_cell_runs`.
* **API keys** — every `api_keys` row pins to one workspace via
  `api_keys.workspace_id`.  Sprint 28.5's plugin sends an
  `X-Workspace` header to override the pin per call; mismatched
  combinations 403 with an `audit_log` breadcrumb.

## What's NOT isolated

* **Unity Catalog catalogs** — global namespace.  Workspace A
  reading `prod.silver.orders` is a feature, not a bug; UC
  privileges already gate cross-workspace data flow.
* **`system_keys`** — install-level secrets (PII salt, etc.).
* **`audit_sinks`, `review_destinations`** — install-level
  webhook configuration.
* **soyuz-catalog** — the lakehouse metadata server is workspace-
  agnostic.  All allow-list / pin logic lives PointlesSQL-side.
* **`workspace_catalog_pins`** — pins are a *cosmetic* sidebar
  hint, never an enforcement boundary.

## How the resolver picks a workspace

Every request goes through a four-tier resolver in
[`pointlessql/services/workspaces.py:resolve_workspace_id`](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/services/workspaces.py):

```text
explicit X-Workspace header (slug)
    → API-key's pinned workspace_id
        → session-cookie current_workspace_slug
            → user.default_workspace_id
                → DEFAULT_WORKSPACE_ID (=1, the seed floor)
```

The order is deliberate:

* **Header wins** so a Hermes-driven agent can re-target per tool
  call without touching the user's stored default.
* **API-key pin beats cookie** because Bearer-token auth doesn't
  carry a session cookie at all — the pin IS the caller's stored
  intent.
* **User default beats fallback** so a browser session ends up
  where the user last logged in.
* **The literal `1` floor** keeps the request pipeline safe
  during exotic edge cases (anonymous public-prefix probe,
  brand-new install, test fixture that bypasses bootstrap).

## The cross-workspace lens (Sprint 28.7)

Tenant-wide admins can opt into cross-workspace queries on the
audit endpoints with `?workspace=`:

| Value | Outcome | Audit-of-audit `read_kind` |
|---|---|---|
| (omitted) | Scope to caller's resolved workspace | `audit_api` |
| `?workspace=<slug>` (admin only) | Scope to that named workspace | `audit_api` |
| `?workspace=all` (admin only) | Lift the workspace filter — god-eye view | `audit_api_cross_workspace` |

Non-admins asking for any workspace other than their resolved one
get a 403.  The escalation is itself audit-logged with the distinct
`audit_api_cross_workspace` read_kind so the cockpit can flag it.

## Cross-workspace data sharing pattern

Because catalogs stay global, the natural pattern for "dev
workspace bootstrapping a sandbox merge from prod data" works
without any new code:

```python
import pointlessql as pql

# Workspace=dev, but reads prod.silver.orders directly.
# UC privileges decide whether this read is allowed.
pql.merge(
    sql="SELECT * FROM prod.silver.orders WHERE order_date >= ...",
    target="dev_sandbox.bronze.orders_snapshot",
    on=["order_id"],
)
```

The merge writes audit rows in `agent_run_operations` with
`workspace_id=<dev>`, even though the source table lives outside
the workspace.  Cross-workspace reads do *not* leak into
workspace B's audit trail; they only leave a row in workspace A's
audit trail referencing the source FQN.

## Common admin tasks

* **Create a workspace** — `/admin/workspaces` page (Sprint 28.6)
  or `POST /api/admin/workspaces`.
* **Add a member** — `POST /api/admin/workspaces/{id}/members`
  with `user_email` + `role` (`member` or `admin`).
* **Pin a default catalog** — `POST /api/admin/workspaces/{id}/pins`
  with `catalog_name` + `mode` (`primary` for default-expansion).
* **Archive** — soft-delete via
  `POST /api/admin/workspaces/{id}/archive`.  The seeded `default`
  workspace (id=1) cannot be archived — the resolver's fallback
  floor depends on it always being live.

The admin runbook at
[`docs/admin/workspace-management.md`](../admin/workspace-management.md)
walks through the typical tenant-onboarding flow end-to-end.

## See also

* [ADR-0008 — workspace soft isolation](../decisions/0008-workspace-soft-isolation.md)
* [Audit trail](audit-trail.md)
* [Authentication & authorization](auth.md)
