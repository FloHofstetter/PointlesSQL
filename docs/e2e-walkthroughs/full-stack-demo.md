# Full-stack demo: raw CSV → ML + every JSON API in ~30 seconds

`scripts/seed-full-stack-demo.py` is the local-replay companion to the
[agent bring-up recipe](../guides/agent-bring-up.md). In one autonomous
run it walks the entire stack — every PQL primitive, every
MLflow ↔ soyuz cross-link, **and 150+ JSON `/api/*` routes** the
agent / cockpit / models / lineage / branching surfaces are built on —
and ends with a hard prediction on a synthetic house.

The default mode covers ~150 routes across 22 numbered steps in
~30 seconds; pass `--core-only` to fall back to the lite 12-step path
(~13 s, the same shape we shipped in the first version of this
walkthrough).

It produces **exactly the audit-trail shape a Hermes-driven session
would produce**, without needing a live agent. Run it nightly (or
whenever a sprint touches one of those surfaces) to surface
regressions early.

## What it does

The script is split into 25 numbered steps; each prints a banner so the
output is easy to scan. Steps 1-12 are the **core path** (raw → ML →
inference → 24-route smoke tour); steps 13-22 are the **
coverage extension** (every other JSON API the agent + cockpit can
reach); 23-25 are the consolidated read-tour, the final prediction,
and the summary.

### Core path (steps 1-12, also the body of `--core-only`)

1. **Setup** — drop + recreate the `demo_ml` catalog with five schemas
 (`bronze` / `silver` / `gold` / `models` / `predictions`). Clears
 stale `autoload_checkpoints` rows so re-runs are honest.
2. **CSV generation** — write `houses.csv` (200 rows: `house_id`,
 `size_sqft`, `bedrooms`, `age_years`) and `sales.csv` (200 rows:
 `house_id`, `sold_at`, `price`) to
 `notebooks/full_stack_demo_data/`. Deterministic via
 `numpy.random.seed(42)`.
3. **Bronze** — `pql.autoload(...)` ingests both CSVs into
 `demo_ml.bronze.houses_raw` and `demo_ml.bronze.sales_raw`.
4. **Silver** — `PQL.sql(...)` joins bronze into a typed Silver
 DataFrame; `pql.write_table(...)` materialises it as
 `demo_ml.silver.houses_with_sales` with column + value-level
 lineage edges. A second `pql.merge(... track_value_changes=True)`
 flips one cell so the value-changes endpoint has data.
5. **Gold (in branch)** — 80/20 train/test split is written to
 `demo_ml.gold.training_set` / `test_set`, then re-staged inside a
 timestamped branch `demo_ml.gold__staging_<ts>`.
 `pql.branch_promote_preview` prints the conflict report;
 `pql.branch_promote` finalises.
6. **Train** — `pql.training_context(framework="sklearn")` enables
 MLflow autolog; `LinearRegression().fit(X, y)` runs against the
 gold training set and is logged via `mlflow.sklearn.log_model`.
 The script asserts the recovered coefficients land within 30 % of
 the synthetic truth (`size=200`, `bed=25 000`, `age=-1 500`).
 Then `link_model_version_to_run` cross-links the model version to
 both the agent-run and the MLflow run.
7. **Promote** — `POST /api/models/<fqn>/promote` flips v1 to
 champion. If the previous run already promoted v1 the script
 detects the 400 "already champion" response and skips the
 re-promote.
8. **Inference** — `model.predict` runs on the gold test set;
 `pql.write_table(..., source_model_uri="models:/<fqn>/1")`
 materialises the predictions and stamps inference-lineage edges
 onto every row.
9. **Rollback (`--demo-rollback` only)** — a deliberately broken
 `pql.merge` writes nonsense into the predictions table. The
 script then hits `/api/runs/<id>/rollback-preview?target=...` and
 calls `pql.rollback(target, before_run=...)` to restore the table
 to its pre-merge version.
