# dbt Pipelines walkthrough

Exercises the dbt cockpit at `/dbt`:

- [`dbt.html`](../../frontend/templates/pages/dbt.html)
  — chrome page (icon-rail + breadcrumbs) with three sub-tabs
  (Pipeline docs / Recent runs / Test failures) and a manifest
  summary card row at the top (model count, test count,
  coverage ratio).  Sprint 36.4 chrome landed via the BUG-37-06
  fix.
- The Pipeline-docs sub-tab still has the two states that
  predate the chrome work:
  - **`dbt_running == True`**: iframe to `/dbt-docs/` (dbt's
    own SPA, served by the lifespan-managed subprocess in
    [pointlessql/services/dbt_subprocess.py](../../pointlessql/services/dbt_subprocess.py))
  - **`dbt_running == False`**: warning card with the install
    + compile + restart instructions
- Recent-runs sub-tab fetches `/api/dbt/runs` (newest 20
  AgentRun rows where `agent_id='dbt-cli'`) and links each to
  `/runs/{id}`.
- Test-failures sub-tab fetches `/api/dbt/test-failures`
  (without `agent_run_id`, returns the 50 most recent
  `lineage_row_rejects` rows joined to `agent_run_operations`
  across all dbt runs).

## Preconditions

- Stack up:
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d
  docker compose -f docker-compose.yml -f docker-compose.e2e.yml \
    exec pointlessql python /app/scripts/seed-e2e.py
  ```
- [`auth.md`](auth.md) ran first — any signed-in user can browse
  `/dbt` (the page is not admin-only; mutating actions like
  `POST /api/dbt/run` are gated separately).
- The seed-e2e stack does NOT install the optional `[dbt]`
  extra by default, so the dbt-docs subprocess is **not**
  running on a fresh stack and the page renders state #2 (the
  warning card).  To exercise state #1, see "Optional: enable
  the dbt-docs subprocess" below.
- Playwright MCP Firefox lock-file gotcha: see CLAUDE.md
  line 227-235.

## Walkthrough

### Part A — Default state: dbt-docs not running (4 steps)

1. **Land on the dbt page**.
   - Action: `browser_navigate('http://127.0.0.1:8000/dbt')`.
   - Assert: title `Pipelines · PointlesSQL`. Heading reads
     "dbt Pipelines" with the bezier-curve icon.
   - Assert: breadcrumb is `Home / Pipelines`.

2. **Verify warning card shows install instructions**.
   - Action:
     ```js
     () => document.querySelector('.alert.alert-warning')?.textContent.trim()
     ```
   - Assert: text contains all four bullet points:
     - `Install the optional [dbt] extra`
     - `Place your dbt project under dbt_project/`
     - `Run dbt compile once to generate target/manifest.json`
     - `Restart PointlesSQL — the subprocess starts during the
       FastAPI lifespan hook`
   - Assert: NO `<iframe>` element on the page (the iframe is
     rendered only when `dbt_running == True`).

3. **Verify proxy is offline**.
   - Action:
     ```js
     async () => (await fetch('/dbt-docs/', {credentials:'same-origin'})).status
     ```
   - Assert: returns either `404` (proxy not registered when
     subprocess is None) or `503` (proxy registered but upstream
     unreachable). The exact status is implementation-detail;
     load-bearing assertion is "not 200".

4. **Anonymous redirect-to-login**.
   - Action: open a private window (no cookies), navigate to
     `/dbt`.
   - Assert: 303 redirect to `/auth/login?next=/dbt`. The
     redirect-with-next pattern is shared with all auth-gated
     HTML pages.

### Part B — dbt API surface (read-only, exists today) (5 steps)

The Phase 36.B routes work even when the subprocess is down —
they read `target/manifest.json` directly from disk. The
cockpit's manifest summary card-row + Recent-runs +
Test-failures sub-tabs (Phase 37.1, BUG-37-06 fix) consume
these routes; this section exercises them programmatically
to document the consumer contract.

1. **Manifest endpoint — 404 on a fresh stack**.
   - Action:
     ```js
     async () => (await fetch('/api/dbt/manifest',
       {credentials:'same-origin'})).status
     ```
   - Assert: `404`. The route returns 404 when
     `target/manifest.json` doesn't exist. Body says "run dbt
     compile first".

2. **Coverage endpoint — same 404**.
   - Action:
     `await fetch('/api/dbt/coverage', {credentials:'same-origin'})`
   - Assert: status `404` until a manifest exists.

3. **Test-failures endpoint — needs an agent_run_id**.
   - Action:
     `await fetch('/api/dbt/test-failures?agent_run_id=fake', ...)`
   - Assert: status `400` or `200 {rows: []}` depending on
     whether the run id exists. Either is valid empty-state.

4. **Compile endpoint — auth-required, accepts JSON body**.
   - Action:
     `await fetch('/api/dbt/compile', {method:'POST',
       credentials:'same-origin'})`
   - Assert: status `400` or `503` when dbt-duckdb isn't
     installed (the executor raises before the subprocess
     spawns). On a stack with `[dbt]` installed, returns 200
     with `{exit_code, manifest_path, run_results_path}`.

5. **Run + Test endpoints — supervisor scope required**.
   - Action:
     `await fetch('/api/dbt/run', {method:'POST',
       credentials:'same-origin'})`
   - Assert: 200 (admin) or 403 (non-admin / non-supervisor).
     The signed-in admin@pql.test passes.

### Part C — Optional: enable the dbt-docs subprocess (4 steps)

The default e2e Docker image does not install `[dbt]`. To
exercise the iframe path:

1. **Install dbt-duckdb in the running container**.
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.e2e.yml \
     exec pointlessql uv pip install dbt-duckdb
   ```
   - **Caveat:** `dbt-duckdb 1.9 + Python 3.14` has a known
     `mashumaro.UnserializableField` import error. If pip
     install fails or `import dbt.cli.main` raises non-
     ImportError, this entire Part C is skipped — the e2e
     stack tracks Python 3.14 and the dbt-duckdb gate is in
     `pyproject.toml [project.optional-dependencies] dbt`.

