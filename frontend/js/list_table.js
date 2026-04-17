/*
 * PointlesSQL list-table helper — Sprint 33.
 *
 * Wraps a Bootstrap `<table>` with debounced client-side search,
 * sortable column headers, and optional filter chips. Progressive
 * enhancement: the server always renders the full table; if JS
 * never runs (or fails to load), rows remain visible and the page
 * is still usable.
 *
 * Usage:
 *   <div x-data="listTable({
 *       searchPlaceholder: 'Search jobs…',
 *       chips: [
 *           { id: 'paused', label: 'Paused',
 *             match: (tr) => tr.dataset.paused === '1' },
 *       ],
 *       initialSort: { key: 'name', dir: 'asc' },
 *   })">
 *       <div class="pql-list-controls">
 *           <input type="search" class="form-control"
 *                  x-ref="search" x-model="query" x-on:input="onInput()">
 *           <template x-for="chip in chips" :key="chip.id">
 *               <button type="button" class="pql-chip"
 *                       :class="activeChips[chip.id] ? 'pql-chip--active' : ''"
 *                       x-on:click="toggleChip(chip.id)"
 *                       x-text="chip.label"></button>
 *           </template>
 *       </div>
 *       <table class="table"> ... </table>
 *   </div>
 *
 * Data contract:
 *   - Each `<tr>` in `<tbody>` may carry `data-search` (lowercased
 *     space-separated tokens) and `data-sort-<key>` attributes for
 *     each sortable column.
 *   - Each sortable `<th>` carries `data-sort-key="<key>"`. The
 *     helper rewrites those headers into buttons with `aria-sort`
 *     indicators on mount; cycling is asc → desc → none.
 *   - The "no results" fallback is injected once as a sibling of
 *     the table; it uses the component's configured `emptyMessage`.
 */
window.listTable = function (config) {
    const cfg = config || {};
    const chips = Array.isArray(cfg.chips) ? cfg.chips : [];
    const initialSort = cfg.initialSort || null;
    const emptyMessage = cfg.emptyMessage || 'No results.';
    const debounceMs = Number.isFinite(cfg.debounceMs) ? cfg.debounceMs : 150;

    const activeChips = {};
    for (const c of chips) activeChips[c.id] = false;

    return {
        query: '',
        chips,
        activeChips,
        sortKey: initialSort ? initialSort.key : null,
        sortDir: initialSort ? initialSort.dir : 'asc',
        searchPlaceholder: cfg.searchPlaceholder || 'Search…',
        emptyMessage,
        _rows: [],
        _tbody: null,
        _emptyEl: null,
        _debounceTimer: null,

        init() {
            const table = this.$root.querySelector('table');
            if (!table) return;
            const tbody = table.tBodies[0];
            if (!tbody) return;
            this._tbody = tbody;
            this._rows = Array.from(tbody.rows);

            // Wire sortable headers.
            const heads = table.tHead
                ? Array.from(table.tHead.querySelectorAll('th[data-sort-key]'))
                : [];
            for (const th of heads) {
                const key = th.getAttribute('data-sort-key');
                if (!key) continue;
                th.classList.add('pql-sortable');
                th.setAttribute('role', 'button');
                th.setAttribute('tabindex', '0');
                th.setAttribute('aria-sort', 'none');
                th.addEventListener('click', () => this.toggleSort(key));
                th.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        this.toggleSort(key);
                    }
                });
            }
            this._reflectSortUi();

            // Empty-state sibling.
            const empty = document.createElement('div');
            empty.className = 'pql-list-empty text-muted small fst-italic p-3';
            empty.textContent = this.emptyMessage;
            empty.hidden = true;
            table.parentNode.insertBefore(empty, table.nextSibling);
            this._emptyEl = empty;

            // Initial paint.
            if (this.sortKey) this._applySort();
            this._applyFilter();
        },

        onInput() {
            if (this._debounceTimer) clearTimeout(this._debounceTimer);
            this._debounceTimer = setTimeout(() => this._applyFilter(), debounceMs);
        },

        toggleChip(id) {
            this.activeChips[id] = !this.activeChips[id];
            this._applyFilter();
        },

        toggleSort(key) {
            if (this.sortKey !== key) {
                this.sortKey = key;
                this.sortDir = 'asc';
            } else if (this.sortDir === 'asc') {
                this.sortDir = 'desc';
            } else {
                this.sortKey = null;
                this.sortDir = 'asc';
            }
            this._applySort();
            this._reflectSortUi();
            this._applyFilter();
        },

        _reflectSortUi() {
            const heads = this.$root.querySelectorAll('th[data-sort-key]');
            heads.forEach((th) => {
                const key = th.getAttribute('data-sort-key');
                if (key === this.sortKey) {
                    th.setAttribute('aria-sort',
                        this.sortDir === 'desc' ? 'descending' : 'ascending');
                } else {
                    th.setAttribute('aria-sort', 'none');
                }
            });
        },

        _coerce(raw) {
            if (raw == null) return { kind: 'str', value: '' };
            if (/^-?\d+(\.\d+)?$/.test(raw)) {
                const n = Number(raw);
                if (Number.isFinite(n)) return { kind: 'num', value: n };
            }
            // ISO-8601-ish: YYYY-MM-DD optionally followed by a time.
            if (/^\d{4}-\d{2}-\d{2}/.test(raw)) {
                const t = Date.parse(raw);
                if (!Number.isNaN(t)) return { kind: 'num', value: t };
            }
            return { kind: 'str', value: String(raw).toLowerCase() };
        },

        _applySort() {
            if (!this.sortKey || !this._tbody) return;
            const attr = 'data-sort-' + this.sortKey;
            const dir = this.sortDir === 'desc' ? -1 : 1;
            const sorted = this._rows.slice().sort((a, b) => {
                const av = this._coerce(a.getAttribute(attr));
                const bv = this._coerce(b.getAttribute(attr));
                // Empty strings sort to the end, regardless of direction.
                if (av.kind === 'str' && av.value === '' && bv.value !== '') return 1;
                if (bv.kind === 'str' && bv.value === '' && av.value !== '') return -1;
                if (av.value < bv.value) return -1 * dir;
                if (av.value > bv.value) return 1 * dir;
                return 0;
            });
            // Reappend in sorted order — detached rows are moved, not copied.
            const frag = document.createDocumentFragment();
            for (const tr of sorted) frag.appendChild(tr);
            this._tbody.appendChild(frag);
            this._rows = sorted;
        },

        _matches(tr) {
            const q = this.query.trim().toLowerCase();
            if (q) {
                const hay = (tr.getAttribute('data-search') || '').toLowerCase();
                if (hay && !hay.includes(q)) return false;
            }
            for (const chip of this.chips) {
                if (this.activeChips[chip.id] && !chip.match(tr)) return false;
            }
            return true;
        },

        _applyFilter() {
            let visible = 0;
            for (const tr of this._rows) {
                const ok = this._matches(tr);
                tr.hidden = !ok;
                if (ok) visible += 1;
            }
            if (this._emptyEl) this._emptyEl.hidden = visible > 0;
        },
    };
};
