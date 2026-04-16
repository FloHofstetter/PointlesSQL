# Jobs + DAG walkthrough

Exercises the scheduler surface: single-task job create + Run-now,
DAG create via the JSON-textarea modal, retry + fail-skip propagation,
Pause / Resume, the per-task log panel, and a cross-feature smoke run
of a `pg_sync`-kind job against Sprint 22's foreign catalog
`pg_mirror`.

## Preconditions

- Stack up with the e2e overlay; seed script run (Sprint 22).
- `POINTLESSQL_SCHEDULER_TICK_SECONDS=2` (default from the overlay
  env passthroughs — `pointlessql/settings.py:51` sets 30 s
  otherwise).
- `admin@pql.test` and `user@pql.test` exist (from `auth.md`).
- `foreign-catalog-sync.md` ran at least once, so `pg_mirror` exists
  with schemas `pg_mirror.shop.*` populated. The cross-feature
  smoke step below reuses it.
- Currently logged in as `admin@pql.test`.

## Walkthrough

### Part A — single-task job (happy path)

1. **Navigate to `/jobs`**.
   - Action: `browser_navigate('http://127.0.0.1:8000/jobs')`
   - Assert: URL is `/jobs`, "New DAG job" button is visible
     (admin-only gate).

2. **Create a single-task job via the JSON API** (the modal is for
   DAG jobs; single-task jobs are simpler to drive via the API).
   - Action:
     ```js
     await fetch('/api/jobs', {
         method: 'POST',
         headers: {'Content-Type': 'application/json'},
         body: JSON.stringify({
             name: 'smoke_single',
             cron_expr: '0 0 1 1 *',        // never auto-triggers
             kind: 'python',
             config: {entry_point: 'nonexistent_for_now'},
             run_as_user_id: 1,
         }),
     });
     ```
   - Assert: response 201/200 with JSON body; reload `/jobs`; the
     `smoke_single` row appears in the table with `kind=python`,
     `status=active`.

3. **Open the job detail page and click "Run now"**.
   - Action: click the `smoke_single` link in the table.
   - Assert: URL is `/jobs/{id}`, Run-now / Pause / Resume buttons
     render in the header, `x-data` `busy` state is `false`.
   - Action: `Alpine.$data(document.querySelector('[x-data*="busy"]')).post('/api/jobs/{id}/run')`
     (call through Alpine to bypass the `window.location.reload()`
     that the click handler triggers — we want to observe state
     transitions without the page reload blowing away the browser
     evaluation context).
   - Assert: after ~3 s, `/api/jobs/{id}/runs/{run_id}/tasks`
     returns a row with `status` in `{succeeded, failed}` —
     expected `failed` since the `entry_point` is intentionally
     unresolved. The error string references `importlib.metadata`.

### Part B — DAG create via modal

4. **Open the "New DAG job" modal**.
   - Action: click the "New DAG job" button on `/jobs`.
   - Assert: `#createJobModal` becomes visible.

5. **Submit a valid 3-task DAG**:
   - Task `a` (no deps) → task `b` (depends on `a`) → task `c`
     (depends on `a` + `b`). All `kind=python` with
     `config={entry_point:"noop"}` so they fail the plugin lookup
     but in a deterministic order — this playbook exercises
     orchestration, not task bodies.
   - Action: drive the modal's Alpine directly:
     ```js
     const d = Alpine.$data(document.querySelector('#createJobModal'));
     d.name = 'smoke_dag';
     d.cron = '0 0 1 1 *';
     d.maxParallel = 1;
     d.tasks = JSON.stringify([
         {name:'a', kind:'python', config:{entry_point:'noop'}, depends_on:[]},
         {name:'b', kind:'python', config:{entry_point:'noop'}, depends_on:['a']},
         {name:'c', kind:'python', config:{entry_point:'noop'}, depends_on:['a','b']},
     ]);
     await d.submit();
     ```
   - Assert: `d.error === null`, browser navigates to
     `/jobs/{new_id}`.

6. **Negative: cycle detection**. Reopen the modal on `/jobs`,
   change `a.depends_on = ['c']` and `d.name = 'smoke_cycle'`.
   - Assert after submit: `d.error` contains `"cycle detected in
     task graph"` (from `scheduler.py:532`), modal stays open.

7. **Negative: unknown dependency**. Reset, then use
   `tasks=[{name:'a', depends_on:['does_not_exist'], ...}]`.
   - Assert: `d.error` contains `"depends on unknown task"` (from
     `main.py:1302`).

8. **Negative: duplicate task name**. Reset, then
   `tasks=[{name:'a',...},{name:'a',...}]`.
   - Assert: `d.error` contains `"duplicate task name"` (from
     `main.py:1228`).

### Part C — retry + fail-skip propagation

9. **Create a DAG with a retrying, always-failing task**:
   - Task `pre` (no deps) → task `flaky` (depends `pre`,
     `max_retries=2`) → task `downstream` (depends `flaky`).
   - All tasks use `kind=python` + `config={entry_point:'noop'}`
     so they all fail (no such entry point). The purpose here is
     to observe the retry + skip bookkeeping, not the task body.
   - Action: submit as in step 5 with `name='retry_smoke'`.
   - Action: `Alpine.$data(document.querySelector('[x-data*="busy"]')).post('/api/jobs/{id}/run')`
   - Wait ~15 s for retry backoff + scheduler ticks.
   - Assert via
     `fetch('/api/jobs/{id}/runs/{run_id}/tasks').then(r=>r.json())`:
     - `pre.status === 'failed'` (one attempt).
     - `flaky.status === 'failed'`, `flaky.attempts === 3`
       (initial + 2 retries).
     - `downstream.status === 'skipped'` with error matching
       `"upstream [...] did not succeed"`.

