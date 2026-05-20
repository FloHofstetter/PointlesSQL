/**
 * Replays / scenario-mode panel (Phase 103 UI).
 *
 * Backend ships ``GET /api/notebooks/replays`` + per-replay envelope
 * + diff endpoint.  This mixin exposes a panel that lists recent
 * replays (newest first) and lets the user expand a row to view the
 * cell-by-cell diff envelope.  The kernel re-execution worker is
 * deferred — the diff classifier currently reports any captured
 * outputs against the base revision.
 */

export function installReplays(state) {
 state.replays = {
  open: false,
  rows: [],
  loaded: false,
  loading: false,
  error: '',
  expandedUuid: '',
  diffByUuid: {},
  diffLoading: {},
  draftRevision: '',
  draftBranch: '',
  submitting: false,
 };

 state.toggleReplaysPanel = async function () {
  this.replays.open = !this.replays.open;
  if (this.replays.open && !this.replays.loaded) {
   await this.loadReplays();
  }
 };

 state.loadReplays = async function () {
  if (!this.path) return;
  this.replays.loading = true;
  this.replays.error = '';
  try {
   const res = await window.pqlApi.fetch(
    `/api/notebooks/replays?path=${encodeURIComponent(this.path)}`,
    { silent: true },
   );
   if (res.ok && res.data) {
    this.replays.rows = res.data.replays || [];
    this.replays.loaded = true;
   } else {
    this.replays.error =
     (res.data && res.data.detail) || `HTTP ${res.status}`;
   }
  } catch (err) {
   this.replays.error = (err && err.message) || String(err);
  } finally {
   this.replays.loading = false;
  }
 };

 /**
  * Insert a fresh replay row (worker would pick it up + populate
  * outputs).  Backend creates the row in ``pending`` state.
  */
 state.startReplay = async function () {
  const rev = (this.replays.draftRevision || '').trim();
  if (!rev) return;
  if (this.replays.submitting) return;
  this.replays.submitting = true;
  this.replays.error = '';
  try {
   const body = { path: this.path, base_revision_uuid: rev };
   const branch = (this.replays.draftBranch || '').trim();
   if (branch) body.branch_name = branch;
   const res = await window.pqlApi.fetch('/api/notebooks/replay', {
    method: 'POST',
    body,
   });
   if (!res.ok) {
    this.replays.error =
     (res.data && res.data.detail) || `HTTP ${res.status}`;
    return;
   }
   this.replays.draftRevision = '';
   this.replays.draftBranch = '';
   await this.loadReplays();
  } catch (err) {
   this.replays.error = (err && err.message) || String(err);
  } finally {
   this.replays.submitting = false;
  }
 };

 /**
  * Toggle the diff drawer for one row; lazy-loads the diff envelope
  * the first time a row is expanded.
  */
 state.toggleReplayDiff = async function (replayUuid) {
  if (!replayUuid) return;
  if (this.replays.expandedUuid === replayUuid) {
   this.replays.expandedUuid = '';
   return;
  }
  this.replays.expandedUuid = replayUuid;
  if (this.replays.diffByUuid[replayUuid]) return;
  this.replays.diffLoading[replayUuid] = true;
  try {
   const res = await window.pqlApi.fetch(
    `/api/notebooks/replay/${encodeURIComponent(replayUuid)}/diff`,
    { silent: true },
   );
   if (res.ok && res.data) {
    this.replays.diffByUuid[replayUuid] = res.data;
   } else {
    this.replays.error =
     (res.data && res.data.detail) || `HTTP ${res.status}`;
   }
  } catch (err) {
   this.replays.error = (err && err.message) || String(err);
  } finally {
   this.replays.diffLoading[replayUuid] = false;
  }
 };
}
