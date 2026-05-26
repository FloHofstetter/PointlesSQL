# Rollback walkthrough

> **Mode:** `browser` · **Surface:** /runs/{id} admin rollback card

**** — closes (First-Class Rollback). Replay
this playbook to verify the audit→action loop in headful Firefox:
admin clicks a Rollback button on `/runs/{id}`, the modal renders
the version-delta + cascade preview, and the spawned rollback run
shows up at `/runs/{new_id}` with a single `op_name='rollback'`
row whose `delta_version_before/after` proves the table moved.

## What this walkthrough exercises

| Layer | Surface | Sprint |
| --- | --- | --- |
| Primitive | `pql.rollback(target, before_run=...)` + `RollbackError` family | 16.1 |
| Read API | `GET /api/runs/{id}/rollback-preview?target=...` | 16.2 |
| Write API | `POST /api/runs/{id}/rollback` | 16.3 |
| Cascade | `lineage_row_edges` + `lineage_column_map` walk | 16.2 |
| UI | `frontend/templates/pages/run_view.html` rollback card | 16.3 |
| CloudEvent | `pointlessql.rollback.executed` | 16.3 |
| Audit | second `agent_run_operations` row with `op_name='rollback'` | 16.0 + 16.1 |

## Preconditions

1. **PointlesSQL** + **soyuz-catalog** running per the
 [Hermes-Medallion playbook](hermes-medallion.md) preconditions.
