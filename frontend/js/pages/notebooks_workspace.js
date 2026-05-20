/**
 * Notebooks workspace page Alpine factory.
 *
 * Lists the nested tree from ``/api/notebooks/tree`` (with
 * sessionStorage caching), flattens it for rendering, and exposes
 * four per-row actions:
 *
 *  - ``openEditor(path)`` — navigate to ``/notebooks/edit/{path}``;
 *  - ``schedule(path)`` — hand off to ``/jobs`` create-modal via
 *    prefill query params;
 *  - ``renameNotebook(path)`` — opens the rename modal;
 *  - ``deleteNotebook(path)`` — opens the confirm-delete modal.
 *
 * Plus a top-level ``createNotebook()`` that opens the new-path modal.
 *
 * The underlying API calls live in ``_createNotebookApi`` /
 * ``_renameNotebookApi`` / ``_deleteNotebookApi``; the modals invoke
 * them after client-side validation.  ``notebookDialogs()`` ships the
 * modal state + submit handlers and is spread into the factory return
 * so both halves share the same Alpine ``$data`` proxy.
 *
 * ``bootstrap.js`` re-attaches the factory to
 * ``window.notebookWorkspace`` so the template's
 * ``x-data="notebookWorkspace()"`` resolves unchanged.
 */

import { notebookDialogs } from './notebooks_workspace_dialogs.js';

const STORAGE_KEY = 'pql.notebooks';
const OPEN_KEY = 'pql.notebooks.open';

/**
 * Flatten a nested tree into a list of rows. A row is rendered only
 * when every one of its ancestor directories is open (per `open`).
 * The root directories are always visible.
 */
function flatten(tree, open) {
 const out = [];
 function visit(nodes, depth, ancestorsVisible) {
  for (const n of nodes) {
   if (ancestorsVisible) {
    out.push({
     path: n.path,
     name: n.name,
     kind: n.kind,
     format: n.format || 'ipynb',
     depth: depth,
     parameters_tagged: !!n.parameters_tagged,
    });
   }
   if (n.kind === 'dir' && n.children && n.children.length) {
    const opened = !!open['d:' + n.path];
    visit(n.children, depth + 1, ancestorsVisible && opened);
   }
  }
 }
 visit(tree || [], 0, true);
 return out;
}

export function notebookWorkspace() {
 return {
  ...notebookDialogs(),

  // Phase 98.B — starter-template gallery state.  Kept on the outer
  // factory rather than the dialogs mixin so the field is visible
  // even if the browser's ES-module cache is still serving an older
  // dialogs.js (which has no asset_version-derived URL on the
  // static import).
  templates: [],
  templatesLoaded: false,

  tree: null,
  loading: false,
  error: null,
  open: {},

  isOpen(key) { return !!this.open[key]; },

  toggle(key) {
   this.open[key] = !this.open[key];
   try { sessionStorage.setItem(OPEN_KEY, JSON.stringify(this.open)); } catch (e) {}
  },

  flatRows() { return flatten(this.tree, this.open); },

  async load() {
   try {
    const cached = sessionStorage.getItem(STORAGE_KEY);
    if (cached) this.tree = JSON.parse(cached);
    const openCached = sessionStorage.getItem(OPEN_KEY);
    if (openCached) this.open = JSON.parse(openCached);
   } catch (e) {}

   if (!this.tree) await this.fetchTree();
   else this.fetchTree();
  },

  async reload() {
   try { sessionStorage.removeItem(STORAGE_KEY); } catch (e) {}
   this.tree = null;
   await this.fetchTree();
  },

  async fetchTree() {
   this.loading = true;
   this.error = null;
   try {
    const res = await fetch('/api/notebooks/tree');
    if (!res.ok) {
     const body = await res.json().catch(() => null);
     throw new Error(body?.error?.message || ('HTTP ' + res.status));
    }
    const data = await res.json();
    this.tree = data;
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data)); } catch (e) {}
   } catch (e) {
    if (!this.tree) this.error = 'Failed to load tree: ' + e.message;
   } finally {
    this.loading = false;
   }
  },

  schedule(path) {
   const qs = new URLSearchParams({
    prefill_kind: 'papermill',
    prefill_notebook_path: path,
   });
   window.location.href = '/jobs?' + qs.toString();
  },

  // Path segments include slashes; encodeURI keeps "/" literal while
  // percent-encoding spaces/unicode. /notebooks/edit/{path:path} on
  // the server handles the joined form.
  openEditor(path) {
   window.location.href = '/notebooks/edit/' + encodeURI(path);
  },

  // Public entry points called from the template @click bindings.
  // They simply open the corresponding modal; the modal's submit
  // handler then calls the matching ``_*Api`` method below.
  createNotebook() { this.openCreate(); },
  renameNotebook(path) { this.openRename(path); },
  deleteNotebook(path) { this.openDeleteDialog(path); },

  async _createNotebookApi(path) {
   const res = await window.pqlApi.fetch('/api/notebooks/create', {
    method: 'POST',
    body: { path: path },
   });
   if (!res.ok) return;
   const created = (res.data && res.data.path) || path;
   try { sessionStorage.removeItem(STORAGE_KEY); } catch (e) {}
   this.openEditor(created);
  },

  async _renameNotebookApi(fromPath, toPath) {
   const res = await window.pqlApi.fetch('/api/notebooks/rename', {
    method: 'POST',
    body: { from_path: fromPath, to_path: toPath },
   });
   if (!res.ok) return;
   try { sessionStorage.removeItem(STORAGE_KEY); } catch (e) {}
   if (window.pqlToast) window.pqlToast.success('Renamed.');
   await this.reload();
  },

  async _deleteNotebookApi(path) {
   const qs = new URLSearchParams({ path: path, confirm: 'true' });
   const res = await window.pqlApi.fetch(
    '/api/notebooks/delete?' + qs.toString(),
    { method: 'DELETE' },
   );
   if (!res.ok) return;
   try { sessionStorage.removeItem(STORAGE_KEY); } catch (e) {}
   if (window.pqlToast) window.pqlToast.success('Deleted.');
   await this.reload();
  },
 };
}
