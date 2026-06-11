# Ingest streaming walkthrough

> **Mode:** `browser + curl` · **Surface:** /ingest/sources + /api/ingest/streams

End-to-end exercise of the auto-loader + streaming ingest surface:
flip a file-based ingest mapping to the auto-loader pull mode and
verify only new files land on re-pull, then stream JSON events
straight into a Delta table through the direct-write API and
force-flush them. The stream endpoints are the same ones event
producers script against; the cockpit only configures the pull side.

## Preconditions

- E2E stack up:
  ```bash
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml up -d
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml \
    exec pointlessql python /app/scripts/seed-e2e.py
  ```
- [`auth.md`](auth.md) ran first (admin@pql.test exists and is
  signed in).
- The stream router (`pointlessql/api/ingest_stream_routes.py`) is
  registered on the app — it ships unregistered; Part B answers 404
  until the wiring lands.
- A target table for streaming exists in the catalog with a
  registered `storage_location` (the seed script's bronze table
  works; any UC table the admin holds `MODIFY` on does).
- Playwright MCP Firefox (`--browser firefox`); see
  [admin-console.md](admin-console.md) for the stale-profile-lock
  recovery note.

## Walkthrough

### Part A — Auto-loader pull mode (5 steps)

1. **Create a file-based source**.
   - Action: `browser_navigate('http://127.0.0.1:8000/ingest/sources')`,
     click "New source", pick kind `file_upload`, name
     `e2e-autoloader`, path `/data/e2e-autoloader/*.csv` (a
     container-local directory pre-seeded with one CSV); save.
   - Assert: redirect to the source detail page with the
     `file_upload` badge next to the heading.

2. **Flip the mapping to Auto loader**.
   - Action: open the *Mappings* tab, press "Refresh source", check
     the discovered row, set Target FQN
     `main.bronze.autoloader_events`, and in the new **Pull mode**
     select (only rendered for `file_upload` / `parquet_glob`
     sources; `aria-label` is `Pull mode for <table>`) choose
     "Auto loader". Click "Save mappings".
   - Assert: toast "1 mapping(s) saved."; re-fetching
     `/api/ingest/sources/{id}` shows the mapping carrying
     `"pull_mode": "auto_loader"`.

3. **First pull ingests the seed file**.
   - Action: click "Pull now"; open the *Runs* tab.
   - Assert: the latest pull row is `ok` with the seed file's row
     count; the manual-pull JSON response carries
     `"files_processed": 1` and `"mode": "auto_loader"`.

4. **Re-pull without new files is a no-op**.
   - Action: click "Pull now" again.
   - Assert: the new run reports 0 rows (`files_processed: 0`) —
     the processed-files registry filtered the already-ingested
     file out.

5. **Only the new file lands on the next pull**.
   - Action: drop a second CSV into the watched directory
     (`docker compose ... exec pointlessql sh -c 'printf
     "id\n42\n" > /data/e2e-autoloader/new.csv'`), then "Pull now".
   - Assert: the run reports exactly the new file's rows; querying
     `main.bronze.autoloader_events` in the SQL editor shows the
     union of both files with no duplicates of the first one.

### Part B — Direct-write stream API (4 steps)

6. **Stream a batch of events**.
   - Action (replace `$COOKIE` with the signed-in session cookie,
     e.g. exported from the browser devtools):
     ```bash
     curl -s -X POST \
       -H 'Content-Type: application/json' \
       -b "pql_session=$COOKIE" \
       -d '{"rows": [{"id": 1, "kind": "click"}, {"id": 2, "kind": "view"}]}' \
       http://127.0.0.1:8000/api/ingest/streams/main/bronze/events
     ```
   - Assert: `{"accepted": 2, "buffered": 2}` — the rows sit in the
     in-process buffer (they auto-flush at 500 rows or after ~5
     seconds even without step 7).

7. **Force-flush the buffer**.
   - Action:
     ```bash
     curl -s -X POST -b "pql_session=$COOKIE" \
       http://127.0.0.1:8000/api/ingest/streams/main/bronze/events/flush
     ```
   - Assert: `{"flushed": 2}`; `SELECT * FROM main.bronze.events`
     in the SQL editor returns both events. A second flush answers
     `{"flushed": 0}`.

8. **Verify the guardrails**.
   - Action: repeat step 6 with 1001 rows in one request; then once
     more without the cookie.
   - Assert: the oversized batch answers 422 with the per-request
     cap in the message; the anonymous call answers 401/403 and
     nothing new lands in the table.

9. **Verify the audit trail carries counts, not payloads**.
   - Action: open `/admin/audit`.
   - Assert: the newest rows include `ingest_stream.appended` and
     `ingest_stream.flushed` on target `table:main.bronze.events`
     whose detail shows row *counts* only — the strings `click` /
     `view` appear nowhere. Console stays free of errors for the
     whole walkthrough.
