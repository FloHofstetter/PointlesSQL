// Auto-extracted from frontend/templates/pages/lineage_index.html.
// Exports: lineageExplorerForm.
//
// Lineage explorer Alpine factory — localStorage-backed recent
// traces.  Trace forms redirect into the existing per-row /
// per-column pages; the factory records each navigation here
// so the "Recent traces" card surfaces them.
export function lineageExplorerForm() {
  const KEY = 'pql.recentTraces';
  const MAX = 10;

  function readRecent() {
    try {
      const raw = localStorage.getItem(KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
      return [];
    }
  }
  function push(kind, label, url) {
    const items = readRecent().filter((r) => r.url !== url);
    items.unshift({ kind, label, url, ts: Date.now() });
    if (items.length > MAX) items.length = MAX;
    try {
      localStorage.setItem(KEY, JSON.stringify(items));
    } catch (e) {}
  }

  // The trace pages live under the split FQN path
  // (/catalogs/<c>/schemas/<s>/tables/<t>/…), not /tables/<fqn>/… — a
  // single-segment /tables/<fqn> route doesn't exist and 404s. Split the
  // three-part name and build the real path.
  function tableBasePath(fqn) {
    const parts = fqn.split('.');
    if (parts.length !== 3 || !parts.every((p) => p.length > 0)) return null;
    const [cat, schema, table] = parts.map(encodeURIComponent);
    return `/catalogs/${cat}/schemas/${schema}/tables/${table}`;
  }

  return {
    rowTable: '',
    rowId: '',
    colTable: '',
    colName: '',
    recent: [],
    loadRecent() {
      this.recent = readRecent();
    },
    goRow() {
      const t = this.rowTable.trim();
      const id = this.rowId.trim();
      if (!t || !id) return;
      const base = tableBasePath(t);
      if (!base) return;
      const url = `${base}/rows/${encodeURIComponent(id)}/trace`;
      push('row', `${t} · row ${id}`, url);
      window.location.href = url;
    },
    goColumn() {
      const t = this.colTable.trim();
      const c = this.colName.trim();
      if (!t || !c) return;
      const base = tableBasePath(t);
      if (!base) return;
      const url = `${base}/columns/${encodeURIComponent(c)}/trace`;
      push('column', `${t} · ${c}`, url);
      window.location.href = url;
    },
    clearRecent() {
      try {
        localStorage.removeItem(KEY);
      } catch (e) {}
      this.recent = [];
    },
  };
}
