# Sprint 13.11 — Reflexive supervision tools walkthrough

**Phase 13 close-out replay.** This playbook proves the five
sub-sprints of Sprint 13.11 actually close the read-loop the
2026-04-25 walkthrough surfaced — three bugs in that demo all
shared one root cause (no tool to *check state* before *acting*).
Replay this end-to-end after touching anything in
`pointlessql/api/pql_introspect_routes.py`,
`pointlessql/api/agent_runs_routes.py`,
`pointlessql/services/api_keys.py`, or the Hermes plugin's
`tools/` dir.

The playbook is **API-centric on purpose**: the new routes are
HTTP, so a curl + Firefox-via-Playwright-MCP pair can replay the
whole arc without booting a real Hermes process. The
`post_tool_call` hook is simulated by direct
`POST /api/agent-runs/{id}/tool-call` calls — same DB rows, same
CloudEvent emission as Hermes would produce.

## Why each tool exists

The 2026-04-25 Hermes-Medallion live replay surfaced three bugs
([`docs/e2e-walkthroughs/hermes_medallion.md`](hermes_medallion.md)
captures the original session). Each Sprint-13.11 tool answers
one of them:

| 2026-04-25 bug | Tool that would have caught it | Sprint |
| --- | --- | --- |
| `pql.autoload(source=...)` was wrong — kwarg is `source_path` | `pql_describe_primitive("autoload")` returns the real signature | 13.11.1 |
| `pql.merge(...)` knalled because target didn't exist | `pql_target_state("main.silver.orders")` returns `exists=False` | 13.11.2 |
| `pql.sql("CREATE OR REPLACE TABLE …")` — `pql.sql` is SELECT-only | `pql_describe_primitive("sql")` shows the constraint | 13.11.1 |

Plus four supervisor tools (Family B) that walk cross-run
history — gated by an `api_keys.supervisor=True` row.

## Preconditions

1. **soyuz-catalog** running on `:8080`
   (`uv run uvicorn soyuz_catalog.api.main:create_app --factory --host 127.0.0.1 --port 8080`).
2. **PointlesSQL** running on `:8000` with two seeded API keys —
   one normal, one supervisor:
   ```bash
   POINTLESSQL_API_KEYS="dev:devkey-secret-32-bytes-or-longer-here, sup:supkey-secret-32-bytes-or-longer:supervisor" \
     uv run pointlessql
   ```
   Bootstrap log line should read
   `Bootstrapped 2 API keys from POINTLESSQL_API_KEYS` — that's
   the Sprint-13.11.4a seed-into-DB hook proving itself.
3. The `main.silver.orders` table exists from a prior Medallion
   walkthrough replay (any 13.5.5-style run leaves it). The
   `recent_failures` + `lineage` checks below assume it.
4. Firefox-via-Playwright-MCP for the browser legs (see the
   Sprint-22 backstory in [`docs/e2e-walkthroughs/README.md`](README.md);
   never the system Chrome channel — bundled `chrome-for-testing`
   or `--browser firefox` only).

## 0. Sanity check — gate is open

```bash
curl -sf http://127.0.0.1:8000/healthz
curl -sf http://127.0.0.1:8080/healthz
```

Both return `200`. PointlesSQL boot log carries
`Bootstrapped 2 API keys from POINTLESSQL_API_KEYS`. If you see
`0` keys, re-export `POINTLESSQL_API_KEYS` and restart — boot
hook is idempotent so re-running with the same env is a no-op
on already-present rows.

## 1. Family A pair 1 — `pql_describe_primitive`

```bash
curl -sf http://127.0.0.1:8000/api/pql/primitives \
  -H "Authorization: Bearer devkey-secret-32-bytes-or-longer-here" \
  | python3 -m json.tool | head -40
```

Expected: five entries — `table`, `sql`, `write_table`, `merge`,
`autoload`. The `autoload.signature` field carries
`source_path: 'str'` — that's the **bug 1 catch**: the LLM that
typed `source=` would have read this and switched to
`source_path=` in one round-trip.