### Part D — pause / resume

10. **On any job detail page**, click Pause (the post-`e09a661`
    Alpine wrapper).
    - Action: click the Pause button.
    - Assert: page reloads, `badge` shows "paused", the Pause
      button swaps for Resume (two icons — `bi-play` vs
      `bi-pause`).
    - Assert: `fetch('/api/jobs/{id}').then(r=>r.json()).then(j=>j.is_paused)`
      returns `true`.
    - Action: click Resume.
    - Assert: `is_paused === false`.

### Part E — task log panel

11. **On a job with at least one completed run**, expand a task
    row's logs.
    - Action: click the "Logs" button inside the task table row.
    - Assert: the `openTaskId` Alpine state matches the row's
      task id; `browser_network_requests()` shows a GET to
      `/api/jobs/{id}/runs/{run_id}/logs?task_id=…` issued only
      on click (lazy fetch).
    - Assert: at least one row rendered in the expanded
      `<tbody>` with timestamp + level badge + message. If the
      run was a failing one, the message contains the original
      error string (from the `log_job` writer, Sprint 20).

### Part F — cross-feature smoke (`pg_sync` kind)

12. **Create and run a `pg_sync`-kind job** against the seeded
    `pg_mirror` foreign catalog.
    - Action via `fetch('/api/jobs', ...)`:
      ```js
      body: {
          name: 'pg_sync_smoke',
          cron_expr: '0 0 1 1 *',
          kind: 'pg_sync',
          config: {catalog_name: 'pg_mirror'},
          run_as_user_id: 1,
      }
      ```
    - Action: trigger `Run now` via the Alpine `post()` path.
    - Wait ~5 s for the scheduler to pick it up and for
      `_pg_sync_executor` (at `services/scheduler.py:145`) to
      drive the Sprint 18 `run_sync()`.
    - Assert: `/api/jobs/{id}/runs/{run_id}/tasks` returns
      status `succeeded` (idempotent re-sync; Postgres content
      unchanged since `foreign-catalog-sync.md`).
    - Assert: navigate to `/catalogs/pg_mirror`, the Sync history
      card shows a new row with `added=0, changed=0, dropped=0`
      and a timestamp within the last minute.

## Playwright MCP script

```text
# Part A
browser_navigate('http://127.0.0.1:8000/jobs')
browser_evaluate(async () => {
    const r = await fetch('/api/jobs', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
            name:'smoke_single', cron_expr:'0 0 1 1 *',
            kind:'python', config:{entry_point:'nonexistent'},
            run_as_user_id: 1,
        }),
    });
    return (await r.json()).id;
})
browser_navigate('http://127.0.0.1:8000/jobs/{id}')
browser_evaluate(async () => {
    await Alpine.$data(document.querySelector('[x-data*="busy"]'))
        .post('/api/jobs/{id}/run');
})
# wait 3s, then fetch /api/jobs/{id}/runs/.../tasks

# Parts B + C: same pattern via the #createJobModal Alpine data
# Parts D + E: click Pause/Resume and Logs button directly

# Part F: create pg_sync job and Run now; poll /api/jobs
```

## Found bugs

- **BUG-23-02** — fixed in the same sprint commit. `POST
  /api/jobs` in
  [`pointlessql/api/main.py`](../../pointlessql/api/main.py)
  committed the `Job` row and its `JobTask` rows *before* calling
  `scheduler_service.validate_dag`. A payload with a cycle or an
  unknown `depends_on` was rejected with 422 after the rows
  landed, leaving orphan entries in the DB that showed up on
  `/jobs` forever. The fix replaces the mid-flow
  `session.commit()` calls with `session.flush()` and does a
  single final commit only after `validate_dag` succeeds — so a
  rejected payload rolls back cleanly when the session context
  exits. Live verification: after the fix, a cycle payload
  returns 422 and no row for it appears in `GET /api/jobs`.

Live-run notes (no bugs):

- All three negative-case error strings land verbatim at `422`:
  `"cycle detected in task graph: [<id>, <id>]"`,
  `"task '<n>' depends on unknown task '<dep>'"`,
  `"duplicate task name: '<n>'"`.
- Retry at root: `flaky` (max_retries=2) ran 3 attempts with
  linear backoff (~1 s, ~2 s between them);
  `downstream` flipped to `skipped` with
  `"upstream [<id>] failed"`. `job_logs` carries an INFO start
  line, three WARNING per-attempt lines, and a final ERROR
  "exhausted retries" line — all with timestamps and the
  per-task Alpine log panel rendered them correctly.
- `pg_sync` kind: scheduler invoked `_pg_sync_executor` (at
  `scheduler.py:145`) and `run_sync()` mirrored the seeded
  Postgres `shop` schema into the `pg_mirror` foreign catalog
  in ~700 ms. The existing `/catalogs/pg_mirror` sync-history
  card already covers the persisted `SyncRun` row.
- Pause/Resume: the post-`e09a661` Alpine wrapper works —
  clicking Pause toggles `is_paused:true`, the button swaps
  icon+label to Resume, and clicking Resume flips back.
