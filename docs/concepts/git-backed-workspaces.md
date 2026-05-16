# Git-Backed Workspaces

A *git-backed workspace* in PointlesSQL is the convention "this
workspace pulls 1..n configuration sources straight from git
repositories committed by the data team".  Phase 51 adds the
workspace-side bracket on top of the yaml-canonical pattern
Phase 50 introduced for Data Products (and Phase 13.5 introduced
for Conventions).

PointlesSQL does **not** introduce a new UC entity for these
repos.  A *workspace_repo* is an opt-in property of an existing
workspace — registered through the admin pages (or
`POST /api/admin/repos`), cloned on demand into
`<base_dir>/<workspace_id>/<slug>/`, and re-synced via webhook
or cron.

## Why bother?

Without the convention, every yaml that PointlesSQL consumes
needs an admin to drop it into the right local directory and
keep it in sync by hand.  With it:

- **Single canonical source.**  Git is the truth, the DB is a
  cache.  Any `pointlessql.yaml` (data product / conventions /
  dashboards / saved queries) lands in the team's repo and
  flows into PointlesSQL automatically.
- **Notebook portability.**  Schedule a notebook with the
  spec `repo:<workspace_id>:<slug>/<rel>.py` and the executor
  resolves the file under the workspace's clone tree
  (read-only).
- **Read-only by design.**  PointlesSQL never edits the repo —
  changes go through the team's normal git tool / pull request
  flow.  This carries Phase 50's "git-blame is the audit log"
  property forward across every yaml-canonical asset.
- **Provider abstraction.**  A `GitProvider` Protocol with
  `GenericGitProvider` (vanilla SSH/HTTPS) and `GitHubProvider`
  (with HMAC webhook signature verification) ships today;
  GitLab / Gitea drop in as additional axis files in
  `pointlessql/git/` without touching the service layer.

## What gets read from a repo?

| Path / yaml block | Loader | Phase |
|---|---|---|
| `pointlessql.yaml` with `data_product:` | `load_contracts_for_workspace` | 50 + 51.2 |
| `pointlessql.yaml` without `data_product:` | `load_conventions_for_workspace` | 13.5 + 51.2 |
| `<rel>.py` referenced by `repo:<ws>:<slug>/<rel>.py` notebook spec | `resolve_notebook_path` | 51.3 |

The two glob patterns walked under each clone dir (configurable
via `POINTLESSQL_REPOS_YAML_SEARCH_GLOBS`) default to:

```
pointlessql.yaml
**/pointlessql.yaml
```

A single yaml file can carry multiple top-level keys; the
loaders that don't recognise a key skip it as a no-op.

## Yaml shape (combined example)

```yaml
data_product:
  name: Sales Orders
  version: "1.2.0"
  catalog: main
  schema: sales_gold
  steward_email: alice@example.com
  sla_minutes: 60
  tables:
    - name: orders
      primary_key: [order_id]
      columns:
        - {name: order_id,    type: long,      nullable: false}
        - {name: order_total, type: decimal,   nullable: true}
        - {name: ordered_at,  type: timestamp, nullable: false}

```

## Auth model

A workspace_repo carries 0..n encrypted credentials
(`workspace_repo_secrets`):

- **`deploy_key`** — PEM-encoded SSH private key for repos
  served over `git@github.com:owner/repo.git`-style URLs.
- **`https_token`** — PAT-style bearer for HTTPS clones.
  Injected as `https://x-access-token:<token>@host/path` at
  clone time.
- **`oauth_token`** — short-lived GitHub-App installation
  token; reserved for the deferred Sprint 51.6 path.

All three kinds are encrypted at rest with **Fernet
authenticated encryption**, keyed off an install-scoped master
key in `system_keys` (`name='repo_secrets_master'`).  Secrets
are never logged, never echoed back through `GET` calls, and
revealed at most once at insert time.

The webhook secret is the exception: it's stored as plaintext
because the inbound-signature verification needs constant-time
HMAC comparison.  It's still reveal-once at create time + on
explicit rotation.

## Sync triggers

Three ways for an upstream commit to land in the on-disk clone:

1. **Manual.**  ``POST /api/admin/repos/{id}/sync`` (admin)
   or the agent tool ``pql_trigger_repo_sync``
   (supervisor-gated).
2. **Webhook.**  GitHub-style ``POST /webhook/git/{id}``;
   signature verified against `webhook_secret`; non-push events
   ignored with a 202.
3. **Cron.**  Lifespan ``_workspace_repos_sync_loop`` opt-in
   via `POINTLESSQL_REPOS_SYNC_INTERVAL_SECONDS≥60`; pulls
   every repo whose `last_synced_at` is older than the cadence.

Every successful sync re-runs the data-products + conventions
loaders via the post-pull hook; counts surface in the
`SyncOutcome` envelope for the admin / plugin caller.

## Anti-goals

- **No browser notebook editor.**  Notebooks are read-only —
  edits flow through the team's git tool.
- **No in-app diff or conflict resolution.**  PR workflow lives
  in the team's git host.
- **No new UC securable.**  `workspace_repos` is a cache; the
  source of truth is the yaml + git-blame.
- **No domain-specific RBAC ladder.**  The workspace + scope
  (admin / supervisor / auditor) gates every feature.
- **No DB-side guard against UI mutations on repo-loaded
  rows.**  The next sync overwrites them; convention-only.

## See also

- [`docs/e2e-walkthroughs/git-backed-workspaces.md`](../e2e-walkthroughs/git-backed-workspaces.md)
  — replayable browser + curl + agent walkthrough.
- [`pointlessql/git/`](https://github.com/FloHofstetter/PointlesSQL/tree/main/pointlessql/git)
  — provider package source.