## 2. Family A pair 1 — `pql_my_run`

Seed a run with the same shape as the 2026-04-25 buggy attempt —
the agent was about to merge into a table that didn't exist:

```bash
RUN_A="11111111-aaaa-1111-aaaa-111111111111"
curl -sf -X POST http://127.0.0.1:8000/api/agent-runs \
  -H "Authorization: Bearer devkey-secret-32-bytes-or-longer-here" \
  -H "X-Principal: alice@example.com" \
  -H "Content-Type: application/json" \
  -d "$(cat <<JSON
{
  "id": "$RUN_A",
  "notebook_path": "demo/run_a.py",
  "agent_id": "hermes-demo",
  "source": "# would-have-failed run\nimport pql\npql.PQL().merge(df, 'main.silver.orders', on=['id'])\n",
  "runtime_versions": {"python": "3.14.0", "hermes": "v1"}
}
JSON
)"
```

Now hit the `/full` aggregator — the route `pql_my_run` wraps:

```bash
curl -sf "http://127.0.0.1:8000/api/agent-runs/$RUN_A/full" \
  -H "Authorization: Bearer devkey-secret-32-bytes-or-longer-here" \
  | python3 -m json.tool | head -25
```

Expected keys: `run`, `source`, `operations`, `tool_calls`,
`events`, `queries`. `events` already carries the `started`
CloudEvent emitted by Sprint 13.3.

## 3. Family A pair 2 — `pql_target_state` (the merge-fail catch)

```bash
curl -sf "http://127.0.0.1:8000/api/pql/target-state?table=main.silver.demo_does_not_exist_13_11" \
  -H "Authorization: Bearer devkey-secret-32-bytes-or-longer-here" \
  -H "X-Principal: alice@example.com"
```

Expected:

```json
{"table": "main.silver.demo_does_not_exist_13_11",
 "exists": false, "schema": null, "last_5_writes": []}
```

**Bug 2 catch.** `exists=false` is the signal that `pql.merge`
will explode — pick `write_table` or `pql.autoload` for
bootstrap instead.

For an existing table the same call returns the schema (trimmed
to `name/type_text/nullable/comment`) and the latest five
operations targeting it:

```bash
curl -sf "http://127.0.0.1:8000/api/pql/target-state?table=main.silver.orders" \
  -H "Authorization: Bearer devkey-secret-32-bytes-or-longer-here" \
  -H "X-Principal: alice@example.com" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('exists:', d['exists']); print('cols:', [c['name'] for c in d['schema']]); print('last writes:', len(d['last_5_writes']))"
```

## 4. Family A pair 2 — `pql_recent_failures`

```bash
curl -sf "http://127.0.0.1:8000/api/agent-runs/operations?errored=true&since=2026-01-01T00:00:00Z&limit=5" \
  -H "Authorization: Bearer devkey-secret-32-bytes-or-longer-here"
```

Empty `operations: []` is the happy path — no run has hit a
PQL error against any target inside the lookback. Add a
`target=…` filter to scope to one table.

## 5. Family A — `pql_lineage`

```bash
curl -sf "http://127.0.0.1:8000/api/pql/lineage?table=main.silver.orders&depth=2" \
  -H "Authorization: Bearer devkey-secret-32-bytes-or-longer-here" \
  -H "X-Principal: alice@example.com" \
  | python3 -m json.tool | head -30
```

Returns `{table, depth, upstream, downstream}` — each side
mirrors the soyuz `LineageGraphResponse` shape (`{root,
direction, nodes, edges}`). Cap is `depth=5` server-side; bigger
values 422 via `Query(le=5)`.

## 6. Simulate a tool-call hook fire

`post_tool_call` from Hermes posts here for any `pql_*` tool.
We simulate one:

