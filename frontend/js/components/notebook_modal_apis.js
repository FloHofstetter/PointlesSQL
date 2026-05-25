/**
 * Shared notebook CRUD API mixin.
 *
 * The three REST helpers (``_createNotebookApi``,
 * ``_renameNotebookApi``, ``_deleteNotebookApi``) used by the
 * ``notebookDialogs()`` mixin's submit handlers.  Spread into any
 * factory that also spreads ``notebookDialogs()`` so the modal
 * submit path resolves both halves on the same ``$data`` proxy.
 *
 * extracted from ``notebooks_workspace.js`` so the
 * workspace sidebar factory can mount its own copy of
 * ``notebook_modals.html`` without duplicating these methods.
 */

const STORAGE_KEY = 'pql.notebooks';

export function notebookModalApis() {
  return {
    async _createNotebookApi(path) {
      const res = await window.pqlApi.fetch('/api/notebooks/create', {
        method: 'POST',
        body: { path: path },
      });
      if (!res.ok) return;
      const created = (res.data && res.data.path) || path;
      try {
        sessionStorage.removeItem(STORAGE_KEY);
      } catch (e) {}
      window.location.href = '/notebooks/edit/' + encodeURI(created);
    },

    async _renameNotebookApi(fromPath, toPath) {
      const res = await window.pqlApi.fetch('/api/notebooks/rename', {
        method: 'POST',
        body: { from_path: fromPath, to_path: toPath },
      });
      if (!res.ok) return;
      try {
        sessionStorage.removeItem(STORAGE_KEY);
      } catch (e) {}
      if (window.pqlToast) window.pqlToast.success('Renamed.');
      // The hosting factory may want to refresh its own view; fire an
      // event so both the workspace-page factory and the sidebar can
      // reload independently.
      window.dispatchEvent(
        new CustomEvent('pql:workspace:tree-changed', {
          detail: { kind: 'rename', from: fromPath, to: toPath },
        })
      );
    },

    async _deleteNotebookApi(path) {
      const qs = new URLSearchParams({ path: path, confirm: 'true' });
      const res = await window.pqlApi.fetch('/api/notebooks/delete?' + qs.toString(), {
        method: 'DELETE',
      });
      if (!res.ok) return;
      try {
        sessionStorage.removeItem(STORAGE_KEY);
      } catch (e) {}
      if (window.pqlToast) window.pqlToast.success('Deleted.');
      window.dispatchEvent(
        new CustomEvent('pql:workspace:tree-changed', {
          detail: { kind: 'delete', path },
        })
      );
    },
  };
}