2. **Compile the in-repo sample project**.
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.e2e.yml \
     exec -w /app pointlessql dbt compile --project-dir dbt_project
   ```
   - Assert: exits 0; `dbt_project/target/manifest.json`
     exists. The 3-model demo (`bronze_raw`, `silver_clean`,
     `gold_summary`) plus 5 tests from
     `dbt_project/models/schema.yml` are now compiled.

3. **Restart PointlesSQL so the subprocess starts**.
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.e2e.yml \
     restart pointlessql
   ```

4. **Reload `/dbt`**.
   - Action: `browser_navigate('http://127.0.0.1:8000/dbt')`.
   - Assert: warning card is gone; `<iframe src="/dbt-docs/">`
     is present. Iframe loads dbt's own SPA — assert the iframe
     has non-zero dimensions and the `/dbt-docs/` HTTP request
     in the network panel returns 200.
   - Note: dbt-docs is a third-party SPA; its internal selectors
     are out of scope for this playbook. Stick to chrome-page
     assertions and iframe-existence.

## Found bugs

- **BUG-37-06** ✅ Fixed — Phase 36.4 chrome landed:
  - Manifest summary card-row above the tab nav (model count,
    test count, coverage ratio); fetched from
    `/api/dbt/manifest` + `/api/dbt/coverage`.
  - Three sub-tabs (Pipeline docs / Recent runs / Test
    failures); pipeline tab keeps the iframe-or-warning
    rendering, the other two lazy-load their data on tab
    activation.
  - Recent runs links each row to `/runs/{id}`; relies on
    a new `GET /api/dbt/runs` endpoint that filters
    AgentRun by `agent_id='dbt-cli'`.
  - Test failures uses the existing `/api/dbt/test-failures`
    route, now with `agent_run_id` optional — when omitted,
    returns the 50 most recent failures across all dbt
    runs, including the `agent_run_id` per row for
    cross-link.

## Cleanup

```bash
# Optional: roll back the [dbt] install if you ran Part C
docker compose -f docker-compose.yml -f docker-compose.e2e.yml \
  exec pointlessql uv pip uninstall -y dbt-duckdb
docker compose -f docker-compose.yml -f docker-compose.e2e.yml \
  restart pointlessql
```
