# Notebook Operations — end-to-end walkthrough

> **Mode:** browser (Playwright MCP replay).
>
> Surface: Phase 67 — Schedule-from-Notebook + Parametrized runs +
> Run-Once + Variable Inspector + in-editor Jobs panel.
> Requires Phase 66 (live notebook editor) to be running.

Replays the surface end-to-end: declare a parameters
cell, schedule the notebook on cron, trigger a one-shot run with
overrides, watch the variable inspector refresh, and verify the
run appears in `/jobs` plus the in-editor panel.

## 0. Preconditions

- PointlesSQL running locally (`uv run pointlessql`).
- Logged in as admin (`docs/e2e-walkthroughs/auth.md`).
- At least one notebook exists under `/notebooks/workspace`.  If
  not, create `workspace/etl-demo.py` via the workspace browser.

## 1. Declare a parameters cell

1. Navigate to `/notebooks/edit/workspace/etl-demo.py`.
2. Click `+ Code cell` in the bottom toolbar.
3. Type `cutoff_date = "2026-05-01"` into the new cell.
4. Click the cell-type dropdown on the cell toolbar (current label
   "code") → click **Mark as parameters**.  The dropdown label flips
   to `PARAMS`; the cell header now shows the params badge.
5. Add a second cell: `print(f"ETL up to {cutoff_date}")`.
6. Cmd/Ctrl+S to save.  Verify the on-disk file (open in VSCode or
   `cat`) carries `# %% tags=["parameters"]` above the first cell.

The top toolbar should also show a `1 param` badge next to the
notebook path.  If it does not appear immediately, refresh — the
`loadParameters` call fires after the first save.

## 2. Run-once with parameter override

1. Click the **Run as job** button in the toolbar (the lightning
   icon).
2. The Run-Once modal opens with a parameter form pre-populated
   from `papermill.inspect_notebook`.
3. Type `2026-05-10` into the `cutoff_date` input.
4. Click **Run**.  The status text becomes `Run #<id> started —
   polling…`.
5. Within a few seconds the status flips to `Run #<id> succeeded.`
6. Close the modal.

The browser polled `GET /api/jobs/{id}/runs` every 0.5–5 s
(exponential backoff) until the run reached a terminal status.

## 3. Inspect the run in `/jobs`

1. Open `/jobs` in a new tab.
2. Filter the table by name = `notebook-runonce`.
3. Click the freshly-created job → `/jobs/{id}`.
4. The "Runs" panel shows one row with status `succeeded`,
   trigger `manual`.
5. Click the run → output replay.  The cell that wrote
   `ETL up to 2026-05-10` is captured (output bridged from the
   `.ipynb` papermill produced).

## 4. Schedule the notebook on cron

1. Switch back to the notebook editor tab.
2. Click the **Schedule** button (clock icon).
3. Fill the form:
   - Job name: `daily-etl-demo`.
   - Cron: `0 5 * * *` (5 AM daily — the helper text confirms
     "At 05:00").
   - Parameters: leave `cutoff_date` empty so the on-disk default
     wins.
4. Click **Schedule**.  The toast confirms the job was created.

Optional sanity check: open `/jobs` and confirm `daily-etl-demo`
appears as a paused-false papermill job.

## 5. Browse the in-editor Jobs panel

1. In the editor, click the **Jobs** toolbar button.
2. The collapsible panel below the toolbar lists:
   - **Scheduled jobs** — `daily-etl-demo @ 0 5 * * *` (with last-
     run status badge if the cron has fired yet).
   - **Recent runs** — the manual one-shot from step 2.

Both lists are pulled from `GET /api/notebooks/jobs?path=…` which
joins through the `notebook_job_link` index table; every link was
written opportunistically by the create-job + run-once handlers.

## 6. Variable Inspector

1. Click the **Variables** toolbar button.  The floating side-pane
   appears at the right edge.
2. Run any code cell that defines variables, e.g. a new cell
   `df = [1, 2, 3, 4]` followed by Shift+Enter.
3. The Variables pane refreshes within ~100 ms with an entry
   `df : list[4]` showing the truncated repr.
4. Click the `df` row.  A detail block expands below the list
   showing the full repr (and `head(5).to_html()` rendered as a
   table when the variable is a pandas-like object).
5. Click the refresh icon at the top of the pane to force a
   re-snapshot any time without running another cell.
6. Click the X to close the pane.

Variable snapshots are routed via the WS pump's custom-MIME branch
(`application/x-pql-vars+json`) and never land in
`notebook_outputs` — they are transient and re-emitted after every
cell run automatically.

## 7. Verify on-disk marker round-trip

Open `workspace/etl-demo.py` in VSCode or run `cat` — the file
must contain:

```python
# %% tags=["parameters"]
cutoff_date = "2026-05-01"

# %%
print(f"ETL up to {cutoff_date}")
```

If you toggle the cell back to non-params via the toolbar dropdown
and save, the `tags=["parameters"]` segment disappears from disk.
This is the canonical jupytext shape — papermill, the inspect
endpoint, and the Schedule/Run-Once modals all read it via the
same `papermill.inspect_notebook` path.

## Cleanup

- Pause the `daily-etl-demo` job from `/jobs` so it does not fire
  in the background.
- The one-shot `notebook-runonce:…` job stays as an audit anchor;
  no cleanup needed.

## Phase-67 contract pinned by this walkthrough

- Marker grammar accepts `tags=["parameters"]` on any cell type.
- `cell.tags` is metadata; `compute_content_hash` ignores it.
- `papermill.inspect_notebook` works on `.py` via in-memory
  jupytext + nbformat conversion.
- Schedule modal posts to existing `POST /api/jobs` with
  `kind="papermill"`; no notebook-specific create-job endpoint.
- Run-once creates a paused permanent Job + fires
  `execute_run` async; polling reaches terminal via
  `GET /api/jobs/{id}/runs`.
- `notebook_job_link` is written opportunistically; the
  in-editor panel reads through it.
- Variable Inspector custom MIME (`application/x-pql-vars+json`)
  is routed via the WS pump as a `variable_snapshot` notify
  rather than a kernel_message frame.
- Papermill outputs are bridged to `notebook_outputs` with
  `kernel_session_id = "job:<run_id>"` so the editor reload-
  replay also surfaces job artefacts.
