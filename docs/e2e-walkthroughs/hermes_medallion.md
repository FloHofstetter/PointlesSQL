# Hermes-Medallion walkthrough

**** — closes + 13.5. Replay this
playbook to verify a real Hermes agent (running in its own
sandbox) authors a three-layer Medallion lakehouse from a CSV
in a UC Volume, with the full forced audit trail
visible in `/runs/{id}`.

This is the ** done moment**: the first reproducible
end-to-end flow where an agent — not a human — writes the
bronze / silver / gold transformations.

The walkthrough exercises every primitive + 13.5 + 13.7
shipped in one run:

| Layer | Primitive | Sprint |
| --- | --- | --- |
| Lifecycle | `POST /api/agent-runs` strict + Bearer | 13.2 + 13.7.0.5 + 13.8 |
| Compute | `pql.autoload` / `pql.merge` / `pql.sql` | 13.5.2 + 13.5.3 |
| Conventions | `pointlessql.yaml` + audit columns | 13.5.1 |
| Trace | `agent_run_operations` + `agent_run_sources` | 13.8 |
| Queries | `query_history.agent_run_id` | 13.9 |
| LLM tools | `pql_*` tools + `agent_run_tool_calls` | 13.7.2 + 13.7.3 + 13.7.4 |
| CloudEvents | `pointlessql.agent_run.{started,completed,tool_call}` | 13.3 + 13.7.4 |
| Conformance | per-layer contract on `/runs/{id}` | 13.5.4 |

## Preconditions

1. **PointlesSQL** running on `http://127.0.0.1:8000` with the
.x routes (`/api/agent-runs`, `/api/sql/*`,
 `/runs/{id}`, `/api/conventions`).
2. **soyuz-catalog** reachable at the URL pointed to by
 `POINTLESSQL_SOYUZ_CATALOG_URL` (default
 `http://127.0.0.1:8080`). The Medallion schemas
 (`main.bronze`, `main.silver`, `main.gold`) must already
 exist with their `storage_root` set — UC semantics make
 `storage_root` set-on-create only, so a schema that was
 created without one cannot be patched later (
 doc-fix in soyuz `docs/reference/api.md`). Either create
 them in the catalog browser with the storage-root field
 filled in, or shell-script it:
 ```bash
 for layer in bronze silver gold; do
 curl -fsS -X POST "$POINTLESSQL_SOYUZ_CATALOG_URL/api/2.1/unity-catalog/schemas" \
 -H 'Content-Type: application/json' \
 -d "{\"name\": \"$layer\", \"catalog_name\": \"main\",
 \"storage_root\": \"file:///tmp/pql_demo_warehouse/$layer\"}"
 done
 ```
 If a schema already exists without `storage_root`,
 `DELETE` it first (PATCH is rejected by design).
3. **Hermes** installed (`~/git/hermes-agent` clone) with the
 `hermes-plugin-pointlessql` symlinked under
 `${HERMES_HOME:-$HOME/.hermes}/plugins/pointlessql/`:
 ```bash
 ln -s ~/git/hermes-plugin-pointlessql \
 "${HERMES_HOME:-$HOME/.hermes}/plugins/pointlessql"
 ```
4. **API-key gate** — set `POINTLESSQL_API_KEYS` on the
 PointlesSQL side before launch and `POINTLESSQL_API_KEY` on
 the Hermes side so the Bearer hop matches. Skip if you are
 running on a single-user dev box and want to demo the
 gate-disabled fallback.
5. The CSV fixture `notebooks/hermes_medallion_data/orders.csv`
 ships in-tree. No external download.
6. Admin account logged in via cookie (the run-detail tabs need
 admin to render the approval panel; reads work for any user).

## Step 0 — Set the env Hermes will inherit

```bash
export POINTLESSQL_BASE_URL="http://127.0.0.1:8000"
export POINTLESSQL_API_KEY="$YOUR_BEARER_TOKEN" # matches POINTLESSQL_API_KEYS
export POINTLESSQL_PRINCIPAL="alice@example.com" # human attribution
export HERMES_TASK_FILE="$(pwd)/notebooks/hermes_medallion.py"
export MEDALLION_CATALOG="main"
export MEDALLION_VOLUME_PATH="$(pwd)/notebooks/hermes_medallion_data"
```

The plugin's `on_session_start` hook turns these into a
strict-POST `/api/agent-runs` registration with the verbatim
`hermes_medallion.py` bytes as `source`.

## Step 1 — Start a Hermes session

In a Hermes shell:

```text
hermes> Build a Medallion lakehouse from the orders CSV under
 ${MEDALLION_VOLUME_PATH}.

 First read pql_conventions() so you follow the audit-column
 and tag rules. Then run notebooks/hermes_medallion.py via
 the terminal tool. When it finishes, summarise the three
 new tables.
```

**Expected** (per the four supervision levels):

- `agent_runs` row created at the start (status `queued`),
 `agent_run_sources` row carries the notebook bytes, the source
 SHA matches `sha256 notebooks/hermes_medallion.py`.
