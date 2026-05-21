/**
 * Revision history + cell-diff panel (Phase 97 UI, Wave-D).
 *
 * Backend (Phase 97, 14 pytest) shipped the revision-history surface
 * months ago; the editor's "History" panel render was deferred behind
 * the nested-x-data trap.  This install*-mixin wires the existing
 * REST surface (``/api/notebooks/revisions{,/diff,/{uuid}}``) to a
 * toolbar drawer.
 *
 * The diff renderer is intentionally simple: it groups the diff
 * envelope into Added / Removed / Changed / Moved / Unchanged cards
 * and shows the cell source inline.  A Monaco / CodeMirror-merge
 * side-by-side view can drop in later behind the same panel — the
 * envelope already carries ``old`` + ``new`` source pairs for the
 * Changed bucket so no backend churn is needed.
 *
 * Selection model: clicking a row toggles it as the "left" pin; the
 * next clicked row becomes "right" and triggers the diff fetch.
 * Snapshot button records a fresh revision (idempotent on the
 * canonical hash so re-snapshotting unchanged state is a no-op).
 */

export function installRevisions(state) {
 state.revisions = {
  open: false,
  loaded: false,
  loading: false,
  error: '',
  rows: [],
  selectedLeftUuid: null,
  selectedRightUuid: null,
  snapshotMessage: '',
  snapshotting: false,
  diff: null,
  diffLoading: false,
  diffError: '',
 };

 /**
  * Open / close the revisions drawer.  First open triggers the
  * initial GET so the panel renders with data already populated.
  */
 state.toggleRevisionsPanel = async function () {
  this.revisions.open = !this.revisions.open;
  if (this.revisions.open && !this.revisions.loaded) {
   await this.loadRevisions();
  }
 };

 state.loadRevisions = async function () {
  if (!this.path) return;
  this.revisions.loading = true;
  this.revisions.error = '';
  try {
   const res = await window.pqlApi.fetch(
    `/api/notebooks/revisions?path=${encodeURIComponent(this.path)}&limit=50`,
    { silent: true },
   );
   if (res.ok && res.data) {
    this.revisions.rows = res.data.revisions || [];
    this.revisions.loaded = true;
   } else {
    this.revisions.error = (res.data && res.data.detail) || `HTTP ${res.status}`;
   }
  } catch (err) {
   this.revisions.error = (err && err.message) || String(err);
  } finally {
   this.revisions.loading = false;
  }
 };

 /**
  * POST a new snapshot.  Idempotent on canonical hash; the server
  * returns ``created=false`` when the call collapses to an existing
  * row, which the UI surfaces as "no changes since last snapshot".
  */
 state.snapshotRevision = async function () {
  if (this.revisions.snapshotting || !this.path) return;
  this.revisions.snapshotting = true;
  this.revisions.error = '';
  try {
   const res = await window.pqlApi.fetch('/api/notebooks/revisions', {
    method: 'POST',
    body: { path: this.path, message: this.revisions.snapshotMessage || null },
   });
   if (!res.ok) {
    this.revisions.error = (res.data && res.data.detail) || `HTTP ${res.status}`;
    return;
   }
   this.revisions.snapshotMessage = '';
   await this.loadRevisions();
  } catch (err) {
   this.revisions.error = (err && err.message) || String(err);
  } finally {
   this.revisions.snapshotting = false;
  }
 };

 /**
  * Two-click selection: first click pins ``left``, second click
  * pins ``right`` and fetches the diff envelope.  Third click
  * resets the pair to start over.
  */
 state.selectRevisionForDiff = async function (uuid) {
  if (!uuid) return;
  if (!this.revisions.selectedLeftUuid) {
   this.revisions.selectedLeftUuid = uuid;
   this.revisions.diff = null;
   return;
  }
  if (!this.revisions.selectedRightUuid) {
   if (uuid === this.revisions.selectedLeftUuid) {
    // Clicking the same row twice clears the pin.
    this.revisions.selectedLeftUuid = null;
    return;
   }
   this.revisions.selectedRightUuid = uuid;
   await this.loadRevisionDiff();
   return;
  }
  // Both pinned — third click resets.
  this.revisions.selectedLeftUuid = uuid;
  this.revisions.selectedRightUuid = null;
  this.revisions.diff = null;
 };

 state.clearRevisionDiff = function () {
  this.revisions.selectedLeftUuid = null;
  this.revisions.selectedRightUuid = null;
  this.revisions.diff = null;
  this.revisions.diffError = '';
 };

 state.loadRevisionDiff = async function () {
  const { selectedLeftUuid, selectedRightUuid } = this.revisions;
  if (!selectedLeftUuid || !selectedRightUuid) return;
  this.revisions.diffLoading = true;
  this.revisions.diffError = '';
  try {
   const qs = new URLSearchParams({
    left: selectedLeftUuid,
    right: selectedRightUuid,
   });
   const res = await window.pqlApi.fetch(
    `/api/notebooks/revisions/diff?${qs.toString()}`,
    { silent: true },
   );
   if (res.ok && res.data) {
    this.revisions.diff = res.data;
   } else {
    this.revisions.diffError =
     (res.data && res.data.detail) || `HTTP ${res.status}`;
   }
  } catch (err) {
   this.revisions.diffError = (err && err.message) || String(err);
  } finally {
   this.revisions.diffLoading = false;
  }
 };

 /**
  * Render a naive line-by-line diff between two strings.  Returns
  * an array of ``{kind: 'context' | 'add' | 'remove', text: str}``
  * rows the panel paints as a tidy unified-diff block.  Not as
  * smart as Monaco's tokenisation but good enough for cell-source
  * deltas which are usually small.
  */
 state.renderUnifiedDiff = function (oldText, newText) {
  const a = (oldText || '').split('\n');
  const b = (newText || '').split('\n');
  // Common prefix/suffix trim so the diff focuses on the change.
  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start++;
  let endA = a.length;
  let endB = b.length;
  while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) {
   endA--;
   endB--;
  }
  const rows = [];
  for (let i = 0; i < start; i++) rows.push({ kind: 'context', text: a[i] });
  for (let i = start; i < endA; i++) rows.push({ kind: 'remove', text: a[i] });
  for (let i = start; i < endB; i++) rows.push({ kind: 'add', text: b[i] });
  for (let i = endA; i < a.length; i++) rows.push({ kind: 'context', text: a[i] });
  return rows;
 };
}