2. The Medallion notebook
 [`notebooks/hermes_medallion.py`](https://github.com/FloHofstetter/PointlesSQL/blob/main/notebooks/hermes_medallion.py)
 has been replayed at least once so silver and gold tables
 exist with `lineage_row_edges` / `lineage_column_map`
 populated. (If you've never run it, replay it before this
 playbook.)
3. The admin auth cookie is loaded in Firefox (login at
 `/auth/login` first).

## Walkthrough — happy path

1. **Pre-flight**: `rm -rf /tmp/pql_demo_warehouse`.
2. **Replay the notebook once**. Capture the resulting run id
 (visible at the top of `/runs`) — call it `RUN_A_ID`.
3. **Probe the preview API** to confirm the `delta_version_*`
 fields are populated:
 ```bash
 curl -fsS -b "$AUTH_COOKIE" \
 "http://127.0.0.1:8000/api/runs/$RUN_A_ID/rollback-preview?target=main.silver.orders" \
 | jq '.'
 ```
 Expected:
 - `is_stale: false` (no later runs touched silver yet)
 - `op_id` non-null (single op write)
 - `delta_version_before` and `delta_version_after` both ints
 - `downstream_warnings` lists `main.gold.daily_revenue` (or
 equivalent — depends on the notebook's gold layer).
4. **Headful Firefox**:
 1. Navigate to `/runs/RUN_A_ID`.
 2. Confirm the **"Rollback this run"** card is visible (red
 header, dropdown + button). The card only renders for
 admins on runs that have at least one write op — non-admin
 sessions will see a card-free run page.
 3. Pick `main.silver.orders` from the dropdown, click
 **Preview rollback…**.
 4. Modal opens. Verify:
 - **Target version restored: 0** (or whichever version the
 op recorded as `delta_version_before`).
 - **Was at v1** (matching `delta_version_after`).
 - **Downstream impact** panel shows `main.gold.daily_revenue`
 with a `(row, N edge(s))` annotation.
 - No staleness warning.
 - **Run rollback** button enabled.
 5. Click **Run rollback**.
 6. Browser redirects to `/runs/{NEW_RUN_ID}` (the spawned
 rollback run). Page shows:
 - status badge `succeeded`.
 - **Operations** tab carries one row, `op_name = rollback`,
 `target_table = main.silver.orders`,
 `delta_version_before = 1`, `delta_version_after = 2`
 (the restore writes a NEW commit, it does not rewind).
 - Console clean (open DevTools and confirm no JS errors
 before navigating away).
5. **DB probe**: confirm the rollback op is on disk:
 ```bash
 sqlite3.data/pointlessql.db <<'SQL'
 SELECT op_name, target_table, delta_version_before, delta_version_after,
 json_extract(params_json, '$.rolled_back_run') AS rolled_back_run
 FROM agent_run_operations
 WHERE op_name = 'rollback'
 ORDER BY id DESC
 LIMIT 1;
 SQL
 ```
 Expected: one row with the correct rolled_back_run id.
6. **CloudEvent probe**:
 ```bash
 sqlite3.data/pointlessql.db <<'SQL'
 SELECT event_type, json_extract(payload_json, '$.data.rolled_back_run_id') AS rolled
 FROM agent_run_events
 WHERE event_type = 'pointlessql.rollback.executed'
 ORDER BY id DESC
 LIMIT 1;
 SQL
 ```
 Expected: exactly one row with the right `rolled_back_run_id`.

## Walkthrough — stale path (force flag required)

1. **Pre-flight**: keep the warehouse from the happy-path replay
 (do NOT `rm -rf`).
2. **Replay the notebook a second time** — call the new run
 `RUN_B_ID`. This second pass writes to silver again, moving
 the Delta version forward. Capture `RUN_A_ID` from the
 _first_ replay (still visible at the bottom of `/runs`).
3. **Headful Firefox**:
 1. Navigate to `/runs/RUN_A_ID`.
 2. Click the rollback card's dropdown → pick
 `main.silver.orders` → **Preview rollback…**.
 3. Modal renders the ⚠ stale warning panel. Verify:
 - "table has moved to v…" matches the post-replay version.
 - The mandatory `[ ] I understand intervening writes will
 be lost` checkbox is present.
 - **Run rollback** button is **disabled** until the box is
 ticked.
 4. Tick the checkbox. Submit button enables.
 5. Click **Run rollback** → redirect to the spawned run.
 6. New rollback run records `allow_force=true` in
 `params_json`:
 ```bash
 sqlite3.data/pointlessql.db <<'SQL'
 SELECT json_extract(params_json, '$.allow_force') AS forced
 FROM agent_run_operations WHERE op_name='rollback'
 ORDER BY id DESC LIMIT 1;
 SQL
 ```
 Expected: `1` (boolean true serialised as JSON).

## Walkthrough — refusal modes (CLI-only)

These never reach the modal because the route raises before the
preview returns. A quick smoke that the API mappings hold:

| Refusal | Curl shape | Expected status |
| --- | --- | --- |
| `target` missing/blank | `-d '{}'` | 422 |
| run/target combination unknown | unknown run uuid | 404 |
| run created the table (`delta_version_before` is None) | rollback the very first `pql.write_table` of the notebook | 422 with "drop" in body |
| stale without force | second replay then rollback original run via API | 422 with "stale" in body |

## Stop conditions

- **Modal opens but `current_version` shows `null`**: the route's
 `_read_delta_version` couldn't reach soyuz. Confirm soyuz is
 up; otherwise the rollback would silently bypass staleness
 detection. Fix at the source rather than papering over.
- **`/runs/{NEW_RUN_ID}` shows status `failed`** after a happy-
 path attempt: open the DB and check `denied_reason` on the
 rollback run row — that's the message
 `_mark_rollback_run_failed` stamped from the underlying
 exception. Common cause: deltalake-python returned an
 unexpected metrics-dict shape; `restored_file_count` ends up
 ``None`` but should still succeed.
- **CloudEvent missing**: webhook URL is unset (default in dev),
 so the row lands with `outcome='no_destination'`. That is the
 expected dev-mode shape; the row itself should still exist.
- **Rollback card invisible**: confirm `current_user.is_admin`
 is true and the run actually wrote a target via merge / write_
 table / autoload / aggregate. `pql.sql`-only runs have no
 rollback targets.

## Playwright MCP script

Browser-only replay for the happy-path + stale path. The DB / API
probes stay as shell snippets above — the browser steps are:

1. `browser_navigate('http://127.0.0.1:8000/runs/<RUN_A_ID>')`
   — assert the red "Rollback this run" card is visible (admin
   only; non-admin sessions see no card).
2. `browser_select_option(role="combobox", value="main.silver.orders")`
   — pick the target table from the dropdown.
3. `browser_click("Preview rollback…")`
   — `browser_wait_for("Run rollback")` (modal opens).
4. `browser_evaluate('() => document.querySelector(".rollback-target-version").innerText')`
   — assert it matches the `delta_version_before` from the
   preview API.
5. `browser_click("Run rollback")`
   — assert URL becomes `/runs/<NEW_RUN_ID>` and status badge
   reads `succeeded`.
6. `browser_click("Operations")` (tab)
   — assert one row whose `op_name` cell reads `rollback` and
   `delta_version_after = delta_version_before + 1`.
7. **Stale path** —
   `browser_navigate('http://127.0.0.1:8000/runs/<RUN_A_ID>')`
   after a second notebook replay, then
   `browser_click("Preview rollback…")` — assert the ⚠ stale
   warning panel is visible and the `Run rollback` button is
   disabled.
8. `browser_click(".form-check-input")` (the staleness checkbox)
   — assert `Run rollback` becomes enabled.
9. `browser_click("Run rollback")` — assert the spawned run's
   `params_json.allow_force` is `true` (DB probe in shell block
   above).

## Bug tail

(none yet — is the first replay)
