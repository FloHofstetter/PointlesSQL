/**
 * Notebook editor — co-edit lifecycle mixin (Phase 105.3 scaffold).
 *
 * Spins up :func:`createCoeditClient` after the notebook's
 * ``notebook_uuid`` lands, keeps a single status field
 * (``coeditStatus``) that the toolbar binds to for the live pill,
 * and tears the client down on ``destroy()``.
 *
 * The client itself is the passive scaffold from
 * ``./coedit_client.js`` — Y.Doc stays in sync with the server but
 * is not yet bound to the per-cell CodeMirror views.  That wiring
 * lands in Phase 105.3b once the save-path barrier (Phase 105.5)
 * has solved the cell_uuid reconciler race.
 */

import { createCoeditClient } from './coedit_client.js';

export function installCoeditLifecycle(state) {
  state.coeditStatus = 'idle';
  state._coedit = null;

  state._initCoedit = function () {
    if (this._coedit) return;
    if (!this.notebookUuid) return;
    this._coedit = createCoeditClient({
      notebookUuid: this.notebookUuid,
      onStatusChange: (next) => { this.coeditStatus = next; },
    });
    this._coedit.connect();
  };

  state._teardownCoedit = function () {
    if (!this._coedit) return;
    try { this._coedit.close(); } catch (_e) { /* swallow */ }
    this._coedit = null;
    this.coeditStatus = 'idle';
  };

  state.coeditLabel = function () {
    switch (this.coeditStatus) {
      case 'live': return 'Live';
      case 'connecting': return 'Connecting…';
      case 'offline': return 'Reconnecting…';
      case 'unauthorized': return 'View-only';
      case 'error': return 'Unavailable';
      default: return 'Offline';
    }
  };

  state.coeditDotClass = function () {
    switch (this.coeditStatus) {
      case 'live': return 'bg-success';
      case 'connecting':
      case 'offline': return 'bg-warning';
      case 'unauthorized': return 'bg-secondary';
      case 'error': return 'bg-danger';
      default: return 'bg-secondary';
    }
  };

  state.coeditTooltip = function () {
    switch (this.coeditStatus) {
      case 'live': return 'Co-edit channel connected — changes sync across open tabs.';
      case 'connecting': return 'Opening co-edit channel…';
      case 'offline': return 'Co-edit channel dropped — reconnecting.';
      case 'unauthorized': return 'You are viewing this notebook in read-only mode.';
      case 'error': return 'Co-edit channel unavailable on this host.';
      default: return 'Co-edit channel idle.';
    }
  };
}
