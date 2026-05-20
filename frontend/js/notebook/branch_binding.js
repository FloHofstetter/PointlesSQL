/**
 * Branch-binding picker (Phase 102 UI).
 *
 * Backend (REST + 11 pytest) shipped in Phase 102 (migration
 * ``311c87f25421``); only the editor wiring was deferred.  This
 * mixin exposes a toolbar dropdown with three states:
 *
 *   * **No binding** — show "Bind to branch" button.
 *   * **Pending binding** — show branch name + Promote / Discard.
 *   * **Promoted binding** — show branch name + Unbind (discard).
 *
 * Loading happens lazily on first open so the editor's initial load
 * isn't blocked by a synchronous round-trip.  History is fetched on
 * demand and rendered inline below the active card.
 */

export function installBranchBinding(state) {
 state.branchBinding = {
  open: false,
  current: null,
  history: [],
  loaded: false,
  historyLoaded: false,
  loading: false,
  submitting: false,
  error: '',
  draftName: '',
  draftRevision: '',
 };

 /**
  * Toggle the popover; lazy-loads on first open.
  */
 state.toggleBranchBinding = async function () {
  this.branchBinding.open = !this.branchBinding.open;
  if (this.branchBinding.open && !this.branchBinding.loaded) {
   await this.loadBranchBinding();
  }
 };

 /**
  * Fetch the active binding (or ``null``) for this notebook path.
  */
 state.loadBranchBinding = async function () {
  if (!this.path) return;
  this.branchBinding.loading = true;
  this.branchBinding.error = '';
  try {
   const res = await window.pqlApi.fetch(
    `/api/notebooks/branch?path=${encodeURIComponent(this.path)}`,
    { silent: true },
   );
   if (res.ok && res.data) {
    this.branchBinding.current = res.data.current || null;
    this.branchBinding.loaded = true;
   } else {
    this.branchBinding.error =
     (res.data && res.data.detail) || `HTTP ${res.status}`;
   }
  } catch (err) {
   this.branchBinding.error = (err && err.message) || String(err);
  } finally {
   this.branchBinding.loading = false;
  }
 };

 /**
  * Lazy-load historical bindings (newest first).
  */
 state.loadBranchHistory = async function () {
  if (!this.path) return;
  this.branchBinding.error = '';
  try {
   const res = await window.pqlApi.fetch(
    `/api/notebooks/branch/history?path=${encodeURIComponent(this.path)}`,
    { silent: true },
   );
   if (res.ok && res.data) {
    this.branchBinding.history = res.data.bindings || [];
    this.branchBinding.historyLoaded = true;
   } else {
    this.branchBinding.error =
     (res.data && res.data.detail) || `HTTP ${res.status}`;
   }
  } catch (err) {
   this.branchBinding.error = (err && err.message) || String(err);
  }
 };

 /**
  * POST a new binding from the draft form fields.  Server validates
  * the branch name; refresh both the current binding + history once
  * the call returns 201.
  */
 state.submitBranchBinding = async function () {
  const branchName = (this.branchBinding.draftName || '').trim();
  if (!branchName) return;
  if (this.branchBinding.submitting) return;
  this.branchBinding.submitting = true;
  this.branchBinding.error = '';
  try {
   const body = { path: this.path, branch_name: branchName };
   const rev = (this.branchBinding.draftRevision || '').trim();
   if (rev) body.base_revision_uuid = rev;
   const res = await window.pqlApi.fetch('/api/notebooks/branch', {
    method: 'POST',
    body,
   });
   if (!res.ok) {
    this.branchBinding.error =
     (res.data && res.data.detail) || `HTTP ${res.status}`;
    return;
   }
   this.branchBinding.draftName = '';
   this.branchBinding.draftRevision = '';
   await this.loadBranchBinding();
   if (this.branchBinding.historyLoaded) await this.loadBranchHistory();
  } catch (err) {
   this.branchBinding.error = (err && err.message) || String(err);
  } finally {
   this.branchBinding.submitting = false;
  }
 };

 /**
  * Promote the active binding (human-reviewed gate).  Idempotent
  * once promoted on the server.
  */
 state.promoteBranchBinding = async function () {
  if (this.branchBinding.submitting) return;
  this.branchBinding.submitting = true;
  this.branchBinding.error = '';
  try {
   const res = await window.pqlApi.fetch(
    '/api/notebooks/branch/promote',
    { method: 'POST', body: { path: this.path } },
   );
   if (!res.ok) {
    this.branchBinding.error =
     (res.data && res.data.detail) || `HTTP ${res.status}`;
    return;
   }
   await this.loadBranchBinding();
   if (this.branchBinding.historyLoaded) await this.loadBranchHistory();
  } catch (err) {
   this.branchBinding.error = (err && err.message) || String(err);
  } finally {
   this.branchBinding.submitting = false;
  }
 };

 /**
  * Discard the active binding.  Server returns 200 with ``{discarded: row}``
  * (or ``{discarded: null}`` when no binding existed).
  */
 state.discardBranchBinding = async function () {
  if (this.branchBinding.submitting) return;
  this.branchBinding.submitting = true;
  this.branchBinding.error = '';
  try {
   const res = await window.pqlApi.fetch(
    `/api/notebooks/branch?path=${encodeURIComponent(this.path)}`,
    { method: 'DELETE' },
   );
   if (!res.ok) {
    this.branchBinding.error =
     (res.data && res.data.detail) || `HTTP ${res.status}`;
    return;
   }
   await this.loadBranchBinding();
   if (this.branchBinding.historyLoaded) await this.loadBranchHistory();
  } catch (err) {
   this.branchBinding.error = (err && err.message) || String(err);
  } finally {
   this.branchBinding.submitting = false;
  }
 };
}
