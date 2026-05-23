# External SQL Statement Execution API walkthrough

Phase 117 ships PointlesSQL's first **token-authenticated public
REST surface**: a Databricks-compatible SQL Statement Execution API
that lets external clients (curl, dbt, BI tools, application
backends) run SELECT queries against the lakehouse without driving
the browser UI.

This playbook covers:

1. Minting an `sql_execute`-scoped API key.
2. Sync happy-path with curl.
3. Async submission + poll cycle.
4. Cancel mid-flight.
5. Typed parameter binding.
6. Default-catalog / default-schema rewrite.
7. Common failure shapes (auth, parse, permission, rate-limit).
8. Compatibility with the official `databricks-sql-python` client.

## Prerequisites

- PointlesSQL running on `http://127.0.0.1:8000` (e.g.
  `uv run pointlessql`).
- soyuz-catalog reachable per the `POINTLESSQL_SOYUZ_CATALOG_URL`
  env var.
- An admin session cookie in your browser (visit `/admin/api-keys`
  to mint Bearer tokens), or admin credentials for the CLI seed
  path described below.

## 1. Mint an `sql_execute` Bearer token

Two paths:

**Admin UI:** `/admin/api-keys` → *Create* → check the
**SQL Execute** scope checkbox → copy the plaintext secret shown
once.

**Env-var bootstrap** (clean-machine / CI):

```bash
export POINTLESSQL_API_KEYS="bi-readonly:s3cr3t-bi-token-xyz:sql_execute"
uv run pointlessql
```

The server idempotently spills declared `name:secret:scope` pairs
into the `api_keys` table on startup.

**Programmatic seed** (admin Python REPL):

```python
from pointlessql.api.main import app
from pointlessql.services.api_keys import create_api_key

row, plaintext = create_api_key(
    app.state.session_factory,
    name="dbt-runner",
    sql_execute=True,
)
print(plaintext)  # → only shown once; persist somewhere safe
```

Verify the scope:

```bash
curl -sS -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/2.0/sql/statements \
  -d '{"statement": "SELECT 1"}' \
  -H "Content-Type: application/json" | jq .status.state
# → "SUCCEEDED" (or "FAILED" with PERMISSION_DENIED if grants are missing)
```

A 403 from this call means the key lacks `sql_execute`. A 401 means
the bearer token doesn't resolve to any key — re-check the value.

## 2. Sync happy-path

```bash
TOKEN="..."
curl -sS -X POST http://127.0.0.1:8000/api/2.0/sql/statements \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "statement": "SELECT id, name FROM main.sales.orders ORDER BY id LIMIT 10",
    "wait_timeout": "10s"
  }' | jq .
```

Expected response shape (truncated):

```json
{
  "statement_id": "1f5d…",
  "status": { "state": "SUCCEEDED" },
  "manifest": {
    "format": "JSON_ARRAY",
    "schema": { "column_count": 2, "columns": [...] },
    "total_row_count": 10,
    "total_chunk_count": 1,
    "chunks": [{"chunk_index": 0, "row_offset": 0, "row_count": 10}]
  },
  "result": {
    "chunk_index": 0,
    "row_offset": 0,
    "row_count": 10,
    "data_array": [["1", "alpha"], ["2", "beta"], ...]
  }
}
```

Numerics are serialised as JSON strings to preserve precision (the
official DBX adapters do the same).

## 3. Async submission + poll

When `wait_timeout` elapses before the query completes (default
`10s`), the server returns a PENDING envelope:

```bash
curl -sS -X POST .../sql/statements \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"statement": "SELECT count(*) FROM main.huge.fact",
       "wait_timeout": "1s",
       "on_wait_timeout": "CONTINUE"}'
# → { "statement_id": "abc-…", "status": {"state": "PENDING"} }

SID="abc-…"
sleep 2
curl -sS -H "Authorization: Bearer ${TOKEN}" \
  http://127.0.0.1:8000/api/2.0/sql/statements/${SID} | jq .
# → eventually returns the same SUCCEEDED envelope as the sync call.
```

`on_wait_timeout=CANCEL` would have aborted the in-flight statement
instead of leaving it running.

Single-chunk fetch (v1 always returns exactly one chunk):

```bash
curl -sS -H "Authorization: Bearer ${TOKEN}" \
  http://127.0.0.1:8000/api/2.0/sql/statements/${SID}/result/chunks/0
# → just the {"chunk_index", "row_offset", "row_count", "data_array"} sub-object
```

## 4. Cancel mid-flight

```bash
curl -sS -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  http://127.0.0.1:8000/api/2.0/sql/statements/${SID}/cancel
# → { "statement_id": "...", "status": {"state": "CANCELED"} }
```

Cancel is best-effort: an already-completed statement returns its
current envelope (idempotent no-op); an in-flight one interrupts the
underlying DuckDB connection.

