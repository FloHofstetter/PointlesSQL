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
        } catch (e) { return []; }
    }
    function push(kind, label, url) {
        const items = readRecent().filter(r => r.url !== url);
        items.unshift({ kind, label, url, ts: Date.now() });
        if (items.length > MAX) items.length = MAX;
        try { localStorage.setItem(KEY, JSON.stringify(items)); } catch (e) {}
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
            const url = `/tables/${encodeURIComponent(t)}/rows/${encodeURIComponent(id)}/trace`;
            push('row', `${t} · row ${id}`, url);
            window.location.href = url;
        },
        goColumn() {
            const t = this.colTable.trim();
            const c = this.colName.trim();
            if (!t || !c) return;
            const url = `/tables/${encodeURIComponent(t)}/columns/${encodeURIComponent(c)}/trace`;
            push('column', `${t} · ${c}`, url);
            window.location.href = url;
        },
        clearRecent() {
            try { localStorage.removeItem(KEY); } catch (e) {}
            this.recent = [];
        },
    };
};
