# E2E walkthrough — Agent-memory page

> **Mode:** browser · **Phase:** 90 · **Surface:** `/memory/<agent-id>`

This playbook validates the agent-memory "brain browser" page
that Phase 90 ships on top of the existing `agent_runs` +
`agent_run_operations` + `branch_audit_log` tables.  The vertical
slice: a reviewer opens an agent's memory page, filters its
operation tape, branches off one of its runs, replays the branch,
and posts a comment via the polymorphic social tab.

## Setup

```bash
# Terminal 1 — soyuz-catalog
cd ~/git/soyuz-catalog
uv run soyuz-catalog       # http://127.0.0.1:8080

# Terminal 2 — PointlesSQL
cd ~/git/PointlesSQL
uv run pointlessql         # http://127.0.0.1:8000
```

Seed at least one agent run with mixed operation types so the
recall filter has something to chew on.  The simplest way is to
run the Phase-21 `agent-ml-registry` walkthrough first — it
emits 5+ operations under `agent_id="hermes-ml-smoke"`.  If you
don't have that data, fall back to:

```bash
uv run python - <<'PY'
import datetime, json, uuid
from pointlessql.db import get_session_factory
from pointlessql.models import AgentRun, AgentRunOperation

factory = get_session_factory()
agent_id = "phase90-walkthrough"
now = datetime.datetime.now(datetime.UTC)
run_id = str(uuid.uuid4())
with factory() as s:
    s.add(AgentRun(
        id=run_id, principal="flo@example.com", agent_id=agent_id,
        notebook_path="phase90.py", status="succeeded",
        started_at=now, finished_at=now,
        tables_touched=json.dumps(["main.bronze.orders"]),
    ))
    s.flush()
    for i, (op, target) in enumerate([
        ("write_table", "main.bronze.orders"),
        ("sql", None),
        ("merge", "main.silver.orders"),
        ("sql", None),
    ], start=1):
        s.add(AgentRunOperation(
            agent_run_id=run_id, ordinal=i, op_name=op,
            params_json=json.dumps({"query": "SELECT 1"} if op == "sql" else {}),
            target_table=target, delta_version_before=i,
            started_at=now, finished_at=now,
        ))
    s.commit()
print("seeded", agent_id, run_id)
PY
```

## Step 1 — Navigate to the memory page

In the browser (or via Playwright-MCP):

1. Log in as the admin test user.
2. Navigate to `/memory/phase90-walkthrough` (or your seeded `agent_id`).

Expect:

* Header carries the agent_id in monospace, `run_count >= 1` and
  a `last seen` timestamp.
* Four top-tabs visible: **Timeline**, **Operations**,
  **Branches**, **Social**.
* Timeline tab active by default, showing today's date with one
  list-group row per run.

Playwright assertion ideas:

```python
await page.goto("http://127.0.0.1:8000/memory/phase90-walkthrough")
await expect(page.get_by_test_id("run-count-badge")).to_contain_text("run")
await expect(page.get_by_role("tab", name="Operations")).to_be_visible()
```

## Step 2 — Filter the operation tape

1. Click the **Operations** tab.
2. Confirm the table shows ≥4 rows ordered by `started_at` desc.
3. Change the **Op name** dropdown to `sql`.

Expect: the table refreshes (HTTP GET to
`/api/memory/<agent>/recall?op_name=sql`) and only `sql` rows
remain.

4. Clear the op-name filter and type `silver` into the
   **Target table** input.

Expect: only the `merge` row remains (its `target_table` is
`main.silver.orders`).

Playwright assertion:

```python
await page.get_by_test_id("recall-op-name").select_option("sql")
rows = page.locator('[data-testid="operations-table"] tbody tr')
await expect(rows).to_have_count(2)
```

## Step 3 — Inspect branches and trigger a replay

1. Click the **Branches** tab.

Without a prior `pql.memory.branch` call there's no branch to
work with.  Trigger one with `curl`:

```bash
curl -X POST http://127.0.0.1:8000/api/memory/phase90-walkthrough/branch \
  -H "Cookie: ${POINTLESSQL_TEST_COOKIE}" \
  -H "Content-Type: application/json" \
  -d '{"from_run_id": "<the run_id from setup>", "intent": "fork", "pin_to_version": true}'
```

Expect: 200 JSON with `branch_schema_fqn`, `parent_schema_fqn`,
`pinned_delta_version`, `intent: "fork"`.

2. Refresh `/memory/phase90-walkthrough` → click **Branches**.

Expect: one row with `intent=fork`, `Pin` column showing `v1`,
and a **Replay** button.

3. Click **Replay**.

Expect: the button enters a `Replaying…` spinner state, then the
browser redirects to `/runs/<new-replay-run-id>` showing the
replay run's detail page.  The new run carries
`notebook_path = "<replay of {original_run_id}>"`.

Playwright assertion:

```python
await page.get_by_test_id("replay-button").click()
await page.wait_for_url("**/runs/**", timeout=10_000)
```

## Step 4 — Post a comment via the social tab

1. Return to `/memory/phase90-walkthrough`.
2. Click the **Social** tab.
3. The **Discussion** sub-tab loads (empty by default).
4. Type a markdown comment into the textarea and click **Post**.

Expect: the new comment renders in the list immediately and a
POST to `/api/social/agent_memory/<agent>/comments` returns 200.

5. Switch to **Endorsements** → click `Verified by steward`.

Expect: the endorsement count increments to 1.

## Step 5 — Verify the replay surfaces back on the memory page

1. Refresh `/memory/phase90-walkthrough`.
2. Timeline tab now shows two runs grouped under today: the
   original + the replay (with `<replay of …>` in the notebook
   path column).
3. Operations tab: the replay run contributes one new SQL op
   whose `params_json["_replay_recorded_only"]` is `true`.

## Known caveats (Phase 90 scope)

* **Replay records intent, not execution.**  Replayable ops are
  re-recorded against the new run with `_replay_recorded_only:
  true` stamped in params.  Real execution (re-running SQL
  against the branch's DuckDB views) lands in Phase 91 alongside
  the NL→SQL chat panel.
* **Version-pinning is metadata.**  `pin_to_version=true` stamps
  the source's `delta_version_before` into
  `BranchAuditLog.payload_json` and the branch tag set, but
  branch tables are cloned at *current* source version.  True
  per-table time-travel is a follow-up sprint.

## BUG-90-NN — known issues to fix in-place

None at landing time.  Add new ones below as they surface in
replay sessions.
