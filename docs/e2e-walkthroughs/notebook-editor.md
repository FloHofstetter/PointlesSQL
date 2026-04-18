# Native notebook editor walkthrough

Verifies the Phase-12.6 Monaco-based notebook editor end-to-end —
load + save round-trip, kernel execute, output persistence across
page reload, kernel restart, Pyright LSP (completion + hover),
Variable Explorer, Insert-from-catalog modal, and the retired-
JupyterLab surface.  Replaces the Sprint-23 `notebook.md`
playbook (the embedded JupyterLab iframe retired in Sprint 63).

## Preconditions

- Stack up with the e2e overlay; admin user logged in.
- `notebooks/` is writable by the PointlesSQL process (default
  for both local dev and the Docker overlay).
- soyuz-catalog reachable on :8080 (Insert-from-catalog step
  exercises `/api/tree`).
- **Browser**: Firefox via Playwright-MCP (or the bundled
  `chrome-for-testing` — see `CLAUDE.md` for why the system
  Chrome channel flakes).  Monaco's AMD loader needs modern
  JS; all target browsers are fine.

## Walkthrough

### Part A — First open: UUID mint + autosave

1. **Landing route**.
   - Action: `browser_navigate('http://127.0.0.1:8000/notebook')`
   - Assert: 302 redirect to
     `/notebook/editor?path=scratch.py`, page title contains
     `Editor · scratch.py`, navbar "Notebook" link is active.

