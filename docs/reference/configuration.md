# Configuration

Every PointlesSQL setting lives in
[`pointlessql/settings.py`](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/settings.py)
as a pydantic-settings `BaseSettings` sub-model.  Sprint 45 split
the original flat schema into 18 sub-models with per-sub-model
`env_prefix`; every variable follows the
`POINTLESSQL_<SUBMODEL>_<FIELD>` shape.

`.env.example` in the repo root carries the full machine-
readable list with comments — this page is the prose
companion grouped by sub-model with rationale per setting.

## Server

Bind address + public URL.  Reads `POINTLESSQL_SERVER_*`.

| Variable | Default | Description |
|---|---|---|
| `POINTLESSQL_SERVER_HOST` | `127.0.0.1` | Uvicorn bind address.  Set to `0.0.0.0` in containers. |
| `POINTLESSQL_SERVER_PORT` | `8000` | HTTP port. |
| `POINTLESSQL_SERVER_BASE_URL` | `None` | Public URL used to build OIDC callbacks.  `None` = derive from the incoming request. |

## soyuz-catalog

Where to find the UC REST server.  Reads `POINTLESSQL_SOYUZ_*`.

| Variable | Default | Description |
|---|---|---|
| `POINTLESSQL_SOYUZ_CATALOG_URL` | `http://127.0.0.1:8080` | Base URL of the running `soyuz-catalog` server. |

## Database (own metadata DB)

PointlesSQL's *own* SQLAlchemy database — sessions, audit log,
agent_runs, lineage, scheduler state.  Reads
`POINTLESSQL_DB_*`.

| Variable | Default | Description |
|---|---|---|
| `POINTLESSQL_DB_URL` | `sqlite:///./pointlessql.db` | SQLAlchemy URL.  Use `postgresql+psycopg://...` for the Postgres mode (Phase 19.0.1). |

The Lakehouse metadata is owned by `soyuz-catalog`, never written
here directly.

## Auth

JWT signing + session lifetime.  Reads `POINTLESSQL_AUTH_*`.

| Variable | Default | Description |
|---|---|---|
| `POINTLESSQL_AUTH_SECRET_KEY` | `change-me-in-production` | JWT signing key.  Must be overridden in production. |
| `POINTLESSQL_AUTH_SECRET_KEY_PREVIOUS` | `None` | Optional grace-period key during rotation (verifies fall-through, never signs). |
| `POINTLESSQL_AUTH_JWT_EXPIRY_HOURS` | `168` (7 days) | Session lifetime. |

For the rotation procedure see
[`docs/concepts/auth.md`](../concepts/auth.md).

## OIDC

OpenID Connect single-sign-on (opt-in).  Reads
`POINTLESSQL_OIDC_*`.

| Variable | Default | Description |
|---|---|---|
| `POINTLESSQL_OIDC_DISCOVERY_URL` | `None` | Provider's `.well-known/openid-configuration` URL. |
| `POINTLESSQL_OIDC_CLIENT_ID` | `None` | OAuth client ID. |
| `POINTLESSQL_OIDC_CLIENT_SECRET` | `None` | OAuth client secret (omit for PKCE-only public clients). |
| `POINTLESSQL_OIDC_HTTP_TIMEOUT_SECONDS` | `10.0` | Discovery + token-exchange timeout. |

OIDC is **enabled** only when both `DISCOVERY_URL` and
`CLIENT_ID` are non-empty.

## Logging

Reads `POINTLESSQL_LOG_*`.

| Variable | Default | Description |
|---|---|---|
| `POINTLESSQL_LOG_LEVEL` | `INFO` | Python logging level (`DEBUG` / `INFO` / `WARNING` / `ERROR`). |
| `POINTLESSQL_LOG_FORMAT` | `text` | `text` (human-readable) or `json` (single-line per record, for log aggregators). |

## Rate limits

Fixed-window counters on `/auth/*`.  Reads
`POINTLESSQL_RATE_LIMIT_*`.

