---
title: ADR-0008 Workspace soft isolation
status: Accepted
date: 2026-05-05
---

# ADR-0008 — Workspace soft isolation

## Status

**Accepted** (2026-05-05).  Phase 28 closed across nine
sub-sprints (28.0 through 28.8) under this contract.

## Context

After Phase 18.7 (audit FTS) PointlesSQL had a feature-complete
audit / lineage / branching / promotion stack but was
**single-tenant**: every install assumed one user community
sharing one set of jobs, dashboards, saved queries, recents, and
audit trails.  For OSS launch, multi-team installs, or any
"agent-driven sandbox vs. production" pattern this was the next
foundational gap.

Two adjacent ecosystems frame the design space:

* **Databricks workspaces** — global Unity Catalog + per-
  workspace user-state.  Cross-workspace data reads work via UC
  privileges; per-workspace audit / job state stays isolated.
* **Hard tenancy** (DB-per-tenant, separate processes) — the
  enterprise-edition shape.  Strong isolation, but ~6 months of
  work and rules out the cross-workspace data-sharing patterns
  that make agent-driven dev → prod dataflow easy.

## Decision

Phase 28 adopts the **Databricks soft-isolation model**:

1. **Catalogs stay global.**  soyuz UC namespace is install-wide.
   Every workspace can read any catalog subject to UC privileges.
   Cross-workspace data flow (e.g. dev workspace reading
   `prod.silver.orders` to bootstrap a sandbox merge) is a
   feature, not a bug.
2. **Tables stay catalog-scoped.**  No `workspace_id` on Delta
   tables.  Sharing between workspaces requires zero new code;
   UC privileges already gate it.
3. **Workspaces are governance/audit containers.**  Every
   PointlesSQL-owned table that today represents per-user /
   per-run / global-audit state grew a `workspace_id` column.
   Audit trails, jobs, dashboards, saved queries, recents,
   alerts, and anomaly-acks all became workspace-scoped.
   **A user in workspace A cannot see workspace B's runs, jobs,
   or audit logs**, even though both can query the same global
   catalog.
4. **`workspace_catalog_pins` is cosmetic only.**  A workspace
   pins a default catalog so its sidebar tree starts there; no
   enforcement.  Avoids creating false expectations of isolation
   that would contradict decision 1.
5. **M:M user↔workspace** (`workspace_members` junction) from
   the start.  UI initially exposes a single-active-workspace
   switcher, but the model supports multi-membership without a
   future migration.
6. **Soyuz untouched.**  The allow-list / grant logic lives
   entirely PointlesSQL-side.  The Phase-14 external-write
   scanner stays workspace-orthogonal (scans Delta history
   globally, attributes against PointlesSQL ops by FK).
7. **Single seed `default` workspace at id=1**, created in the
   Sprint-28.0 migration.  All existing rows backfill to
   `workspace_id=1`; all existing users become members; all
   existing api_keys pin to `workspace_id=1`.  Single-tenant
   installs see zero behaviour change.

## Resolution priority

The middleware threads four tiers, picked carefully so each
caller-shape resolves to the right intent:

```text
explicit X-Workspace header (slug)
    → API-key's pinned workspace_id
        → session-cookie current_workspace_slug (Sprint 28.4)
            → user.default_workspace_id
                → DEFAULT_WORKSPACE_ID (=1, fallback floor)
```

* Header wins: lets a Hermes-driven agent re-target per call.
* API-key pin beats cookie: Bearer auth has no cookie at all.
* User default beats fallback: browser sessions resume where the
  user last left off.
* The literal `1` floor keeps the pipeline safe during
  anonymous-prefix probes / fresh-install windows.

## Consequences

### Positive

* OSS-launch-ready multi-team support without rewriting the
  query engine or moving to per-tenant processes.
* Existing single-tenant installs see zero behaviour change.
  The topbar switcher hides itself when ≤1 workspace exists.
* Cross-workspace data sharing works out of the box — a sandbox
  workspace reading prod data is just a UC privilege away.
* Audit trail stays trustworthy across tenants: a workspace
  admin cannot see another workspace's audit history without
  the explicit super-admin lens.

### Negative

* No hard isolation guarantee.  A SQL bug that bypasses the
  workspace_id filter would leak data; the test suite covers
  every endpoint to mitigate but the *runtime* boundary is
  software, not OS.
* `workspace_catalog_pins` is purely cosmetic — admins who
  expect "pinning means scoping" will be surprised.  The
  switcher dropdown's contextual help (`workspace.what-is-a-
  workspace`) calls this out explicitly.
* Per-workspace rate limits / quotas are out of scope.
  `rate_limit_middleware.py` keys by IP / api_key today; a
  workspace-aware refactor lands in a future sprint when a real
  customer asks.
* `system_keys`, `audit_sinks`, `review_destinations` stay
  install-level — one PII salt, one Slack webhook.  Per-
  workspace destinations are out of scope for Phase 28.

## Out of scope (named explicitly)

* Hard isolation (DB-per-tenant) — enterprise-edition territory.
* Per-workspace rate limits.
* soyuz-side tenant primitives — soyuz stays workspace-agnostic.
* Workspace OIDC group mapping — auto-assign membership from
  OIDC group claims; defer to Phase 29.x once a real customer
  asks.
* Workspace-scoped MLflow tracking — Phase 21 MLflow subprocess
  is install-level today.
* Hard delete of workspaces — only soft-archive in MVP.

## Cross-references

* [Workspaces concept doc](../concepts/workspaces.md)
* [Workspace management runbook](../admin/workspace-management.md)
* [`pointlessql/services/workspaces.py`](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/services/workspaces.py)
* Sprint-28 migrations:
  - `z6w8a0b2c4d6` — workspace foundation (Phase 28.0)
  - `aa1c3e5g7i9k` — agent-run audit core (Phase 28.1a)
  - `bb2d4f6h8j0l` — lineage / audit_log / governance (Phase 28.1b)
  - `cc3e5g7i9k1m` — user-owned + scheduler tables (Phase 28.2)
  - `dd4f6h8j0l2n` — `users.default_workspace_id` NOT NULL (Phase 28.6)
