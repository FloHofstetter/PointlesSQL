/**
 * Per-cell pinned-fact chip strip (Phase 97 Rest UI).
 *
 * Backend ``GET /api/notebooks/facts/bulk`` returns the active facts
 * for a list of cell ``content_hash`` values in one request, so a
 * 50-cell notebook costs one HTTP call instead of 50.  Same dodge as
 * :func:`installCellLineage` — methods live on the outer
 * ``notebookEditor`` state so the inner per-cell template can call
 * ``factsFor(cell)`` from inside ``x-for cell in cells`` without
 * crossing a nested-x-data boundary.
 *
 * Lookup is keyed by ``cell.content_hash`` because that is the join
 * key the fact rows already record on every cell-output pin
 * (revision-level pins have no entry here — they surface in the
 * revision drawer's pin badge instead).
 */

export function installCellFacts(state) {
 state.cellFactsBulk = {};
 state.cellFactsLoaded = false;
 state.cellFactsLoading = false;
 state.cellFactsError = '';

 /**
  * Return active cell-output facts for one cell, or ``[]`` when none
  * are pinned.  Reads by ``content_hash`` so a cell re-saved with the
  * same source keeps its chips lit.
  */
 state.factsFor = function (cell) {
  if (!cell || !cell.content_hash) return [];
  return this.cellFactsBulk[cell.content_hash] || [];
 };

 /**
  * Fetch ``{content_hash: [fact_envelope, ...]}`` for every cell
  * currently in the editor.  Refreshed implicitly on save (called
  * from ``installPersistence``) + explicitly on first load.
  */
 state.loadCellFactsBulk = async function () {
  if (!this.path) return;
  const hashes = (this.cells || [])
  .map((c) => c.content_hash)
  .filter(Boolean);
  if (hashes.length === 0) {
   this.cellFactsBulk = {};
   this.cellFactsLoaded = true;
   return;
  }
  this.cellFactsLoading = true;
  this.cellFactsError = '';
  try {
   const qs = new URLSearchParams({
    notebook_path: this.path,
    cell_content_hashes: hashes.join(','),
   });
   const res = await window.pqlApi.fetch(
    `/api/notebooks/facts/bulk?${qs.toString()}`,
    { silent: true },
   );
   if (res.ok && res.data) {
    this.cellFactsBulk = res.data.facts || {};
    this.cellFactsLoaded = true;
   } else {
    // Non-fatal — chip strip stays empty.
    this.cellFactsError = (res.data && res.data.detail) || `HTTP ${res.status}`;
   }
  } catch (err) {
   this.cellFactsError = (err && err.message) || String(err);
  } finally {
   this.cellFactsLoading = false;
  }
 };

 /**
  * Open the cell-output pin dialog rooted on the revisions drawer.
  *
  * Cell-output facts pin a *specific revision's* version of the
  * cell, so we need a fresh revision UUID before the dialog renders.
  * The simplest path: snapshot the notebook (idempotent on canonical
  * hash) and surface the resulting revision UUID in
  * ``state.cellFactsDialog`` together with the cell's content_hash.
  * The user then types title + optional description and confirms.
  *
  * The dialog itself lives in the revisions-panel partial (same
  * outer-scope as the revision-drawer's revision-pin button) so the
  * nested-x-data trap stays dodged.
  */
 state.cellFactsDialog = {
  open: false,
  cellContentHash: '',
  title: '',
  description: '',
  busy: false,
  error: '',
 };

 state.openCellFactDialog = async function (cell) {
  if (!cell || !cell.content_hash) return;
  this.cellFactsDialog = {
   open: true,
   cellContentHash: cell.content_hash,
   title: '',
   description: '',
   busy: false,
   error: '',
  };
  // Make sure the revisions drawer is open so the dialog is visible.
  if (!this.revisions.open) {
   await this.toggleRevisionsPanel();
  }
 };

 state.cancelCellFactDialog = function () {
  this.cellFactsDialog.open = false;
  this.cellFactsDialog.cellContentHash = '';
  this.cellFactsDialog.title = '';
  this.cellFactsDialog.description = '';
  this.cellFactsDialog.error = '';
 };

 state.confirmCellFactPin = async function () {
  const dlg = this.cellFactsDialog;
  if (!dlg.title || dlg.busy) return;
  dlg.busy = true;
  dlg.error = '';
  try {
   // Step 1: snapshot the current state so the fact points at a
   // concrete revision UUID.  Idempotent on canonical hash.
   const snap = await window.pqlApi.fetch('/api/notebooks/revisions', {
    method: 'POST',
    body: {
     path: this.path,
     message: `auto-snapshot before pin: ${dlg.title}`,
    },
   });
   if (!snap.ok || !snap.data || !snap.data.revision_uuid) {
    dlg.error = (snap.data && snap.data.detail) || `HTTP ${snap.status}`;
    return;
   }
   // Step 2: POST the cell-output pin against that revision.
   const pin = await window.pqlApi.fetch('/api/notebooks/facts', {
    method: 'POST',
    body: {
     revision_uuid: snap.data.revision_uuid,
     title: dlg.title,
     description_md: dlg.description || null,
     cell_content_hash: dlg.cellContentHash,
    },
   });
   if (!pin.ok) {
    dlg.error = (pin.data && pin.data.detail) || `HTTP ${pin.status}`;
    return;
   }
   // Refresh chip strip + revision list so the new pin lights up.
   await Promise.all([this.loadCellFactsBulk(), this.loadRevisions()]);
   this.cancelCellFactDialog();
  } catch (err) {
   dlg.error = (err && err.message) || String(err);
  } finally {
   dlg.busy = false;
  }
 };

 /**
  * Soft-delete the most-recent active fact for a cell (chip click
  * when the cell already has a pin).  When multiple facts exist on
  * the same cell, we unpin the newest one — the older bookmarks
  * stay visible for explainability.
  */
 state.unpinCellFact = async function (cell) {
  const facts = this.factsFor(cell);
  if (facts.length === 0) return;
  const target = facts[0]; // chip strip orders newest-first
  if (!target.fact_uuid) return;
  try {
   const res = await window.pqlApi.fetch(
    `/api/notebooks/facts/${encodeURIComponent(target.fact_uuid)}`,
    { method: 'DELETE' },
   );
   if (!res.ok) {
    this.cellFactsError = (res.data && res.data.detail) || `HTTP ${res.status}`;
    return;
   }
   await this.loadCellFactsBulk();
  } catch (err) {
   this.cellFactsError = (err && err.message) || String(err);
  }
 };
}