2. **Monaco boots + single empty cell**.
   - Action: `browser_wait_for(time=2)` (Monaco AMD loader +
     vendored bundle take ~1 s on a warm cache).
   - Assert: the `.pql-nbedit-editor` div has a Monaco editor
     instance; the buffer contains exactly one `# %%
     pql_cell_id="…"` marker (empty cell scaffold from
     `notebook_editor_page` when the file doesn't exist yet).

3. **Toolbar pills**.
   - Action: `browser_snapshot()` of the `.pql-nbedit-toolbar`.
   - Assert:
     - `Kernel ready` (green) within ~3 s of load — ipykernel
       starts on first WS connect.
     - `Pyright ready` (green) within ~3 s — pyright-langserver
       starts with its Node bundle.
     - `Saved` (green) — the file was just materialised with
       one cell on first save.

4. **First save materialises the file**.
   - Action (shell, adjust path):
     ```bash
     cat notebooks/scratch.py
     ```
   - Assert: a jupytext Percent header is present, followed by
     one `# %% pql_cell_id="<UUID>"` marker and zero source
     lines.  The UUID regex is `[0-9a-fA-F-]{36}`.

### Part B — Execute, outputs, persistence

5. **Type code into the cell**.
   - Action: `browser_click` into the editor area, then
     `browser_type('import pandas as pd\ndf = pd.DataFrame({"a":[1,2,3]})\ndf')`.
   - Assert: the `Saved` pill flips to `Unsaved changes`
     (yellow) on the first keystroke, back to `Saved` 1.5 s
     after the last keystroke (Sprint-58 autosave debounce).

6. **Run the cell (Shift+Enter)**.
   - Action: place cursor inside the cell, press `Shift+Enter`.
   - Assert:
     - A Monaco view zone appears directly beneath the cell.
     - Within ~2 s the view zone contains a pandas-styled HTML
       table (first 3 rows of `df`) — the Sprint-60 rich-mime
       renderer for `text/html`.
     - The "Kernel ready" pill briefly flashes "busy" via the
       internal `executingCells` state; scripted replay can
       skip this check because timing is tight.

7. **Outputs persist across reload**.
   - Action: `browser_navigate` away (e.g. to `/`) and back to
     `/notebook/editor?path=scratch.py`.
   - Assert: before the kernel WS opens, the rendered pandas
     HTML is *already* visible in the output zone — the
     Sprint-60 replay path runs synchronously on Alpine
     mount, so there is no "empty view → output arrives"
     flicker.  The Network panel shows no new kernel execute
     in this interval.

8. **Clear-cell button purges row + DOM**.
   - Action: click `Clear cell`.
   - Assert: the view zone collapses to zero height; reload the
     page — the output zone stays empty (Sprint-60 persistence
     hook deleted the row).

9. **Restart kernel wipes every session row**.
   - Prereq: re-run the cell so there's at least one output.
   - Action: click `Restart`.
   - Assert:
     - Toolbar pill briefly shows `Restarting…` → `Kernel ready`.
     - Every view zone in the editor is empty immediately
       after restart.
     - Reloading the page does not repopulate outputs (the
       Sprint-60 restart path clears all persisted rows for
       the outgoing session).

### Part C — Pyright LSP

10. **Completion on `json.`**.
    - Action: add a new code cell (toolbar `Add cell` button),
      type `import json\njson.` and let the cursor rest
      after the dot.
    - Assert: Monaco's completion widget opens within ~500 ms
      showing at least `dumps`, `loads`, `dump`, `load` in the
      suggestions list.  Each entry's "detail" column carries
      pyright's type signature.

11. **Hover on `json.dumps`**.
    - Action: type `json.dumps(...)` somewhere, hover the
      `dumps` identifier.
    - Assert: Monaco's hover popover opens showing pyright's
      signature (`dumps(obj: Any, *, skipkeys: bool = False, ...) -> str`)
      and the docstring.

12. **Diagnostic on a bad reference**.
    - Action: type `undefinedsymbol_xyz` on a line of its own.
    - Assert: within ~1 s a red squiggle appears under the
      identifier.  Hovering it shows pyright's diagnostic
      message ("undefinedsymbol_xyz" is not defined).

### Part D — Insert from catalog

13. **Open the modal**.
    - Action: press `Ctrl+Shift+I` (or click the `Catalog`
      toolbar button, or invoke the command palette entry
      "PointlesSQL: Insert from catalog…").
    - Assert: the Bootstrap modal overlays the editor; the
      filter input is focused; the list populates within
      ~500 ms from `/api/tree`.

14. **Filter + pick**.
    - Action: type `main` into the filter; click the first
      remaining entry.
    - Assert: modal closes; the editor's cursor line now
      contains `pql.read_table("main.<schema>.<table>")`
      (exact table name depends on the seeded catalog).
    - Assert: Monaco reports no Pyright diagnostic on the
      new line (PQL is importable).

### Part E — Variable Explorer

15. **Open the sidebar**.
    - Action: click the `Variables` toolbar button (or the
      "Toggle variable explorer" command-palette entry).
    - Assert: right-side sidebar expands.  If no user cells
      have run since the last restart, the sidebar shows
      "No user variables yet. Run a cell that defines one."

16. **DataFrame row**.
    - Prereq: run the Part-B cell that defined `df`.
    - Action: observe the sidebar auto-refresh on idle
      (50 ms scheduled debounce per `_handleKernelFrame`).
    - Assert: a row named `df` with type `DataFrame`, shape
      `[3, 1]`, and a 3-row `head()` HTML preview (the
      `.pql-nbedit-vars-df` class is scoped in the template
      so the preview inherits the sidebar styles).

17. **Scalar row**.
    - Action: add a cell `answer = 42`, run it.
    - Assert: sidebar now has an `answer` row with type `int`
      and `repr` `42`.

### Part F — Post-retirement surfaces

18. **No JupyterLab iframe anywhere**.
    - Action: `browser_evaluate(() => document.querySelectorAll('iframe').length)`
      on both `/` and `/jobs/<any-papermill-job>`.
    - Assert: zero iframes matching `src*="lab/"` on the
      home + catalog + jobs pages.

19. **`/api/jupyter/status` is gone**.
    - Action: `fetch('/api/jupyter/status').then(r => r.status)`
    - Assert: `404` (the route was removed in Sprint 63; any
      future re-introduction would need to pass through a
      new route handler).

20. **Sprint-26 output card is single-view**.
    - Action: navigate to `/jobs/<papermill-job>` with a
      completed run.
    - Assert: the output-artifacts card header has no
      `Rendered / JupyterLab` toggle — just the card title +
      run number.  The "Download" button on the run row
      hits `/jobs/{id}/runs/{rid}/notebook/download?format=ipynb`.

21. **Sprint-34 open-in-notebook returns editor_url**.
    - Action: from a UC table detail page, admin-click "Open
      in notebook".
    - Assert: the browser navigates to
      `/notebook/editor?path=scratch/<generated>.py` (not to a
      JupyterLab tree URL).  The scaffolded file contains
      a markdown header cell + a code cell with
      `pql.table("cat.schema.tbl")` + `df.head()` — jupytext
      Percent format with two `pql_cell_id="<UUID>"` markers.

22. **Papermill schedules a `.py` notebook** (optional — needs
    the scheduler overlay).
    - Action: from `/jobs`, create a papermill job with
      `notebook_path: scratch.py`, Run now.
    - Assert: the run transitions running → succeeded; a new
      `notebooks/runs/<run_id>.ipynb` appears on disk; the
      Sprint-63 jupytext-convert temp
      `notebooks/runs/<run_id>.input.ipynb` does **not**
      exist after the run (the `finally` block unlinked it).

## Found bugs

Record any BUG-64-NN entries here in the same shape as Sprint 22
/ Sprint 23's close-outs: diagnosis + fix location, or TODO
reference when the fix lives in a follow-up commit.

## What worked on the first try

- Part A (first open + UUID mint + autosave flush) — the
  Sprint-58 + Sprint-58-followup paths compose cleanly without
  a flash of "unsaved" on foreign-notebook open.
- Part B persistence — Sprint-60's replay-on-mount paints
  outputs before the WS handshake completes, so there is no
  visible empty-then-populated flicker.
- Part C completion + hover + diagnostics against `json` and
  an undefined symbol — pyright's bundled Node binary starts
  in ~1 s on a warm cache.
- Part D Insert-from-catalog round-trip — the Ctrl+Shift+I
  binding fires even from inside a focused Monaco instance
  because the command is registered via `editor.addAction`
  rather than a bare document-level hotkey.
- Part F retirement surfaces — the only iframe left in the app
  is the Sprint-26 papermill output viewer (which uses
  nbconvert HTML, not JupyterLab).
