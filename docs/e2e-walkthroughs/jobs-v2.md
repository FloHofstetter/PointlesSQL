# Jobs v2 walkthrough

> **Mode:** `browser` · **Surface:** /jobs + /jobs/{id} (repair, run_if, triggers)

Exercise the orchestration upgrades: an error-handler task that only
runs on upstream failure, a repair run that reuses previous
successes, a file-arrival trigger, and the opt-in run notification.

## Preconditions

- E2E stack up + seeded; [`auth.md`](auth.md) ran first (admin).
- A writable host path visible to the app container for the
  file-arrival part (the steps use `/tmp/e2e-arrivals`).

## Walkthrough

### Part A — run_if error handler (3 steps)

1. **Create a DAG with a handler**.
   - Action: `/jobs` → "Create job", kind DAG, name `e2e-handler`,
     tasks JSON:
     `[{"name":"boom","kind":"python","config":{"entry_point":"missing_entry"},"depends_on":[]},{"name":"alert","kind":"python","config":{"entry_point":"missing_entry"},"depends_on":["boom"],"run_if":"at_least_one_failed"}]`
     (both entry points are intentionally broken — what matters is
     who *attempts* to run).
   - Assert: job created; detail page lists both tasks.

2. **Run and read the statuses**.
   - Action: "Run now"; reload after a moment.
   - Assert: run status `failed`; task `boom` shows `failed`, task
     `alert` shows `failed` too — crucially it **ran** (status is
     failed, not `skipped`), proving the `at_least_one_failed`
     condition fired the handler.

3. **Handler is excluded on success**: optional — repeat with a
   valid entry point for `boom` and assert `alert` lands in the
   new benign `excluded` status while the run stays `succeeded`.

### Part B — repair run (2 steps)

4. **Repair only what failed**.
   - Action: on a failed DAG run row click **Repair**.
   - Assert: a new run appears with trigger `repair (of #<id>)`;
     its task list shows previously-succeeded tasks as `succeeded`
     instantly (reused) while only the failed chain re-executed —
     the job log carries "reused previous success (repair run)".

### Part C — file-arrival trigger (3 steps)

5. **Create the event job**.
   - Action: "Create job", Trigger = "File arrival (glob)", path
     `/tmp/e2e-arrivals/*.csv`, any single-task kind/config; create.
   - Assert: detail page shows Trigger badge "file arrival" with
     the glob (no cron line).

6. **Baseline does not fire**.
   - Action: wait one scheduler tick (default a few seconds).
   - Assert: no run rows (the first evaluation only records the
     baseline).

7. **A new file fires exactly once**.
   - Action: `touch /tmp/e2e-arrivals/orders.csv` (inside the app's
     filesystem namespace); wait a tick.
   - Assert: exactly one run with trigger `event`; further ticks
     without file changes add no runs.

### Part D — notify_on (1 step)

8. **Failure notification**.
   - Action: create a single-task job with a broken config and
     "Notify run-as user: on failure" checked; Run now.
   - Assert: the bell inbox (`/notifications`) shows
     "Job **<name>** run #<id> failed…" for the run-as user.