```bash
curl -sf -X POST "http://127.0.0.1:8000/api/agent-runs/$RUN_A/tool-call" \
  -H "Authorization: Bearer devkey-secret-32-bytes-or-longer-here" \
  -H "Content-Type: application/json" \
  -d '{"tool_name": "pql_describe_primitive",
       "args_json": "{\"name\":\"merge\"}",
       "result_summary": "{\"found\":true,\"signature\":\"merge(self, source, target, *, on, strategy=upsert)\"}",
       "duration_ms": 3}'
```

Re-run the `/full` aggregator from §2 — `tool_calls` is now
length 1 with the new entry. The Sprint-13.10 run-detail
template surfaces this in its **Tool calls** tab (browser leg,
§9 below).

## 7. Family B — DB-backed admin CRUD for API keys

The supervisor key was bootstrapped from env. To prove the
admin CRUD path also works (Sprint 13.11.4a), open the browser
(see §9) and POST a fresh key by hand, OR drive it via curl —
this leg requires a **cookie session** since admin routes are
gated by `require_admin`:

```bash
# expect 403 from a Bearer key (admin CRUD is cookie-only)
curl -s -o /dev/null -w "bearer→admin status=%{http_code}\n" \
  http://127.0.0.1:8000/api/admin/api-keys \
  -H "Authorization: Bearer supkey-secret-32-bytes-or-longer"
# bearer→admin status=403
```

That's the deliberate split: Family-B *reads* are Bearer-keyed,
admin *writes* are cookie-only. Browse to `/api/admin/api-keys`
in the §9 browser leg with the admin cookie session for the
happy path.

## 8. Family B — supervisor scope vs normal key

```bash
RUN_A="11111111-aaaa-1111-aaaa-111111111111"

# Normal key → 403 (no supervisor scope)
curl -s -o /dev/null -w "dev→summary status=%{http_code}\n" \
  "http://127.0.0.1:8000/api/agent-runs/$RUN_A/summary" \
  -H "Authorization: Bearer devkey-secret-32-bytes-or-longer-here"
# dev→summary status=403

# Supervisor key → 200 + risk summary (no cost_gate_threshold!)
curl -sf "http://127.0.0.1:8000/api/agent-runs/$RUN_A/summary" \
  -H "Authorization: Bearer supkey-secret-32-bytes-or-longer" \
  | python3 -m json.tool
```

Expected fields: `id`, `status`, `principal`, `agent_id`,
`rows_touched`, `errored_ops_count`, `operations_count`,
`tool_calls_count`, `queries_count`, `tables_touched`,
`delta_version_range`, `has_denied_reason`. **Verify
`cost_gate_threshold` is NOT in the response** — the anti-gaming
guard from the Sprint-13.11 design memo.

## 8b. Family B — `pql_diff_runs` summary + detail

Seed a second run with a few tool calls so the diff is non-empty:

```bash
RUN_B="22222222-bbbb-2222-bbbb-222222222222"
curl -sf -X POST http://127.0.0.1:8000/api/agent-runs \
  -H "Authorization: Bearer devkey-secret-32-bytes-or-longer-here" \
  -H "X-Principal: alice@example.com" \
  -H "Content-Type: application/json" \
  -d "$(cat <<JSON
{
  "id": "$RUN_B",
  "notebook_path": "demo/run_b.py",
  "agent_id": "hermes-demo",
  "source": "# fixed run — describe + target-state first, then write_table, then merge\nimport pql\np = pql.PQL()\np.write_table(df, 'main.silver.orders_demo')\np.merge(df2, 'main.silver.orders_demo', on=['id'], strategy='upsert')\n",
  "runtime_versions": {"python": "3.14.0", "hermes": "v1"}
}
JSON
)"

for tool in pql_describe_primitive pql_target_state pql_recent_failures pql_query; do
  curl -sf -X POST "http://127.0.0.1:8000/api/agent-runs/$RUN_B/tool-call" \
    -H "Authorization: Bearer devkey-secret-32-bytes-or-longer-here" \
    -H "Content-Type: application/json" \
    -d "{\"tool_name\":\"$tool\",\"args_json\":\"{}\",\"duration_ms\":2}" -o /dev/null
done
```

Summary diff:

