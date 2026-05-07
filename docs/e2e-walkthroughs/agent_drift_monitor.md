# Agent: Drift-Monitor walkthrough

> **Mode:** `hybrid` · **Phase:** 13.x · **Surface:** Notebook + /runs/{id}

**** — replay this playbook to verify the Drift-Monitor
agent end-to-end: a Hermes-style external runtime registers an
agent run, fires the `notebooks/agent_drift_monitor.py` notebook,
appends per-check rows to `ops.quality_history`, and emits a
CloudEvent when thresholds break. The replay exercises three
shipped primitives in one flow:

- **** registry routes (`POST /api/agent-runs`, `/finish`)
- **** CloudEvents envelope (`pointlessql.agent_run.*`)
- **** control-room `/runs` filter bar + detail card deck
- **** `X-Principal` header forwarded into the PQL
 session
- **** Medallion conformance check on `/runs/{id}`

This is **not** the Hermes-Medallion demo (that one
covers `pql.autoload` + `pql.merge` + a SQL aggregation through a
real Hermes process). Drift-Monitor is the lightweight second
demo: no new connector code, no new primitives — just supervision
+ the column-stats rails.

## Preconditions

1. PointlesSQL is running on `http://127.0.0.1:8000` with the
.x routes (`/api/agent-runs`, `/api/sql/explain`,
 `/runs`, `/runs/{id}`).
2. soyuz-catalog is reachable at the configured URL.
3. A bronze table exists at `main.bronze.events` with the audit
 columns from (`_ingested_at` / `_source_file` /
 `_source_system`). The Hermes-Medallion walkthrough
 creates one — replay that first if needed.
4. An admin account is logged in via cookie (the approval panel
 only shows for admins).
5. **Optional** but recommended: a webhook receiver listens on a
 localhost port and the env var
 `POINTLESSQL_AGENT_RUNS_WEBHOOK_URL` points at it. Without
 this the CloudEvent emission step is a debug-level no-op.

## Step 1 — Register the agent run

