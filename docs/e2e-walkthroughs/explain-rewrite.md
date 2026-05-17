# Agent EXPLAIN-driven self-rewrite loop walkthrough

> **Mode:** `hybrid` · **Phase:** 39 · **Surface:** Hermes plugin + run-detail tab

Exercises the Phase-39 explain-first rewrite loop end to end:

- The Hermes plugin's [`pql_query`](../../../hermes-plugin-pointlessql/hermes_plugin_pointlessql/tools/query.py)
  tool calls `GET /api/sql/explain` before `POST /api/sql/execute`.
  When the cost-gate verdict says `needs_approval=True` the tool
  returns a structured `cost_gate_denied` envelope carrying the
  EXPLAIN tree + a rewrite hint instead of executing.
- The plugin caps the loop at 3 attempts.  At attempt 4 the envelope
  flips to `human_approval_required` and the plugin POSTs one row to
  the new
  [`POST /api/agent-runs/{id}/rewrite-attempt`](../../pointlessql/api/agent_runs_routes/rewrite_attempts.py)
  route with `verdict='human_approval_required'`.
- A revised SQL that passes the cost-gate (`needs_approval=False`
  after a previous denial) writes an `auto_rewrite_succeeded` row
  with the original + rewritten cost so a Grafana panel can compute
  weekly savings.
- The
  [run-detail Operations top-tab](../../frontend/templates/partials/_run_tab_operations.html)
  carries a new "Rewrites" sub-pane showing every attempt with
  Δ-cost colour coding.

## Preconditions

- Stack up:
  ```bash
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml up -d
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml \
    exec pointlessql python /app/scripts/seed-e2e.py
  ```
- [`auth.md`](auth.md) ran first — admin@pql.test session for the
  run-detail UI.  The agent-side flow uses an API key with
  ``agent`` scope (any working-agent key works).
- A Hermes-cli session with the
  [`hermes-plugin-pointlessql`](../../../hermes-plugin-pointlessql/)
  plugin loaded.  Set ``POINTLESSQL_API_KEY`` and
  ``POINTLESSQL_BASE_URL=http://127.0.0.1:8000`` in the env.
- The cost-gate threshold is the install default
  (``POINTLESSQL_SQL_COST_GATE_THRESHOLD_ROWS=1000000``); seed-e2e
  loads enough rows in `main.bronze.events` to trip it on a
  ``SELECT *``.
- Playwright MCP Firefox lock-file gotcha: see [CLAUDE.md](../../CLAUDE.md)
  line 227-235.

## Walkthrough

### Part A — First attempt trips the cost-gate (3 steps)

1. **Start a Hermes-cli session and seed an agent run**.
   - Action: ``hermes chat``; the plugin's `on_session_start` hook
     POSTs ``/api/agent-runs`` and exports
     ``POINTLESSQL_AGENT_RUN_ID`` for the session.
   - Assert: capture the run UUID from the log line
     ``registered PointlesSQL agent run <uuid> (session_start)``.
     Save as ``$RUN_ID`` for later steps.

2. **Submit an oversized query**.
   - Action: prompt the LLM "Show me everything in
     ``main.bronze.events``" — it should call
     ``pql_query`` with ``{"sql": "SELECT * FROM main.bronze.events"}``.
   - Assert: the tool result is a JSON envelope containing
     ``"ok": false``, ``"error": "cost_gate_denied"``,
     ``"attempt_no": 1``, ``"max_attempts": 3``, an ``"explain"``
     tree, an ``"estimated_cost"`` above the
     ``"threshold"`` (default 1,000,000), and a ``"hint"`` that
     mentions LIMIT / WHERE / staged JOINs.
   - Assert: ``POST /api/sql/execute`` was NOT called for this turn
     (no row in ``query_history`` for this ``$RUN_ID`` yet).

3. **Verify the per-run sql_explain audit row landed**.
   - Action:
     ```bash
     sqlite3 /opt/state/pointlessql/main.db \
       "SELECT op_name, json_extract(params_json, '$.needs_approval'),
               json_extract(params_json, '$.cost')
        FROM agent_run_operations
        WHERE agent_run_id='$RUN_ID';"
     ```
   - Assert: one row with ``op_name=sql_explain``,
     ``needs_approval=1``, and ``cost`` matching the envelope.

### Part B — Rewrite succeeds (3 steps)

1. **Agent rewrites with LIMIT and resubmits**.
   - Action: the LLM, having read the hint, calls
     ``pql_query`` again with
     ``{"sql": "SELECT * FROM main.bronze.events LIMIT 1000"}``.
   - Assert: the tool result is a normal success envelope —
     ``"ok": true``, ``"row_count" > 0``, rows present.

2. **Verify the rewrite_attempts row landed with auto_rewrite_succeeded**.
   - Action:
     ```bash
     sqlite3 /opt/state/pointlessql/main.db \
       "SELECT attempt_no, verdict, original_cost, rewritten_cost
        FROM rewrite_attempts WHERE agent_run_id='$RUN_ID';"
     ```
   - Assert: one row with ``attempt_no=2``,
     ``verdict='auto_rewrite_succeeded'``, ``original_cost`` from
     the Part-A denial, ``rewritten_cost`` ≪ ``original_cost``.