```bash
curl -sf "http://127.0.0.1:8000/api/agent-runs/diff?a=$RUN_A&b=$RUN_B" \
  -H "Authorization: Bearer supkey-secret-32-bytes-or-longer" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('tool_calls_count_diff:', d['tool_calls_count_diff']); print('tables_only_in_a:', d['tables_only_in_a']); print('tables_only_in_b:', d['tables_only_in_b'])"
```

Detail diff (Sprint 13.11.4b — tool-call-by-tool-call alignment):

```bash
curl -sf "http://127.0.0.1:8000/api/agent-runs/diff?a=$RUN_A&b=$RUN_B&detail=true&align=ordinal" \
  -H "Authorization: Bearer supkey-secret-32-bytes-or-longer" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('align:', d['align']); print('truncated:', d['truncated']); print('tool_calls_diff len:', len(d['tool_calls_diff'])); print('first half-pair:', json.dumps(d['tool_calls_diff'][3], indent=2)[:200])"
```

`align=ordinal` zips by index — the longer side has trailing
half-pairs (`a_call: null` or `b_call: null`).
`align=content` greedy-matches on `tool_name` so insertions on
one side don't shift later slots.

## 9. Browser leg — Playwright-MCP

`/runs` and `/runs/{id}` should show both seeded runs after the
curl legs above. Drive it via Playwright-MCP:

```text
mcp__playwright__browser_navigate url="http://127.0.0.1:8000/runs"
mcp__playwright__browser_take_screenshot fullPage=true filename="13_11_runs_list.png"
mcp__playwright__browser_navigate url="http://127.0.0.1:8000/runs/11111111-aaaa-1111-aaaa-111111111111"
mcp__playwright__browser_take_screenshot fullPage=true filename="13_11_run_detail_run_a.png"
mcp__playwright__browser_navigate url="http://127.0.0.1:8000/admin/api-keys"
mcp__playwright__browser_take_screenshot fullPage=true filename="13_11_api_keys_admin.png"
```

Expected on the run-detail page:

- **Source** tab carries the `.py` body posted in §2 verbatim
  (Sprint 13.8 forced-source-capture).
- **Tool calls** tab carries the entries posted in §6 + §8b
  (Sprint 13.10 added the template tab; Sprint 13.7.4 added the
  backend route).
- **Operations** tab is empty for these synthetic runs (we
  didn't fire `pql.merge` for real). For a real Hermes-Medallion
  replay it carries the per-primitive trail from Sprint 13.8.

## Bug check — `cost_gate_threshold` MUST NOT leak

```bash
curl -sf "http://127.0.0.1:8000/api/agent-runs/$RUN_A/summary" \
  -H "Authorization: Bearer supkey-secret-32-bytes-or-longer" \
  | grep -ic cost_gate_threshold
# 0
```

If this prints anything other than `0`, file BUG-13_11-01: the
anti-gaming guard described in the Sprint 13.11 plan was
breached. The whole point of leaving the threshold out is so an
agent can't tune writes to stay under the gate.

## Cleanup

The seeded runs + tool calls stay in the DB by design — they're
audit-log rows. To wipe between replays:

```bash
curl -sf -X POST "http://127.0.0.1:8000/api/agent-runs/11111111-aaaa-1111-aaaa-111111111111/finish" \
  -H "Authorization: Bearer devkey-secret-32-bytes-or-longer-here" \
  -H "Content-Type: application/json" \
  -d '{"status":"failed","exit_code":1}' -o /dev/null
curl -sf -X POST "http://127.0.0.1:8000/api/agent-runs/22222222-bbbb-2222-bbbb-222222222222/finish" \
  -H "Authorization: Bearer devkey-secret-32-bytes-or-longer-here" \
  -H "Content-Type: application/json" \
  -d '{"status":"succeeded","exit_code":0}' -o /dev/null
```

Either UUID can be re-seeded from §2 / §8b after that — the
`POST /api/agent-runs` route is idempotent on `id` collision
(returns the existing row).
