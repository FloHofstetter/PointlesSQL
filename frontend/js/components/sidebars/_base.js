/**
 * Shared base factory for context-panel sidebars.
 *
 * Six section panels (Runs, Branches, Workspace, Jobs, Alerts,
 * MLflow) hit the same shape: hydrate from ``sessionStorage`` for
 * instant first paint, fetch over HTTP, write back, expose
 * ``loading`` + ``error`` state, ``reload()`` to clear and refetch,
 * ``isActive(id)`` against the current URL, ``relativeTime()`` via
 * ``window.pqlRelativeTime``.
 *
 * This factory absorbs all of that so each section's sidebar is a
 * thin config: endpoint, storage key, list-extractor, optional
 * post-fetch transform, optional grouping, plus an
 * ``activeFromUrl`` reader.  Section-specific helpers
 * (``statusBadgeClass``, ``shortId`` etc.) layer on top via the
 * ``methods`` extension point.
 */

const RELATIVE_TIME_FALLBACK = (iso) =>
    iso ? iso.slice(0, 16).replace('T', ' ') : '';

/**
 * Build an Alpine factory object for a context-panel sidebar.
 *
 * @param {object} cfg
 * @param {string} cfg.endpoint - Fetch URL (e.g. ``/api/runs?limit=15``).
 * @param {string} cfg.storageKey - sessionStorage key (e.g. ``pql.runs.recent``).
 * @param {(data: object) => Array} [cfg.itemsPath] - Pluck the
 *   list out of the response body.  Default: ``d => d.items ?? []``.
 * @param {(items: Array) => Array} [cfg.transform] - Optional
 *   post-fetch step (sort, slice, normalise).  Runs before the
 *   sessionStorage write-back and the ``items`` assignment.
 * @param {number} [cfg.cap=15] - Max items kept after the transform.
 * @param {(items: Array) => object} [cfg.group] - Optional grouping
 *   function exposed as ``grouped()``.  Default returns
 *   ``{ all: items }``.
 * @param {() => unknown} [cfg.activeFromUrl] - Reader for the
 *   currently-active item id.  Default: ``() => null``.
 * @param {string} [cfg.activeKey='activeId'] - Field name on the
 *   factory state where the active id lives.  Lets sections that
 *   key on a different shape (``activeFqn``, ``activeSlug``,
 *   ``activePath``, …) keep their existing template bindings.
 * @param {object} [cfg.methods] - Extra fields / methods spread
 *   onto the factory (e.g. ``statusBadgeClass``, ``shortId``).
 * @returns {object} - Alpine x-data object.
 */
export function makeSidebar(cfg) {
    const {
        endpoint,
        storageKey,
        itemsPath = (d) => d?.items ?? [],
        transform = null,
        cap = 15,
        group = null,
        activeFromUrl = () => null,
        activeKey = 'activeId',
        methods = {},
    } = cfg;

    const factory = {
        items: [],
        loading: false,
        error: null,
        [activeKey]: activeFromUrl(),

        async load() {
            try {
                const cached = sessionStorage.getItem(storageKey);
                if (cached) this.items = JSON.parse(cached);
            } catch (e) { /* quota / disabled storage */ }
            await this.fetch();
        },

        async fetch() {
            this.loading = true;
            this.error = null;
            try {
                const res = await fetch(endpoint);
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                let list = itemsPath(data) || [];
                if (transform) list = transform(list);
                if (cap != null) list = list.slice(0, cap);
                this.items = list;
                try {
                    sessionStorage.setItem(storageKey, JSON.stringify(this.items));
                } catch (e) { /* quota */ }
            } catch (e) {
                if (!this.items.length) this.error = e.message;
            } finally {
                this.loading = false;
            }
        },

        async reload() {
            try { sessionStorage.removeItem(storageKey); } catch (e) {}
            this.items = [];
            await this.fetch();
        },

        grouped() {
            return group ? group(this.items) : { all: this.items };
        },

        relativeTime(iso) {
            if (!iso) return '';
            if (typeof window.pqlRelativeTime === 'function') {
                try { return window.pqlRelativeTime(iso); } catch (e) {}
            }
            return RELATIVE_TIME_FALLBACK(iso);
        },

        isActive(id) {
            return id === this[activeKey];
        },
    };

    return Object.assign(factory, methods);
}