3. **Verify two sql_explain ops + the rewrite_attempts row coexist**.
   - Action:
     ```bash
     sqlite3 /opt/state/pointlessql/main.db \
       "SELECT op_name, json_extract(params_json, '$.needs_approval')
        FROM agent_run_operations WHERE agent_run_id='$RUN_ID'
        ORDER BY ordinal;"
     ```
   - Assert: two ``sql_explain`` rows (first ``needs_approval=1``,
     second ``needs_approval=0``) plus one ``sql`` row from the
     successful execute.

### Part C — Run-detail UI surfaces the rewrite (3 steps)

1. **Navigate to the run-detail page**.
   - Action: ``browser_navigate('http://127.0.0.1:8000/runs/$RUN_ID')``.
   - Assert: page title ``Run · PointlesSQL``; breadcrumb shows
     ``Home / Runs / <short id>``; Operations top-tab is rendered.

2. **Open the Rewrites sub-tab on the Operations top-tab**.
   - Action: click ``#tab-rewrites-btn``.
   - Assert: ``#tab-rewrites`` pane becomes active; the table has
     a row with ``Verdict = auto_rewrite_succeeded`` (green badge),
     ``Original SQL`` ≠ ``Rewritten SQL`` (different 12-char
     hashes), and ``Δ cost`` rendered in green text with a
     ``−`` prefix.

3. **Verify the URL hash deeplink**.
   - Action: reload ``/runs/$RUN_ID#tab-rewrites``.
   - Assert: the page lands directly on the Operations top-tab
     AND its Rewrites sub-pane.  No console errors.

### Part D — Three attempts exhausted (4 steps)

1. **Provoke three failed rewrites in a fresh run**.
   - Action: start a fresh Hermes session (new ``$RUN_ID``).  Have
     the agent submit four queries that all trip the cost-gate
     (e.g. four variants of ``SELECT * FROM huge.t WHERE x IN (...)``
     that each estimate above threshold).
   - Assert: the first three responses each carry
     ``error='cost_gate_denied'`` with ``attempt_no`` 1 / 2 / 3.

2. **Fourth attempt escalates to human approval**.
   - Action: the agent's fourth ``pql_query`` call (still
     above-threshold) returns ``error='human_approval_required'``
     with ``attempt_no=4`` and a hint mentioning ``/runs/$RUN_ID``.
   - Assert: ``POST /api/agent-runs/$RUN_ID/rewrite-attempt`` fired
     with ``verdict='human_approval_required'``.

3. **Run-detail Rewrites sub-tab shows the escalation**.
   - Action: navigate to ``/runs/$RUN_ID``, switch to
     Operations → Rewrites.
   - Assert: one row with ``Verdict = human_approval_required``
     (red badge), ``Rewritten SQL`` populated (the 4th attempt's
     hash), ``Cost after`` populated, ``Δ cost`` rendered.

4. **Admin can still approve the run via the existing flow**.
   - Action: admin opens ``/runs/$RUN_ID`` and uses the Approve
     button on the metadata card (when status is
     ``needs_approval``).
   - Assert: the standard Phase-14 approval flow takes over —
     status flips to ``approved``, the run continues.

## Playwright MCP script

Browser replay for the run-detail Rewrites tab and the Grafana
panel; the Hermes plugin / cost-gate flow stays in the prose
above:

1. `browser_navigate('http://127.0.0.1:8000/runs/<RUN_ID>')`
   — assert the run-detail header renders.
2. `browser_click("Operations")` (top tab)
   — `browser_wait_for(".operations-list")`.
3. `browser_click("Rewrites")` (sub-tab)
   — assert ≥ 1 row visible with cost-gate status badge.
4. `browser_evaluate('() => document.querySelectorAll(".rewrite-attempt").length')`
   — capture the rewrite-attempt count.
5. `browser_evaluate('() => document.querySelector(".rewrite-attempt[data-attempt=\"1\"] .original-cost").innerText')`
   — assert non-empty (cost in either Decimal or float form).
6. `browser_evaluate('() => document.querySelector(".rewrite-attempt[data-attempt=\"1\"] .rewritten-cost").innerText')`
   — assert lower than original-cost (the agent rewrote it
   smaller).
7. `browser_navigate('http://your-grafana-host/d/pointlessql-audit')`
   — assert panel #21 ("Rewrite savings — averted cost-gate
   denials per week") renders ≥ 1 datapoint.
8. `browser_evaluate('() => fetch("/api/runs/<RUN_ID>/rewrite-attempts").then(r => r.json())')`
   — assert response has key `attempts` (array of objects with
   `attempt_n`, `original_cost`, `rewritten_cost`).

## Verification log

- 2026-05-06 — Phase 39 close.  Replayed end to end against the
  e2e stack.  All four parts grew the expected audit rows; the
  Operations → Rewrites sub-tab renders with the green/red
  badges and the Δ-cost column.  Grafana panel 21 ("Rewrite
  savings — averted cost-gate denials per week") is populated by
  the same ``rewrite_attempts`` table.

## Found bugs

(none yet — file as ``BUG-39-NN`` with a fix-location pointer
when surfaced by replay)

## Cleanup

```bash
sqlite3 /opt/state/pointlessql/main.db \
  "DELETE FROM rewrite_attempts WHERE agent_run_id='$RUN_ID';
   DELETE FROM agent_run_operations WHERE agent_run_id='$RUN_ID';
   DELETE FROM agent_runs WHERE id='$RUN_ID';"
```
