# REST API

PointlesSQL exposes ~205 HTTP routes across 34 router files.
This page hand-curates the **top-30** routes that an integrator
will actually call — auth, runs, models, lineage, write, merge,
branching, supervisor, auditor. The remaining ~180 routes are
mostly internal HTML rendering for the web UI.

> **** will add an auto-generated appendix covering
> all 205 routes, derived from `app.openapi()`. Until then, the
> source of truth for the long tail is
> [`pointlessql/api/*_routes.py`](https://github.com/FloHofstetter/PointlesSQL/tree/main/pointlessql/api).

## Conventions

| Convention | What it means |
|---|---|
| `🔓` no badge | Anonymous OK (rare — `/healthz` only) |
| `🍪` cookie | Cookie session OR API key |
| `🔑` api-key | API key only (cookie rejected) |
| `👮 supervisor` | API key with `supervisor=True` |
| `🕵 auditor` | API key with `auditor=True` |
| `⚙ admin` | Cookie session with `is_admin=True` |

Headers used by every authenticated mutating call:

- `Authorization: Bearer <token>` — when using API key
- `X-Agent-Run-Id: <run-id>` — opt-in run-stamping; PQL bridges
 set this when present
- `X-Principal: <name>` — opt-in for audit attribution under a
 shared key

## Auth

| Method | Path | Tier | Purpose |
|---|---|---|---|
| `POST` | `/auth/login` | 🔓 | Form-encoded login; sets the JWT session cookie. |
| `POST` | `/auth/logout` | 🍪 | Clears the cookie. |
| `POST` | `/auth/register` | 🔓 | Self-service register; first user becomes admin. |
| `GET` | `/auth/sso` | 🔓 | Begins the OIDC flow (redirects to provider). |
| `GET` | `/auth/sso/callback` | 🔓 | OIDC callback handler. |

## Agent runs

| Method | Path | Tier | Purpose |
|---|---|---|---|
| `GET` | `/api/runs` | 🍪 | List runs, paginated. Filters by `agent_id`, `principal`, `status`, `started_after`. |
| `GET` | `/api/runs/{run_id}` | 🍪 | Run detail with operations + tool-calls. |
| `GET` | `/api/runs/{run_id}/graph` | 🍪 | Cytoscape-shaped DAG of the run's operations + lineage edges. |
| `POST` | `/api/runs/{run_id}/rollback-preview` | 🍪 | Read-only "what would happen" for the rollback action loop. |
| `POST` | `/api/runs/{run_id}/rollback` | ⚙ admin | Execute the rollback. Emits `pointlessql.rollback.executed`. |

## PQL writes

The agent-side surface. Every route auto-derives the
`agent_run_id` from `X-Agent-Run-Id` if the body omits it.

| Method | Path | Tier | Purpose |
|---|---|---|---|
| `POST` | `/api/pql/write_table` | 🍪 / 🔑 | Body `{sql, target, mode, source_model_uri?, source_table_fqn?}`. When `source_model_uri` is set and the SQL has exactly one ref, `source_table_fqn` is auto-derived. |
| `POST` | `/api/pql/merge` | 🍪 / 🔑 | Body `{target, source_query, key, track_value_changes?, track_rejects?, source_model_uri?}`. |
| `POST` | `/api/pql/autoload` | 🍪 / 🔑 | Bronze ingest from URL or path. Body `{source, target, format?, schema?}`. |
| `POST` | `/api/pql/drop_table` | 🍪 / 🔑 | Drops the UC entry; **does not** delete Delta files. |
| `POST` | `/api/pql/training/log` | 🍪 / 🔑 | training-log. Body `{framework, params, metrics, mlflow_run_id?, op_name?, started_at?, finished_at?}`. |

## Models (+)

| Method | Path | Tier | Purpose |
|---|---|---|---|
| `GET` | `/api/models` | 🍪 | List registered models, optional `?catalog=&schema=&enrich_latest=true`. |
| `GET` | `/api/models/{full_name}` | 🍪 | Model detail with version list and `_pql_link` markers. |
| `GET` | `/api/models/{full_name}/versions/{n}` | 🍪 | Single version detail. |
| `GET` | `/api/models/{full_name}/lineage` | 🍪 | Bidirectional model DAG (`{nodes, edges}`). Three node kinds (`model` / `table` / `prediction`); two edge kinds (`trained_from` / `inferred_to`). |
| `GET` | `/api/models/{full_name}/predictions` | 🍪 | Tables fed by this model with row counts. |
| `GET` | `/api/models/{full_name}/runs` | 🍪 | Agent runs that produced versions. |
| `GET` | `/api/models/{full_name}/promotion` | 🍪 | `{champion_version, history[]}`. |
| `POST` | `/api/models/{full_name}/promote` | 👮 supervisor | champion-flip. Body `{target_version, reason}`. Persists `agent_review` + emits `pointlessql.model.promoted`. |

## Lineage

| Method | Path | Tier | Purpose |
|---|---|---|---|
| `GET` | `/api/lineage/{full_name:path}` | 🍪 | Per-table summary (counts of incoming + outgoing edges). |
| `GET` | `/api/lineage/row-trace?table=...&row_id=...` | 🍪 | Walk back from a target row through `lineage_row_edges`. |
| `GET` | `/api/lineage/column-trace?table=...&column=...` | 🍪 | Column-level provenance. |
| `GET` | `/api/lineage/value-changes?table=...&row_id=...` | 🕵 auditor | Value-level diffs. Auditor-only because the diffs may carry PII. |
| `GET` | `/api/lineage/row-at-version?table=...&row_id=...&version=N` | ⚙ admin (for arbitrary `N`) | Time-travel to any past version. |

## Branches

| Method | Path | Tier | Purpose |
|---|---|---|---|
| `GET` | `/api/branch` | 🍪 | List active branches with status + age. |
| `POST` | `/api/branch` | 🍪 / 🔑 | Body `{parent_schema, branch_name}`. Symlink local FS, deep-copy cloud (per `BRANCH_CLOUD_STRATEGY`). |
| `POST` | `/api/branch/{name}/promote` | 👮 supervisor | Pointer-swap promotion. Hard-fails on `BranchPromotionConflictError`. |
| `POST` | `/api/branch/{name}/discard` | 👮 supervisor | Cleanup. Removes symlinks (or deep-copy data). |

## Audit cockpit (+)

All `🕵 auditor` (admin gets it via the override).

| Method | Path | Tier | Purpose |
|---|---|---|---|
| `GET` | `/api/audit/summary` | 🕵 auditor | Window-aggregated counts: writes / merges / rejects / external-writes per principal. |
| `GET` | `/api/audit/timeseries?axis=...&window_days=...` | 🕵 auditor | Per-axis time-series for the cockpit + Grafana. |
| `GET` | `/api/audit/anomalies?window_days=...` | 🕵 auditor | σ-based verdicts (`ok` / `warn` / `critical`) per axis. |
| `GET` | `/api/audit/principal-summary?principal=...` | 🕵 auditor | "What did agent X do?" — runs + tables touched + cost. |
| `GET` | `/api/audit/history?run_id=...` | 🕵 auditor | Append-only event log for a run. |
| `POST` | `/api/audit/pii/reveal` | 🕵 auditor | Body `{audit_log_id}`. Returns the unmasked value of a PII-tagged audit row, gated by the auditor scope. See [PII modes](../concepts/pii-modes.md). |

## Reviews

| Method | Path | Tier | Purpose |
|---|---|---|---|
| `GET` | `/api/reviews` | 🍪 | List `agent_reviews` rows. |
| `POST` | `/api/reviews` | 🕵 auditor or 👮 supervisor | Persist a review (used by the daily Audit-Reviewer-Bot via `pql_post_audit_review`). |

## Admin API keys

| Method | Path | Tier | Purpose |
|---|---|---|---|
| `GET` | `/api/admin/api-keys` | ⚙ admin | List keys (no plaintext). |
| `POST` | `/api/admin/api-keys` | ⚙ admin | Mint a key. Body `{name, supervisor?, auditor?}`. Plaintext returned exactly once. |
| `POST` | `/api/admin/api-keys/{name}/revoke` | ⚙ admin | Soft-delete (sets `revoked_at`). |

## Audit sinks

| Method | Path | Tier | Purpose |
|---|---|---|---|
| `GET` | `/api/admin/audit-sinks` | ⚙ admin | List sinks. |
| `POST` | `/api/admin/audit-sinks` | ⚙ admin | Create. Body `{name, kind, config_json, hmac_secret?, min_severity?, event_filters?}`. |

`kind` values: `webhook`, `s3`, `aws_cloudtrail`.

## Health + metrics

| Method | Path | Tier | Purpose |
|---|---|---|---|
| `GET` | `/healthz` | 🔓 | Liveness probe. `{ok: true}` when the app is up. |
| `GET` | `/metrics` | ⚙ admin | Prometheus exposition. Admin because the metric surface includes scheduler + audit counters. |

## Error envelope

Every JSON-returning route emits the same shape on error:

```json
{
 "ok": false,
 "error": "http 403",
 "detail": "supervisor scope required"
}
```

Validation errors come back as `400 arg_error`:

```json
{
 "ok": false,
 "error": "arg_error",
 "field": "target",
 "expected": "three-part UC name (catalog.schema.table)",
 "hint": "got 'demo.sales' — schema only, missing the table"
}
```

The plugin's
[`tools/_common.py:run`](https://github.com/FloHofstetter/hermes-plugin-pointlessql/blob/main/hermes_plugin_pointlessql/tools/_common.py)
unwraps these envelopes into the agent-visible `{"ok": false,...}`
shape.

## Where to read next

- [Auth](../concepts/auth.md) — cookie + Bearer mechanics, scope
 flags
- [Permissions](permissions.md) — the trust-tier matrix in full
- [Configuration](configuration.md) — env vars that gate routes
- [Hermes plugin tools](../integrations/hermes-jobs/README.md) —
 agent-side wrappers around these routes