| Variable | Default | Description |
|---|---|---|
| `POINTLESSQL_RATE_LIMIT_ENABLED` | `True` | Master switch. |
| `POINTLESSQL_RATE_LIMIT_LOGIN_IP_COUNT` | `10` | Login attempts per IP per window. |
| `POINTLESSQL_RATE_LIMIT_LOGIN_IP_WINDOW_S` | `600` | Login per-IP window (10 min). |
| `POINTLESSQL_RATE_LIMIT_LOGIN_EMAIL_COUNT` | `5` | Login attempts per email per window. |
| `POINTLESSQL_RATE_LIMIT_LOGIN_EMAIL_WINDOW_S` | `600` | Login per-email window. |
| `POINTLESSQL_RATE_LIMIT_REGISTER_IP_COUNT` | `5` | Register attempts per IP per window. |
| `POINTLESSQL_RATE_LIMIT_REGISTER_IP_WINDOW_S` | `3600` | Register per-IP window (1 h). |
| `POINTLESSQL_RATE_LIMIT_OIDC_IP_COUNT` | `20` | OIDC callback attempts per IP per window. |
| `POINTLESSQL_RATE_LIMIT_OIDC_IP_WINDOW_S` | `600` | OIDC per-IP window. |
| `POINTLESSQL_RATE_LIMIT_TRUST_X_FORWARDED_FOR` | `False` | Trust the `X-Forwarded-For` header for client-IP detection.  Only set behind a known reverse proxy. |

## Jupyter / notebook executor

Reads `POINTLESSQL_JUPYTER_*`.

| Variable | Default | Description |
|---|---|---|
| `POINTLESSQL_JUPYTER_ENABLED` | `True` | Master switch for the embedded notebook editor + papermill executor. |
| `POINTLESSQL_JUPYTER_PORT` | `8888` | Reserved for future re-introduction; currently unused (Sprint 63 retired the iframe). |
| `POINTLESSQL_JUPYTER_NOTEBOOKS_DIR` | `notebooks` | Where `.py` jupytext notebooks live.  Resolved against startup CWD. |
| `POINTLESSQL_JUPYTER_RUNS_DIR` | `notebooks/runs` | Where papermill execution outputs land. |
| `POINTLESSQL_JUPYTER_EXECUTE_TIMEOUT_SECONDS` | `300` | Per-cell execution timeout. |

## Scheduler

In-process job scheduler.  Reads `POINTLESSQL_SCHEDULER_*`.

| Variable | Default | Description |
|---|---|---|
| `POINTLESSQL_SCHEDULER_ENABLED` | `True` | Master switch.  `conftest.py` flips it `False` so unit tests never tick. |
| `POINTLESSQL_SCHEDULER_TICK_SECONDS` | `30` | How often the scheduler picks up due jobs. |
| `POINTLESSQL_SCHEDULER_MAX_CONCURRENT_RUNS` | `4` | Global ceiling.  Per-job semaphore (`Job.max_parallel_runs`) layers on top. |

## Audit

Cleanup + cockpit.  Reads `POINTLESSQL_AUDIT_*`.

| Variable | Default | Description |
|---|---|---|
| `POINTLESSQL_AUDIT_RETENTION_DAYS` | `365` | Audit-log row TTL.  `0` = disable retention. |
| `POINTLESSQL_AUDIT_CLEANUP_INTERVAL_SECONDS` | `86400` | How often the cleanup tick runs (default once per day). |
| `POINTLESSQL_AUDIT_ANOMALY_BASELINE_WINDOW_DAYS` | `7` | Rolling window the anomaly endpoint compares against. |
| `POINTLESSQL_AUDIT_ANOMALY_THRESHOLD_SIGMA` | `2.0` | σ above mean = `warn`; 2σ × this = `critical`. |
| `POINTLESSQL_AUDIT_PII_MASK_DEFAULT` | `True` | Mask values flagged PII in soyuz tags.  See [PII modes](../concepts/pii-modes.md). |
| `POINTLESSQL_AUDIT_PII_CACHE_TTL_SECONDS` | `600` | TTL on the `(table, column) → PII` lookup cache. |
| `POINTLESSQL_AUDIT_PII_MODE` | `hash_only` | One of `store_clear` / `hash_only` / `redact_with_audit_log`. |
| `POINTLESSQL_AUDIT_PII_HASH_SECRET` | `None` | Required when `PII_MODE=hash_only`. |

