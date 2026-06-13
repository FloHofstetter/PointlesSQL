/**
 * Workspace context-panel Alpine factory.
 *
 * rebuilt around the nested ``/api/notebooks/tree``
 * shape (was a flat 30-item list).  The sidebar now mirrors the
 * full-page workspace UX in a denser column:
 *
 * - Nested folders with click-to-expand chevrons.
 * - Filename search input (case-insensitive substring match,
 *   ancestors of matches are auto-expanded).
 * - Active highlight on both ``/notebooks/workspace?path=…`` and
 *   ``/notebooks/edit/{path}`` so the user always sees which file
 *   is currently open in the editor.
 * - "+ New" button in the header opens the same create-notebook
 *   modal the full page uses (modal partial mounted inside this
 *   factory's scope; ID collision avoided via ``$refs``).
 *
 * Source: ``/api/notebooks/tree`` (admin-only).
 */

import { notebookDialogs } from '../../pages/notebooks_workspace_dialogs.js';
import { notebookModalApis } from '../notebook_modal_apis.js';
import { installWorkspaceContextMenu } from '../workspace_context_menu.js';
import { installWorkspaceDnd } from '../workspace_dnd.js';
import { makeSidebar } from './_base.js';

const OPEN_KEY = 'pql.workspace.sidebar.open';

function activePathFromUrl() {
  const path = window.location.pathname;
  if (path === '/notebooks/workspace') {
    const params = new URLSearchParams(window.location.search);
    return params.get('path') || '';
  }
  if (path.startsWith('/notebooks/edit/')) {
    try {
      return decodeURI(path.slice('/notebooks/edit/'.length));
    } catch {
      return path.slice('/notebooks/edit/'.length);
    }
  }
  return '';
}

function leafName(p) {
  const i = (p || '').lastIndexOf('/');
  return i >= 0 ? p.slice(i + 1) : p;
}

function parentDir(p) {
  const i = (p || '').lastIndexOf('/');
  return i >= 0 ? p.slice(0, i) : '';
}

function ancestorPaths(p) {
  const out = [];
  let cur = parentDir(p);
  while (cur) {
    out.push(cur);
    cur = parentDir(cur);
  }
  return out;
}

function collectMatches(tree, query) {
  const out = new Set();
  const auto = new Set();
  const q = query.toLowerCase();
  const walk = (nodes) => {
    for (const n of nodes || []) {
      if (n.kind === 'notebook' && leafName(n.path).toLowerCase().includes(q)) {
        out.add(n.path);
        for (const anc of ancestorPaths(n.path)) auto.add(anc);
      }
      if (n.kind === 'dir' && n.children) walk(n.children);
    }
  };
  walk(tree);
  return { matches: out, autoOpen: auto };
}

function flattenForRender(tree, openSet) {
  const out = [];
  const walk = (nodes, depth) => {
    for (const n of nodes || []) {
      out.push({
        path: n.path,
        name: n.name || leafName(n.path),
        kind: n.kind,
        format: n.format || '',
        depth: depth,
        parameters_tagged: !!n.parameters_tagged,
      });
      if (n.kind === 'dir' && n.children && openSet.has(n.path)) {
        walk(n.children, depth + 1);
      }
    }
  };
  walk(tree, 0);
  return out;
}

export function workspaceSidebar() {
  const base = makeSidebar({
    endpoint: '/api/notebooks/tree',
    storageKey: 'pql.workspace.tree',
    itemsPath: (d) => (Array.isArray(d) ? d : d?.tree || []),
    transform: null,
    cap: null,
    activeKey: 'activePath',
    activeFromUrl: activePathFromUrl,
    methods: {
      // Spread modal state + handlers so the modal partial
      // mounted inside this factory's scope finds everything
      // it needs (pathDialog / deleteDialog / templates / …).
      ...notebookDialogs(),
      ...notebookModalApis(),

      // Tree expansion + search state.
      open: {},
      searchQuery: '',

      initWorkspaceSidebar() {
        try {
          const cached = sessionStorage.getItem(OPEN_KEY);
          if (cached) this.open = JSON.parse(cached);
        } catch {}
        // Auto-expand ancestors of the currently-active file
        // so the user lands on a visible row after navigation.
        if (this.activePath) {
          for (const anc of ancestorPaths(this.activePath)) {
            this.open[anc] = true;
          }
        }
      },

      isOpen(path) {
        return !!this.open[path];
      },

      toggle(path) {
        this.open[path] = !this.open[path];
        try {
          sessionStorage.setItem(OPEN_KEY, JSON.stringify(this.open));
        } catch {}
      },

      filteredRows() {
        const tree = this.items || [];
        const q = (this.searchQuery || '').trim();
        if (!q) return flattenForRender(tree, this._openSet());
        const { matches, autoOpen } = collectMatches(tree, q);
        if (matches.size === 0) return [];
        // Union user-toggled opens + filter auto-opens so
        // matched files surface without persisting churn.
        const merged = new Set([...this._openSet(), ...autoOpen]);
        const rows = flattenForRender(tree, merged);
        // Keep only matched notebooks + folders that lie on
        // the path to at least one match (i.e. were marked
        // as auto-open).  Folders elsewhere are off-topic.
        return rows.filter((r) => {
          if (r.kind === 'notebook') return matches.has(r.path);
          return autoOpen.has(r.path);
        });
      },

      _openSet() {
        return new Set(Object.keys(this.open).filter((k) => this.open[k]));
      },

      isActive(path) {
        return path === this.activePath;
      },

      iconClassFor(row) {
        if (row.kind === 'dir') return 'bi-folder2';
        if (row.format === 'py') return 'bi-journal-code text-info';
        return 'bi-journal-code';
      },

      formatBadge(format) {
        if (format === 'py') return 'bg-info-subtle text-info-emphasis';
        if (format === 'ipynb') return 'bg-secondary-subtle text-secondary-emphasis';
        return 'bg-secondary-subtle text-secondary-emphasis';
      },

      hrefFor(row) {
        if (row.kind === 'dir') return '#';
        // The in-browser editor only handles .py (jupytext Percent)
        // notebooks; an .ipynb path 422s there. Point .ipynb rows at the
        // workspace browser instead, where they can be scheduled or run.
        if (row.format !== 'py') {
          return '/notebooks/workspace?path=' + encodeURI(row.path);
        }
        return '/notebooks/edit/' + encodeURI(row.path);
      },

      onRowClick(ev, row) {
        if (row.kind === 'dir') {
          ev.preventDefault();
          this.toggle(row.path);
        }
        // Notebooks: let the <a href> take over (browser navigation).
      },

      createNotebook() {
        this.openCreate();
      },

      renameNotebook(path) {
        this.openRename(path);
      },
      deleteNotebook(path) {
        this.openDeleteDialog(path);
      },
      openEditor(path) {
        window.location.href = '/notebooks/edit/' + encodeURI(path);
      },
      schedule(path) {
        const qs = new URLSearchParams({
          prefill_kind: 'papermill',
          prefill_notebook_path: path,
        });
        window.location.href = '/jobs?' + qs.toString();
      },

      clearSearch() {
        this.searchQuery = '';
      },

      // Refresh hook fired by the shared modal APIs after
      // create / rename / delete.  Re-fetches the tree so the
      // sidebar sees the mutation immediately.
      onTreeChanged() {
        this.reload();
      },
    },
  });
  installWorkspaceContextMenu(base, { surface: 'sidebar' });
  installWorkspaceDnd(base);
  return base;
}
