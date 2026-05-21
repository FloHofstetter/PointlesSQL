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
  *
  * After both pins are set the pair is normalised chronologically so
  * L is always the older revision and R the newer one — the diff then
  * reads as "what was added/removed going forward in time", which
  * matches the standard `git diff old new` mental model and makes the
  * red/green colours intuitive.
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
    this.revisions.selectedLeftUuid = null;
    return;
   }
   const [left, right] = this._orderRevisionsChronologically(
    this.revisions.selectedLeftUuid,
    uuid,
   );
   this.revisions.selectedLeftUuid = left;
   this.revisions.selectedRightUuid = right;
   await this.loadRevisionDiff();
   return;
  }
  this.revisions.selectedLeftUuid = uuid;
  this.revisions.selectedRightUuid = null;
  this.revisions.diff = null;
 };

 /**
  * Swap the L and R pins in place and re-fetch the diff so the user
  * can flip the comparison direction without re-pinning from scratch.
  */
 state.swapRevisionPins = async function () {
  const { selectedLeftUuid, selectedRightUuid } = this.revisions;
  if (!selectedLeftUuid || !selectedRightUuid) return;
  this.revisions.selectedLeftUuid = selectedRightUuid;
  this.revisions.selectedRightUuid = selectedLeftUuid;
  await this.loadRevisionDiff();
 };

 /**
  * Return ``[olderUuid, newerUuid]`` based on the ``created_at`` field
  * already loaded into ``this.revisions.rows``.  Falls back to insert
  * order when timestamps are missing or equal.
  */
 state._orderRevisionsChronologically = function (uuidA, uuidB) {
  const lookup = Object.fromEntries(
   this.revisions.rows.map((r) => [r.revision_uuid, r.created_at || '']),
  );
  const tsA = lookup[uuidA] || '';
  const tsB = lookup[uuidB] || '';
  if (tsA && tsB && tsA !== tsB) {
   return tsA < tsB ? [uuidA, uuidB] : [uuidB, uuidA];
  }
  return [uuidA, uuidB];
 };

 /**
  * Per-cell ``+N / -M`` stats for a Changed entry, derived from the
  * same naive line-diff the rendered block uses so the badge matches
  * what the reader sees.
  */
 state.diffStatsFor = function (entry) {
  const rows = this.renderUnifiedDiff(entry.old.source, entry.new.source);
  let adds = 0;
  let removes = 0;
  for (const row of rows) {
   if (row.kind === 'add') adds++;
   else if (row.kind === 'remove') removes++;
  }
  return { adds, removes };
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
  * an array of ``{kind, text, lnoOld, lnoNew}`` rows the panel paints
  * as a tidy two-column unified-diff block.  Line numbers are 1-based
  * and ``null`` when the row doesn't exist on that side.  Not as smart
  * as Monaco's tokenisation but good enough for cell-source deltas
  * which are usually small.
  */
 state.renderUnifiedDiff = function (oldText, newText) {
  const a = (oldText || '').split('\n');
  const b = (newText || '').split('\n');
  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start++;
  let endA = a.length;
  let endB = b.length;
  while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) {
   endA--;
   endB--;
  }
  const rows = [];
  for (let i = 0; i < start; i++) {
   rows.push({ kind: 'context', text: a[i], lnoOld: i + 1, lnoNew: i + 1 });
  }
  for (let i = start; i < endA; i++) {
   rows.push({ kind: 'remove', text: a[i], lnoOld: i + 1, lnoNew: null });
  }
  for (let i = start; i < endB; i++) {
   rows.push({ kind: 'add', text: b[i], lnoOld: null, lnoNew: i + 1 });
  }
  const tailOffsetNew = endB - endA;
  for (let i = endA; i < a.length; i++) {
   rows.push({
    kind: 'context',
    text: a[i],
    lnoOld: i + 1,
    lnoNew: i + 1 + tailOffsetNew,
   });
  }
  return rows;
 };
}