### Lineage retention sub-keys

Reads `POINTLESSQL_AUDIT_LINEAGE_RETENTION_*`.  Each `_DAYS` is a
positive int, or `None` / `0` = never prune.

| Variable | Default | Description |
|---|---|---|
| `..._ROW_EDGES_DAYS` | `365` | Row-level lineage TTL. |
| `..._ROW_REJECTS_DAYS` | `365` | Rejects table TTL. |
| `..._COLUMN_MAP_DAYS` | `None` | Column-level lineage TTL.  Default never. |
| `..._VALUE_CHANGES_DAYS` | `730` | Value-level lineage TTL (longer; strongest forensic surface). |
| `..._CRON` | `0 3 * * *` | Pruner cron expression (default 03:00 UTC daily). |

## Delta engine

Reads `POINTLESSQL_DELTA_*`.

| Variable | Default | Description |
|---|---|---|
| `POINTLESSQL_DELTA_ENGINE` | `pandas` | Compute engine.  Reserved for future `polars` / `duckdb` / `daft`. |

## SQL editor

Reads `POINTLESSQL_SQL_*`.

| Variable | Default | Description |
|---|---|---|
| `POINTLESSQL_SQL_ENABLED` | `True` | Hides `/sql` and rejects `/api/sql/*` when `False`. |
| `POINTLESSQL_SQL_MAX_ROWS` | `10000` | Cap on `SELECT` LIMIT applied by DuckDB. |
| `POINTLESSQL_SQL_QUERY_TIMEOUT_SECONDS` | `60` | Aborts long-running queries. |
| `POINTLESSQL_SQL_COST_GATE_THRESHOLD_ROWS` | `1000000` | Phase 13.6: queries with EXPLAIN row estimate ≥ this need confirmation. |

## Agent-run lifecycle webhooks

Reads `POINTLESSQL_AGENT_RUNS_*`.

| Variable | Default | Description |
|---|---|---|
| `POINTLESSQL_AGENT_RUNS_WEBHOOK_URL` | `None` | POST target for `pointlessql.agent_run.*` CloudEvents. |
| `POINTLESSQL_AGENT_RUNS_WEBHOOK_HMAC_SECRET` | `None` | Optional HMAC-SHA-256 of the body, sent as `X-PointlesSQL-Signature: sha256=<hex>`. |

## Audit-stream forwarder

Phase 20.  Reads `POINTLESSQL_AUDIT_STREAM_*`.

| Variable | Default | Description |
|---|---|---|
| `POINTLESSQL_AUDIT_STREAM_ENABLED` | `False` | Master switch.  Sinks fire only when this AND at least one active row in `audit_sinks` exist. |
| `POINTLESSQL_AUDIT_STREAM_MIRROR_LIFECYCLE_TO_SINKS` | `False` | Also fan agent_run lifecycle CloudEvents into audit sinks. |

## External-write detection

Phase 14.3 scanner.  Reads `POINTLESSQL_EXTERNAL_WRITES_*`.

| Variable | Default | Description |
|---|---|---|
| `POINTLESSQL_EXTERNAL_WRITES_SCAN_INTERVAL_SECONDS` | `0` (disabled) | Cron-like scanner that walks `DeltaTable.history()` and INSERT-OR-IGNOREs into `unattributed_writes`.  On-demand admin route works regardless. |
| `POINTLESSQL_EXTERNAL_WRITES_HISTORY_LIMIT` | `200` | Max history rows scanned per table per tick. |

