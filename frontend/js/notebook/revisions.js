/**
 * Revision history + cell-diff panel.
 *
 * Backend shipped the revision-history surface; the editor's
 * "History" panel render was deferred behind the nested-x-data
 * trap.  This install*-mixin wires the existing REST surface
 * (``/api/notebooks/revisions{,/diff,/{uuid}}``) to a toolbar
 * drawer.
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
  // inline "Pin as fact" dialog per revision row.
  // ``revisionUuid`` keys the active row; empty when the dialog is
  // closed.  ``factsByRevision`` is a lazy cache keyed by revision
  // UUID so the "📌 pinned" badge knows which rows already carry a
  // whole-revision fact.
  pinDialog: {
   revisionUuid: '',
   title: '',
   description: '',
   busy: false,
   error: '',
  },
  factsByRevision: {},
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
    // Refresh the per-revision fact lookup in lockstep so the row's
    // "📌 pinned" badge stays in sync with the list.
    await this.loadFactsByRevision();
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
  * Fetch the workspace's active facts filtered to this notebook and
  * group by ``revision_id`` so each revision row can show "📌 pinned".
  * Cheap one-shot GET — the list is naturally small (50/page) so we
  * skip the bulk endpoint and reuse the human-browse list endpoint.
  */
 state.loadFactsByRevision = async function () {
  if (!this.path) return;
  try {
   const qs = new URLSearchParams({ notebook_path: this.path, limit: '200' });
   const res = await window.pqlApi.fetch(
    `/api/notebooks/facts?${qs.toString()}`,
    { silent: true },
   );
   if (!res.ok || !res.data) {
    this.revisions.factsByRevision = {};
    return;
   }
   const map = {};
   for (const fact of res.data.facts || []) {
    // Only count whole-revision facts (cell-output facts surface
    // in the cell-header chip strip instead).
    if (fact.cell_content_hash) continue;
    const key = String(fact.revision_id);
    if (!map[key]) map[key] = [];
    map[key].push(fact);
   }
   this.revisions.factsByRevision = map;
  } catch (_) {
   this.revisions.factsByRevision = {};
  }
 };

 /**
  * Return the active whole-revision fact for a row, or ``null`` when
  * the revision is unpinned.  Template-friendly truthy / falsy check.
  */
 state.factForRevision = function (revisionRow) {
  if (!revisionRow) return null;
  const key = String(revisionRow.id ?? '');
  // Backend envelope already includes ``revision_id``; the list
  // endpoint omits the FK so we fall back to UUID-keyed lookup when
  // a row only carries ``revision_uuid``.
  if (key && this.revisions.factsByRevision[key]) {
   return this.revisions.factsByRevision[key][0] || null;
  }
  // Fallback: scan the cached map for a fact whose envelope includes
  // a matching ``revision_uuid``.  Slow but called once per row.
  for (const facts of Object.values(this.revisions.factsByRevision)) {
   for (const f of facts) {
    if (f.revision_uuid === revisionRow.revision_uuid) return f;
   }
  }
  return null;
 };

 /**
  * Open the inline pin-as-fact dialog rooted on a revision row.
  */
 state.openRevisionPinDialog = function (revisionUuid) {
  if (!revisionUuid) return;
  this.revisions.pinDialog = {
   revisionUuid,
   title: '',
   description: '',
   busy: false,
   error: '',
  };
 };

 state.cancelRevisionPinDialog = function () {
  this.revisions.pinDialog = {
   revisionUuid: '',
   title: '',
   description: '',
   busy: false,
   error: '',
  };
 };

 state.confirmRevisionPin = async function () {
  const dlg = this.revisions.pinDialog;
  if (!dlg.revisionUuid || !dlg.title || dlg.busy) return;
  dlg.busy = true;
  dlg.error = '';
  try {
   const res = await window.pqlApi.fetch('/api/notebooks/facts', {
    method: 'POST',
    body: {
     revision_uuid: dlg.revisionUuid,
     title: dlg.title,
     description_md: dlg.description || null,
    },
   });
   if (!res.ok) {
    dlg.error = (res.data && res.data.detail) || `HTTP ${res.status}`;
    return;
   }
   this.cancelRevisionPinDialog();
   await this.loadFactsByRevision();
  } catch (err) {
   dlg.error = (err && err.message) || String(err);
  } finally {
   dlg.busy = false;
  }
 };

 state.unpinRevisionFact = async function (revisionRow) {
  const fact = this.factForRevision(revisionRow);
  if (!fact || !fact.fact_uuid) return;
  try {
   const res = await window.pqlApi.fetch(
    `/api/notebooks/facts/${encodeURIComponent(fact.fact_uuid)}`,
    { method: 'DELETE' },
   );
   if (!res.ok) {
    this.revisions.error = (res.data && res.data.detail) || `HTTP ${res.status}`;
    return;
   }
   await this.loadFactsByRevision();
  } catch (err) {
   this.revisions.error = (err && err.message) || String(err);
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
