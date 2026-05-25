/**
 * Revision history + snapshot + pin-as-fact panel.
 *
 * Backend shipped the revision-history surface; the editor's
 * "History" panel render was deferred behind the nested-x-data
 * trap.  This install*-mixin wires the existing REST surface
 * (``/api/notebooks/revisions{,/{uuid}}`` + ``/api/notebooks/facts``)
 * to a toolbar drawer.
 *
 * The diff-pair pick + unified-diff render lives in the sibling
 * `revision_diff.js` module; both installers mutate the same
 * `state.revisions` object so the template only sees one source of
 * truth.
 *
 * Snapshot button records a fresh revision (idempotent on the
 * canonical hash so re-snapshotting unchanged state is a no-op).
 */

import { installRevisionDiff } from './revision_diff.js';

export function installRevisions(state) {
 state.revisions = {
  open: false,
  loaded: false,
  loading: false,
  error: '',
  rows: [],
  snapshotMessage: '',
  snapshotting: false,
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

 // Diff-pair pick + unified-diff render live in the sibling module.
 installRevisionDiff(state);
}