## Delta-branching

Phase 16.5.  Reads `POINTLESSQL_BRANCH_*`.

| Variable | Default | Description |
|---|---|---|
| `POINTLESSQL_BRANCH_CLOUD_STRATEGY` | `error` | One of `error` (refuse cloud branching) or `deep_copy` (opt into the bigger storage cost).  Local FS always uses symlink path. |
| `POINTLESSQL_BRANCH_AUTO_CLEANUP_ENABLED` | `False` | Opt-in scheduler job that discards old `status=active` branches. |
| `POINTLESSQL_BRANCH_AUTO_CLEANUP_RETENTION_DAYS` | `30` | Branches older than this get auto-discarded when cleanup is on. |
| `POINTLESSQL_BRANCH_AUTO_CLEANUP_CRON` | `0 2 * * *` | Cleanup cron (default 02:00 UTC daily). |

## Conventions (Medallion override)

Reads `POINTLESSQL_CONVENTIONS_*`.

| Variable | Default | Description |
|---|---|---|
| `POINTLESSQL_CONVENTIONS_PATH` | `None` | Path to a `pointlessql.yaml` whose top-level fields shallow-merge over the built-in [data-layers](../concepts/data-layers.md) defaults. |

## MLflow

Phase 21.0.  Reads `POINTLESSQL_MLFLOW_*`.

| Variable | Default | Description |
|---|---|---|
| `POINTLESSQL_MLFLOW_ENABLED` | `True` | Master switch for the embedded MLflow Tracking subprocess + reverse-proxy. |
| `POINTLESSQL_MLFLOW_PORT` | `5000` | Subprocess listen port. |
| `POINTLESSQL_MLFLOW_BACKEND_STORE_URI` | derived → `sqlite:///./mlflow.db` | MLflow backend store. |
| `POINTLESSQL_MLFLOW_ARTIFACT_ROOT` | derived → `file://{cwd}/mlflow_artifacts` | Where MLflow puts run artefacts. |
| `POINTLESSQL_MLFLOW_REGISTRY_URI` | derived → `uc:{soyuz_url}` | MLflow UC-OSS registry URI (Phase 21.1's `uc:` scheme, not `uc-oss:`). |

## Special agent-run env vars

Read by the `PQL` constructor and the plugin lifecycle hook,
not by `Settings`:

| Variable | Default | Description |
|---|---|---|
| `POINTLESSQL_AGENT_RUN_ID` | `None` | The session id PQL stamps onto every audit row.  Hermes plugin sets this per-turn via `lifecycle.pre_llm_call`. |
| `POINTLESSQL_API_KEY` | `None` | Bearer token for HTTP calls.  Mint with `pointlessql admin issue-auditor-key`. |
| `POINTLESSQL_SUPERVISOR_MODE` | `0` | `1` = plugin registers supervisor-gated tools at session start. |
| `POINTLESSQL_AUDITOR_MODE` | `0` | `1` = plugin registers auditor tools at session start. |
| `GHCR_PAT` | `None` | Used by the Docker quickstart for `docker login ghcr.io`. |

For the plugin-side env-var contract see
[`hermes-plugin-pointlessql/CLAUDE.md`](https://github.com/FloHofstetter/hermes-plugin-pointlessql/blob/main/CLAUDE.md)
when that repo is public.

## How settings get loaded

1. Each sub-model is constructed with `default_factory` so env
   vars are read at `Settings()` instantiation time, not class-
   definition time.  This matters under papermill — papermill
   does a process-wide `os.chdir` and re-instantiating
   `Settings` after the chdir surfaces the new CWD-relative
   paths cleanly.
2. Empty-string overrides count as "not configured".  The
   docker-compose `${VAR:-}` fallback makes empty strings the
   default on a clean install — code paths that probe whether
   a setting is "configured" use a truthy check, not
   `is None`.
3. Validators normalise paths to absolute form against the
   startup CWD (captured at module-import time, before any
   papermill tick).
