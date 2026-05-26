# dbt Pipelines walkthrough

> **Mode:** `browser` · **Surface:** /dbt cockpit + iframe

Exercises the dbt cockpit at `/dbt`:

- [`dbt.html`](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/pages/dbt.html)
  — chrome page (icon-rail + breadcrumbs) with three sub-tabs
  (Pipeline docs / Recent runs / Test failures) and a manifest
  summary card row at the top (model count, test count,
  coverage ratio).  Sprint 36.4 chrome landed via the BUG-37-06
  fix.
- The Pipeline-docs sub-tab still has the two states that
  predate the chrome work:
  - **`dbt_running == True`**: iframe to `/dbt-docs/` (dbt's
    own SPA, served by the lifespan-managed subprocess in
    [pointlessql/services/dbt_subprocess.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/services/dbt_subprocess.py))
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
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml up -d
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml \
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
     - `Place your dbt project under examples/dbt_project/`
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

The routes work even when the subprocess is down —
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

### Part C — enable the dbt-docs subprocess (5 steps)

The default e2e Docker image does not install `[dbt]`. The
project also carries a `[tool.uv] override-dependencies` for
`mashumaro>=3.17` — without
that override `dbt-core <=1.11`'s `mashumaro<3.15` upper bound
clashes with mashumaro 3.17's Python-3.14 fix
(dbt-labs/dbt-core#12098).

1. **Install the `[dbt]` extra into the venv**.
   ```bash
   docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml \
     exec -T pointlessql /opt/venv/bin/python -m pip install dbt-duckdb
   ```
   - Note: `pip install` lands in the running venv at
     `/opt/venv`. Restarting the container with `--build`
     would re-resolve via `uv sync` and pick up the
     `override-dependencies` automatically; the in-place
     `pip install` here is the faster ad-hoc path.

2. **Force-upgrade mashumaro to 3.17 (Python 3.14 unblock)**.
   ```bash
   docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml \
     exec -T pointlessql /opt/venv/bin/python -m pip install \
       --upgrade --no-deps mashumaro==3.17
   ```
   - `--no-deps` skips re-resolving dbt-core's transitive pins.
   - Verified runtime-clean against `dbt-core 1.11.8` +
     `dbt-adapters 1.22.10` on 2026-05-06.
   - Sanity:
     ```bash
     docker compose ... exec -T pointlessql /opt/venv/bin/python \
       -c "import dbt.cli.main; print('OK')"
     ```
     should print `OK` instead of `UnserializableField: Field
     "schema" of type Optional[str] in JSONObjectSchema is
     not serializable`.

3. **Compile the in-repo sample project**.
   ```bash
   docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml \
     exec -w /app -T pointlessql /opt/venv/bin/dbt compile \
       --project-dir examples/dbt_project --profiles-dir examples/dbt_project/profiles
   docker compose ... exec -w /tmp/dbt_project -T pointlessql \
     /opt/venv/bin/dbt docs generate --profiles-dir profiles
   ```
   - Assert: both exit 0; `examples/dbt_project/target/manifest.json`
     and `examples/dbt_project/target/catalog.json` exist. The
     3-model demo (`bronze_raw`, `silver_clean`,
     `gold_summary`) plus 5 tests from
     `examples/dbt_project/models/schema.yml` are now compiled.
   - Without `catalog.json` the dbt-docs SPA throws an alert
     dialog on every page load — `dbt docs generate` is what
     produces it.

4. **Restart PointlesSQL so the subprocess starts**.
   ```bash
   docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml \
     restart pointlessql
   ```

5. **Reload `/dbt`**.
   - Action: `browser_navigate('http://127.0.0.1:8000/dbt')`.
   - Assert: warning card is gone; `<iframe src="/dbt-docs/">`
     is present. Iframe loads dbt's own SPA — assert the iframe
     has non-zero dimensions and the `/dbt-docs/` HTTP request
     in the network panel returns 200.
   - Phase-36.4 chrome populates from manifest:
     - `#dbt-summary-models` reads `3`
     - `#dbt-summary-tests` reads `6`
     - `#dbt-summary-coverage` reads `66.7%`
   - Click **Recent runs** sub-tab → `/api/dbt/runs` lazy-fires;
     empty-state on a fresh stack reads "0 recent dbt run(s) —
     `agent_id="dbt-cli"`".
   - Click **Test failures** sub-tab → `/api/dbt/test-failures`
     lazy-fires; empty-state reads "0 recent test failure(s)
     across all dbt runs".
   - Note: dbt-docs is a third-party SPA; its internal selectors
     are out of scope for this playbook. Stick to chrome-page
     assertions and iframe-existence.

## Playwright MCP script

Browser replay for the `/dbt` cockpit (both states):

1. `browser_navigate('http://127.0.0.1:8000/dbt')`
   — assert the page renders chrome (header, breadcrumbs).
2. **Subprocess-up state:**
   `browser_evaluate('() => document.querySelector("iframe[src*=\"/dbt-docs/\"]") !== null')`
   — assert `true`; the embedded iframe loaded.
3. `browser_evaluate('() => document.querySelector(".dbt-coverage-card .badge").innerText')`
   — assert it reads a non-empty coverage percentage.
4. `browser_evaluate('() => fetch("/api/dbt/manifest").then(r => r.json())')`
   — assert response contains `models` array.
5. `browser_evaluate('() => fetch("/api/dbt/coverage").then(r => r.json())')`
   — assert response has key `models_with_tests`.
6. `browser_evaluate('() => fetch("/api/dbt/test-failures").then(r => r.json())')`
   — assert key `failures` is an array (empty if no failures).
7. **Subprocess-down state:** stop the dbt subprocess, reload —
   `browser_evaluate('() => document.querySelector(".alert-warning") !== null')`
   — assert the warning card is visible; iframe is absent.
8. `browser_navigate('http://127.0.0.1:8000/admin')`
   — assert the dbt admin tile reflects the down status.

## Verification log

- **2026-05-06.7 close, end-to-end verified.**
  Replayed Part C end-to-end against the e2e stack (dbt-core
  1.11.8 + dbt-duckdb 1.10.1 + mashumaro 3.17 [override] +
  Python 3.14.4): `dbt compile` and `dbt docs generate` both
  exit 0, the lifespan-spawned `dbt docs serve` subprocess
  comes up, the cockpit chrome populates with `models=3 /
  tests=6 / coverage=66.7%`, and both `/api/dbt/runs` +
  `/api/dbt/test-failures` lazy-load on tab activation with
  empty-state messages. 0 console errors on `/dbt` itself
  (dbt-docs SPA's missing-catalog modal goes away after
  step 3's `dbt docs generate`).

## Found bugs

- **BUG-37-06** ✅ Fixed.4 chrome landed:
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
docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml \
  exec pointlessql uv pip uninstall -y dbt-duckdb
docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml \
  restart pointlessql
```