10. **Read-tour** — when the script has a logged-in HTTP session it
 hits the 24 core-path routes covering every Family-A/B/C surface
 (catalog tree, runs, audit cockpit, lineage, branches, models).
 Each route is logged as `OK 200 GET …`, `EXPC <code> …`
 (legitimate non-2xx like a 403 on a managed-catalog `/sync`), or
 `FAIL <code> …`.
11. **Final prediction** — feeds a single synthetic house
 `(size=1800sqft, bedrooms=3, age=8yr)` into the trained model
 and prints the predicted price.
12. **Summary table** — prints tables created, agent runs, routes
 exercised, predictions written, and the final prediction.

### coverage extension (steps 13-22, default)

13. **PQL HTTP writes** — `POST /api/pql/{autoload,write_table,merge,
 drop_table}` against a scratch table the step also cleans up.
14. **SQL HTTP** — `POST /api/sql/execute`, `GET /api/sql/explain`,
 `GET /api/sql/execute/{id}/download?format=csv`, and a no-op
 `cancel` of a non-existing query (expected 404).
15. **Time-travel** — `versions`, `preview-at-version`,
 `row-at-version` against the silver table.
16. **Governance** — `profile`, `stats`, `tags` GET + PATCH,
 `permissions` GET, `effective-permissions`, `lineage/{name}`,
 plus catalog-mutation routes (`POST /api/catalogs`,
 `PATCH /api/catalogs/{n}`, `PATCH /api/catalogs/{n}/schemas/{s}`,
 `POST /api/catalogs/{n}/sync` — the sync 403s on a managed
 catalog by design and is recorded as `EXPC`).
17. **Agent-runs control surface** — registers three external runs
 via `POST /api/agent-runs`, walks one through `tool-call → finish`,
 approves a second, denies a third. This is the
 "Hermes-plugin-talks-to-PointlesSQL" code path the audit trail
 needs to record.
18. **Saved & history queries** — `/api/queries`,
 `/api/queries/{id}/chart-config`, `/api/saved-queries` CRUD,
 `/api/saved-audit-queries` CRUD + `run` + `export.csv` +
 `export.json`.
19. **Dashboards / Jobs / Alerts** — three CRUD blocks; the alert is
 wired to the saved-query from Step 18, then both are deleted.
 Atom + JSON syndication feeds (`/alerts/feed.{atom,json}`) are
 hit with the rotated feed-token.
20. **Volumes + notebooks** — creates a UC volume securable via raw
 HTTP against soyuz, uploads a CSV, lists files,
 `/api/notebooks/inspect` + `/api/notebooks/tree`,
 `convert-to-delta`, then deletes the file.
21. **Admin** — `api-keys` CRUD + revoke, `external-writes` scan +
 acknowledge, `audit-sinks` CRUD + test, `review-destinations`
 CRUD, `pii/reveal` (against a real `lineage_value_changes` row),
 `/api/pql/training/log`.
22. **Federation** — `connections` / `external-locations` /
 `credentials` CRUD; routes that need a live JDBC backend can
 surface 4xx-5xx and are accepted as `EXPC`.

### Coverage tail

23. **Read-tour (extended)** — the original 24 routes plus every
 other read surface: deep catalog walk, tree-search,
 recents, `/api/search`, `/api/home/summary`, `/api/conventions`,
 PQL introspection, agent-runs list/operations/summary/diff,
 five per-run audit aggregations, branch detail + preview-promote,
 ML-context, `/auth/me`, `/healthz`, `/metrics`.
24. **Final prediction** — same synthetic house as the lite path.
25. **Summary** — totals across both paths, including separate
 ` routes` count.

## Replay