- `agent_run_tool_calls` rows for each LLM exploration tool
 (`pql_conventions`, possibly `pql_list_tables`, `pql_get_table`).
- `agent_run_operations` rows for each PQL primitive
 (`autoload`, `merge`, `sql`) with input SHA + Delta version
 pre/post.
- `query_history` rows for any ad-hoc `pql_query` calls plus the
 internal SQL inside `pql.sql(...)`.
- `agent_run_events` rows for `started`, `tool_call` (one per
 pql_* call), and `completed`.

## Step 2 — Verify in the run-detail view

Open `http://127.0.0.1:8000/runs/<run_id>` in Firefox (the
PointlesSQL Playwright config pins `--browser firefox` per
`CLAUDE.md`). Walk the tabs in this order:

1. **Source** — confirm the SHA matches the on-disk file. The
 bytes shown are immutable: editing
 `notebooks/hermes_medallion.py` after the run does not
 change what this tab renders.
2. **Operations** — three rows in order: `autoload`, `merge`,
 `sql`. Each row carries `input_sha`,
 `delta_version_before`, `delta_version_after`, and
 `rows_affected`.
3. **Tool calls** — chronological list of `pql_*` tool
 invocations. At minimum the LLM should have called
 `pql_conventions` once before writing.
4. **Queries** — every SQL the LLM (or the `pql.sql` primitive)
 ran, with full `sql_text` + `referenced_tables` linked back
 to this run via the `agent_run_id` column.
5. **Conformance** — bronze passes (audit columns present),
 silver passes (primary key on `order_id`), gold passes
 (narrow). No `error` markers.

## Step 3 — Verify column statistics populated

The stats should appear on each layer's catalog page:

- `/catalogs/main/schemas/bronze/tables/orders_raw` — column
 list shows `order_id`, `customer_id`, `product`, `qty`,
 `unit_price`, `placed_at` plus the audit columns
 (`_ingested_at`, `_source_file`, `_source_system`).
- `/catalogs/main/schemas/silver/tables/orders` — same columns
 but typed (qty `BIGINT`, unit_price `DOUBLE`, placed_at
 `TIMESTAMP_NTZ`).
- `/catalogs/main/schemas/gold/tables/orders_summary` — three
 columns: `placed_day`, `product`, `units_sold`, `revenue`.

## Step 4 — Verify CloudEvents (optional)

If you set `POINTLESSQL_AGENT_RUNS_WEBHOOK_URL` to a localhost
receiver (e.g. `nc -lk 7000`), confirm it received:

- one `pointlessql.agent_run.started`
- one `pointlessql.agent_run.tool_call` per `pql_*` tool call
- one `pointlessql.agent_run.completed`

Each envelope is `application/cloudevents+json`; the `subject`
field carries the run id.

## Step 5 — Cleanup (optional)

```bash
curl -s -H "Authorization: Bearer $POINTLESSQL_API_KEY" \
 "http://127.0.0.1:8000/api/agent-runs?limit=1" | jq

# Drop the demo tables (admin only; bypass UC client for speed)
duckdb -c "DROP TABLE main.bronze.orders_raw"
duckdb -c "DROP TABLE main.silver.orders"
duckdb -c "DROP TABLE main.gold.orders_summary"
```

Or leave them in place — re-running the playbook is idempotent
( SHA-based dedup on autoload, upsert
on merge, `CREATE OR REPLACE` on gold).

## Replaying via Playwright MCP

The browser-side verification (Step 2) is replayable via the
`mcp__playwright__browser_*` tools. Sequence:

```text
mcp__playwright__browser_navigate http://127.0.0.1:8000/auth/login
mcp__playwright__browser_fill_form { email, password }
mcp__playwright__browser_click "Login"
mcp__playwright__browser_navigate http://127.0.0.1:8000/runs
mcp__playwright__browser_click "<run row>"
mcp__playwright__browser_snapshot
mcp__playwright__browser_click "Operations"
mcp__playwright__browser_snapshot
mcp__playwright__browser_click "Tool calls"
mcp__playwright__browser_snapshot
mcp__playwright__browser_click "Queries"
mcp__playwright__browser_snapshot
mcp__playwright__browser_click "Conformance"
mcp__playwright__browser_snapshot
```

If Firefox fails to launch with `process did exit: exitCode=0`,
clear the stale lock per the `CLAUDE.md` Playwright note.

## Known follow-ups

- **No `pql_run_notebook` tool**. Per
 `feedback_cells_vs_operations_for_agents.md`, agent-authored
 runs are plain `.py`; Hermes' own `terminal` tool executes
 them. PointlesSQL has no opinion on which subprocess shape
 Hermes uses.
- **Tier-3 audit gaps** stay open (soyuz UC mutation
 cross-reference, read-audit, cost-gate EXPLAIN snapshot).
 See `project_phase13_audit_gaps.md`; + shoreguard
 provenance log layers on top.
