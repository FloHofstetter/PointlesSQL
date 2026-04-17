# Dashboards + run-compare walkthrough

Exercises the Sprint 28 dashboards surface (list, create modal, detail,
Refresh, sidebar tree) and the run-compare view launched from a
papermill job's detail page. Runs as the closing playbook for
Phase 8 (Notebook-as-job).

## Preconditions

- Stack up with the e2e overlay; seed script run (Sprint 22).
- `admin@pql.test` and `user@pql.test` exist (from `auth.md`).
- `notebook-jobs.md` ran through Part A at least once, so
  `/app/notebooks/smoke.ipynb` exists in the workspace and a
  papermill-kind job (`smoke_papermill`, or whatever name the
  notebook-jobs playbook created) has produced **at least two**
  `status=succeeded` runs. The run-compare step depends on this.
- Currently logged in as `admin@pql.test`.

## Walkthrough

### Part A — navbar + empty list

1. **Navigate to `/dashboards`**.
   - Action: `browser_navigate('http://127.0.0.1:8000/dashboards')`
   - Assert: URL is `/dashboards`, "Dashboards" link in the navbar
     is active, the "New dashboard" button is visible (admin gate).
   - Assert: sidebar on the left shows the "Dashboards" header
     and the empty-state "No dashboards yet." message.

### Part B — create dashboard via modal

2. **Open the create modal**.
   - Action: click the "New dashboard" button.
   - Assert: `#createDashboardModal` becomes visible.

3. **Fill the modal and submit**.
   - Action: drive the Alpine state directly:
     ```js
     const d = Alpine.$data(document.querySelector('#createDashboardModal'));
     d.slug = 'smoke-overview';
     d.title = 'Smoke overview';
     d.description = 'Output-only view of the smoke notebook.';
     d.notebookPath = 'smoke.ipynb';
     const papermillJobId = /* look up from the <select>: first
         option value that is the papermill job you seeded */;
     d.jobId = papermillJobId;
     await d.submit();
     ```
   - Assert: `d.error === null`, browser navigates to
     `/dashboards/smoke-overview`.
   - Assert: `fetch('/api/dashboards').then(r => r.json())` returns
     a one-element list with the new row, `owner_id` set to the
     admin's user id.

### Part C — detail page renders code-hidden output

4. **On `/dashboards/smoke-overview`**, verify the output card.
   - Assert: the "About" card shows title, description, notebook
     path, and the bound job link.
   - Assert: the "Output" card contains an iframe whose `src`
     ends in `/runs/{latest_run_id}/notebook?exclude_input=true`.
   - Action (inside the iframe — use
     `browser_evaluate` with the iframe's contentDocument or
     `browser_frame_evaluate` if available):
     ```js
     const iframe = document.querySelector('iframe[title="Dashboard output"]');
     const doc = iframe.contentDocument;
     // nbconvert's lab template wraps each code cell in
     // .jp-InputArea — exclude_input=true removes these entirely.
     return doc.querySelectorAll('.jp-InputArea').length;
     ```
   - Assert: returns `0`. Output cells (`.jp-OutputArea`) should be
     present — count > 0.

### Part D — Refresh button triggers a new run

5. **Click "Refresh"**.
   - Action: click the Refresh button in the header.
   - Assert: fetch returns 2xx, page reloads.
   - Assert: `fetch('/api/jobs/{papermillJobId}/runs/{latest}/...')`
     shows a new `trigger=manual` run within ~5 s.
   - Assert: after the new run completes successfully, a page
     reload shows the iframe `src` pointing at the new run id
     (higher integer).

### Part E — sidebar tree

6. **After creating a second dashboard** (`slug=empty-one`,
   `notebookPath=something.ipynb`, `job_id=null`), reload
   `/dashboards`.
   - Assert: the left sidebar lists both dashboards.
   - Assert: `empty-one` has the `UNBOUND` badge (null `job_id`).
   - Action: click `empty-one` in the sidebar.
   - Assert: URL → `/dashboards/empty-one`, the detail page shows
     the empty-state card ("No job bound yet"), no Refresh button.
   - Assert: `sessionStorage.getItem('pql.dashboards')` returns a
     serialized array of two elements — the cache key is warm.

### Part F — non-admin visibility

7. **Log out and log in as `user@pql.test`** (non-admin).
   - Action: sign out via the navbar dropdown → sign in again.
   - Navigate to `/dashboards`.
   - Assert: the table lists both dashboards (consumers see
     everything — dashboards are a publishing surface).
   - Assert: the "New dashboard" button is **absent**.
   - Action: navigate to `/dashboards/smoke-overview`.
   - Assert: the "Refresh" and "Open job" buttons in the header
     are **absent**. The output iframe still renders.
   - Assert (negative): `fetch('/api/dashboards', {method:'POST',
     body: JSON.stringify({slug:'x', title:'x', notebook_path:'x'})})`
     returns `403` with `error.code` set to the admin-gate code.
   - Assert (negative): `fetch('/api/dashboards/smoke-overview/refresh',
     {method:'POST'})` returns `403`.

### Part G — run-compare

Log back in as `admin@pql.test` before this part.

8. **On the papermill job's detail page** (the one bound to
   `smoke-overview`), find the "Compare runs" card.
   - Assert: the card is present only when ≥ 2 completed runs
     exist. Default selection is the two most recent.
   - Action: pick a Left and Right from the two `<select>`s,
     click "Compare".
   - Assert: URL navigates to
     `/jobs/{id}/runs/{left}/compare?to={right}`.
   - Assert: the page shows two side-by-side cards, each with a
     run metadata `<dl>` and an iframe pointing at
     `/jobs/{id}/runs/{rid}/notebook`. The code-visible render
     (no `exclude_input`) is used for diffing.
   - Assert (negative): hand-craft a URL with `to=` pointing at a
     run id that belongs to a **different** job. `browser_navigate`
     should land on a 404 page, not render the foreign run.

## Playwright MCP script

```text
# Part A
browser_navigate('http://127.0.0.1:8000/dashboards')

# Part B
browser_click('[data-bs-target="#createDashboardModal"]')
browser_evaluate(async () => {
    const d = Alpine.$data(document.querySelector('#createDashboardModal'));
    d.slug = 'smoke-overview';
    d.title = 'Smoke overview';
    d.description = 'Output-only view of the smoke notebook.';
    d.notebookPath = 'smoke.ipynb';
    // pick the first papermill option id from the modal's <select>
    const opt = document.querySelector('#createDashboardModal select option[value]:not([value=""])');
    d.jobId = opt ? opt.value : '';
    await d.submit();
})

# Part C — verify iframe has no .jp-InputArea cells
browser_evaluate(() => {
    const f = document.querySelector('iframe[title="Dashboard output"]');
    return f.contentDocument.querySelectorAll('.jp-InputArea').length;
})  # expect 0

# Part D — click Refresh, wait, reload, inspect latest run id

# Part E — create a second dashboard via fetch, reload list,
# inspect sidebar entries + sessionStorage

# Part F — log out, log in as user@pql.test, repeat visibility asserts

# Part G — on /jobs/{papermillJobId}, pick Left+Right, click Compare
browser_click('button:has-text("Compare")')
# then assert URL + iframe count == 2
```

## Found bugs

_No bugs surfaced yet — this section gets filled in when the live
Playwright replay happens during sprint close._

When replaying, use the `BUG-28-NN` prefix for any defects found. If
the fix is trivial, land it in the same commit as this playbook and
record the commit hash here. If non-trivial, add a TODO with a named
fix location at the bottom of the relevant playbook section.