## 5. Typed parameter binding

```bash
curl -sS -X POST .../sql/statements \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{
    "statement": "SELECT * FROM main.sales.orders WHERE region = :region AND amount > :floor",
    "parameters": [
      {"name": "region", "value": "EU", "type": "STRING"},
      {"name": "floor",  "value": 100,  "type": "INT"}
    ]
  }'
```

Supported types: `STRING`, `INT`, `LONG`, `DOUBLE`, `FLOAT`,
`BOOLEAN`, `DATE` (ISO 8601), `TIMESTAMP` (ISO 8601), `NULL`.

`DECIMAL` deferred to v2 — wrap as STRING for now if you need exact
precision.

Binding goes through sqlglot AST substitution so injection-via-
parameter is structurally impossible: a string like
`EU'); DROP TABLE x; --` survives as one quoted literal, not two
statements.

## 6. Default catalog / schema

```bash
# 1-part table ref qualified server-side
curl -sS -X POST .../sql/statements \
  -d '{
    "statement": "SELECT id FROM orders LIMIT 5",
    "catalog": "main",
    "schema": "sales"
  }'

# 2-part ref + catalog default
curl -sS -X POST .../sql/statements \
  -d '{
    "statement": "SELECT id FROM sales.orders LIMIT 5",
    "catalog": "main"
  }'
```

3-part refs pass through unchanged. When the request omits the
defaults, the existing 3-part requirement still applies.

## 7. Failure envelopes

Everything below returns HTTP 200 with a FAILED `status.state` —
the wire shape matches DBX exactly so the existing client adapters
detect failures via `status.error.error_code`.

| Trigger                              | `error_code`              |
|--------------------------------------|---------------------------|
| Malformed SQL                        | `SQL_PARSE_ERROR`         |
| Non-SELECT (DML / DDL in v1)         | `INVALID_PARAMETER_VALUE` |
| Caller lacks UC SELECT on a table    | `PERMISSION_DENIED`       |
| Table unknown to soyuz               | `RESOURCE_NOT_FOUND`      |
| Per-key budget exceeded              | `REQUEST_LIMIT_EXCEEDED` (HTTP 429) |
| API disabled by operator             | `WORKSPACE_TEMPORARILY_UNAVAILABLE` (HTTP 503) |

HTTP-level errors (400 / 401 / 403 / 404 / 429 / 503) carry a JSON
body with the same `error_code` + `message` shape as the FAILED
envelope so client code can use one detection path.

## 8. Compatibility with `databricks-sql-python`

PointlesSQL implements the same wire shape as the official DBX SQL
Statement Execution API, so swapping the base URL works:

```python
import os, httpx

token = os.environ["POINTLESSQL_BEARER"]
client = httpx.Client(
    base_url="http://127.0.0.1:8000",
    headers={"Authorization": f"Bearer {token}"},
)
resp = client.post(
    "/api/2.0/sql/statements",
    json={"statement": "SELECT 1 AS one"},
)
print(resp.json()["status"]["state"])  # → SUCCEEDED
```

The official `databricks-sql-python` connector has not been
verified end-to-end yet — known compat gaps are tracked in the
phase-117 ROADMAP entry as `BUG-117-Xn` items.

## Operator notes

- **Per-key rate limit**: 60 statements/minute by default. Tune via
  `POINTLESSQL_RATE_LIMIT_SQL_STATEMENTS_APIKEY_COUNT` /
  `_WINDOW_S`.
- **Result retention**: SUCCEEDED envelopes linger 24h in
  `sql_statements.result_payload`. Tune via
  `POINTLESSQL_SQL_EXECUTION_API_RESULT_PAYLOAD_RETENTION_HOURS`.
- **Wait timeout cap**: client `wait_timeout` is clamped to
  `POINTLESSQL_SQL_EXECUTION_API_MAX_WAIT_TIMEOUT_SECONDS` (50s
  default — matches DBX).
- **Row-limit cap**: client `row_limit` is clamped to
  `POINTLESSQL_SQL_EXECUTION_API_MAX_ROW_LIMIT` (100k default).
- **Disable in incident**: flip
  `POINTLESSQL_SQL_EXECUTION_API_ENABLED=0` (every call returns
  503 with `WORKSPACE_TEMPORARILY_UNAVAILABLE`).

## Out of scope for v1

- DML / DDL (Phase 117 is SELECT-only; DML lands in Phase 118 with
  the approval-flow integration).
- `format=ARROW_STREAM` (rejected with 400).
- `disposition=EXTERNAL_LINKS` (rejected with 400; would need S3 /
  MinIO).
- Chunked pagination (single chunk only).
- Per-key catalog / schema allowlists.
- DECIMAL parameter type.
- Long-poll on GET.
- Arrow Flight SQL, JDBC / ODBC, Postgres wire protocol.