In a terminal (or via Hermes's `register_run` lifecycle hook):

```bash
RUN_ID=$(uuidgen)
curl -s -X POST http://127.0.0.1:8000/api/agent-runs \
 -H 'Content-Type: application/json' \
 -H 'X-Principal: drift-monitor@ops.local' \
 -d "{\"id\": \"$RUN_ID\",
 \"agent_id\": \"drift_monitor\",
 \"notebook_path\": \"agent_drift_monitor.py\",
 \"status\": \"running\",
 \"tables_touched\": [\"main.bronze.events\", \"main.ops.quality_history\"]}"
```

**Expected**: HTTP 200, JSON echo of the created row, the audit
log gains a `create_agent_run` entry attributed to
`drift-monitor@ops.local` (the `X-Principal` value, not the
session-cookie user — ).

If `POINTLESSQL_AGENT_RUNS_WEBHOOK_URL` is set, the receiver
gets a `pointlessql.agent_run.started` envelope with the same
data shape.

## Step 2 — Run the notebook

In a separate terminal:

```bash
export POINTLESSQL_AGENT_RUN_ID="$RUN_ID"
export POINTLESSQL_PRINCIPAL="drift-monitor@ops.local"
export MONITOR_TARGET="main.bronze.events"
export MONITOR_NULL_RATE_MAX="0.20"
export MONITOR_FRESHNESS_MAX_H="24"
uv run jupytext --execute notebooks/agent_drift_monitor.py
```

**Expected**: stdout shows
- `Read N rows from main.bronze.events`
- `Findings: K`
- `Appended K row(s) to main.ops.quality_history`
- `Emitted.failed CloudEvent for K breach(es)` *or*
 `No breaches — staying quiet`

If the notebook raises `AuthorizationError`, `drift-monitor@ops.local`
lacks SELECT on `main.bronze.events` — grant it via soyuz then
retry.

## Step 3 — Terminate the run

```bash
curl -s -X POST http://127.0.0.1:8000/api/agent-runs/$RUN_ID/finish \
 -H 'Content-Type: application/json' \
 -d '{"status": "succeeded", "exit_code": 0}'
```

**Expected**: HTTP 200, terminal row, second CloudEvent
(`pointlessql.agent_run.completed`) on the webhook receiver.

## Step 4 — Verify in the control-room (Firefox via Playwright MCP)

```text
mcp__playwright__browser_navigate url: http://127.0.0.1:8000/runs
mcp__playwright__browser_snapshot
```

**Expected**: the new row appears at the top with status
`succeeded`, principal `drift-monitor@ops.local`, agent
`drift_monitor`, and `tables_touched` showing both the bronze
and ops tables as catalog-link badges.

Type `drift` in the filter bar — the row stays visible
(matched `agent_id`). Click the **Failed** chip — the row
hides. Click **Succeeded** — the row reappears.

## Step 5 — Drill into the detail page

```text
mcp__playwright__browser_click ref: row link with run id
mcp__playwright__browser_snapshot
```

**Expected** on `/runs/{run_id}`:

- **Run metadata** card lists Principal `drift-monitor@ops.local`,
 Agent `drift_monitor`, and Tables-touched as two clickable
 badges.
- **Medallion conformance** card — if the bronze
 table is missing any of the three audit columns, an `error`
 finding lists the missing one. Otherwise the card is hidden
 (no findings).
- **Audit log** card lists three rows: `create_agent_run`,
 `finish_agent_run`, and (if any conformance check fired) the
 related row. All attributed to `drift-monitor@ops.local`.
- **No approval panel** — the run is `succeeded`, not
 `needs_approval`.

## Step 6 — Inspect the appended quality-history rows

```bash
curl -s 'http://127.0.0.1:8000/api/sql/execute' \
 -H 'Content-Type: application/json' \
 -H 'X-Principal: drift-monitor@ops.local' \
 -d '{"sql": "SELECT * FROM main.ops.quality_history ORDER BY checked_at DESC LIMIT 5"}'
```

**Expected**: the latest rows from this run, one per check.
's principal forwarding means the audit log shows
`drift-monitor@ops.local` as the actor on the query, not the
cookie user.

## Step 7 — Verify the CloudEvent payload (optional)

If a webhook receiver is configured, its log should show two
envelopes:

```json
{
 "specversion": "1.0",
 "type": "pointlessql.agent_run.started",
 "source": "/pointlessql/agent_runs/<RUN_ID>",
 "subject": "<RUN_ID>",
 "data": { "principal": "drift-monitor@ops.local", "status": "running", … }
}
```

```json
{
 "specversion": "1.0",
 "type": "pointlessql.agent_run.completed",
 "source": "/pointlessql/agent_runs/<RUN_ID>",
 "subject": "<RUN_ID>",
 "data": { "status": "succeeded", "exit_code": 0, … }
}
```

If `MONITOR_NULL_RATE_MAX` was set low enough that a check
fired (or if the bronze table is genuinely stale), a third
envelope of type `pointlessql.agent_run.failed` arrives —
that one carries the `breaches` list in `data` for the
subscriber to ticket / Slack-notify.

## Playwright MCP script

Browser-only verifications for the run-detail surfaces (the
notebook + curl preamble stays as prose above):

1. `browser_navigate('http://127.0.0.1:8000/runs')`
   — assert the latest row is the agent-drift-monitor synthetic
   run.
2. `browser_click("td a:first")` — URL becomes `/runs/<id>`.
3. `browser_evaluate('() => document.querySelector(".conformance-card .badge").innerText')`
   — assert it reads `BREACH` (the drift demo seeds a breach).
4. `browser_click("Operations")` (top tab) — assert ≥ 1
   `pql.write_table` op row.
5. `browser_evaluate('() => Array.from(document.querySelectorAll(".tables-touched-chip")).map(n => n.innerText)')`
   — assert array contains `ops.quality_history`.
6. `browser_evaluate('() => document.querySelector("[data-attribution=x-principal]").innerText')`
   — assert non-empty (X-Principal-forwarded identity).
7. `browser_evaluate('() => fetch("/api/agent-runs?limit=1").then(r => r.json())')`
   — assert the latest run has `kind` matching the drift-monitor
   axis.
8. `browser_navigate('http://127.0.0.1:8000/audit/inbox')`
   — assert the drift breach is visible as an anomaly row with
   the matching run-id.

## Cleanup

```bash
# Drop just this run's history rows; keep the run row + audit
curl -s -X POST 'http://127.0.0.1:8000/api/sql/execute' \
 -H 'Content-Type: application/json' \
 -d "{\"sql\": \"DELETE FROM main.ops.quality_history WHERE target_table = 'main.bronze.events'\"}"
```

Or simply: leave the run + history in place and re-run later.
The Drift-Monitor flow is idempotent across runs (each
invocation appends rather than replacing).