```bash
# 1. Bring up a stack (host-side).
uv run pointlessql # in one terminal
# soyuz-catalog must be on :8080 too (separate terminal in
# ~/git/soyuz-catalog: `uv run soyuz-catalog`).

# 2. Run the demo. --register-if-missing (default on) bootstraps
# the demo user the first time; subsequent runs just log in.
export E2E_WAREHOUSE_ROOT=/tmp/pql-demo-warehouse

# Default — full coverage (~30 s, 155 routes). ``--login-email``
# defaults to ``demo@local`` / password ``demopass1`` (override with
# POINTLESSQL_DEMO_EMAIL / POINTLESSQL_DEMO_PASSWORD or the matching
# CLI flags). The first-ever run registers the account; the first
# registered user becomes admin automatically.
uv run python scripts/seed-full-stack-demo.py --fresh --demo-rollback --verbose

# Lite — original 12-step path (~13 s, 24 routes).
uv run python scripts/seed-full-stack-demo.py --fresh --core-only --demo-rollback --verbose
```

A successful first run in the default mode prints **all 25 step
banners**, ends with `✓ 155/155 routes returned 2xx (or expected)`,
and exits in ~30 s. The stateful steps are idempotent (every
CRUD step deletes its own state), but a re-run without `--fresh` is
NOT supported because promoted-branch state on `demo_ml.gold`
blocks the second branch — `--fresh` is the canonical idempotency
hook.

To tear down without re-seeding:

```bash
uv run python scripts/seed-full-stack-demo.py --drop
```

## Output sample (default mode)

```
▶ Step 6 ( 3.4s) Train — sklearn LinearRegression in pql.training_context
 ────────────────────────────────────────────────────────────
 · mlflow tracking_uri=http://127.0.0.1:5000
 · mlflow registry_uri=uc:http://127.0.0.1:8080
🏃 View run shivering-crow-668 at: http://127.0.0.1:5000/#/experiments/0/runs/...
 ✓ trained: intercept=58853, coefs=(198.2, 23470.5, -1497.6)
 ✓ coefs within 30% tolerance
 ✓ registered demo_ml.models.house_price_lr version 1
 ✓ cross-linked v1 ↔ agent_run + mlflow_run
…
▶ Step 22 ( 24.6s) Federation — connections / external-locations / credentials
 ───────────────────────────────────────────────────────────────
 · OK 200 GET /api/connections
 · EXPC 404 POST /api/external-locations (route requires JDBC connector)
 …
▶ Step 25 ( 28.8s) Summary
 ───────────
 Tables created 7
 Agent runs created 74
 Routes exercised 155/155
 routes 104/104
 Branches promoted 1
 Predictions written 40
 Rollback demo executed
 Review created 3
 Final prediction $473,965
 Total elapsed 28.8s
```

Lines prefixed with `EXPC` are routes that legitimately surface
non-2xx codes — federation routes that need a live JDBC backend, the
managed-catalog `/sync` 403, the agent-run finish 422 when the run is
already terminal, etc. They count as successful coverage hits.

## Continue the tour

After the seed run completes, the **[grand tour](grand-tour.md)**
walks you through every major UI surface that the freshly-populated
state lights up — catalog, lineage (with the spotlight),
SQL editor, jobs, run-detail audit tabs, ML Registry, branches,
dashboards, alerts, audit cockpit, federation, volumes, and the
responsive + theme toggles. Run the seed with `--keep-state` so the
ephemeral objects (dashboards, alerts, saved queries,
audit-sinks, federation entities) stay on screen for the tour:

```bash
uv run python scripts/seed-full-stack-demo.py --fresh --demo-rollback --keep-state -v
```

## lineage acceptance

 closes the spec/end-to-end-loop gap surfaced by the
first replay (where the demo silently produced 0 rows on
three lineage axes for `demo_ml.*`). After `--fresh --demo-rollback`
finishes, run these queries against `pointlessql.db` — every axis
must come back non-zero:

```bash
sqlite3 pointlessql.db <<'EOF'
SELECT 'silver', COUNT(*) FROM lineage_row_edges WHERE target_table = 'demo_ml.silver.houses_with_sales'
UNION ALL SELECT 'gold-train', COUNT(*) FROM lineage_row_edges WHERE target_table = 'demo_ml.gold.training_set'
UNION ALL SELECT 'gold-test', COUNT(*) FROM lineage_row_edges WHERE target_table = 'demo_ml.gold.test_set'
UNION ALL SELECT 'predictions',COUNT(*) FROM lineage_row_edges WHERE target_table = 'demo_ml.predictions.house_prices_v1'
UNION ALL SELECT 'value_changes', COUNT(*) FROM lineage_value_changes WHERE target_table = 'demo_ml.silver.houses_with_sales'
UNION ALL SELECT 'pred_with_model_uri', COUNT(*) FROM lineage_row_edges WHERE target_table = 'demo_ml.predictions.house_prices_v1' AND source_model_uri IS NOT NULL;
EOF
```

The contract: every count > 0. If `silver` is 0 the demo's
`PQL.sql` projection has stopped projecting `_lineage_row_id`
(the original 15.8 bug). If `value_changes` is 0 but `silver` is
not, the in-step re-merge or its CDF bootstrap is broken. If
`pred_with_model_uri` is 0 but `predictions` is not, the
inference-step `source_model_uri` plumbing has regressed.

## Routes deliberately NOT exercised

| Route | Reason |
|---|---|
| `POST /register` | Account-lifecycle would mutate the user table on every re-run |
| `GET /auth/sso` + `/auth/callback` | Needs an OIDC provider configured |
| `POST /auth/logout` | Would 401 every subsequent route in the same session |
| HTML / template routes (everything `response_class=HTMLResponse`) | Out of scope here — covered separately by the Playwright walkthroughs under [`docs/e2e-walkthroughs/`](README.md) |

## Failure modes

| Symptom | Likely cause |
|---|---|
| `Internal server error` on `--fresh` (catalog drop) | A leftover MLflow registered model under `demo_ml.models.*` blocks the cascade. The script auto-drops registered models before the catalog now, but a partial run from before this fix may leave residue — drop the model row directly: `curl -X DELETE 'http://127.0.0.1:8080/api/2.1/unity-catalog/models/demo_ml.models.house_price_lr?force=true'` |
| `Permission denied: /home/flo/git/PointlesSQL/warehouse/...` | The default `E2E_WAREHOUSE_ROOT` of `/app/warehouse` only works in Docker. Set `E2E_WAREHOUSE_ROOT=/tmp/pql-demo-warehouse` (or any host path you own) before re-running. |
| `coefs drifted >30%` warning | The synthetic seed produces predictable coefficients; if the warning fires consistently a regression in `pql.training_context` or sklearn's autolog is the next thing to check. |
| `promote refused (403)` | The login user is not an admin. Promote your demo user: see the snippet below. |
| `connection refused: 127.0.0.1:5000` during training | MLflow subprocess is not running. `uv run pointlessql` boots it via lifespan; for a manual smoke verify with `curl -sf http://127.0.0.1:5000/health`. |
| `connection refused: 127.0.0.1:8080` | soyuz-catalog is not running. `cd ~/git/soyuz-catalog && uv run soyuz-catalog`. |

## Promote a demo user to admin

The first registered user becomes admin automatically. Subsequent
users (e.g. a `demo@local` account) need a one-time DB nudge:

```python
from pointlessql.db import init_db, get_session_factory
from pointlessql.models import User
from pointlessql.settings import Settings

init_db(Settings().db.url)
with get_session_factory()() as s:
 u = s.query(User).filter_by(email="demo@local").one()
 u.is_admin = True
 s.commit()
```

## Why this script exists

 closure left "manual e2e replay" as a user-job — and for
months the only way to know the full raw-to-ML pipeline still worked
was to wire a Hermes agent against a Hermes-plugin-pointlessql build,
which is heavy, slow, and hard to reproduce. This script is the
**fast smoke test**: it stresses the same primitives and routes a real
Hermes session would, runs in 13 seconds against a fresh stack, and
gives a deterministic pass/fail signal that you can paste into a PR
description or a release-readiness checklist.
